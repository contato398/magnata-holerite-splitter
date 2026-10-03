/**
 * Cartoes de resumo operacional (item 3 do pedido): total de
 * documentos, recebidos hoje, em processamento, em revisao, bloqueados,
 * com acao humana, em erro, prontos, concluidos.
 *
 * "Recebidos hoje" nao e um campo do ResumoEsteiraResponse (Fase 4 so
 * expõe `lotes_recebidos_hoje`) -- e calculado por uma chamada
 * suplementar a listarDocumentos() com o filtro `recebido_de` (campo
 * que ja existe no contrato de filtro), lendo `total_itens` da resposta
 * paginada. Ver views/DashboardView.js. Nenhum campo novo foi inventado
 * na API.
 */
import { h } from '../utils/dom.js';

/**
 * @param {import('../api/contracts.js').ResumoEsteiraResponse} resumo
 * @param {{recebidosHoje?: number, onSelecionar?: (chave:string)=>void}} opcoes
 */
export function ResumoCards(resumo, opcoes = {}) {
  const { recebidosHoje = null, onSelecionar } = opcoes;
  const porSituacao = resumo.total_por_situacao || {};

  const cartoes = [
    { chave: 'total', rotulo: 'Total de documentos', valor: resumo.total_documentos },
    { chave: 'recebidos_hoje', rotulo: 'Recebidos hoje', valor: recebidosHoje ?? '—' },
    { chave: 'EM_PROCESSAMENTO', rotulo: 'Em processamento', valor: porSituacao.EM_PROCESSAMENTO || 0 },
    { chave: 'EM_REVISAO', rotulo: 'Em revisão', valor: porSituacao.EM_REVISAO || 0 },
    { chave: 'bloqueados', rotulo: 'Bloqueados', valor: resumo.total_bloqueados, destaque: 'erro' },
    { chave: 'acao_humana', rotulo: 'Com ação humana', valor: resumo.total_com_acao_humana, destaque: 'dourado' },
    { chave: 'ERRO', rotulo: 'Em erro', valor: resumo.total_em_erro, destaque: 'erro' },
    { chave: 'PRONTO', rotulo: 'Prontos', valor: porSituacao.PRONTO || 0 },
    { chave: 'CONCLUIDO', rotulo: 'Concluídos', valor: porSituacao.CONCLUIDO || 0 },
  ];

  return h('div', { className: 'grade-resumo', role: 'list', 'aria-label': 'Resumo operacional' },
    cartoes.map((c) => h('div', {
      className: [
        'cartao-resumo',
        c.destaque === 'dourado' ? 'destaque-dourado' : '',
        c.destaque === 'erro' ? 'destaque-erro' : '',
        onSelecionar ? 'clicavel' : '',
      ].filter(Boolean).join(' '),
      role: 'listitem',
      tabIndex: onSelecionar ? 0 : undefined,
      onClick: onSelecionar ? () => onSelecionar(c.chave) : undefined,
    }, [
      h('span', { className: 'valor' }, String(c.valor)),
      h('span', { className: 'rotulo' }, c.rotulo),
    ]))
  );
}
