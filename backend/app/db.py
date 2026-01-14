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

# Configuração do engine para SQLite
connect_args = {}
poolclass = None

if "sqlite" in settings.database_url:
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

# Cria engine
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    poolclass=poolclass,
    pool_pre_ping=True,  # Verifica conexão antes de usar
    echo=False
)

# Registra evento para SQLite
if "sqlite" in settings.database_url:
    event.listen(engine, "connect", _set_sqlite_pragma)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Cria todas as tabelas no banco de dados e executa migrações"""
    Base.metadata.create_all(bind=engine)
    _migrate_add_new_columns()


def _migrate_add_new_columns():
    """
    Migração automática: adiciona novas colunas se não existirem.
    Compatível com bancos de dados existentes.
    """
    from sqlalchemy import inspect, text
    
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        if 'comparacoes' not in table_names:
            return  # Tabela não existe ainda, será criada pelo create_all
        
        columns = {col['name']: col for col in inspector.get_columns('comparacoes')}
        
        with engine.begin() as conn:  # begin() faz commit automático
            # Adiciona source_type se não existir
            if 'source_type' not in columns:
                try:
                    conn.execute(text("ALTER TABLE comparacoes ADD COLUMN source_type VARCHAR(50) DEFAULT 'DOMINIO'"))
                except Exception as e:
                    # Coluna pode já existir em alguns casos
                    logger.warning(f"Erro ao adicionar source_type (pode já existir): {e}")
            
            # Adiciona bank_source_type se não existir
            if 'bank_source_type' not in columns:
                try:
                    conn.execute(text("ALTER TABLE comparacoes ADD COLUMN bank_source_type VARCHAR(50) DEFAULT 'PDF'"))
                except Exception as e:
                    logger.warning(f"Erro ao adicionar bank_source_type (pode já existir): {e}")
            
            # Adiciona input_files se não existir
            if 'input_files' not in columns:
                try:
                    conn.execute(text("ALTER TABLE comparacoes ADD COLUMN input_files TEXT"))
                except Exception as e:
                    logger.warning(f"Erro ao adicionar input_files (pode já existir): {e}")
            
            # Adiciona parsing_issues se não existir
            if 'parsing_issues' not in columns:
                try:
                    conn.execute(text("ALTER TABLE comparacoes ADD COLUMN parsing_issues TEXT"))
                except Exception as e:
                    logger.warning(f"Erro ao adicionar parsing_issues (pode já existir): {e}")
            
            # Migração: torna caminho_extrato e caminho_razao nullable
            # SQLite não permite MODIFY COLUMN, então precisamos recriar a tabela
            if 'caminho_extrato' in columns and not columns['caminho_extrato']['nullable']:
                logger.info("Migrando: tornando caminho_extrato e caminho_razao nullable...")
                try:
                    # SQLite não permite MODIFY, então recriamos a tabela
                    conn.execute(text("PRAGMA foreign_keys=OFF"))
                    
                    # Cria tabela temporária com schema atualizado
                    conn.execute(text("""
                        CREATE TABLE comparacoes_new (
                            id INTEGER NOT NULL PRIMARY KEY,
                            criado_em DATETIME NOT NULL,
                            periodo_inicio DATE NOT NULL,
                            periodo_fim DATE NOT NULL,
                            source_type VARCHAR(50) DEFAULT 'OTIMIZA_TXT',
                            bank_source_type VARCHAR(50) DEFAULT 'CSV',
                            input_files TEXT,
                            status VARCHAR(50) DEFAULT 'pendente',
                            erro TEXT,
                            qtd_lancamentos_extrato INTEGER,
                            qtd_lancamentos_razao INTEGER,
                            qtd_divergencias INTEGER,
                            parsing_issues TEXT
                        )
                    """))
                    
                    # Copia dados (ignora colunas antigas que não existem mais)
                    conn.execute(text("""
                        INSERT INTO comparacoes_new 
                        (id, criado_em, periodo_inicio, periodo_fim, source_type, bank_source_type, 
                         input_files, status, erro, qtd_lancamentos_extrato, qtd_lancamentos_razao, 
                         qtd_divergencias, parsing_issues)
                        SELECT 
                            id, criado_em, periodo_inicio, periodo_fim,
                            COALESCE(source_type, 'OTIMIZA_TXT') as source_type,
                            COALESCE(bank_source_type, 'CSV') as bank_source_type,
                            input_files, status, erro, qtd_lancamentos_extrato, 
                            qtd_lancamentos_razao, qtd_divergencias, parsing_issues
                        FROM comparacoes
                    """))
                    
                    # Remove tabela antiga e renomeia nova
                    conn.execute(text("DROP TABLE comparacoes"))
                    conn.execute(text("ALTER TABLE comparacoes_new RENAME TO comparacoes"))
                    
                    conn.execute(text("PRAGMA foreign_keys=ON"))
                    logger.info("Migração concluída: caminho_extrato e caminho_razao removidos")
                except Exception as e:
                    logger.error(f"Erro na migração de schema (pode precisar recriar banco): {e}")
                    conn.execute(text("PRAGMA foreign_keys=ON"))
            
    except Exception as e:
        logger.warning(f"Erro na migração automática (pode ser ignorado): {e}")


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

