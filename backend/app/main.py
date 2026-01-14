"""
Comparador de Extratos - TXT Otimiza x MPDS
API principal FastAPI
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db import init_db
from app.api.routes_comparacao import router as comparacoes_router
from app.api.routes_plano_contas import router as plano_contas_router

app = FastAPI(
    title="Comparador de Extratos",
    description="Ferramenta para comparar TXT Otimiza com MPDS (extrato estruturado)",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origens
    allow_credentials=True,
    allow_methods=["*"],
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

