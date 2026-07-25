/**
 * Quadro da esteira completo -- 10 colunas (ENTRADA..AUDITORIA, item 4).
 * Em telas pequenas NAO comprime as colunas: troca para uma lista unica
 * com um seletor de etapa (ver utils/responsive.js e item 11 do
 * pedido). Documentos nao rastreados pela esteira (legados) ficam fora
 * do quadro -- eles pertencem a tela de Documentos, nao a esteira.
 */
import { h } from '../utils/dom.js';
import { ORDEM_ETAPAS } from '../api/contracts.js';
import { EsteiraColuna } from './EsteiraColuna.js';
import { DocumentoCard } from './DocumentoCard.js';
import { estadoVazio } from './EstadosUI.js';
import { rotuloEtapa } from '../utils/format.js';
import { escolherModoEsteira } from '../utils/responsive.js';

function agruparPorEtapa(documentos) {
  const grupos = new Map(ORDEM_ETAPAS.map((etapa) => [etapa, []]));
  for (const doc of documentos) {
    if (!doc.rastreado_pela_esteira || !grupos.has(doc.etapa_atual)) continue;
    grupos.get(doc.etapa_atual).push(doc);
  }
  return grupos;
}

/**
 * @param {import('../api/contracts.js').DocumentoEsteiraResponse[]} documentos
 * @param {{larguraViewport:number, etapaSelecionadaMobile?:string, onSelecionarEtapaMobile?:(etapa:string)=>void, onAbrirDocumento?:(id:string)=>void}} opcoes
 */
export function EsteiraBoard(documentos, opcoes) {
  const { larguraViewport, etapaSelecionadaMobile, onSelecionarEtapaMobile, onAbrirDocumento } = opcoes;
  const grupos = agruparPorEtapa(documentos);
  const modo = escolherModoEsteira(larguraViewport);

  if (modo === 'kanban') {
    return h('div', { className: 'rolagem-horizontal', role: 'list', 'aria-label': 'Esteira documental por etapa' },
      ORDEM_ETAPAS.map((etapa) => EsteiraColuna(etapa, grupos.get(etapa) || [], { onAbrirDocumento }))
    );
  }

  // modo 'lista': seletor de etapa + lista unica (nunca colunas espremidas)
  const etapaAtual = etapaSelecionadaMobile && ORDEM_ETAPAS.includes(etapaSelecionadaMobile)
    ? etapaSelecionadaMobile
    : ORDEM_ETAPAS[0];
  const documentosDaEtapa = grupos.get(etapaAtual) || [];

  const seletor = h('select', {
    onChange: (ev) => onSelecionarEtapaMobile && onSelecionarEtapaMobile(ev.target.value),
  }, ORDEM_ETAPAS.map((etapa) => h('option', {
    value: etapa,
    selected: etapa === etapaAtual,
  }, `${rotuloEtapa(etapa)} (${(grupos.get(etapa) || []).length})`)));

  return h('div', {}, [
    h('div', { className: 'esteira-seletor-mobile' }, [seletor]),
    h('div', { className: 'lista-cartoes' },
      documentosDaEtapa.length
        ? documentosDaEtapa.map((doc) => DocumentoCard(doc, { layout: 'linha', onAbrir: onAbrirDocumento }))
        : [estadoVazio({ titulo: 'Nenhum documento nesta etapa', descricao: `Não há documentos em "${rotuloEtapa(etapaAtual)}" no momento.` })]
    ),
  ]);
}
