/**
 * Bootstrap do painel (Modulo 01, Fase 5) -- monta o shell (sidebar +
 * cabecalho + navegacao mobile) e um roteador minimo baseado em hash
 * (sem biblioteca de rotas). Cada view em views/*.js e responsavel por
 * si mesma: recebe o container e o apiClient, cuida do proprio
 * carregamento/erro/paginacao, e devolve uma funcao de limpeza chamada
 * antes de trocar de tela.
 */
import { h, mount, qs } from './utils/dom.js';
import { createStore } from './state/store.js';
import { mockApiClient } from './api/mockAdapter.js';
import { apiClient as apiClientReal, verificarSessaoAtual } from './api/apiAdapter.js';
import { Perfil } from './api/autorizacao.js';
import { ROTAS, rotaPorId } from './nav.js';
import { Sidebar, NavMobile } from './components/Sidebar.js';
import { Header } from './components/Header.js';
import { TelaLogin } from './components/TelaLogin.js';
import { tempoRelativoDeIso } from './utils/format.js';

/**
 * Painel roda contra a API real por padrao. `?mock=1` na URL liga o
 * modo demonstracao (mockAdapter.js + mockData.js) -- SEM sessao real,
 * SEM autenticacao real, so para desenvolvimento local do proprio
 * painel sem o servidor da API rodando (ver docs/decisoes/
 * painel-fase5-dados-reais-v1.md, "o que continua mockado").
 */
function modoMockAtivo() {
  try {
    return new URLSearchParams(location.search).get('mock') === '1';
  } catch (excecao) {
    return false;
  }
}

import { DashboardView } from './views/DashboardView.js';
import { DocumentosView } from './views/DocumentosView.js';
import { BloqueiosView } from './views/BloqueiosView.js';
import { AcoesHumanasView } from './views/AcoesHumanasView.js';
import { ParadosView } from './views/ParadosView.js';
import { IngestaoLoteView } from './views/IngestaoLoteView.js';

const VIEWS = {
  resumo: DashboardView,
  documentos: DocumentosView,
  bloqueios: BloqueiosView,
  'acoes-humanas': AcoesHumanasView,
  parados: ParadosView,
  'ingestao-lote': IngestaoLoteView,
};

/**
 * `apiClient`/`perfilInicial`/`perfilEditavel`/`emailAutenticado`
 * continuam injetaveis explicitamente (usado por testes e pelo modo
 * `?mock=1`) -- quando omitidos, `iniciarApp` decide sozinho: checa
 * `/auth/me` (verificarSessaoAtual) e usa a API real se houver sessao
 * valida, ou mostra a tela de login (TelaLogin.js) se nao houver.
 * Sem sessao, devolve uma Promise que so resolve (com o `store`) depois
 * que a pessoa completa o login com sucesso -- nunca monta o painel
 * antes disso.
 */
export async function iniciarApp(raiz, opcoes = {}) {
  let { apiClient, perfilInicial, perfilEditavel, emailAutenticado = null } = opcoes;

  if (apiClient === undefined) {
    if (modoMockAtivo()) {
      apiClient = mockApiClient;
      perfilInicial = perfilInicial ?? Perfil.GESTOR;
      perfilEditavel = perfilEditavel ?? true;
    } else {
      const sessao = await verificarSessaoAtual();
      if (!sessao.autenticado) {
        return new Promise((resolve) => {
          TelaLogin({
            raiz,
            aoAutenticar: (sessaoLogin) => {
              resolve(montarPainel(raiz, {
                apiClient: apiClientReal,
                perfilInicial: sessaoLogin.perfil,
                perfilEditavel: false,
                emailAutenticado: sessaoLogin.email || null,
              }));
            },
          });
        });
      }
      apiClient = apiClientReal;
      perfilInicial = sessao.perfil;
      perfilEditavel = false;
      emailAutenticado = sessao.email || null;
    }
  } else {
    perfilInicial = perfilInicial ?? Perfil.GESTOR;
    perfilEditavel = perfilEditavel ?? true;
  }

  return montarPainel(raiz, { apiClient, perfilInicial, perfilEditavel, emailAutenticado });
}

function montarPainel(raiz, { apiClient, perfilInicial, perfilEditavel, emailAutenticado }) {
  const store = createStore({
    perfil: perfilInicial,
    rotaId: idDaRota(location.hash) || 'resumo',
    ultimaAtualizacao: null,
    atualizando: false,
    atualizarViewAtual: null,
  });

  let destruirViewAtual = null;

  mount(raiz, h('div', { id: 'app-shell' }, [
    h('div', { id: 'slot-sidebar' }),
    h('div', { id: 'slot-header' }),
    h('div', { id: 'slot-nav-mobile' }),
    h('main', { id: 'app-main', className: 'app-main' }),
  ]));

  function renderShell() {
    const { rotaId, perfil, atualizando, ultimaAtualizacao } = store.getState();
    mount(qs('#slot-sidebar', raiz), Sidebar({ rotaAtualId: rotaId }));
    mount(qs('#slot-nav-mobile', raiz), NavMobile({ rotaAtualId: rotaId }));
    mount(qs('#slot-header', raiz), Header({
      tituloPagina: rotaPorId(rotaId).titulo,
      perfilAtual: perfil,
      atualizando,
      textoUltimaAtualizacao: ultimaAtualizacao ? `Atualizado ${tempoRelativoDeIso(ultimaAtualizacao.toISOString())}` : '',
      onAtualizar: aoClicarAtualizar,
      onMudarPerfil: perfilEditavel ? aoMudarPerfil : null,
      perfilEditavel,
      emailAutenticado,
    }));
  }

  async function aoClicarAtualizar() {
    const fn = store.getState().atualizarViewAtual;
    if (!fn) return;
    store.setState({ atualizando: true });
    try {
      await fn();
    } finally {
      store.setState({ atualizando: false });
    }
  }

  function aoMudarPerfil(novoPerfil) {
    store.setState({ perfil: novoPerfil });
    montarViewAtual(); // perfis diferentes tem acesso a telas diferentes -- recarrega do zero
  }

  function montarViewAtual() {
    if (destruirViewAtual) {
      destruirViewAtual();
      destruirViewAtual = null;
    }
    const { rotaId } = store.getState();
    const ViewFn = VIEWS[rotaId] || VIEWS.resumo;
    const container = qs('#app-main', raiz);
    destruirViewAtual = ViewFn({ container, apiClient, store }) || null;
    renderShell();
  }

  store.subscribe(() => renderShell());

  window.addEventListener('hashchange', () => {
    const novaRota = idDaRota(location.hash) || 'resumo';
    if (novaRota !== store.getState().rotaId) {
      store.setState({ rotaId: novaRota });
      montarViewAtual();
    }
  });

  // mantem o "atualizado ha X" vivo sem precisar de nova consulta
  setInterval(() => renderShell(), 30000);

  renderShell();
  montarViewAtual();

  return store;
}

function idDaRota(hash) {
  const encontrada = ROTAS.find((r) => r.rota === hash);
  return encontrada ? encontrada.id : null;
}
