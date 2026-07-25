/**
 * Dados mockados (Modulo 01, Fase 5) -- nenhuma linha aqui vem de
 * Postgres, S3, R2 ou Airtable reais. Nomes de arquivo, origens e
 * lotes sao ficticios, criados so para demonstrar o painel; nenhum
 * campo ou identificador do Airtable e reaproveitado (ver restricao
 * "nao usar IDs ou campos do Airtable" do pedido da Fase 5).
 *
 * Os documentos e lotes aqui ja estao no formato exato dos contratos
 * da API (contracts.js) -- e o que mockAdapter.js devolve diretamente,
 * sem nenhuma transformacao adicional de forma (so filtro/ordenacao/
 * paginacao, que sao a MESMA logica que um backend real aplicaria).
 */

import { EtapaEsteira, SituacaoEsteira, TipoProximaAcao } from '../api/contracts.js';

const AGORA = Date.now();
const MINUTO = 60 * 1000;
const HORA = 60 * MINUTO;
const DIA = 24 * HORA;

function isoHaAtras(ms) {
  return new Date(AGORA - ms).toISOString();
}

function isoDaquiA(ms) {
  return new Date(AGORA + ms).toISOString();
}

// ---------------------------------------------------------------------
// Lotes
// ---------------------------------------------------------------------

export const LOTES = [
  {
    lote_id: 'lote-a1b2c3',
    origem: 'upload_manual',
    recebido_em: isoHaAtras(20 * MINUTO),
    quantidade_arquivos: 4,
    situacao: SituacaoEsteira.EM_PROCESSAMENTO,
    correlation_id: 'lote7a91f0c2',
    criado_em: isoHaAtras(20 * MINUTO),
    atualizado_em: isoHaAtras(5 * MINUTO),
    metadados: { canal: 'painel_operacional' },
  },
  {
    lote_id: 'lote-d4e5f6',
    origem: 'email_intake',
    recebido_em: isoHaAtras(3 * HORA),
    quantidade_arquivos: 6,
    situacao: SituacaoEsteira.CONCLUIDO,
    correlation_id: 'loteb62e91aa',
    criado_em: isoHaAtras(3 * HORA),
    atualizado_em: isoHaAtras(2 * HORA),
    metadados: { canal: 'caixa_entrada_documental' },
  },
  {
    lote_id: 'lote-g7h8i9',
    origem: 'integracao_ponto',
    recebido_em: isoHaAtras(2 * DIA),
    quantidade_arquivos: 3,
    situacao: SituacaoEsteira.EM_REVISAO,
    correlation_id: 'lote118cd4f5',
    criado_em: isoHaAtras(2 * DIA),
    atualizado_em: isoHaAtras(1 * DIA),
    metadados: { canal: 'integracao_relogio_ponto' },
  },
  {
    lote_id: 'lote-j1k2l3',
    origem: 'upload_manual',
    recebido_em: isoHaAtras(6 * DIA),
    quantidade_arquivos: 2,
    situacao: SituacaoEsteira.CONCLUIDO,
    correlation_id: 'lote99a1c3e0',
    criado_em: isoHaAtras(6 * DIA),
    atualizado_em: isoHaAtras(5 * DIA),
    metadados: { canal: 'painel_operacional' },
  },
];

// ---------------------------------------------------------------------
// Documentos -- cobrindo as 10 etapas, varias situacoes, bloqueios,
// acao humana/automatica e um documento legado (fora da esteira).
// ---------------------------------------------------------------------

function motivoBloqueio(codigo, descricao, detalheTecnico, resolvivelAutomaticamente) {
  return { codigo, descricao, detalhe_tecnico: detalheTecnico, resolvivel_automaticamente: resolvivelAutomaticamente };
}

function proximaAcao(acao, tipo, prazo = null, responsavel = null) {
  return { acao, tipo, prazo, responsavel };
}

function ultimoEvento(evento, quandoMs, correlationId) {
  return { evento, timestamp: isoHaAtras(quandoMs), correlation_id: correlationId };
}

function documento({
  id, nome, lote, origem, etapa, situacao, motivoBloqueioObj = null, acao = null,
  tempoNaEtapaMs, recebidoHaMs, atualizadoHaMs, evento, correlationId, rastreado = true,
}) {
  return {
    documento_id: id,
    nome_original: nome,
    lote_id: lote,
    origem,
    etapa_atual: rastreado ? etapa : null,
    situacao: rastreado ? situacao : null,
    motivo_bloqueio: motivoBloqueioObj,
    proxima_acao: acao,
    tempo_na_etapa_segundos: rastreado ? Math.round(tempoNaEtapaMs / 1000) : null,
    ultimo_evento: evento ? ultimoEvento(evento, atualizadoHaMs, correlationId) : null,
    recebido_em: isoHaAtras(recebidoHaMs),
    atualizado_em: rastreado ? isoHaAtras(atualizadoHaMs) : null,
    rastreado_pela_esteira: rastreado,
  };
}

export const DOCUMENTOS = [
  // ENTRADA
  documento({
    id: 'doc-0001', nome: 'Holerite Julho 2026 - Equipe Zona Norte.pdf', lote: 'lote-a1b2c3',
    origem: 'upload_manual', etapa: EtapaEsteira.ENTRADA, situacao: SituacaoEsteira.CONCLUIDO,
    acao: proximaAcao('Confirmar recebimento e avancar automaticamente para REGISTRO', TipoProximaAcao.AUTOMATICA),
    tempoNaEtapaMs: 4 * MINUTO, recebidoHaMs: 4 * MINUTO, atualizadoHaMs: 4 * MINUTO,
    evento: 'DOCUMENTO_RECEBIDO', correlationId: 'lote7a91f0c2',
  }),
  documento({
    id: 'doc-0002', nome: 'Guia FGTS Digital - Competencia 06-2026.pdf', lote: 'lote-a1b2c3',
    origem: 'upload_manual', etapa: EtapaEsteira.ENTRADA, situacao: SituacaoEsteira.CONCLUIDO,
    acao: proximaAcao('Confirmar recebimento e avancar automaticamente para REGISTRO', TipoProximaAcao.AUTOMATICA),
    tempoNaEtapaMs: 2 * MINUTO, recebidoHaMs: 2 * MINUTO, atualizadoHaMs: 2 * MINUTO,
    evento: 'DOCUMENTO_RECEBIDO', correlationId: 'lote7a91f0c2',
  }),

  // REGISTRO
  documento({
    id: 'doc-0003', nome: 'Ficha de Registro - Colaborador Novo 0231.pdf', lote: 'lote-a1b2c3',
    origem: 'upload_manual', etapa: EtapaEsteira.REGISTRO, situacao: SituacaoEsteira.CONCLUIDO,
    acao: proximaAcao('Avancar para CLASSIFICACAO (implementacao em fase futura)', TipoProximaAcao.AUTOMATICA),
    tempoNaEtapaMs: 8 * MINUTO, recebidoHaMs: 10 * MINUTO, atualizadoHaMs: 8 * MINUTO,
    evento: 'DOCUMENTO_REGISTRADO', correlationId: 'lote7a91f0c2',
  }),

  // CLASSIFICACAO (um livre, um bloqueado)
  documento({
    id: 'doc-0004', nome: 'Extrato FGTS - Junho 2026.pdf', lote: 'lote-d4e5f6',
    origem: 'email_intake', etapa: EtapaEsteira.CLASSIFICACAO, situacao: SituacaoEsteira.AGUARDANDO,
    acao: proximaAcao('Classificar o documento (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 45 * MINUTO, recebidoHaMs: 3 * HORA, atualizadoHaMs: 45 * MINUTO,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'loteb62e91aa',
  }),
  documento({
    id: 'doc-0005', nome: 'Termo de Prorrogacao - Contrato 004521.pdf', lote: 'lote-d4e5f6',
    origem: 'email_intake', etapa: EtapaEsteira.CLASSIFICACAO, situacao: SituacaoEsteira.BLOQUEADO,
    motivoBloqueioObj: motivoBloqueio(
      'CPF_ILEGIVEL', 'CPF ilegivel no documento digitalizado',
      'confianca_ocr=0.31 abaixo do minimo aceitavel (0.80)', false,
    ),
    acao: proximaAcao('Resolver bloqueio: CPF ilegivel no documento digitalizado', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 5 * HORA, recebidoHaMs: 3 * HORA + 20 * MINUTO, atualizadoHaMs: 5 * HORA,
    evento: 'ESTEIRA_BLOQUEIO_REGISTRADO', correlationId: 'loteb62e91aa',
  }),

  // SEPARACAO
  documento({
    id: 'doc-0006', nome: 'Assiduidade Julho 2026 - Equipe Zona Sul.pdf', lote: 'lote-d4e5f6',
    origem: 'email_intake', etapa: EtapaEsteira.SEPARACAO, situacao: SituacaoEsteira.EM_PROCESSAMENTO,
    acao: proximaAcao('Separar/fatiar o documento (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 1 * HORA + 10 * MINUTO, recebidoHaMs: 3 * HORA + 5 * MINUTO, atualizadoHaMs: 1 * HORA + 10 * MINUTO,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'loteb62e91aa',
  }),

  // IDENTIFICACAO (um recente, um bem parado)
  documento({
    id: 'doc-0007', nome: 'Guia de Pagamento - DCTFWeb 06-2026.pdf', lote: 'lote-d4e5f6',
    origem: 'email_intake', etapa: EtapaEsteira.IDENTIFICACAO, situacao: SituacaoEsteira.AGUARDANDO,
    acao: proximaAcao('Identificar funcionario/cliente vinculado (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 30 * MINUTO, recebidoHaMs: 3 * HORA + 12 * MINUTO, atualizadoHaMs: 30 * MINUTO,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'loteb62e91aa',
  }),
  documento({
    id: 'doc-0008', nome: 'Certidao Negativa de Debitos - Junho 2026.pdf', lote: 'lote-g7h8i9',
    origem: 'integracao_ponto', etapa: EtapaEsteira.IDENTIFICACAO, situacao: SituacaoEsteira.AGUARDANDO,
    acao: proximaAcao('Identificar funcionario/cliente vinculado (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 2 * DIA + 3 * HORA, recebidoHaMs: 2 * DIA + 4 * HORA, atualizadoHaMs: 2 * DIA + 3 * HORA,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote118cd4f5',
  }),

  // VALIDACAO -- em revisao (acao humana explicita por situacao)
  documento({
    id: 'doc-0009', nome: 'Folha de Ponto - Junho 2026 - Lago Azul.pdf', lote: 'lote-g7h8i9',
    origem: 'integracao_ponto', etapa: EtapaEsteira.VALIDACAO, situacao: SituacaoEsteira.EM_REVISAO,
    acao: proximaAcao('Revisar documento manualmente na etapa VALIDACAO', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 1 * DIA + 2 * HORA, recebidoHaMs: 2 * DIA + 1 * HORA, atualizadoHaMs: 1 * DIA + 2 * HORA,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote118cd4f5',
  }),

  // MONTAGEM_PACOTE
  documento({
    id: 'doc-0010', nome: 'Recibo de Ferias - Competencia 06-2026.pdf', lote: 'lote-j1k2l3',
    origem: 'upload_manual', etapa: EtapaEsteira.MONTAGEM_PACOTE, situacao: SituacaoEsteira.AGUARDANDO,
    acao: proximaAcao('Montar pacote de envio (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 3 * HORA, recebidoHaMs: 6 * DIA, atualizadoHaMs: 3 * HORA,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote99a1c3e0',
  }),

  // DISTRIBUICAO
  documento({
    id: 'doc-0011', nome: 'Pacote Mensal - Cliente Villa Verde - 06-2026.pdf', lote: 'lote-j1k2l3',
    origem: 'upload_manual', etapa: EtapaEsteira.DISTRIBUICAO, situacao: SituacaoEsteira.EM_PROCESSAMENTO,
    acao: proximaAcao('Distribuir/enviar pacote (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 40 * MINUTO, recebidoHaMs: 6 * DIA + 1 * HORA, atualizadoHaMs: 40 * MINUTO,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote99a1c3e0',
  }),

  // CONFIRMACAO
  documento({
    id: 'doc-0012', nome: 'Comprovante de Entrega - Pacote 06-2026 - Herbert.pdf', lote: 'lote-j1k2l3',
    origem: 'upload_manual', etapa: EtapaEsteira.CONFIRMACAO, situacao: SituacaoEsteira.AGUARDANDO,
    acao: proximaAcao('Confirmar entrega (implementacao em fase futura)', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 15 * MINUTO, recebidoHaMs: 5 * DIA + 23 * HORA, atualizadoHaMs: 15 * MINUTO,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote99a1c3e0',
  }),

  // AUDITORIA -- um concluido (terminal) e um em erro
  documento({
    id: 'doc-0013', nome: 'Holerite Maio 2026 - Equipe Zona Norte.pdf', lote: 'lote-j1k2l3',
    origem: 'upload_manual', etapa: EtapaEsteira.AUDITORIA, situacao: SituacaoEsteira.CONCLUIDO,
    acao: null,
    tempoNaEtapaMs: 5 * DIA, recebidoHaMs: 12 * DIA, atualizadoHaMs: 5 * DIA,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote99a1c3e0',
  }),
  documento({
    id: 'doc-0014', nome: 'DCTFWeb Maio 2026 - Divergencia de Competencia.pdf', lote: 'lote-g7h8i9',
    origem: 'integracao_ponto', etapa: EtapaEsteira.AUDITORIA, situacao: SituacaoEsteira.ERRO,
    acao: proximaAcao('Revisar documento manualmente na etapa AUDITORIA', TipoProximaAcao.HUMANA),
    tempoNaEtapaMs: 6 * HORA, recebidoHaMs: 4 * DIA, atualizadoHaMs: 6 * HORA,
    evento: 'ESTEIRA_ETAPA_AVANCADA', correlationId: 'lote118cd4f5',
  }),

  // Documento legado -- nunca passou por ServicoCriacaoLote (Fase 3),
  // sem EstadoEsteiraDocumento. Nao e erro -- e o caso explicito de
  // compatibilidade documentado na Fase 3/4.
  documento({
    id: 'doc-0015', nome: 'Contrato de Prestacao de Servicos - Arquivo Historico.pdf', lote: null,
    origem: 'migracao_legado', rastreado: false,
    recebidoHaMs: 90 * DIA, atualizadoHaMs: 90 * DIA,
  }),
];

// ---------------------------------------------------------------------
// Historico por documento_id -- eventos tecnicos (Fase 1) + ESTEIRA_*
// (Fase 3), mesma disciplina de EventoHistorico.
// ---------------------------------------------------------------------

export const HISTORICO = {
  'doc-0005': [
    { evento: 'DOCUMENTO_RECEBIDO', status_anterior: null, status_novo: 'RECEBIDO', timestamp: isoHaAtras(3 * HORA + 20 * MINUTO), correlation_id: 'loteb62e91aa', detalhes: { origem: 'email_intake', tamanho: 182934 } },
    { evento: 'DOCUMENTO_REGISTRADO', status_anterior: 'RECEBIDO', status_novo: 'REGISTRADO', timestamp: isoHaAtras(3 * HORA + 15 * MINUTO), correlation_id: 'loteb62e91aa', detalhes: {} },
    { evento: 'ESTEIRA_ESTADO_INICIAL_CRIADO', status_anterior: null, status_novo: null, timestamp: isoHaAtras(3 * HORA + 15 * MINUTO), correlation_id: 'loteb62e91aa', detalhes: { etapa_inicial: 'ENTRADA', situacao_inicial: 'CONCLUIDO' } },
    { evento: 'ESTEIRA_ETAPA_AVANCADA', status_anterior: null, status_novo: null, timestamp: isoHaAtras(3 * HORA + 14 * MINUTO), correlation_id: 'loteb62e91aa', detalhes: { etapa_anterior: 'ENTRADA', etapa_nova: 'REGISTRO', situacao_nova: 'CONCLUIDO' } },
    { evento: 'ESTEIRA_ETAPA_AVANCADA', status_anterior: null, status_novo: null, timestamp: isoHaAtras(3 * HORA + 10 * MINUTO), correlation_id: 'loteb62e91aa', detalhes: { etapa_anterior: 'REGISTRO', etapa_nova: 'CLASSIFICACAO', situacao_nova: 'AGUARDANDO' } },
    { evento: 'ESTEIRA_BLOQUEIO_REGISTRADO', status_anterior: null, status_novo: null, timestamp: isoHaAtras(5 * HORA), correlation_id: 'loteb62e91aa', detalhes: { etapa: 'CLASSIFICACAO', motivo_codigo: 'CPF_ILEGIVEL', motivo_descricao: 'CPF ilegivel no documento digitalizado', resolvivel_automaticamente: false } },
  ],
  'doc-0009': [
    { evento: 'DOCUMENTO_RECEBIDO', status_anterior: null, status_novo: 'RECEBIDO', timestamp: isoHaAtras(2 * DIA + 1 * HORA), correlation_id: 'lote118cd4f5', detalhes: { origem: 'integracao_ponto', tamanho: 94021 } },
    { evento: 'DOCUMENTO_REGISTRADO', status_anterior: 'RECEBIDO', status_novo: 'REGISTRADO', timestamp: isoHaAtras(2 * DIA), correlation_id: 'lote118cd4f5', detalhes: {} },
    { evento: 'ESTEIRA_ETAPA_AVANCADA', status_anterior: null, status_novo: null, timestamp: isoHaAtras(1 * DIA + 20 * HORA), correlation_id: 'lote118cd4f5', detalhes: { etapa_anterior: 'CLASSIFICACAO', etapa_nova: 'VALIDACAO', situacao_nova: 'EM_REVISAO', eh_salto: true, motivo_transicao: 'dados ja extraidos e identificados previamente' } },
  ],
};

export function historicoDoDocumento(documentoId) {
  return HISTORICO[documentoId] || [];
}
