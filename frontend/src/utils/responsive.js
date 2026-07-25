/**
 * Decisao pura de modo de layout por largura de viewport -- separada do
 * componente que renderiza (EsteiraBoard.js) para ser testavel sem DOM
 * (tests/responsive.test.js). Nenhuma chamada a matchMedia/window aqui.
 *
 * 'lista': celular -- a esteira NUNCA aparece como colunas espremidas;
 *          vira uma unica lista com um seletor de etapa (ver item 11 do
 *          pedido: "substituir colunas largas por navegacao adequada").
 * 'kanban': tablet/desktop -- colunas horizontais roláveis.
 */
export const LARGURA_CORTE_MOBILE = 768;

export function escolherModoEsteira(larguraViewport) {
  return larguraViewport < LARGURA_CORTE_MOBILE ? 'lista' : 'kanban';
}
