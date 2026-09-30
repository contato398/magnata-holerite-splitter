/**
 * Adapter local/mock da API de esteira (Modulo 01, Fase 5).
 *
 * Implementa os 9 "endpoints conceituais" da Fase 4
 * (magnata_os/documental/modulo01/api/handlers.py) contra os dados em
 * data/mockData.js -- mesma forma de entrada/saida que um client.js
 * real (fetch contra a API HTTP, fase futura) teria. Nenhuma tela
 * conhece a diferenca entre este adapter e um real: views/*.js so
 * chamam `apiClient.<metodo>(...)`, nunca importam mockData.js
 * diretamente.
 *
 * Cada metodo aqui:
 *   1. Valida permissao do perfil (mesma logica de exigir_perfil,
 *      handlers.py) -- PermissaoNegada se o perfil nao tiver acesso.
 *   2. Valida filtro/paginacao/ordenacao (mesma logica de filtros.py).
 *   3. Aplica filtro + ordenacao segura + paginacao (state/filtros.js).
 *   4. Qualquer excecao que nao seja ApiError vira ErroInternoNaoExposto
 *      antes de sair daqui -- nunca expõe uma mensagem tecnica crua
 *      (mesma garantia de handlers.py/proteger_erros).
 *
 * `configurarSimulacao()` existe so para os estados de UI que a Fase 5
 * pede para tratar (erro, servico indisponivel) -- nunca usado pelas
 * views em uso normal, so por tests/ e por um botao de depuracao
 * opcional no proprio painel (ver components/EstadosUI.js).
 */

import { EtapaEsteira, SituacaoEsteira, TipoProximaAcao } from './contracts.js';
import {
  PERMISSAO_LEITURA_GERAL, PERMISSAO_FILA_OPERACIONAL, PERMISSAO_AUDITORIA, exigirPerfil,
} from './autorizacao.js';
import { ApiError, DocumentoNaoEncontrado, LoteNaoEncontrado, FiltroInvalido, ErroInternoNaoExposto } from './errors.js';
import {
  criarPaginacao, criarOrdenacao, validarPaginacao, validarOrdenacao,
  validarFiltroDocumentos, validarFiltroLotes,
  aplicarFiltroDocumentos, aplicarFiltroLotes, ordenarSeguro, paginar,
  CAMPOS_ORDENACAO_DOCUMENTOS, CAMPOS_ORDENACAO_LOTES, CAMPOS_ORDENACAO_BLOQUEIOS,
} from '../state/filtros.js';
import { DOCUMENTOS, LOTES, historicoDoDocumento } from '../data/mockData.js';

const LIMITE_PARADO_PADRAO_SEGUNDOS = 24 * 60 * 60;

const _simulacao = { falhaGlobal: false, latenciaMs: 180 };

/** So para tests/ e para o botao de depuracao do painel. */
export function configurarSimulacao({ falhaGlobal = false, latenciaMs = 180 } = {}) {
  _simulacao.falhaGlobal = falhaGlobal;
  _simulacao.latenciaMs = latenciaMs;
}

function atraso() {
  const ms = _simulacao.latenciaMs;
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
}

async function protegerErros(fn) {
  try {
    await atraso();
    if (_simulacao.falhaGlobal) {
      throw new Error('Falha de infraestrutura simulada (configurarSimulacao).');
    }
    return await fn();
  } catch (excecao) {
    if (excecao instanceof ApiError) throw excecao;
    throw new ErroInternoNaoExposto();
  }
}

const EXTRATORES_DOCUMENTOS = {
  atualizado_em: (doc) => doc.atualizado_em,
  entrou_na_etapa_em: (doc) => doc.atualizado_em, // mock nao guarda entrou_na_etapa_em separado; atualizado_em e proxy fiel (mesma semantica de "quando entrou na etapa atual")
  recebido_em: (doc) => doc.recebido_em,
  documento_id: (doc) => doc.documento_id,
  tempo_na_etapa_segundos: (doc) => doc.tempo_na_etapa_segundos,
};

const EXTRATORES_LOTES = {
  criado_em: (lote) => lote.criado_em,
  recebido_em: (lote) => lote.recebido_em,
  quantidade_arquivos: (lote) => lote.quantidade_arquivos,
  lote_id: (lote) => lote.lote_id,
};

const EXTRATORES_BLOQUEIOS = {
  tempo_bloqueado_segundos: (linha) => linha.tempo_bloqueado_segundos,
  documento_id: (linha) => linha.documento_id,
};

function paraBloqueioResponse(doc) {
  return {
    documento_id: doc.documento_id,
    nome_original: doc.nome_original,
    lote_id: doc.lote_id,
    etapa_atual: doc.etapa_atual,
    motivo_bloqueio: doc.motivo_bloqueio,
    proxima_acao: doc.proxima_acao,
    tempo_bloqueado_segundos: doc.tempo_na_etapa_segundos,
  };
}

export const mockApiClient = {
  /** GET /magnata-os/documental/esteira/resumo */
  async obterResumoEsteira(sujeito, { limiteParadoSegundos = LIMITE_PARADO_PADRAO_SEGUNDOS } = {}) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_LEITURA_GERAL);
      if (limiteParadoSegundos < 0) throw new FiltroInvalido('limiteParadoSegundos nao pode ser negativo.');

      const rastreados = DOCUMENTOS.filter((d) => d.rastreado_pela_esteira);

      const totalPorEtapa = {};
      const totalPorSituacao = {};
      for (const doc of rastreados) {
        totalPorEtapa[doc.etapa_atual] = (totalPorEtapa[doc.etapa_atual] || 0) + 1;
        totalPorSituacao[doc.situacao] = (totalPorSituacao[doc.situacao] || 0) + 1;
      }
      const totalBloqueados = totalPorSituacao[SituacaoEsteira.BLOQUEADO] || 0;
      const totalComAcaoHumana = rastreados.filter(
        (d) => d.proxima_acao != null && d.proxima_acao.tipo === TipoProximaAcao.HUMANA
      ).length;
      const totalEmErro = totalPorSituacao[SituacaoEsteira.ERRO] || 0;
      const totalParados = rastreados.filter((d) => d.tempo_na_etapa_segundos >= limiteParadoSegundos).length;

      const hoje = new Date().toDateString();
      const lotesRecebidosHoje = LOTES.filter((l) => new Date(l.recebido_em).toDateString() === hoje).length;

      const tempos = rastreados.map((d) => d.tempo_na_etapa_segundos);
      const tempoMedio = tempos.length ? tempos.reduce((a, b) => a + b, 0) / tempos.length : null;

      const pendentes = rastreados.filter(
        (d) => !(d.etapa_atual === EtapaEsteira.AUDITORIA && d.situacao === SituacaoEsteira.CONCLUIDO)
      );
      let documentoMaisAntigoPendente = null;
      if (pendentes.length) {
        documentoMaisAntigoPendente = pendentes.reduce(
          (mais, atual) => (atual.tempo_na_etapa_segundos > mais.tempo_na_etapa_segundos ? atual : mais)
        );
      }

      return {
        total_documentos: DOCUMENTOS.length,
        total_por_etapa: totalPorEtapa,
        total_por_situacao: totalPorSituacao,
        total_bloqueados: totalBloqueados,
        total_com_acao_humana: totalComAcaoHumana,
        total_em_erro: totalEmErro,
        total_parados_acima_do_limite: totalParados,
        limite_parado_segundos: limiteParadoSegundos,
        lotes_recebidos_hoje: lotesRecebidosHoje,
        tempo_medio_na_etapa_segundos: tempoMedio,
        documento_mais_antigo_pendente: documentoMaisAntigoPendente,
      };
    });
  },

  /** GET /magnata-os/documental/lotes */
  async listarLotes(sujeito, { filtro = {}, paginacao = criarPaginacao(), ordenacao = criarOrdenacao('criado_em', 'desc') } = {}) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_LEITURA_GERAL);
      validarFiltroLotes(filtro);
      validarPaginacao(paginacao);
      validarOrdenacao(ordenacao, CAMPOS_ORDENACAO_LOTES);

      let lotes = aplicarFiltroLotes(LOTES, filtro);
      lotes = ordenarSeguro(lotes, EXTRATORES_LOTES[ordenacao.campo], ordenacao.direcao);
      return paginar(lotes, paginacao);
    });
  },

  /** GET /magnata-os/documental/lotes/{lote_id} */
  async obterLote(sujeito, loteId) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_LEITURA_GERAL);
      const lote = LOTES.find((l) => l.lote_id === loteId);
      if (!lote) throw new LoteNaoEncontrado(`Lote nao encontrado: "${loteId}".`);
      return lote;
    });
  },

  /** GET /magnata-os/documental/documentos */
  async listarDocumentos(sujeito, { filtro = {}, paginacao = criarPaginacao(), ordenacao = criarOrdenacao('atualizado_em', 'desc') } = {}) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_LEITURA_GERAL);
      validarFiltroDocumentos(filtro);
      validarPaginacao(paginacao);
      validarOrdenacao(ordenacao, CAMPOS_ORDENACAO_DOCUMENTOS);

      let documentos = aplicarFiltroDocumentos(DOCUMENTOS, filtro);
      documentos = ordenarSeguro(documentos, EXTRATORES_DOCUMENTOS[ordenacao.campo], ordenacao.direcao);
      return paginar(documentos, paginacao);
    });
  },

  /** GET /magnata-os/documental/documentos/{documento_id} */
  async obterDocumento(sujeito, documentoId) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_LEITURA_GERAL);
      const doc = DOCUMENTOS.find((d) => d.documento_id === documentoId);
      if (!doc) throw new DocumentoNaoEncontrado(`Documento nao encontrado: "${documentoId}".`);
      return doc;
    });
  },

  /** GET /magnata-os/documental/documentos/{documento_id}/historico */
  async obterHistoricoDocumento(sujeito, documentoId) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_AUDITORIA);
      const doc = DOCUMENTOS.find((d) => d.documento_id === documentoId);
      if (!doc) throw new DocumentoNaoEncontrado(`Documento nao encontrado: "${documentoId}".`);
      const eventos = [...historicoDoDocumento(documentoId)].sort(
        (a, b) => new Date(a.timestamp) - new Date(b.timestamp)
      );
      return { documento_id: documentoId, total_eventos: eventos.length, eventos };
    });
  },

  /** GET /magnata-os/documental/bloqueios */
  async listarBloqueios(sujeito, { paginacao = criarPaginacao(), ordenacao = criarOrdenacao('tempo_bloqueado_segundos', 'desc') } = {}) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_FILA_OPERACIONAL);
      validarPaginacao(paginacao);
      validarOrdenacao(ordenacao, CAMPOS_ORDENACAO_BLOQUEIOS);

      let linhas = DOCUMENTOS.filter((d) => d.situacao === SituacaoEsteira.BLOQUEADO).map(paraBloqueioResponse);
      linhas = ordenarSeguro(linhas, EXTRATORES_BLOQUEIOS[ordenacao.campo], ordenacao.direcao);
      return paginar(linhas, paginacao);
    });
  },

  /** GET /magnata-os/documental/acoes-humanas */
  async listarAcoesHumanas(sujeito, { paginacao = criarPaginacao(), ordenacao = criarOrdenacao('atualizado_em', 'desc') } = {}) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_FILA_OPERACIONAL);
      validarPaginacao(paginacao);
      validarOrdenacao(ordenacao, CAMPOS_ORDENACAO_DOCUMENTOS);

      let documentos = DOCUMENTOS.filter((d) => d.proxima_acao != null && d.proxima_acao.tipo === TipoProximaAcao.HUMANA);
      documentos = ordenarSeguro(documentos, EXTRATORES_DOCUMENTOS[ordenacao.campo], ordenacao.direcao);
      return paginar(documentos, paginacao);
    });
  },

  /** GET /magnata-os/documental/parados */
  async listarDocumentosParados(sujeito, tempoMinimoSegundos, { paginacao = criarPaginacao(), ordenacao = criarOrdenacao('entrou_na_etapa_em', 'asc') } = {}) {
    return protegerErros(() => {
      exigirPerfil(sujeito.perfil, PERMISSAO_LEITURA_GERAL);
      if (tempoMinimoSegundos < 0) throw new FiltroInvalido('tempoMinimoSegundos nao pode ser negativo.');
      validarPaginacao(paginacao);
      validarOrdenacao(ordenacao, CAMPOS_ORDENACAO_DOCUMENTOS);

      let documentos = DOCUMENTOS.filter(
        (d) => d.tempo_na_etapa_segundos != null && d.tempo_na_etapa_segundos >= tempoMinimoSegundos
      );
      documentos = ordenarSeguro(documentos, EXTRATORES_DOCUMENTOS[ordenacao.campo], ordenacao.direcao);
      return paginar(documentos, paginacao);
    });
  },
};
