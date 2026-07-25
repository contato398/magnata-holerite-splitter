/**
 * "compatibilidade com os contratos da API", "bloqueios", "ações
 * humanas", "erro", "sem permissão", "vazio" (item 12) -- os 9
 * endpoints do mockAdapter, testados contra a MESMA forma de contrato
 * que um client HTTP real devolveria.
 *
 * `configurarSimulacao({latenciaMs:0})` no topo -- testes aqui rodam
 * contra o adapter de verdade (nao um duplo), so sem a latencia
 * artificial, para o suite inteiro nao ficar lento.
 */
import { describe, it, assertEqual, assertTrue, assertRejects } from './test-harness.js';
import { mockApiClient, configurarSimulacao } from '../src/api/mockAdapter.js';
import { Perfil } from '../src/api/autorizacao.js';
import {
  DocumentoNaoEncontrado, LoteNaoEncontrado, FiltroInvalido, PaginacaoInvalida,
  OrdenacaoInvalida, PermissaoNegada, ErroInternoNaoExposto,
} from '../src/api/errors.js';

configurarSimulacao({ falhaGlobal: false, latenciaMs: 0 });

const OPERACIONAL = { perfil: Perfil.OPERACIONAL };
const GESTOR = { perfil: Perfil.GESTOR };
const AUDITOR = { perfil: Perfil.AUDITOR };

describe('mockAdapter -- obterResumoEsteira', () => {
  it('devolve todos os campos de ResumoEsteiraResponse', async () => {
    const resumo = await mockApiClient.obterResumoEsteira(GESTOR);
    for (const campo of [
      'total_documentos', 'total_por_etapa', 'total_por_situacao', 'total_bloqueados',
      'total_com_acao_humana', 'total_em_erro', 'total_parados_acima_do_limite',
      'limite_parado_segundos', 'lotes_recebidos_hoje', 'tempo_medio_na_etapa_segundos',
      'documento_mais_antigo_pendente',
    ]) {
      assertTrue(campo in resumo, `campo ausente no resumo: ${campo}`);
    }
    assertTrue(resumo.total_documentos > 0);
  });

  it('todo perfil tem acesso ao resumo (leitura geral)', async () => {
    await mockApiClient.obterResumoEsteira(OPERACIONAL);
    await mockApiClient.obterResumoEsteira(GESTOR);
    await mockApiClient.obterResumoEsteira(AUDITOR);
  });

  it('limite_parado_segundos negativo e FiltroInvalido', async () => {
    await assertRejects(() => mockApiClient.obterResumoEsteira(GESTOR, { limiteParadoSegundos: -1 }), FiltroInvalido);
  });
});

describe('mockAdapter -- lotes', () => {
  it('listarLotes devolve PaginacaoResponse com LoteResponse', async () => {
    const resp = await mockApiClient.listarLotes(GESTOR);
    assertTrue(Array.isArray(resp.itens));
    assertTrue(resp.total_itens >= resp.itens.length);
    assertTrue('lote_id' in resp.itens[0]);
    assertTrue('situacao' in resp.itens[0]);
  });

  it('obterLote encontra um lote existente', async () => {
    const lotes = await mockApiClient.listarLotes(GESTOR);
    const primeiro = lotes.itens[0];
    const lote = await mockApiClient.obterLote(GESTOR, primeiro.lote_id);
    assertEqual(lote.lote_id, primeiro.lote_id);
  });

  it('obterLote com id inexistente -> LoteNaoEncontrado', async () => {
    await assertRejects(() => mockApiClient.obterLote(GESTOR, 'lote-nao-existe-123'), LoteNaoEncontrado);
  });

  it('ordenacao invalida em listarLotes lanca OrdenacaoInvalida', async () => {
    await assertRejects(
      () => mockApiClient.listarLotes(GESTOR, { ordenacao: { campo: 'campo_inventado', direcao: 'asc' } }),
      OrdenacaoInvalida,
    );
  });
});

describe('mockAdapter -- documentos', () => {
  it('listarDocumentos devolve PaginacaoResponse com DocumentoEsteiraResponse', async () => {
    const resp = await mockApiClient.listarDocumentos(GESTOR);
    assertTrue(resp.itens.length > 0);
    const doc = resp.itens[0];
    for (const campo of [
      'documento_id', 'nome_original', 'lote_id', 'origem', 'etapa_atual', 'situacao',
      'motivo_bloqueio', 'proxima_acao', 'tempo_na_etapa_segundos', 'ultimo_evento',
      'recebido_em', 'atualizado_em', 'rastreado_pela_esteira',
    ]) {
      assertTrue(campo in doc, `campo ausente no documento: ${campo}`);
    }
  });

  it('filtro por situacao BLOQUEADO so devolve documentos bloqueados', async () => {
    const resp = await mockApiClient.listarDocumentos(GESTOR, { filtro: { situacao: 'BLOQUEADO' } });
    assertTrue(resp.itens.length > 0);
    assertTrue(resp.itens.every((d) => d.situacao === 'BLOQUEADO'));
  });

  it('filtro impossivel devolve lista vazia, nao erro ("vazio")', async () => {
    const resp = await mockApiClient.listarDocumentos(GESTOR, { filtro: { origem: 'origem-que-nunca-existe' } });
    assertEqual(resp.itens.length, 0);
    assertEqual(resp.total_itens, 0);
    assertEqual(resp.total_paginas, 0);
  });

  it('obterDocumento encontra um documento existente', async () => {
    const lista = await mockApiClient.listarDocumentos(GESTOR);
    const doc = await mockApiClient.obterDocumento(GESTOR, lista.itens[0].documento_id);
    assertEqual(doc.documento_id, lista.itens[0].documento_id);
  });

  it('obterDocumento com id inexistente -> DocumentoNaoEncontrado', async () => {
    await assertRejects(() => mockApiClient.obterDocumento(GESTOR, 'doc-nao-existe-999'), DocumentoNaoEncontrado);
  });

  it('paginacao invalida (tamanho_pagina 0) lanca PaginacaoInvalida', async () => {
    await assertRejects(
      () => mockApiClient.listarDocumentos(GESTOR, { paginacao: { pagina: 1, tamanho_pagina: 0 } }),
      PaginacaoInvalida,
    );
  });
});

describe('mockAdapter -- historico (exige GESTOR/AUDITOR)', () => {
  it('GESTOR e AUDITOR conseguem ver o historico', async () => {
    const lista = await mockApiClient.listarDocumentos(GESTOR);
    const id = lista.itens[0].documento_id;
    const h1 = await mockApiClient.obterHistoricoDocumento(GESTOR, id);
    const h2 = await mockApiClient.obterHistoricoDocumento(AUDITOR, id);
    assertEqual(h1.documento_id, id);
    assertEqual(h2.documento_id, id);
    assertTrue(Array.isArray(h1.eventos));
    assertEqual(h1.total_eventos, h1.eventos.length);
  });

  it('OPERACIONAL NAO consegue ver o historico ("sem permissão")', async () => {
    const lista = await mockApiClient.listarDocumentos(GESTOR);
    const id = lista.itens[0].documento_id;
    await assertRejects(() => mockApiClient.obterHistoricoDocumento(OPERACIONAL, id), PermissaoNegada);
  });

  it('eventos do historico vem ordenados cronologicamente', async () => {
    const lista = await mockApiClient.listarDocumentos(GESTOR, { filtro: { bloqueado: true } });
    const id = lista.itens[0].documento_id;
    const h = await mockApiClient.obterHistoricoDocumento(GESTOR, id);
    const timestamps = h.eventos.map((e) => new Date(e.timestamp).getTime());
    const ordenado = [...timestamps].sort((a, b) => a - b);
    assertEqual(JSON.stringify(timestamps), JSON.stringify(ordenado));
  });
});

describe('mockAdapter -- bloqueios (exige OPERACIONAL/GESTOR)', () => {
  it('OPERACIONAL e GESTOR conseguem listar bloqueios', async () => {
    const r1 = await mockApiClient.listarBloqueios(OPERACIONAL);
    const r2 = await mockApiClient.listarBloqueios(GESTOR);
    assertTrue(Array.isArray(r1.itens));
    assertTrue(Array.isArray(r2.itens));
  });

  it('AUDITOR NAO consegue listar bloqueios ("sem permissão")', async () => {
    await assertRejects(() => mockApiClient.listarBloqueios(AUDITOR), PermissaoNegada);
  });

  it('todo item da fila de bloqueios tem motivo_bloqueio preenchido', async () => {
    const resp = await mockApiClient.listarBloqueios(GESTOR);
    assertTrue(resp.itens.length > 0);
    assertTrue(resp.itens.every((b) => b.motivo_bloqueio && b.motivo_bloqueio.codigo));
  });
});

describe('mockAdapter -- acoes humanas (exige OPERACIONAL/GESTOR)', () => {
  it('OPERACIONAL e GESTOR conseguem listar acoes humanas', async () => {
    await mockApiClient.listarAcoesHumanas(OPERACIONAL);
    await mockApiClient.listarAcoesHumanas(GESTOR);
  });

  it('AUDITOR NAO consegue listar acoes humanas ("sem permissão")', async () => {
    await assertRejects(() => mockApiClient.listarAcoesHumanas(AUDITOR), PermissaoNegada);
  });

  it('todo item tem proxima_acao.tipo HUMANA', async () => {
    const resp = await mockApiClient.listarAcoesHumanas(GESTOR);
    assertTrue(resp.itens.length > 0);
    assertTrue(resp.itens.every((d) => d.proxima_acao && d.proxima_acao.tipo === 'HUMANA'));
  });
});

describe('mockAdapter -- documentos parados', () => {
  it('tempoMinimoSegundos negativo e FiltroInvalido', async () => {
    await assertRejects(() => mockApiClient.listarDocumentosParados(GESTOR, -1), FiltroInvalido);
  });

  it('limite muito alto devolve lista vazia ("vazio")', async () => {
    const resp = await mockApiClient.listarDocumentosParados(GESTOR, 999999999);
    assertEqual(resp.itens.length, 0);
  });

  it('limite 0 devolve todos os documentos rastreados parados >= 0', async () => {
    const resp = await mockApiClient.listarDocumentosParados(GESTOR, 0);
    assertTrue(resp.itens.length > 0);
  });
});

describe('mockAdapter -- erro interno nao vaza detalhes ("erro")', () => {
  it('falha simulada de infraestrutura vira ErroInternoNaoExposto em qualquer endpoint', async () => {
    configurarSimulacao({ falhaGlobal: true, latenciaMs: 0 });
    try {
      await assertRejects(() => mockApiClient.obterResumoEsteira(GESTOR), ErroInternoNaoExposto);
      await assertRejects(() => mockApiClient.listarDocumentos(GESTOR), ErroInternoNaoExposto);
    } finally {
      configurarSimulacao({ falhaGlobal: false, latenciaMs: 0 }); // nunca deixa vazando para os proximos testes
    }
  });

  it('depois de desligar a simulacao, o adapter volta ao normal', async () => {
    const resumo = await mockApiClient.obterResumoEsteira(GESTOR);
    assertTrue(resumo.total_documentos > 0);
  });
});
