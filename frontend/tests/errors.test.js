/**
 * "erro" e "sem permissao" (item 12) -- ApiError e tratarErroParaResposta
 * nunca vazam mensagem tecnica crua de uma excecao nao prevista.
 */
import { describe, it, assertEqual, assertTrue } from './test-harness.js';
import {
  ApiError, DocumentoNaoEncontrado, LoteNaoEncontrado, FiltroInvalido,
  OrdenacaoInvalida, PaginacaoInvalida, PermissaoNegada, ErroInternoNaoExposto,
  tratarErroParaResposta, MENSAGEM_ERRO_INTERNO_PADRAO,
} from '../src/api/errors.js';

describe('api/errors.js', () => {
  it('cada subclasse de ApiError carrega o codigo certo', () => {
    assertEqual(new DocumentoNaoEncontrado('x').codigo, 'DOCUMENTO_NAO_ENCONTRADO');
    assertEqual(new LoteNaoEncontrado('x').codigo, 'LOTE_NAO_ENCONTRADO');
    assertEqual(new FiltroInvalido('x').codigo, 'FILTRO_INVALIDO');
    assertEqual(new OrdenacaoInvalida('x').codigo, 'ORDENACAO_INVALIDA');
    assertEqual(new PaginacaoInvalida('x').codigo, 'PAGINACAO_INVALIDA');
    assertEqual(new PermissaoNegada('x').codigo, 'PERMISSAO_NEGADA');
    assertEqual(new ErroInternoNaoExposto().codigo, 'ERRO_INTERNO');
  });

  it('todas as subclasses sao instancias de ApiError', () => {
    assertTrue(new DocumentoNaoEncontrado('x') instanceof ApiError);
    assertTrue(new ErroInternoNaoExposto() instanceof ApiError);
  });

  it('ErroInternoNaoExposto sempre usa a mesma mensagem generica', () => {
    assertEqual(new ErroInternoNaoExposto().mensagem, MENSAGEM_ERRO_INTERNO_PADRAO);
  });

  it('tratarErroParaResposta preserva codigo/mensagem de um ApiError conhecido', () => {
    const resposta = tratarErroParaResposta(new DocumentoNaoEncontrado('Documento nao encontrado: xyz'));
    assertEqual(resposta.codigo, 'DOCUMENTO_NAO_ENCONTRADO');
    assertEqual(resposta.mensagem, 'Documento nao encontrado: xyz');
  });

  it('tratarErroParaResposta NUNCA expõe a mensagem de uma excecao generica', () => {
    const excecaoComSegredo = new Error('postgres user=admin password=SUPER_SECRETO host=10.0.0.5');
    const resposta = tratarErroParaResposta(excecaoComSegredo);
    assertEqual(resposta.codigo, 'ERRO_INTERNO');
    assertEqual(resposta.mensagem, MENSAGEM_ERRO_INTERNO_PADRAO);
    assertTrue(!resposta.mensagem.includes('SUPER_SECRETO'));
    assertTrue(!JSON.stringify(resposta).includes('SUPER_SECRETO'));
  });

  it('tratarErroParaResposta trata TypeError/ReferenceError (bugs) da mesma forma', () => {
    const resposta = tratarErroParaResposta(new TypeError('cannot read property x of undefined'));
    assertEqual(resposta.codigo, 'ERRO_INTERNO');
    assertEqual(resposta.mensagem, MENSAGEM_ERRO_INTERNO_PADRAO);
  });
});
