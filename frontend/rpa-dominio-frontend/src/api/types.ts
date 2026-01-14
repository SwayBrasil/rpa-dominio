// src/api/types.ts

export interface ComparacaoResumo {
  id: number;
  criado_em: string;
  periodo_inicio: string;
  periodo_fim: string;
  source_type?: string;
  bank_source_type?: string;
  status: string;
  qtd_lancamentos_extrato?: number | null; // MPDS (movimentações bancárias)
  qtd_lancamentos_razao?: number | null; // TXT Otimiza (lançamentos contábeis)
  qtd_divergencias?: number | null;
}

export interface AccountValidationSummary {
  total: number;
  ok: number;
  invalid: number;
  unknown: number;
}

export interface Divergencia {
  id: number;
  tipo: string; // vem como string do Enum
  descricao: string;

  data_extrato?: string | null;
  descricao_extrato?: string | null;
  valor_extrato?: number | null;
  documento_extrato?: string | null;
  conta_contabil_extrato?: string | null;

  data_dominio?: string | null;
  descricao_dominio?: string | null;
  valor_dominio?: number | null;
  documento_dominio?: string | null;
  conta_contabil_dominio?: string | null;
}

export interface ComparacaoDetalhe extends ComparacaoResumo {
  divergencias: Divergencia[];
  account_validation_summary?: AccountValidationSummary | null;
}





