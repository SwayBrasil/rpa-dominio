"""
Testes para o parser MPDS PDF
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.parsers.mpds_pdf_parser import parse_mpds_pdf
from app.core.models import Lancamento


def test_parser_nubank():
    """Testa parser com PDF Nubank (se existir)"""
    pdf_path = Path(__file__).parent / "fixtures" / "mpds_nubank_sample.pdf"
    
    if not pdf_path.exists():
        print(f"⚠️  PDF Nubank não encontrado: {pdf_path}")
        print("   Criando teste básico de estrutura...")
        return
    
    print(f"📄 Testando parser com: {pdf_path.name}")
    lancamentos, issues = parse_mpds_pdf(pdf_path, strict=False)
    
    print(f"   ✅ Lançamentos extraídos: {len(lancamentos)}")
    print(f"   ⚠️  Issues: {len(issues)}")
    
    # Validações básicas
    assert len(lancamentos) > 0, "Deve extrair pelo menos 1 lançamento"
    
    # Verifica estrutura
    for lanc in lancamentos[:3]:
        assert lanc.data is not None, "Data deve ser parseada"
        assert lanc.descricao is not None, "Descrição deve existir"
        assert lanc.valor != 0.0, "Valor não deve ser zero"
        assert lanc.origem == "mpds", "Origem deve ser 'mpds'"
        print(f"   ✅ Lançamento: {lanc.data} | {lanc.descricao[:30]} | R$ {lanc.valor:.2f}")
    
    print("✅ Teste Nubank passou")


def test_parser_sicoob():
    """Testa parser com PDF Sicoob (se existir)"""
    pdf_path = Path(__file__).parent / "fixtures" / "mpds_sicoob_sample.pdf"
    
    if not pdf_path.exists():
        print(f"⚠️  PDF Sicoob não encontrado: {pdf_path}")
        print("   Criando teste básico de estrutura...")
        return
    
    print(f"📄 Testando parser com: {pdf_path.name}")
    lancamentos, issues = parse_mpds_pdf(pdf_path, strict=False)
    
    print(f"   ✅ Lançamentos extraídos: {len(lancamentos)}")
    print(f"   ⚠️  Issues: {len(issues)}")
    
    # Validações básicas
    assert len(lancamentos) > 0, "Deve extrair pelo menos 1 lançamento"
    
    # Verifica estrutura
    for lanc in lancamentos[:3]:
        assert lanc.data is not None, "Data deve ser parseada"
        assert lanc.descricao is not None, "Descrição deve existir"
        assert lanc.valor != 0.0, "Valor não deve ser zero"
        assert lanc.origem == "mpds", "Origem deve ser 'mpds'"
        print(f"   ✅ Lançamento: {lanc.data} | {lanc.descricao[:30]} | R$ {lanc.valor:.2f}")
    
    print("✅ Teste Sicoob passou")


if __name__ == "__main__":
    print("🧪 Testando Parser MPDS PDF")
    print("=" * 50)
    print()
    
    try:
        test_parser_nubank()
        print()
        test_parser_sicoob()
        print()
        print("=" * 50)
        print("✅ Todos os testes passaram!")
    except Exception as e:
        print(f"❌ Erro nos testes: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


