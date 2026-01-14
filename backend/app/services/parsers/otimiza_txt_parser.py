"""
Parser para arquivos TXT do Otimiza (lançamentos contábeis/financeiros)
"""

import re
import logging
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

from app.core.models import Lancamento

logger = logging.getLogger(__name__)


def _parse_valor(valor_str: str) -> float:
    """
    Converte string brasileira (ex: '1.234,56' ou '-1.234,56') ou americana (ex: '1500.00') para float.
    """
    if not valor_str or valor_str.strip() == '':
        return 0.0
    
    valor_str = valor_str.strip()
    
    # Detecta sinal negativo
    negativo = False
    if valor_str.startswith('-'):
        negativo = True
        valor_str = valor_str[1:].strip()
    
    # Detecta formato (brasileiro vs americano)
    # Brasileiro: 1.234,56 (ponto milhares, vírgula decimal)
    # Americano: 1500.00 (ponto decimal, sem separador de milhares ou vírgula milhares)
    
    if ',' in valor_str and '.' in valor_str:
        # Tem ambos: decide pelo padrão
        # Se vírgula vem depois do ponto, é formato brasileiro
        if valor_str.rindex(',') > valor_str.rindex('.'):
            # Brasileiro: 1.234,56
            valor_str = valor_str.replace('.', '').replace(',', '.')
        else:
            # Americano: 1,234.56
            valor_str = valor_str.replace(',', '')
    elif ',' in valor_str:
        # Só vírgula: pode ser brasileiro (vírgula decimal) ou americano (vírgula milhares)
        # Se tem mais de 3 dígitos após vírgula, provavelmente é milhares
        partes = valor_str.split(',')
        if len(partes) == 2 and len(partes[1]) <= 2:
            # Brasileiro: vírgula decimal
            valor_str = valor_str.replace('.', '').replace(',', '.')
        else:
            # Americano: vírgula milhares
            valor_str = valor_str.replace(',', '')
    elif '.' in valor_str:
        # Só ponto: pode ser decimal ou milhares
        # Se tem mais de 3 dígitos após ponto, provavelmente não é decimal
        partes = valor_str.split('.')
        if len(partes) == 2 and len(partes[1]) <= 2:
            # Decimal (formato americano)
            pass  # Já está no formato correto
        else:
            # Pode ser formato brasileiro sem vírgula (improvável mas possível)
            # Ou formato americano com ponto decimal
            # Assumimos formato americano (ponto decimal)
            pass
    else:
        # Sem separadores: número inteiro
        pass
    
    try:
        valor = float(valor_str)
        return -valor if negativo else valor
    except ValueError:
        logger.warning(f"Não foi possível converter valor: {valor_str}")
        return 0.0


# Regex para validar formato de data antes de parsear
RE_DATA_STRICT = re.compile(r"^\d{2}/\d{2}/\d{4}$")
RE_DATA_YY = re.compile(r"^\d{2}/\d{2}/\d{2}$")
RE_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_data_safe(token: str) -> Optional[date]:
    """
    Valida que o token é uma data válida antes de parsear.
    Evita chamar _parse_data() em tokens que não são datas (ex: "0000", "6000", "X").
    """
    if not token or not token.strip():
        return None
    
    token = token.strip()
    
    # Valida formato antes de tentar parsear
    if RE_DATA_STRICT.match(token):
        try:
            return datetime.strptime(token, "%d/%m/%Y").date()
        except ValueError:
            return None
    elif RE_DATA_YY.match(token):
        try:
            return datetime.strptime(token, "%d/%m/%y").date()
        except ValueError:
            return None
    elif RE_DATA_ISO.match(token):
        try:
            return datetime.strptime(token, "%Y-%m-%d").date()
        except ValueError:
            return None
    
    # Não é um formato de data válido
    return None


def _parse_data(data_str: str) -> Optional[date]:
    """
    Converte string de data para date.
    Aceita formatos: DD/MM/YYYY, DD/MM/YY, YYYY-MM-DD
    
    DEPRECATED: Use _parse_data_safe() que valida formato antes de parsear.
    """
    if not data_str or data_str.strip() == '':
        return None
    
    data_str = data_str.strip()
    
    # Tenta primeiro com validação segura
    data = _parse_data_safe(data_str)
    if data:
        return data
    
    # Fallback para formatos antigos (compatibilidade)
    formatos = [
        '%d/%m/%Y',
        '%d/%m/%y',
        '%Y-%m-%d',
        '%d-%m-%Y',
        '%d-%m-%y',
    ]
    
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            continue
    
    # Não loga warning para evitar ruído - apenas retorna None
    return None


def parse_otimiza_txt(
    file_path: str | Path,
    strict: bool = False
) -> Tuple[List[Lancamento], List[str]]:
    """
    Lê um arquivo TXT do Otimiza e retorna uma lista de Lancamento.
    
    Args:
        file_path: Caminho para o arquivo TXT
        strict: Se True, falha ao encontrar linhas não parseáveis. Se False, registra issues.
        
    Returns:
        Tupla (lista de Lancamento, lista de issues/erros)
        
    TODO:
        - Ajustar regex conforme layout real do TXT do Otimiza
        - Implementar detecção automática de layout
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    
    if not path.suffix.lower() == '.txt':
        logger.warning(f"Arquivo não tem extensão .txt: {path}")
    
    lancamentos = []
    issues = []
    
    logger.info(f"Iniciando parsing do TXT Otimiza: {path}")
    
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
        
        logger.debug(f"Total de linhas no arquivo: {len(linhas)}")
        
        # Padrões regex para detectar lançamentos
        # Layout genérico esperado (ajustar conforme necessário):
        # DD/MM/YYYY | Descrição | Documento? | Valor | Tipo (D/C)?
        
        # Padrão 1: Data no início da linha (DD/MM/YYYY ou DD/MM/YY)
        padrao_data_inicio = re.compile(
            r'^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d.,-]+)\s*(D|C|DEBITO|CREDITO)?$',
            re.IGNORECASE
        )
        
        # Padrão 2: Data no meio (mais flexível)
        padrao_data_meio = re.compile(
            r'(.+?)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d.,-]+)',
            re.IGNORECASE
        )
        
        # Padrão 3: Separado por delimitadores (|, ;, tab) - formato completo
        # Formato esperado: Data | Descrição | Conta | Documento? | Valor | EventType? | Category? | EntityType?
        padrao_delimitado = re.compile(
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})[|;\t]+(.+?)[|;\t]+([^|;\t]+?)(?:[|;\t]+([^|;\t]+?))?(?:[|;\t]+([\d.,-]+))?(?:[|;\t]+([^|;\t]+?))?(?:[|;\t]+([^|;\t]+?))?(?:[|;\t]+([^|;\t]+?))?',
            re.IGNORECASE
        )
        
        for num_linha, linha in enumerate(linhas, 1):
            linha = linha.strip()
            
            # Pula linhas vazias
            if not linha:
                continue
            
            # Pula linhas que parecem cabeçalho
            if any(palavra in linha.upper() for palavra in [
                'DATA', 'DESCRIÇÃO', 'HISTÓRICO', 'DOCUMENTO', 'VALOR',
                'DÉBITO', 'CRÉDITO', 'SALDO', 'LANÇAMENTO', 'LANCAMENTO'
            ]):
                continue
            
            lancamento = None
            match = None  # Inicializa match
            
            # Tenta padrão 3 primeiro (delimitado) se detectar delimitadores
            if '|' in linha or ';' in linha or '\t' in linha:
                # Tenta parsing por delimitadores (|, ;, tab)
                # Formato esperado: Data|Descrição|Conta|Documento?|Valor|EventType?|Category?|EntityType?
                # OU: |Campo1|Data|... (quando linha começa com |)
                partes = re.split(r'[|;\t]+', linha)
                # Remove partes vazias do início (quando linha começa com delimitador)
                while partes and not partes[0].strip():
                    partes.pop(0)
                
                if len(partes) >= 3:
                    try:
                        # Tenta detectar formato: pode ser Data|Descrição|... ou Campo|Data|...
                        # Se primeira parte parece data (DD/MM/YYYY), usa como data
                        # Senão, tenta segunda parte como data
                        data_str = None
                        descricao = None
                        idx_inicio = 0
                        
                        # Verifica se primeira parte é data
                        if _parse_data(partes[0].strip()):
                            data_str = partes[0].strip()
                            descricao = partes[1].strip() if len(partes) > 1 else ""
                            idx_inicio = 2
                        # Se não, tenta segunda parte como data (formato: |Campo|Data|...)
                        elif len(partes) > 1 and _parse_data(partes[1].strip()):
                            data_str = partes[1].strip()
                            descricao = partes[0].strip() if len(partes) > 0 else ""
                            idx_inicio = 2
                        # Se ainda não, tenta terceira parte (formato: |Campo1|Campo2|Data|...)
                        elif len(partes) > 2 and _parse_data(partes[2].strip()):
                            data_str = partes[2].strip()
                            descricao = " ".join([p.strip() for p in partes[:2] if p.strip()])
                            idx_inicio = 3
                        else:
                            # Fallback: usa primeira parte como data (pode falhar)
                            data_str = partes[0].strip()
                            descricao = partes[1].strip() if len(partes) > 1 else ""
                            idx_inicio = 2
                        
                        # Formato esperado: Data|Descrição|Conta|Documento?|Valor|EventType?|Category?|EntityType?
                        # Tenta identificar campos por posição
                        account_code = None
                        documento = None
                        valor_str = None
                        event_type = None
                        category = None
                        entity_type = None
                        
                        # Procura valor e descrição nas partes restantes
                        # Formato típico: |6100|16/10/2025|266|543|2500,00||TRANSFERENCIA ENVIADA...
                        valor_idx = None
                        
                        # Procura valor (formato numérico com vírgula ou ponto decimal)
                        for i in range(idx_inicio, len(partes)):
                            parte_clean = partes[i].strip()
                            if not parte_clean:
                                continue
                            # Se parece com valor numérico (tem vírgula/ponto decimal)
                            if re.match(r'^[\d.,-]+$', parte_clean):
                                # Verifica se tem vírgula ou ponto (indicando decimal)
                                if ',' in parte_clean or ('.' in parte_clean and len(parte_clean.split('.')[-1]) <= 2):
                                    valor_str = parte_clean
                                    valor_idx = i
                                    break
                                
                        # Se encontrou valor, procura descrição após ele
                        if valor_str and valor_idx is not None:
                            # Procura descrição após o valor (pode estar em várias posições)
                            for i in range(valor_idx + 1, len(partes)):
                                parte_desc = partes[i].strip()
                                if parte_desc and len(parte_desc) > 10:  # Descrição geralmente é longa
                                    # Se não parece número, é provavelmente descrição
                                    if not re.match(r'^[\d.,-]+$', parte_desc):
                                        if not descricao or len(parte_desc) > len(descricao):
                                            descricao = parte_desc
                            
                            # Se não encontrou descrição após valor, tenta última parte não vazia
                            if not descricao or len(descricao) < 10:
                                for i in range(len(partes) - 1, valor_idx, -1):
                                    parte_desc = partes[i].strip()
                                    if parte_desc and len(parte_desc) > 10:
                                        if not re.match(r'^[\d.,-]+$', parte_desc):
                                            descricao = parte_desc
                                            break
                        
                        data = _parse_data_safe(data_str)
                        if not data:
                            # Não adiciona issue se não é formato de data válido (evita ruído)
                            continue
                        
                        if not valor_str:
                            issues.append(f"Linha {num_linha}: Valor não encontrado")
                            if strict:
                                raise ValueError(f"Linha {num_linha}: Valor não encontrado")
                            continue
                        
                        valor = _parse_valor(valor_str)
                        if valor == 0.0:
                            continue
                        
                        lancamento = Lancamento(
                            data=data,
                            descricao=descricao,
                            documento=documento,
                            valor=valor,
                            saldo=None,
                            conta_contabil=account_code,  # Mantém compatibilidade
                            origem="otimiza",
                            account_code=account_code,  # Novo campo
                            event_type=event_type,
                            category=category,
                            entity_type=entity_type
                        )
                    except Exception as e:
                        issues.append(f"Linha {num_linha}: Erro ao parsear formato delimitado: {e}")
                        if strict:
                            raise
                        continue
            
            # Tenta padrão 1: data no início (apenas se não parseou com delimitado)
            if not lancamento:
                match = padrao_data_inicio.match(linha)
                if match:
                    data_str = match.group(1)
                    descricao = match.group(2).strip()
                    valor_str = match.group(3)
                    tipo_str = match.group(4) if len(match.groups()) > 3 else None
                    
                    data = _parse_data_safe(data_str)
                    if not data:
                        # Não adiciona issue se não é formato de data válido (evita ruído)
                        continue
                    
                    valor = _parse_valor(valor_str)
                    if tipo_str and tipo_str.upper() in ['D', 'DEBITO']:
                        valor = -abs(valor)
                    elif tipo_str and tipo_str.upper() in ['C', 'CREDITO']:
                        valor = abs(valor)
                    
                    if valor == 0.0:
                        continue
                    
                    lancamento = Lancamento(
                        data=data,
                        descricao=descricao,
                        documento=None,  # Pode ser extraído se estiver no padrão
                        valor=valor,
                        saldo=None,
                        conta_contabil=None,  # Pode ser extraído se estiver no padrão
                        origem="otimiza"
                    )
            
            # Tenta padrão 2: data no meio
            if not lancamento:
                match = padrao_data_meio.match(linha)
                if match:
                    descricao = match.group(1).strip()
                    data_str = match.group(2)
                    descricao2 = match.group(3).strip()
                    valor_str = match.group(4)
                    
                    data = _parse_data_safe(data_str)
                    if not data:
                        # Não adiciona issue se não é formato de data válido (evita ruído)
                        continue
                    
                    descricao_completa = f"{descricao} {descricao2}".strip()
                    valor = _parse_valor(valor_str)
                    
                    if valor == 0.0:
                        continue
                    
                    lancamento = Lancamento(
                        data=data,
                        descricao=descricao_completa,
                        documento=None,
                        valor=valor,
                        saldo=None,
                        conta_contabil=None,
                        origem="otimiza"
                    )
            
            
            # Se não conseguiu parsear
            if not lancamento:
                issues.append(f"Linha {num_linha}: Não foi possível parsear: {linha[:100]}")
                if strict:
                    raise ValueError(f"Linha {num_linha}: Não foi possível parsear")
                continue
            
            lancamentos.append(lancamento)
        
        logger.info(f"Parsing concluído. Total de lançamentos extraídos: {len(lancamentos)}")
        if issues:
            logger.warning(f"Total de issues encontradas: {len(issues)}")
        
    except Exception as e:
        logger.error(f"Erro ao processar TXT: {e}")
        raise
    
    return lancamentos, issues

