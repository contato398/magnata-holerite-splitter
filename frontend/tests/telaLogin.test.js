/**
 * Testes da tela de login real (TelaLogin.js, Fase 5 -- "login real").
 * Toda integracao com SDK/rede do Google e injetada (`carregarGis`/
 * `renderizarBotao`) e a chamada ao backend tambem (`autenticar`) --
 * nenhum teste aqui depende de rede real nem do SDK real do Google,
 * mesmo padrao de `verificador` injetavel em provedor_google_oidc.py.
 */
import { describe, it, assertEqual, assertTrue, assertFalse } from './test-harness.js';
import { TelaLogin } from '../src/components/TelaLogin.js';
import { ErroLogin } from '../src/api/apiAdapter.js';

function montarRaiz() {
  const raiz = document.createElement('div');
  document.body.appendChild(raiz);
  return raiz;
}

function comConfiguracao(clientId, fn) {
  const original = window.MAGNATA_CONFIG;
  window.MAGNATA_CONFIG = clientId ? { GOOGLE_OAUTH_CLIENT_ID: clientId } : undefined;
  try {
    return fn();
  } finally {
    window.MAGNATA_CONFIG = original;
  }
}

describe('components/TelaLogin.js -- renderização básica', () => {
  it('renderiza título, texto explicativo e o container do botão do Google', async () => {
    const raiz = montarRaiz();
    try {
      await comConfiguracao('client-id-teste', () => new Promise((resolve) => {
        TelaLogin({
          raiz,
          aoAutenticar: () => {},
          carregarGis: async () => {},
          renderizarBotao: () => resolve(),
        });
      }));
      assertTrue(raiz.textContent.includes('Entrar no Magnata OS'));
      assertTrue(raiz.querySelector('#gis-botao-login') !== null);
      assertTrue(raiz.querySelector('img.header-logo-horizontal') !== null);
    } finally {
      raiz.remove();
    }
  });

  it('chama carregarGis + renderizarBotao com o clientId configurado', async () => {
    const raiz = montarRaiz();
    let chamadaClientId = null;
    try {
      await comConfiguracao('client-id-xyz', () => new Promise((resolve) => {
        TelaLogin({
          raiz,
          aoAutenticar: () => {},
          carregarGis: async () => {},
          renderizarBotao: ({ clientId }) => { chamadaClientId = clientId; resolve(); },
        });
      }));
      assertEqual(chamadaClientId, 'client-id-xyz');
    } finally {
      raiz.remove();
    }
  });
});

describe('components/TelaLogin.js -- configuração ausente', () => {
  it('sem GOOGLE_OAUTH_CLIENT_ID configurado, mostra erro estrutural e nunca chama carregarGis/aoAutenticar', () => {
    const raiz = montarRaiz();
    let carregarGisChamado = false;
    let aoAutenticarChamado = false;
    try {
      comConfiguracao(null, () => {
        TelaLogin({
          raiz,
          aoAutenticar: () => { aoAutenticarChamado = true; },
          carregarGis: async () => { carregarGisChamado = true; },
          renderizarBotao: () => {},
        });
      });
      assertTrue(raiz.textContent.includes('Login indisponível'), 'deveria mostrar a mensagem de configuração ausente');
      assertTrue(raiz.textContent.includes('GOOGLE_OAUTH_CLIENT_ID'));
      assertFalse(carregarGisChamado, 'nao deveria tentar carregar o SDK do Google sem client id');
      assertFalse(aoAutenticarChamado, 'nao deveria autenticar sem configuração');
    } finally {
      raiz.remove();
    }
  });
});

describe('components/TelaLogin.js -- submissão de credencial', () => {
  it('credencial válida: chama o backend, e em sucesso repassa a sessão para aoAutenticar', async () => {
    const raiz = montarRaiz();
    const sessaoEsperada = { autenticado: true, email: 'gestor@exemplo.com', perfil: 'GESTOR', csrfToken: 'exemplo' };
    let sessaoRecebida = null;
    let idTokenEnviado = null;

    await comConfiguracao('client-id-teste', () => new Promise((resolve) => {
      TelaLogin({
        raiz,
        aoAutenticar: (sessao) => { sessaoRecebida = sessao; resolve(); },
        carregarGis: async () => {},
        renderizarBotao: ({ aoReceberCredencial }) => {
          // simula o SDK real do Google entregando a credencial assim que o botao "renderiza"
          aoReceberCredencial('id-token-sintetico-de-teste');
        },
        autenticar: async (idToken) => { idTokenEnviado = idToken; return sessaoEsperada; },
      });
    }));

    assertEqual(idTokenEnviado, 'id-token-sintetico-de-teste');
    assertEqual(sessaoRecebida, sessaoEsperada);
    raiz.remove();
  });

  it('backend recusa (conta fora da allowlist): mostra a mensagem certa, nunca chama aoAutenticar', async () => {
    const raiz = montarRaiz();
    let aoAutenticarChamado = false;

    await comConfiguracao('client-id-teste', () => new Promise((resolve) => {
      TelaLogin({
        raiz,
        aoAutenticar: () => { aoAutenticarChamado = true; },
        carregarGis: async () => {},
        renderizarBotao: ({ aoReceberCredencial }) => { aoReceberCredencial('id-token-nao-autorizado').then(resolve); },
        autenticar: async () => { throw new ErroLogin('nao_autorizado', 403); },
      });
    }));

    assertTrue(raiz.textContent.includes('não está autorizada'), `mensagem inesperada: ${raiz.textContent}`);
    assertFalse(aoAutenticarChamado);
    raiz.remove();
  });

  it('identidade inválida (401): mostra mensagem específica de identidade', async () => {
    const raiz = montarRaiz();
    await comConfiguracao('client-id-teste', () => new Promise((resolve) => {
      TelaLogin({
        raiz,
        aoAutenticar: () => {},
        carregarGis: async () => {},
        renderizarBotao: ({ aoReceberCredencial }) => { aoReceberCredencial('token-invalido').then(resolve); },
        autenticar: async () => { throw new ErroLogin('identidade_invalida', 401); },
      });
    }));
    assertTrue(raiz.textContent.includes('validar sua identidade'), `mensagem inesperada: ${raiz.textContent}`);
    raiz.remove();
  });

  it('provedor indisponível (503): mostra mensagem de configuração ausente no backend', async () => {
    const raiz = montarRaiz();
    await comConfiguracao('client-id-teste', () => new Promise((resolve) => {
      TelaLogin({
        raiz,
        aoAutenticar: () => {},
        carregarGis: async () => {},
        renderizarBotao: ({ aoReceberCredencial }) => { aoReceberCredencial('token-qualquer').then(resolve); },
        autenticar: async () => { throw new ErroLogin('provedor_indisponivel', 503); },
      });
    }));
    assertTrue(raiz.textContent.includes('provedor de identidade não está configurado'), `mensagem inesperada: ${raiz.textContent}`);
    raiz.remove();
  });

  it('falha ao carregar o script do Google: mostra mensagem de indisponibilidade, nunca quebra', async () => {
    const raiz = montarRaiz();
    await comConfiguracao('client-id-teste', () => new Promise((resolve) => {
      TelaLogin({
        raiz,
        aoAutenticar: () => {},
        carregarGis: async () => { throw new Error('rede indisponivel'); },
        renderizarBotao: () => {},
      });
      setTimeout(resolve, 0);
    }));
    assertTrue(raiz.textContent.includes('Não foi possível carregar o login do Google'), `mensagem inesperada: ${raiz.textContent}`);
    raiz.remove();
  });
});
