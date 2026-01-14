"""
Configurações da aplicação
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do .env"""
    
    # Ambiente
    environment: str = "development"
    debug: bool = True
    
    # Database (suporta SQLite local e PostgreSQL no Render)
    database_url: str = "sqlite:///./data/rpa_dominio.db"
    
    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"  # Separado por vírgula
    
    # Paths
    data_dir: Path = Path("./data")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Instância global de settings
settings = Settings()


# Garantir que os diretórios existam
def ensure_directories():
    """Cria os diretórios necessários se não existirem"""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "otimiza").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "mpds").mkdir(parents=True, exist_ok=True)


# Inicializar diretórios ao importar
ensure_directories()

