"""
Modelos Pydantic para divergências detectadas na comparação
"""

from typing import Literal, Optional
from pydantic import BaseModel
from app.core.models import Lancamento


TipoDivergencia = Literal[
    "NAO_ENCONTRADO_DOMINIO",
    "NAO_ENCONTRADO_EXTRATO",
    "VALOR_DIFERENTE",
    "SALDO_DIVERGENTE",
    "CLASSIFICACAO_SUSPEITA",
]


class Divergencia(BaseModel):
    """
    Representa uma divergência encontrada na comparação entre extrato e razão Domínio.
    """
    tipo: TipoDivergencia
    descricao: str  # texto humano explicando o problema
    lancamento_extrato: Optional[Lancamento] = None
    lancamento_dominio: Optional[Lancamento] = None
    
    class Config:
        json_encoders = {
            # Lancamento já tem seus próprios encoders
        }






