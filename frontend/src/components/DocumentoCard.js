/**
 * Cartao de documento (item 5 do pedido) -- mostra nome original,
 * origem, lote, etapa, situacao, tempo parado, motivo do bloqueio,
 * proxima acao, prioridade e se a acao e humana ou automatica.
 *
 * Dois layouts: 'coluna' (compacto, usado dentro da esteira) e 'linha'
 * (usado em listas -- bloqueios, acoes humanas, parados, busca).
 */
import { h } from '../utils/dom.js';
import { icon } from '../utils/icons.js';
import { rotuloEtapa, rotuloSituacao, tempoRelativoDeSegundos, truncarNomeArquivo } from '../utils/format.js';
import { ehPrioritario, LIMITE_PARADO_PADRAO_SEGUNDOS } from '../utils/prioridade.js';

function badgeSituacao(situacao) {
  if (!situacao) return null;
  return h('span', { className: `badge badge-situacao-${situacao.toLowerCase()} badge-ponto` }, rotuloSituacao(situacao));
}

function badgeAcao(proximaAcao) {
  if (!proximaAcao) return null;
  const ehHumana = proximaAcao.tipo === 'HUMANA';
  return h('span', { className: `badge ${ehHumana ? 'badge-acao-humana' : 'badge-acao-automatica'}` }, [
    icon(ehHumana ? 'pessoa' : 'raio', { style: { width: '11px', height: '11px' } }),
    ehHumana ? 'Precisa de você' : 'Automática',
  ]);
}

/**
 * @param {import('../api/contracts.js').DocumentoEsteiraResponse} documento
 * @param {{layout?: 'coluna'|'linha', limiteParadoSegundos?: number, onAbrir?: (documentoId:string)=>void}} opcoes
 */
export function DocumentoCard(documento, opcoes = {}) {
  const { layout = 'coluna', limiteParadoSegundos = LIMITE_PARADO_PADRAO_SEGUNDOS, onAbrir } = opcoes;
  const prioritario = ehPrioritario(documento, limiteParadoSegundos);
  const tempoAlerta = documento.tempo_na_etapa_segundos != null && documento.tempo_na_etapa_segundos >= limiteParadoSegundos;

  const classes = ['cartao-documento'];
  if (layout === 'linha') classes.push('layout-linha');
  if (prioritario) classes.push('prioritario');
  if (documento.proxima_acao && documento.proxima_acao.tipo === 'HUMANA') classes.push('acao-humana');

  const nome = h('div', { className: 'cartao-documento-nome' }, truncarNomeArquivo(documento.nome_original));

  const meta = h('div', { className: 'cartao-documento-meta' }, [
    documento.origem ? h('span', {}, documento.origem) : null,
    documento.lote_id ? h('span', {}, `Lote ${documento.lote_id}`) : h('span', {}, 'Sem lote'),
    !documento.rastreado_pela_esteira ? h('span', {}, 'Documento anterior à esteira') : null,
  ]);

  const badges = h('div', { className: 'cartao-documento-badges' }, [
    layout === 'linha' ? h('span', { className: 'badge', style: { background: '#eef0f3', color: 'var(--cor-texto-secundario)' } }, rotuloEtapa(documento.etapa_atual)) : null,
    badgeSituacao(documento.situacao),
    prioritario ? h('span', { className: 'badge badge-prioridade' }, 'Prioritário') : null,
  ]);

  const tempoNode = h('span', { className: `cartao-documento-tempo ${tempoAlerta ? 'tempo-alerta' : ''}` }, [
    icon('relogio', { style: { width: '11px', height: '11px', display: 'inline', verticalAlign: '-1px', marginRight: '3px' } }),
    tempoRelativoDeSegundos(documento.tempo_na_etapa_segundos).replace('há ', ''),
  ]);

  const blocoBloqueio = documento.motivo_bloqueio
    ? h('div', { className: 'cartao-documento-proxima-acao', style: { color: 'var(--cor-situacao-bloqueado)', fontWeight: '600' } }, [
      icon('cadeado', { style: { width: '11px', height: '11px' } }),
      documento.motivo_bloqueio.descricao,
    ])
    : null;

  const blocoProximaAcao = documento.proxima_acao
    ? h('div', { className: 'cartao-documento-proxima-acao' }, [
      icon('seta', { style: { width: '11px', height: '11px' } }),
      documento.proxima_acao.acao,
    ])
    : null;

  const conteudoPrincipal = h('div', { className: layout === 'linha' ? 'cartao-documento-principal' : undefined }, [
    nome, meta, badges, blocoBloqueio, layout === 'coluna' ? blocoProximaAcao : null,
  ].filter(Boolean));

  const lateral = layout === 'linha'
    ? h('div', { className: 'cartao-documento-lateral' }, [
      badgeAcao(documento.proxima_acao),
      tempoNode,
    ])
    : h('div', { className: 'cartao-documento-badges', style: { justifyContent: 'space-between', alignItems: 'center' } }, [
      badgeAcao(documento.proxima_acao),
      tempoNode,
    ]);

  const filhos = layout === 'linha' ? [conteudoPrincipal, lateral] : [conteudoPrincipal, lateral];

  return h('article', {
    className: classes.join(' '),
    role: 'button',
    tabIndex: 0,
    'aria-label': `Abrir detalhes de ${documento.nome_original}`,
    dataset: { documentoId: documento.documento_id },
    onClick: () => onAbrir && onAbrir(documento.documento_id),
    onKeydown: (ev) => {
      if ((ev.key === 'Enter' || ev.key === ' ') && onAbrir) {
        ev.preventDefault();
        onAbrir(documento.documento_id);
      }
    },
  }, filhos);
}
