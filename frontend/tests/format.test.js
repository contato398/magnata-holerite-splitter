import { describe, it, assertEqual } from './test-harness.js';
import {
  rotuloEtapa, rotuloSituacao, rotuloTipoAcao, rotuloPerfil,
  tempoRelativoDeSegundos, formatarDuracaoSegundos, truncarNomeArquivo,
} from '../src/utils/format.js';

describe('utils/format.js', () => {
  it('traduz etapas para PT-BR', () => {
    assertEqual(rotuloEtapa('MONTAGEM_PACOTE'), 'Montagem de pacote');
    assertEqual(rotuloEtapa('AUDITORIA'), 'Auditoria');
    assertEqual(rotuloEtapa(null), 'Sem etapa');
  });

  it('traduz situacoes para PT-BR', () => {
    assertEqual(rotuloSituacao('EM_REVISAO'), 'Em revisão');
    assertEqual(rotuloSituacao('BLOQUEADO'), 'Bloqueado');
    assertEqual(rotuloSituacao(null), '—');
  });

  it('traduz tipo de proxima acao', () => {
    assertEqual(rotuloTipoAcao('AUTOMATICA'), 'Automática');
    assertEqual(rotuloTipoAcao('HUMANA'), 'Precisa de você');
  });

  it('traduz perfil', () => {
    assertEqual(rotuloPerfil('GESTOR'), 'Gestor');
    assertEqual(rotuloPerfil('AUDITOR'), 'Auditor');
  });

  it('tempo relativo -- minutos, horas, dias', () => {
    assertEqual(tempoRelativoDeSegundos(30), 'agora mesmo');
    assertEqual(tempoRelativoDeSegundos(300), 'há 5 min');
    assertEqual(tempoRelativoDeSegundos(3600 * 3), 'há 3h');
    assertEqual(tempoRelativoDeSegundos(3600 * 24 * 2), 'há 2 dias');
    assertEqual(tempoRelativoDeSegundos(3600 * 24), 'há 1 dia');
  });

  it('tempo relativo -- valores nulos/invalidos viram travessao', () => {
    assertEqual(tempoRelativoDeSegundos(null), '—');
    assertEqual(tempoRelativoDeSegundos(undefined), '—');
  });

  it('formata duracao em unidades legiveis', () => {
    assertEqual(formatarDuracaoSegundos(45), '45s');
    assertEqual(formatarDuracaoSegundos(150), '2 min');
    assertEqual(formatarDuracaoSegundos(3600 + 600), '1h 10min');
    assertEqual(formatarDuracaoSegundos(3600 * 25), '1d 1h');
  });

  it('trunca nomes de arquivo longos preservando a extensao', () => {
    const nomeLongo = 'Comprovante de Entrega Extremamente Detalhado do Pacote Mensal 06-2026.pdf';
    const truncado = truncarNomeArquivo(nomeLongo, 30);
    assertEqual(truncado.endsWith('.pdf'), true);
    assertEqual(truncado.length <= 31, true);
  });

  it('nao trunca nomes ja curtos', () => {
    assertEqual(truncarNomeArquivo('a.pdf', 30), 'a.pdf');
  });
});
