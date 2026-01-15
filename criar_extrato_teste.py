#!/usr/bin/env python3
"""
Script para criar um PDF de extrato Sicoob de teste.
Requer: pip install reportlab
"""

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
except ImportError:
    print("ERRO: reportlab não está instalado.")
    print("Instale com: pip install reportlab")
    exit(1)

def criar_extrato_sicoob_teste():
    """Cria um PDF simples de extrato Sicoob para testes"""
    
    output_path = "EXTRATO_SICOOB_TESTE.pdf"
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Cabeçalho
    y = height - 2*cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, y, "SICOOB")
    c.setFont("Helvetica", 10)
    y -= 0.5*cm
    c.drawString(2*cm, y, "Sistema de Cooperativas de Crédito do Brasil")
    
    y -= 0.5*cm
    c.drawString(2*cm, y, "EXTRATO CONTA CORRENTE")
    y -= 0.3*cm
    c.drawString(2*cm, y, "COOP.: 12345 | CONTA: 12345-6 | AGÊNCIA: 0001")
    
    # Período
    y -= 0.8*cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2*cm, y, "PERÍODO: 01/03/2025 - 31/03/2025")
    
    # Cabeçalho da tabela
    y -= 0.8*cm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2*cm, y, "DATA")
    c.drawString(4*cm, y, "HISTÓRICO")
    c.drawString(15*cm, y, "VALOR")
    
    # Linha separadora
    y -= 0.2*cm
    c.line(2*cm, y, 18*cm, y)
    
    # Lançamentos (formato: DD/MM Descrição Valor D/C)
    lancamentos = [
        ("15/03", "PAGAMENTO FORNECEDOR ABC LTDA", "1.500,00", "D"),
        ("16/03", "PIX ENVIADO PARA JOAO SILVA", "300,00", "D"),
        ("20/03", "TARIFA BANCARIA MENSAL", "25,00", "D"),
        ("22/03", "PAGAMENTO BOLETO 12345", "1.200,00", "D"),
        ("25/03", "TED ENVIADA PARA CONTA 12345-6", "800,00", "D"),
        ("28/03", "PAGAMENTO FORNECEDOR XYZ COMERCIO", "2.000,00", "D"),
        ("01/03", "RECEBIMENTO CLIENTE ABC LTDA", "5.000,00", "C"),
        ("05/03", "PIX RECEBIDO DE MARIA COSTA", "1.500,00", "C"),
        ("10/03", "TED RECEBIDA CONTA 11111-2", "3.000,00", "C"),
        ("12/03", "RECEBIMENTO CLIENTE XYZ S.A.", "4.200,00", "C"),
    ]
    
    c.setFont("Helvetica", 9)
    y -= 0.5*cm
    
    for data, descricao, valor, dc in lancamentos:
        if y < 3*cm:  # Nova página se necessário
            c.showPage()
            y = height - 2*cm
        
        # Data
        c.drawString(2*cm, y, data)
        
        # Descrição (truncada se muito longa)
        desc_display = descricao[:40] if len(descricao) > 40 else descricao
        c.drawString(4*cm, y, desc_display)
        
        # Valor
        c.drawString(15*cm, y, valor)
        
        # D/C na linha seguinte (formato Sicoob)
        y -= 0.4*cm
        c.drawString(15*cm, y, dc)
        
        y -= 0.3*cm
    
    # Saldo
    y -= 0.5*cm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2*cm, y, "SALDO DO DIA")
    c.drawString(15*cm, y, "10.675,00")
    
    c.save()
    print(f"PDF criado com sucesso: {output_path}")

if __name__ == "__main__":
    criar_extrato_sicoob_teste()
