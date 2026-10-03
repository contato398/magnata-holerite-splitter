/**
 * Tela de Resumo (item 3 + 4 do pedido): cartoes operacionais e a
 * esteira visual completa. E a home do painel.
 */
import { h, mount } from '../utils/dom.js';
import { ResumoCards } from '../components/ResumoCards.js';
import { EsteiraBoard } from '../components/EsteiraBoard.js';
import { PainelDetalheDocumento } from '../components/PainelDetalheDocumento.js';
import { PainelDetalheLote } from '../components/PainelDetalheLote.js';
import { estadoCarregando } from '../components/EstadosUI.js';
import { renderErroApi, inicioDoDiaIso, criarGerenciadorPainel } from './viewHelpers.js';

export function DashboardView({ container, apiClient, store }) {
  const painel = criarGerenciadorPainel();
  let etapaSelecionadaMobile = null;
  let destruido = false;

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
    const renderPainel = () => mount(overlay, PainelDetalheDocumento(documento, {
      historico, onFechar: painel.fechar, onAbrirLote: abrirLote,
    }));
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
    const renderPainel = () => mount(overlay, PainelDetalheLote(lote, {
      documentos: documentosEstado, onFechar: painel.fechar, onAbrirDocumento: abrirDocumento,
    }));
    renderPainel();

    try {
      const resp = await apiClient.listarDocumentos(sujeitoAtual(), { filtro: { lote_id: loteId }, paginacao: { pagina: 1, tamanho_pagina: 50 } });
      documentosEstado = { status: 'ok', dados: resp.itens };
    } catch {
      documentosEstado = { status: 'ok', dados: [] };
    }
    renderPainel();
  }

  function renderConteudo(resumo, documentos, recebidosHoje) {
    const raiz = h('div', { className: 'conteudo-largura-max' }, [
      h('div', { className: 'secao-cabecalho' }, [
        h('div', {}, [
          h('h1', { className: 'secao-titulo' }, 'Resumo operacional'),
          h('p', { className: 'secao-subtitulo' }, 'O que chegou, o que está andando e o que precisa de atenção — em poucos segundos.'),
        ]),
      ]),
      ResumoCards(resumo, { recebidosHoje }),
      h('div', { className: 'secao-cabecalho', style: { marginTop: 'var(--espaco-6)' } }, [
        h('div', {}, [h('h2', { className: 'secao-titulo', style: { fontSize: 'var(--fonte-tamanho-lg)' } }, 'Esteira documental')]),
      ]),
      EsteiraBoard(documentos, {
        larguraViewport: window.innerWidth,
        etapaSelecionadaMobile,
        onSelecionarEtapaMobile: (etapa) => { etapaSelecionadaMobile = etapa; renderConteudo(resumo, documentos, recebidosHoje); },
        onAbrirDocumento: abrirDocumento,
      }),
    ]);
    mount(container, raiz);
  }

  async function carregar() {
    mount(container, estadoCarregando({ linhas: 6 }));
    try {
      const sujeito = sujeitoAtual();
      const [resumo, documentosResp, recebidosHojeResp] = await Promise.all([
        apiClient.obterResumoEsteira(sujeito),
        apiClient.listarDocumentos(sujeito, { paginacao: { pagina: 1, tamanho_pagina: 200 } }),
        apiClient.listarDocumentos(sujeito, { filtro: { recebido_de: inicioDoDiaIso() }, paginacao: { pagina: 1, tamanho_pagina: 1 } }),
      ]);
      if (destruido) return;
      renderConteudo(resumo, documentosResp.itens, recebidosHojeResp.total_itens);
      store.setState({ ultimaAtualizacao: new Date() });
    } catch (erro) {
      if (destruido) return;
      renderErroApi(container, erro, { perfilAtual: store.getState().perfil, onTentarNovamente: carregar });
    }
  }

  let resizeTimeout = null;
  function aoRedimensionar() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => { if (!destruido) carregar(); }, 200);
  }
  window.addEventListener('resize', aoRedimensionar);

  carregar();
  store.setState({ atualizarViewAtual: carregar });

  return function destruir() {
    destruido = true;
    window.removeEventListener('resize', aoRedimensionar);
    clearTimeout(resizeTimeout);
    painel.fechar();
  };
}
