import { describe, it, assertTrue, assertFalse } from './test-harness.js';
import { ehPrioritario, LIMITE_PARADO_PADRAO_SEGUNDOS } from '../src/utils/prioridade.js';

describe('utils/prioridade.js', () => {
  it('documento bloqueado e sempre prioritario', () => {
    assertTrue(ehPrioritario({ situacao: 'BLOQUEADO', tempo_na_etapa_segundos: 10 }));
  });

  it('documento em erro e sempre prioritario', () => {
    assertTrue(ehPrioritario({ situacao: 'ERRO', tempo_na_etapa_segundos: 10 }));
  });

  it('documento parado acima do limite e prioritario mesmo sem bloqueio', () => {
    assertTrue(ehPrioritario({ situacao: 'AGUARDANDO', tempo_na_etapa_segundos: LIMITE_PARADO_PADRAO_SEGUNDOS + 1 }));
  });

  it('documento normal, dentro do tempo, nao e prioritario', () => {
    assertFalse(ehPrioritario({ situacao: 'AGUARDANDO', tempo_na_etapa_segundos: 60 }));
  });

  it('documento nulo nunca e prioritario (nunca lanca)', () => {
    assertFalse(ehPrioritario(null));
  });
});
