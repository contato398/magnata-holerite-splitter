/**
 * Testes do adapter HTTP real (apiAdapter.js, Fase 5 -- "dados reais").
 * Nunca chama uma rede real -- `window.fetch` e substituido por um
 * duplo controlado em cada teste (guardado/restaurado sempre, mesmo em
 * falha), que confere o caminho/metodo/credenciais chamados e devolve
 * uma resposta sintetica fixa.
 *
 * Cobre exatamente o que o mockAdapter.js ja cobre por contrato (mesma
 * forma de retorno), mais o que e especifico do transporte HTTP:
 * querystring, cookie de sessao (fetch com credenciais restritas a
 * mesma origem), 401 ->
 * AutenticacaoAusente, e mapeamento de `codigo` de erro para a
 * subclasse certa de ApiError.
 */
import { describe, it, assertEqual, assertTrue, assertRejects } from './test-harness.js';
import { apiClient, verificarSessaoAtual, AutenticacaoAusente } from '../src/api/apiAdapter.js';
import {
  DocumentoNaoEncontrado, FiltroInvalido, PermissaoNegada, ErroInternoNaoExposto,
} from '../src/api/errors.js';

function instalarFetchFalso(respostaOuFn) {
  const original = window.fetch;
  const chamadas = [];
  window.fetch = async (url, opcoes) => {
    chamadas.push({ url: String(url), opcoes });
    const resposta = typeof respostaOuFn === 'function' ? respostaOuFn(String(url), opcoes) : respostaOuFn;
    return {
      ok: resposta.status >= 200 && resposta.status < 300,
      status: resposta.status,
      json: async () => resposta.corpo,
    };
  };
  return { chamadas, restaurar: () => { window.fetch = original; } };
}

describe('apiAdapter -- transporte HTTP', () => {
  it('obterResumoEsteira chama GET /magnata-os/documental/esteira/resumo com credentials same-origin', async () => {
    const { chamadas, restaurar } = instalarFetchFalso({ status: 200, corpo: { total_documentos: 3 } });
    try {
      const resumo = await apiClient.obterResumoEsteira({});
      assertEqual(resumo.total_documentos, 3);
      assertEqual(chamadas.length, 1);
      assertTrue(chamadas[0].url.startsWith('/magnata-os/documental/esteira/resumo'));
      assertEqual(chamadas[0].opcoes.method, 'GET');
      assertEqual(chamadas[0].opcoes.credentials, 'same-origin');
    } finally {
      restaurar();
    }
  });

  it('listarDocumentos serializa filtro/paginacao/ordenacao como querystring, sem chaves vazias', async () => {
    const { chamadas, restaurar } = instalarFetchFalso({ status: 200, corpo: { itens: [] } });
    try {
      await apiClient.listarDocumentos({}, {
        filtro: { situacao: 'BLOQUEADO', origem: null },
        paginacao: { pagina: 2, tamanho_pagina: 10 },
        ordenacao: { campo: 'atualizado_em', direcao: 'asc' },
      });
      const url = new URL(chamadas[0].url, 'http://teste.local');
      assertEqual(url.searchParams.get('situacao'), 'BLOQUEADO');
      assertEqual(url.searchParams.get('pagina'), '2');
      assertEqual(url.searchParams.get('tamanho_pagina'), '10');
      assertEqual(url.searchParams.get('ordenar_por'), 'atualizado_em');
      assertEqual(url.searchParams.get('direcao'), 'asc');
      assertTrue(!url.searchParams.has('origem'), 'origem=null nao deveria aparecer na querystring');
    } finally {
      restaurar();
    }
  });

  it('401 vira AutenticacaoAusente, nunca um ApiError generico', async () => {
    const { restaurar } = instalarFetchFalso({ status: 401, corpo: { erro: 'nao_autenticado' } });
    try {
      await assertRejects(
        () => apiClient.obterResumoEsteira({}),
        (erro) => erro instanceof AutenticacaoAusente,
        'deveria lancar AutenticacaoAusente em 401',
      );
    } finally {
      restaurar();
    }
  });

  it('404 com codigo DOCUMENTO_NAO_ENCONTRADO vira a subclasse certa de ApiError', async () => {
    const { restaurar } = instalarFetchFalso({
      status: 404, corpo: { codigo: 'DOCUMENTO_NAO_ENCONTRADO', mensagem: 'nao encontrado', detalhes: null },
    });
    try {
      await assertRejects(
        () => apiClient.obterDocumento({}, 'doc-x'),
        (erro) => erro instanceof DocumentoNaoEncontrado,
        'deveria lancar DocumentoNaoEncontrado',
      );
    } finally {
      restaurar();
    }
  });

  it('403 com codigo PERMISSAO_NEGADA vira PermissaoNegada', async () => {
    const { restaurar } = instalarFetchFalso({
      status: 403, corpo: { codigo: 'PERMISSAO_NEGADA', mensagem: 'sem permissao', detalhes: null },
    });
    try {
      await assertRejects(
        () => apiClient.obterHistoricoDocumento({}, 'doc-x'),
        (erro) => erro instanceof PermissaoNegada,
        'deveria lancar PermissaoNegada',
      );
    } finally {
      restaurar();
    }
  });

  it('400 com codigo FILTRO_INVALIDO vira FiltroInvalido', async () => {
    const { restaurar } = instalarFetchFalso({
      status: 400, corpo: { codigo: 'FILTRO_INVALIDO', mensagem: 'invalido', detalhes: null },
    });
    try {
      await assertRejects(
        () => apiClient.listarDocumentos({}),
        (erro) => erro instanceof FiltroInvalido,
        'deveria lancar FiltroInvalido',
      );
    } finally {
      restaurar();
    }
  });

  it('resposta 500 sem corpo JSON valido vira ErroInternoNaoExposto, nunca vaza detalhe tecnico', async () => {
    const original = window.fetch;
    window.fetch = async () => ({ ok: false, status: 500, json: async () => { throw new Error('nao e JSON'); } });
    try {
      await assertRejects(
        () => apiClient.obterResumoEsteira({}),
        (erro) => erro instanceof ErroInternoNaoExposto,
        'deveria lancar ErroInternoNaoExposto',
      );
    } finally {
      window.fetch = original;
    }
  });

  it('verificarSessaoAtual devolve {autenticado:false} em qualquer falha de rede, nunca lanca', async () => {
    const original = window.fetch;
    window.fetch = async () => { throw new Error('rede indisponivel'); };
    try {
      const sessao = await verificarSessaoAtual();
      assertEqual(sessao.autenticado, false);
    } finally {
      window.fetch = original;
    }
  });

  it('verificarSessaoAtual repassa autenticado/email/perfil de /auth/me', async () => {
    const { chamadas, restaurar } = instalarFetchFalso({
      status: 200, corpo: { autenticado: true, email: 'gestor@exemplo.com', perfil: 'GESTOR' },
    });
    try {
      const sessao = await verificarSessaoAtual();
      assertEqual(sessao.autenticado, true);
      assertEqual(sessao.perfil, 'GESTOR');
      assertTrue(chamadas[0].url.startsWith('/auth/me'));
    } finally {
      restaurar();
    }
  });
});
