"""
Rotas FastAPI para Plano de Contas
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from pathlib import Path
import tempfile

from app.db import get_db
from app.models.plano_contas import ChartOfAccounts
from app.services.parsers.plano_contas_parser import parse_plano_contas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plano-contas", tags=["plano-contas"])


@router.post("/upload")
async def upload_plano_contas(
    file: UploadFile = File(...),
    source: str = Form("dominio"),
    replace: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Faz upload do plano de contas (CSV ou XLSX).
    
    Args:
        file: Arquivo CSV ou XLSX
        source: Fonte do plano (default: "dominio")
        replace: Se True, apaga plano anterior do mesmo source antes de inserir
        
    Returns:
        Resumo: total lidas, inseridas, ignoradas, duplicadas
    """
    # Valida tipo de arquivo
    if file.content_type not in (
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream"
    ):
        # Verifica extensão
        filename = file.filename or ""
        if not (filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')):
            raise HTTPException(
                status_code=400,
                detail="Envie um arquivo CSV ou Excel (.csv, .xlsx, .xls)"
            )
    
    # Salva arquivo temporário
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail="Arquivo vazio"
        )
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_path = tmp_file.name
    
    try:
        # Parse do arquivo
        contas_data = parse_plano_contas(tmp_path)
        
        total_lidas = len(contas_data)
        inseridas = 0
        ignoradas = 0
        duplicadas = 0
        
        # Se replace=True, apaga contas anteriores do mesmo source
        if replace:
            db.query(ChartOfAccounts).filter(ChartOfAccounts.source == source).delete()
            db.flush()
            logger.info(f"Plano de contas anterior do source '{source}' removido")
        
        # Insere contas
        for conta_data in contas_data:
            account_code = conta_data["account_code"]
            
            # Verifica se já existe
            existing = (
                db.query(ChartOfAccounts)
                .filter(
                    ChartOfAccounts.account_code == account_code,
                    ChartOfAccounts.source == source
                )
                .first()
            )
            
            if existing:
                # Atualiza existente
                existing.account_name = conta_data["account_name"]
                existing.account_level = conta_data.get("account_level")
                existing.parent_code = conta_data.get("parent_code")
                existing.account_type = conta_data.get("account_type")
                existing.nature = conta_data.get("nature")
                existing.is_active = True
                existing.updated_at = db.query(ChartOfAccounts).filter(
                    ChartOfAccounts.id == existing.id
                ).first().updated_at  # Mantém updated_at atual
                duplicadas += 1
            else:
                # Cria novo
                conta = ChartOfAccounts(
                    source=source,
                    account_code=account_code,
                    account_name=conta_data["account_name"],
                    account_level=conta_data.get("account_level"),
                    parent_code=conta_data.get("parent_code"),
                    account_type=conta_data.get("account_type"),
                    nature=conta_data.get("nature"),
                    is_active=True
                )
                db.add(conta)
                inseridas += 1
        
        db.commit()
        
        logger.info(
            f"Plano de contas carregado: source={source}, "
            f"total_lidas={total_lidas}, inseridas={inseridas}, "
            f"duplicadas={duplicadas}, ignoradas={ignoradas}"
        )
        
        return {
            "total_lidas": total_lidas,
            "inseridas": inseridas,
            "duplicadas": duplicadas,
            "ignoradas": ignoradas,
            "source": source
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao processar plano de contas: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar arquivo: {str(e)}"
        )
    finally:
        # Remove arquivo temporário
        try:
            Path(tmp_path).unlink()
        except:
            pass


@router.get("/")
def listar_plano_contas(
    source: Optional[str] = None,
    prefix: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Lista plano de contas com filtros opcionais.
    
    Args:
        source: Filtrar por fonte
        prefix: Filtrar por prefixo do código
        skip: Paginação
        limit: Limite de resultados
    """
    query = db.query(ChartOfAccounts).filter(ChartOfAccounts.is_active == True)
    
    if source:
        query = query.filter(ChartOfAccounts.source == source)
    
    if prefix:
        query = query.filter(ChartOfAccounts.account_code.like(f"{prefix}%"))
    
    total = query.count()
    contas = query.order_by(ChartOfAccounts.account_code).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "contas": [
            {
                "id": c.id,
                "source": c.source,
                "account_code": c.account_code,
                "account_name": c.account_name,
                "account_level": c.account_level,
                "parent_code": c.parent_code,
                "account_type": c.account_type,
                "nature": c.nature,
                "is_active": c.is_active
            }
            for c in contas
        ]
    }


