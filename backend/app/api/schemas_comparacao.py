"""
Schemas Pydantic para API de comparações
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.core.divergencias import TipoDivergencia


class DivergenciaSchema(BaseModel):
    """Schema de divergência para resposta da API"""
    
    id: int
    tipo: str  # String ao invés de enum para compatibilidade
    descricao: str
    
    # Campos do MPDS (movimentações bancárias)
    data_extrato: Optional[date] = None
    descricao_extrato: Optional[str] = None
    valor_extrato: Optional[float] = None
    documento_extrato: Optional[str] = None
    conta_contabil_extrato: Optional[str] = None
    
    # Campos do TXT Otimiza (lançamentos contábeis)
    data_dominio: Optional[date] = None  # Mantém nome para compatibilidade
    descricao_dominio: Optional[str] = None
    valor_dominio: Optional[float] = None
    documento_dominio: Optional[str] = None
    conta_contabil_dominio: Optional[str] = None
    
    class Config:
        from_attributes = True  # Pydantic v2 (antes era orm_mode)
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
        }


class ComparacaoCreate(BaseModel):
    """Schema para criação de comparação"""
    
    data_inicio: date
    data_fim: date


class ComparacaoResumo(BaseModel):
    """Schema resumido de comparação"""
    
    id: int
    criado_em: datetime
    periodo_inicio: date
    periodo_fim: date
    source_type: str
    bank_source_type: str
    status: str
    qtd_lancamentos_extrato: Optional[int] = None  # MPDS (movimentações bancárias)
    qtd_lancamentos_razao: Optional[int] = None  # TXT Otimiza (lançamentos contábeis)
    qtd_divergencias: Optional[int] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }


class AccountValidationResultSchema(BaseModel):
    """Schema de resultado de validação de conta"""
    
    id: int
    lancamento_key: str
    account_code: str
    status: str  # "ok" | "invalid" | "unknown"
    reason_code: str
    message: str
    expected: Optional[dict] = None
    meta: Optional[dict] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class AccountValidationSummary(BaseModel):
    """Resumo de validação de contas"""
    
    total: int
    ok: int
    invalid: int
    unknown: int


class ComparacaoDetalhe(ComparacaoResumo):
    """Schema detalhado de comparação com divergências"""
    
    divergencias: List[DivergenciaSchema]
    account_validation_summary: Optional[AccountValidationSummary] = None





