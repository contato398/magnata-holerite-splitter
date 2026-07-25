/**
 * Estados de interface reutilizaveis (item 8 do pedido da Fase 5):
 * carregando, vazio, erro, sem permissao, dados parciais, atualizacao
 * recente, servico indisponivel, nenhuma ocorrencia encontrada.
 *
 * Cada funcao devolve um Node pronto para ser montado no lugar do
 * conteudo normal da view -- nunca os dois ao mesmo tempo.
 */
import { h } from '../utils/dom.js';
import { icon } from '../utils/icons.js';

export function estadoCarregando({ linhas = 4 } = {}) {
  const itens = [];
  for (let i = 0; i < linhas; i += 1) {
    itens.push(h('div', { className: 'esqueleto', style: { height: '64px', marginBottom: '10px' } }));
  }
  return h('div', { 'aria-busy': 'true', 'aria-live': 'polite' }, [
    h('span', { className: 'somente-leitor-tela' }, 'Carregando dados…'),
    ...itens,
  ]);
}

export function estadoVazio({ titulo = 'Nada por aqui ainda', descricao = '' } = {}) {
  return h('div', { className: 'estado-ui estado-vazio' }, [
    icon('caixaVazia', { className: 'icone-estado' }),
    h('div', { className: 'titulo-estado' }, titulo),
    descricao ? h('p', { className: 'descricao-estado' }, descricao) : null,
  ]);
}

export function estadoNenhumaOcorrencia({ contexto = 'os filtros aplicados' } = {}) {
  return h('div', { className: 'estado-ui estado-vazio' }, [
    icon('busca', { className: 'icone-estado' }),
    h('div', { className: 'titulo-estado' }, 'Nenhuma ocorrência encontrada'),
    h('p', { className: 'descricao-estado' }, `Nenhum documento corresponde a ${contexto}. Tente ajustar ou limpar os filtros.`),
  ]);
}

export function estadoErro({ mensagem = 'Não foi possível carregar esses dados agora.', aoTentarNovamente } = {}) {
  return h('div', { className: 'estado-ui estado-erro' }, [
    icon('alerta', { className: 'icone-estado' }),
    h('div', { className: 'titulo-estado' }, 'Algo deu errado'),
    h('p', { className: 'descricao-estado' }, mensagem),
    aoTentarNovamente ? h('button', { className: 'btn btn-primario', onClick: aoTentarNovamente }, 'Tentar novamente') : null,
  ]);
}

export function estadoServicoIndisponivel({ aoTentarNovamente } = {}) {
  return h('div', { className: 'estado-ui estado-erro' }, [
    icon('semConexao', { className: 'icone-estado' }),
    h('div', { className: 'titulo-estado' }, 'Serviço indisponível no momento'),
    h('p', { className: 'descricao-estado' }, 'Não conseguimos falar com a esteira agora. Isso costuma se resolver sozinho — tente novamente em instantes.'),
    aoTentarNovamente ? h('button', { className: 'btn btn-primario', onClick: aoTentarNovamente }, 'Tentar novamente') : null,
  ]);
}

export function estadoSemPermissao({ perfilAtual, perfisPermitidos = [] } = {}) {
  return h('div', { className: 'estado-ui estado-sem-permissao' }, [
    icon('cadeado', { className: 'icone-estado' }),
    h('div', { className: 'titulo-estado' }, 'Você não tem acesso a esta área'),
    h('p', { className: 'descricao-estado' },
      perfisPermitidos.length
        ? `O perfil "${perfilAtual}" não pode ver esta tela. Acesso permitido para: ${perfisPermitidos.join(', ')}.`
        : `O perfil "${perfilAtual}" não pode ver esta tela.`
    ),
  ]);
}

/** Faixa (nao substitui o conteudo -- fica acima dele) para indicar que a resposta veio incompleta. */
export function faixaDadosParciais({ mensagem = 'Alguns dados podem estar desatualizados ou incompletos.' } = {}) {
  return h('div', { className: 'faixa-parcial' }, [icon('alerta', { style: { width: '15px', height: '15px' } }), mensagem]);
}

/** Selo pequeno "atualizado há X" -- usado no cabecalho. */
export function seloAtualizacaoRecente(texto) {
  return h('span', { className: 'selo-atualizacao' }, texto);
}
