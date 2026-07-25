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
import { Perfil } from './api/autorizacao.js';
import { ROTAS, rotaPorId } from './nav.js';
import { Sidebar, NavMobile } from './components/Sidebar.js';
import { Header } from './components/Header.js';
import { tempoRelativoDeIso } from './utils/format.js';

import { DashboardView } from './views/DashboardView.js';
import { DocumentosView } from './views/DocumentosView.js';
import { BloqueiosView } from './views/BloqueiosView.js';
import { AcoesHumanasView } from './views/AcoesHumanasView.js';
import { ParadosView } from './views/ParadosView.js';

const VIEWS = {
  resumo: DashboardView,
  documentos: DocumentosView,
  bloqueios: BloqueiosView,
  'acoes-humanas': AcoesHumanasView,
  parados: ParadosView,
};

export function iniciarApp(raiz, { apiClient = mockApiClient } = {}) {
  const store = createStore({
    perfil: Perfil.GESTOR,
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
      onMudarPerfil: aoMudarPerfil,
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
