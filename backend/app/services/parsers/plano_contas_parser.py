"""
Parser para Plano de Contas (CSV/XLSX)
"""

import csv
import logging
from typing import List, Dict, Optional
from pathlib import Path
import pandas as pd

from app.models.plano_contas import ChartOfAccounts

logger = logging.getLogger(__name__)


def _normalize_column_name(col: str) -> str:
    """Normaliza nome de coluna para comparação"""
    if not col:
        return ""
    col = str(col).strip().upper()
    # Remove acentos básicos
    col = col.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
    col = col.replace('Ã', 'A').replace('Õ', 'O').replace('Ç', 'C')
    return col


def _find_column_index(headers: List[str], possible_names: List[str]) -> Optional[int]:
    """Encontra o índice de uma coluna pelo nome"""
    for idx, header in enumerate(headers):
        header_norm = _normalize_column_name(header)
        for name in possible_names:
            if _normalize_column_name(name) in header_norm or header_norm in _normalize_column_name(name):
                return idx
    return None


def parse_plano_contas_csv(
    file_path: str | Path
) -> List[Dict]:
    """
    Lê um arquivo CSV do plano de contas.
    
    Returns:
        Lista de dicionários com os dados das contas
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    
    contas = []
    
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        # Detecta delimitador
        first_line = f.readline()
        delimiter = ';' if ';' in first_line and first_line.count(';') > first_line.count(',') else ','
        f.seek(0)
        
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader, None)
        
        if not headers:
            raise ValueError("Arquivo CSV vazio ou sem cabeçalho")
        
        # Encontra colunas
        col_codigo = _find_column_index(headers, [
            'codigo', 'conta', 'account_code', 'cod', 'code'
        ])
        
        col_nome = _find_column_index(headers, [
            'descricao', 'nome', 'account_name', 'name', 'desc'
        ])
        
        col_nivel = _find_column_index(headers, [
            'nivel', 'level', 'niv'
        ])
        
        col_pai = _find_column_index(headers, [
            'pai', 'parent', 'parent_code', 'conta_pai'
        ])
        
        col_tipo = _find_column_index(headers, [
            'tipo', 'account_type', 'type', 'natureza'
        ])
        
        col_natureza = _find_column_index(headers, [
            'nature', 'natureza', 'natureza_conta'
        ])
        
        if col_codigo is None or col_nome is None:
            raise ValueError(f"Colunas obrigatórias não encontradas. Colunas disponíveis: {headers}")
        
        # Processa linhas
        for row in reader:
            if not row or len(row) == 0:
                continue
            
            if col_codigo >= len(row) or not row[col_codigo]:
                continue
            
            account_code = str(row[col_codigo]).strip()
            if not account_code:
                continue
            
            account_name = str(row[col_nome]).strip() if col_nome < len(row) else ""
            
            account_level = None
            if col_nivel is not None and col_nivel < len(row) and row[col_nivel]:
                try:
                    account_level = int(row[col_nivel])
                except:
                    pass
            
            parent_code = None
            if col_pai is not None and col_pai < len(row) and row[col_pai]:
                parent_code = str(row[col_pai]).strip()
            
            account_type = None
            if col_tipo is not None and col_tipo < len(row) and row[col_tipo]:
                account_type = str(row[col_tipo]).strip()
            
            nature = None
            if col_natureza is not None and col_natureza < len(row) and row[col_natureza]:
                nature = str(row[col_natureza]).strip()
            
            contas.append({
                "account_code": account_code,
                "account_name": account_name,
                "account_level": account_level,
                "parent_code": parent_code,
                "account_type": account_type,
                "nature": nature
            })
    
    return contas


def parse_plano_contas_excel(
    file_path: str | Path
) -> List[Dict]:
    """
    Lê um arquivo Excel do plano de contas.
    
    Returns:
        Lista de dicionários com os dados das contas
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    
    df = pd.read_excel(path, engine='openpyxl')
    
    contas = []
    
    # Encontra colunas
    col_codigo = None
    col_nome = None
    col_nivel = None
    col_pai = None
    col_tipo = None
    col_natureza = None
    
    for col in df.columns:
        col_upper = _normalize_column_name(str(col))
        
        if not col_codigo and any(n.upper() in col_upper for n in ['codigo', 'conta', 'account_code', 'cod', 'code']):
            col_codigo = col
        if not col_nome and any(n.upper() in col_upper for n in ['descricao', 'nome', 'account_name', 'name', 'desc']):
            col_nome = col
        if not col_nivel and any(n.upper() in col_upper for n in ['nivel', 'level', 'niv']):
            col_nivel = col
        if not col_pai and any(n.upper() in col_upper for n in ['pai', 'parent', 'parent_code', 'conta_pai']):
            col_pai = col
        if not col_tipo and any(n.upper() in col_upper for n in ['tipo', 'account_type', 'type', 'natureza']):
            col_tipo = col
        if not col_natureza and any(n.upper() in col_upper for n in ['nature', 'natureza', 'natureza_conta']):
            col_natureza = col
    
    if not col_codigo or not col_nome:
        raise ValueError(f"Colunas obrigatórias não encontradas. Colunas disponíveis: {list(df.columns)}")
    
    # Processa linhas
    for idx, row in df.iterrows():
        account_code = str(row[col_codigo]).strip() if pd.notna(row[col_codigo]) else ""
        if not account_code:
            continue
        
        account_name = str(row[col_nome]).strip() if pd.notna(row[col_nome]) else ""
        
        account_level = None
        if col_nivel and pd.notna(row[col_nivel]):
            try:
                account_level = int(row[col_nivel])
            except:
                pass
        
        parent_code = None
        if col_pai and pd.notna(row[col_pai]):
            parent_code = str(row[col_pai]).strip()
        
        account_type = None
        if col_tipo and pd.notna(row[col_tipo]):
            account_type = str(row[col_tipo]).strip()
        
        nature = None
        if col_natureza and pd.notna(row[col_natureza]):
            nature = str(row[col_natureza]).strip()
        
        contas.append({
            "account_code": account_code,
            "account_name": account_name,
            "account_level": account_level,
            "parent_code": parent_code,
            "account_type": account_type,
            "nature": nature
        })
    
    return contas


def parse_plano_contas(
    file_path: str | Path
) -> List[Dict]:
    """
    Função unificada que detecta o tipo de arquivo e chama o parser apropriado.
    """
    path = Path(file_path)
    
    if path.suffix.lower() == '.csv':
        return parse_plano_contas_csv(path)
    elif path.suffix.lower() in ['.xlsx', '.xls']:
        return parse_plano_contas_excel(path)
    else:
        raise ValueError(f"Formato não suportado: {path.suffix}. Use CSV ou Excel.")


