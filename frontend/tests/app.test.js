/**
 * Testes de bootstrap do painel (app.js, Fase 5 -- "login real"):
 * sem sessão mostra a tela de login de verdade (TelaLogin.js) e, só
 * depois de um login bem-sucedido, monta o painel com o perfil/e-mail
 * vindos da sessão -- nunca antes disso.
 *
 * `window.fetch` é substituído por um duplo controlado (mesmo padrão
 * de apiAdapter.test.js). `window.google` também é substituído por um
 * duplo mínimo do SDK do Google Identity Services -- como o duplo já
 * expõe `google.accounts.id`, `carregarScriptGis` (real, não
 * injetado aqui de propósito -- é o próprio app.js quem monta a
 * TelaLogin real) nunca insere um <script> nem toca rede real (ver
 * src/auth/googleIdentity.js).
 */
import { describe, it, assertEqual, assertTrue } from './test-harness.js';
import { iniciarApp } from '../src/app.js';

function instalarAmbienteFalso({ autenticadoEm401 = false } = {}) {
  const original = {
    fetch: window.fetch, google: window.google, config: window.MAGNATA_CONFIG,
  };

  let credencialCallback = null;
  const chamadasFetch = [];

  window.MAGNATA_CONFIG = { GOOGLE_OAUTH_CLIENT_ID: 'client-id-de-teste' };
  window.google = {
    accounts: {
      id: {
        initialize: ({ callback }) => { credencialCallback = callback; },
        renderButton: () => {},
      },
    },
  };
  window.fetch = async (url, opcoes) => {
    const urlTexto = String(url);
    chamadasFetch.push({ url: urlTexto, opcoes });
    if (urlTexto.startsWith('/auth/me')) {
      return { ok: true, status: 200, json: async () => ({ autenticado: false }) };
    }
    if (urlTexto.startsWith('/auth/login')) {
      if (autenticadoEm401) {
        return { ok: false, status: 403, json: async () => ({ erro: 'nao_autorizado' }) };
      }
      return {
        ok: true, status: 200,
        json: async () => ({ email: 'gestor.teste@exemplo.com', perfil: 'GESTOR', csrf_token: 'exemplo' }),
      };
    }
    throw new Error(`chamada inesperada a fetch: ${urlTexto}`);
  };

  return {
    chamadasFetch,
    dispararCredencial: (idToken) => credencialCallback && credencialCallback({ credential: idToken }),
    restaurar: () => {
      window.fetch = original.fetch;
      window.google = original.google;
      window.MAGNATA_CONFIG = original.config;
    },
  };
}

async function aguardarMicrotasks(vezes = 3) {
  for (let i = 0; i < vezes; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('app.js -- bootstrap sem sessão, login real', () => {
  it('sem sessão, mostra a tela de login (não o painel)', async () => {
    const raiz = document.createElement('div');
    document.body.appendChild(raiz);
    const ambiente = instalarAmbienteFalso();
    try {
      iniciarApp(raiz); // promessa só resolve depois do login -- nao aguardamos aqui
      await aguardarMicrotasks();
      assertTrue(raiz.textContent.includes('Entrar no Magnata OS'));
      assertTrue(raiz.querySelector('#app-shell') === null, 'painel nao deveria estar montado antes do login');
    } finally {
      ambiente.restaurar();
      raiz.remove();
    }
  });

  it('login bem-sucedido: resolve iniciarApp com o store do painel, perfil/e-mail vindos da sessão', async () => {
    const raiz = document.createElement('div');
    document.body.appendChild(raiz);
    const ambiente = instalarAmbienteFalso();
    try {
      const promessaApp = iniciarApp(raiz);
      await aguardarMicrotasks();
      assertTrue(raiz.textContent.includes('Entrar no Magnata OS'));

      ambiente.dispararCredencial('id-token-sintetico');
      const store = await promessaApp;

      assertTrue(store !== null && store !== undefined, 'iniciarApp deveria resolver com o store do painel');
      assertEqual(store.getState().perfil, 'GESTOR');
      assertTrue(raiz.querySelector('#app-shell') !== null, 'painel deveria estar montado apos o login');
      assertTrue(raiz.textContent.includes('gestor.teste@exemplo.com'), 'cabecalho deveria mostrar o e-mail autenticado');
    } finally {
      ambiente.restaurar();
      raiz.remove();
    }
  });

  it('login recusado pelo backend: continua na tela de login com a mensagem certa, nunca monta o painel', async () => {
    const raiz = document.createElement('div');
    document.body.appendChild(raiz);
    const ambiente = instalarAmbienteFalso({ autenticadoEm401: true });
    try {
      iniciarApp(raiz);
      await aguardarMicrotasks();
      ambiente.dispararCredencial('id-token-nao-autorizado');
      await aguardarMicrotasks();

      assertTrue(raiz.textContent.includes('não está autorizada'), `mensagem inesperada: ${raiz.textContent}`);
      assertTrue(raiz.querySelector('#app-shell') === null, 'painel nunca deveria montar apos login recusado');
    } finally {
      ambiente.restaurar();
      raiz.remove();
    }
  });

  it('sem GOOGLE_OAUTH_CLIENT_ID configurado, mostra o erro estrutural (nunca finge sessão autenticada)', async () => {
    const raiz = document.createElement('div');
    document.body.appendChild(raiz);
    const ambiente = instalarAmbienteFalso();
    window.MAGNATA_CONFIG = undefined; // simula ambiente sem a variavel de configuracao
    try {
      iniciarApp(raiz);
      await aguardarMicrotasks();
      assertTrue(raiz.textContent.includes('Login indisponível'), `mensagem inesperada: ${raiz.textContent}`);
      assertTrue(raiz.querySelector('#app-shell') === null);
    } finally {
      ambiente.restaurar();
      raiz.remove();
    }
  });
});
