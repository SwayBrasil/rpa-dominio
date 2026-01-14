"""
Motor de comparação entre extratos bancários e razão analítico do Domínio
"""

import logging
from typing import List, Dict, Tuple, Set, Optional
from datetime import date, timedelta
from collections import defaultdict

from app.core.models import Lancamento
from app.core.divergencias import Divergencia, TipoDivergencia

logger = logging.getLogger(__name__)


def _normalizar_descricao(descricao: str) -> str:
    """
    Normaliza descrição para comparação:
    - Converte para minúsculas
    - Remove acentos (simplificado)
    - Normaliza espaços múltiplos
    - Remove informações redundantes de PIX (DOC, CNPJ/CPF, PGT/PGTO, etc.)
    """
    if not descricao:
        return ""
    
    import re
    
    # Converte para minúsculas
    desc = descricao.lower().strip()
    
    # Remove acentos (mapeamento básico)
    acentos = {
        'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n'
    }
    for acento, sem_acento in acentos.items():
        desc = desc.replace(acento, sem_acento)
    
    # Remove informações redundantes de PIX/transações
    # Remove DOC. seguido de números
    desc = re.sub(r'\bdoc\.?\s*\d+\b', '', desc)
    # Remove CNPJ/CPF (formato XX.XXX.XXX/XXXX-XX ou XXX.XXX.XXX-XX)
    desc = re.sub(r'\b\d{2,3}\.?\d{3}\.?\d{3}[\/-]?\d{2,4}[-\s]?\d{2}\b', '', desc)
    # Remove "PGT", "PGTO", "PAGTO" seguido de números
    desc = re.sub(r'\b(pgt|pgto|pagto)\.?\s*\d*\b', '', desc, flags=re.IGNORECASE)
    # Remove "NU PAGAMENTOS", "IP", "AGENCIA", "CONTA" seguido de números
    desc = re.sub(r'\b(nu\s+pagamentos|ip|agencia|conta)\s*:?\s*\d+[-\s]?\d*\b', '', desc, flags=re.IGNORECASE)
    # Remove "•••" (mascaramento de CPF)
    desc = re.sub(r'•+', '', desc)
    
    # Normaliza espaços múltiplos
    desc = re.sub(r'\s+', ' ', desc)
    
    return desc.strip()


def _chave_principal(l: Lancamento, arredondar_valor: bool = True) -> Tuple[date, float]:
    """
    Retorna chave de match principal: (data, valor_arredondado).
    
    Args:
        l: Lançamento
        arredondar_valor: Se True, arredonda valor para 2 casas decimais
        
    Returns:
        Tupla (data, valor_arredondado)
    """
    valor = round(l.valor, 2) if arredondar_valor else l.valor
    return (l.data, valor)


def _chave_documento(l: Lancamento) -> Optional[Tuple[date, str]]:
    """
    Retorna chave de match por documento: (data, documento).
    Retorna None se não houver documento.
    """
    if not l.documento or l.documento.strip() == '':
        return None
    return (l.data, l.documento.strip().upper())


def _chave_descricao(l: Lancamento) -> Tuple[date, str]:
    """
    Retorna chave de match por descrição normalizada: (data, descricao_normalizada).
    """
    desc_normalizada = _normalizar_descricao(l.descricao)
    return (l.data, desc_normalizada)


def _detectar_valor_diferente(
    lanc_extrato: List[Lancamento],
    lanc_razao: List[Lancamento],
    tolerancia_valor: float,
    casados: Set[Tuple[int, int]]
) -> List[Divergencia]:
    """
    Detecta lançamentos com mesma data + documento (ou descrição) mas valor diferente.
    
    Args:
        lanc_extrato: Lista de lançamentos do extrato
        lanc_razao: Lista de lançamentos do razão
        tolerancia_valor: Tolerância para diferença de valor
        casados: Set de tuplas (idx_extrato, idx_razao) já casados (será atualizado)
        
    Returns:
        Lista de divergências do tipo VALOR_DIFERENTE
    """
    divergencias = []
    
    # Índice por (data, documento) do razão
    indice_doc_razao: Dict[Tuple[date, str], List[int]] = defaultdict(list)
    for idx, l in enumerate(lanc_razao):
        chave = _chave_documento(l)
        if chave:
            indice_doc_razao[chave].append(idx)
    
    # Índice por (data, descrição_normalizada) do razão (fallback)
    indice_desc_razao: Dict[Tuple[date, str], List[int]] = defaultdict(list)
    for idx, l in enumerate(lanc_razao):
        chave = _chave_descricao(l)
        indice_desc_razao[chave].append(idx)
    
    # Para cada lançamento do extrato
    for idx_ext, lanc_ext in enumerate(lanc_extrato):
        # Tenta match por documento primeiro
        chave_doc = _chave_documento(lanc_ext)
        match_encontrado = False
        
        if chave_doc and chave_doc in indice_doc_razao:
            for idx_raz in indice_doc_razao[chave_doc]:
                lanc_raz = lanc_razao[idx_raz]
                
                # Verifica se já foi casado
                if (idx_ext, idx_raz) in casados:
                    continue
                
                # Verifica diferença de valor
                diff_valor = abs(lanc_ext.valor - lanc_raz.valor)
                if diff_valor > tolerancia_valor:
                    divergencias.append(Divergencia(
                        tipo="VALOR_DIFERENTE",
                        descricao=(
                            f"Lançamento com mesmo documento ({lanc_ext.documento}) "
                            f"e data ({lanc_ext.data}) tem valor diferente. "
                            f"Extrato: R$ {lanc_ext.valor:,.2f}, "
                            f"Domínio: R$ {lanc_raz.valor:,.2f} "
                            f"(diferença: R$ {diff_valor:,.2f})"
                        ),
                        lancamento_extrato=lanc_ext,
                        lancamento_dominio=lanc_raz
                    ))
                    casados.add((idx_ext, idx_raz))
                    match_encontrado = True
                    break
        
        # Se não encontrou por documento, tenta por descrição normalizada
        if not match_encontrado:
            chave_desc = _chave_descricao(lanc_ext)
            if chave_desc in indice_desc_razao:
                for idx_raz in indice_desc_razao[chave_desc]:
                    lanc_raz = lanc_razao[idx_raz]
                    
                    if (idx_ext, idx_raz) in casados:
                        continue
                    
                    diff_valor = abs(lanc_ext.valor - lanc_raz.valor)
                    if diff_valor > tolerancia_valor:
                        # Só cria divergência se a diferença for significativa
                        # e as descrições forem muito similares
                        if diff_valor > 1.0:  # Pelo menos R$ 1,00 de diferença
                            divergencias.append(Divergencia(
                                tipo="VALOR_DIFERENTE",
                                descricao=(
                                    f"Lançamento com mesma descrição e data ({lanc_ext.data}) "
                                    f"tem valor diferente. "
                                    f"Extrato: R$ {lanc_ext.valor:,.2f}, "
                                    f"Domínio: R$ {lanc_raz.valor:,.2f} "
                                    f"(diferença: R$ {diff_valor:,.2f})"
                                ),
                                lancamento_extrato=lanc_ext,
                                lancamento_dominio=lanc_raz
                            ))
                            casados.add((idx_ext, idx_raz))
                            break
    
    return divergencias


def _comparar_por_data_valor(
    lanc_extrato: List[Lancamento],
    lanc_razao: List[Lancamento],
    tolerancia_valor: float,
    casados: Set[Tuple[int, int]]
) -> Tuple[List[Divergencia], Set[int], Set[int]]:
    """
    Compara lançamentos por data + valor (com tolerância).
    
    Args:
        lanc_extrato: Lista de lançamentos do extrato
        lanc_razao: Lista de lançamentos do razão
        tolerancia_valor: Tolerância para diferença de valor
        casados: Set de tuplas (idx_extrato, idx_razao) já casados (será atualizado)
        
    Returns:
        Tupla (divergencias, indices_extrato_nao_casados, indices_razao_nao_casados)
    """
    divergencias = []
    
    # Índice do razão por (data, valor_arredondado)
    # Usa lista porque pode haver múltiplos lançamentos com mesma chave
    indice_razao: Dict[Tuple[date, float], List[int]] = defaultdict(list)
    for idx, l in enumerate(lanc_razao):
        chave = _chave_principal(l)
        indice_razao[chave].append(idx)
    
    # Índices não casados
    indices_extrato_nao_casados = set(range(len(lanc_extrato)))
    indices_razao_nao_casados = set(range(len(lanc_razao)))
    
    # Para cada lançamento do extrato
    for idx_ext, lanc_ext in enumerate(lanc_extrato):
        if idx_ext not in indices_extrato_nao_casados:
            continue  # Já foi casado
        
        chave = _chave_principal(lanc_ext)
        
        # Procura match exato primeiro
        if chave in indice_razao:
            for idx_raz in indice_razao[chave]:
                if idx_raz not in indices_razao_nao_casados:
                    continue
                
                # Verifica se já foi casado em outra etapa
                if (idx_ext, idx_raz) in casados:
                    continue
                
                # Match encontrado!
                indices_extrato_nao_casados.discard(idx_ext)
                indices_razao_nao_casados.discard(idx_raz)
                casados.add((idx_ext, idx_raz))
                break
        
        # Se não encontrou match exato, tenta com tolerância
        else:
            # Procura valores próximos na mesma data
            for idx_raz, lanc_raz in enumerate(lanc_razao):
                if idx_raz not in indices_razao_nao_casados:
                    continue
                
                if (idx_ext, idx_raz) in casados:
                    continue
                
                # Mesma data e valor dentro da tolerância
                if lanc_ext.data == lanc_raz.data:
                    diff_valor = abs(lanc_ext.valor - lanc_raz.valor)
                    if diff_valor <= tolerancia_valor:
                        # Match com tolerância
                        indices_extrato_nao_casados.discard(idx_ext)
                        indices_razao_nao_casados.discard(idx_raz)
                        casados.add((idx_ext, idx_raz))
                        break
    
    return divergencias, indices_extrato_nao_casados, indices_razao_nao_casados


def _detectar_faltantes(
    lanc_extrato: List[Lancamento],
    lanc_razao: List[Lancamento],
    indices_extrato_nao_casados: Set[int],
    indices_razao_nao_casados: Set[int]
) -> List[Divergencia]:
    """
    Cria divergências para lançamentos não encontrados.
    """
    divergencias = []
    
    # Lançamentos no extrato que não foram encontrados no domínio
    for idx in indices_extrato_nao_casados:
        lanc = lanc_extrato[idx]
        divergencias.append(Divergencia(
            tipo="NAO_ENCONTRADO_DOMINIO",
            descricao=(
                f"Lançamento do extrato não encontrado no Domínio. "
                f"Data: {lanc.data.strftime('%d/%m/%Y')}, "
                f"Descrição: {lanc.descricao[:50]}, "
                f"Valor: R$ {lanc.valor:,.2f}"
            ),
            lancamento_extrato=lanc,
            lancamento_dominio=None
        ))
    
    # Lançamentos no domínio que não foram encontrados no extrato
    for idx in indices_razao_nao_casados:
        lanc = lanc_razao[idx]
        divergencias.append(Divergencia(
            tipo="NAO_ENCONTRADO_EXTRATO",
            descricao=(
                f"Lançamento do Domínio não encontrado no extrato. "
                f"Data: {lanc.data.strftime('%d/%m/%Y')}, "
                f"Descrição: {lanc.descricao[:50]}, "
                f"Valor: R$ {lanc.valor:,.2f}"
            ),
            lancamento_extrato=None,
            lancamento_dominio=lanc
        ))
    
    return divergencias


def _comparar_saldos(
    lanc_extrato: List[Lancamento],
    lanc_razao: List[Lancamento],
    tolerancia_valor: float
) -> List[Divergencia]:
    """
    Compara saldos iniciais e finais entre extrato e razão.
    
    Args:
        lanc_extrato: Lista de lançamentos do extrato
        lanc_razao: Lista de lançamentos do razão
        tolerancia_valor: Tolerância para diferença de saldo
        
    Returns:
        Lista de divergências do tipo SALDO_DIVERGENTE
    """
    divergencias = []
    
    # Extrai saldos do extrato
    saldos_extrato = [l.saldo for l in lanc_extrato if l.saldo is not None]
    if not saldos_extrato:
        return divergencias  # Sem saldos no extrato, não há o que comparar
    
    saldo_inicial_extrato = saldos_extrato[0]
    saldo_final_extrato = saldos_extrato[-1]
    
    # Extrai saldos do razão
    saldos_razao = [l.saldo for l in lanc_razao if l.saldo is not None]
    if not saldos_razao:
        return divergencias  # Sem saldos no razão, não há o que comparar
    
    saldo_inicial_razao = saldos_razao[0]
    saldo_final_razao = saldos_razao[-1]
    
    # Compara saldos iniciais
    diff_inicial = abs(saldo_inicial_extrato - saldo_inicial_razao)
    diff_final = abs(saldo_final_extrato - saldo_final_razao)
    
    if diff_inicial > tolerancia_valor or diff_final > tolerancia_valor:
        descricao = (
            f"Saldo inicial/final divergente entre extrato e domínio. "
            f"Extrato: R$ {saldo_inicial_extrato:,.2f} → R$ {saldo_final_extrato:,.2f}; "
            f"Domínio: R$ {saldo_inicial_razao:,.2f} → R$ {saldo_final_razao:,.2f}."
        )
        
        if diff_inicial > tolerancia_valor:
            descricao += f" Diferença no saldo inicial: R$ {diff_inicial:,.2f}."
        if diff_final > tolerancia_valor:
            descricao += f" Diferença no saldo final: R$ {diff_final:,.2f}."
        
        divergencias.append(Divergencia(
            tipo="SALDO_DIVERGENTE",
            descricao=descricao,
            lancamento_extrato=None,
            lancamento_dominio=None
        ))
    
    return divergencias


def _detectar_classificacao_suspeita(
    lanc_razao: List[Lancamento]
) -> List[Divergencia]:
    """
    Detecta lançamentos com classificação contábil suspeita.
    
    Regras básicas:
    - Descrições que sugerem tarifas/encargos/juros sem conta contábil adequada
    - Contas contábeis muito genéricas (ex.: só "1" ou "9")
    
    TODO: Ajustar regras conforme necessidade do escritório.
    
    Args:
        lanc_razao: Lista de lançamentos do razão (domínio)
        
    Returns:
        Lista de divergências do tipo CLASSIFICACAO_SUSPEITA
    """
    divergencias = []
    
    # Palavras-chave que sugerem despesas/tarifas
    palavras_suspeitas = [
        'tarifa', 'taxa', 'encargo', 'juros', 'multa', 'iof',
        'cobrança', 'manutenção', 'anuidade', 'serviço bancário'
    ]
    
    # Contas genéricas suspeitas (apenas números simples)
    contas_genericas = {'1', '9', '0', '00', '000'}
    
    for lanc in lanc_razao:
        if lanc.origem != "dominio":
            continue
        
        desc_lower = _normalizar_descricao(lanc.descricao)
        
        # Verifica se descrição contém palavras suspeitas
        tem_palavra_suspeita = any(palavra in desc_lower for palavra in palavras_suspeitas)
        
        # Verifica conta contábil
        conta_ok = False
        if lanc.conta_contabil:
            conta_clean = lanc.conta_contabil.strip()
            # Conta não pode ser muito genérica
            if conta_clean not in contas_genericas and len(conta_clean) >= 3:
                conta_ok = True
        
        # Se tem palavra suspeita mas não tem conta adequada
        if tem_palavra_suspeita and not conta_ok:
            divergencias.append(Divergencia(
                tipo="CLASSIFICACAO_SUSPEITA",
                descricao=(
                    f"Lançamento com descrição suspeita de tarifa/encargo "
                    f"({lanc.descricao[:50]}) sem classificação contábil adequada. "
                    f"Conta: {lanc.conta_contabil or 'N/A'}"
                ),
                lancamento_extrato=None,
                lancamento_dominio=lanc
            ))
    
    return divergencias


def comparar_lancamentos(
    lanc_extrato: List[Lancamento],
    lanc_razao: List[Lancamento],
    tolerancia_valor: float = 0.01,
    tolerancia_dias: int = 0,
) -> List[Divergencia]:
    """
    Compara listas de lançamentos do extrato e do domínio e retorna divergências.
    
    Fluxo completo:
    1. Detecta VALOR_DIFERENTE (por documento/descrição).
    2. Casa lançamentos por data + valor.
    3. Marca NAO_ENCONTRADO_DOMINIO e NAO_ENCONTRADO_EXTRATO.
    4. Compara saldos e gera SALDO_DIVERGENTE, se houver.
    5. Roda regras de CLASSIFICACAO_SUSPEITA.
    
    Args:
        lanc_extrato: Lista de lançamentos do extrato bancário
        lanc_razao: Lista de lançamentos do razão analítico do Domínio
        tolerancia_valor: Tolerância para diferença de valor (default: 0.01 = 1 centavo)
        tolerancia_dias: Tolerância para diferença de dias (não implementado ainda, TODO)
        
    Returns:
        Lista de divergências encontradas
        
    TODO:
        - Implementar tolerancia_dias para matching com deslocamento de data
        - Melhorar regras de CLASSIFICACAO_SUSPEITA conforme feedback
    """
    logger.info(f"Iniciando comparação: {len(lanc_extrato)} lançamentos no extrato, "
                f"{len(lanc_razao)} no razão")
    
    divergencias = []
    
    # Set para rastrear lançamentos já casados (idx_extrato, idx_razao)
    casados: Set[Tuple[int, int]] = set()
    
    # 1. Detecta VALOR_DIFERENTE (por documento/descrição)
    divergencias.extend(_detectar_valor_diferente(
        lanc_extrato, lanc_razao, tolerancia_valor, casados
    ))
    
    # 2. Casa lançamentos por data + valor (com tolerância)
    _, indices_extrato_nao_casados, indices_razao_nao_casados = _comparar_por_data_valor(
        lanc_extrato, lanc_razao, tolerancia_valor, casados
    )
    
    # 3. Marca lançamentos faltantes
    divergencias.extend(_detectar_faltantes(
        lanc_extrato, lanc_razao,
        indices_extrato_nao_casados, indices_razao_nao_casados
    ))
    
    # 4. Compara saldos
    divergencias.extend(_comparar_saldos(
        lanc_extrato, lanc_razao, tolerancia_valor
    ))
    
    # 5. Detecta classificação contábil suspeita
    divergencias.extend(_detectar_classificacao_suspeita(lanc_razao))
    
    logger.info(f"Comparação concluída. Total de divergências: {len(divergencias)}")
    
    return divergencias


def compare_bank_vs_txt(
    bank_movements: List[Lancamento],
    txt_movements: List[Lancamento],
    date_window_days: int = 2,
    amount_tolerance: float = 0.01,
    min_description_similarity: float = 0.55,
    allow_many_to_one: bool = True,
) -> List[Divergencia]:
    """
    Compara movimentos bancários (extrato) com lançamentos do TXT Otimiza.
    
    Args:
        bank_movements: Lista de lançamentos do extrato bancário (origem="mpds")
        txt_movements: Lista de lançamentos do TXT Otimiza (origem="otimiza")
        date_window_days: Janela de dias para matching (padrão: 2)
        amount_tolerance: Tolerância para diferença de valor (padrão: 0.01)
        min_description_similarity: Similaridade mínima de descrição (0-1, padrão: 0.55)
        allow_many_to_one: Se True, permite múltiplos lançamentos TXT casarem com um do banco
        
    Returns:
        Lista de divergências encontradas
    """
    from datetime import timedelta
    from difflib import SequenceMatcher
    
    logger.info(f"Iniciando comparação TXT: {len(bank_movements)} movimentos bancários, "
                f"{len(txt_movements)} lançamentos TXT")
    
    divergencias = []
    casados_bank: Set[int] = set()
    casados_txt: Set[int] = set()
    
    def _similarity(str1: str, str2: str) -> float:
        """Calcula similaridade entre duas strings (0-1) usando normalização"""
        if not str1 or not str2:
            return 0.0
        # Normaliza ambas as strings antes de comparar
        str1_norm = _normalizar_descricao(str1)
        str2_norm = _normalizar_descricao(str2)
        return SequenceMatcher(None, str1_norm, str2_norm).ratio()
    
    # Para cada movimento bancário, tenta encontrar match no TXT
    for idx_bank, mov_bank in enumerate(bank_movements):
        if idx_bank in casados_bank:
            continue
        
        melhor_match = None
        melhor_score = 0.0
        melhor_idx_txt = None
        
        # Procura melhor match no TXT
        for idx_txt, mov_txt in enumerate(txt_movements):
            if idx_txt in casados_txt:
                continue
            
            score = 0.0
            
            # Score por valor (peso forte: 0.5)
            diff_valor = abs(mov_bank.valor - mov_txt.valor)
            if diff_valor <= amount_tolerance:
                score += 0.5  # Match exato de valor
            elif diff_valor <= 1.0:  # Diferença pequena
                score += 0.3
            elif diff_valor <= 10.0:  # Diferença média
                score += 0.1
            else:
                continue  # Diferença muito grande, pula
            
            # Score por data (peso médio: 0.3)
            diff_dias = abs((mov_bank.data - mov_txt.data).days)
            if diff_dias == 0:
                score += 0.3
            elif diff_dias <= date_window_days:
                score += 0.2 - (diff_dias * 0.05)  # Penaliza por dia
            else:
                continue  # Fora da janela, pula
            
            # Score por descrição (peso baixo: 0.2)
            sim_desc = _similarity(mov_bank.descricao, mov_txt.descricao)
            if sim_desc >= min_description_similarity:
                score += 0.2 * sim_desc
            
            # Score por documento (bônus: 0.1)
            if mov_bank.documento and mov_txt.documento:
                if mov_bank.documento.strip().upper() == mov_txt.documento.strip().upper():
                    score += 0.1
            
            # Atualiza melhor match
            if score > melhor_score:
                melhor_score = score
                melhor_match = mov_txt
                melhor_idx_txt = idx_txt
        
        # Se encontrou match bom (score >= 0.6)
        if melhor_match and melhor_score >= 0.6:
            casados_bank.add(idx_bank)
            casados_txt.add(melhor_idx_txt)
            
            # Verifica se há divergência de valor mesmo com match
            diff_valor = abs(mov_bank.valor - melhor_match.valor)
            if diff_valor > amount_tolerance:
                divergencias.append(Divergencia(
                    tipo="VALOR_DIFERENTE",
                    descricao=(
                        f"Movimento bancário casado com TXT mas valor diferente. "
                        f"Banco: R$ {mov_bank.valor:,.2f}, TXT: R$ {melhor_match.valor:,.2f} "
                        f"(diferença: R$ {diff_valor:,.2f})"
                    ),
                    lancamento_extrato=mov_bank,
                    lancamento_dominio=melhor_match
                ))
        else:
            # Não encontrou match - movimento bancário faltante no TXT
            divergencias.append(Divergencia(
                tipo="NAO_ENCONTRADO_DOMINIO",  # Reutiliza tipo existente
                descricao=(
                    f"Movimento bancário não encontrado no TXT Otimiza. "
                    f"Data: {mov_bank.data.strftime('%d/%m/%Y')}, "
                    f"Descrição: {mov_bank.descricao[:50]}, "
                    f"Valor: R$ {mov_bank.valor:,.2f}"
                ),
                lancamento_extrato=mov_bank,
                lancamento_dominio=None
            ))
    
    # Lançamentos TXT que não foram casados
    for idx_txt in range(len(txt_movements)):
        if idx_txt not in casados_txt:
            mov_txt = txt_movements[idx_txt]
            divergencias.append(Divergencia(
                tipo="NAO_ENCONTRADO_EXTRATO",  # Reutiliza tipo existente
                descricao=(
                    f"Lançamento TXT Otimiza não encontrado no extrato bancário. "
                    f"Data: {mov_txt.data.strftime('%d/%m/%Y')}, "
                    f"Descrição: {mov_txt.descricao[:50]}, "
                    f"Valor: R$ {mov_txt.valor:,.2f}"
                ),
                lancamento_extrato=None,
                lancamento_dominio=mov_txt
            ))
    
    logger.info(f"Comparação TXT concluída. Total de divergências: {len(divergencias)}")
    
    return divergencias

