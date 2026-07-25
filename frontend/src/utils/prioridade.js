/**
 * Regra de "documento prioritario" -- conceito de UI (nao existe campo
 * `prioridade` nos contratos da Fase 4), derivado de dois sinais que a
 * API ja expõe: bloqueio ativo ou tempo na etapa acima do limite
 * padrao de "parado" (mesmo limite_parado_segundos usado no resumo,
 * ver handlers.py LIMITE_PARADO_PADRAO_SEGUNDOS).
 *
 * Funcao pura -- testada isoladamente (tests/prioridade.test.js).
 */

export const LIMITE_PARADO_PADRAO_SEGUNDOS = 24 * 60 * 60;

export function ehPrioritario(documento, limiteSegundos = LIMITE_PARADO_PADRAO_SEGUNDOS) {
  if (!documento) return false;
  if (documento.situacao === 'BLOQUEADO') return true;
  if (documento.situacao === 'ERRO') return true;
  return documento.tempo_na_etapa_segundos != null && documento.tempo_na_etapa_segundos >= limiteSegundos;
}
