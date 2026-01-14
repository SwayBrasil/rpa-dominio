#!/bin/bash
# Script para iniciar o backend

cd "$(dirname "$0")/backend"

echo "🚀 Iniciando backend RPA Domínio..."
echo ""

# Ativa o ambiente virtual
if [ ! -d "venv" ]; then
    echo "❌ Ambiente virtual não encontrado!"
    echo "Execute primeiro: cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r ../requirements.txt"
    exit 1
fi

source venv/bin/activate

# Verifica se a porta está em uso
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "⚠️  Porta 8000 já está em uso!"
    echo "Parando processo anterior..."
    lsof -ti:8000 | xargs kill -9
    sleep 2
fi

# Inicia o servidor
echo "✅ Iniciando servidor em http://localhost:8000"
echo "📚 Documentação: http://localhost:8000/docs"
echo ""
echo "Pressione CTRL+C para parar"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000






