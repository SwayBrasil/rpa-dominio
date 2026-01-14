// src/api/comparacoes.ts
import api from "./client";
import {
  ComparacaoResumo,
  ComparacaoDetalhe,
} from "./types";

export async function criarComparacao(params: {
  data_inicio: string; // YYYY-MM-DD
  data_fim: string;    // YYYY-MM-DD
  otimiza_txt_files: File[];  // Lista de arquivos TXT (1 ou 2)
  mpds_pdf: File;  // Obrigatório no modo cliente
}): Promise<ComparacaoResumo> {
  const form = new FormData();
  form.append("data_inicio", params.data_inicio);
  form.append("data_fim", params.data_fim);
  
  // Adiciona múltiplos arquivos TXT
  for (const txtFile of params.otimiza_txt_files) {
    form.append("otimiza_txt_files", txtFile);
  }
  
  form.append("mpds_pdf", params.mpds_pdf);

  const { data } = await api.post<ComparacaoResumo>("/comparacoes", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return data;
}

export async function listarComparacoes(): Promise<ComparacaoResumo[]> {
  const { data } = await api.get<ComparacaoResumo[]>("/comparacoes");
  return data;
}

export async function obterComparacao(
  id: number
): Promise<ComparacaoDetalhe> {
  const { data } = await api.get<ComparacaoDetalhe>(`/comparacoes/${id}`);
  return data;
}

export async function deletarComparacao(id: number): Promise<void> {
  await api.delete(`/comparacoes/${id}`);
}


