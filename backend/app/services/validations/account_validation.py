"""
Motor de Validação Determinística de Contas Contábeis
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.plano_contas import (
    ChartOfAccounts,
    AccountValidationRule,
    AccountValidationResult,
)
from app.core.models import Lancamento

logger = logging.getLogger(__name__)


def validate_account_exists(
    account_code: str,
    source: str = "dominio",
    db: Session = None
) -> Tuple[bool, str]:
    """
    Valida se a conta existe no plano de contas.
    
    Args:
        account_code: Código da conta
        source: Fonte do plano de contas (default: "dominio")
        db: Sessão do banco de dados
        
    Returns:
        Tupla (existe: bool, mensagem: str)
    """
    if not account_code or not account_code.strip():
        return False, "Código de conta vazio"
    
    account_code = account_code.strip()
    
    if not db:
        return False, "Sessão do banco não fornecida"
    
    conta = (
        db.query(ChartOfAccounts)
        .filter(
            and_(
                ChartOfAccounts.account_code == account_code,
                ChartOfAccounts.source == source,
                ChartOfAccounts.is_active == True
            )
        )
        .first()
    )
    
    if conta:
        return True, f"Conta {account_code} encontrada: {conta.account_name}"
    else:
        return False, f"Conta {account_code} não encontrada no plano de contas"


def find_matching_rules(
    lancamento: Lancamento,
    db: Session
) -> List[AccountValidationRule]:
    """
    Encontra regras de validação que correspondem ao lançamento.
    
    Args:
        lancamento: Lançamento do Otimiza
        db: Sessão do banco de dados
        
    Returns:
        Lista de regras que correspondem
    """
    if not db:
        return []
    
    # Busca regras habilitadas
    regras = (
        db.query(AccountValidationRule)
        .filter(AccountValidationRule.is_enabled == True)
        .all()
    )
    
    matching_rules = []
    
    for regra in regras:
        # Obtém o valor do campo de match do lançamento
        match_value = None
        
        if regra.match_field == "event_type":
            match_value = lancamento.event_type
        elif regra.match_field == "category":
            match_value = lancamento.category
        elif regra.match_field == "entity_type":
            match_value = lancamento.entity_type
        else:
            # Tenta acessar como atributo do lançamento
            match_value = getattr(lancamento, regra.match_field, None)
        
        # Match simples: igualdade case-insensitive
        if match_value and match_value.strip().upper() == regra.match_value.strip().upper():
            matching_rules.append(regra)
    
    return matching_rules


def validate_account_against_rules(
    account_code: str,
    rules: List[AccountValidationRule]
) -> Dict:
    """
    Valida se a conta está de acordo com as regras.
    
    Args:
        account_code: Código da conta
        rules: Lista de regras aplicáveis
        
    Returns:
        Dict com status, reason_code, message, expected, meta
    """
    if not account_code or not account_code.strip():
        return {
            "status": "unknown",
            "reason_code": "MISSING_ACCOUNT_CODE",
            "message": "Código de conta não fornecido",
            "expected": None,
            "meta": None
        }
    
    account_code = account_code.strip()
    
    if not rules:
        return {
            "status": "unknown",
            "reason_code": "NO_RULE_MATCH",
            "message": "Nenhuma regra encontrada para este tipo de lançamento",
            "expected": None,
            "meta": None
        }
    
    # Aplica todas as regras (se uma falhar, retorna invalid)
    for regra in rules:
        allowed = False
        
        # Verifica allowed_account_codes
        if regra.allowed_account_codes:
            if account_code in regra.allowed_account_codes:
                allowed = True
        
        # Verifica allowed_account_prefixes
        if not allowed and regra.allowed_account_prefixes:
            for prefix in regra.allowed_account_prefixes:
                if account_code.startswith(prefix):
                    allowed = True
                    break
        
        # Verifica blocked_account_codes
        if regra.blocked_account_codes and account_code in regra.blocked_account_codes:
            return {
                "status": "invalid",
                "reason_code": "RULE_VIOLATION",
                "message": regra.message or f"Conta {account_code} está bloqueada pela regra '{regra.name}'",
                "expected": {
                    "allowed_prefixes": regra.allowed_account_prefixes or [],
                    "allowed_codes": regra.allowed_account_codes or [],
                    "blocked_prefixes": regra.blocked_account_prefixes or [],
                    "blocked_codes": regra.blocked_account_codes or []
                },
                "meta": {
                    "rule_id": regra.id,
                    "rule_name": regra.name,
                    "match_field": regra.match_field,
                    "match_value": regra.match_value,
                    "severity": regra.severity
                }
            }
        
        # Verifica blocked_account_prefixes
        if regra.blocked_account_prefixes:
            for prefix in regra.blocked_account_prefixes:
                if account_code.startswith(prefix):
                    return {
                        "status": "invalid",
                        "reason_code": "RULE_VIOLATION",
                        "message": regra.message or f"Conta {account_code} está bloqueada pela regra '{regra.name}' (prefixo {prefix})",
                        "expected": {
                            "allowed_prefixes": regra.allowed_account_prefixes or [],
                            "allowed_codes": regra.allowed_account_codes or [],
                            "blocked_prefixes": regra.blocked_account_prefixes or [],
                            "blocked_codes": regra.blocked_account_codes or []
                        },
                        "meta": {
                            "rule_id": regra.id,
                            "rule_name": regra.name,
                            "match_field": regra.match_field,
                            "match_value": regra.match_value,
                            "severity": regra.severity
                        }
                    }
        
        # Se não está em allowed, viola a regra
        if not allowed:
            return {
                "status": "invalid",
                "reason_code": "RULE_VIOLATION",
                "message": regra.message or f"Conta {account_code} não está permitida pela regra '{regra.name}'",
                "expected": {
                    "allowed_prefixes": regra.allowed_account_prefixes or [],
                    "allowed_codes": regra.allowed_account_codes or [],
                    "blocked_prefixes": regra.blocked_account_prefixes or [],
                    "blocked_codes": regra.blocked_account_codes or []
                },
                "meta": {
                    "rule_id": regra.id,
                    "rule_name": regra.name,
                    "match_field": regra.match_field,
                    "match_value": regra.match_value,
                    "severity": regra.severity
                }
            }
    
    # Se passou por todas as regras, está OK
    return {
        "status": "ok",
        "reason_code": "VALID",
        "message": f"Conta {account_code} validada com sucesso",
        "expected": None,
        "meta": {
            "rules_applied": [r.id for r in rules]
        }
    }


def validate_lancamentos_accounts(
    comparacao_id: int,
    lancamentos_otimiza: List[Lancamento],
    source: str = "dominio",
    db: Session = None
) -> Dict:
    """
    Valida contas de todos os lançamentos do Otimiza.
    
    Args:
        comparacao_id: ID da comparação
        lancamentos_otimiza: Lista de lançamentos do Otimiza
        source: Fonte do plano de contas
        db: Sessão do banco de dados
        
    Returns:
        Dict com resumo: total, ok, invalid, unknown
    """
    if not db:
        raise ValueError("Sessão do banco de dados é obrigatória")
    
    total = len(lancamentos_otimiza)
    ok_count = 0
    invalid_count = 0
    unknown_count = 0
    
    logger.info(f"[ACCOUNT_VALIDATION] Iniciando validação para comparação {comparacao_id}, total={total}")
    
    for idx, lancamento in enumerate(lancamentos_otimiza):
        # Gera chave única do lançamento
        lancamento_key = f"{lancamento.data.isoformat()}_{lancamento.valor}_{idx}"
        
        account_code = lancamento.account_code or lancamento.conta_contabil
        
        # Se não tem código de conta
        if not account_code or not account_code.strip():
            result = AccountValidationResult(
                comparacao_id=comparacao_id,
                lancamento_key=lancamento_key,
                account_code="",
                status="unknown",
                reason_code="MISSING_ACCOUNT_CODE",
                message="Código de conta não fornecido no lançamento",
                expected=None,
                meta={
                    "data": lancamento.data.isoformat(),
                    "descricao": lancamento.descricao,
                    "valor": lancamento.valor
                }
            )
            db.add(result)
            unknown_count += 1
            continue
        
        account_code = account_code.strip()
        
        # Valida existência
        exists, exists_msg = validate_account_exists(account_code, source, db)
        
        if not exists:
            result = AccountValidationResult(
                comparacao_id=comparacao_id,
                lancamento_key=lancamento_key,
                account_code=account_code,
                status="invalid",
                reason_code="ACCOUNT_NOT_FOUND",
                message=exists_msg,
                expected=None,
                meta={
                    "data": lancamento.data.isoformat(),
                    "descricao": lancamento.descricao,
                    "valor": lancamento.valor
                }
            )
            db.add(result)
            invalid_count += 1
            logger.warning(f"[ACCOUNT_VALIDATION] comparacao_id={comparacao_id} account_code={account_code} ACCOUNT_NOT_FOUND")
            continue
        
        # Busca regras
        rules = find_matching_rules(lancamento, db)
        
        # Valida contra regras
        validation_result = validate_account_against_rules(account_code, rules)
        
        # Adiciona dados do lançamento ao meta
        if validation_result["meta"]:
            validation_result["meta"].update({
                "data": lancamento.data.isoformat(),
                "descricao": lancamento.descricao,
                "valor": lancamento.valor,
                "event_type": lancamento.event_type,
                "category": lancamento.category,
                "entity_type": lancamento.entity_type
            })
        
        result = AccountValidationResult(
            comparacao_id=comparacao_id,
            lancamento_key=lancamento_key,
            account_code=account_code,
            status=validation_result["status"],
            reason_code=validation_result["reason_code"],
            message=validation_result["message"],
            expected=validation_result["expected"],
            meta=validation_result["meta"]
        )
        db.add(result)
        
        if validation_result["status"] == "ok":
            ok_count += 1
        elif validation_result["status"] == "invalid":
            invalid_count += 1
            logger.warning(
                f"[ACCOUNT_VALIDATION] comparacao_id={comparacao_id} account_code={account_code} "
                f"RULE_VIOLATION rule_id={validation_result['meta'].get('rule_id') if validation_result['meta'] else None}"
            )
        else:
            unknown_count += 1
    
    db.flush()
    
    logger.info(
        f"[ACCOUNT_VALIDATION] comparacao_id={comparacao_id} total={total} "
        f"ok={ok_count} invalid={invalid_count} unknown={unknown_count}"
    )
    
    return {
        "total": total,
        "ok": ok_count,
        "invalid": invalid_count,
        "unknown": unknown_count
    }


