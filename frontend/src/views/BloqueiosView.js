/**
 * Fila de bloqueios (item 7 do pedido) -- documentos parados por
 * bloqueio ativo, quem precisa agir e por que.
 */
import { h, mount } from '../utils/dom.js';
import { DocumentoCard } from '../components/DocumentoCard.js';
import { Paginacao } from '../components/Paginacao.js';
import { PainelDetalheDocumento } from '../components/PainelDetalheDocumento.js';
import { estadoCarregando, estadoVazio } from '../components/EstadosUI.js';
import { renderErroApi, criarGerenciadorPainel } from './viewHelpers.js';

/** BloqueioResponse nao tem todos os campos de DocumentoEsteiraResponse (ver contratos.py) -- normaliza so o que DocumentoCard precisa. */
function bloqueioComoDocumento(b) {
  return {
    documento_id: b.documento_id,
    nome_original: b.nome_original,
    lote_id: b.lote_id,
    origem: null,
    etapa_atual: b.etapa_atual,
    situacao: 'BLOQUEADO',
    motivo_bloqueio: b.motivo_bloqueio,
    proxima_acao: b.proxima_acao,
    tempo_na_etapa_segundos: b.tempo_bloqueado_segundos,
    ultimo_evento: null,
    recebido_em: null,
    atualizado_em: null,
    rastreado_pela_esteira: true,
  };
}

export function BloqueiosView({ container, apiClient, store }) {
  const painel = criarGerenciadorPainel();
  let destruido = false;
  let paginacao = { pagina: 1, tamanho_pagina: 20 };
  const ordenacao = { campo: 'tempo_bloqueado_segundos', direcao: 'desc' };

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
          h('h1', { className: 'secao-titulo' }, 'Bloqueios'),
          h('p', { className: 'secao-subtitulo' }, 'Documentos parados por bloqueio ativo, ordenados pelos mais antigos.'),
        ]),
      ]),
      resp.itens.length
        ? h('div', { className: 'lista-cartoes' }, resp.itens.map((b) => DocumentoCard(bloqueioComoDocumento(b), { layout: 'linha', onAbrir: abrirDocumento })))
        : estadoVazio({ titulo: 'Nenhum bloqueio ativo', descricao: 'Nenhum documento está bloqueado no momento — ótimo sinal.' }),
      Paginacao(resp, { onMudarPagina: (p) => { paginacao = { ...paginacao, pagina: p }; carregar(); } }),
    ]);
    mount(container, raiz);
  }

  async function carregar() {
    mount(container, estadoCarregando({ linhas: 5 }));
    try {
      const resp = await apiClient.listarBloqueios(sujeitoAtual(), { paginacao, ordenacao });
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
