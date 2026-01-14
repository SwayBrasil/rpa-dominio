# 🚀 Guia de Deploy no Render

Este guia explica como publicar o projeto Comparador de Extratos no Render.

## 📋 Pré-requisitos

1. Conta no [Render](https://render.com) (gratuita)
2. Repositório no GitHub (já configurado: `SwayBrasil/rpa-dominio`)
3. Acesso ao repositório GitHub

## 🎯 Opção 1: Deploy Automático via render.yaml (Recomendado)

### Passo 1: Conectar Repositório

1. Acesse [Render Dashboard](https://dashboard.render.com)
2. Clique em **"New +"** → **"Blueprint"**
3. Conecte seu repositório GitHub: `SwayBrasil/rpa-dominio`
4. Render detectará automaticamente o arquivo `render.yaml`
5. Clique em **"Apply"**

### Passo 2: Configuração Automática

O `render.yaml` criará automaticamente:
- ✅ **Backend** (Web Service Python)
- ✅ **Frontend** (Static Site)
- ✅ **PostgreSQL Database**

### Passo 3: Variáveis de Ambiente

O Render configurará automaticamente:
- `DATABASE_URL` - Conectado ao PostgreSQL
- `VITE_API_BASE_URL` - URL do backend para o frontend

## 🎯 Opção 2: Deploy Manual (Passo a Passo)

### 1. Criar Banco de Dados PostgreSQL

1. No Render Dashboard, clique em **"New +"** → **"PostgreSQL"**
2. Configure:
   - **Name:** `rpa-dominio-db`
   - **Database:** `rpa_dominio`
   - **User:** `rpa_dominio_user`
   - **Region:** `Oregon` (ou mais próximo)
   - **Plan:** `Free`
3. Clique em **"Create Database"**
4. **Copie a Internal Database URL** (será usada depois)

### 2. Criar Backend (Web Service)

1. No Render Dashboard, clique em **"New +"** → **"Web Service"**
2. Conecte o repositório: `SwayBrasil/rpa-dominio`
3. Configure:

   **Basic Settings:**
   - **Name:** `rpa-dominio-backend`
   - **Region:** `Oregon`
   - **Branch:** `main`
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r ../requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

   **Environment Variables:**
   ```
   PYTHON_VERSION=3.11.0
   ENVIRONMENT=production
   DEBUG=false
   DATABASE_URL=<cole a Internal Database URL do PostgreSQL>
   DATA_DIR=./data
   ```

4. Clique em **"Create Web Service"**

### 3. Criar Frontend (Static Site)

1. No Render Dashboard, clique em **"New +"** → **"Static Site"**
2. Conecte o repositório: `SwayBrasil/rpa-dominio`
3. Configure:

   **Basic Settings:**
   - **Name:** `rpa-dominio-frontend`
   - **Branch:** `main`
   - **Root Directory:** `frontend/rpa-dominio-frontend`
   - **Build Command:** `npm install && npm run build`
   - **Publish Directory:** `dist`

   **Environment Variables:**
   ```
   VITE_API_BASE_URL=https://rpa-dominio-backend.onrender.com
   ```
   ⚠️ **Importante:** Substitua `rpa-dominio-backend` pelo nome real do seu backend no Render.

4. Clique em **"Create Static Site"**

## 🔧 Configurações Importantes

### Backend

- **Port:** Render define automaticamente via `$PORT`
- **Health Check:** `/health` (configurado no `render.yaml`)
- **Database:** PostgreSQL (conexão automática via `DATABASE_URL`)

### Frontend

- **Build:** Vite compila para `dist/`
- **API URL:** Configurada via `VITE_API_BASE_URL`
- **CORS:** Backend permite todas as origens (ajuste em produção se necessário)

## 🔐 Segurança em Produção

### 1. CORS no Backend

Edite `backend/app/main.py` para restringir CORS:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rpa-dominio-frontend.onrender.com",
        "http://localhost:5173"  # Para desenvolvimento local
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. Variáveis Sensíveis

Nunca commite arquivos `.env` com credenciais. Use **Environment Variables** no Render Dashboard.

## 📊 Monitoramento

- **Logs:** Acesse os logs em tempo real no Dashboard do Render
- **Health Check:** Backend responde em `/health`
- **Métricas:** Render fornece métricas básicas no plano gratuito

## 🐛 Troubleshooting

### Backend não inicia

1. Verifique os logs no Render Dashboard
2. Confirme que `DATABASE_URL` está configurado
3. Verifique se todas as dependências estão em `requirements.txt`

### Frontend não conecta ao backend

1. Verifique `VITE_API_BASE_URL` no frontend
2. Confirme que o backend está rodando (verifique `/health`)
3. Verifique CORS no backend

### Erro de banco de dados

1. Confirme que o PostgreSQL está criado e ativo
2. Verifique `DATABASE_URL` (deve ser Internal Database URL)
3. Verifique se as tabelas foram criadas (backend cria automaticamente na startup)

### Build falha

1. Verifique logs de build no Render
2. Confirme que `requirements.txt` está na raiz do projeto
3. Verifique se todas as dependências estão corretas

## 📝 URLs Finais

Após o deploy, você terá:

- **Backend:** `https://rpa-dominio-backend.onrender.com`
- **Frontend:** `https://rpa-dominio-frontend.onrender.com`
- **API Docs:** `https://rpa-dominio-backend.onrender.com/docs`

## 🔄 Atualizações

O Render faz **deploy automático** quando você faz push para a branch `main` no GitHub.

Para forçar um novo deploy:
1. Vá no Dashboard do serviço
2. Clique em **"Manual Deploy"** → **"Deploy latest commit"**

## 💰 Custos

- **Plano Free:** 
  - Backend: 750 horas/mês (suficiente para uso moderado)
  - Frontend: Ilimitado
  - PostgreSQL: 90 dias (depois precisa upgrade ou recriar)

**Nota:** Serviços free "dormem" após 15 minutos de inatividade. O primeiro acesso pode demorar ~30s para "acordar".

---

**Última atualização:** 14/12/2025
