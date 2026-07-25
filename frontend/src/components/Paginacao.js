/**
 * Controles de paginacao -- usados pelas listas (documentos, bloqueios,
 * acoes humanas, parados). Componente controlado: so chama
 * `onMudarPagina(novaPagina)`.
 */
import { h } from '../utils/dom.js';

/** @param {import('../api/contracts.js').PaginacaoResponse} paginacao */
export function Paginacao(paginacao, { onMudarPagina }) {
  if (paginacao.total_paginas <= 1) return h('div', {});
  const { pagina, total_paginas: totalPaginas, total_itens: totalItens } = paginacao;
  return h('nav', { className: 'paginacao', 'aria-label': 'Paginação' }, [
    h('button', { onClick: () => onMudarPagina(pagina - 1), disabled: pagina <= 1, type: 'button' }, 'Anterior'),
    h('span', { className: 'paginacao-info' }, `Página ${pagina} de ${totalPaginas} · ${totalItens} no total`),
    h('button', { onClick: () => onMudarPagina(pagina + 1), disabled: pagina >= totalPaginas, type: 'button' }, 'Próxima'),
  ]);
}
