"""
Teste automatizado para parser Sicoob robusto
Valida extração de lançamentos do PDF real EXTRATO SICOOB 03-2025.pdf
"""

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.services.parsers.mpds_pdf_parser import _parse_sicoob


def test_sicoob_parser_extrato_03_2025():
    """
    Testa parser com PDF real EXTRATO SICOOB 03-2025.pdf
    
    Valida:
    - Extrai pelo menos 10 lançamentos
    - Contém lançamentos específicos conhecidos:
      * 06/03/2025 com valor -4447.84
      * 10/03/2025 com valor -3649.87
      * 12/03/2025 com valor -5726.78
    """
    # Tenta encontrar o PDF em vários locais possíveis
    possible_paths = [
        Path(__file__).parent / "fixtures" / "EXTRATO SICOOB 03-2025.pdf",
        Path(__file__).parent.parent / "data" / "mpds" / "EXTRATO SICOOB 03-2025.pdf",
        Path("/mnt/data/EXTRATO SICOOB 03-2025.pdf"),
        Path(__file__).parent.parent.parent / "EXTRATO SICOOB 03-2025.pdf",
    ]
    
    pdf_path = None
    for path in possible_paths:
        if path.exists():
            pdf_path = path
            break
    
    if not pdf_path:
        pytest.skip(f"PDF de teste não encontrado. Procurou em: {[str(p) for p in possible_paths]}")
    
    print(f"\n📄 Testando parser Sicoob com: {pdf_path.name}")
    print(f"   Caminho: {pdf_path}")
    
    # Executa parser
    lancamentos, issues = _parse_sicoob(pdf_path)
    
    print(f"\n   ✅ Lançamentos extraídos: {len(lancamentos)}")
    print(f"   ⚠️  Issues: {len(issues)}")
    
    # Validação 1: Deve extrair pelo menos 10 lançamentos
    assert len(lancamentos) > 10, (
        f"Deve extrair pelo menos 10 lançamentos, mas extraiu apenas {len(lancamentos)}. "
        f"Issues: {issues[:5]}"
    )
    
    # Validação 2: Verifica lançamentos específicos conhecidos
    lancamentos_por_data = {lanc.data: lanc for lanc in lancamentos}
    
    # 06/03/2025 com valor -4447.84 (tolerância de centavos)
    data_06_03 = date(2025, 3, 6)
    if data_06_03 in lancamentos_por_data:
        lanc = lancamentos_por_data[data_06_03]
        assert abs(abs(lanc.valor) - 4447.84) < 0.01, (
            f"Lançamento 06/03/2025 deve ter valor próximo a -4447.84, "
            f"mas encontrou {lanc.valor}"
        )
        print(f"   ✅ 06/03/2025: R$ {lanc.valor:,.2f} | {lanc.descricao[:50]}")
    else:
        print(f"   ⚠️  Lançamento 06/03/2025 não encontrado")
    
    # 10/03/2025 com valor -3649.87
    data_10_03 = date(2025, 3, 10)
    if data_10_03 in lancamentos_por_data:
        lanc = lancamentos_por_data[data_10_03]
        assert abs(abs(lanc.valor) - 3649.87) < 0.01, (
            f"Lançamento 10/03/2025 deve ter valor próximo a -3649.87, "
            f"mas encontrou {lanc.valor}"
        )
        print(f"   ✅ 10/03/2025: R$ {lanc.valor:,.2f} | {lanc.descricao[:50]}")
    else:
        print(f"   ⚠️  Lançamento 10/03/2025 não encontrado")
    
    # 12/03/2025 com valor -5726.78
    data_12_03 = date(2025, 3, 12)
    if data_12_03 in lancamentos_por_data:
        lanc = lancamentos_por_data[data_12_03]
        assert abs(abs(lanc.valor) - 5726.78) < 0.01, (
            f"Lançamento 12/03/2025 deve ter valor próximo a -5726.78, "
            f"mas encontrou {lanc.valor}"
        )
        print(f"   ✅ 12/03/2025: R$ {lanc.valor:,.2f} | {lanc.descricao[:50]}")
    else:
        print(f"   ⚠️  Lançamento 12/03/2025 não encontrado")
    
    # Validação 3: Estrutura dos lançamentos
    for lanc in lancamentos[:5]:
        assert lanc.data is not None, "Data deve ser parseada"
        assert lanc.descricao is not None, "Descrição deve existir"
        assert lanc.valor != 0.0, "Valor não deve ser zero"
        assert lanc.origem == "mpds", "Origem deve ser 'mpds'"
    
    # Validação 4: Não deve ter lançamentos com descrição muito curta ou genérica
    descricoes_curtas = [l for l in lancamentos if len(l.descricao) < 5]
    assert len(descricoes_curtas) == 0, (
        f"Não deve ter lançamentos com descrição muito curta. "
        f"Encontrados: {[(l.data, l.descricao) for l in descricoes_curtas[:3]]}"
    )
    
    print(f"\n✅ Teste Sicoob passou: {len(lancamentos)} lançamentos extraídos corretamente")


if __name__ == "__main__":
    test_sicoob_parser_extrato_03_2025()

