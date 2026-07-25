/**
 * Hierarquia de erros do frontend -- espelha erros.py (Fase 4) de
 * proposito: mesmo `codigo`, mesma logica de "nenhum detalhe tecnico
 * sensivel escapa para a interface".
 *
 * ApiError e a unica forma de erro que os componentes de UI sabem
 * tratar (ver components/EstadosUI.js) -- qualquer excecao que nao seja
 * ApiError, ao atravessar a fronteira do mockAdapter/client, e
 * convertida aqui em ErroInternoNaoExposto com uma mensagem generica
 * fixa, nunca `String(excecaoOriginal)`.
 */

import { CodigoErro } from './contracts.js';

export const MENSAGEM_ERRO_INTERNO_PADRAO =
  'Erro interno ao processar a consulta. Tente novamente mais tarde.';

export class ApiError extends Error {
  constructor(codigo, mensagem, detalhes = null) {
    super(mensagem);
    this.name = 'ApiError';
    this.codigo = codigo;
    this.mensagem = mensagem;
    this.detalhes = detalhes;
  }
}

export class DocumentoNaoEncontrado extends ApiError {
  constructor(mensagem, detalhes = null) {
    super(CodigoErro.DOCUMENTO_NAO_ENCONTRADO, mensagem, detalhes);
    this.name = 'DocumentoNaoEncontrado';
  }
}

export class LoteNaoEncontrado extends ApiError {
  constructor(mensagem, detalhes = null) {
    super(CodigoErro.LOTE_NAO_ENCONTRADO, mensagem, detalhes);
    this.name = 'LoteNaoEncontrado';
  }
}

export class FiltroInvalido extends ApiError {
  constructor(mensagem, detalhes = null) {
    super(CodigoErro.FILTRO_INVALIDO, mensagem, detalhes);
    this.name = 'FiltroInvalido';
  }
}

export class OrdenacaoInvalida extends ApiError {
  constructor(mensagem, detalhes = null) {
    super(CodigoErro.ORDENACAO_INVALIDA, mensagem, detalhes);
    this.name = 'OrdenacaoInvalida';
  }
}

export class PaginacaoInvalida extends ApiError {
  constructor(mensagem, detalhes = null) {
    super(CodigoErro.PAGINACAO_INVALIDA, mensagem, detalhes);
    this.name = 'PaginacaoInvalida';
  }
}

export class PermissaoNegada extends ApiError {
  constructor(mensagem, detalhes = null) {
    super(CodigoErro.PERMISSAO_NEGADA, mensagem, detalhes);
    this.name = 'PermissaoNegada';
  }
}

export class ErroInternoNaoExposto extends ApiError {
  constructor() {
    super(CodigoErro.ERRO_INTERNO, MENSAGEM_ERRO_INTERNO_PADRAO, null);
    this.name = 'ErroInternoNaoExposto';
  }
}

/**
 * Unico ponto de conversao de "qualquer excecao" -> ErroApiResponse.
 * Mesma regra de tratar_erro_para_resposta() (erros.py): uma excecao que
 * nao seja ApiError vira sempre a mesma mensagem generica, nunca expõe
 * `excecao.message` original.
 * @returns {import('./contracts.js').ErroApiResponse}
 */
export function tratarErroParaResposta(excecao) {
  if (excecao instanceof ApiError) {
    return { codigo: excecao.codigo, mensagem: excecao.mensagem, detalhes: excecao.detalhes };
  }
  return { codigo: CodigoErro.ERRO_INTERNO, mensagem: MENSAGEM_ERRO_INTERNO_PADRAO, detalhes: null };
}
