// src/api/comparacoes.ts
import api from "./client";
import {
  ComparacaoResumo,
  ComparacaoDetalhe,
} from "./types";

/**
 * Cria uma nova comparação.
 * Retorna imediatamente com status="processing".
 * Use aguardarComparacao() para polling até conclusão.
 */
export async function criarComparacao(params: {
  data_inicio: string; // YYYY-MM-DD
  data_fim: string;    // YYYY-MM-DD
  otimiza_txt_files: File[];
  mpds_pdf: File;
}): Promise<ComparacaoResumo> {
  const form = new FormData();
  form.append("data_inicio", params.data_inicio);
  form.append("data_fim", params.data_fim);
  
  for (const txtFile of params.otimiza_txt_files) {
    form.append("otimiza_txt_files", txtFile);
  }
  
  form.append("mpds_pdf", params.mpds_pdf);

  // Não setar Content-Type manualmente - deixar o browser definir boundary
  const { data } = await api.post<ComparacaoResumo>("/comparacoes/", form);
  return data;
}

/**
 * Aguarda a conclusão de uma comparação (polling).
 * @param id ID da comparação
 * @param intervaloMs Intervalo entre checks (default 2s)
 * @param timeoutMs Timeout máximo (default 180s)
 * @returns ComparacaoDetalhe quando concluída
 * @throws Error se falhar ou timeout
 */
export async function aguardarComparacao(
  id: number,
  intervaloMs: number = 2000,
  timeoutMs: number = 180000
): Promise<ComparacaoDetalhe> {
  const inicio = Date.now();
  
  while (true) {
    const detalhe = await obterComparacao(id);
    
    if (detalhe.status === "concluida") {
      return detalhe;
    }
    
    if (detalhe.status === "erro") {
      throw new Error(detalhe.erro || "Erro no processamento da comparação");
    }
    
    // Verifica timeout
    if (Date.now() - inicio > timeoutMs) {
      throw new Error("Timeout: processamento demorou mais que o esperado");
    }
    
    // Aguarda antes do próximo check
    await new Promise(resolve => setTimeout(resolve, intervaloMs));
  }
}

/**
 * Cria e aguarda conclusão da comparação (helper).
 */
export async function criarEAguardarComparacao(params: {
  data_inicio: string;
  data_fim: string;
  otimiza_txt_files: File[];
  mpds_pdf: File;
}): Promise<ComparacaoDetalhe> {
  const resumo = await criarComparacao(params);
  return aguardarComparacao(resumo.id);
}

export async function listarComparacoes(): Promise<ComparacaoResumo[]> {
  const { data } = await api.get<ComparacaoResumo[]>("/comparacoes/");
  return data;
}

export async function obterComparacao(id: number): Promise<ComparacaoDetalhe> {
  const { data } = await api.get<ComparacaoDetalhe>(`/comparacoes/${id}`);
  return data;
}

export async function deletarComparacao(id: number): Promise<void> {
  await api.delete(`/comparacoes/${id}`);
}
