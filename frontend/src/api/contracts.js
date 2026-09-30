/**
 * Espelho fiel dos contratos e enums da API de esteira (Modulo 01, Fase 4
 * -- ver magnata_os/documental/modulo01/api/contratos.py,
 * dominio_esteira.py e autorizacao.py).
 *
 * Nao redefine nada por conta propria: todo nome de campo, todo valor de
 * enum e todo codigo de erro aqui e IDENTICO ao equivalente Python, de
 * proposito -- e o que garante que trocar mockAdapter.js por um cliente
 * HTTP real (fase futura) nao exige mudar mais nada no frontend, so a
 * implementacao de api/client.js.
 *
 * Nenhum valor aqui e calculado -- so as constantes/enums em si. Este
 * modulo nunca importa nada de data/ ou components/.
 */

// ---------------------------------------------------------------------
// Enums de dominio (dominio_esteira.py)
// ---------------------------------------------------------------------

export const EtapaEsteira = Object.freeze({
  ENTRADA: 'ENTRADA',
  REGISTRO: 'REGISTRO',
  CLASSIFICACAO: 'CLASSIFICACAO',
  SEPARACAO: 'SEPARACAO',
  IDENTIFICACAO: 'IDENTIFICACAO',
  VALIDACAO: 'VALIDACAO',
  MONTAGEM_PACOTE: 'MONTAGEM_PACOTE',
  DISTRIBUICAO: 'DISTRIBUICAO',
  CONFIRMACAO: 'CONFIRMACAO',
  AUDITORIA: 'AUDITORIA',
});

// Ordem canonica -- so para exibicao (colunas da esteira, Fase 5) e para
// medir "salto" -- mesma semantica de INDICE_ETAPA em dominio_esteira.py.
export const ORDEM_ETAPAS = Object.freeze([
  EtapaEsteira.ENTRADA,
  EtapaEsteira.REGISTRO,
  EtapaEsteira.CLASSIFICACAO,
  EtapaEsteira.SEPARACAO,
  EtapaEsteira.IDENTIFICACAO,
  EtapaEsteira.VALIDACAO,
  EtapaEsteira.MONTAGEM_PACOTE,
  EtapaEsteira.DISTRIBUICAO,
  EtapaEsteira.CONFIRMACAO,
  EtapaEsteira.AUDITORIA,
]);

export const SituacaoEsteira = Object.freeze({
  AGUARDANDO: 'AGUARDANDO',
  EM_PROCESSAMENTO: 'EM_PROCESSAMENTO',
  EM_REVISAO: 'EM_REVISAO',
  PRONTO: 'PRONTO',
  CONCLUIDO: 'CONCLUIDO',
  ERRO: 'ERRO',
  BLOQUEADO: 'BLOQUEADO',
});

export const TipoProximaAcao = Object.freeze({
  AUTOMATICA: 'AUTOMATICA',
  HUMANA: 'HUMANA',
});

// ---------------------------------------------------------------------
// Autorizacao -- ver autorizacao.js (Perfil, PERMISSAO_*, exigirPerfil).
// Movida para um modulo proprio para poder depender de errors.js
// (PermissaoNegada) sem criar import circular com este arquivo.
// ---------------------------------------------------------------------

// ---------------------------------------------------------------------
// Codigos de erro (erros.py) -- identicos aos `codigo` de cada ApiError.
// ---------------------------------------------------------------------

export const CodigoErro = Object.freeze({
  DOCUMENTO_NAO_ENCONTRADO: 'DOCUMENTO_NAO_ENCONTRADO',
  LOTE_NAO_ENCONTRADO: 'LOTE_NAO_ENCONTRADO',
  FILTRO_INVALIDO: 'FILTRO_INVALIDO',
  ORDENACAO_INVALIDA: 'ORDENACAO_INVALIDA',
  PAGINACAO_INVALIDA: 'PAGINACAO_INVALIDA',
  PERMISSAO_NEGADA: 'PERMISSAO_NEGADA',
  ERRO_INTERNO: 'ERRO_INTERNO',
});

// ---------------------------------------------------------------------
// Formas de contrato (contratos.py) -- documentadas via JSDoc, nao
// impostas em tempo de execucao (JS nao tem tipos estaticos) -- as
// funcoes de validacao ficam em api/errors.js, nao aqui.
// ---------------------------------------------------------------------

/**
 * @typedef {Object} MotivoBloqueioResponse
 * @property {string} codigo
 * @property {string} descricao
 * @property {?string} detalhe_tecnico
 * @property {boolean} resolvivel_automaticamente
 */

/**
 * @typedef {Object} ProximaAcaoResponse
 * @property {string} acao
 * @property {'AUTOMATICA'|'HUMANA'} tipo
 * @property {?string} prazo ISO-8601
 * @property {?string} responsavel
 */

/**
 * @typedef {Object} UltimoEventoResponse
 * @property {string} evento
 * @property {string} timestamp ISO-8601
 * @property {string} correlation_id
 */

/**
 * @typedef {Object} DocumentoEsteiraResponse
 * @property {string} documento_id
 * @property {string} nome_original
 * @property {?string} lote_id
 * @property {string} origem
 * @property {?string} etapa_atual
 * @property {?string} situacao
 * @property {?MotivoBloqueioResponse} motivo_bloqueio
 * @property {?ProximaAcaoResponse} proxima_acao
 * @property {?number} tempo_na_etapa_segundos
 * @property {?UltimoEventoResponse} ultimo_evento
 * @property {string} recebido_em ISO-8601
 * @property {?string} atualizado_em ISO-8601
 * @property {boolean} rastreado_pela_esteira
 */

/**
 * @typedef {Object} LoteResponse
 * @property {string} lote_id
 * @property {string} origem
 * @property {string} recebido_em
 * @property {number} quantidade_arquivos
 * @property {string} situacao
 * @property {string} correlation_id
 * @property {string} criado_em
 * @property {string} atualizado_em
 * @property {Object} metadados
 */

/**
 * @typedef {Object} HistoricoItemResponse
 * @property {string} evento
 * @property {?string} status_anterior
 * @property {?string} status_novo
 * @property {string} timestamp
 * @property {string} correlation_id
 * @property {Object} detalhes
 */

/**
 * @typedef {Object} HistoricoResumidoResponse
 * @property {string} documento_id
 * @property {number} total_eventos
 * @property {HistoricoItemResponse[]} eventos
 */

/**
 * @typedef {Object} BloqueioResponse
 * @property {string} documento_id
 * @property {string} nome_original
 * @property {?string} lote_id
 * @property {string} etapa_atual
 * @property {MotivoBloqueioResponse} motivo_bloqueio
 * @property {?ProximaAcaoResponse} proxima_acao
 * @property {number} tempo_bloqueado_segundos
 */

/**
 * @typedef {Object} ResumoEsteiraResponse
 * @property {number} total_documentos
 * @property {Object<string, number>} total_por_etapa
 * @property {Object<string, number>} total_por_situacao
 * @property {number} total_bloqueados
 * @property {number} total_com_acao_humana
 * @property {number} total_em_erro
 * @property {number} total_parados_acima_do_limite
 * @property {number} limite_parado_segundos
 * @property {number} lotes_recebidos_hoje
 * @property {?number} tempo_medio_na_etapa_segundos
 * @property {?DocumentoEsteiraResponse} documento_mais_antigo_pendente
 */

/**
 * @typedef {Object} PaginacaoResponse
 * @property {number} pagina
 * @property {number} tamanho_pagina
 * @property {number} total_itens
 * @property {number} total_paginas
 * @property {Array} itens
 */

/**
 * @typedef {Object} ErroApiResponse
 * @property {string} codigo
 * @property {string} mensagem
 * @property {?Object} detalhes
 */
