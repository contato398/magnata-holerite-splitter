/**
 * Filtros, paginacao e ordenacao -- espelha filtros.py (Fase 4): mesmos
 * campos, mesmos limites, mesma logica de "ordenacao segura" (allowlist
 * fixo por endpoint, nunca acesso dinamico a um campo vindo de fora).
 *
 * Funcoes puras, sem DOM, sem fetch -- testadas isoladamente em
 * tests/filtros.test.js e reaproveitadas tanto pelo mockAdapter.js
 * quanto (no futuro) por um client.js real.
 */

import { FiltroInvalido, OrdenacaoInvalida, PaginacaoInvalida } from '../api/errors.js';

export const TAMANHO_PAGINA_PADRAO = 20;
export const TAMANHO_PAGINA_MAXIMO = 200;

export const CAMPOS_ORDENACAO_DOCUMENTOS = Object.freeze([
  'atualizado_em', 'entrou_na_etapa_em', 'recebido_em', 'documento_id', 'tempo_na_etapa_segundos',
]);
export const CAMPOS_ORDENACAO_LOTES = Object.freeze(['criado_em', 'recebido_em', 'quantidade_arquivos', 'lote_id']);
export const CAMPOS_ORDENACAO_BLOQUEIOS = Object.freeze(['tempo_bloqueado_segundos', 'documento_id']);

/** @returns {{pagina:number, tamanho_pagina:number}} */
export function criarPaginacao(pagina = 1, tamanho_pagina = TAMANHO_PAGINA_PADRAO) {
  return { pagina, tamanho_pagina };
}

/** @returns {{campo:string, direcao:'asc'|'desc'}} */
export function criarOrdenacao(campo, direcao = 'desc') {
  return { campo, direcao };
}

export function validarPaginacao(paginacao) {
  if (paginacao.pagina < 1) {
    throw new PaginacaoInvalida(`pagina deve ser >= 1 (recebido: ${paginacao.pagina}).`);
  }
  if (paginacao.tamanho_pagina < 1) {
    throw new PaginacaoInvalida(`tamanho_pagina deve ser >= 1 (recebido: ${paginacao.tamanho_pagina}).`);
  }
  if (paginacao.tamanho_pagina > TAMANHO_PAGINA_MAXIMO) {
    throw new PaginacaoInvalida(
      `tamanho_pagina nao pode exceder ${TAMANHO_PAGINA_MAXIMO} (recebido: ${paginacao.tamanho_pagina}).`
    );
  }
}

export function validarOrdenacao(ordenacao, camposPermitidos) {
  if (!camposPermitidos.includes(ordenacao.campo)) {
    const permitidosStr = [...camposPermitidos].sort().join(', ');
    throw new OrdenacaoInvalida(`campo de ordenacao invalido: "${ordenacao.campo}" (permitido: ${permitidosStr}).`);
  }
  if (ordenacao.direcao !== 'asc' && ordenacao.direcao !== 'desc') {
    throw new OrdenacaoInvalida(`direcao de ordenacao invalida: "${ordenacao.direcao}" (permitido: asc, desc).`);
  }
}

function validarIntervaloRecebido(recebidoDe, recebidoAte) {
  if (recebidoDe != null && recebidoAte != null && new Date(recebidoDe) > new Date(recebidoAte)) {
    throw new FiltroInvalido('recebido_de nao pode ser posterior a recebido_ate.');
  }
}

export function validarFiltroDocumentos(filtro) {
  validarIntervaloRecebido(filtro.recebido_de, filtro.recebido_ate);
  if (filtro.tempo_minimo_parado_segundos != null && filtro.tempo_minimo_parado_segundos < 0) {
    throw new FiltroInvalido('tempo_minimo_parado_segundos nao pode ser negativo.');
  }
}

export function validarFiltroLotes(filtro) {
  validarIntervaloRecebido(filtro.recebido_de, filtro.recebido_ate);
}

// ---------------------------------------------------------------------
// Aplicacao pura de filtro/ordenacao/paginacao sobre arrays em memoria
// (usado pelo mockAdapter -- um client HTTP real delegaria isso ao
// backend via query string, mas a MESMA validacao acima continua
// valendo no frontend antes de disparar a chamada).
// ---------------------------------------------------------------------

/** Documentos ja no formato DocumentoEsteiraResponse. */
export function aplicarFiltroDocumentos(documentos, filtro = {}) {
  return documentos.filter((doc) => {
    if (filtro.etapa != null && doc.etapa_atual !== filtro.etapa) return false;
    if (filtro.situacao != null && doc.situacao !== filtro.situacao) return false;
    if (filtro.lote_id != null && doc.lote_id !== filtro.lote_id) return false;
    if (filtro.origem != null && doc.origem !== filtro.origem) return false;
    if (filtro.bloqueado != null && (doc.situacao === 'BLOQUEADO') !== filtro.bloqueado) return false;
    if (filtro.acao_humana != null) {
      const temAcaoHumana = doc.proxima_acao != null && doc.proxima_acao.tipo === 'HUMANA';
      if (temAcaoHumana !== filtro.acao_humana) return false;
    }
    if (filtro.recebido_de != null && new Date(doc.recebido_em) < new Date(filtro.recebido_de)) return false;
    if (filtro.recebido_ate != null && new Date(doc.recebido_em) > new Date(filtro.recebido_ate)) return false;
    if (filtro.tempo_minimo_parado_segundos != null) {
      if (doc.tempo_na_etapa_segundos == null || doc.tempo_na_etapa_segundos < filtro.tempo_minimo_parado_segundos) {
        return false;
      }
    }
    if (filtro.busca) {
      const alvo = `${doc.nome_original} ${doc.documento_id}`.toLowerCase();
      if (!alvo.includes(filtro.busca.toLowerCase())) return false;
    }
    return true;
  });
}

export function aplicarFiltroLotes(lotes, filtro = {}) {
  return lotes.filter((lote) => {
    if (filtro.origem != null && lote.origem !== filtro.origem) return false;
    if (filtro.situacao != null && lote.situacao !== filtro.situacao) return false;
    if (filtro.recebido_de != null && new Date(lote.recebido_em) < new Date(filtro.recebido_de)) return false;
    if (filtro.recebido_ate != null && new Date(lote.recebido_em) > new Date(filtro.recebido_ate)) return false;
    return true;
  });
}

/**
 * Itens sem valor no campo de ordenacao sempre vao para o fim, em
 * qualquer direcao -- mesma regra de _ordenar_seguro() (handlers.py).
 */
export function ordenarSeguro(itens, extrator, direcao) {
  const comValor = [];
  const semValor = [];
  for (const item of itens) {
    (extrator(item) == null ? semValor : comValor).push(item);
  }
  comValor.sort((a, b) => {
    const va = extrator(a);
    const vb = extrator(b);
    let cmp = 0;
    if (va > vb) cmp = 1;
    else if (va < vb) cmp = -1;
    return direcao === 'desc' ? -cmp : cmp;
  });
  return [...comValor, ...semValor];
}

/**
 * Converte o estado bruto da UI (Filtros.js -- datas como string
 * 'YYYY-MM-DD', tempo parado em HORAS, campo `busca`) para o formato
 * de filtro dos contratos da API (ISO datetime, segundos). Nenhum
 * campo novo e inventado -- so uma conversao de unidade/formato para o
 * que o contrato ja espera.
 */
export function converterFiltroUIParaContrato(valoresUI = {}) {
  const filtro = {};
  if (valoresUI.etapa) filtro.etapa = valoresUI.etapa;
  if (valoresUI.situacao) filtro.situacao = valoresUI.situacao;
  if (valoresUI.origem) filtro.origem = valoresUI.origem;
  if (valoresUI.lote_id) filtro.lote_id = valoresUI.lote_id;
  if (valoresUI.bloqueado === true) filtro.bloqueado = true;
  if (valoresUI.acao_humana === true) filtro.acao_humana = true;
  if (valoresUI.busca) filtro.busca = valoresUI.busca;
  if (valoresUI.recebido_de_data) filtro.recebido_de = new Date(`${valoresUI.recebido_de_data}T00:00:00`).toISOString();
  if (valoresUI.recebido_ate_data) filtro.recebido_ate = new Date(`${valoresUI.recebido_ate_data}T23:59:59`).toISOString();
  if (valoresUI.tempo_minimo_parado_horas !== '' && valoresUI.tempo_minimo_parado_horas != null) {
    filtro.tempo_minimo_parado_segundos = Number(valoresUI.tempo_minimo_parado_horas) * 3600;
  }
  return filtro;
}

export function paginar(itens, paginacao) {
  const totalItens = itens.length;
  const totalPaginas = totalItens > 0 ? Math.ceil(totalItens / paginacao.tamanho_pagina) : 0;
  const inicio = (paginacao.pagina - 1) * paginacao.tamanho_pagina;
  const fim = inicio + paginacao.tamanho_pagina;
  return {
    pagina: paginacao.pagina,
    tamanho_pagina: paginacao.tamanho_pagina,
    total_itens: totalItens,
    total_paginas: totalPaginas,
    itens: itens.slice(inicio, fim),
  };
}
