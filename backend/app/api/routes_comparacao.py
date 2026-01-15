"""
Rotas FastAPI para comparações
Implementa processamento assíncrono para evitar timeout no Render
"""

import logging
import json
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.schemas_comparacao import (
    ComparacaoCreate,
    ComparacaoResumo,
    ComparacaoDetalhe,
    AccountValidationResultSchema,
    AccountValidationSummary,
    DivergenciaSchema,
)
from app.models.plano_contas import AccountValidationResult
from app.models.comparacao import Comparacao, DivergenciaDB
from app.db import get_db, SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparacoes", tags=["comparacoes"])


# ============================================================================
# WORKER DE BACKGROUND - Processa comparação de forma assíncrona
# ============================================================================

def processar_comparacao_background(
    comparacao_id: int,
    otimiza_paths: List[str],
    mpds_path: str,
    bank_source_type: str,
    data_inicio: date,
    data_fim: date,
    temp_dir: str,
):
    """
    Worker que processa a comparação em background.
    Atualiza o status no banco conforme progride.
    
    IMPORTANTE: Este worker NUNCA deve crashar o processo principal.
    Todos os erros são capturados e salvos no banco.
    """
    import time
    import traceback
    start_time = time.time()
    db = None
    
    try:
        # Cria sessão própria (background task não tem acesso à sessão do request)
        db = SessionLocal()
        
        logger.info(f"[BG] Iniciando processamento da comparação {comparacao_id}")
        
        # Atualiza started_at
        comparacao = db.query(Comparacao).filter(Comparacao.id == comparacao_id).first()
        if not comparacao:
            logger.error(f"[BG] Comparação {comparacao_id} não encontrada")
            return
        
        comparacao.started_at = datetime.utcnow()
        db.commit()
        
        # Importa funções de parsing
        from app.services.parsers.otimiza_txt_parser import parse_otimiza_txt
        from app.services.parsers.mpds_csv_parser import parse_mpds_csv
        from app.services.parsers.mpds_ofx_parser import parse_mpds_ofx
        from app.services.parsers.mpds_pdf_parser import parse_mpds_pdf
        from app.services.comparador.motor import compare_bank_vs_txt
        from app.services.validations.account_validation import validate_lancamentos_accounts
        from app.core.divergencias import Divergencia as DivergenciaModelo
        
        all_lancamentos_txt = []
        all_issues_txt = []
        
        # 1) Parse dos TXTs
        logger.info(f"[BG] Parsing de {len(otimiza_paths)} arquivo(s) TXT...")
        txt_start = time.time()
        
        for txt_path in otimiza_paths:
            try:
                lancamentos, issues = parse_otimiza_txt(Path(txt_path), strict=False)
                
                # Normaliza sinal baseado no nome do arquivo
                txt_nome_upper = Path(txt_path).name.upper()
                if "PAGAR" in txt_nome_upper:
                    for lanc in lancamentos:
                        lanc.valor = -abs(lanc.valor)
                elif "RECEBER" in txt_nome_upper:
                    for lanc in lancamentos:
                        lanc.valor = abs(lanc.valor)
                
                all_lancamentos_txt.extend(lancamentos)
                all_issues_txt.extend(issues)
                logger.info(f"[BG] TXT {Path(txt_path).name}: {len(lancamentos)} lançamentos")
            except Exception as e:
                logger.exception(f"[BG] Erro no parsing TXT {txt_path}: {e}")
                all_issues_txt.append(f"Erro em {Path(txt_path).name}: {str(e)}")
        
        logger.info(f"[BG] Parsing TXT concluído em {time.time()-txt_start:.2f}s: {len(all_lancamentos_txt)} lançamentos")
        
        comparacao.qtd_lancamentos_razao = len(all_lancamentos_txt)
        db.commit()
        
        # 2) Parse do extrato bancário
        logger.info(f"[BG] Parsing do extrato {bank_source_type}...")
        pdf_start = time.time()
        
        lanc_mpds = []
        issues_mpds = []
        
        try:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
            
            PDF_TIMEOUT_SECONDS = 30  # Timeout para parsing de PDF
            
            if bank_source_type == 'CSV':
                lanc_mpds, issues_mpds = parse_mpds_csv(Path(mpds_path), strict=False)
            elif bank_source_type == 'OFX':
                lanc_mpds, issues_mpds = parse_mpds_ofx(Path(mpds_path), strict=False)
            elif bank_source_type == 'PDF':
                logger.info(f"[BG] Iniciando parse_mpds_pdf para {mpds_path} (timeout={PDF_TIMEOUT_SECONDS}s)")
                
                # Executa com timeout para evitar travamento
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(parse_mpds_pdf, Path(mpds_path), False)
                    try:
                        lanc_mpds, issues_mpds = future.result(timeout=PDF_TIMEOUT_SECONDS)
                    except FuturesTimeoutError:
                        logger.error(f"[BG] TIMEOUT: parsing PDF demorou mais de {PDF_TIMEOUT_SECONDS}s")
                        raise RuntimeError(f"Timeout: parsing do PDF demorou mais de {PDF_TIMEOUT_SECONDS} segundos")
                
                logger.info(f"[BG] parse_mpds_pdf retornou {len(lanc_mpds)} lançamentos")
            else:
                raise ValueError(f"Formato não suportado: {bank_source_type}")
            
            elapsed = time.time() - pdf_start
            logger.info(f"[BG] Parsing extrato concluído em {elapsed:.2f}s: {len(lanc_mpds)} movimentações")
        except Exception as e:
            elapsed = time.time() - pdf_start
            logger.error(f"[BG] Erro no parsing do extrato após {elapsed:.2f}s: {e}")
            logger.error(f"[BG] Traceback parsing: {traceback.format_exc()}")
            raise RuntimeError(f"Falha no parsing do extrato: {str(e)}")
        
        comparacao.qtd_lancamentos_extrato = len(lanc_mpds)
        comparacao.parsing_issues = json.dumps({
            "txt_issues": all_issues_txt,
            "mpds_issues": issues_mpds
        })
        db.commit()
        
        # 3) Comparação
        logger.info("[BG] Iniciando comparação...")
        cmp_start = time.time()
        
        divergencias: List[DivergenciaModelo] = compare_bank_vs_txt(
            bank_movements=lanc_mpds,
            txt_movements=all_lancamentos_txt,
            date_window_days=2,
            amount_tolerance=0.01,
            min_description_similarity=0.55,
            allow_many_to_one=True,
        )
        
        logger.info(f"[BG] Comparação concluída em {time.time()-cmp_start:.2f}s: {len(divergencias)} divergências")
        
        comparacao.qtd_divergencias = len(divergencias)
        db.commit()
        
        # 4) Salva divergências no banco
        for div in divergencias:
            div_db = DivergenciaDB(
                comparacao_id=comparacao_id,
                tipo=div.tipo.value if hasattr(div.tipo, 'value') else str(div.tipo),
                descricao=div.descricao,
                data_extrato=div.data_extrato,
                descricao_extrato=div.descricao_extrato,
                valor_extrato=div.valor_extrato,
                documento_extrato=div.documento_extrato,
                conta_contabil_extrato=div.conta_contabil_extrato,
                data_dominio=div.data_dominio,
                descricao_dominio=div.descricao_dominio,
                valor_dominio=div.valor_dominio,
                documento_dominio=div.documento_dominio,
                conta_contabil_dominio=div.conta_contabil_dominio,
            )
            db.add(div_db)
        
        db.commit()
        
        # 5) Validação de contas (opcional)
        try:
            all_lancamentos = lanc_mpds + all_lancamentos_txt
            validation_results = validate_lancamentos_accounts(all_lancamentos, db)
            
            for result in validation_results:
                result.comparacao_id = comparacao_id
                db.add(result)
            
            db.commit()
            logger.info(f"[BG] Validação de contas: {len(validation_results)} resultados")
        except Exception as e:
            logger.warning(f"[BG] Validação de contas falhou (não crítico): {e}")
        
        # 6) Finaliza com sucesso
        comparacao.status = "concluida"
        comparacao.finished_at = datetime.utcnow()
        db.commit()
        
        total_time = time.time() - start_time
        logger.info(f"[BG] Comparação {comparacao_id} concluída com sucesso em {total_time:.2f}s")
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[BG] Erro fatal na comparação {comparacao_id}: {error_msg}")
        logger.error(f"[BG] Traceback: {traceback.format_exc()}")
        
        try:
            if db:
                comparacao = db.query(Comparacao).filter(Comparacao.id == comparacao_id).first()
                if comparacao:
                    comparacao.status = "erro"
                    comparacao.erro = error_msg[:500]  # Limita tamanho
                    comparacao.finished_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"[BG] Status de erro salvo para comparação {comparacao_id}")
        except Exception as db_error:
            logger.error(f"[BG] Erro ao salvar status de erro: {db_error}")
    
    finally:
        # Fecha sessão do banco
        if db:
            try:
                db.close()
            except Exception:
                pass
        
        # Limpa arquivos temporários
        try:
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir)
                logger.info(f"[BG] Arquivos temporários removidos: {temp_dir}")
        except Exception as e:
            logger.warning(f"[BG] Erro ao limpar temp: {e}")


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/", response_model=ComparacaoResumo, status_code=201)
async def criar_comparacao(
    background_tasks: BackgroundTasks,
    data_inicio: date = Form(...),
    data_fim: date = Form(...),
    otimiza_txt: UploadFile = File(None),
    otimiza_txt_files: List[UploadFile] = File(None),
    mpds_csv: UploadFile = File(None),
    mpds_ofx: UploadFile = File(None),
    mpds_pdf: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """
    Cria uma nova comparação (processamento assíncrono).
    
    Retorna imediatamente com status="processing".
    Use GET /comparacoes/{id} para verificar o progresso.
    """
    # Validações
    if data_inicio > data_fim:
        raise HTTPException(status_code=400, detail="Data inicial deve ser anterior à data final")
    
    # Coleta arquivos TXT
    otimiza_files = []
    if otimiza_txt_files:
        otimiza_files = [f for f in otimiza_txt_files if f and f.filename]
    elif otimiza_txt and otimiza_txt.filename:
        otimiza_files = [otimiza_txt]
    
    if not otimiza_files:
        raise HTTPException(status_code=400, detail="É necessário fornecer pelo menos um arquivo TXT do Otimiza")
    
    if len(otimiza_files) > 2:
        raise HTTPException(status_code=400, detail="Máximo 2 arquivos TXT permitidos")
    
    # Identifica arquivo bancário
    mpds_file = None
    bank_source_type = None
    
    if mpds_pdf and mpds_pdf.filename:
        mpds_file = mpds_pdf
        bank_source_type = "PDF"
    elif mpds_ofx and mpds_ofx.filename:
        mpds_file = mpds_ofx
        bank_source_type = "OFX"
    elif mpds_csv and mpds_csv.filename:
        mpds_file = mpds_csv
        bank_source_type = "CSV"
    
    if not mpds_file:
        raise HTTPException(status_code=400, detail="É necessário fornecer o extrato bancário (PDF, CSV ou OFX)")
    
    # Cria diretório temporário para os arquivos
    temp_dir = tempfile.mkdtemp(prefix="comparacao_")
    logger.info(f"Criando comparação. Temp dir: {temp_dir}")
    
    try:
        # Salva arquivos TXT
        otimiza_paths = []
        for i, txt_file in enumerate(otimiza_files):
            txt_bytes = await txt_file.read()
            if len(txt_bytes) == 0:
                raise HTTPException(status_code=400, detail=f"Arquivo TXT vazio: {txt_file.filename}")
            
            txt_path = Path(temp_dir) / f"txt_{i}_{txt_file.filename}"
            txt_path.write_bytes(txt_bytes)
            otimiza_paths.append(str(txt_path))
            logger.info(f"TXT salvo: {txt_path} ({len(txt_bytes)} bytes)")
        
        # Salva arquivo bancário
        mpds_bytes = await mpds_file.read()
        if len(mpds_bytes) == 0:
            raise HTTPException(status_code=400, detail="Arquivo de extrato bancário vazio")
        
        mpds_path = Path(temp_dir) / f"extrato_{mpds_file.filename}"
        mpds_path.write_bytes(mpds_bytes)
        logger.info(f"Extrato salvo: {mpds_path} ({len(mpds_bytes)} bytes)")
        
        # Cria registro no banco com status="processing"
        comparacao = Comparacao(
            periodo_inicio=data_inicio,
            periodo_fim=data_fim,
            source_type="OTIMIZA_TXT",
            bank_source_type=bank_source_type,
            status="processing",
            input_files=json.dumps({
                "otimiza_txt_paths": [Path(p).name for p in otimiza_paths],
                "extrato_path": mpds_file.filename,
                "temp_dir": temp_dir
            })
        )
        db.add(comparacao)
        db.commit()
        db.refresh(comparacao)
        
        logger.info(f"Comparação {comparacao.id} criada. Disparando processamento em background...")
        
        # Dispara processamento em background
        background_tasks.add_task(
            processar_comparacao_background,
            comparacao.id,
            otimiza_paths,
            str(mpds_path),
            bank_source_type,
            data_inicio,
            data_fim,
            temp_dir,
        )
        
        # Retorna imediatamente
        return comparacao
        
    except HTTPException:
        # Limpa temp em caso de erro de validação
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.exception(f"Erro ao criar comparação: {e}")
        # Retorna erro com detalhes para o frontend (evita "CORS blocked" por falta de body)
        error_msg = str(e)
        if "column" in error_msg.lower() and "does not exist" in error_msg.lower():
            error_msg = "Erro de banco de dados: schema desatualizado. Reinicie o backend."
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[ComparacaoResumo])
def listar_comparacoes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Lista todas as comparações (mais recentes primeiro)."""
    comparacoes = (
        db.query(Comparacao)
        .order_by(Comparacao.criado_em.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return comparacoes


@router.get("/{comparacao_id}", response_model=ComparacaoDetalhe)
def obter_comparacao(comparacao_id: int, db: Session = Depends(get_db)):
    """
    Obtém detalhes de uma comparação.
    
    - Se status="processing": retorna dados parciais, divergencias=[]
    - Se status="concluida": retorna dados completos
    - Se status="erro": retorna erro em 'erro'
    """
    comparacao = db.query(Comparacao).filter(Comparacao.id == comparacao_id).first()
    
    if not comparacao:
        raise HTTPException(status_code=404, detail="Comparação não encontrada")
    
    # Busca divergências (vazio se ainda processando)
    divergencias = []
    if comparacao.status == "concluida":
        divergencias_db = (
            db.query(DivergenciaDB)
            .filter(DivergenciaDB.comparacao_id == comparacao_id)
            .all()
        )
        divergencias = [DivergenciaSchema.model_validate(d) for d in divergencias_db]
    
    # Busca resumo de validação de contas
    validation_summary = None
    if comparacao.status == "concluida":
        validation_results = (
            db.query(AccountValidationResult)
            .filter(AccountValidationResult.comparacao_id == comparacao_id)
            .all()
        )
        if validation_results:
            validation_summary = AccountValidationSummary(
                total=len(validation_results),
                ok=sum(1 for r in validation_results if r.status == "ok"),
                invalid=sum(1 for r in validation_results if r.status == "invalid"),
                unknown=sum(1 for r in validation_results if r.status == "unknown")
            )
    
    # Monta resposta
    detalhe = ComparacaoDetalhe.model_validate(comparacao)
    detalhe.divergencias = divergencias
    detalhe.account_validation_summary = validation_summary
    
    return detalhe


@router.get("/{comparacao_id}/validacao-contas", response_model=List[AccountValidationResultSchema])
def obter_validacao_contas(
    comparacao_id: int,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Obtém resultados de validação de contas."""
    query = (
        db.query(AccountValidationResult)
        .filter(AccountValidationResult.comparacao_id == comparacao_id)
    )
    
    if status:
        query = query.filter(AccountValidationResult.status == status)
    
    return query.order_by(AccountValidationResult.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{comparacao_id}/divergencias")
def obter_divergencias(
    comparacao_id: int,
    skip: int = 0,
    limit: int = 100,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Obtém divergências de uma comparação."""
    comparacao = db.query(Comparacao).filter(Comparacao.id == comparacao_id).first()
    
    if not comparacao:
        raise HTTPException(status_code=404, detail="Comparação não encontrada")
    
    query = db.query(DivergenciaDB).filter(DivergenciaDB.comparacao_id == comparacao_id)
    
    if tipo:
        query = query.filter(DivergenciaDB.tipo == tipo)
    
    results = query.order_by(DivergenciaDB.id.desc()).offset(skip).limit(limit).all()
    return [DivergenciaSchema.model_validate(d) for d in results]


@router.delete("/{comparacao_id}", status_code=204)
def deletar_comparacao(comparacao_id: int, db: Session = Depends(get_db)):
    """Deleta uma comparação e todos os dados relacionados."""
    comparacao = db.query(Comparacao).filter(Comparacao.id == comparacao_id).first()
    
    if not comparacao:
        raise HTTPException(status_code=404, detail="Comparação não encontrada")
    
    # Deleta dados relacionados primeiro
    db.query(DivergenciaDB).filter(DivergenciaDB.comparacao_id == comparacao_id).delete(synchronize_session=False)
    db.query(AccountValidationResult).filter(AccountValidationResult.comparacao_id == comparacao_id).delete(synchronize_session=False)
    db.flush()
    
    db.delete(comparacao)
    db.flush()
    
    return None
