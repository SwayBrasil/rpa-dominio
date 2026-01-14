#!/bin/bash
# Script para iniciar backend e frontend do projeto RPA Domínio

echo "🚀 Iniciando projeto RPA Domínio..."
echo ""

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Função para verificar porta
check_port() {
    local port=$1
    if lsof -ti:$port > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Porta $port já está em uso${NC}"
        read -p "Deseja parar o processo na porta $port? (s/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Ss]$ ]]; then
            lsof -ti:$port | xargs kill -9 2>/dev/null
            sleep 2
            echo -e "${GREEN}✅ Processo na porta $port parado${NC}"
        else
            echo -e "${RED}❌ Não é possível iniciar na porta $port${NC}"
            return 1
        fi
    fi
    return 0
}

# Verificar portas
echo "🔍 Verificando portas..."
check_port 8000 || exit 1
check_port 5173 || exit 1
echo ""

# Backend
echo -e "${GREEN}📦 Iniciando Backend...${NC}"
cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Ambiente virtual não encontrado!${NC}"
    echo "Execute: cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate

# Verificar se .env existe
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Arquivo .env não encontrado${NC}"
    echo "Copiando env.example para .env..."
    cp ../env.example .env 2>/dev/null || echo "Crie o arquivo .env manualmente"
fi

echo -e "${GREEN}✅ Iniciando servidor backend em http://localhost:8000${NC}"
echo -e "${GREEN}📚 Documentação: http://localhost:8000/docs${NC}"
echo ""

# Inicia backend em background
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"
echo ""

# Aguarda backend iniciar
sleep 3

# Verifica se backend está rodando
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Erro ao iniciar backend. Verifique backend.log${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Backend iniciado com sucesso!${NC}"
echo ""

# Frontend
echo -e "${GREEN}📦 Iniciando Frontend...${NC}"
cd ../frontend/rpa-dominio-frontend

if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠️  Dependências não instaladas. Instalando...${NC}"
    npm install
fi

# Verifica se .env existe no frontend
if [ ! -f ".env" ]; then
    echo "Criando .env para frontend..."
    echo "VITE_API_URL=http://localhost:8000" > .env
fi

echo -e "${GREEN}✅ Iniciando servidor frontend em http://localhost:5173${NC}"
echo ""

# Inicia frontend em background
npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"
echo ""

# Aguarda frontend iniciar
sleep 3

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Projeto iniciado com sucesso!${NC}"
echo ""
echo -e "${GREEN}📍 Backend:  http://localhost:8000${NC}"
echo -e "${GREEN}📍 Frontend: http://localhost:5173${NC}"
echo -e "${GREEN}📍 Docs API: http://localhost:8000/docs${NC}"
echo ""
echo -e "${YELLOW}📝 Logs:${NC}"
echo "   Backend:  tail -f backend/backend.log"
echo "   Frontend: tail -f frontend/rpa-dominio-frontend/frontend.log"
echo ""
echo -e "${YELLOW}🛑 Para parar:${NC}"
echo "   kill $BACKEND_PID $FRONTEND_PID"
echo "   ou: pkill -f 'uvicorn app.main:app' && pkill -f 'vite'"
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"

# Mantém script rodando
wait






