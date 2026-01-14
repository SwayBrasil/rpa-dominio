"""
Serviço de orquestração do fluxo completo de comparação
"""

import logging
import json
from datetime import date, datetime
from typing import List, Tuple
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.models import Lancamento
from app.services.parsers.otimiza_txt_parser import parse_otimiza_txt
from typing import Tuple
from app.services.parsers.mpds_csv_parser import parse_mpds_csv
from app.services.parsers.mpds_ofx_parser import parse_mpds_ofx
from app.services.parsers.mpds_pdf_parser import parse_mpds_pdf
from app.services.comparador.motor import compare_bank_vs_txt
from app.services.validations.account_validation import validate_lancamentos_accounts
from app.models.comparacao import Comparacao, DivergenciaDB
from app.core.divergencias import Divergencia as DivergenciaModelo
from app.core.config import settings

logger = logging.getLogger(__name__)


def load_otimiza_movements(
    otimiza_files_data: List[Tuple[bytes, str]],
    data_dir: Path,
    timestamp: str
) -> Tuple[List[Lancamento], List[str], dict]:
    """
    Carrega e unifica lançamentos de múltiplos arquivos TXT do Otimiza.
    
    Args:
        otimiza_files_data: Lista de tuplas (bytes, nome_arquivo)
        data_dir: Diretório para salvar arquivos
        timestamp: Timestamp para nomear arquivos
        
    Returns:
        Tupla (lista_unificada_lancamentos, lista_issues_total, dict_parsing_por_arquivo)
    """
    all_lancamentos = []
    all_issues = []
    parsing_info = {}
    
    otimiza_dir = data_dir / "otimiza"
    otimiza_dir.mkdir(parents=True, exist_ok=True)
    
    for idx, (otimiza_bytes, otimiza_nome) in enumerate(otimiza_files_data, 1):
        # Salva arquivo
        otimiza_path = otimiza_dir / f"{timestamp}_{idx}_{otimiza_nome}"
        otimiza_path.write_bytes(otimiza_bytes)
        
        logger.info(f"Processando arquivo TXT Otimiza {idx}/{len(otimiza_files_data)}: {otimiza_nome}")
        
        # Parse do arquivo
        try:
            lancamentos, issues = parse_otimiza_txt(otimiza_path, strict=False)
            
            # Normaliza sinal baseado no tipo do arquivo (PAGAR/RECEBER)
            # PAGAR = negativo, RECEBER = positivo
            otimiza_nome_upper = otimiza_nome.upper()
            if "PAGAR" in otimiza_nome_upper:
                # Arquivo PAGAR: valores devem ser negativos
                for lanc in lancamentos:
                    lanc.valor = -abs(lanc.valor)
            elif "RECEBER" in otimiza_nome_upper:
                # Arquivo RECEBER: valores devem ser positivos
                for lanc in lancamentos:
                    lanc.valor = abs(lanc.valor)
            # Se não identificar tipo, mantém sinal original
            
            all_lancamentos.extend(lancamentos)
            all_issues.extend([f"[{otimiza_nome}] {issue}" for issue in issues])
            
            parsing_info[otimiza_nome] = {
                "path": str(otimiza_path),
                "lancamentos_count": len(lancamentos),
                "issues_count": len(issues),
                "issues": issues
            }
            
            logger.info(
                f"Arquivo {otimiza_nome}: {len(lancamentos)} lançamentos extraídos, "
                f"{len(issues)} issues"
            )
        except Exception as e:
            error_msg = f"Erro ao processar {otimiza_nome}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            all_issues.append(f"[{otimiza_nome}] ERRO: {error_msg}")
            parsing_info[otimiza_nome] = {
                "path": str(otimiza_path),
                "lancamentos_count": 0,
                "issues_count": 1,
                "issues": [error_msg],
                "error": str(e)
            }
    
    # Remove duplicidades baseado em data, descrição e valor (tolerância pequena)
    lancamentos_unicos = []
    seen = set()
    
    for lanc in all_lancamentos:
        # Cria chave única baseada em data, descrição (normalizada) e valor
        desc_normalizada = lanc.descricao.strip().upper()[:50]  # Primeiros 50 chars
        chave = (
            lanc.data.isoformat(),
            desc_normalizada,
            round(lanc.valor, 2)  # Arredonda para 2 casas decimais
        )
        
        if chave not in seen:
            seen.add(chave)
            lancamentos_unicos.append(lanc)
    
    duplicados_removidos = len(all_lancamentos) - len(lancamentos_unicos)
    if duplicados_removidos > 0:
        logger.info(f"Removidos {duplicados_removidos} lançamentos duplicados")
        all_issues.append(f"Removidos {duplicados_removidos} lançamentos duplicados entre arquivos")
    
    logger.info(
        f"Total unificado: {len(lancamentos_unicos)} lançamentos únicos de "
        f"{len(otimiza_files_data)} arquivo(s)"
    )
    
    return lancamentos_unicos, all_issues, parsing_info


def rodar_comparacao_txt(
    db: Session,
    otimiza_txt_bytes: bytes,
    otimiza_txt_nome: str,
    mpds_file_bytes: bytes,
    mpds_file_nome: str,
    data_inicio: date,
    data_fim: date,
) -> Comparacao:
    """
    Pipeline completo de comparação no modo TXT:
    
    1. Salva arquivos TXT Otimiza e MPDS
    2. Faz parsing dos dois arquivos
    3. Compara lançamentos usando compare_bank_vs_txt
    4. Salva comparação + divergências no banco
    
    Args:
        db: Sessão do banco de dados
        otimiza_txt_bytes: Bytes do arquivo TXT do Otimiza
        otimiza_txt_nome: Nome do arquivo TXT
        mpds_file_bytes: Bytes do arquivo MPDS (CSV ou OFX)
        mpds_file_nome: Nome do arquivo MPDS
        data_inicio: Data inicial do período
        data_fim: Data final do período
        
    Returns:
        Objeto Comparacao salvo no banco
        
    Raises:
        RuntimeError em caso de falha crítica no processo
    """
    import json
    from pathlib import Path
    
    logger.info(f"Iniciando pipeline de comparação TXT: {data_inicio} a {data_fim}")
    
    try:
        # 1) Salvar arquivos
        data_dir = settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Salva TXT Otimiza
        otimiza_dir = data_dir / "otimiza"
        otimiza_dir.mkdir(parents=True, exist_ok=True)
        otimiza_path = otimiza_dir / f"{timestamp}_{otimiza_txt_nome}"
        otimiza_path.write_bytes(otimiza_txt_bytes)
        
        # Salva MPDS
        mpds_dir = data_dir / "mpds"
        mpds_dir.mkdir(parents=True, exist_ok=True)
        mpds_path = mpds_dir / f"{timestamp}_{mpds_file_nome}"
        mpds_path.write_bytes(mpds_file_bytes)
        
        # Detecta tipo do MPDS pela extensão
        mpds_ext = Path(mpds_file_nome).suffix.lower()
        if mpds_ext == '.csv':
            bank_source_type = 'CSV'
        elif mpds_ext == '.ofx':
            bank_source_type = 'OFX'
        elif mpds_ext == '.pdf':
            bank_source_type = 'PDF'
        else:
            bank_source_type = 'CSV'  # Default
        
        # 2) Cria registro inicial
        comparacao = Comparacao(
            periodo_inicio=data_inicio,
            periodo_fim=data_fim,
            source_type="OTIMIZA_TXT",
            bank_source_type=bank_source_type,
            status="processando",
            input_files=json.dumps({
                "otimiza_txt": str(otimiza_path),
                f"mpds_{bank_source_type.lower()}": str(mpds_path)
            })
        )
        db.add(comparacao)
        db.flush()
        
        logger.info(f"Arquivos salvos: TXT={otimiza_path}, MPDS={mpds_path}")
        
        # 3) Parsing
        logger.info("Iniciando parsing dos arquivos...")
        try:
            # Parse TXT Otimiza
            lanc_txt, issues_txt = parse_otimiza_txt(otimiza_path, strict=False)
            
            # Parse MPDS
            if bank_source_type == 'CSV':
                lanc_mpds, issues_mpds = parse_mpds_csv(mpds_path, strict=False)
            elif bank_source_type == 'OFX':
                lanc_mpds, issues_mpds = parse_mpds_ofx(mpds_path, strict=False)
            elif bank_source_type == 'PDF':
                lanc_mpds, issues_mpds = parse_mpds_pdf(mpds_path, strict=False)
            else:
                raise ValueError(f"Formato MPDS não suportado: {bank_source_type}")
            
            comparacao.qtd_lancamentos_extrato = len(lanc_mpds)  # MPDS = extrato
            comparacao.qtd_lancamentos_razao = len(lanc_txt)  # TXT = razão
            comparacao.parsing_issues = json.dumps({
                "txt_issues": issues_txt,
                "mpds_issues": issues_mpds
            })
            db.flush()
            
            logger.info(
                f"Parsing concluído: {len(lanc_mpds)} lançamentos no MPDS, "
                f"{len(lanc_txt)} no TXT Otimiza"
            )
            if issues_txt or issues_mpds:
                logger.warning(f"Issues de parsing: TXT={len(issues_txt)}, MPDS={len(issues_mpds)}")
        except Exception as e:
            logger.error(f"Erro no parsing: {e}")
            comparacao.status = "erro"
            comparacao.erro = f"Falha no parsing: {str(e)}"
            db.flush()
            raise RuntimeError(f"Falha no parsing: {e}")
        
        # 4) Comparação
        logger.info("Iniciando comparação de lançamentos...")
        try:
            divergencias: List[DivergenciaModelo] = compare_bank_vs_txt(
                bank_movements=lanc_mpds,
                txt_movements=lanc_txt,
                date_window_days=2,
                amount_tolerance=0.01,
                min_description_similarity=0.55,
                allow_many_to_one=True,
            )
            
            comparacao.qtd_divergencias = len(divergencias)
            db.flush()
            
            logger.info(f"Comparação concluída: {len(divergencias)} divergências encontradas")
        except Exception as e:
            logger.error(f"Erro na comparação: {e}")
            comparacao.status = "erro"
            comparacao.erro = f"Falha na comparação: {str(e)}"
            db.flush()
            raise RuntimeError(f"Falha na comparação: {e}")
        
        # 5) Persistir divergências no banco
        logger.info("Salvando divergências no banco...")
        for d in divergencias:
            tipo_str = d.tipo.value if hasattr(d.tipo, "value") else str(d.tipo)
            
            div_db = DivergenciaDB(
                comparacao_id=comparacao.id,
                tipo=tipo_str,
                descricao=d.descricao,
                # Campos do extrato (MPDS)
                data_extrato=d.lancamento_extrato.data if d.lancamento_extrato else None,
                descricao_extrato=d.lancamento_extrato.descricao if d.lancamento_extrato else None,
                valor_extrato=d.lancamento_extrato.valor if d.lancamento_extrato else None,
                documento_extrato=d.lancamento_extrato.documento if d.lancamento_extrato else None,
                conta_contabil_extrato=d.lancamento_extrato.conta_contabil if d.lancamento_extrato else None,
                # Campos do domínio (TXT - reutiliza campos do domínio)
                data_dominio=d.lancamento_dominio.data if d.lancamento_dominio else None,
                descricao_dominio=d.lancamento_dominio.descricao if d.lancamento_dominio else None,
                valor_dominio=d.lancamento_dominio.valor if d.lancamento_dominio else None,
                documento_dominio=d.lancamento_dominio.documento if d.lancamento_dominio else None,
                conta_contabil_dominio=d.lancamento_dominio.conta_contabil if d.lancamento_dominio else None,
            )
            db.add(div_db)
        
        # 6) Validação de contas (se houver lançamentos do Otimiza)
        validation_summary = None
        if lanc_txt:
            logger.info("Iniciando validação de contas contábeis...")
            try:
                validation_summary = validate_lancamentos_accounts(
                    comparacao_id=comparacao.id,
                    lancamentos_otimiza=lanc_txt,
                    source="dominio",
                    db=db
                )
                comparacao.parsing_issues = json.dumps({
                    "txt_issues": issues_txt,
                    "mpds_issues": issues_mpds,
                    "account_validation": validation_summary
                })
                db.flush()
                logger.info(
                    f"Validação de contas concluída: ok={validation_summary['ok']}, "
                    f"invalid={validation_summary['invalid']}, unknown={validation_summary['unknown']}"
                )
            except Exception as e:
                logger.error(f"Erro na validação de contas: {e}")
                # Não bloqueia o processo, apenas registra o erro
                comparacao.parsing_issues = json.dumps({
                    "txt_issues": issues_txt,
                    "mpds_issues": issues_mpds,
                    "account_validation_error": str(e)
                })
        
        # Marca como concluída
        comparacao.status = "concluida"
        # Não faz commit aqui - get_db() faz commit automaticamente
        db.flush()
        db.refresh(comparacao)
        
        logger.info(
            f"Comparação TXT {comparacao.id} concluída com sucesso. "
            f"{len(divergencias)} divergências salvas."
        )
        
        return comparacao
        
    except Exception as e:
        # Em caso de erro, marca como erro
        logger.error(f"Erro na comparação TXT: {e}", exc_info=True)
        if comparacao and comparacao.status != "erro":
            comparacao.status = "erro"
            comparacao.erro = str(e)
            db.flush()
        # Não faz commit aqui - get_db() faz rollback em caso de exceção
        raise


def rodar_comparacao_txt_multiplos(
    db: Session,
    otimiza_files_data: List[Tuple[bytes, str]],
    mpds_file_bytes: bytes,
    mpds_file_nome: str,
    bank_source_type: str,
    data_inicio: date,
    data_fim: date,
) -> Comparacao:
    """
    Pipeline completo de comparação com múltiplos arquivos TXT Otimiza:
    
    1. Salva arquivos TXT Otimiza (múltiplos) e extrato bancário
    2. Faz parsing e unifica lançamentos dos TXTs
    3. Faz parsing do extrato bancário
    4. Compara lançamentos usando compare_bank_vs_txt
    5. Salva comparação + divergências no banco
    
    Args:
        db: Sessão do banco de dados
        otimiza_files_data: Lista de tuplas (bytes, nome_arquivo) dos TXTs Otimiza
        mpds_file_bytes: Bytes do arquivo de extrato bancário
        mpds_file_nome: Nome do arquivo de extrato
        bank_source_type: Tipo do arquivo bancário ("PDF", "CSV", "OFX")
        data_inicio: Data inicial do período
        data_fim: Data final do período
        
    Returns:
        Objeto Comparacao salvo no banco
        
    Raises:
        RuntimeError em caso de falha crítica no processo
    """
    comparacao = None
    
    logger.info(
        f"Iniciando pipeline de comparação com {len(otimiza_files_data)} arquivo(s) TXT: "
        f"{data_inicio} a {data_fim}"
    )
    
    try:
        # 1) Salvar arquivos
        data_dir = settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Salva extrato bancário
        mpds_dir = data_dir / "mpds"
        mpds_dir.mkdir(parents=True, exist_ok=True)
        mpds_path = mpds_dir / f"{timestamp}_{mpds_file_nome}"
        mpds_path.write_bytes(mpds_file_bytes)
        
        # 2) Cria registro inicial
        otimiza_paths = [f"{timestamp}_{idx}_{nome}" for idx, (_, nome) in enumerate(otimiza_files_data, 1)]
        comparacao = Comparacao(
            periodo_inicio=data_inicio,
            periodo_fim=data_fim,
            source_type="OTIMIZA_TXT",
            bank_source_type=bank_source_type,
            status="processando",
            input_files=json.dumps({
                "otimiza_txt_paths": otimiza_paths,
                "extrato_pdf_path": str(mpds_path) if bank_source_type == "PDF" else None,
                f"extrato_{bank_source_type.lower()}_path": str(mpds_path)
            })
        )
        db.add(comparacao)
        db.flush()
        
        logger.info(f"Arquivos salvos: {len(otimiza_files_data)} TXT(s), extrato={mpds_path}")
        
        # 3) Parsing e unificação dos TXTs Otimiza
        logger.info("Iniciando parsing e unificação dos arquivos TXT Otimiza...")
        try:
            lanc_txt, issues_txt, parsing_info_txt = load_otimiza_movements(
                otimiza_files_data,
                data_dir,
                timestamp
            )
            
            comparacao.qtd_lancamentos_razao = len(lanc_txt)
            logger.info(
                f"Parsing TXT concluído: {len(lanc_txt)} lançamentos únicos extraídos de "
                f"{len(otimiza_files_data)} arquivo(s)"
            )
            if issues_txt:
                logger.warning(f"Issues de parsing TXT: {len(issues_txt)}")
        except Exception as e:
            logger.error(f"Erro no parsing TXT: {e}")
            comparacao.status = "erro"
            comparacao.erro = f"Falha no parsing TXT: {str(e)}"
            db.flush()
            raise RuntimeError(f"Falha no parsing TXT: {e}")
        
        # 4) Parsing do extrato bancário
        logger.info(f"Iniciando parsing do extrato bancário ({bank_source_type})...")
        try:
            if bank_source_type == 'CSV':
                lanc_mpds, issues_mpds = parse_mpds_csv(mpds_path, strict=False)
            elif bank_source_type == 'OFX':
                lanc_mpds, issues_mpds = parse_mpds_ofx(mpds_path, strict=False)
            elif bank_source_type == 'PDF':
                lanc_mpds, issues_mpds = parse_mpds_pdf(mpds_path, strict=False)
            else:
                raise ValueError(f"Formato de extrato não suportado: {bank_source_type}")
            
            comparacao.qtd_lancamentos_extrato = len(lanc_mpds)
            comparacao.parsing_issues = json.dumps({
                "txt_parsing_info": parsing_info_txt,
                "txt_issues": issues_txt,
                "mpds_issues": issues_mpds
            })
            db.flush()
            
            logger.info(
                f"Parsing extrato concluído: {len(lanc_mpds)} movimentações extraídas"
            )
            if issues_mpds:
                logger.warning(f"Issues de parsing extrato: {len(issues_mpds)}")
        except Exception as e:
            logger.error(f"Erro no parsing extrato: {e}")
            comparacao.status = "erro"
            comparacao.erro = f"Falha no parsing extrato: {str(e)}"
            db.flush()
            raise RuntimeError(f"Falha no parsing extrato: {e}")
        
        # 5) Comparação
        logger.info("Iniciando comparação de lançamentos...")
        try:
            divergencias: List[DivergenciaModelo] = compare_bank_vs_txt(
                bank_movements=lanc_mpds,
                txt_movements=lanc_txt,
                date_window_days=2,
                amount_tolerance=0.01,
                min_description_similarity=0.55,
                allow_many_to_one=True,
            )
            
            comparacao.qtd_divergencias = len(divergencias)
            db.flush()
            
            logger.info(f"Comparação concluída: {len(divergencias)} divergências encontradas")
        except Exception as e:
            logger.error(f"Erro na comparação: {e}")
            comparacao.status = "erro"
            comparacao.erro = f"Falha na comparação: {str(e)}"
            db.flush()
            raise RuntimeError(f"Falha na comparação: {e}")
        
        # 6) Persistir divergências no banco
        logger.info("Salvando divergências no banco...")
        for d in divergencias:
            tipo_str = d.tipo.value if hasattr(d.tipo, "value") else str(d.tipo)
            
            div_db = DivergenciaDB(
                comparacao_id=comparacao.id,
                tipo=tipo_str,
                descricao=d.descricao,
                # Campos do extrato (MPDS)
                data_extrato=d.lancamento_extrato.data if d.lancamento_extrato else None,
                descricao_extrato=d.lancamento_extrato.descricao if d.lancamento_extrato else None,
                valor_extrato=d.lancamento_extrato.valor if d.lancamento_extrato else None,
                documento_extrato=d.lancamento_extrato.documento if d.lancamento_extrato else None,
                conta_contabil_extrato=d.lancamento_extrato.conta_contabil if d.lancamento_extrato else None,
                # Campos do domínio (TXT)
                data_dominio=d.lancamento_dominio.data if d.lancamento_dominio else None,
                descricao_dominio=d.lancamento_dominio.descricao if d.lancamento_dominio else None,
                valor_dominio=d.lancamento_dominio.valor if d.lancamento_dominio else None,
                documento_dominio=d.lancamento_dominio.documento if d.lancamento_dominio else None,
                conta_contabil_dominio=d.lancamento_dominio.conta_contabil if d.lancamento_dominio else None,
            )
            db.add(div_db)
        
        # 7) Validação de contas (se houver lançamentos do Otimiza)
        validation_summary = None
        if lanc_txt:
            logger.info("Iniciando validação de contas contábeis...")
            try:
                validation_summary = validate_lancamentos_accounts(
                    comparacao_id=comparacao.id,
                    lancamentos_otimiza=lanc_txt,
                    source="dominio",
                    db=db
                )
                comparacao.parsing_issues = json.dumps({
                    "txt_parsing_info": parsing_info_txt,
                    "txt_issues": issues_txt,
                    "mpds_issues": issues_mpds,
                    "account_validation": validation_summary
                })
                db.flush()
                logger.info(
                    f"Validação de contas concluída: ok={validation_summary['ok']}, "
                    f"invalid={validation_summary['invalid']}, unknown={validation_summary['unknown']}"
                )
            except Exception as e:
                logger.error(f"Erro na validação de contas: {e}")
                # Não bloqueia o processo, apenas registra o erro
                comparacao.parsing_issues = json.dumps({
                    "txt_parsing_info": parsing_info_txt,
                    "txt_issues": issues_txt,
                    "mpds_issues": issues_mpds,
                    "account_validation_error": str(e)
                })
        
        # Marca como concluída
        comparacao.status = "concluida"
        # Não faz commit aqui - get_db() faz commit automaticamente
        db.flush()
        db.refresh(comparacao)
        
        logger.info(
            f"Comparação {comparacao.id} concluída com sucesso. "
            f"{len(divergencias)} divergências salvas."
        )
        
        return comparacao
        
    except Exception as e:
        # Em caso de erro, marca como erro
        logger.error(f"Erro na comparação: {e}", exc_info=True)
        if comparacao and comparacao.status != "erro":
            comparacao.status = "erro"
            comparacao.erro = str(e)
            db.flush()
        # Não faz commit aqui - get_db() faz rollback em caso de exceção
        raise

