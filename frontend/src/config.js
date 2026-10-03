/**
 * Configuracao publica do painel, injetada em tempo de deploy --
 * NUNCA um segredo (o Client ID OAuth do Google e publico por
 * natureza: e enviado ao navegador de qualquer forma para renderizar
 * o botao "Entrar com o Google", ver
 * magnata_os/autenticacao/provedor_google_oidc.py).
 *
 * Mecanismo: `config.js` (arquivo IRMAO deste, na raiz de
 * `frontend/`, carregado por `index.html` ANTES do modulo `app.js`)
 * define `window.MAGNATA_CONFIG`. O arquivo committado aqui tem
 * `GOOGLE_OAUTH_CLIENT_ID: null` -- cada ambiente (local/produção)
 * sobrescreve esse arquivo com o valor real no momento do deploy,
 * sem precisar de build step nem de servidor de template (o painel
 * continua estático, ver frontend/CLAUDE.md "nunca conectar direto
 * ao legado"). Nenhum valor real de Client ID é commitado neste
 * repositório.
 *
 * `obterConfiguracao()` nunca lança -- ausência de `window` ou de
 * `MAGNATA_CONFIG` (config.js não carregado/bloqueado) vira
 * `googleClientId: null`, e quem consome isso (TelaLogin) trata como
 * "login indisponível: configuração ausente", nunca finge que está
 * configurado.
 */
export function obterConfiguracao() {
  try {
    const cfg = (typeof window !== 'undefined' && window.MAGNATA_CONFIG) || {};
    const clientId = cfg.GOOGLE_OAUTH_CLIENT_ID;
    return { googleClientId: typeof clientId === 'string' && clientId.trim() ? clientId.trim() : null };
  } catch (excecao) {
    return { googleClientId: null };
  }
}
