/**
 * Tela de login real do painel (Fase 5 -- login com sessao real,
 * substitui a tela minima "sessao ausente"). Usa exatamente o
 * mecanismo ja existente no backend (auth_bp -- Google Identity
 * Services + POST /auth/login com {id_token}), nunca inventa um
 * sistema de autenticacao novo.
 *
 * Todo acesso a rede/SDK e injetavel (`carregarGis`/`renderizarBotao`/
 * `autenticar`) -- mesmo padrao de dependencia injetavel do resto do
 * codebase (ver `verificador` em provedor_google_oidc.py) -- para que
 * os testes nunca dependam de rede real nem do SDK real do Google.
 *
 * Sem `GOOGLE_OAUTH_CLIENT_ID` configurado neste ambiente
 * (src/config.js -- variavel publica, nunca segredo), a tela renderiza
 * normalmente e mostra o estado estrutural "login indisponivel", nunca
 * finge estar autenticada nem quebra (item 4 do pedido).
 */
import { h, mount } from '../utils/dom.js';
import { estadoErro, estadoCarregando } from './EstadosUI.js';
import { obterConfiguracao } from '../config.js';
import { autenticarComIdToken } from '../api/apiAdapter.js';
import { carregarScriptGis, renderizarBotaoGis } from '../auth/googleIdentity.js';

function mensagemDeErroLogin(erro) {
  if (erro && erro.name === 'ErroLogin') {
    switch (erro.codigoErro) {
      case 'nao_autorizado':
        return 'Sua conta Google não está autorizada a acessar o Magnata OS. Fale com o time responsável pela allowlist administrativa.';
      case 'identidade_invalida':
        return 'Não foi possível validar sua identidade com o Google. Tente entrar novamente.';
      case 'provedor_indisponivel':
        return 'Login indisponível: o provedor de identidade não está configurado neste ambiente.';
      case 'id_token_ausente':
        return 'Não recebemos uma credencial válida do Google. Tente entrar novamente.';
      default:
        return 'Não foi possível entrar agora. Tente novamente em instantes.';
    }
  }
  return 'Não foi possível entrar agora. Tente novamente em instantes.';
}

/**
 * @param {{raiz: HTMLElement, aoAutenticar: (sessao: object) => void,
 *   carregarGis?: Function, renderizarBotao?: Function, autenticar?: Function}} opcoes
 */
export function TelaLogin({
  raiz,
  aoAutenticar,
  carregarGis = carregarScriptGis,
  renderizarBotao = renderizarBotaoGis,
  autenticar = autenticarComIdToken,
}) {
  const { googleClientId } = obterConfiguracao();

  const containerBotao = h('div', { id: 'gis-botao-login', className: 'gis-botao-login' });
  const areaEstado = h('div', { id: 'area-estado-login', 'aria-live': 'polite' });

  mount(raiz, h('div', { className: 'tela-login', role: 'main' }, [
    h('img', { className: 'header-logo-horizontal', src: 'assets/brand/magnata-logo-horizontal.svg', alt: 'Grupo Magnata' }),
    h('h1', {}, 'Entrar no Magnata OS'),
    h('p', {}, 'Entre com sua conta Google administrativa para acessar o painel da esteira documental.'),
    containerBotao,
    areaEstado,
  ]));

  if (!googleClientId) {
    mount(areaEstado, estadoErro({
      mensagem: 'Login indisponível: configuração ausente neste ambiente (GOOGLE_OAUTH_CLIENT_ID não definido). Fale com o time técnico antes de tentar novamente.',
    }));
    return;
  }

  async function aoReceberCredencial(idToken) {
    mount(areaEstado, estadoCarregando({ linhas: 1 }));
    try {
      const sessao = await autenticar(idToken);
      aoAutenticar(sessao);
    } catch (erro) {
      // Sem aoTentarNovamente: o botao do Google (containerBotao) continua
      // visivel abaixo da mensagem de erro -- um novo clique ja tenta de novo,
      // nao precisa de um segundo controle.
      mount(areaEstado, estadoErro({ mensagem: mensagemDeErroLogin(erro) }));
    }
  }

  carregarGis()
    .then(() => renderizarBotao({ clientId: googleClientId, container: containerBotao, aoReceberCredencial }))
    .catch(() => mount(areaEstado, estadoErro({
      mensagem: 'Não foi possível carregar o login do Google agora. Verifique sua conexão e tente novamente em instantes.',
    })));
}
