# 📋 Pendências e Melhorias Futuras

Este documento lista funcionalidades pendentes e melhorias planejadas para o projeto.

## ⚠️ Funcionalidades Pendentes

### 1. Tolerância de Dias no Matching
**Localização:** `backend/app/services/comparador/motor.py:457`

**Status:** Não implementado

**Descrição:** O parâmetro `tolerancia_dias` está definido mas não é utilizado no matching de lançamentos. Isso permitiria casar lançamentos com pequenas diferenças de data (ex: lançamento no banco em 01/03 e no TXT em 02/03).

**Impacto:** Médio - Pode reduzir falsos positivos de divergências quando há pequenos deslocamentos de data.

**Implementação sugerida:**
- Modificar `_comparar_por_data_valor` para considerar `tolerancia_dias`
- Permitir matching quando `abs(data1 - data2).days <= tolerancia_dias`

---

### 2. Melhorias nas Regras de Classificação Suspeita
**Localização:** `backend/app/services/comparador/motor.py:464`

**Status:** Implementado parcialmente

**Descrição:** As regras de detecção de classificação contábil suspeita podem ser aprimoradas com base em feedback do uso real.

**Impacto:** Baixo - Funcionalidade já implementada, apenas refinamento.

**Melhorias sugeridas:**
- Expandir lista de palavras-chave suspeitas
- Ajustar regras de contas adequadas conforme feedback
- Adicionar regras específicas por tipo de lançamento

---

### 3. Detecção Automática de Layout do TXT Otimiza
**Localização:** `backend/app/services/parsers/otimiza_txt_parser.py:166`

**Status:** Não implementado

**Descrição:** O parser atual tenta múltiplos padrões, mas poderia detectar automaticamente o layout do arquivo TXT para melhorar a precisão.

**Impacto:** Médio - Melhoraria a robustez do parser para diferentes formatos de exportação do Otimiza.

**Implementação sugerida:**
- Analisar primeiras linhas do arquivo para identificar padrão
- Detectar delimitadores, formato de data, posição dos campos
- Aplicar parser específico baseado na detecção

---

### 4. Parsing Alternativo para OFX
**Localização:** `backend/app/services/parsers/mpds_ofx_parser.py:189`

**Status:** Não implementado

**Descrição:** Há um TODO para implementar parsing alternativo caso o formato OFX padrão não funcione.

**Impacto:** Baixo - Funcionalidade já funciona para OFX padrão, apenas fallback.

---

## ✅ Funcionalidades Implementadas

- ✅ Upload de múltiplos arquivos TXT (PAGAR e RECEBER)
- ✅ Parser robusto de PDF Sicoob com state machine
- ✅ Parser de PDF Nubank
- ✅ Parser de CSV e OFX
- ✅ Comparação de lançamentos com matching inteligente
- ✅ Validação de contas contábeis
- ✅ Interface web completa
- ✅ API REST completa
- ✅ Testes automatizados
- ✅ Suporte a valores isolados antes da data (Sicoob)
- ✅ Normalização de descrições para matching
- ✅ Detecção de divergências (valor diferente, faltantes, etc.)

---

## 🔄 Melhorias de Performance (Opcional)

1. **Cache de parsing:** Cachear resultados de parsing de arquivos idênticos
2. **Processamento assíncrono:** Processar comparações grandes em background
3. **Otimização de queries:** Índices adicionais no banco para consultas mais rápidas

---

## 📝 Notas

- As funcionalidades pendentes são melhorias opcionais, não bloqueiam o uso do sistema
- O sistema está funcional e pronto para uso em produção
- As melhorias podem ser implementadas conforme necessidade e feedback dos usuários

---

**Última atualização:** 14/12/2025
