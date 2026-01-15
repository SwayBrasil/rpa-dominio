"""
Modelos SQLAlchemy para comparações e divergências
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Float, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class Comparacao(Base):
    """Modelo de comparação entre TXT Otimiza e MPDS"""
    
    __tablename__ = "comparacoes"
    
    id = Column(Integer, primary_key=True, index=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)  # Início do processamento
    finished_at = Column(DateTime, nullable=True)  # Fim do processamento
    
    # Metadados da comparação
    periodo_inicio = Column(Date, nullable=False)
    periodo_fim = Column(Date, nullable=False)
    
    # Tipo de fonte de dados
    source_type = Column(String(50), default="OTIMIZA_TXT")  # Sempre OTIMIZA_TXT
    bank_source_type = Column(String(50), default="CSV")  # CSV | OFX | PDF
    
    # Informações dos arquivos de entrada (JSON)
    input_files = Column(JSON, nullable=True)  # {"otimiza_txt": "...", "mpds_csv": "...", "mpds_ofx": "..."}
    
    # Status da comparação
    status = Column(String(50), default="pendente")  # pendente, processando, concluida, erro
    erro = Column(Text, nullable=True)
    
    # Estatísticas
    qtd_lancamentos_extrato = Column(Integer, nullable=True)  # MPDS (movimentações bancárias)
    qtd_lancamentos_razao = Column(Integer, nullable=True)  # TXT Otimiza (lançamentos contábeis)
    qtd_divergencias = Column(Integer, nullable=True)
    
    # Issues de parsing
    parsing_issues = Column(JSON, nullable=True)  # Lista de problemas encontrados durante parsing
    
    # Relacionamento
    divergencias = relationship(
        "DivergenciaDB",
        back_populates="comparacao",
        cascade="all, delete-orphan"
    )


class DivergenciaDB(Base):
    """Modelo de divergência encontrada na comparação"""
    
    __tablename__ = "divergencias"
    
    id = Column(Integer, primary_key=True, index=True)
    comparacao_id = Column(Integer, ForeignKey("comparacoes.id"), nullable=False)
    
    tipo = Column(String(50), nullable=False)
    descricao = Column(Text, nullable=False)
    
    # Campos resumidos do lançamento do extrato
    data_extrato = Column(Date, nullable=True)
    descricao_extrato = Column(String(255), nullable=True)
    valor_extrato = Column(Float, nullable=True)
    documento_extrato = Column(String(100), nullable=True)
    conta_contabil_extrato = Column(String(100), nullable=True)
    
    # Campos resumidos do lançamento do domínio
    data_dominio = Column(Date, nullable=True)
    descricao_dominio = Column(String(255), nullable=True)
    valor_dominio = Column(Float, nullable=True)
    documento_dominio = Column(String(100), nullable=True)
    conta_contabil_dominio = Column(String(100), nullable=True)
    
    # Relacionamento
    comparacao = relationship("Comparacao", back_populates="divergencias")

