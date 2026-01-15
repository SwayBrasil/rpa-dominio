"""
Configuração do banco de dados SQLAlchemy
"""

import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, StaticPool
from app.core.config import settings
from app.models.base import Base

# Importa modelos para garantir registro no metadata
from app.models import (
    Comparacao, DivergenciaDB,
    ChartOfAccounts, AccountValidationRule, AccountValidationResult
)  # noqa: F401

logger = logging.getLogger(__name__)

# Configuração do engine para SQLite ou PostgreSQL
connect_args = {}
poolclass = None

if "sqlite" in settings.database_url.lower():
    # SQLite: configurações para evitar "database is locked"
    connect_args = {
        "check_same_thread": False,
        "timeout": 20.0  # Timeout de 20 segundos
    }
    # Usa NullPool para SQLite (evita pool de conexões que pode causar locks)
    poolclass = NullPool
    
    # Habilita WAL mode para melhor concorrência
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        """Habilita WAL mode e outras otimizações do SQLite"""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Cria engine para SQLite
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        poolclass=poolclass,
        pool_pre_ping=True,  # Verifica conexão antes de usar
        echo=False
    )
    
    # Registra evento para SQLite
    event.listen(engine, "connect", _set_sqlite_pragma)
else:
    # PostgreSQL (usado no Render)
    # Render fornece DATABASE_URL no formato: postgresql://user:pass@host:port/dbname
    # Ajusta URL se necessário (alguns drivers usam postgres:// ao invés de postgresql://)
    db_url = settings.database_url
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(
        db_url,
        pool_pre_ping=True,  # Verifica conexão antes de usar
        pool_size=5,  # Pool de conexões para PostgreSQL
        max_overflow=10,
        echo=False
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Cria todas as tabelas no banco de dados e executa migrações"""
    Base.metadata.create_all(bind=engine)
    _migrate_add_new_columns()


def _migrate_add_new_columns():
    """
    Migração automática: adiciona novas colunas se não existirem.
    Compatível com PostgreSQL e SQLite.
    
    IMPORTANTE: Cada ALTER é executado em transação separada para evitar
    que um erro aborte toda a transação (problema comum no PostgreSQL).
    """
    from sqlalchemy import inspect, text
    
    is_postgres = "postgresql" in settings.database_url.lower() or "postgres" in settings.database_url.lower()
    is_sqlite = "sqlite" in settings.database_url.lower()
    
    logger.info(f"Iniciando migração de schema (postgres={is_postgres}, sqlite={is_sqlite})")
    
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        if 'comparacoes' not in table_names:
            logger.info("Tabela 'comparacoes' não existe ainda, será criada pelo create_all")
            return
        
        # Obtém colunas existentes
        existing_columns = {col['name'] for col in inspector.get_columns('comparacoes')}
        logger.info(f"Colunas existentes: {existing_columns}")
        
        # Define colunas a adicionar com tipos específicos por banco
        columns_to_add = []
        
        if 'source_type' not in existing_columns:
            columns_to_add.append(('source_type', "VARCHAR(50) DEFAULT 'OTIMIZA_TXT'"))
        
        if 'bank_source_type' not in existing_columns:
            columns_to_add.append(('bank_source_type', "VARCHAR(50) DEFAULT 'PDF'"))
        
        if 'input_files' not in existing_columns:
            col_type = "JSONB" if is_postgres else "TEXT"
            columns_to_add.append(('input_files', col_type))
        
        if 'parsing_issues' not in existing_columns:
            col_type = "JSONB" if is_postgres else "TEXT"
            columns_to_add.append(('parsing_issues', col_type))
        
        if 'started_at' not in existing_columns:
            col_type = "TIMESTAMPTZ" if is_postgres else "DATETIME"
            columns_to_add.append(('started_at', col_type))
        
        if 'finished_at' not in existing_columns:
            col_type = "TIMESTAMPTZ" if is_postgres else "DATETIME"
            columns_to_add.append(('finished_at', col_type))
        
        if 'status' not in existing_columns:
            columns_to_add.append(('status', "VARCHAR(50) DEFAULT 'pendente'"))
        
        if 'erro' not in existing_columns:
            columns_to_add.append(('erro', "TEXT"))
        
        # Executa cada ALTER em transação separada
        for col_name, col_type in columns_to_add:
            _add_column_safe(col_name, col_type, is_postgres)
        
        # Remove colunas antigas se existirem (PostgreSQL)
        if is_postgres:
            for old_col in ['caminho_extrato', 'caminho_razao']:
                if old_col in existing_columns:
                    _drop_column_safe(old_col)
        
        logger.info("Migração de schema concluída")
        
    except Exception as e:
        logger.error(f"Erro na migração automática: {e}", exc_info=True)


def _add_column_safe(col_name: str, col_type: str, is_postgres: bool):
    """
    Adiciona coluna de forma segura, em transação isolada.
    Para PostgreSQL usa IF NOT EXISTS.
    """
    try:
        with engine.connect() as conn:
            if is_postgres:
                # PostgreSQL: usa ADD COLUMN IF NOT EXISTS
                sql = f"ALTER TABLE comparacoes ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            else:
                # SQLite: precisa verificar antes (não tem IF NOT EXISTS para ADD COLUMN)
                sql = f"ALTER TABLE comparacoes ADD COLUMN {col_name} {col_type}"
            
            conn.execute(text(sql))
            conn.commit()
            logger.info(f"Schema: coluna '{col_name}' OK")
    except Exception as e:
        # Ignora erro se coluna já existe (SQLite)
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            logger.info(f"Schema: coluna '{col_name}' já existe")
        else:
            logger.warning(f"Schema: erro ao adicionar '{col_name}': {e}")


def _drop_column_safe(col_name: str):
    """Remove coluna de forma segura (PostgreSQL only)."""
    try:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE comparacoes DROP COLUMN IF EXISTS {col_name}"))
            conn.commit()
            logger.info(f"Schema: coluna '{col_name}' removida")
    except Exception as e:
        logger.warning(f"Schema: erro ao remover '{col_name}': {e}")


def get_db() -> Session:
    """
    Dependency para obter sessão do banco de dados.
    Usar com Depends(get_db) no FastAPI.
    
    Garante que a sessão seja fechada corretamente e faz rollback em caso de erro.
    Evita "database is locked" com WAL mode e gerenciamento adequado de transações.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erro na sessão do banco: {e}", exc_info=True)
        raise
    finally:
        db.close()

