/**
 * Tela de Documentos (itens 5 e 6 do pedido): busca, filtros completos
 * e lista paginada de documentos.
 */
import { h, mount } from '../utils/dom.js';
import { Filtros } from '../components/Filtros.js';
import { DocumentoCard } from '../components/DocumentoCard.js';
import { Paginacao } from '../components/Paginacao.js';
import { PainelDetalheDocumento } from '../components/PainelDetalheDocumento.js';
import { PainelDetalheLote } from '../components/PainelDetalheLote.js';
import { estadoCarregando, estadoNenhumaOcorrencia } from '../components/EstadosUI.js';
import { converterFiltroUIParaContrato } from '../state/filtros.js';
import { renderErroApi, criarGerenciadorPainel } from './viewHelpers.js';
import { debounce } from '../utils/debounce.js';

export function DocumentosView({ container, apiClient, store, filtroInicial = {} }) {
  const painel = criarGerenciadorPainel();
  let destruido = false;
  let filtroUI = { ...filtroInicial };
  let paginacao = { pagina: 1, tamanho_pagina: 20 };
  const ordenacao = { campo: 'atualizado_em', direcao: 'desc' };
  let origensConhecidas = [];
  let lotesConhecidos = [];

  function sujeitoAtual() {
    return { perfil: store.getState().perfil };
  }

  async function abrirDocumento(documentoId) {
    const overlay = h('div');
    painel.abrir(overlay);
    mount(overlay, estadoCarregando({ linhas: 4 }));
    let documento;
    try {
      documento = await apiClient.obterDocumento(sujeitoAtual(), documentoId);
    } catch (erro) {
      renderErroApi(overlay, erro, { perfilAtual: store.getState().perfil });
      return;
    }
    let historico = { status: 'carregando' };
    const renderPainel = () => mount(overlay, PainelDetalheDocumento(documento, { historico, onFechar: painel.fechar, onAbrirLote: abrirLote }));
    renderPainel();
    try {
      const resp = await apiClient.obterHistoricoDocumento(sujeitoAtual(), documentoId);
      historico = { status: 'ok', dados: resp };
    } catch (erro) {
      historico = erro && erro.codigo === 'PERMISSAO_NEGADA'
        ? { status: 'sem-permissao', perfilAtual: store.getState().perfil }
        : { status: 'erro' };
    }
    renderPainel();
  }

  async function abrirLote(loteId) {
    const overlay = h('div');
    painel.abrir(overlay);
    mount(overlay, estadoCarregando({ linhas: 4 }));
    let lote;
    try {
      lote = await apiClient.obterLote(sujeitoAtual(), loteId);
    } catch (erro) {
      renderErroApi(overlay, erro, { perfilAtual: store.getState().perfil });
      return;
    }
    let documentosEstado = { status: 'carregando' };
    const renderPainel = () => mount(overlay, PainelDetalheLote(lote, { documentos: documentosEstado, onFechar: painel.fechar, onAbrirDocumento: abrirDocumento }));
    renderPainel();
    try {
      const resp = await apiClient.listarDocumentos(sujeitoAtual(), { filtro: { lote_id: loteId }, paginacao: { pagina: 1, tamanho_pagina: 50 } });
      documentosEstado = { status: 'ok', dados: resp.itens };
    } catch {
      documentosEstado = { status: 'ok', dados: [] };
    }
    renderPainel();
  }

  const carregarComDebounce = debounce(() => carregar(), 220);

  function aoMudarFiltro(novoFiltro) {
    filtroUI = novoFiltro;
    paginacao = { ...paginacao, pagina: 1 };
    carregarComDebounce();
  }

  function aoLimparFiltro() {
    filtroUI = {};
    paginacao = { ...paginacao, pagina: 1 };
    carregar();
  }

  function renderLista(resp) {
    const semResultado = resp.itens.length === 0;
    const raiz = h('div', { className: 'conteudo-largura-max' }, [
      h('div', { className: 'secao-cabecalho' }, [
        h('div', {}, [
          h('h1', { className: 'secao-titulo' }, 'Documentos'),
          h('p', { className: 'secao-subtitulo' }, 'Busque, filtre e abra o detalhe de qualquer documento da esteira.'),
        ]),
      ]),
      Filtros(filtroUI, { origens: origensConhecidas, lotes: lotesConhecidos, onMudar: aoMudarFiltro, onLimpar: aoLimparFiltro }),
      semResultado
        ? estadoNenhumaOcorrencia({ contexto: 'esses filtros' })
        : h('div', { className: 'lista-cartoes' }, resp.itens.map((doc) => DocumentoCard(doc, { layout: 'linha', onAbrir: abrirDocumento }))),
      Paginacao(resp, { onMudarPagina: (p) => { paginacao = { ...paginacao, pagina: p }; carregar(); } }),
    ]);
    mount(container, raiz);
  }

  async function carregar() {
    mount(container, estadoCarregando({ linhas: 5 }));
    try {
      const filtroContrato = converterFiltroUIParaContrato(filtroUI);
      const resp = await apiClient.listarDocumentos(sujeitoAtual(), { filtro: filtroContrato, paginacao, ordenacao });
      if (destruido) return;
      const novasOrigens = new Set(origensConhecidas);
      resp.itens.forEach((d) => d.origem && novasOrigens.add(d.origem));
      origensConhecidas = [...novasOrigens].sort();
      renderLista(resp);
      store.setState({ ultimaAtualizacao: new Date() });
    } catch (erro) {
      if (destruido) return;
      renderErroApi(container, erro, { perfilAtual: store.getState().perfil, onTentarNovamente: carregar });
    }
  }

  apiClient.listarLotes(sujeitoAtual(), { paginacao: { pagina: 1, tamanho_pagina: 200 } })
    .then((resp) => { lotesConhecidos = resp.itens.map((l) => l.lote_id); })
    .catch(() => {});

  carregar();
  store.setState({ atualizarViewAtual: carregar });

  return function destruir() {
    destruido = true;
    carregarComDebounce.cancelar();
    painel.fechar();
  };
}
