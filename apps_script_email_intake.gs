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
  'dp.contabilidade1@hotmail.com',           // contador novo (Departamento Pessoal)
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
    'from:jaqueline@saviancontabilidade.com.br has:attachment after:2026/05/25 before:2026/06/15',
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
