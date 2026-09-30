/**
 * Helpers compartilhados por todas as views -- principalmente o
 * mapeamento de ApiError -> estado de UI certo (item 8 do pedido).
 * Nenhuma view decide isso por conta propria, para o mapeamento nunca
 * divergir entre telas.
 */
import { mount } from '../utils/dom.js';
import { estadoErro, estadoServicoIndisponivel, estadoSemPermissao } from '../components/EstadosUI.js';

/**
 * @param {HTMLElement} container
 * @param {Error} erro
 * @param {{perfilAtual?: string, onTentarNovamente?: () => void}} opcoes
 */
export function renderErroApi(container, erro, opcoes = {}) {
  const { perfilAtual, onTentarNovamente } = opcoes;
  const codigo = erro && erro.codigo;

  if (codigo === 'PERMISSAO_NEGADA') {
    mount(container, estadoSemPermissao({ perfilAtual, perfisPermitidos: extrairPerfisDaMensagem(erro.mensagem) }));
    return;
  }
  if (codigo === 'ERRO_INTERNO') {
    mount(container, estadoServicoIndisponivel({ aoTentarNovamente: onTentarNovamente }));
    return;
  }
  mount(container, estadoErro({ mensagem: (erro && erro.mensagem) || 'Não foi possível carregar esses dados agora.', aoTentarNovamente: onTentarNovamente }));
}

function extrairPerfisDaMensagem(mensagem) {
  const match = /permitido: ([A-Z, ]+)/.exec(mensagem || '');
  return match ? match[1].split(',').map((s) => s.trim()) : [];
}

/** now - iso, em segundos, para calcular filtros "recebido hoje" etc. */
export function inicioDoDiaIso(agora = new Date()) {
  const inicio = new Date(agora);
  inicio.setHours(0, 0, 0, 0);
  return inicio.toISOString();
}

/**
 * Gerenciador simples de painel sobreposto (item 7 -- detalhe de
 * documento/lote): anexa ao <body>, nunca ao container da view, para
 * sobreviver a um re-render da view por baixo dele. So um painel por
 * vez -- abrir um novo fecha o anterior.
 */
export function criarGerenciadorPainel() {
  let painelAtual = null;
  return {
    abrir(node) {
      if (painelAtual) painelAtual.remove();
      painelAtual = node;
      document.body.appendChild(node);
    },
    fechar() {
      if (painelAtual) { painelAtual.remove(); painelAtual = null; }
    },
  };
}
