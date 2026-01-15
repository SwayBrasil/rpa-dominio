"""
Rotas FastAPI para comparações
"""

import logging
from typing import List, Optional
import asyncio
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from datetime import date
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

from app.api.schemas_comparacao import (
    ComparacaoCreate,
    ComparacaoResumo,
    ComparacaoDetalhe,
    AccountValidationResultSchema,
    AccountValidationSummary,
)
from app.models.plano_contas import AccountValidationResult
from app.services.comparador.service import rodar_comparacao_txt, rodar_comparacao_txt_multiplos
from app.models.comparacao import Comparacao, DivergenciaDB
from app.db import get_db

router = APIRouter(prefix="/comparacoes", tags=["comparacoes"])


@router.post("/", response_model=ComparacaoResumo, status_code=201)
async def criar_comparacao(
    data_inicio: date = Form(...),
    data_fim: date = Form(...),
    otimiza_txt: UploadFile = File(None),  # Mantido para compatibilidade
    otimiza_txt_files: List[UploadFile] = File(None),  # Novo: aceita múltiplos
    mpds_csv: UploadFile = File(None),
    mpds_ofx: UploadFile = File(None),
    mpds_pdf: UploadFile = File(None),  # Obrigatório no modo cliente, opcional para compatibilidade
    db: Session = Depends(get_db),
):
    """
    Cria uma nova comparação entre TXT(s) Otimiza e extrato bancário em PDF.
    
    O sistema compara:
    - Lançamentos contábeis do TXT Otimiza (PAGAR e/ou RECEBER)
    - Movimentações bancárias do extrato em PDF (Nubank/Sicoob)
    
    Processo:
    1. Faz parsing dos arquivos
    2. Unifica lançamentos se houver múltiplos TXTs
    3. Compara e detecta divergências
    4. Valida contas contábeis usando o Plano de Contas (se carregado)
    5. Retorna resumo e detalhes
    
    Args:
        data_inicio: Data inicial do período
        data_fim: Data final do período
        otimiza_txt: Arquivo TXT do Otimiza (obrigatório se otimiza_txt_files não fornecido)
        otimiza_txt_files: Lista de arquivos TXT do Otimiza (PAGAR e/ou RECEBER, max 2)
        mpds_pdf: Arquivo PDF do extrato bancário - Nubank/Sicoob (obrigatório)
        mpds_csv: Arquivo MPDS em formato CSV (suporte interno, não usado na UI principal)
        mpds_ofx: Arquivo MPDS em formato OFX (suporte interno, não usado na UI principal)
        
    Nota: No modo cliente, use mpds_pdf (obrigatório) e otimiza_txt_files (1 ou 2 arquivos).
          CSV/OFX ficam disponíveis para suporte interno.
    """
    # Valida período
    if data_inicio > data_fim:
        raise HTTPException(
            status_code=400,
            detail="Data inicial deve ser anterior à data final"
        )
    
    # Coleta arquivos TXT Otimiza (suporta ambos os formatos para compatibilidade)
    otimiza_files = []
    
    # Se forneceu otimiza_txt_files (novo formato)
    if otimiza_txt_files:
        otimiza_files = otimiza_txt_files
    # Se forneceu otimiza_txt (formato antigo para compatibilidade)
    elif otimiza_txt:
        otimiza_files = [otimiza_txt]
    
    # Valida que pelo menos um TXT foi fornecido
    if not otimiza_files:
        raise HTTPException(
            status_code=400,
            detail="É necessário fornecer pelo menos um arquivo TXT do Otimiza (PAGAR e/ou RECEBER)"
        )
    
    # Valida quantidade máxima de TXTs (2: PAGAR + RECEBER)
    if len(otimiza_files) > 2:
        raise HTTPException(
            status_code=400,
            detail="É permitido enviar no máximo 2 arquivos TXT do Otimiza (PAGAR e RECEBER)"
        )
    
    # Valida que pelo menos um arquivo bancário foi fornecido
    # No modo cliente, PDF é obrigatório, mas mantemos CSV/OFX para compatibilidade
    mpds_count = sum([bool(mpds_csv), bool(mpds_ofx), bool(mpds_pdf)])
    
    if mpds_count == 0:
        raise HTTPException(
            status_code=400,
            detail="É necessário fornecer o extrato bancário (PDF, CSV ou OFX). No modo cliente, use PDF."
        )
    
    if mpds_count > 1:
        raise HTTPException(
            status_code=400,
            detail="Forneça apenas um arquivo de extrato bancário (PDF, CSV ou OFX), não múltiplos"
        )
    
    try:
        # Lê arquivos TXT Otimiza
        otimiza_data = []
        for otimiza_file in otimiza_files:
            otimiza_bytes = await otimiza_file.read()
        if len(otimiza_bytes) == 0:
            raise HTTPException(
                status_code=400,
                    detail=f"Arquivo TXT Otimiza vazio: {otimiza_file.filename or 'sem nome'}"
            )
            otimiza_nome = otimiza_file.filename or "otimiza.txt"
            otimiza_data.append((otimiza_bytes, otimiza_nome))
        
        # Lê arquivo bancário (prioridade: PDF > OFX > CSV para modo cliente)
        mpds_bytes = None
        mpds_nome = None
        bank_source_type = "PDF"
        
        if mpds_pdf:
            mpds_bytes = await mpds_pdf.read()
            mpds_nome = mpds_pdf.filename or "extrato.pdf"
            bank_source_type = "PDF"
        elif mpds_ofx:
            mpds_bytes = await mpds_ofx.read()
            mpds_nome = mpds_ofx.filename or "extrato.ofx"
            bank_source_type = "OFX"
        elif mpds_csv:
            mpds_bytes = await mpds_csv.read()
            mpds_nome = mpds_csv.filename or "extrato.csv"
            bank_source_type = "CSV"
        
        if len(mpds_bytes) == 0:
            raise HTTPException(
                status_code=400,
                detail="Arquivo de extrato bancário vazio"
            )
        
        # Executa comparação em thread separada
        loop = asyncio.get_event_loop()
        comparacao = await loop.run_in_executor(
            None,
            rodar_comparacao_txt_multiplos,
            db,
            otimiza_data,  # Lista de tuplas (bytes, nome)
            mpds_bytes,
            mpds_nome,
            bank_source_type,
            data_inicio,
            data_fim,
        )
        
        return comparacao
        
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.exception(f"RuntimeError ao processar comparação: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar comparação: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Exception ao processar comparação: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado: {str(e)}"
        )


@router.get("/", response_model=List[ComparacaoResumo])
def listar_comparacoes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Lista todas as comparações realizadas, ordenadas por data de criação (mais recentes primeiro).
    """
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
    Obtém detalhes de uma comparação específica, incluindo todas as divergências e resumo de validação de contas.
    """
    comparacao = (
        db.query(Comparacao)
        .filter(Comparacao.id == comparacao_id)
        .first()
    )
    
    if not comparacao:
        raise HTTPException(
            status_code=404,
            detail="Comparação não encontrada"
        )
    
    # Busca resumo de validação de contas
    validation_results = (
        db.query(AccountValidationResult)
        .filter(AccountValidationResult.comparacao_id == comparacao_id)
        .all()
    )
    
    validation_summary = None
    if validation_results:
        total = len(validation_results)
        ok = sum(1 for r in validation_results if r.status == "ok")
        invalid = sum(1 for r in validation_results if r.status == "invalid")
        unknown = sum(1 for r in validation_results if r.status == "unknown")
        
        validation_summary = AccountValidationSummary(
            total=total,
            ok=ok,
            invalid=invalid,
            unknown=unknown
        )
    
    # Busca divergências
    divergencias = (
        db.query(DivergenciaDB)
        .filter(DivergenciaDB.comparacao_id == comparacao_id)
        .all()
    )
    
    # Retorna usando from_attributes do Pydantic
    from app.api.schemas_comparacao import ComparacaoDetalhe, DivergenciaSchema
    
    detalhe = ComparacaoDetalhe.model_validate(comparacao)
    detalhe.divergencias = [DivergenciaSchema.model_validate(d) for d in divergencias]
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
    """
    Obtém resultados de validação de contas de uma comparação.
    
    Args:
        comparacao_id: ID da comparação
        skip: Paginação
        limit: Limite de resultados
        status: Filtrar por status (ok, invalid, unknown)
    """
    query = (
        db.query(AccountValidationResult)
        .filter(AccountValidationResult.comparacao_id == comparacao_id)
    )
    
    if status:
        query = query.filter(AccountValidationResult.status == status)
    
    results = query.order_by(AccountValidationResult.created_at.desc()).offset(skip).limit(limit).all()
    
    return results


@router.get("/{comparacao_id}/divergencias")
def obter_divergencias(
    comparacao_id: int,
    skip: int = 0,
    limit: int = 100,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Obtém divergências de uma comparação.
    
    Args:
        comparacao_id: ID da comparação
        skip: Paginação
        limit: Limite de resultados
        tipo: Filtrar por tipo de divergência
    """
    comparacao = (
        db.query(Comparacao)
        .filter(Comparacao.id == comparacao_id)
        .first()
    )
    
    if not comparacao:
        raise HTTPException(
            status_code=404,
            detail="Comparação não encontrada"
        )
    
    query = (
        db.query(DivergenciaDB)
        .filter(DivergenciaDB.comparacao_id == comparacao_id)
    )
    
    if tipo:
        query = query.filter(DivergenciaDB.tipo == tipo)
    
    results = query.order_by(DivergenciaDB.id.desc()).offset(skip).limit(limit).all()
    
    # Converte para schema Pydantic
    from app.api.schemas_comparacao import DivergenciaSchema
    return [DivergenciaSchema.model_validate(d) for d in results]


@router.delete("/{comparacao_id}", status_code=204)
def deletar_comparacao(comparacao_id: int, db: Session = Depends(get_db)):
    """
    Deleta uma comparação e todas as suas divergências.
    """
    comparacao = (
        db.query(Comparacao)
        .filter(Comparacao.id == comparacao_id)
        .first()
    )
    
    if not comparacao:
        raise HTTPException(
            status_code=404,
            detail="Comparação não encontrada"
        )
    
    # Deleta divergências relacionadas primeiro (evita FOREIGN KEY constraint)
    # SQLite pode não respeitar cascade delete corretamente
    divergencias_count = db.query(DivergenciaDB).filter(DivergenciaDB.comparacao_id == comparacao_id).count()
    if divergencias_count > 0:
        db.query(DivergenciaDB).filter(DivergenciaDB.comparacao_id == comparacao_id).delete(synchronize_session=False)
        db.flush()  # Flush explícito para garantir que as divergências foram deletadas
    
    # Deleta AccountValidationResult relacionado (se existir)
    from app.models.plano_contas import AccountValidationResult
    validations_count = db.query(AccountValidationResult).filter(
        AccountValidationResult.comparacao_id == comparacao_id
    ).count()
    if validations_count > 0:
        db.query(AccountValidationResult).filter(
            AccountValidationResult.comparacao_id == comparacao_id
        ).delete(synchronize_session=False)
        db.flush()  # Flush explícito para garantir que as validações foram deletadas
    
    # Agora pode deletar a comparação
    db.delete(comparacao)
    # Não faz commit aqui - get_db() faz commit automaticamente
    db.flush()
    
    return None

