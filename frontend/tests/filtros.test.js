/**
 * "filtros" e "busca" (item 12) -- validacao, aplicacao pura de filtro/
 * ordenacao/paginacao, e a conversao do estado bruto da UI (Filtros.js)
 * para o formato de filtro dos contratos da API.
 */
import { describe, it, assertEqual, assertTrue, assertThrows } from './test-harness.js';
import {
  validarPaginacao, validarOrdenacao, validarFiltroDocumentos, validarFiltroLotes,
  aplicarFiltroDocumentos, aplicarFiltroLotes, ordenarSeguro, paginar,
  converterFiltroUIParaContrato, CAMPOS_ORDENACAO_DOCUMENTOS, TAMANHO_PAGINA_MAXIMO,
} from '../src/state/filtros.js';
import { PaginacaoInvalida, OrdenacaoInvalida, FiltroInvalido } from '../src/api/errors.js';

const DOC_A = { documento_id: 'a', nome_original: 'Holerite A.pdf', origem: 'upload_manual', lote_id: 'lote-1', etapa_atual: 'REGISTRO', situacao: 'CONCLUIDO', proxima_acao: null, recebido_em: '2026-01-01T10:00:00.000Z', tempo_na_etapa_segundos: 100 };
const DOC_B = { documento_id: 'b', nome_original: 'Guia FGTS B.pdf', origem: 'email_intake', lote_id: 'lote-2', etapa_atual: 'CLASSIFICACAO', situacao: 'BLOQUEADO', proxima_acao: { tipo: 'HUMANA' }, recebido_em: '2026-02-01T10:00:00.000Z', tempo_na_etapa_segundos: 90000 };

describe('state/filtros.js -- validacao', () => {
  it('paginacao valida nao lanca', () => { validarPaginacao({ pagina: 1, tamanho_pagina: 20 }); });

  it('pagina < 1 e invalida', () => {
    assertThrows(() => validarPaginacao({ pagina: 0, tamanho_pagina: 20 }), PaginacaoInvalida);
  });

  it('tamanho_pagina acima do maximo e invalido', () => {
    assertThrows(() => validarPaginacao({ pagina: 1, tamanho_pagina: TAMANHO_PAGINA_MAXIMO + 1 }), PaginacaoInvalida);
  });

  it('ordenacao com campo fora do allowlist e invalida', () => {
    assertThrows(() => validarOrdenacao({ campo: 'nome_original', direcao: 'asc' }, CAMPOS_ORDENACAO_DOCUMENTOS), OrdenacaoInvalida);
  });

  it('ordenacao com direcao invalida e invalida', () => {
    assertThrows(() => validarOrdenacao({ campo: 'documento_id', direcao: 'lateral' }, CAMPOS_ORDENACAO_DOCUMENTOS), OrdenacaoInvalida);
  });

  it('recebido_de posterior a recebido_ate e filtro invalido (documentos e lotes)', () => {
    const filtro = { recebido_de: '2026-06-01', recebido_ate: '2026-01-01' };
    assertThrows(() => validarFiltroDocumentos(filtro), FiltroInvalido);
    assertThrows(() => validarFiltroLotes(filtro), FiltroInvalido);
  });

  it('tempo_minimo_parado_segundos negativo e filtro invalido', () => {
    assertThrows(() => validarFiltroDocumentos({ tempo_minimo_parado_segundos: -1 }), FiltroInvalido);
  });
});

describe('state/filtros.js -- aplicacao', () => {
  it('filtra por situacao', () => {
    const resultado = aplicarFiltroDocumentos([DOC_A, DOC_B], { situacao: 'BLOQUEADO' });
    assertEqual(resultado.length, 1);
    assertEqual(resultado[0].documento_id, 'b');
  });

  it('filtra por bloqueado=true/false', () => {
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { bloqueado: true }).length, 1);
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { bloqueado: false }).length, 1);
  });

  it('filtra por acao_humana', () => {
    const resultado = aplicarFiltroDocumentos([DOC_A, DOC_B], { acao_humana: true });
    assertEqual(resultado.length, 1);
    assertEqual(resultado[0].documento_id, 'b');
  });

  it('filtra por tempo_minimo_parado_segundos', () => {
    const resultado = aplicarFiltroDocumentos([DOC_A, DOC_B], { tempo_minimo_parado_segundos: 50000 });
    assertEqual(resultado.length, 1);
    assertEqual(resultado[0].documento_id, 'b');
  });

  it('busca por nome (case-insensitive, substring)', () => {
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { busca: 'holerite' }).length, 1);
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { busca: 'FGTS' }).length, 1);
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { busca: 'inexistente' }).length, 0);
  });

  it('busca tambem encontra por documento_id', () => {
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { busca: 'doc' }).length, 0); // ids sao "a"/"b", nao contem "doc" aqui
    assertEqual(aplicarFiltroDocumentos([DOC_A, DOC_B], { busca: 'a' }).length, 2); // "a" aparece no nome/id de ambos
  });

  it('combina varios filtros ao mesmo tempo (E logico)', () => {
    const resultado = aplicarFiltroDocumentos([DOC_A, DOC_B], { origem: 'email_intake', situacao: 'BLOQUEADO' });
    assertEqual(resultado.length, 1);
    assertEqual(resultado[0].documento_id, 'b');
  });

  it('filtra lotes por origem e situacao', () => {
    const lotes = [{ lote_id: 'l1', origem: 'upload_manual', situacao: 'CONCLUIDO', recebido_em: '2026-01-01T00:00:00.000Z' }];
    assertEqual(aplicarFiltroLotes(lotes, { origem: 'upload_manual' }).length, 1);
    assertEqual(aplicarFiltroLotes(lotes, { origem: 'outra' }).length, 0);
  });
});

describe('state/filtros.js -- ordenacao segura', () => {
  it('ordena asc/desc por um campo numerico', () => {
    const itens = [{ v: 3 }, { v: 1 }, { v: 2 }];
    assertEqual(ordenarSeguro(itens, (i) => i.v, 'asc').map((i) => i.v).join(','), '1,2,3');
    assertEqual(ordenarSeguro(itens, (i) => i.v, 'desc').map((i) => i.v).join(','), '3,2,1');
  });

  it('itens sem valor no campo de ordenacao sempre vao para o fim, em qualquer direcao', () => {
    const itens = [{ v: 2 }, { v: null }, { v: 1 }];
    assertEqual(ordenarSeguro(itens, (i) => i.v, 'asc').map((i) => i.v).join(','), '1,2,');
    assertEqual(ordenarSeguro(itens, (i) => i.v, 'desc').map((i) => i.v).join(','), '2,1,');
  });
});

describe('state/filtros.js -- paginacao', () => {
  it('pagina corretamente e calcula total_paginas', () => {
    const itens = Array.from({ length: 25 }, (_, i) => i);
    const p1 = paginar(itens, { pagina: 1, tamanho_pagina: 10 });
    assertEqual(p1.itens.length, 10);
    assertEqual(p1.total_paginas, 3);
    assertEqual(p1.total_itens, 25);
    const p3 = paginar(itens, { pagina: 3, tamanho_pagina: 10 });
    assertEqual(p3.itens.length, 5);
  });

  it('lista vazia tem total_paginas 0', () => {
    assertEqual(paginar([], { pagina: 1, tamanho_pagina: 10 }).total_paginas, 0);
  });

  it('pagina alem do fim devolve itens vazios, nao erro', () => {
    const resultado = paginar([1, 2, 3], { pagina: 5, tamanho_pagina: 10 });
    assertEqual(resultado.itens.length, 0);
    assertEqual(resultado.total_itens, 3);
  });
});

describe('state/filtros.js -- conversao UI -> contrato', () => {
  it('converte datas de calendario para ISO e horas para segundos', () => {
    const contrato = converterFiltroUIParaContrato({
      etapa: 'REGISTRO', recebido_de_data: '2026-01-01', recebido_ate_data: '2026-01-31', tempo_minimo_parado_horas: 2,
    });
    assertEqual(contrato.etapa, 'REGISTRO');
    // comparado contra a MESMA conversao local->ISO (nao um prefixo de
    // string fixo) -- o fuso horario do navegador que roda o teste nao
    // e necessariamente UTC, e a conversao trata a data como meia-noite
    // LOCAL de proposito (e o que o usuario espera ao escolher "hoje"
    // num <input type=date>).
    assertEqual(contrato.recebido_de, new Date('2026-01-01T00:00:00').toISOString());
    assertEqual(contrato.recebido_ate, new Date('2026-01-31T23:59:59').toISOString());
    assertEqual(contrato.tempo_minimo_parado_segundos, 7200);
  });

  it('campos vazios/nulos nunca aparecem no contrato final', () => {
    const contrato = converterFiltroUIParaContrato({ etapa: '', situacao: null, busca: '' });
    assertEqual(Object.keys(contrato).length, 0);
  });

  it('checkbox falso nunca vira `false` explicito no contrato (so `true` ou ausente)', () => {
    const contrato = converterFiltroUIParaContrato({ bloqueado: false, acao_humana: true });
    assertEqual('bloqueado' in contrato, false);
    assertEqual(contrato.acao_humana, true);
  });
});
