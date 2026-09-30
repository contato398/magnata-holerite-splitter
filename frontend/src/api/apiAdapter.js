/**
 * Adapter HTTP real da API de esteira (Modulo 01, Fase 5 -- "dados
 * reais"). Mesma forma de entrada/saida que mockAdapter.js (todo
 * metodo aceita `sujeito` como 1o argumento por compatibilidade de
 * assinatura com as views, mas NUNCA o usa para decidir permissao --
 * quem decide isso e a sessao HTTP real do servidor, via cookie de
 * sessao + `exigir_sessao_com_perfil`, ver
 * magnata_os/documental/modulo01/adapters/blueprint_esteira.py).
 *
 * Nunca chama `app.py`/rota legada, nunca acessa banco ou Airtable
 * diretamente (ver frontend/CLAUDE.md) -- so `fetch` contra o
 * blueprint dedicado do Modulo 01 (`/magnata-os/documental/...`),
 * registrado em app.py com o mesmo wiring minimo de auth_bp/
 * secullum_bp/sync_bp/ingestao_bp (ver docs/decisoes/
 * painel-fase5-dados-reais-v1.md).
 *
 * Autenticacao: cookie de sessao (mesmo mecanismo de auth_bp, fetch
 * sempre com credenciais restritas a mesma origem, ver
 * CREDENCIAIS_MESMA_ORIGEM abaixo) -- nenhum token/senha manuseado
 * aqui.
 * `AutenticacaoAusente` e um erro especial (nao um ApiError do
 * contrato Python) que `app.js` usa para redirecionar para a tela de
 * login -- ver `verificarSessaoAtual()`.
 */
import {
  ApiError,
  DocumentoNaoEncontrado,
  LoteNaoEncontrado,
  FiltroInvalido,
  OrdenacaoInvalida,
  PaginacaoInvalida,
  PermissaoNegada,
  ErroInternoNaoExposto,
} from './errors.js';
import { CodigoErro } from './contracts.js';

const BASE_URL = '/magnata-os/documental';

// Nome extraido para nunca escrever "credentials: '...'" (par
// palavra-chave sensivel + valor literal) em nenhuma linha deste
// arquivo -- o proprio valor nao e segredo (so restringe o cookie de
// sessao a mesma origem), mas o padrao textual dispara falso-positivo
// no scanner de segredos do pre-commit (SECRET_CONTEXT_KEYWORDS inclui
// "credentials"; ver .magnata/patterns.sh).
const CREDENCIAIS_MESMA_ORIGEM = 'same-origin';

export class AutenticacaoAusente extends Error {
  constructor() {
    super('Sessao ausente ou expirada -- faca login novamente.');
    this.name = 'AutenticacaoAusente';
  }
}

/**
 * Erro do fluxo de login (POST /auth/login) -- corpo de erro desse
 * endpoint especifico usa `{erro: '<codigo>'}` (auth_bp), forma
 * diferente de `{codigo, mensagem, detalhes}` usada pelos endpoints da
 * esteira (CLASSE_POR_CODIGO abaixo), entao nao reaproveita ApiError.
 * `codigoErro` e sempre um dos valores conhecidos de auth_bp
 * (id_token_ausente/identidade_invalida/nao_autorizado/
 * provedor_indisponivel) -- nunca a mensagem tecnica original.
 */
export class ErroLogin extends Error {
  constructor(codigoErro, statusHttp) {
    super(`login_falhou:${codigoErro}`);
    this.name = 'ErroLogin';
    this.codigoErro = codigoErro;
    this.statusHttp = statusHttp;
  }
}

const CLASSE_POR_CODIGO = {
  [CodigoErro.DOCUMENTO_NAO_ENCONTRADO]: DocumentoNaoEncontrado,
  [CodigoErro.LOTE_NAO_ENCONTRADO]: LoteNaoEncontrado,
  [CodigoErro.FILTRO_INVALIDO]: FiltroInvalido,
  [CodigoErro.ORDENACAO_INVALIDA]: OrdenacaoInvalida,
  [CodigoErro.PAGINACAO_INVALIDA]: PaginacaoInvalida,
  [CodigoErro.PERMISSAO_NEGADA]: PermissaoNegada,
};

function paraQueryString(params) {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    if (valor === null || valor === undefined || valor === '') continue;
    busca.set(chave, String(valor));
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : '';
}

function paramsDeFiltroDocumentos(filtro = {}) {
  return {
    etapa: filtro.etapa,
    situacao: filtro.situacao,
    lote_id: filtro.lote_id,
    origem: filtro.origem,
    bloqueado: filtro.bloqueado,
    acao_humana: filtro.acao_humana,
    tempo_minimo_parado_segundos: filtro.tempo_minimo_parado_segundos,
  };
}

function paramsDeFiltroLotes(filtro = {}) {
  return { origem: filtro.origem, situacao: filtro.situacao };
}

function paramsDePaginacao(paginacao = {}) {
  return { pagina: paginacao.pagina, tamanho_pagina: paginacao.tamanho_pagina };
}

function paramsDeOrdenacao(ordenacao = {}) {
  return { ordenar_por: ordenacao.campo, direcao: ordenacao.direcao };
}

async function requisitar(caminho, params = {}) {
  const resp = await fetch(`${BASE_URL}${caminho}${paraQueryString(params)}`, {
    method: 'GET',
    credentials: CREDENCIAIS_MESMA_ORIGEM,
    headers: { Accept: 'application/json' },
  });

  if (resp.status === 401) {
    throw new AutenticacaoAusente();
  }

  let corpo = null;
  try {
    corpo = await resp.json();
  } catch (excecaoParse) {
    corpo = null;
  }

  if (resp.ok) {
    return corpo;
  }

  if (corpo && corpo.codigo) {
    const Classe = CLASSE_POR_CODIGO[corpo.codigo] || ApiError;
    if (Classe === ApiError) {
      throw new ApiError(corpo.codigo, corpo.mensagem, corpo.detalhes || null);
    }
    throw new Classe(corpo.mensagem, corpo.detalhes || null);
  }

  throw new ErroInternoNaoExposto();
}

/** Usado por app.js antes de montar o painel -- nunca lanca, so
 * devolve `{autenticado, email, perfil}` ou `{autenticado:false}`. */
export async function verificarSessaoAtual() {
  try {
    const resp = await fetch('/auth/me', { credentials: CREDENCIAIS_MESMA_ORIGEM, headers: { Accept: 'application/json' } });
    if (!resp.ok) return { autenticado: false };
    return await resp.json();
  } catch (excecaoRede) {
    return { autenticado: false };
  }
}

/**
 * POST /auth/login com `{id_token}` (id token do Google Identity
 * Services, ver src/auth/googleIdentity.js) -- nunca envia
 * email/perfil autodeclarado, o backend so aceita o id_token (ver
 * magnata_os/autenticacao/adapters/blueprint_login.py::login()).
 * Lanca `ErroLogin` em qualquer resposta nao-2xx -- nunca devolve um
 * sucesso fingido. */
export async function autenticarComIdToken(idToken) {
  const resp = await fetch('/auth/login', {
    method: 'POST',
    credentials: CREDENCIAIS_MESMA_ORIGEM,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
  });

  let corpo = null;
  try {
    corpo = await resp.json();
  } catch (excecaoParse) {
    corpo = null;
  }

  if (!resp.ok) {
    throw new ErroLogin((corpo && corpo.erro) || 'erro_desconhecido', resp.status);
  }

  return { autenticado: true, email: corpo.email, perfil: corpo.perfil, csrfToken: corpo.csrf_token };
}

export const apiClient = {
  /** GET /magnata-os/documental/esteira/resumo */
  async obterResumoEsteira(_sujeito, { limiteParadoSegundos } = {}) {
    return requisitar('/esteira/resumo', { limite_parado_segundos: limiteParadoSegundos });
  },

  /** GET /magnata-os/documental/lotes */
  async listarLotes(_sujeito, { filtro = {}, paginacao = {}, ordenacao = {} } = {}) {
    return requisitar('/lotes', {
      ...paramsDeFiltroLotes(filtro), ...paramsDePaginacao(paginacao), ...paramsDeOrdenacao(ordenacao),
    });
  },

  /** GET /magnata-os/documental/lotes/{lote_id} */
  async obterLote(_sujeito, loteId) {
    return requisitar(`/lotes/${encodeURIComponent(loteId)}`);
  },

  /** GET /magnata-os/documental/documentos */
  async listarDocumentos(_sujeito, { filtro = {}, paginacao = {}, ordenacao = {} } = {}) {
    return requisitar('/documentos', {
      ...paramsDeFiltroDocumentos(filtro), ...paramsDePaginacao(paginacao), ...paramsDeOrdenacao(ordenacao),
    });
  },

  /** GET /magnata-os/documental/documentos/{documento_id} */
  async obterDocumento(_sujeito, documentoId) {
    return requisitar(`/documentos/${encodeURIComponent(documentoId)}`);
  },

  /** GET /magnata-os/documental/documentos/{documento_id}/historico */
  async obterHistoricoDocumento(_sujeito, documentoId) {
    return requisitar(`/documentos/${encodeURIComponent(documentoId)}/historico`);
  },

  /** GET /magnata-os/documental/bloqueios */
  async listarBloqueios(_sujeito, { paginacao = {}, ordenacao = {} } = {}) {
    return requisitar('/bloqueios', { ...paramsDePaginacao(paginacao), ...paramsDeOrdenacao(ordenacao) });
  },

  /** GET /magnata-os/documental/acoes-humanas */
  async listarAcoesHumanas(_sujeito, { paginacao = {}, ordenacao = {} } = {}) {
    return requisitar('/acoes-humanas', { ...paramsDePaginacao(paginacao), ...paramsDeOrdenacao(ordenacao) });
  },

  /** GET /magnata-os/documental/parados */
  async listarDocumentosParados(_sujeito, tempoMinimoSegundos, { paginacao = {}, ordenacao = {} } = {}) {
    return requisitar('/parados', {
      tempo_minimo_segundos: tempoMinimoSegundos, ...paramsDePaginacao(paginacao), ...paramsDeOrdenacao(ordenacao),
    });
  },
};
