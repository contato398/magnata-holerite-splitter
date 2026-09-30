/**
 * Formatacao e rotulos em PT-BR -- linguagem simples, para usuario nao
 * tecnico (ver "Direcao visual" do pedido da Fase 5). Nenhuma funcao
 * aqui toca o DOM -- so recebe valores e devolve string, para ser
 * testavel isoladamente (tests/format.test.js).
 */

export const ROTULO_ETAPA = Object.freeze({
  ENTRADA: 'Entrada',
  REGISTRO: 'Registro',
  CLASSIFICACAO: 'Classificação',
  SEPARACAO: 'Separação',
  IDENTIFICACAO: 'Identificação',
  VALIDACAO: 'Validação',
  MONTAGEM_PACOTE: 'Montagem de pacote',
  DISTRIBUICAO: 'Distribuição',
  CONFIRMACAO: 'Confirmação',
  AUDITORIA: 'Auditoria',
});

export const ROTULO_SITUACAO = Object.freeze({
  AGUARDANDO: 'Aguardando',
  EM_PROCESSAMENTO: 'Em processamento',
  EM_REVISAO: 'Em revisão',
  PRONTO: 'Pronto',
  CONCLUIDO: 'Concluído',
  ERRO: 'Em erro',
  BLOQUEADO: 'Bloqueado',
});

export const ROTULO_TIPO_ACAO = Object.freeze({
  AUTOMATICA: 'Automática',
  HUMANA: 'Precisa de você',
});

export const ROTULO_PERFIL = Object.freeze({
  OPERACIONAL: 'Operacional',
  GESTOR: 'Gestor',
  AUDITOR: 'Auditor',
});

export function rotuloEtapa(etapa) {
  return etapa == null ? 'Sem etapa' : (ROTULO_ETAPA[etapa] || etapa);
}

export function rotuloSituacao(situacao) {
  return situacao == null ? '—' : (ROTULO_SITUACAO[situacao] || situacao);
}

export function rotuloTipoAcao(tipo) {
  return tipo == null ? '—' : (ROTULO_TIPO_ACAO[tipo] || tipo);
}

export function rotuloPerfil(perfil) {
  return ROTULO_PERFIL[perfil] || perfil;
}

/**
 * "há 5 min", "há 2h", "há 3 dias" -- sempre a partir de segundos ja
 * calculados (nunca recalcula timestamp aqui, quem chama decide a
 * referencia de "agora").
 */
export function tempoRelativoDeSegundos(segundos) {
  if (segundos == null || Number.isNaN(segundos)) return '—';
  const s = Math.max(0, Math.round(segundos));
  if (s < 60) return 'agora mesmo';
  const min = Math.round(s / 60);
  if (min < 60) return `há ${min} min`;
  const horas = Math.round(min / 60);
  if (horas < 24) return `há ${horas}h`;
  const dias = Math.round(horas / 24);
  if (dias < 30) return `há ${dias} ${dias === 1 ? 'dia' : 'dias'}`;
  const meses = Math.round(dias / 30);
  return `há ${meses} ${meses === 1 ? 'mês' : 'meses'}`;
}

export function tempoRelativoDeIso(iso, agora = new Date()) {
  if (!iso) return '—';
  const segundos = (agora.getTime() - new Date(iso).getTime()) / 1000;
  return tempoRelativoDeSegundos(segundos);
}

const FORMATADOR_DATA_HORA = new Intl.DateTimeFormat('pt-BR', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
});

const FORMATADOR_DATA = new Intl.DateTimeFormat('pt-BR', {
  day: '2-digit', month: '2-digit', year: 'numeric',
});

export function formatarDataHora(iso) {
  if (!iso) return '—';
  return FORMATADOR_DATA_HORA.format(new Date(iso));
}

export function formatarData(iso) {
  if (!iso) return '—';
  return FORMATADOR_DATA.format(new Date(iso));
}

export function formatarDuracaoSegundos(segundos) {
  if (segundos == null || Number.isNaN(segundos)) return '—';
  const s = Math.max(0, Math.round(segundos));
  if (s < 60) return `${s}s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `${min} min`;
  const horas = Math.floor(min / 60);
  const minRestantes = min % 60;
  if (horas < 24) return minRestantes ? `${horas}h ${minRestantes}min` : `${horas}h`;
  const dias = Math.floor(horas / 24);
  const horasRestantes = horas % 24;
  return horasRestantes ? `${dias}d ${horasRestantes}h` : `${dias}d`;
}

/** Trunca nomes de arquivo longos preservando a extensao -- para caber no card. */
export function truncarNomeArquivo(nome, maxLen = 42) {
  if (!nome || nome.length <= maxLen) return nome;
  const pontoIdx = nome.lastIndexOf('.');
  const extensao = pontoIdx > -1 ? nome.slice(pontoIdx) : '';
  const base = pontoIdx > -1 ? nome.slice(0, pontoIdx) : nome;
  const restante = Math.max(3, maxLen - extensao.length - 1);
  return `${base.slice(0, restante)}…${extensao}`;
}
