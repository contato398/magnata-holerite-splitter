/**
 * Fila de acoes humanas (item 7 do pedido) -- documentos cuja proxima
 * acao exige uma pessoa, nao automacao.
 */
import { h, mount } from '../utils/dom.js';
import { DocumentoCard } from '../components/DocumentoCard.js';
import { Paginacao } from '../components/Paginacao.js';
import { PainelDetalheDocumento } from '../components/PainelDetalheDocumento.js';
import { estadoCarregando, estadoVazio } from '../components/EstadosUI.js';
import { renderErroApi, criarGerenciadorPainel } from './viewHelpers.js';

export function AcoesHumanasView({ container, apiClient, store }) {
  const painel = criarGerenciadorPainel();
  let destruido = false;
  let paginacao = { pagina: 1, tamanho_pagina: 20 };
  const ordenacao = { campo: 'atualizado_em', direcao: 'desc' };

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
    const renderPainel = () => mount(overlay, PainelDetalheDocumento(documento, { historico, onFechar: painel.fechar }));
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

  function renderLista(resp) {
    const raiz = h('div', { className: 'conteudo-largura-max' }, [
      h('div', { className: 'secao-cabecalho' }, [
        h('div', {}, [
          h('h1', { className: 'secao-titulo' }, 'Ações humanas'),
          h('p', { className: 'secao-subtitulo' }, 'Documentos que precisam de alguém da equipe para seguir em frente.'),
        ]),
      ]),
      resp.itens.length
        ? h('div', { className: 'lista-cartoes' }, resp.itens.map((doc) => DocumentoCard(doc, { layout: 'linha', onAbrir: abrirDocumento })))
        : estadoVazio({ titulo: 'Nenhuma ação humana pendente', descricao: 'Nenhum documento está esperando por você agora.' }),
      Paginacao(resp, { onMudarPagina: (p) => { paginacao = { ...paginacao, pagina: p }; carregar(); } }),
    ]);
    mount(container, raiz);
  }

  async function carregar() {
    mount(container, estadoCarregando({ linhas: 5 }));
    try {
      const resp = await apiClient.listarAcoesHumanas(sujeitoAtual(), { paginacao, ordenacao });
      if (destruido) return;
      renderLista(resp);
      store.setState({ ultimaAtualizacao: new Date() });
    } catch (erro) {
      if (destruido) return;
      renderErroApi(container, erro, { perfilAtual: store.getState().perfil, onTentarNovamente: carregar });
    }
  }

  carregar();
  store.setState({ atualizarViewAtual: carregar });

  return function destruir() {
    destruido = true;
    painel.fechar();
  };
}
