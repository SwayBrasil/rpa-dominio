"""
Parser para arquivos MPDS em formato OFX (Open Financial Exchange)
"""

import re
import logging
from typing import List, Optional, Tuple
from pathlib import Path
from datetime import datetime, date

from app.core.models import Lancamento

logger = logging.getLogger(__name__)


def _parse_ofx_date(date_str: str) -> Optional[date]:
    """
    Converte data OFX para date.
    Formato OFX: YYYYMMDD ou YYYYMMDDHHMMSS
    """
    if not date_str or date_str.strip() == '':
        return None
    
    date_str = date_str.strip()
    
    # OFX pode ter formato YYYYMMDD ou YYYYMMDDHHMMSS
    if len(date_str) >= 8:
        try:
            year = int(date_str[0:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            return date(year, month, day)
        except (ValueError, IndexError):
            pass
    
    logger.warning(f"Não foi possível converter data OFX: {date_str}")
    return None


def _parse_ofx_amount(amount_str: str) -> float:
    """
    Converte valor OFX para float.
    OFX usa formato americano (ponto decimal).
    """
    if not amount_str or amount_str.strip() == '':
        return 0.0
    
    amount_str = amount_str.strip()
    
    try:
        return float(amount_str)
    except ValueError:
        logger.warning(f"Não foi possível converter valor OFX: {amount_str}")
        return 0.0


def parse_mpds_ofx(
    file_path: str | Path,
    strict: bool = False
) -> Tuple[List[Lancamento], List[str]]:
    """
    Lê um arquivo OFX MPDS e retorna uma lista de Lancamento.
    
    Args:
        file_path: Caminho para o arquivo OFX
        strict: Se True, falha ao encontrar transações não parseáveis. Se False, registra issues.
        
    Returns:
        Tupla (lista de Lancamento, lista de issues/erros)
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    
    lancamentos = []
    issues = []
    
    logger.info(f"Iniciando parsing do OFX MPDS: {path}")
    
    try:
        # Lê arquivo OFX
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # OFX pode ter tags XML ou formato SGML
        # Procura por blocos STMTTRN (Statement Transaction)
        
        # Padrão para encontrar transações
        # Formato OFX 1.x (SGML):
        # <STMTTRN>
        #   <DTPOSTED>20250101
        #   <TRNAMT>-1234.56
        #   <FITID>123456
        #   <MEMO>Descrição
        # </STMTTRN>
        
        # Formato OFX 2.x (XML):
        # <STMTTRN>
        #   <DTPOSTED>20250101
        #   <TRNAMT>-1234.56
        #   <FITID>123456
        #   <MEMO>Descrição
        # </STMTTRN>
        
        # Regex para encontrar transações (funciona com ambos os formatos)
        stmttrn_pattern = re.compile(
            r'<STMTTRN>(.*?)</STMTTRN>',
            re.DOTALL | re.IGNORECASE
        )
        
        transacoes = stmttrn_pattern.findall(content)
        
        logger.debug(f"Total de transações encontradas: {len(transacoes)}")
        
        for idx, transacao in enumerate(transacoes, 1):
            try:
                # Extrai campos da transação
                dtposted_match = re.search(r'<DTPOSTED[^>]*>([^<]+)', transacao, re.IGNORECASE)
                trnamt_match = re.search(r'<TRNAMT[^>]*>([^<]+)', transacao, re.IGNORECASE)
                fitid_match = re.search(r'<FITID[^>]*>([^<]+)', transacao, re.IGNORECASE)
                memo_match = re.search(r'<MEMO[^>]*>([^<]+)', transacao, re.IGNORECASE)
                name_match = re.search(r'<NAME[^>]*>([^<]+)', transacao, re.IGNORECASE)
                
                # Data (obrigatória)
                if not dtposted_match:
                    issues.append(f"Transação {idx}: DTPOSTED não encontrado")
                    if strict:
                        raise ValueError(f"Transação {idx}: DTPOSTED não encontrado")
                    continue
                
                data = _parse_ofx_date(dtposted_match.group(1))
                if not data:
                    issues.append(f"Transação {idx}: Data inválida: {dtposted_match.group(1)}")
                    if strict:
                        raise ValueError(f"Transação {idx}: Data inválida")
                    continue
                
                # Valor (obrigatório)
                if not trnamt_match:
                    issues.append(f"Transação {idx}: TRNAMT não encontrado")
                    if strict:
                        raise ValueError(f"Transação {idx}: TRNAMT não encontrado")
                    continue
                
                valor = _parse_ofx_amount(trnamt_match.group(1))
                if valor == 0.0:
                    continue  # Pula transações com valor zero
                
                # Descrição (MEMO ou NAME)
                descricao = ""
                if memo_match:
                    descricao = memo_match.group(1).strip()
                elif name_match:
                    descricao = name_match.group(1).strip()
                
                if not descricao:
                    descricao = "Transação sem descrição"
                
                # Documento (FITID - Financial Institution Transaction ID)
                documento = None
                if fitid_match:
                    documento = fitid_match.group(1).strip()
                
                lancamento = Lancamento(
                    data=data,
                    descricao=descricao,
                    documento=documento,
                    valor=valor,
                    saldo=None,  # OFX geralmente não tem saldo por transação
                    conta_contabil=None,
                    origem="mpds"
                )
                
                lancamentos.append(lancamento)
                
            except Exception as e:
                issues.append(f"Transação {idx}: Erro ao processar: {e}")
                if strict:
                    raise
                continue
        
        # Se não encontrou transações no formato STMTTRN, tenta formato alternativo
        if len(transacoes) == 0:
            logger.warning("Nenhuma transação STMTTRN encontrada. Tentando formato alternativo...")
            
            # Tenta encontrar padrões mais simples
            # Alguns OFX podem ter formato diferente
            # TODO: Implementar parsing alternativo se necessário
        
        logger.info(f"Parsing concluído. Total de lançamentos extraídos: {len(lancamentos)}")
        if issues:
            logger.warning(f"Total de issues encontradas: {len(issues)}")
        
    except Exception as e:
        logger.error(f"Erro ao processar OFX: {e}")
        raise
    
    return lancamentos, issues


