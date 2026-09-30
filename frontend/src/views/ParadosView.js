/**
 * Documentos parados (item 7 do pedido) -- documentos acima de um
 * tempo minimo na etapa atual, ajustavel pelo usuario.
 */
import { h, mount } from '../utils/dom.js';
import { DocumentoCard } from '../components/DocumentoCard.js';
import { Paginacao } from '../components/Paginacao.js';
import { PainelDetalheDocumento } from '../components/PainelDetalheDocumento.js';
import { estadoCarregando, estadoVazio } from '../components/EstadosUI.js';
import { renderErroApi, criarGerenciadorPainel } from './viewHelpers.js';
import { LIMITE_PARADO_PADRAO_SEGUNDOS } from '../utils/prioridade.js';

export function ParadosView({ container, apiClient, store }) {
  const painel = criarGerenciadorPainel();
  let destruido = false;
  let paginacao = { pagina: 1, tamanho_pagina: 20 };
  const ordenacao = { campo: 'entrou_na_etapa_em', direcao: 'asc' };
  let tempoMinimoHoras = LIMITE_PARADO_PADRAO_SEGUNDOS / 3600;

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
          h('h1', { className: 'secao-titulo' }, 'Documentos parados'),
          h('p', { className: 'secao-subtitulo' }, 'Documentos há mais tempo do que o esperado na mesma etapa, do mais parado para o menos.'),
        ]),
      ]),
      h('div', { className: 'barra-filtros' }, [
        h('div', { className: 'campo-filtro' }, [
          h('label', { htmlFor: 'tempo-minimo-parados' }, 'Parado há mais de (horas)'),
          h('input', {
            id: 'tempo-minimo-parados', type: 'number', min: '0', value: tempoMinimoHoras,
            onInput: (ev) => { tempoMinimoHoras = ev.target.value === '' ? 0 : Number(ev.target.value); paginacao = { ...paginacao, pagina: 1 }; carregar(); },
          }),
        ]),
      ]),
      resp.itens.length
        ? h('div', { className: 'lista-cartoes' }, resp.itens.map((doc) => DocumentoCard(doc, { layout: 'linha', onAbrir: abrirDocumento })))
        : estadoVazio({ titulo: 'Nenhum documento parado nesse período', descricao: 'Tente reduzir o tempo mínimo para ver mais resultados.' }),
      Paginacao(resp, { onMudarPagina: (p) => { paginacao = { ...paginacao, pagina: p }; carregar(); } }),
    ]);
    mount(container, raiz);
  }

  async function carregar() {
    mount(container, estadoCarregando({ linhas: 5 }));
    try {
      const tempoMinimoSegundos = Math.max(0, tempoMinimoHoras) * 3600;
      const resp = await apiClient.listarDocumentosParados(sujeitoAtual(), tempoMinimoSegundos, { paginacao, ordenacao });
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
