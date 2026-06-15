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
      var msg = messages[m];

      // Só processa mensagens com pelo menos 1 anexo PDF
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
        continue;
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
        dry_run: DRY_RUN,
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
      Logger.log('HTTP ' + code + ': ' + body);

      // Só marca como processado se: sucesso (200) E não estamos em dry_run
      if (code === 200 && !DRY_RUN) {
        thread.addLabel(GmailApp.getUserLabelByName(LABEL_PROCESSADO));
      }
    }
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
