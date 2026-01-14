"""
Modelos Pydantic para dados em memória
"""

from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel


class Lancamento(BaseModel):
    """Modelo de lançamento padronizado"""
    data: date
    descricao: str
    documento: Optional[str] = None
    valor: float
    saldo: Optional[float] = None
    conta_contabil: Optional[str] = None
    origem: Literal["extrato", "dominio", "otimiza", "mpds"]
    
    # Campos específicos do Otimiza para validação
    account_code: Optional[str] = None  # Código da conta do plano de contas
    event_type: Optional[str] = None  # Tipo de evento (ex: CLIENTE, FORNECEDOR)
    category: Optional[str] = None  # Categoria (ex: IMPOSTO, TARIFA)
    entity_type: Optional[str] = None  # Tipo de entidade
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }





