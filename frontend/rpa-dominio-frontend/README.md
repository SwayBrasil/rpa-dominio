# RPA Domínio - Frontend

Interface web para o Comparador de Extratos Bancários.

## 🚀 Setup

### Instalação

```bash
# Instalar dependências
npm install

# Copiar arquivo de ambiente
cp .env.example .env
```

Edite o `.env` se necessário:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### Desenvolvimento

```bash
npm run dev
```

A aplicação estará disponível em `http://localhost:5173`

### Build para produção

```bash
npm run build
```

Os arquivos estarão em `dist/`

## 📋 Funcionalidades

- Upload de extrato bancário (PDF)
- Configuração de período e filtros
- Listagem de comparações realizadas
- Visualização detalhada de divergências
- Filtro por tipo de divergência

## 🔗 Integração

O frontend se comunica com a API backend em `http://localhost:8000` por padrão.

Certifique-se de que o backend está rodando antes de usar o frontend.






