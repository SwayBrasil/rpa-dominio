#!/bin/bash
# Script para resetar o banco de dados local (útil para testes)

echo "🔄 Resetando banco de dados local..."
echo ""

# Navega para o diretório do backend
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

DB_PATH="data/rpa_dominio.db"

if [ -f "$DB_PATH" ]; then
    echo "📁 Removendo banco existente: $DB_PATH"
    rm -f "$DB_PATH"
    echo "✅ Banco removido"
else
    echo "⚠️  Banco não encontrado: $DB_PATH"
fi

echo ""
echo "🔧 Recriando schema..."

# Verifica se venv existe e ativa
if [ -d "venv" ]; then
    echo "   Ativando ambiente virtual..."
    source venv/bin/activate
elif [ -d "../venv" ]; then
    echo "   Ativando ambiente virtual (diretório pai)..."
    source ../venv/bin/activate
else
    echo "⚠️  Ambiente virtual não encontrado. Tentando sem venv..."
fi

python3 << 'PYTHON_SCRIPT'
import sys
from pathlib import Path

# Adiciona o diretório do backend ao path
backend_dir = Path.cwd()
sys.path.insert(0, str(backend_dir))

try:
    from app.db import init_db, SessionLocal
    from app.services.validations.seed_rules import seed_example_rules

    print('Inicializando banco...')
    init_db()
    print('✅ Schema criado')

    print('Seed de regras de validação...')
    db = SessionLocal()
    try:
        seed_example_rules(db)
        db.commit()
        print('✅ Regras seeded')
    except Exception as e:
        print(f'⚠️  Erro ao seedar regras: {e}')
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()
except ImportError as e:
    print(f'❌ Erro de importação: {e}')
    print('   Certifique-se de que o ambiente virtual está ativado e as dependências instaladas.')
    print('   Execute: source venv/bin/activate && pip install -r requirements.txt')
    sys.exit(1)
except Exception as e:
    print(f'❌ Erro inesperado: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_SCRIPT

echo ""
echo "✅ Banco resetado com sucesso!"
echo "📁 Localização: $DB_PATH"

