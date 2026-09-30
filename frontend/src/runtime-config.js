/**
 * Placeholder de configuracao publica -- ver src/config.js (modulo
 * consumidor) para a explicacao completa do mecanismo.
 * `GOOGLE_OAUTH_CLIENT_ID: null` aqui e DE PROPOSITO: nenhum ambiente
 * real esta configurado neste repositorio. Script classico (nao
 * modulo ES), carregado por index.html ANTES de src/app.js, porque
 * precisa rodar antes do import de config.js e nao precisa de
 * import/export nenhum -- so define uma variavel global lida por
 * config.js.
 *
 * Cada deploy (local/producao) sobrescreve este arquivo com o Client
 * ID PUBLICO real daquele ambiente -- nunca um segredo (e enviado ao
 * navegador de qualquer forma para renderizar o botao de login), mas
 * tambem nunca commitado aqui por padrao (evita vazar qual
 * ambiente/projeto Google Cloud esta em uso).
 */
window.MAGNATA_CONFIG = {
  GOOGLE_OAUTH_CLIENT_ID: null,
};
