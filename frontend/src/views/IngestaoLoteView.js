/**
 * Tela de Ingestão de Documentos em Lote (painel operacional --
 * elimina a dependência de Shell/terminal para rodar
 * `scripts/ingerir_documentos_lote_real_cli.py`, decisão de produto já
 * tomada desde o início da automação). Formulário simples (cliente +
 * competência) + botão "Ingerir documentos"; ao clicar, chama
 * `apiClient.ingerirDocumentosLote` (POST real via apiAdapter.js, ou
 * simulado via mockAdapter.js em `?mock=1`) e mostra um resumo
 * legível, nunca JSON cru.
 *
 * Limitação declarada (V1, ver
 * docs/decisoes/painel-ingestao-documentos-lote-ui-v1.md): o campo
 * "cliente" é o id bruto do registro Airtable (texto livre, ex.:
 * `recXXXXXXXXXXXXXX`) -- um seletor com nome do cliente é melhoria
 * futura, não bloqueia esta entrega. A chamada é SÍNCRONA: o botão
 * fica desabilitado com um indicador de carregamento até a resposta
 * voltar, o que pode demorar para lotes grandes.
 */
import { h, mount } from '../utils/dom.js';
import { estadoCarregando } from '../components/EstadosUI.js';
import { renderErroApi } from './viewHelpers.js';

function sujeitoAtual(store) {
  return { perfil: store.getState().perfil };
}

function campoTexto({ id, rotulo, tipo = 'text', valor, placeholder, onInput, ajuda }) {
  return h('div', { className: 'campo-filtro' }, [
    h('label', { htmlFor: id }, rotulo),
    h('input', {
      id, type: tipo, value: valor, placeholder,
      onInput: (ev) => onInput(ev.target.value),
    }),
    ajuda ? h('p', { className: 'descricao-estado', style: { margin: '4px 0 0' } }, ajuda) : null,
  ]);
}

function cartaoResumo(resumo) {
  const linhas = [
    { rotulo: 'Anexos encontrados', valor: resumo.anexos_encontrados },
    { rotulo: 'Documentos ingeridos', valor: resumo.documentos_ingeridos },
    { rotulo: 'Já existiam (idempotente)', valor: resumo.documentos_ja_existentes },
    { rotulo: 'Registros sem anexo', valor: (resumo.registros_sem_anexo || []).length },
    { rotulo: 'Falhas', valor: resumo.total_falhas || 0, destaque: (resumo.total_falhas || 0) > 0 },
  ];

  const falhas = resumo.falhas || [];

  return h('div', { className: 'conteudo-largura-max', 'aria-live': 'polite' }, [
    h('div', { className: 'grade-resumo', role: 'list', 'aria-label': 'Resumo da ingestão' },
      linhas.map((l) => h('div', {
        className: ['cartao-resumo', l.destaque ? 'destaque-erro' : ''].filter(Boolean).join(' '),
        role: 'listitem',
      }, [
        h('span', { className: 'valor' }, String(l.valor)),
        h('span', { className: 'rotulo' }, l.rotulo),
      ]))),
    falhas.length > 0 ? h('div', { className: 'lista-cartoes', style: { marginTop: '16px' } }, [
      h('h2', { className: 'secao-subtitulo' }, 'Falhas por anexo'),
      ...falhas.map((f) => h('div', { className: 'cartao-resumo' }, [
        h('span', { className: 'rotulo' }, `${f.tabela} · registro ${f.registro_airtable_id} · anexo #${f.indice_anexo}`),
        h('span', { className: 'descricao-estado' }, f.motivo),
      ])),
    ]) : null,
  ]);
}

/**
 * @param {{container: HTMLElement, apiClient: object, store: object}} opcoes
 */
export function IngestaoLoteView({ container, apiClient, store }) {
  let destruido = false;
  let clienteId = '';
  let competenciaBase = '';
  let enviando = false;
  let resumo = null;
  let erro = null;

  function render() {
    if (destruido) return;

    const corpo = [
      h('div', { className: 'secao-cabecalho' }, [
        h('div', {}, [
          h('h1', { className: 'secao-titulo' }, 'Ingestão de documentos'),
          h('p', { className: 'secao-subtitulo' },
            'Importa, de um cliente e uma competência, todo documento (Holerites, Extratos Mensais, FGTS Digital) que ainda não tem conteúdo real no armazenamento -- a mesma ingestão que antes só rodava por linha de comando.'),
        ]),
      ]),
      h('form', {
        className: 'barra-filtros',
        role: 'form',
        'aria-label': 'Ingerir documentos de um cliente/competência',
        onSubmit: (ev) => { ev.preventDefault(); aoEnviar(); },
      }, [
        campoTexto({
          id: 'ingestao-cliente',
          rotulo: 'Cliente (id do registro Airtable)',
          valor: clienteId,
          placeholder: 'recXXXXXXXXXXXXXX',
          ajuda: 'Seletor com nome do cliente é melhoria futura -- por ora, cole o id do registro Airtable (campo "recXXXX...").',
          onInput: (v) => { clienteId = v; },
        }),
        campoTexto({
          id: 'ingestao-competencia',
          rotulo: 'Competência',
          tipo: 'month',
          valor: competenciaBase,
          onInput: (v) => { competenciaBase = v; },
        }),
        h('div', { className: 'campo-filtro' }, [
          h('button', {
            type: 'submit',
            className: 'btn btn-primario',
            disabled: enviando || !clienteId.trim() || !competenciaBase,
            'aria-busy': enviando ? 'true' : 'false',
          }, enviando ? 'Ingerindo…' : 'Ingerir documentos'),
        ]),
      ]),
    ];

    if (enviando) {
      corpo.push(estadoCarregando({ linhas: 2 }));
    } else if (erro) {
      const areaErro = h('div');
      corpo.push(areaErro);
      mount(container, h('div', { className: 'conteudo-largura-max' }, corpo));
      renderErroApi(areaErro, erro, { perfilAtual: store.getState().perfil, onTentarNovamente: aoEnviar });
      return;
    } else if (resumo) {
      corpo.push(cartaoResumo(resumo));
    }

    mount(container, h('div', { className: 'conteudo-largura-max' }, corpo));
  }

  async function aoEnviar() {
    if (enviando || !clienteId.trim() || !competenciaBase) return;
    enviando = true;
    erro = null;
    resumo = null;
    render();
    try {
      const resposta = await apiClient.ingerirDocumentosLote(sujeitoAtual(store), {
        clienteId: clienteId.trim(),
        competenciaBase,
      });
      if (destruido) return;
      resumo = resposta;
      store.setState({ ultimaAtualizacao: new Date() });
    } catch (excecao) {
      if (destruido) return;
      erro = excecao;
    } finally {
      if (!destruido) {
        enviando = false;
        render();
      }
    }
  }

  render();

  return function destruir() {
    destruido = true;
  };
}
