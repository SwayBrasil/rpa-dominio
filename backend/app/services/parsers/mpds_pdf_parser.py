"""
Parser para extratos bancários em PDF (Nubank/Sicoob)
Extrai movimentações para formato MPDS
"""

import re
import logging
from typing import List, Tuple, Optional
from pathlib import Path
from datetime import datetime, date

import pdfplumber
from app.core.models import Lancamento

logger = logging.getLogger(__name__)


def _parse_valor(valor_str: str) -> float:
    """
    Converte string brasileira de valor para float.
    
    Exemplos:
        'R$ 1.234,56' -> 1234.56
        '1.234,56-' -> -1234.56
        '1.234,56D' -> -1234.56 (D = débito)
        '1.234,56C' -> 1234.56 (C = crédito)
    """
    if not valor_str or valor_str.strip() == '':
        return 0.0
    
    valor_str = valor_str.strip()
    
    # Remove R$ e espaços
    valor_str = re.sub(r'R\$\s*', '', valor_str)
    valor_str = valor_str.strip()
    
    # Detecta sinal negativo
    negativo = False
    if valor_str.endswith('-') or valor_str.endswith('D') or valor_str.endswith('d'):
        negativo = True
        valor_str = valor_str[:-1].strip()
    elif valor_str.startswith('-'):
        negativo = True
        valor_str = valor_str[1:].strip()
    
    # Remove pontos (milhares) e substitui vírgula por ponto (decimal)
    valor_str = valor_str.replace('.', '').replace(',', '.')
    
    try:
        valor = float(valor_str)
        return -valor if negativo else valor
    except ValueError:
        logger.warning(f"Não foi possível converter valor: {valor_str}")
        return 0.0


def _parse_data(data_str: str) -> Optional[date]:
    """
    Tenta parsear data em vários formatos brasileiros.
    
    Formatos suportados:
    - DD/MM/YYYY
    - DD/MM/YY
    - DD-MM-YYYY
    """
    if not data_str or not data_str.strip():
        return None
    
    data_str = data_str.strip()
    
    # Remove espaços extras
    data_str = re.sub(r'\s+', ' ', data_str)
    
    # Tenta formatos comuns
    formatos = [
        '%d/%m/%Y',
        '%d/%m/%y',
        '%d-%m-%Y',
        '%d-%m-%y',
        '%Y-%m-%d',
    ]
    
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            continue
    
    logger.warning(f"Não foi possível parsear data: {data_str}")
    return None


def _normalizar_descricao(desc: str) -> str:
    """Normaliza descrição: trim e collapse espaços"""
    if not desc:
        return ""
    return re.sub(r'\s+', ' ', desc.strip())


# Regex para detectar período no PDF Sicoob
RE_PERIODO = re.compile(r"PER[IÍ]ODO\s*:\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
RE_LINHA_LANC = re.compile(
    r"^(?P<dd>\d{2})/(?P<mm>\d{2})(?:/(?P<yyyy>\d{2,4}))?\s+(?P<desc>.+?)\s+(?P<val>\d{1,3}(?:\.\d{3})*,\d{2})\s*$"
)


def _infer_year_from_period(texto: str) -> Optional[int]:
    """Infere o ano do período extraído do texto do PDF"""
    m = RE_PERIODO.search(texto or "")
    if not m:
        return None
    try:
        ini = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        fim = datetime.strptime(m.group(2), "%d/%m/%Y").date()
        # geralmente o extrato é do mesmo ano; se atravessar ano, você pode ajustar conforme o mês
        return fim.year
    except Exception:
        return None


def _detectar_banco(texto_pagina: str) -> str:
    """
    Detecta qual banco é baseado no texto da primeira página.
    Retorna 'nubank', 'sicoob' ou 'unknown'
    """
    texto_lower = texto_pagina.lower()
    
    if 'nubank' in texto_lower or 'nu pagamentos' in texto_lower:
        return 'nubank'
    elif 'sicoob' in texto_lower or 'sistema de cooperativas' in texto_lower:
        return 'sicoob'
    
    return 'unknown'


def _parse_nubank(pdf_path: Path) -> Tuple[List[Lancamento], List[str]]:
    """
    Parser específico para extratos Nubank.
    
    Formato típico:
    - Tabela com colunas: Data, Descrição, Valor
    - Valores podem ter R$ e vírgula decimal
    """
    lancamentos = []
    issues = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for num_pag, page in enumerate(pdf.pages, 1):
                texto = page.extract_text()
                if not texto:
                    continue
                
                # Tenta extrair tabela
                tabelas = page.extract_tables()
                
                for tabela in tabelas:
                    if not tabela or len(tabela) < 2:
                        continue
                    
                    # Primeira linha geralmente é cabeçalho
                    # Procura por colunas de data, descrição, valor
                    cabecalho = tabela[0] if tabela else []
                    cabecalho_lower = ' '.join([str(c).lower() if c else '' for c in cabecalho])
                    
                    # Detecta índices das colunas
                    idx_data = None
                    idx_desc = None
                    idx_valor = None
                    
                    for i, col in enumerate(cabecalho):
                        col_lower = str(col).lower() if col else ''
                        if 'data' in col_lower or 'dia' in col_lower:
                            idx_data = i
                        elif 'descrição' in col_lower or 'descricao' in col_lower or 'histórico' in col_lower:
                            idx_desc = i
                        elif 'valor' in col_lower or 'saldo' in col_lower:
                            idx_valor = i
                    
                    # Se não encontrou cabeçalho, tenta detectar automaticamente
                    if idx_data is None or idx_desc is None or idx_valor is None:
                        # Tenta nas primeiras linhas
                        for linha in tabela[1:6]:
                            if not linha:
                                continue
                            # Primeira coluna geralmente é data
                            if idx_data is None and linha[0]:
                                data_teste = _parse_data(str(linha[0]))
                                if data_teste:
                                    idx_data = 0
                            # Última coluna geralmente é valor
                            if idx_valor is None and len(linha) > 1:
                                valor_teste = _parse_valor(str(linha[-1]))
                                if valor_teste != 0.0:
                                    idx_valor = len(linha) - 1
                            # Meio geralmente é descrição
                            if idx_desc is None and len(linha) > 2:
                                idx_desc = 1
                    
                    # Processa linhas da tabela
                    for linha_idx, linha in enumerate(tabela[1:], 1):
                        if not linha or len(linha) < 3:
                            continue
                        
                        try:
                            # Extrai dados
                            data_str = str(linha[idx_data]) if idx_data is not None and idx_data < len(linha) else None
                            descricao = str(linha[idx_desc]) if idx_desc is not None and idx_desc < len(linha) else None
                            valor_str = str(linha[idx_valor]) if idx_valor is not None and idx_valor < len(linha) else None
                            
                            if not data_str or not valor_str:
                                continue
                            
                            # Parse
                            data = _parse_data(data_str)
                            if not data:
                                issues.append(f"Página {num_pag}, linha {linha_idx}: Data inválida: {data_str}")
                                continue
                            
                            valor = _parse_valor(valor_str)
                            if valor == 0.0:
                                continue  # Ignora valores zero
                            
                            descricao = _normalizar_descricao(descricao) if descricao else "Sem descrição"
                            
                            lancamento = Lancamento(
                                data=data,
                                descricao=descricao,
                                documento=None,
                                valor=valor,
                                saldo=None,
                                conta_contabil=None,
                                origem="mpds"
                            )
                            lancamentos.append(lancamento)
                            
                        except Exception as e:
                            issues.append(f"Página {num_pag}, linha {linha_idx}: Erro ao processar: {e}")
                            continue
                
                # Se não encontrou tabelas, tenta extrair do texto
                # Formato Nubank típico:
                # "16 OUT 2025 Total de entradas + 12.763,60"
                # "Transferência Recebida ONCO RAD SERV RADI LTDA - 03.721.886/0001-50 3.378,60"
                # OU: "16 OUT 2025 Transferência enviada pelo Pix ... 1.123,60"
                if not lancamentos and texto:
                    # Padrão 1: DD MMM YYYY Descrição Valor (formato: "16 OUT 2025 Transferência ... 1.123,60")
                    padrao1 = re.compile(
                        r'(\d{1,2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+(\d{4})\s+(.+?)\s+([\d.,-]+)',
                        re.IGNORECASE | re.MULTILINE
                    )
                    matches1 = padrao1.findall(texto)
                    
                    meses = {
                        'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 'MAI': '05', 'JUN': '06',
                        'JUL': '07', 'AGO': '08', 'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
                    }
                    
                    for match in matches1:
                        dia, mes_abr, ano, desc, valor_str = match
                        mes_num = meses.get(mes_abr.upper(), '01')
                        data_str = f"{dia.zfill(2)}/{mes_num}/{ano}"
                        data = _parse_data(data_str)
                        if not data:
                            continue
                        valor = _parse_valor(valor_str)
                        if valor == 0.0:
                            continue
                        
                        # Remove palavras comuns do início da descrição
                        desc_clean = _normalizar_descricao(desc)
                        # Remove "Total de entradas" ou "Total de saídas" se presente
                        desc_clean = re.sub(r'^Total\s+de\s+(entradas|saídas)\s*[+-]?\s*', '', desc_clean, flags=re.IGNORECASE)
                        
                        lancamento = Lancamento(
                            data=data,
                            descricao=desc_clean,
                            documento=None,
                            valor=valor,
                            saldo=None,
                            conta_contabil=None,
                            origem="mpds"
                        )
                        lancamentos.append(lancamento)
                    
                    # Padrão 2: DD/MM/YYYY Descrição R$ 1.234,56 (formato tradicional)
                    if not lancamentos:
                        padrao2 = re.compile(r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(R\$\s*[\d.,-]+)', re.MULTILINE)
                        matches2 = padrao2.findall(texto)
                        
                        for match in matches2:
                            data_str, desc, valor_str = match
                            data = _parse_data(data_str)
                            if not data:
                                continue
                            valor = _parse_valor(valor_str)
                            if valor == 0.0:
                                continue
                            
                            lancamento = Lancamento(
                                data=data,
                                descricao=_normalizar_descricao(desc),
                                documento=None,
                                valor=valor,
                                saldo=None,
                                conta_contabil=None,
                                origem="mpds"
                            )
                            lancamentos.append(lancamento)
                    
                    # Padrão 3: Linhas separadas - data em uma linha, descrição+valor na próxima
                    # "16 OUT 2025 Total de entradas + 12.763,60"
                    # "Transferência Recebida ... 3.378,60"
                    # OU: "25 OUT 2025 Total de saídas - 318,00"
                    # "Transferência enviada pelo Pix ... 318,00"
                    if not lancamentos:
                        linhas = texto.split('\n')
                        datas_por_indice = {}  # Mapeia índice da linha para data
                        
                        # Primeiro passo: identifica todas as datas e armazena
                        for i, linha in enumerate(linhas):
                            linha_clean = linha.strip()
                            match_data = re.search(r'(\d{1,2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+(\d{4})', linha_clean, re.IGNORECASE)
                            if match_data:
                                dia, mes_abr, ano = match_data.groups()
                                mes_num = meses.get(mes_abr.upper(), '01')
                                data_str = f"{dia.zfill(2)}/{mes_num}/{ano}"
                                data_parsed = _parse_data(data_str)
                                if data_parsed:
                                    # Armazena data para esta linha e próximas (até próxima data)
                                    for j in range(i, min(i + 20, len(linhas))):
                                        if j not in datas_por_indice:
                                            datas_por_indice[j] = data_parsed
                        
                        # Segundo passo: procura movimentações e associa à data mais próxima anterior
                        for i, linha in enumerate(linhas):
                            linha_clean = linha.strip()
                            if not linha_clean or re.search(r'Total\s+de\s+(entradas|saídas)', linha_clean, re.IGNORECASE):
                                continue
                            
                            # Procura linhas com "Transferência" e valor no final
                            if 'Transferência' in linha_clean or 'transferência' in linha_clean:
                                # Procura valor no final da linha (formato: ... 1.234,56 ou ... 318,00)
                                # Pode estar na mesma linha ou na próxima
                                valor_str = None
                                desc = linha_clean
                                
                                # Tenta encontrar valor no final desta linha
                                match_valor = re.search(r'\s+([\d.,-]+)\s*$', linha_clean)
                                if not match_valor and i + 1 < len(linhas):
                                    # Se não encontrou, tenta na próxima linha
                                    linha_prox = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
                                    match_valor = re.search(r'([\d.,-]+)\s*$', linha_prox)
                                    if match_valor:
                                        desc = linha_clean + " " + linha_prox.replace(match_valor.group(0), '').strip()
                                
                                if match_valor:
                                    valor_str = match_valor.group(1)
                                    valor = _parse_valor(valor_str)
                                    if valor != 0.0 and abs(valor) > 0.01:
                                        # Busca data mais próxima anterior
                                        data_mov = None
                                        for j in range(i, max(-1, i - 10), -1):
                                            if j in datas_por_indice:
                                                data_mov = datas_por_indice[j]
                                                break
                                        
                                        if data_mov:
                                            # Remove o valor da descrição
                                            desc_clean = desc.replace(match_valor.group(0), '').strip()
                                            # Remove caracteres especiais do início/fim
                                            desc_clean = re.sub(r'^[-•\s]+|[-•\s]+$', '', desc_clean)
                                            # Remove informações redundantes
                                            desc_clean = re.sub(r'\s+-\s+NU\s+PAGAMENTOS.*$', '', desc_clean, flags=re.IGNORECASE)
                                            desc_clean = re.sub(r'\s+Agência:.*$', '', desc_clean)
                                            desc_clean = re.sub(r'\s+Conta:.*$', '', desc_clean)
                                            if len(desc_clean) > 5:
                                                lancamento = Lancamento(
                                                    data=data_mov,
                                                    descricao=_normalizar_descricao(desc_clean),
                            documento=None,
                            valor=valor,
                            saldo=None,
                            conta_contabil=None,
                            origem="mpds"
                        )
                        lancamentos.append(lancamento)
    
    except Exception as e:
        logger.error(f"Erro ao processar PDF Nubank: {e}")
        issues.append(f"Erro crítico: {str(e)}")
    
    return lancamentos, issues


# Regex para detectar período no PDF
RE_PERIODO = re.compile(r"PER[IÍ]ODO\s*:\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
RE_DATA_INICIO = re.compile(r"^(?P<dd>\d{2})/(?P<mm>\d{2})(?:/(?P<yyyy>\d{2,4}))?\b")
RE_VALOR = re.compile(r"(?P<val>\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
RE_MONEY_ONLY = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")
RE_START = RE_DATA_INICIO  # Alias para compatibilidade
RE_VAL_END = RE_VALOR  # Alias para compatibilidade


def _infer_year_from_period(texto: str) -> Optional[int]:
    """Infere o ano do período extraído do texto do PDF"""
    m = RE_PERIODO.search(texto or "")
    if not m:
        return None
    try:
        ini = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        fim = datetime.strptime(m.group(2), "%d/%m/%Y").date()
        # geralmente o extrato é do mesmo ano; se atravessar ano, você pode ajustar conforme o mês
        return fim.year
    except Exception:
        return None


def _is_dc_line(s: str) -> bool:
    """Verifica se a linha é apenas D ou C (débito/crédito)"""
    s = (s or "").strip().upper()
    return s in {"D", "C"}


def _is_dc(s: str) -> bool:
    """Alias para _is_dc_line (compatibilidade)"""
    return _is_dc_line(s)


def _clean_line(s: str) -> str:
    """Limpa e retorna linha"""
    return (s or "").strip()


def _parse_sicoob_text_fallback(linhas: List[str], year_hint: Optional[int], num_pag: int, issues: List[str]) -> List[Lancamento]:
    """
    Fallback robusto para parser Sicoob via texto.
    Cobre 3 padrões:
    - Padrão A: data+desc+valor na mesma linha
    - Padrão B: valor só aparece na linha seguinte
    - Padrão C: várias descrições antes do valor (multi-linha real)
    """
    out: List[Lancamento] = []
    i = 0

    def next_nonempty(idx: int) -> int:
        while idx < len(linhas) and not linhas[idx].strip():
            idx += 1
        return idx

    while i < len(linhas):
        i = next_nonempty(i)
        if i >= len(linhas):
            break

        ln0 = _clean_line(linhas[i])
        m0 = RE_START.match(ln0)
        if not m0:
            i += 1
            continue

        dd = int(m0.group("dd"))
        mm = int(m0.group("mm"))
        yyyy_raw = m0.group("yyyy")
        if yyyy_raw:
            yyyy = int(yyyy_raw)
            if yyyy < 100:
                yyyy += 2000
        else:
            yyyy = year_hint

        if not yyyy:
            issues.append(f"Página {num_pag}: sem ano para {dd:02d}/{mm:02d}")
            i += 1
            continue

        dt = date(yyyy, mm, dd)

        # Parte 1: montar bloco "pré-valor"
        pre_lines = [ln0]
        j = i + 1
        valor_str = None

        # Varre até achar valor (pode estar na própria linha, no fim; ou numa linha isolada)
        # Critério: primeiro valor monetário plausível após o start.
        while j < len(linhas):
            cur = _clean_line(linhas[j])

            # começou outro lançamento => aborta (registro sem valor)
            if RE_START.match(cur):
                break

            # ignora linhas de saldo/resumo
            if "SALDO" in cur.upper() or "RESUMO" in cur.upper():
                j += 1
                continue

            # se cur for D/C, ainda não achou valor => quebra (registro malformado)
            if _is_dc(cur) and valor_str is None:
                break

            # valor isolado em linha própria
            if RE_MONEY_ONLY.match(cur):
                valor_str = cur
                j += 1
                break

            # valor no final da linha
            mval = RE_VAL_END.search(cur)
            if mval:
                valor_str = mval.group("val")
                pre_lines.append(cur)
                j += 1
                break

            # segue acumulando descrição
            pre_lines.append(cur)
            j += 1

        if not valor_str:
            # não conseguiu formar lançamento
            issues.append(f"Página {num_pag}: lançamento sem valor a partir de '{ln0[:40]}'")
            i += 1
            continue

        # Parte 2: ler D/C
        j = next_nonempty(j)
        dc = _clean_line(linhas[j]).upper() if j < len(linhas) else ""
        if dc not in {"D", "C"}:
            # se não achou, assume débito (Sicoob costuma marcar), mas registra issue
            issues.append(f"Página {num_pag}: sem D/C após {dt} valor {valor_str}, encontrado '{dc}'")
            dc = "D"
        else:
            j += 1

        # Parte 3: coletar complementos até próximo lançamento
        comp = []
        k = j
        while k < len(linhas):
            cur = _clean_line(linhas[k])
            if RE_START.match(cur):
                break
            if not cur:
                k += 1
                continue
            if "SALDO" in cur.upper() or "RESUMO" in cur.upper():
                k += 1
                continue
            if _is_dc(cur):
                k += 1
                continue
            if RE_MONEY_ONLY.match(cur):
                k += 1
                continue
            comp.append(cur)
            k += 1

        # Monta descrição final
        full = " ".join(pre_lines + comp)

        # remove o prefixo DD/MM(/YYYY) do início
        full = RE_START.sub("", full, count=1).strip()

        # remove valor do final, se tiver ficado
        full = re.sub(r"\s+\d{1,3}(?:\.\d{3})*,\d{2}\s*$", "", full).strip()

        desc = _normalizar_descricao(full) if full else "Sem descrição"

        valor = _parse_valor(valor_str)
        valor = -abs(valor) if dc == "D" else abs(valor)

        out.append(Lancamento(
            data=dt,
            descricao=desc,
            documento=None,
            valor=valor,
            saldo=None,
            conta_contabil=None,
            origem="mpds"
        ))

        i = k

    return out


def _parse_sicoob(pdf_path: Path) -> Tuple[List[Lancamento], List[str]]:
    """
    Parser robusto para extratos Sicoob com state machine.
    
    Estratégia:
    - Parsing 100% por texto (linha a linha) com state machine
    - Não depende de extract_tables() (frequentemente falha)
    - Detecta início de lançamento por regex: ^\s*\d{2}/\d{2}\b
    - Usa lookahead para valores isolados que pertencem ao próximo lançamento
    - Cobre 4 padrões: valor na mesma linha, valor isolado, valor antes da data, descrição longa
    
    Padrões suportados:
    A) 06/03 PIX EMIT.OUTRA IF 4.447,84 + D + complementos
    B) 12/03 PIX EMIT.OUTRA IF + 5.726,78 (linha seguinte) + D + complementos
    C) 10/03 DB.TR.C.DIF.TIT.INT + 3.649,87 (linha seguinte) + D + complementos longos
    D) 5.383,91 (linha isolada) + 10/03 PIX EMIT.OUTRA IF ... (valor antes da data)
    """
    lancamentos: List[Lancamento] = []
    issues: List[str] = []
    
    # Regex para detectar início de lançamento (DD/MM - mais flexível)
    # Usa grupos nomeados para acesso seguro
    RE_DDMM = re.compile(r"^\s*(?P<dd>\d{2})/(?P<mm>\d{2})\b")
    
    # Regex para detectar valor monetário no final da linha
    RE_VALOR_FIM = re.compile(r"(?P<val>\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
    
    # Regex para linha que é apenas valor monetário
    RE_VALOR_ISOLADO = re.compile(r"^\s*\d{1,3}(?:\.\d{3})*,\d{2}\s*$")
    
    # Stopwords que indicam cabeçalho/resumo (não são lançamentos)
    STOPWORDS = (
        "SALDO ANTERIOR", "SALDO DO DIA", "SALDO EM C.CORRENTE",
        "EXTRATO CONTA", "COOP.:", "CONTA:", "PERÍODO:", "PERIODO:",
        "HISTÓRICO DE MOVIMENTAÇÃO", "DATA HISTÓRICO", "SALDO",
        "RESUMO", "TOTAL", "PÁGINA", "COOPERATIVA", "AGÊNCIA"
    )
    
    # Palavras que indicam que a próxima linha com valor é saldo
    SALDO_INDICATORS = ("SALDO DO DIA", "SALDO ANTERIOR", "SALDO EM C.CORRENTE", "SALDO")
    
    def is_candidate_start(line: str) -> bool:
        """
        Verifica se a linha é candidata a início de lançamento.
        Não depende de keywords - apenas verifica DD/MM e exclui stopwords.
        """
        s = (line or "").strip()
        if not s:
            return False
        # Deve começar com DD/MM
        if not RE_DDMM.match(s):
            return False
        # Não deve conter stopwords
        up = s.upper()
        if any(w in up for w in STOPWORDS):
            return False
        return True
    
    def is_strong_start(line: str) -> bool:
        """
        Verifica se a linha é um início forte (usado para parar buffer).
        Precisa ter DD/MM e letras após a data (histórico).
        """
        if not is_candidate_start(line):
            return False
        # Precisa ter alguma letra após a data (histórico)
        after = RE_DDMM.sub("", line, count=1).strip()
        return any(ch.isalpha() for ch in after)
    
    def _is_dc_linha(linha: str) -> bool:
        """Verifica se a linha é apenas D ou C (débito/crédito)"""
        linha_clean = linha.strip().upper()
        return linha_clean in {"D", "C"}
    
    def is_saldo_context(linha_anterior: str, linha_atual: str) -> bool:
        """
        Verifica se um valor isolado é provavelmente saldo.
        Retorna True se a linha anterior contém indicadores de saldo.
        """
        if not linha_anterior:
            return False
        linha_ant_upper = linha_anterior.upper()
        return any(indicator in linha_ant_upper for indicator in SALDO_INDICATORS)
    
    # State machine: estrutura para lançamento atual
    class LancamentoState:
        def __init__(self):
            self.data: Optional[date] = None
            self.desc_lines: List[str] = []
            self.valor_str: Optional[str] = None
            self.dc: Optional[str] = None
            self.linha_inicio: Optional[str] = None
        
        def is_complete(self) -> bool:
            """Verifica se o lançamento está completo (tem data, valor e dc)"""
            return self.data is not None and self.valor_str is not None and self.dc is not None
        
        def finalize(self) -> Optional[Lancamento]:
            """Finaliza e retorna Lancamento, ou None se inválido"""
            if not self.data or not self.valor_str:
                return None
            
            # Se não tem DC, assume D (padrão Sicoob)
            dc = self.dc if self.dc else "D"
            
            # Parse do valor
            valor = _parse_valor(self.valor_str)
            if valor == 0.0:
                return None
            
            # Aplica sinal
            if dc == "D":
                valor = -abs(valor)
            else:  # C
                valor = abs(valor)
            
            # Monta descrição
            descricao_raw = " ".join(self.desc_lines)
            # Remove data do início (DD/MM)
            descricao_raw = RE_DDMM.sub("", descricao_raw, count=1).strip()
            # Remove valor do final (se ainda estiver lá)
            descricao_raw = re.sub(r"\s+\d{1,3}(?:\.\d{3})*,\d{2}\s*$", "", descricao_raw).strip()
            # Remove espaços múltiplos
            descricao_raw = re.sub(r"\s+", " ", descricao_raw).strip()
            
            # Normaliza descrição
            if descricao_raw:
                descricao = _normalizar_descricao(descricao_raw)
            else:
                descricao = "Sem descrição"
            
            return Lancamento(
                data=self.data,
                descricao=descricao,
                documento=None,
                valor=valor,
                saldo=None,
                conta_contabil=None,
                origem="mpds"
            )
        
        def reset(self):
            """Reseta o estado para próximo lançamento"""
            self.data = None
            self.desc_lines = []
            self.valor_str = None
            self.dc = None
            self.linha_inicio = None
    
    lancamentos_por_pagina = {}  # Para debug: conta lançamentos por página
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extrai texto de todas as páginas
            texto_completo = ""
            for num_pag, page in enumerate(pdf.pages, 1):
                texto_pagina = page.extract_text() or ""
                if texto_pagina.strip():
                    texto_completo += texto_pagina + "\n"
                lancamentos_por_pagina[num_pag] = 0  # Inicializa contador
            
            if not texto_completo.strip():
                issues.append("PDF vazio ou sem texto extraível")
                logger.warning("SICOOB DEBUG: PDF vazio ou sem texto extraível")
                return lancamentos, issues
            
            # DEBUG: Loga primeiras 120 linhas
            linhas_debug = texto_completo.splitlines()
            logger.info("SICOOB DEBUG: primeiras 120 linhas:")
            for i, l in enumerate(linhas_debug[:120], 1):
                logger.info(f"  {i:03d}: {l}")
            
            # DEBUG: Conta linhas com DD/MM
            re_ddmm_debug = re.compile(r"^\s*\d{2}/\d{2}\b")
            cands = [l for l in linhas_debug if re_ddmm_debug.match(l)]
            logger.info(f"SICOOB DEBUG: linhas com DD/MM encontradas: {len(cands)}")
            if cands:
                logger.info("SICOOB DEBUG: primeiras 20 DD/MM:")
                for i, l in enumerate(cands[:20], 1):
                    logger.info(f"  {i:02d}: {l}")
            
            # Infere ano do período
            year_hint = _infer_year_from_period(texto_completo)
            if not year_hint:
                # Tenta inferir do ano atual se não encontrar período
                year_hint = datetime.now().year
                issues.append("Não foi possível inferir ano do período, usando ano atual")
            
            # DEBUG: Loga ano inferido e exemplo de match
            logger.info(f"SICOOB DEBUG: ano_inferido={year_hint}")
            if cands:
                exemplo_linha = cands[0]
                match_exemplo = RE_DDMM.match(exemplo_linha)
                if match_exemplo:
                    dd_ex = match_exemplo.group("dd")
                    mm_ex = match_exemplo.group("mm")
                    logger.info(f"SICOOB DEBUG: exemplo data_str={dd_ex}/{mm_ex}/{year_hint}")
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"SICOOB DEBUG: regex usado: {RE_DDMM.pattern}, linha casada: '{exemplo_linha[:50]}'")
            
            # Divide em linhas (mantém todas, inclusive vazias, para preservar índices)
            linhas = texto_completo.splitlines()
            
            # State machine: estado atual e valores pendentes
            current = LancamentoState()
            pending_value: Optional[str] = None
            pending_dc: Optional[str] = None
            
            # Processa linha a linha
            i = 0
            while i < len(linhas):
                linha = linhas[i].strip()
                linha_anterior = linhas[i - 1].strip() if i > 0 else ""
                
                # Ignora linhas vazias
                if not linha:
                    i += 1
                    continue
                
                # Verifica se é stopword (cabeçalho/resumo) - ignora completamente
                linha_upper = linha.upper()
                if any(w in linha_upper for w in STOPWORDS):
                    i += 1
                    continue
                    
                # 1) Detecta início de lançamento (DD/MM)
                if is_candidate_start(linha):
                    # Finaliza lançamento anterior se existir
                    if current.data is not None:
                        lanc_finalizado = current.finalize()
                        if lanc_finalizado:
                            lancamentos.append(lanc_finalizado)
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    f"SICOOB DEBUG: Lançamento finalizado: "
                                    f"{lanc_finalizado.data.strftime('%d/%m/%Y')} | "
                                    f"R$ {lanc_finalizado.valor:,.2f}"
                                )
                    
                    # Inicia novo lançamento
                    current.reset()
                    current.linha_inicio = linha
                    
                    # Extrai data com proteção robusta
                    match_data = RE_DDMM.match(linha)
                    if match_data:
                        try:
                            dd = int(match_data.group("dd"))
                            mm = int(match_data.group("mm"))
                            yyyy = year_hint
                            
                            # Valida data
                            try:
                                current.data = date(yyyy, mm, dd)
                            except ValueError:
                                issues.append(f"Data inválida: {dd:02d}/{mm:02d}/{yyyy}")
                                i += 1
                                continue
                            
                            # Aplica pending_value se existir (Padrão D: valor antes da data)
                            if pending_value and not current.valor_str:
                                current.valor_str = pending_value
                                if logger.isEnabledFor(logging.DEBUG):
                                    logger.debug(
                                        f"SICOOB DEBUG: Aplicado pending_value={pending_value} "
                                        f"ao lançamento {current.data.strftime('%d/%m/%Y')} (linha {i+1})"
                                    )
                                pending_value = None
                            
                            # Aplica pending_dc se existir
                            if pending_dc and not current.dc:
                                current.dc = pending_dc
                                pending_dc = None
                            
                            # Verifica se tem valor na mesma linha (Padrão A)
                            match_valor = RE_VALOR_FIM.search(linha)
                            if match_valor and not current.valor_str:
                                current.valor_str = match_valor.group("val")
                            
                            # Adiciona linha à descrição (sem o valor, se presente)
                            current.desc_lines.append(linha)
                            
                        except (IndexError, ValueError) as e:
                            issues.append(f"Erro ao extrair data da linha: {linha[:50]}")
                            i += 1
                            continue
                    else:
                        i += 1
                        continue
                
                # 2) Se já temos um lançamento iniciado, processa linhas seguintes
                elif current.data is not None:
                    # Se encontrou próxima data forte, finaliza e processa na próxima iteração
                    if is_strong_start(linha):
                        # Finaliza lançamento atual
                        lanc_finalizado = current.finalize()
                        if lanc_finalizado:
                            lancamentos.append(lanc_finalizado)
                        current.reset()
                        # Não incrementa i - processa esta linha na próxima iteração
                        continue
                    
                    # Verifica se é D/C isolado
                    if _is_dc_linha(linha):
                        if not current.dc:
                            current.dc = linha.upper()
                        i += 1
                        continue
                    
                    # Verifica se é valor isolado (Padrão B/C/D)
                    if RE_VALOR_ISOLADO.match(linha):
                        # Verifica se é saldo (contexto de saldo)
                        if is_saldo_context(linha_anterior, linha):
                            i += 1
                            continue
                        
                        # Se ainda não tem valor, atribui ao lançamento atual (Padrão B/C)
                        if not current.valor_str:
                            current.valor_str = linha.strip()
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    f"SICOOB DEBUG: Valor isolado atribuído: {linha.strip()} "
                                    f"ao lançamento {current.data.strftime('%d/%m/%Y')} (linha {i+1})"
                                )
                        else:
                            # Já tem valor - pode ser do próximo lançamento (Padrão D)
                            # Verifica se próxima linha é início de lançamento
                            if i + 1 < len(linhas):
                                linha_prox = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
                                if is_candidate_start(linha_prox):
                                    pending_value = linha.strip()
                                    if logger.isEnabledFor(logging.DEBUG):
                                        logger.debug(
                                            f"SICOOB DEBUG: Valor isolado armazenado como pending: "
                                            f"{linha.strip()} (linha {i+1}, próximo lançamento em linha {i+2})"
                                        )
                                # Se não é próximo lançamento, ignora (provavelmente saldo ou ruído)
                        i += 1
                        continue
                    
                    # Verifica se tem valor no final da linha (Padrão A ou complemento)
                    match_valor = RE_VALOR_FIM.search(linha)
                    if match_valor:
                        if not current.valor_str:
                            current.valor_str = match_valor.group("val")
                        # Adiciona linha ao buffer (valor será removido depois)
                        current.desc_lines.append(linha)
                        i += 1
                        continue
                    
                    # Adiciona linha à descrição (complemento)
                    current.desc_lines.append(linha)
                    i += 1
                    continue
                
                # 3) Valor isolado sem lançamento ativo (Padrão D: valor antes da data)
                elif RE_VALOR_ISOLADO.match(linha):
                    # Verifica se é saldo
                    if is_saldo_context(linha_anterior, linha):
                        i += 1
                        continue
                    
                    # Verifica se próxima linha é início de lançamento
                    if i + 1 < len(linhas):
                        linha_prox = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
                        if is_candidate_start(linha_prox):
                            pending_value = linha.strip()
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    f"SICOOB DEBUG: Valor isolado armazenado como pending: "
                                    f"{linha.strip()} (linha {i+1}, próximo lançamento)"
                                )
                        else:
                            # Não é próximo lançamento, provavelmente é saldo - ignora
                            pass
                    i += 1
                    continue
                
                # 4) D/C isolado sem lançamento ativo
                elif _is_dc_linha(linha):
                    # Se há pending_value, armazena pending_dc
                    if pending_value:
                        pending_dc = linha.upper()
                    i += 1
                    continue
                
                # 5) Outras linhas - ignora
                else:
                    i += 1
                    continue
            
            # Finaliza último lançamento se existir
            if current.data is not None:
                lanc_finalizado = current.finalize()
                if lanc_finalizado:
                    lancamentos.append(lanc_finalizado)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            f"SICOOB DEBUG: Último lançamento finalizado: "
                            f"{lanc_finalizado.data.strftime('%d/%m/%Y')} | "
                            f"R$ {lanc_finalizado.valor:,.2f}"
                        )
    
    except Exception as e:
        logger.error(f"Erro ao processar PDF Sicoob: {e}", exc_info=True)
        issues.append(f"Erro crítico: {str(e)}")
    
    # Debug: loga os primeiros 10 lançamentos extraídos e estatísticas por página
    if lancamentos:
        logger.info(f"✅ Sicoob: {len(lancamentos)} lançamentos extraídos")
        if logger.isEnabledFor(logging.DEBUG):
            for idx, lanc in enumerate(lancamentos[:10], 1):
                logger.debug(
                    f"  [{idx}] {lanc.data.strftime('%d/%m/%Y')} | "
                    f"R$ {lanc.valor:,.2f} | {lanc.descricao[:70]}"
                )
            # Loga lançamentos por página (se disponível)
            if lancamentos_por_pagina:
                for pag, count in lancamentos_por_pagina.items():
                    if count > 0:
                        logger.debug(f"SICOOB DEBUG: Página {pag}: {count} lançamentos extraídos")
    else:
        logger.warning("⚠️ Sicoob: Nenhum lançamento extraído")
    
    return lancamentos, issues


def parse_mpds_pdf(
    file_path: str | Path,
    strict: bool = False
) -> Tuple[List[Lancamento], List[str]]:
    """
    Parse extrato bancário em PDF (Nubank/Sicoob).
    
    Args:
        file_path: Caminho para o arquivo PDF
        strict: Se True, levanta exceção em caso de erro crítico
        
    Returns:
        Tupla (lista de Lancamento, lista de issues)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    
    if not path.suffix.lower() == '.pdf':
        raise ValueError(f"Arquivo deve ser PDF: {path}")
    
    logger.info(f"Iniciando parsing do PDF MPDS: {path}")
    
    lancamentos = []
    issues = []
    
    try:
        # Detecta banco pela primeira página
        with pdfplumber.open(path) as pdf:
            primeira_pagina = pdf.pages[0]
            texto_primeira = primeira_pagina.extract_text() or ""
            banco = _detectar_banco(texto_primeira)
        
        logger.info(f"Banco detectado: {banco}")
        
        # Chama parser específico
        if banco == 'nubank':
            lancamentos, issues = _parse_nubank(path)
        elif banco == 'sicoob':
            lancamentos, issues = _parse_sicoob(path)
        else:
            # Tenta ambos
            logger.warning(f"Banco não detectado ({banco}), tentando parser genérico...")
            lancamentos_nubank, issues_nubank = _parse_nubank(path)
            lancamentos_sicoob, issues_sicoob = _parse_sicoob(path)
            
            # Usa o que retornou mais lançamentos
            if len(lancamentos_nubank) >= len(lancamentos_sicoob):
                lancamentos = lancamentos_nubank
                issues = issues_nubank
            else:
                lancamentos = lancamentos_sicoob
                issues = issues_sicoob
        
        logger.info(f"Parsing concluído. Total de lançamentos extraídos: {len(lancamentos)}")
        if issues:
            logger.warning(f"Total de issues encontradas: {len(issues)}")
        
        if strict and issues:
            raise ValueError(f"Erros encontrados durante parsing: {issues[:5]}")
        
    except Exception as e:
        logger.error(f"Erro ao processar PDF: {e}")
        if strict:
            raise
        issues.append(f"Erro crítico: {str(e)}")
    
    return lancamentos, issues


