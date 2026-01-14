"""
Teste simples para verificar inicialização do banco de dados
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import init_db, SessionLocal
from app.models.comparacao import Comparacao

def main():
    """Testa criação do banco e modelos"""
    print("Inicializando banco de dados...")
    init_db()
    print("✅ Banco de dados inicializado")
    
    # Testa conexão
    db = SessionLocal()
    try:
        count = db.query(Comparacao).count()
        print(f"✅ Conexão OK. Total de comparações: {count}")
    except Exception as e:
        print(f"❌ Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()






