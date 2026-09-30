/**
 * "responsividade basica" (item 12) -- a decisao pura de qual modo de
 * layout usar por largura de viewport, sem depender de matchMedia/DOM.
 */
import { describe, it, assertEqual } from './test-harness.js';
import { escolherModoEsteira, LARGURA_CORTE_MOBILE } from '../src/utils/responsive.js';

describe('utils/responsive.js', () => {
  it('celular (< 768px) usa lista com seletor de etapa, nunca kanban espremido', () => {
    assertEqual(escolherModoEsteira(375), 'lista');
    assertEqual(escolherModoEsteira(767), 'lista');
  });

  it('tablet/desktop (>= 768px) usa colunas kanban', () => {
    assertEqual(escolherModoEsteira(768), 'kanban');
    assertEqual(escolherModoEsteira(1280), 'kanban');
    assertEqual(escolherModoEsteira(1920), 'kanban');
  });

  it('o corte usado e exatamente LARGURA_CORTE_MOBILE', () => {
    assertEqual(escolherModoEsteira(LARGURA_CORTE_MOBILE - 1), 'lista');
    assertEqual(escolherModoEsteira(LARGURA_CORTE_MOBILE), 'kanban');
  });
});
