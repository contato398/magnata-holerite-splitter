/**
 * Integracao com o SDK "Sign in with Google" (Google Identity
 * Services) -- carrega o script oficial do Google só quando a tela de
 * login precisa dele, e devolve o id_token assinado que
 * src/api/apiAdapter.js::autenticarComIdToken envia para /auth/login
 * (ver magnata_os/autenticacao/provedor_google_oidc.py -- so o Google
 * verifica a identidade, o backend so confirma a assinatura).
 *
 * `carregarScriptGis`/`renderizarBotaoGis` sao as DUAS unicas funcoes
 * deste arquivo que tocam rede/SDK real -- ambas injetaveis em
 * components/TelaLogin.js, mesmo padrao do `verificador` injetavel em
 * provedor_google_oidc.py (testes nunca dependem do SDK real nem de
 * rede real do Google).
 */

const URL_SCRIPT_GIS = 'https://accounts.google.com/gsi/client';

/** Carrega o script do SDK (idempotente -- reaproveita um <script> ja
 * presente/carregado em vez de inserir um segundo). Resolve quando o
 * SDK esta pronto para uso; rejeita (nunca trava para sempre) se o
 * carregamento falhar. */
export function carregarScriptGis({ documento = document, janela = window } = {}) {
  return new Promise((resolve, reject) => {
    if (janela.google && janela.google.accounts && janela.google.accounts.id) {
      resolve();
      return;
    }
    const existente = documento.querySelector(`script[src="${URL_SCRIPT_GIS}"]`);
    if (existente) {
      existente.addEventListener('load', () => resolve());
      existente.addEventListener('error', () => reject(new Error('falha_ao_carregar_sdk_google')));
      return;
    }
    const script = documento.createElement('script');
    script.src = URL_SCRIPT_GIS;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('falha_ao_carregar_sdk_google'));
    documento.head.appendChild(script);
  });
}

/** Inicializa o SDK com `clientId` e renderiza o botao "Entrar com o
 * Google" dentro de `container`. `aoReceberCredencial(idToken)` e
 * chamado pelo proprio SDK quando a pessoa completa o login -- nunca
 * chamado por este modulo diretamente (o id_token so existe depois
 * que o Google confirma a identidade no proprio navegador). */
export function renderizarBotaoGis({ clientId, container, aoReceberCredencial, janela = window }) {
  janela.google.accounts.id.initialize({
    client_id: clientId,
    callback: (resposta) => aoReceberCredencial(resposta.credential),
  });
  janela.google.accounts.id.renderButton(container, { theme: 'outline', size: 'large', text: 'signin_with', shape: 'pill' });
}
