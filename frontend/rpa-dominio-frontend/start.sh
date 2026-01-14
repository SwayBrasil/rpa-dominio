#!/bin/bash
# Script para iniciar o frontend

cd "$(dirname "$0")"

# Verifica se .env existe
if [ ! -f .env ]; then
    echo "📝 Criando arquivo .env..."
    cp env.example .env
fi

# Inicia o servidor de desenvolvimento
echo "🚀 Iniciando servidor de desenvolvimento..."
npm run dev






