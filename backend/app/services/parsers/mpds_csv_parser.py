"""
Parser para arquivos MPDS em formato CSV (extrato estruturado)
"""

import csv
import logging
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from datetime import datetime, date
import io

from app.core.models import Lancamento

logger = logging.getLogger(__name__)


def _detect_delimiter(first_line: str) -> str:
    """
    Detecta o delimitador do CSV (vírgula ou ponto e vírgula).
    """
    if ';' in first_line and first_line.count(';') > first_line.count(','):
        return ';'
    return ','


def _normalize_column_name(col: str) -> str:
    """
    Normaliza nome de coluna para comparação (remove acentos, espaços, etc).
    """
    if not col:
        return ""
    col = col.strip().upper()
    # Remove acentos básicos
    col = col.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
    col = col.replace('Ã', 'A').replace('Õ', 'O').replace('Ç', 'C')
    return col


def _find_column_index(headers: List[str], possible_names: List[str]) -> Optional[int]:
    """
    Encontra o índice de uma coluna pelo nome (com variações).
    """
    for idx, header in enumerate(headers):
        header_norm = _normalize_column_name(header)
        for name in possible_names:
            if _normalize_column_name(name) in header_norm or header_norm in _normalize_column_name(name):
                return idx
    return None


def _parse_valor(valor_str: str) -> float:
    """
    Converte string brasileira (ex: '1.234,56' ou '-1.234,56') para float.
    Também aceita formato americano (1,234.56).
    """
    if not valor_str or valor_str.strip() == '':
        return 0.0
    
    valor_str = str(valor_str).strip()
    
    # Detecta sinal negativo
    negativo = False
    if valor_str.startswith('-'):
        negativo = True
        valor_str = valor_str[1:].strip()
    
    # Detecta formato (brasileiro vs americano)
    # Brasileiro: 1.234,56 (ponto milhares, vírgula decimal)
    # Americano: 1,234.56 (vírgula milhares, ponto decimal)
    
    # Se tem vírgula e ponto, decide pelo padrão
    if ',' in valor_str and '.' in valor_str:
        # Se vírgula vem depois do ponto, é formato brasileiro
        if valor_str.rindex(',') > valor_str.rindex('.'):
            # Brasileiro: 1.234,56
            valor_str = valor_str.replace('.', '').replace(',', '.')
        else:
            # Americano: 1,234.56
            valor_str = valor_str.replace(',', '')
    elif ',' in valor_str:
        # Pode ser brasileiro (vírgula decimal) ou americano (vírgula milhares)
        # Se tem mais de 3 dígitos após vírgula, provavelmente é milhares
        partes = valor_str.split(',')
        if len(partes) == 2 and len(partes[1]) <= 2:
            # Brasileiro: vírgula decimal
            valor_str = valor_str.replace('.', '').replace(',', '.')
        else:
            # Americano: vírgula milhares
            valor_str = valor_str.replace(',', '')
    elif '.' in valor_str:
        # Pode ser decimal ou milhares
        # Se tem mais de 3 dígitos após ponto, provavelmente não é decimal
        partes = valor_str.split('.')
        if len(partes) == 2 and len(partes[1]) <= 2:
            # Decimal
            pass  # Já está no formato correto
        else:
            # Milhares
            valor_str = valor_str.replace('.', '')
    
    try:
        valor = float(valor_str)
        return -valor if negativo else valor
    except ValueError:
        logger.warning(f"Não foi possível converter valor: {valor_str}")
        return 0.0


def _parse_data(data_str: str) -> Optional[date]:
    """
    Converte string de data para date.
    Aceita formatos: DD/MM/YYYY, DD/MM/YY, YYYY-MM-DD
    """
    if not data_str or str(data_str).strip() == '':
        return None
    
    data_str = str(data_str).strip()
    
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
    
    logger.warning(f"Não foi possível converter data: {data_str}")
    return None


def parse_mpds_csv(
    file_path: str | Path,
    strict: bool = False
) -> Tuple[List[Lancamento], List[str]]:
    """
    Lê um arquivo CSV MPDS e retorna uma lista de Lancamento.
    
    Args:
        file_path: Caminho para o arquivo CSV
        strict: Se True, falha ao encontrar linhas não parseáveis. Se False, registra issues.
        
    Returns:
        Tupla (lista de Lancamento, lista de issues/erros)
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    
    lancamentos = []
    issues = []
    
    logger.info(f"Iniciando parsing do CSV MPDS: {path}")
    
    try:
        # Lê primeira linha para detectar delimitador
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            delimiter = _detect_delimiter(first_line)
            f.seek(0)
            
            # Lê CSV
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader, None)
            
            if not headers:
                raise ValueError("Arquivo CSV vazio ou sem cabeçalho")
            
            logger.debug(f"Cabeçalhos detectados: {headers}")
            logger.debug(f"Delimitador detectado: {delimiter}")
            
            # Encontra índices das colunas
            col_data_idx = _find_column_index(headers, [
                'Data', 'DATA', 'Dt', 'DT', 'Data Lançamento', 'Data Movimento',
                'Date', 'DATE', 'Data Operação'
            ])
            
            col_descricao_idx = _find_column_index(headers, [
                'Descrição', 'DESCRIÇÃO', 'Histórico', 'HISTÓRICO', 'Hist', 'HIST',
                'Description', 'Memo', 'MEMO', 'Nome', 'NOME', 'Descrição Operação'
            ])
            
            col_valor_idx = _find_column_index(headers, [
                'Valor', 'VALOR', 'Val', 'VAL', 'Amount', 'AMOUNT', 'Valor Movimento'
            ])
            
            col_debito_idx = _find_column_index(headers, [
                'Débito', 'DÉBITO', 'Deb', 'DEB', 'Debit', 'DEBIT', 'Débito Movimento'
            ])
            
            col_credito_idx = _find_column_index(headers, [
                'Crédito', 'CRÉDITO', 'Cred', 'CRED', 'Credit', 'CREDIT', 'Crédito Movimento'
            ])
            
            col_documento_idx = _find_column_index(headers, [
                'Documento', 'DOCUMENTO', 'Doc', 'DOC', 'Nº Doc', 'Num Doc', 'Número Documento'
            ])
            
            col_saldo_idx = _find_column_index(headers, [
                'Saldo', 'SALDO', 'Sld', 'SLD', 'Balance', 'BALANCE'
            ])
            
            # Valida colunas obrigatórias
            if col_data_idx is None:
                raise ValueError("Coluna de data não encontrada no CSV")
            
            if col_descricao_idx is None:
                raise ValueError("Coluna de descrição/histórico não encontrada no CSV")
            
            if col_valor_idx is None and col_debito_idx is None and col_credito_idx is None:
                raise ValueError("Nenhuma coluna de valor encontrada no CSV (Valor, Débito ou Crédito)")
            
            # Processa linhas
            for num_linha, row in enumerate(reader, start=2):  # Começa em 2 (linha 1 é cabeçalho)
                if not row or len(row) == 0:
                    continue
                
                # Pula linhas vazias ou que parecem rodapé
                if all(not cell or cell.strip() == '' for cell in row):
                    continue
                
                try:
                    # Data
                    if col_data_idx >= len(row) or not row[col_data_idx]:
                        issues.append(f"Linha {num_linha}: Data não encontrada")
                        if strict:
                            raise ValueError(f"Linha {num_linha}: Data não encontrada")
                        continue
                    
                    data = _parse_data(row[col_data_idx])
                    if not data:
                        issues.append(f"Linha {num_linha}: Data inválida: {row[col_data_idx]}")
                        if strict:
                            raise ValueError(f"Linha {num_linha}: Data inválida")
                        continue
                    
                    # Descrição
                    if col_descricao_idx >= len(row) or not row[col_descricao_idx]:
                        issues.append(f"Linha {num_linha}: Descrição não encontrada")
                        if strict:
                            raise ValueError(f"Linha {num_linha}: Descrição não encontrada")
                        continue
                    
                    descricao = str(row[col_descricao_idx]).strip()
                    if not descricao:
                        continue
                    
                    # Valor
                    valor = 0.0
                    
                    # Tenta coluna única de valor
                    if col_valor_idx is not None and col_valor_idx < len(row):
                        valor = _parse_valor(row[col_valor_idx])
                    
                    # Se não encontrou, tenta débito/crédito
                    if valor == 0.0:
                        debito = 0.0
                        credito = 0.0
                        
                        if col_debito_idx is not None and col_debito_idx < len(row):
                            debito = _parse_valor(row[col_debito_idx])
                        
                        if col_credito_idx is not None and col_credito_idx < len(row):
                            credito = _parse_valor(row[col_credito_idx])
                        
                        if debito != 0:
                            valor = -abs(debito)  # Débito é negativo
                        elif credito != 0:
                            valor = abs(credito)  # Crédito é positivo
                    
                    if valor == 0.0:
                        continue  # Pula lançamentos com valor zero
                    
                    # Documento (opcional)
                    documento = None
                    if col_documento_idx is not None and col_documento_idx < len(row):
                        doc_str = str(row[col_documento_idx]).strip()
                        if doc_str:
                            documento = doc_str
                    
                    # Saldo (opcional)
                    saldo = None
                    if col_saldo_idx is not None and col_saldo_idx < len(row):
                        saldo_str = row[col_saldo_idx]
                        if saldo_str:
                            saldo = _parse_valor(saldo_str)
                    
                    lancamento = Lancamento(
                        data=data,
                        descricao=descricao,
                        documento=documento,
                        valor=valor,
                        saldo=saldo,
                        conta_contabil=None,
                        origem="mpds"
                    )
                    
                    lancamentos.append(lancamento)
                    
                except Exception as e:
                    issues.append(f"Linha {num_linha}: Erro ao processar: {e}")
                    if strict:
                        raise
                    continue
        
        logger.info(f"Parsing concluído. Total de lançamentos extraídos: {len(lancamentos)}")
        if issues:
            logger.warning(f"Total de issues encontradas: {len(issues)}")
        
    except Exception as e:
        logger.error(f"Erro ao processar CSV: {e}")
        raise
    
    return lancamentos, issues


