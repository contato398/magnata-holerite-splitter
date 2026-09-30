/**
 * Uma coluna da esteira (item 4 do pedido): quantidade, documentos
 * prioritarios primeiro, situacao, tempo na etapa, bloqueio, proxima
 * acao e indicacao automatica/humana -- estas tres ultimas ja vem
 * dentro de cada DocumentoCard.
 */
import { h } from '../utils/dom.js';
import { DocumentoCard } from './DocumentoCard.js';
import { estadoVazio } from './EstadosUI.js';
import { rotuloEtapa, formatarDuracaoSegundos } from '../utils/format.js';
import { ehPrioritario } from '../utils/prioridade.js';

function ordenarPrioritariosPrimeiro(documentos) {
  return [...documentos].sort((a, b) => {
    const pa = ehPrioritario(a) ? 1 : 0;
    const pb = ehPrioritario(b) ? 1 : 0;
    if (pa !== pb) return pb - pa;
    return (b.tempo_na_etapa_segundos || 0) - (a.tempo_na_etapa_segundos || 0);
  });
}

/**
 * @param {string} etapa
 * @param {import('../api/contracts.js').DocumentoEsteiraResponse[]} documentos
 */
export function EsteiraColuna(etapa, documentos, opcoes = {}) {
  const ordenados = ordenarPrioritariosPrimeiro(documentos);
  const bloqueados = documentos.filter((d) => d.situacao === 'BLOQUEADO').length;
  const acaoHumana = documentos.filter((d) => d.proxima_acao && d.proxima_acao.tipo === 'HUMANA').length;
  const tempos = documentos.map((d) => d.tempo_na_etapa_segundos).filter((t) => t != null);
  const tempoMedio = tempos.length ? tempos.reduce((a, b) => a + b, 0) / tempos.length : null;

  return h('section', { className: 'esteira-coluna', 'aria-label': `Etapa ${rotuloEtapa(etapa)}` }, [
    h('header', { className: 'esteira-coluna-cabecalho' }, [
      h('div', { className: 'esteira-coluna-titulo' }, [
        h('h3', {}, rotuloEtapa(etapa)),
        h('span', { className: 'esteira-coluna-contagem' }, String(documentos.length)),
      ]),
      h('div', { className: 'esteira-coluna-metricas' }, [
        h('span', {}, [h('strong', {}, String(bloqueados)), ' bloqueados']),
        h('span', {}, [h('strong', {}, String(acaoHumana)), ' p/ você']),
        tempoMedio != null ? h('span', {}, [h('strong', {}, formatarDuracaoSegundos(tempoMedio)), ' médio']) : null,
      ].filter(Boolean)),
    ]),
    h('div', { className: 'esteira-coluna-corpo' },
      ordenados.length
        ? ordenados.map((doc) => DocumentoCard(doc, { layout: 'coluna', onAbrir: opcoes.onAbrirDocumento }))
        : [h('div', { className: 'esteira-coluna-vazia' }, 'Nenhum documento nesta etapa')]
    ),
  ]);
}
