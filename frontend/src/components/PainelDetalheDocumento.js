/**
 * Painel de detalhe do documento (item 7 do pedido) -- todos os campos
 * de DocumentoCard mais detalhado, e o historico resumido (item 7
 * tambem pede "historico resumido" como painel proprio; aqui ele vive
 * dentro do painel de documento, que e onde faz sentido de uso).
 *
 * O historico exige perfil GESTOR/AUDITOR (mesma regra de
 * obter_historico_documento, handlers.py) -- se o perfil atual for
 * OPERACIONAL, o bloco de historico mostra o estado "sem permissao"
 * SO nesse bloco, nunca escondendo o resto do painel (dados parciais).
 */
import { h } from '../utils/dom.js';
import { icon } from '../utils/icons.js';
import {
  rotuloEtapa, rotuloSituacao, rotuloTipoAcao, formatarDataHora, formatarDuracaoSegundos, tempoRelativoDeSegundos,
} from '../utils/format.js';
import { estadoCarregando, estadoSemPermissao, estadoVazio } from './EstadosUI.js';

function linha(rotulo, valor) {
  return h('div', { className: 'painel-linha' }, [h('span', { className: 'rotulo' }, rotulo), h('span', { className: 'valor' }, valor)]);
}

function blocoHistorico(estadoHistorico) {
  if (estadoHistorico.status === 'carregando') return estadoCarregando({ linhas: 3 });
  if (estadoHistorico.status === 'sem-permissao') {
    return estadoSemPermissao({ perfilAtual: estadoHistorico.perfilAtual, perfisPermitidos: ['GESTOR', 'AUDITOR'] });
  }
  if (estadoHistorico.status === 'erro') return h('p', { className: 'descricao-estado' }, 'Não foi possível carregar o histórico agora.');
  const eventos = estadoHistorico.dados?.eventos || [];
  if (!eventos.length) return estadoVazio({ titulo: 'Sem eventos registrados' });
  return h('div', { className: 'linha-do-tempo' }, eventos.map((ev) => h('div', { className: 'evento-timeline' }, [
    h('span', { className: 'marcador' }),
    h('div', { className: 'conteudo' }, [
      h('span', { className: 'evento-nome' }, ev.evento),
      h('span', { className: 'evento-quando' }, formatarDataHora(ev.timestamp)),
    ]),
  ])));
}

/**
 * @param {import('../api/contracts.js').DocumentoEsteiraResponse} documento
 * @param {{historico: {status:string, dados?:Object, perfilAtual?:string}, onFechar:()=>void, onAbrirLote?:(loteId:string)=>void}} opcoes
 */
export function PainelDetalheDocumento(documento, opcoes) {
  const { historico, onFechar, onAbrirLote } = opcoes;

  return h('div', { className: 'painel-sobreposto', onClick: (ev) => { if (ev.target === ev.currentTarget) onFechar(); } }, [
    h('div', { className: 'painel-conteudo', role: 'dialog', 'aria-label': `Detalhes de ${documento.nome_original}` }, [
      h('div', { className: 'painel-cabecalho' }, [
        h('div', {}, [
          h('h2', { style: { fontSize: 'var(--fonte-tamanho-lg)', color: 'var(--cor-marinho)' } }, documento.nome_original),
          h('span', { style: { fontSize: 'var(--fonte-tamanho-xs)', color: 'var(--cor-texto-terciario)' } }, documento.documento_id),
        ]),
        h('button', { className: 'painel-fechar', onClick: onFechar, 'aria-label': 'Fechar painel' }, [icon('fechar', { style: { width: '16px', height: '16px' } })]),
      ]),

      !documento.rastreado_pela_esteira
        ? h('div', { className: 'faixa-parcial' }, 'Documento anterior à esteira — sem etapa/situação rastreada.')
        : null,

      documento.motivo_bloqueio ? h('div', { className: 'painel-alerta-bloqueio' }, [
        h('strong', {}, `Bloqueado: ${documento.motivo_bloqueio.descricao}`),
        documento.motivo_bloqueio.detalhe_tecnico ? h('span', {}, documento.motivo_bloqueio.detalhe_tecnico) : null,
        h('span', {}, documento.motivo_bloqueio.resolvivel_automaticamente ? 'Pode se resolver automaticamente.' : 'Precisa de ação manual.'),
      ]) : null,

      h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Identificação'),
        linha('Origem', documento.origem),
        h('div', { className: 'painel-linha' }, [
          h('span', { className: 'rotulo' }, 'Lote'),
          documento.lote_id && onAbrirLote
            ? h('button', {
              className: 'valor', type: 'button',
              style: { background: 'none', border: 'none', color: 'var(--cor-marinho-600)', textDecoration: 'underline', cursor: 'pointer', font: 'inherit' },
              onClick: () => onAbrirLote(documento.lote_id),
            }, documento.lote_id)
            : h('span', { className: 'valor' }, documento.lote_id || 'Sem lote'),
        ]),
        linha('Recebido em', formatarDataHora(documento.recebido_em)),
      ]),

      h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Esteira' ),
        linha('Etapa atual', rotuloEtapa(documento.etapa_atual)),
        linha('Situação', rotuloSituacao(documento.situacao)),
        linha('Tempo na etapa', `${tempoRelativoDeSegundos(documento.tempo_na_etapa_segundos)} (${formatarDuracaoSegundos(documento.tempo_na_etapa_segundos)})`),
        linha('Atualizado em', formatarDataHora(documento.atualizado_em)),
      ]),

      h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Próxima ação'),
        documento.proxima_acao
          ? h('div', {}, [
            linha('O que fazer', documento.proxima_acao.acao),
            linha('Tipo', rotuloTipoAcao(documento.proxima_acao.tipo)),
            documento.proxima_acao.responsavel ? linha('Responsável', documento.proxima_acao.responsavel) : null,
          ].filter(Boolean))
          : h('p', { className: 'descricao-estado' }, 'Nenhuma ação pendente — etapa concluída.'),
      ]),

      documento.ultimo_evento ? h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Último evento'),
        linha('Evento', documento.ultimo_evento.evento),
        linha('Quando', formatarDataHora(documento.ultimo_evento.timestamp)),
      ]) : null,

      h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Histórico resumido'),
        blocoHistorico(historico),
      ]),
    ]),
  ]);
}
