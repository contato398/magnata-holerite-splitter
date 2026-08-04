/**
 * Teste puro, sem Jest e sem mocks de GmailApp/UrlFetchApp/PropertiesService,
 * para interpretarRespostaWebhook_() dentro de apps_script_email_intake.gs.
 *
 * A função é extraída do arquivo .gs real (não duplicada aqui) via
 * casamento de chaves balanceadas, e avaliada isoladamente com
 * `new Function(...)` — ela não depende de nenhuma API do Google, então
 * roda em Node puro.
 *
 * Rodar: node test_interpretar_resposta_webhook.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');

function extrairFuncao(codigoFonte, nomeFuncao) {
  const marcador = 'function ' + nomeFuncao + '(';
  const inicio = codigoFonte.indexOf(marcador);
  if (inicio === -1) {
    throw new Error('Função "' + nomeFuncao + '" não encontrada no arquivo .gs.');
  }
  let i = codigoFonte.indexOf('{', inicio);
  let profundidade = 0;
  let fim = -1;
  for (; i < codigoFonte.length; i++) {
    if (codigoFonte[i] === '{') profundidade++;
    if (codigoFonte[i] === '}') {
      profundidade--;
      if (profundidade === 0) { fim = i + 1; break; }
    }
  }
  if (fim === -1) {
    throw new Error('Não foi possível encontrar o fim da função "' + nomeFuncao + '" (chaves desbalanceadas).');
  }
  return codigoFonte.slice(inicio, fim);
}

const gsPath = path.join(__dirname, 'apps_script_email_intake.gs');
const gsContent = fs.readFileSync(gsPath, 'utf8');
const funcSource = extrairFuncao(gsContent, 'interpretarRespostaWebhook_');
// eslint-disable-next-line no-new-func
const interpretarRespostaWebhook_ = new Function(funcSource + '\nreturn interpretarRespostaWebhook_;')();

let total = 0, falhas = 0;

function teste(nome, fn) {
  total++;
  try {
    fn();
    console.log('OK: ' + nome);
  } catch (erro) {
    falhas++;
    console.error('FALHOU: ' + nome + ' — ' + erro.message);
  }
}

// HTTP diferente de 200
teste('HTTP 500 com corpo HTML -> falha, sem tentar JSON.parse', function () {
  const r = interpretarRespostaWebhook_(500, '<html><body>Internal Server Error</body></html>');
  assert.strictEqual(r.falha, true);
  assert.strictEqual(r.jsonValido, false);
  assert.strictEqual(r.aplicarLabelPermitido, false);
});

// HTTP 200 com JSON inválido
teste('HTTP 200 com JSON inválido -> falha', function () {
  const r = interpretarRespostaWebhook_(200, 'nao é json');
  assert.strictEqual(r.falha, true);
  assert.strictEqual(r.jsonValido, false);
  assert.strictEqual(r.aplicarLabelPermitido, false);
});

// duplicado_message_id + dry_run true -> label proibido
teste('duplicado_message_id com dry_run=true -> aplicarLabelPermitido=false', function () {
  const body = JSON.stringify({
    status: 'ok', dry_run: true, message_id: 'x', anexos_processados: [],
    email_savian: { acao: 'duplicado_message_id', record_id: 'recX', gravado: false },
  });
  const r = interpretarRespostaWebhook_(200, body, 0);
  assert.strictEqual(r.duplicidadeIdempotente, true);
  assert.strictEqual(r.aplicarLabelPermitido, false);
});

// duplicado_message_id + dry_run false -> não prova sucesso integral dos anexos
teste('duplicado_message_id com dry_run=false -> aplicarLabelPermitido segue política atual, mas sucessoIntegral fica false', function () {
  const body = JSON.stringify({
    status: 'ok', dry_run: false, message_id: 'x', anexos_processados: [],
    email_savian: { acao: 'duplicado_message_id', record_id: 'recX', gravado: false },
  });
  const r = interpretarRespostaWebhook_(200, body, 4);
  assert.strictEqual(r.duplicidadeIdempotente, true);
  assert.strictEqual(r.aplicarLabelPermitido, true); // httpCode===200 && !dryRun — política atual preservada
  assert.strictEqual(r.sucessoIntegral, false); // duplicidade não prova conclusão dos anexos
});

// sucesso integral
teste('4 anexos sem erro nem pendência -> sucessoIntegral', function () {
  const anexos = [
    { nome_arquivo: 'a.pdf', arquivo_record_id: 'rec1', processar_record_id: 'rec2', pendencia: null },
    { nome_arquivo: 'b.pdf', arquivo_record_id: 'rec3', processar_record_id: 'rec4', pendencia: null },
    { nome_arquivo: 'c.pdf', acao: 'fatiado_por_cliente' },
    { nome_arquivo: 'd.pdf', acao: 'arquivado_guia_comprovante' },
  ];
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x', anexos_processados: anexos });
  const r = interpretarRespostaWebhook_(200, body, 4);
  assert.strictEqual(r.sucessoIntegral, true);
  assert.strictEqual(r.sucessoParcial, false);
  assert.strictEqual(r.pendencia, false);
  assert.strictEqual(r.falha, false);
  assert.strictEqual(r.aplicarLabelPermitido, true);
});

// sucesso parcial
teste('1 de 4 anexos com erro -> sucessoParcial', function () {
  const anexos = [
    { nome_arquivo: 'a.pdf', erro: 'base64 inválido: x' },
    { nome_arquivo: 'b.pdf', arquivo_record_id: 'rec3', processar_record_id: 'rec4', pendencia: null },
    { nome_arquivo: 'c.pdf', arquivo_record_id: 'rec5', processar_record_id: 'rec6', pendencia: null },
    { nome_arquivo: 'd.pdf', arquivo_record_id: 'rec7', processar_record_id: 'rec8', pendencia: null },
  ];
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x', anexos_processados: anexos });
  const r = interpretarRespostaWebhook_(200, body, 4);
  assert.strictEqual(r.sucessoParcial, true);
  assert.strictEqual(r.sucessoIntegral, false);
});

// pendência
teste('1 anexo com pendência, sem erro -> pendencia', function () {
  const anexos = [
    { nome_arquivo: 'a.pdf', arquivo_record_id: 'rec1', processar_record_id: 'rec2', pendencia: 'Documento não reconhecido', pendencia_record_id: 'rec9' },
  ];
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x', anexos_processados: anexos });
  const r = interpretarRespostaWebhook_(200, body, 1);
  assert.strictEqual(r.pendencia, true);
  assert.strictEqual(r.sucessoIntegral, false);
});

// todos com erro
teste('todos os anexos com erro -> falha', function () {
  const anexos = [
    { nome_arquivo: 'a.pdf', erro: 'base64 inválido' },
    { nome_arquivo: 'b.pdf', erro: 'base64 inválido' },
  ];
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x', anexos_processados: anexos });
  const r = interpretarRespostaWebhook_(200, body, 2);
  assert.strictEqual(r.falha, true);
});

// anexos_processados ausente
teste('anexos_processados ausente -> falha, estrutura inesperada', function () {
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x' });
  const r = interpretarRespostaWebhook_(200, body, 1);
  assert.strictEqual(r.falha, true);
  assert.strictEqual(r.aplicarLabelPermitido, false);
});

// anexos_processados vazio com contagem divergente do enviado
teste('anexos_processados vazio mas 4 foram enviados -> falha por inconsistência', function () {
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x', anexos_processados: [] });
  const r = interpretarRespostaWebhook_(200, body, 4);
  assert.strictEqual(r.falha, true);
  assert.strictEqual(r.aplicarLabelPermitido, false);
});

// item de anexo com estrutura inválida
teste('item de anexo não é objeto -> falha', function () {
  const body = JSON.stringify({ status: 'ok', dry_run: false, message_id: 'x', anexos_processados: ['nao-e-objeto'] });
  const r = interpretarRespostaWebhook_(200, body, 1);
  assert.strictEqual(r.falha, true);
  assert.strictEqual(r.aplicarLabelPermitido, false);
});

console.log('\n' + (total - falhas) + '/' + total + ' testes passaram.');
if (falhas > 0) {
  process.exit(1);
}
