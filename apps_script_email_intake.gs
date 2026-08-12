/**
 * Magnata — Apps Script de Caixa de Entrada (Fase 2)
 *
 * Lê e-mails marcados com o label "Documentos-Magnata" que ainda não têm o
 * label "Processado-Render", extrai anexos PDF, e envia tudo para o
 * endpoint /email/webhook do Render.
 *
 * MODO DE USO (TESTE SEGURO):
 *   1. Cole este código em script.google.com (novo projeto).
 *   2. Rode runSetup() uma vez para salvar a API key e a URL do Render.
 *   3. Rode processarEmails() manualmente (NÃO crie o gatilho automático ainda).
 *      - Com DRY_RUN = true, o Render só responde o que FARIA, sem gravar nada
 *        no Airtable e sem aplicar o label "Processado-Render".
 *   4. Revise os logs (Execuções / Ver registros) e o retorno JSON.
 *   5. Só depois de validar, mude DRY_RUN para false e rode de novo no
 *      mesmo e-mail de teste.
 *   6. Só crie o gatilho automático (time-driven trigger) depois de aprovação
 *      explícita.
 */

// ───────────────────────────────────────────────────────────────────────────
// CONFIGURAÇÃO
// ───────────────────────────────────────────────────────────────────────────

var RENDER_URL = 'https://magnata-holerite-splitter.onrender.com/email/webhook';
var LABEL_ENTRADA    = 'Documentos-Magnata';
var LABEL_PROCESSADO = 'Processado-Render';

// Caixa oficial de recebimento dos documentos (conta Gmail onde este script roda).
var CAIXA_OFICIAL = 'contato@magnataservicos.com.br';

// Remetentes CONFIÁVEIS de documentos. E-mails vindos de qualquer um destes são
// processados automaticamente, SEM exigir o label manual LABEL_ENTRADA — cobre
// tanto envios diretos do contador quanto encaminhamentos da nossa própria caixa.
var REMETENTES_CONFIAVEIS = [
  'contato@magnataservicos.com.br',          // nossa caixa (encaminhamentos)
  'dpessoal.contabilidade1@hotmail.com',     // contador novo (Departamento Pessoal)
  'jaqueline@saviancontabilidade.com.br',    // contador Savian (legado — docs até Maio/2026)
  'dpfiscal.contabilidade2@hotmail.com',     // contador novo (Fiscal/Tributário — v2.67)
];

// Modo de teste: true = não grava nada no Airtable, apenas simula.
// Motor definitivo ARMADO: false (processa e marca como Processado-Render).
var DRY_RUN = false;

// ───────────────────────────────────────────────────────────────────────────
// SETUP — rode uma vez para guardar a API key com segurança
// ───────────────────────────────────────────────────────────────────────────

function runSetup() {
  // Cole aqui a sua chave EMAIL_WEBHOOK_KEY (a mesma configurada no Render).
  // NÃO deixe a chave salva neste arquivo depois de rodar runSetup() uma vez —
  // ela fica armazenada de forma segura no PropertiesService.
  var apiKey = 'COLE_AQUI_A_CHAVE_EMAIL_WEBHOOK_KEY';
  PropertiesService.getScriptProperties().setProperty('EMAIL_WEBHOOK_KEY', apiKey);
  Logger.log('API key salva com sucesso.');
}

// ───────────────────────────────────────────────────────────────────────────
// PROCESSAMENTO PRINCIPAL
// ───────────────────────────────────────────────────────────────────────────

function processarEmails() {
  var apiKey = PropertiesService.getScriptProperties().getProperty('EMAIL_WEBHOOK_KEY');
  if (!apiKey) {
    Logger.log('ERRO: API key não configurada. Rode runSetup() primeiro.');
    return;
  }

  // LockService compartilhado com executarProcessamentoAdministrativo() —
  // evita as duas rodarem ao mesmo tempo. Se o lock estiver ocupado, esta
  // rodada é pulada com segurança: a query não tem filtro de data e só
  // exclui por LABEL_PROCESSADO, então nada fica perdido — a próxima
  // execução horária recaptura o que ficou de fora.
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    Logger.log('processarEmails: lock ocupado (provável execução administrativa em andamento) — pulando esta execução.');
    return;
  }

  try {
    // Captura e-mails marcados com LABEL_ENTRADA OU vindos de QUALQUER remetente
    // confiável (sem exigir label manual nesses casos). Sempre exclui o que já
    // foi processado (LABEL_PROCESSADO), evitando reprocessamento/duplicação.
    var condicoesRemetente = REMETENTES_CONFIAVEIS.map(function (e) {
      return 'from:' + e;
    }).join(' OR ');
    var query = '(label:' + LABEL_ENTRADA + ' OR ' + condicoesRemetente + ') ' +
                '-label:' + LABEL_PROCESSADO;
    var threads = GmailApp.search(query);
    Logger.log('Threads encontradas: ' + threads.length);

    for (var t = 0; t < threads.length; t++) {
      var thread = threads[t];
      var messages = thread.getMessages();

      for (var m = 0; m < messages.length; m++) {
        var resultado = _processarMensagem(messages[m], DRY_RUN, apiKey);

        // Defesa explícita: mesmo que a lógica de aplicarLabelPermitido
        // tenha algum erro, dry-run nunca aplica label (dupla camada com
        // a regra já embutida em interpretarRespostaWebhook_).
        if (!DRY_RUN && resultado.aplicarLabelPermitido) {
          thread.addLabel(GmailApp.getUserLabelByName(LABEL_PROCESSADO));
        }
      }
    }
  } finally {
    lock.releaseLock();
  }
}

/**
 * Processa UMA mensagem: filtra anexos PDF, monta o payload, chama o Render
 * e interpreta a resposta. NÃO decide nem aplica label — devolve um
 * resultado estruturado (ver interpretarRespostaWebhook_) para o chamador
 * decidir. Extraída do corpo original de processarEmails() sem alteração de
 * lógica de filtragem/payload/headers — só reorganizada para ser reutilizável
 * por processarMensagemPorId_() também.
 */
function _processarMensagem(msg, dryRun, apiKey) {
  var attachments = msg.getAttachments({ includeInlineImages: false, includeAttachments: true });
  var pdfAttachments = [];
  for (var a = 0; a < attachments.length; a++) {
    var att = attachments[a];
    if (att.getContentType() === 'application/pdf' ||
        att.getName().toLowerCase().endsWith('.pdf')) {
      pdfAttachments.push(att);
    }
  }

  if (pdfAttachments.length === 0) {
    Logger.log('Mensagem sem PDF, pulando: ' + msg.getSubject());
    return {
      messageId: msg.getId(), dryRun: dryRun, httpCode: null, jsonValido: false,
      duplicidadeIdempotente: false, dryRunValido: false, sucessoIntegral: true,
      sucessoParcial: false, pendencia: false, falha: false,
      aplicarLabelPermitido: false, detalhe: 'Sem PDF — nada enviado ao Render.', anexos: [],
    };
  }

  var anexosPayload = [];
  for (var p = 0; p < pdfAttachments.length; p++) {
    var pdf = pdfAttachments[p];
    anexosPayload.push({
      nome_arquivo: pdf.getName(),
      conteudo_base64: Utilities.base64Encode(pdf.getBytes()),
    });
  }

  var payload = {
    message_id: msg.getId(),
    assunto: msg.getSubject(),
    remetente: msg.getFrom(),
    corpo: msg.getPlainBody().substring(0, 2000),
    anexos: anexosPayload,
    dry_run: dryRun,
  };

  Logger.log('Enviando para Render: ' + msg.getSubject() + ' (' + anexosPayload.length + ' PDF(s))');

  var response = UrlFetchApp.fetch(RENDER_URL, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-API-KEY': apiKey },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  var code = response.getResponseCode();
  var body = response.getContentText();
  Logger.log('HTTP ' + code);

  var resultado = interpretarRespostaWebhook_(code, body, anexosPayload.length);
  resultado.messageId = msg.getId();
  resultado.dryRun = dryRun;
  return resultado;
}

/**
 * Interpreta a resposta HTTP de /email/webhook de forma conservadora — função
 * pura, sem dependência de GmailApp/UrlFetchApp, para poder ser testada
 * isoladamente. HTTP 200 sozinho NÃO significa sucesso: o corpo precisa ser
 * JSON válido, com anexos_processados consistente com o que foi enviado, e
 * sem estrutura inesperada. aplicarLabelPermitido preserva exatamente a
 * política atual do fluxo automático (httpCode===200 && !dryRun), com uma
 * única exceção: corpo estruturalmente inconsistente nunca libera label,
 * mesmo com HTTP 200 (caso que o código original nunca detectava, por nunca
 * fazer JSON.parse do corpo).
 */
function interpretarRespostaWebhook_(httpCode, bodyText, anexosEnviados) {
  var r = {
    httpCode: httpCode, dryRun: null, jsonValido: false, duplicidadeIdempotente: false,
    dryRunValido: false, sucessoIntegral: false, sucessoParcial: false, pendencia: false,
    falha: false, aplicarLabelPermitido: false, detalhe: '', anexos: [],
  };

  if (httpCode !== 200) {
    r.falha = true;
    r.detalhe = 'HTTP ' + httpCode + ' — resposta não-200.';
    return r;
  }

  var json;
  try {
    json = JSON.parse(bodyText);
    r.jsonValido = true;
  } catch (erro) {
    r.falha = true;
    r.detalhe = 'HTTP 200 mas corpo não é JSON válido.';
    return r;
  }
  if (typeof json !== 'object' || json === null) {
    r.falha = true;
    r.detalhe = 'Corpo JSON não é um objeto.';
    return r;
  }

  r.dryRun = (json.dry_run === true);
  r.aplicarLabelPermitido = (httpCode === 200 && r.dryRun === false);

  if (json.email_savian && json.email_savian.acao === 'duplicado_message_id') {
    r.duplicidadeIdempotente = true;
    r.detalhe = 'Message-ID já processado anteriormente — não prova conclusão dos anexos desta chamada.';
    return r;
  }

  if (!('anexos_processados' in json) || !Array.isArray(json.anexos_processados)) {
    r.falha = true;
    r.aplicarLabelPermitido = false;
    r.detalhe = 'anexos_processados ausente ou não é array — estrutura inesperada.';
    return r;
  }
  r.anexos = json.anexos_processados;

  if (typeof anexosEnviados === 'number' && r.anexos.length !== anexosEnviados) {
    r.falha = true;
    r.aplicarLabelPermitido = false;
    r.detalhe = 'Quantidade de anexos na resposta (' + r.anexos.length +
                ') difere do enviado (' + anexosEnviados + ').';
    return r;
  }

  if (r.dryRun) {
    r.dryRunValido = true;
    r.detalhe = 'dry-run — nenhuma gravação real ocorreu.';
    return r;
  }

  var total = r.anexos.length, comErro = 0, comPendencia = 0;
  for (var i = 0; i < total; i++) {
    var item = r.anexos[i];
    if (!item || typeof item !== 'object') {
      r.falha = true;
      r.aplicarLabelPermitido = false;
      r.detalhe = 'Item de anexo com formato inesperado.';
      return r;
    }
    if (item.erro) { comErro++; continue; }
    if (item.pendencia || item.pendencia_record_id) comPendencia++;
  }

  if (comErro === total) {
    r.falha = true;
    r.detalhe = 'Todos os anexos falharam.';
  } else if (comErro > 0) {
    r.sucessoParcial = true;
    r.detalhe = comErro + '/' + total + ' anexo(s) com erro.';
  } else if (comPendencia > 0) {
    r.pendencia = true;
    r.detalhe = comPendencia + ' anexo(s) geraram pendência.';
  } else {
    r.sucessoIntegral = true;
    r.detalhe = 'Todos os anexos processados sem erro nem pendência.';
  }

  return r;
}

// ───────────────────────────────────────────────────────────────────────────
// PROCESSAMENTO ADMINISTRATIVO POR MESSAGE ID — diagnóstico e reprocessamento
// pontual de UMA mensagem, fora do fluxo automático. Nenhuma das funções
// abaixo é referenciada por processarEmails() nem por gatilho — só chamadas
// manualmente pelo editor do Apps Script.
// ───────────────────────────────────────────────────────────────────────────

/**
 * Diagnóstico somente leitura: lê ADMIN_MESSAGE_ID de Script Properties,
 * confirma que é um ID de mensagem válido e acessível, e lista as mensagens
 * da mesma thread com contagem de PDFs — só para inspeção manual antes de
 * decidir reconciliar um label. Sem parâmetros (o botão Executar do editor
 * não permite passar argumentos). Não chama Render, não chama Airtable, não
 * aplica label, não altera nenhuma Script Property, não exige
 * ADMIN_EXECUTION_ENABLED (é só leitura, sem efeito colateral). Não registra
 * corpo do e-mail, base64, CPF ou conteúdo documental — só metadados.
 */
function verificarMessageIdAdministrativo() {
  var messageId = PropertiesService.getScriptProperties().getProperty('ADMIN_MESSAGE_ID');
  if (!messageId) {
    Logger.log('[VERIFICACAO] ADMIN_MESSAGE_ID ausente ou vazio.');
    return;
  }

  var msg;
  try {
    msg = GmailApp.getMessageById(messageId);
  } catch (erro) {
    Logger.log('[VERIFICACAO] ID inválido ou inacessível: ' + erro.message);
    return;
  }

  var pdfsMsg = msg.getAttachments({ includeInlineImages: false, includeAttachments: true })
    .filter(function (att) {
      return att.getContentType() === 'application/pdf' || att.getName().toLowerCase().endsWith('.pdf');
    });

  Logger.log('[VERIFICACAO] messageId=' + messageId +
             ' | assunto=' + msg.getSubject() +
             ' | de=' + msg.getFrom() +
             ' | data=' + msg.getDate() +
             ' | pdfs=' + pdfsMsg.length +
             ' | threadId=' + msg.getThread().getId());

  // Leitura complementar, ainda somente leitura: confirma se outras
  // mensagens da mesma thread também têm PDF, para decidir com segurança se
  // a thread pode receber o label Processado-Render mais adiante (decisão
  // sempre manual — ver nota em executarProcessamentoAdministrativo).
  var mensagensDaThread = msg.getThread().getMessages();
  Logger.log('[VERIFICACAO] Thread tem ' + mensagensDaThread.length + ' mensagem(ns):');
  for (var i = 0; i < mensagensDaThread.length; i++) {
    var m = mensagensDaThread[i];
    var pdfs = m.getAttachments({ includeInlineImages: false, includeAttachments: true })
      .filter(function (att) {
        return att.getContentType() === 'application/pdf' || att.getName().toLowerCase().endsWith('.pdf');
      });
    Logger.log('  [' + i + '] id=' + m.getId() + ' | data=' + m.getDate() + ' | pdfs=' + pdfs.length);
  }
}

/**
 * Processa UMA mensagem pelo ID, fora do fluxo automático. Nunca chamada por
 * processarEmails() nem por gatilho. Não chama GmailApp.search, não chama
 * thread.getMessages, não alcança respostas posteriores da mesma
 * conversa — só a mensagem exata informada.
 */
function processarMensagemPorId_(messageId, dryRun) {
  if (typeof messageId !== 'string' || messageId.trim() === '') {
    throw new Error('processarMensagemPorId_: messageId deve ser string não vazia.');
  }
  if (typeof dryRun !== 'boolean') {
    throw new Error('processarMensagemPorId_: dryRun deve ser informado explicitamente.');
  }

  var apiKey = PropertiesService.getScriptProperties().getProperty('EMAIL_WEBHOOK_KEY');
  if (!apiKey) {
    throw new Error('processarMensagemPorId_: EMAIL_WEBHOOK_KEY não configurada.');
  }

  var msg;
  try {
    msg = GmailApp.getMessageById(messageId);
  } catch (erro) {
    throw new Error('processarMensagemPorId_: falha ao obter mensagem "' + messageId + '": ' + erro.message);
  }
  if (!msg) {
    throw new Error('processarMensagemPorId_: nenhuma mensagem retornada para "' + messageId + '".');
  }

  Logger.log('[ADMIN] Processando mensagem — messageId=' + messageId + ' | dryRun=' + dryRun);
  var resultado = _processarMensagem(msg, dryRun, apiKey);
  Logger.log('[ADMIN] Concluído — messageId=' + messageId + ' | httpCode=' + resultado.httpCode);
  return resultado;
}

/**
 * Executor administrativo sem parâmetros — chamável pelo botão Executar do
 * editor. Lê configuração de Script Properties (ADMIN_MESSAGE_ID,
 * ADMIN_DRY_RUN, ADMIN_EXECUTION_ENABLED). Nunca referenciada por
 * processarEmails() nem por gatilho. Nunca aplica label — o resultado
 * estruturado é só para revisão humana; a decisão de marcar
 * Processado-Render manualmente (depois de reconciliar com
 * verificarMessageIdAdministrativo) é sempre humana, fora deste script.
 */
function executarProcessamentoAdministrativo() {
  var props = PropertiesService.getScriptProperties();
  var lock = LockService.getScriptLock();
  var gotLock = false;

  try {
    if (props.getProperty('ADMIN_EXECUTION_ENABLED') !== 'true') {
      Logger.log('[ADMIN] Não habilitado (ADMIN_EXECUTION_ENABLED != "true"). Abortando.');
      return;
    }

    var messageId = props.getProperty('ADMIN_MESSAGE_ID');
    if (!messageId) {
      Logger.log('[ADMIN] ADMIN_MESSAGE_ID ausente ou vazio. Abortando.');
      return;
    }

    var dryRunRaw = props.getProperty('ADMIN_DRY_RUN');
    if (dryRunRaw !== 'true' && dryRunRaw !== 'false') {
      Logger.log('[ADMIN] ADMIN_DRY_RUN inválido (esperado "true" ou "false", recebido: "' + dryRunRaw + '"). Abortando.');
      return;
    }
    var dryRun = (dryRunRaw === 'true');

    // Segunda camada de proteção de concorrência: aborta se o gatilho
    // automático de processarEmails ainda estiver instalado.
    var gatilhos = ScriptApp.getProjectTriggers();
    for (var g = 0; g < gatilhos.length; g++) {
      if (gatilhos[g].getHandlerFunction() === 'processarEmails') {
        Logger.log('[ADMIN] Gatilho automático de processarEmails ainda ativo — abortando por segurança. Desative com removerGatilhos() antes.');
        return;
      }
    }

    gotLock = lock.tryLock(5000);
    if (!gotLock) {
      Logger.log('[ADMIN] Lock indisponível — outra execução em andamento. Abortando sem processar.');
      return;
    }

    Logger.log('[ADMIN] Iniciando execução administrativa — messageId=' + messageId + ' | dryRun=' + dryRun);
    var resultado = processarMensagemPorId_(messageId, dryRun);
    Logger.log('[ADMIN] Execução administrativa concluída — messageId=' + messageId +
               ' | sucessoIntegral=' + resultado.sucessoIntegral +
               ' | sucessoParcial=' + resultado.sucessoParcial +
               ' | pendencia=' + resultado.pendencia +
               ' | falha=' + resultado.falha +
               ' | aplicarLabelPermitido=' + resultado.aplicarLabelPermitido);
  } catch (erro) {
    Logger.log('[ADMIN] Execução administrativa falhou — erro=' + erro.message);
    throw erro;
  } finally {
    props.setProperty('ADMIN_EXECUTION_ENABLED', 'false');
    if (gotLock) lock.releaseLock();
  }
}

// ───────────────────────────────────────────────────────────────────────────
// GATILHO AUTOMÁTICO (Time-driven Trigger) — roda processarEmails() a cada hora
// ───────────────────────────────────────────────────────────────────────────

/**
 * Cria o gatilho horário de processarEmails(). Idempotente: remove qualquer
 * gatilho anterior da mesma função antes de criar, para nunca duplicar.
 * Rode esta função UMA vez (script.google.com → criarGatilhoHorario → Executar)
 * e autorize as permissões quando solicitado.
 */
function criarGatilhoHorario() {
  removerGatilhos(); // evita gatilhos duplicados
  ScriptApp.newTrigger('processarEmails')
    .timeBased()
    .everyHours(1)
    .create();
  Logger.log('Gatilho horário criado: processarEmails() roda a cada 1 hora.');
}

/** Remove todos os gatilhos da função processarEmails (para desarmar/recriar). */
function removerGatilhos() {
  var gatilhos = ScriptApp.getProjectTriggers();
  var removidos = 0;
  for (var i = 0; i < gatilhos.length; i++) {
    if (gatilhos[i].getHandlerFunction() === 'processarEmails') {
      ScriptApp.deleteTrigger(gatilhos[i]);
      removidos++;
    }
  }
  Logger.log('Gatilhos removidos: ' + removidos);
}

/** Lista os gatilhos ativos (diagnóstico). */
function listarGatilhos() {
  var gatilhos = ScriptApp.getProjectTriggers();
  Logger.log('Total de gatilhos: ' + gatilhos.length);
  for (var i = 0; i < gatilhos.length; i++) {
    Logger.log('- ' + gatilhos[i].getHandlerFunction() + ' / ' + gatilhos[i].getEventType());
  }
}

// ───────────────────────────────────────────────────────────────────────────
// VARREDURA HISTÓRICA (v2.29) — pesca PDFs mestres de Extrato/FGTS direto da
// caixa do contato@ e envia ao FATIADOR POR CLIENTE (/processar-doc-cliente).
// Não precisa baixar nada no PC: o Apps Script lê o anexo e manda pro servidor,
// que fatia por cliente e cria os registros nas abas Extratos Mensais / FGTS.
// ───────────────────────────────────────────────────────────────────────────

var FATIADOR_URL = 'https://magnata-holerite-splitter.onrender.com/processar-doc-cliente';
var GUIA_URL     = 'https://magnata-holerite-splitter.onrender.com/processar-guia';

/**
 * Busca e-mails por `query`, extrai os anexos PDF e envia cada um ao fatiador
 * com `tipo` ('extrato' | 'fgts') e `folhaMensal` (ex.: "Maio 2026").
 * Modo log: mostra cada PDF enviado e a resposta JSON do servidor (clientes
 * identificados / páginas sem cliente). Rode pelo editor (Executar) e veja
 * "Execuções / Ver registros". ATENÇÃO: cria registros no Airtable — rode 1x
 * por (tipo, folha); se repetir, é preciso deduplicar depois.
 */
// `filtroNome` (opcional): se informado, SÓ envia anexos cujo nome contenha
// esse texto (ex.: "extrato da folha") — mira cirúrgica no documento mestre.
// Utilities.sleep de 2s entre chamadas evita o 503 do Render grátis.
function fatiarDocsHistorico(query, tipo, folhaMensal, filtroNome) {
  // Macro 6A (correção de auditoria, achado #4): /processar-doc-cliente
  // passou a exigir X-API-KEY (mesma chave EMAIL_WEBHOOK_KEY já usada por
  // processarEmails() acima — sem segredo novo). Sem isso, a chamada abaixo
  // passa a devolver HTTP 401.
  var apiKey = PropertiesService.getScriptProperties().getProperty('EMAIL_WEBHOOK_KEY');
  if (!apiKey) {
    Logger.log('ERRO: API key não configurada. Rode runSetup() primeiro.');
    return;
  }
  var alvo = filtroNome ? filtroNome.toLowerCase() : null;
  var threads = GmailApp.search(query);
  Logger.log('Query: ' + query + ' | threads: ' + threads.length + (alvo ? ' | filtroNome: "' + alvo + '"' : ''));
  var enviados = 0;
  for (var t = 0; t < threads.length; t++) {
    var msgs = threads[t].getMessages();
    for (var m = 0; m < msgs.length; m++) {
      var atts = msgs[m].getAttachments({ includeInlineImages: false, includeAttachments: true });
      for (var a = 0; a < atts.length; a++) {
        var att = atts[a];
        var nome = att.getName().toLowerCase();
        if (att.getContentType() !== 'application/pdf' && !nome.endsWith('.pdf')) continue;
        if (alvo && nome.indexOf(alvo) === -1) continue;   // mira por nome do arquivo
        var resp = UrlFetchApp.fetch(FATIADOR_URL, {
          method: 'post',
          headers: { 'X-API-KEY': apiKey },
          payload: { pdf: att.copyBlob(), tipo: tipo, folha_mensal: folhaMensal },
          muteHttpExceptions: true,
        });
        Logger.log('[' + folhaMensal + '/' + tipo + '] ' + att.getName() +
                   ' -> HTTP ' + resp.getResponseCode() + ': ' +
                   resp.getContentText().substring(0, 600));
        enviados++;
        Utilities.sleep(2000);   // respiro p/ o Render grátis não dar 503
      }
    }
  }
  Logger.log('Total de PDFs enviados ao fatiador: ' + enviados);
}

// ── Atalhos prontos (Savian) — rode 1 por vez e confira os registros ─────────
function fatiarFGTS_Maio() {
  fatiarDocsHistorico(
    'from:jaqueline@saviancontabilidade.com.br subject:FGTSDIGITAL after:2026/05/25 before:2026/06/10',
    'fgts', 'Maio 2026');
}
function fatiarFGTS_Abril() {
  fatiarDocsHistorico(
    'from:jaqueline@saviancontabilidade.com.br subject:FGTSDIGITAL after:2026/05/01 before:2026/05/15',
    'fgts', 'Abril 2026');
}
// Mira cirúrgica: só anexos cujo NOME contém "extrato mensal".
function fatiarExtrato_Maio() {
  fatiarDocsHistorico(
    'from:jaqueline@saviancontabilidade.com.br has:attachment after:2026/05/25 before:2026/06/16',
    'extrato', 'Maio 2026', 'extrato mensal');
}
function fatiarExtrato_Abril() {
  fatiarDocsHistorico(
    'from:jaqueline@saviancontabilidade.com.br has:attachment after:2026/05/01 before:2026/05/25',
    'extrato', 'Abril 2026', 'extrato mensal');
}

/**
 * Captura GUIAS/COMPROVANTES comuns (INSS, DCTFWeb, PIS/COFINS) — documento
 * único broadcast (vai p/ TODOS os clientes). Cria 1 registro por PDF na aba
 * Guias e Comprovantes. O log mostra o record_id de cada um — anote-os para
 * usar em "guias_ids" no /gerar-fila-envios-email.
 */
function capturarGuias(query, tipoGuia, folhaMensal) {
  // Macro 6A (correção de auditoria, achado #4): /processar-guia passou a
  // exigir X-API-KEY (mesma chave EMAIL_WEBHOOK_KEY já usada por
  // processarEmails() acima — sem segredo novo). Sem isso, a chamada abaixo
  // passa a devolver HTTP 401.
  var apiKey = PropertiesService.getScriptProperties().getProperty('EMAIL_WEBHOOK_KEY');
  if (!apiKey) {
    Logger.log('ERRO: API key não configurada. Rode runSetup() primeiro.');
    return;
  }
  var threads = GmailApp.search(query);
  Logger.log('Query: ' + query + ' | threads: ' + threads.length);
  var ids = [];
  for (var t = 0; t < threads.length; t++) {
    var msgs = threads[t].getMessages();
    for (var m = 0; m < msgs.length; m++) {
      var atts = msgs[m].getAttachments({ includeInlineImages: false, includeAttachments: true });
      for (var a = 0; a < atts.length; a++) {
        var att = atts[a];
        var nome = att.getName().toLowerCase();
        if (att.getContentType() !== 'application/pdf' && !nome.endsWith('.pdf')) continue;
        var resp = UrlFetchApp.fetch(GUIA_URL, {
          method: 'post',
          headers: { 'X-API-KEY': apiKey },
          payload: { pdf: att.copyBlob(), tipo: tipoGuia || '', nome: att.getName(), folha_mensal: folhaMensal || '' },
          muteHttpExceptions: true,
        });
        var body = resp.getContentText();
        Logger.log('[GUIA ' + (tipoGuia || '') + '] ' + att.getName() +
                   ' -> HTTP ' + resp.getResponseCode() + ': ' + body.substring(0, 300));
        try { var j = JSON.parse(body); if (j.record_id) ids.push(j.record_id); } catch (e) {}
      }
    }
  }
  Logger.log('record_ids das guias criadas (use em guias_ids): ' + JSON.stringify(ids));
}

function capturarGuias_DCTFWeb_Abril() {
  capturarGuias('from:saviancontabilidade.com.br has:attachment DCTFWEB after:2026/05/01 before:2026/05/31', 'DCTFWeb', 'Abril 2026');
}
function capturarGuias_PisCofins_Abril() {
  capturarGuias('from:saviancontabilidade.com.br has:attachment ("PIS E COFINS" OR PIS OR COFINS) after:2026/05/01 before:2026/05/31', 'PIS/COFINS', 'Abril 2026');
}
function capturarGuias_DCTFWeb_Maio() {
  capturarGuias('from:saviancontabilidade.com.br has:attachment DCTFWEB after:2026/06/01 before:2026/06/30', 'DCTFWeb', 'Maio 2026');
}
function capturarGuias_PisCofins_Maio() {
  capturarGuias('from:saviancontabilidade.com.br has:attachment ("PIS E COFINS" OR PIS OR COFINS) after:2026/06/01 before:2026/06/30', 'PIS/COFINS', 'Maio 2026');
}
