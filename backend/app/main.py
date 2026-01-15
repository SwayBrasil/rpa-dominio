"""
Comparador de Extratos - TXT Otimiza x MPDS
API principal FastAPI
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db import init_db
from app.api.routes_comparacao import router as comparacoes_router
from app.api.routes_plano_contas import router as plano_contas_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Comparador de Extratos",
    description="Ferramenta para comparar TXT Otimiza com MPDS (extrato estruturado)",
    version="1.0.0",
    redirect_slashes=False  # Evita redirect 307 de /comparacoes para /comparacoes/
)

# CORS - DEVE estar antes de include_router
cors_origins_str = os.getenv("CORS_ORIGINS") or settings.cors_origins
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
print(f"CORS origins list: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Inicializa banco de dados na startup
@app.on_event("startup")
async def on_startup():
    """Inicializa banco de dados na startup"""
    init_db()


# Rotas
app.include_router(comparacoes_router)
app.include_router(plano_contas_router)


@app.get("/health")
async def health_check():
    """Endpoint de saúde da API"""
    return {
        "status": "ok",
        "service": "Comparador de Extratos",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "Comparador de Extratos - TXT Otimiza x MPDS",
        "docs": "/docs",
        "endpoints": {
            "comparacoes": "/comparacoes",
            "health": "/health"
        }
    }

