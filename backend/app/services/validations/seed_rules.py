"""
Seed de regras de validação de exemplo
"""

from sqlalchemy.orm import Session
from app.models.plano_contas import AccountValidationRule


def seed_example_rules(db: Session):
    """
    Insere regras de exemplo para validação de contas.
    """
    regras_exemplo = [
        {
            "name": "Clientes - Contas 1.1 e 1.2",
            "is_enabled": True,
            "match_field": "entity_type",
            "match_value": "CLIENTE",
            "allowed_account_prefixes": ["1.1", "1.2"],
            "allowed_account_codes": None,
            "blocked_account_prefixes": None,
            "blocked_account_codes": None,
            "severity": "error",
            "message": "Lançamentos de CLIENTE devem usar contas que começam com 1.1 ou 1.2"
        },
        {
            "name": "Fornecedores - Contas 2.1 e 2.2",
            "is_enabled": True,
            "match_field": "entity_type",
            "match_value": "FORNECEDOR",
            "allowed_account_prefixes": ["2.1", "2.2"],
            "allowed_account_codes": None,
            "blocked_account_prefixes": None,
            "blocked_account_codes": None,
            "severity": "error",
            "message": "Lançamentos de FORNECEDOR devem usar contas que começam com 2.1 ou 2.2"
        },
        {
            "name": "Impostos - Conta 2.112",
            "is_enabled": True,
            "match_field": "category",
            "match_value": "IMPOSTO",
            "allowed_account_prefixes": ["2.112"],
            "allowed_account_codes": None,
            "blocked_account_prefixes": None,
            "blocked_account_codes": None,
            "severity": "error",
            "message": "Lançamentos de IMPOSTO devem usar contas que começam com 2.112"
        },
    ]
    
    for regra_data in regras_exemplo:
        # Verifica se já existe
        existing = (
            db.query(AccountValidationRule)
            .filter(AccountValidationRule.name == regra_data["name"])
            .first()
        )
        
        if not existing:
            regra = AccountValidationRule(**regra_data)
            db.add(regra)
            print(f"Regra criada: {regra_data['name']}")
        else:
            print(f"Regra já existe: {regra_data['name']}")
    
    db.commit()
    print("Seed de regras concluído")


if __name__ == "__main__":
    from app.db import SessionLocal
    
    db = SessionLocal()
    try:
        seed_example_rules(db)
    finally:
        db.close()


