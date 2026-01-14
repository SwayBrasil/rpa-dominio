# Comparador de Extratos - TXT Otimiza x MPDS

Ferramenta para comparar lançamentos contábeis do **TXT Otimiza** com movimentações bancárias do **MPDS** (extrato estruturado em CSV/OFX).

## 📋 Funcionalidades

- ✅ Upload de **TXT Otimiza** (lançamentos contábeis com códigos de conta)
- ✅ Upload de **MPDS** (extrato estruturado em CSV, OFX ou PDF - Nubank/Sicoob)
- ✅ Upload de **Plano de Contas** do Domínio (CSV/XLSX) para validação
- ✅ Comparação automática entre TXT e MPDS
- ✅ Validação determinística de contas contábeis
- ✅ Detecção de divergências (lançamentos faltantes, valores diferentes)
- ✅ Interface web para visualização de resultados

## 🚀 Setup

### Pré-requisitos

- Python 3.11 ou superior
- Node.js 18+ (para frontend)
- npm ou yarn

### Instalação Backend

1. Crie um ambiente virtual:

```bash
cd backend
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

**Nota:** Não é mais necessário instalar Playwright. O sistema não usa RPA. O sistema aceita extratos bancários em PDF (Nubank/Sicoob), além de CSV e OFX.

### Instalação Frontend

```bash
cd frontend/rpa-dominio-frontend
npm install
```

## 🏃 Como Rodar

### Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

A API estará disponível em:
- API: http://localhost:8000
- Documentação Swagger: http://localhost:8000/docs

### Frontend

```bash
cd frontend/rpa-dominio-frontend
npm run dev
```

A interface estará disponível em: http://localhost:5173

## 📖 Como Usar

### 1. Upload do Plano de Contas (Recomendado)

Antes de criar comparações, faça upload do plano de contas do Domínio:

```bash
curl -X POST "http://localhost:8000/plano-contas/upload" \
  -F "file=@plano_contas.csv" \
  -F "source=dominio" \
  -F "replace=true"
```

**Formato do CSV:**
```csv
codigo,descricao,nivel,pai,tipo,nature
1.1,Ativo Circulante,1,,ASSET,DEBIT
1.1.1,Caixa,2,1.1,ASSET,DEBIT
2.1,Passivo Circulante,1,,LIABILITY,CREDIT
```

### 2. Criar Comparação

Via API:
```bash
curl -X POST "http://localhost:8000/comparacoes/" \
  -F "data_inicio=2025-01-01" \
  -F "data_fim=2025-01-31" \
  -F "otimiza_txt=@otimiza.txt" \
  -F "mpds_csv=@mpds.csv"
```

Via Frontend:
1. Acesse http://localhost:5173
2. Preencha as datas
3. Faça upload do TXT Otimiza
4. Faça upload do MPDS (CSV ou OFX)
5. Clique em "Rodar comparação"

### 3. Ver Resultados

```bash
# Detalhes da comparação
curl "http://localhost:8000/comparacoes/{id}"

# Validações de contas
curl "http://localhost:8000/comparacoes/{id}/validacao-contas"

# Divergências
curl "http://localhost:8000/comparacoes/{id}/divergencias"
```

## 🧪 Testar

### Teste via Interface Web

1. Acesse http://localhost:5173
2. Preencha o período (data início e fim)
3. Faça upload do extrato bancário em PDF (Nubank ou Sicoob)
4. Faça upload do(s) arquivo(s) TXT do Otimiza (PAGAR e/ou RECEBER)
5. Clique em "Rodar conferência"
6. Visualize os resultados e divergências

### Teste via API

```bash
# Criar comparação
curl -X POST "http://localhost:8000/comparacoes/" \
  -F "data_inicio=2025-01-01" \
  -F "data_fim=2025-01-31" \
  -F "otimiza_txt_files=@otimiza_pagar.txt" \
  -F "otimiza_txt_files=@otimiza_receber.txt" \
  -F "mpds_pdf=@extrato.pdf"

# Ver detalhes
curl "http://localhost:8000/comparacoes/{id}" | python3 -m json.tool
```

### Reset do Banco (se necessário)

Se houver problemas com o banco de dados:

```bash
cd backend
./scripts/reset_db.sh
```

## 📁 Estrutura do Projeto

```
.
├── backend/
│   ├── app/
│   │   ├── api/              # Endpoints FastAPI
│   │   ├── core/             # Configurações e modelos base
│   │   ├── models/           # Modelos SQLAlchemy
│   │   ├── services/         # Lógica de negócio
│   │   │   ├── parsers/      # Parsers de TXT, CSV, OFX
│   │   │   ├── comparador/   # Motor de comparação
│   │   │   └── validations/  # Validação de contas
│   │   └── db.py             # Configuração do banco
│   ├── tests/                # Testes e fixtures
│   └── data/                 # Arquivos processados
│       ├── otimiza/          # TXTs do Otimiza
│       └── mpds/             # MPDS (CSV/OFX)
├── frontend/
│   └── rpa-dominio-frontend/ # Interface React
├── documentos_teste/         # Documentos de teste (PDFs)
└── README.md
```

## 🔄 Fluxo do Sistema

1. **Upload do Plano de Contas** (opcional, mas recomendado)
   - CSV/XLSX exportado do Domínio
   - Contém códigos de conta, nomes, tipos

2. **Upload de Arquivos**
   - TXT Otimiza: lançamentos contábeis com códigos de conta
   - MPDS: extrato estruturado (CSV ou OFX)

3. **Processamento**
   - Parsing dos arquivos
   - Comparação TXT vs MPDS
   - Validação de contas contábeis

4. **Resultados**
   - Divergências encontradas
   - Validações de contas (ok/invalid/unknown)
   - Resumo estatístico

## 📊 Validação de Contas

O sistema valida contas contábeis de forma **100% determinística**:

- ✅ Verifica se a conta existe no plano de contas
- ✅ Aplica regras explícitas (ex: CLIENTE → contas 1.1/1.2)
- ✅ Registra motivo claro para cada validação
- ❌ **NÃO** usa heurísticas ou inferências
- ❌ **NÃO** tenta adivinhar contas

## 🚀 API Endpoints

### Comparações

- `POST /comparacoes` - Criar comparação (TXT + MPDS)
- `GET /comparacoes` - Listar comparações
- `GET /comparacoes/{id}` - Detalhes da comparação
- `GET /comparacoes/{id}/divergencias` - Listar divergências
- `GET /comparacoes/{id}/validacao-contas` - Validações de contas
- `DELETE /comparacoes/{id}` - Deletar comparação

### Plano de Contas

- `POST /plano-contas/upload` - Upload do plano (CSV/XLSX)
- `GET /plano-contas` - Listar contas

### Documentação

- `GET /docs` - Swagger UI
- `GET /health` - Health check

## 🔒 Segurança

- Banco de dados SQLite local (não exposto)
- Arquivos processados armazenados localmente
- Sem credenciais necessárias (não usa mais Domínio Web)

## 📝 Notas Importantes

- **Não usa mais Domínio Web**: O sistema não faz login nem RPA no Domínio
- **Plano de Contas**: Apenas como referência para validação (export manual)
- **Formato TXT**: O parser é flexível, mas pode precisar de ajustes conforme o layout real
- **Formato MPDS**: Suporta CSV, OFX e PDF (Nubank/Sicoob), com detecção automática de colunas/tabelas

## 🆘 Troubleshooting

### Erro "SQLite database is locked"

✅ **Corrigido!** O sistema agora usa WAL mode e pool adequado.

### Erro ao criar comparação

- Verifique se os arquivos não estão vazios
- Verifique o formato dos arquivos (TXT e CSV/OFX)
- Veja os logs do backend para mais detalhes

### Validações retornando "unknown"

- Faça upload do plano de contas primeiro
- Crie regras de validação apropriadas
- Verifique se o TXT contém códigos de conta

## 📚 Testes Automatizados

O projeto inclui testes automatizados para validar os parsers:

```bash
cd backend
source venv/bin/activate
pytest tests/
```

Testes disponíveis:
- `test_mpds_pdf_parser.py` - Testes do parser de PDF (Nubank/Sicoob)
- `test_sicoob_parser_robust.py` - Testes específicos do parser Sicoob
- `test_db_init.py` - Testes de inicialização do banco de dados

---

**Versão:** 2.0.0 (sem RPA/Domínio)  
**Última atualização:** 14/12/2025
