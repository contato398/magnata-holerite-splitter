/**
 * Barra de filtros (item 6 do pedido): etapa, situacao, origem, lote,
 * bloqueado, acao humana, periodo (recebido de/ate), tempo minimo
 * parado, busca por nome. Componente controlado -- nunca guarda estado
 * proprio, so chama `onMudar(novosValores)` a cada alteracao; quem
 * decide o que fazer com o valor (persistir na store, disparar nova
 * consulta) e a view.
 */
import { h } from '../utils/dom.js';
import { EtapaEsteira, SituacaoEsteira } from '../api/contracts.js';
import { rotuloEtapa, rotuloSituacao } from '../utils/format.js';

function opcaoVazia(texto) {
  return h('option', { value: '' }, texto);
}

/**
 * @param {Object} valores filtro atual (mesmas chaves de FiltroDocumentos, mais `busca`)
 * @param {{origens?: string[], lotes?: string[], onMudar: (valores:Object)=>void, onLimpar: ()=>void}} opcoes
 */
export function Filtros(valores, opcoes) {
  const { origens = [], lotes = [], onMudar, onLimpar } = opcoes;

  function emitir(campo, valor) {
    onMudar({ ...valores, [campo]: valor === '' ? null : valor });
  }

  const campoSelect = (campo, rotulo, opcoesLista) => h('div', { className: 'campo-filtro' }, [
    h('label', { htmlFor: `filtro-${campo}` }, rotulo),
    h('select', {
      id: `filtro-${campo}`,
      value: valores[campo] || '',
      onChange: (ev) => emitir(campo, ev.target.value),
    }, [opcaoVazia('Todas'), ...opcoesLista]),
  ]);

  return h('div', { className: 'barra-filtros', role: 'search', 'aria-label': 'Filtros de documentos' }, [
    h('div', { className: 'campo-filtro campo-busca' }, [
      h('label', { htmlFor: 'filtro-busca' }, 'Buscar por nome'),
      h('input', {
        id: 'filtro-busca', type: 'search', placeholder: 'Nome do arquivo ou ID do documento…',
        value: valores.busca || '',
        onInput: (ev) => emitir('busca', ev.target.value),
      }),
    ]),

    campoSelect('etapa', 'Etapa', Object.values(EtapaEsteira).map((e) => h('option', { value: e, selected: valores.etapa === e }, rotuloEtapa(e)))),
    campoSelect('situacao', 'Situação', Object.values(SituacaoEsteira).map((s) => h('option', { value: s, selected: valores.situacao === s }, rotuloSituacao(s)))),
    campoSelect('origem', 'Origem', origens.map((o) => h('option', { value: o, selected: valores.origem === o }, o))),
    campoSelect('lote_id', 'Lote', lotes.map((l) => h('option', { value: l, selected: valores.lote_id === l }, l))),

    h('div', { className: 'campo-filtro-checkbox' }, [
      h('input', {
        type: 'checkbox', id: 'filtro-bloqueado', checked: valores.bloqueado === true,
        onChange: (ev) => emitir('bloqueado', ev.target.checked ? true : null),
      }),
      h('label', { htmlFor: 'filtro-bloqueado' }, 'Só bloqueados'),
    ]),
    h('div', { className: 'campo-filtro-checkbox' }, [
      h('input', {
        type: 'checkbox', id: 'filtro-acao-humana', checked: valores.acao_humana === true,
        onChange: (ev) => emitir('acao_humana', ev.target.checked ? true : null),
      }),
      h('label', { htmlFor: 'filtro-acao-humana' }, 'Só ação humana'),
    ]),

    h('div', { className: 'campo-filtro' }, [
      h('label', { htmlFor: 'filtro-recebido-de' }, 'Recebido de'),
      h('input', { id: 'filtro-recebido-de', type: 'date', value: valores.recebido_de_data || '', onInput: (ev) => emitir('recebido_de_data', ev.target.value) }),
    ]),
    h('div', { className: 'campo-filtro' }, [
      h('label', { htmlFor: 'filtro-recebido-ate' }, 'Recebido até'),
      h('input', { id: 'filtro-recebido-ate', type: 'date', value: valores.recebido_ate_data || '', onInput: (ev) => emitir('recebido_ate_data', ev.target.value) }),
    ]),
    h('div', { className: 'campo-filtro' }, [
      h('label', { htmlFor: 'filtro-tempo-parado' }, 'Parado há mais de (horas)'),
      h('input', {
        id: 'filtro-tempo-parado', type: 'number', min: '0', placeholder: 'Ex.: 24',
        value: valores.tempo_minimo_parado_horas || '',
        onInput: (ev) => emitir('tempo_minimo_parado_horas', ev.target.value === '' ? '' : Number(ev.target.value)),
      }),
    ]),

    h('button', { className: 'filtros-acao-limpar', onClick: onLimpar, type: 'button' }, 'Limpar filtros'),
  ]);
}
