// src/api/client.ts
import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  timeout: 120000, // 120 segundos (2 minutos) - suficiente para processar PDFs grandes
});

export default api;






