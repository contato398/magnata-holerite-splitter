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

// Modo de teste: true = não grava nada no Airtable, apenas retorna o que faria
var DRY_RUN = true;

// ───────────────────────────────────────────────────────────────────────────
// SETUP — rode uma vez para guardar a API key com segurança
// ───────────────────────────────────────────────────────────────────────────

function runSetup() {
  var apiKey = '02477d2f7d4e98a8384e576d8ee12f38a115944b3edf3180';
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

  var query = 'label:' + LABEL_ENTRADA + ' -label:' + LABEL_PROCESSADO;
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
