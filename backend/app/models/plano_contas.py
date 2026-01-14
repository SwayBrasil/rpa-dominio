"""
Modelos SQLAlchemy para Plano de Contas e Validação
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ChartOfAccounts(Base):
    """Modelo de Plano de Contas"""
    
    __tablename__ = "chart_of_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), default="dominio", nullable=False, index=True)
    account_code = Column(String(100), nullable=False, index=True)
    account_name = Column(String(255), nullable=False)
    account_level = Column(Integer, nullable=True)
    parent_code = Column(String(100), nullable=True, index=True)
    account_type = Column(String(50), nullable=True)  # ASSET, LIABILITY, INCOME, EXPENSE
    nature = Column(String(50), nullable=True)  # DEBIT, CREDIT
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Unique constraint: account_code + source
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class AccountValidationRule(Base):
    """Modelo de Regra de Validação de Conta"""
    
    __tablename__ = "account_validation_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    match_field = Column(String(100), nullable=False)  # ex: "otimiza_event_type", "otimiza_category"
    match_value = Column(String(255), nullable=False)  # ex: "CLIENTE", "FORNECEDOR"
    allowed_account_prefixes = Column(JSON, nullable=True)  # ["2.112", "2.113"]
    allowed_account_codes = Column(JSON, nullable=True)  # ["2.112111"]
    blocked_account_prefixes = Column(JSON, nullable=True)
    blocked_account_codes = Column(JSON, nullable=True)
    severity = Column(String(20), default="error", nullable=False)  # "error" | "warning"
    message = Column(Text, nullable=True)  # Mensagem padrão se violar
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AccountValidationResult(Base):
    """Modelo de Resultado de Validação de Conta"""
    
    __tablename__ = "account_validation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    comparacao_id = Column(Integer, ForeignKey("comparacoes.id"), nullable=False, index=True)
    lancamento_key = Column(String(255), nullable=False)  # Identificador único do lançamento
    account_code = Column(String(100), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # "ok" | "invalid" | "unknown"
    reason_code = Column(String(50), nullable=False)  # ACCOUNT_NOT_FOUND, RULE_VIOLATION, etc
    message = Column(Text, nullable=False)
    expected = Column(JSON, nullable=True)  # {allowed_prefixes:[], allowed_codes:[]}
    meta = Column(JSON, nullable=True)  # Auditoria: regra aplicada, dados do lançamento
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relacionamento
    comparacao = relationship("Comparacao")

