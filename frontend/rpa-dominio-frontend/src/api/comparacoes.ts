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
 * Aguarda a conclusão de uma comparação (polling com backoff).
 * @param id ID da comparação
 * @param timeoutMs Timeout máximo (default 300s = 5min)
 * @returns ComparacaoDetalhe quando concluída
 * @throws Error se falhar ou timeout
 */
export async function aguardarComparacao(
  id: number,
  timeoutMs: number = 300000
): Promise<ComparacaoDetalhe> {
  const inicio = Date.now();
  let intervalo = 2000; // Começa com 2s
  const maxIntervalo = 10000; // Máximo 10s
  let retries = 0;
  const maxRetries = 3;
  
  while (true) {
    try {
      const detalhe = await obterComparacao(id);
      retries = 0; // Reset retries on success
      
      if (detalhe.status === "concluida") {
        return detalhe;
      }
      
      if (detalhe.status === "erro") {
        throw new Error(detalhe.erro || "Erro no processamento da comparação");
      }
      
      if (detalhe.status === "timeout") {
        throw new Error(detalhe.erro || "Processamento demorou muito. Tente um PDF menor.");
      }
      
      // Verifica timeout do polling
      if (Date.now() - inicio > timeoutMs) {
        throw new Error("Timeout: processamento demorou mais que o esperado");
      }
      
      // Aguarda com backoff
      await new Promise(resolve => setTimeout(resolve, intervalo));
      intervalo = Math.min(intervalo * 1.5, maxIntervalo); // Backoff
      
    } catch (error: unknown) {
      // Se for erro de rede, tenta novamente
      const axiosError = error as { code?: string; message?: string };
      if (axiosError.code === "ERR_NETWORK" && retries < maxRetries) {
        retries++;
        console.warn(`Erro de rede, tentativa ${retries}/${maxRetries}...`);
        await new Promise(resolve => setTimeout(resolve, 5000)); // Aguarda 5s
        continue;
      }
      throw error;
    }
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
