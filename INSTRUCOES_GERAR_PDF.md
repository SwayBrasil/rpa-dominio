# Instruções para Gerar PDF de Teste

## Arquivos TXT Criados ✅

1. **EXTRATO_TESTE_PAGAR.txt** - Arquivo TXT PAGAR com 6 lançamentos
2. **EXTRATO_TESTE_RECEBER.txt** - Arquivo TXT RECEBER com 6 lançamentos

## Gerar PDF de Extrato Sicoob

Para gerar o PDF de extrato bancário, você precisa instalar a biblioteca `reportlab`:

### Opção 1: Usar ambiente virtual do backend (recomendado)

```bash
cd backend
source venv/bin/activate
pip install reportlab
cd ..
python3 criar_extrato_teste.py
```

### Opção 2: Instalar globalmente

```bash
pip3 install reportlab
python3 criar_extrato_teste.py
```

### Opção 3: Usar PDF existente

Se não conseguir instalar reportlab, você pode usar um dos PDFs de teste existentes:
- `backend/data/mpds/` contém vários PDFs de extrato Sicoob
- Exemplo: `backend/data/mpds/20251218_114834_EXTRATO SICOOB 03-2025.pdf`

O script `criar_extrato_teste.py` criará um PDF chamado **EXTRATO_SICOOB_TESTE.pdf** com lançamentos correspondentes aos arquivos TXT criados.
