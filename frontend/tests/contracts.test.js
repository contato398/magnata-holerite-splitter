/**
 * "Compatibilidade com os contratos da API" (item 12 do pedido) --
 * confere que os enums/constantes do frontend continuam identicos aos
 * da Fase 4 (mesmos valores de string, mesmos conjuntos de permissao).
 * Se alguem editar contracts.js/autorizacao.js de forma que diverja do
 * Python, um teste aqui quebra.
 */
import { describe, it, assertEqual, assertDeepEqual, assertTrue, assertThrows } from './test-harness.js';
import { EtapaEsteira, SituacaoEsteira, TipoProximaAcao, ORDEM_ETAPAS, CodigoErro } from '../src/api/contracts.js';
import { Perfil, PERMISSAO_LEITURA_GERAL, PERMISSAO_FILA_OPERACIONAL, PERMISSAO_AUDITORIA, exigirPerfil } from '../src/api/autorizacao.js';
import { PermissaoNegada } from '../src/api/errors.js';

describe('api/contracts.js -- enums identicos a Fase 4', () => {
  it('EtapaEsteira tem exatamente as 10 etapas oficiais, na ordem canonica', () => {
    assertDeepEqual(ORDEM_ETAPAS, [
      'ENTRADA', 'REGISTRO', 'CLASSIFICACAO', 'SEPARACAO', 'IDENTIFICACAO',
      'VALIDACAO', 'MONTAGEM_PACOTE', 'DISTRIBUICAO', 'CONFIRMACAO', 'AUDITORIA',
    ]);
    assertEqual(Object.keys(EtapaEsteira).length, 10);
  });

  it('SituacaoEsteira tem exatamente as 7 situacoes oficiais', () => {
    assertDeepEqual(Object.keys(SituacaoEsteira).sort(), [
      'AGUARDANDO', 'BLOQUEADO', 'CONCLUIDO', 'EM_PROCESSAMENTO', 'EM_REVISAO', 'ERRO', 'PRONTO',
    ].sort());
  });

  it('TipoProximaAcao so tem AUTOMATICA e HUMANA', () => {
    assertDeepEqual(Object.values(TipoProximaAcao).sort(), ['AUTOMATICA', 'HUMANA']);
  });

  it('CodigoErro cobre os 7 codigos de erros.py', () => {
    assertDeepEqual(Object.values(CodigoErro).sort(), [
      'DOCUMENTO_NAO_ENCONTRADO', 'ERRO_INTERNO', 'FILTRO_INVALIDO', 'LOTE_NAO_ENCONTRADO',
      'ORDENACAO_INVALIDA', 'PAGINACAO_INVALIDA', 'PERMISSAO_NEGADA',
    ].sort());
  });
});

describe('api/autorizacao.js -- mesma politica de permissoes de handlers.py', () => {
  it('Perfil tem exatamente OPERACIONAL, GESTOR, AUDITOR', () => {
    assertDeepEqual(Object.values(Perfil).sort(), ['AUDITOR', 'GESTOR', 'OPERACIONAL'].sort());
  });

  it('leitura geral permite os 3 perfis', () => {
    assertDeepEqual([...PERMISSAO_LEITURA_GERAL].sort(), ['AUDITOR', 'GESTOR', 'OPERACIONAL'].sort());
  });

  it('fila operacional exclui AUDITOR', () => {
    assertDeepEqual([...PERMISSAO_FILA_OPERACIONAL].sort(), ['GESTOR', 'OPERACIONAL'].sort());
    assertTrue(!PERMISSAO_FILA_OPERACIONAL.includes(Perfil.AUDITOR));
  });

  it('auditoria exclui OPERACIONAL', () => {
    assertDeepEqual([...PERMISSAO_AUDITORIA].sort(), ['AUDITOR', 'GESTOR'].sort());
    assertTrue(!PERMISSAO_AUDITORIA.includes(Perfil.OPERACIONAL));
  });

  it('exigirPerfil nao levanta quando o perfil esta na lista', () => {
    exigirPerfil(Perfil.GESTOR, PERMISSAO_AUDITORIA); // nao deve lancar
  });

  it('exigirPerfil levanta PermissaoNegada (ApiError de verdade, nao um Error generico) quando nega', () => {
    assertThrows(() => exigirPerfil(Perfil.OPERACIONAL, PERMISSAO_AUDITORIA), PermissaoNegada);
  });

  it('a mensagem de PermissaoNegada lista os perfis permitidos', () => {
    try {
      exigirPerfil(Perfil.OPERACIONAL, PERMISSAO_AUDITORIA);
      throw new Error('deveria ter lancado');
    } catch (erro) {
      assertTrue(erro instanceof PermissaoNegada);
      assertTrue(erro.mensagem.includes('GESTOR'));
      assertTrue(erro.mensagem.includes('AUDITOR'));
      assertEqual(erro.codigo, 'PERMISSAO_NEGADA');
    }
  });
});
