# Decisão — Pacote atômico de assinatura: Holerite + Folha de Ponto

**Branch:** `fix/holerite-ponto-pacote-assinatura`
**Data:** 2026-08-12
**Status:** Implementado localmente, não publicado, não enviado a destinatário real.

## Contexto

Auditoria prévia (mesma sessão, antes desta implementação) encontrou:

- `HOLERITE` não estava na whitelist `TIPOS_DOCUMENTO_VALIDOS` da Assinatura
  Nativa (`app.py`, v3.6) — só `KIT_ADMISSAO`, `FOLHA_PONTO`, `FICHA_EPI`,
  `RESCISAO`, `CONTRATO_EXPERIENCIA`, `CONTRATO_TRABALHO`.
- 65 registros reais em "Assinaturas Digitais" com Tipo de Documento =
  "Holerite" (valor pré-v3.6, não canônico), Status = "Pendente" desde
  08–09/07/2026, permanentemente travados: o código atual não os aceita
  nem para reenvio, porque a whitelist bloqueia o tipo na origem.
- O fluxo de distribuição combinada (`_gerar_fila_envios_combinado` +
  `/disparar-fila-combinado`) produz apenas **recibo de leitura**
  (`/recibo/<hash>`) — nunca assinatura eletrônica com evidências.

## Decisão

Holerite **nunca** é assinável isolado. Passa a ser assinável **somente**
dentro de um pacote atômico com a Folha de Ponto da **mesma competência**,
numa única solicitação, um token, um comprovante — tipo canônico novo:
`HOLERITE_FOLHA_PONTO`.

Isto evita reabrir o mesmo problema estrutural dos 65 registros órfãos
(Holerite sem vínculo formal de competência a nenhum outro documento) e
segue o modelo pedido: 1 solicitação, 2 documentos vinculados, 2 hashes
SHA-256 integrais, 1 colaborador, 1 competência, 1 token, 1 comprovante,
2 PDFs carimbados, histórico único da transação.

## Alternativas consideradas e rejeitadas

1. **Adicionar `HOLERITE` sozinho à whitelist** — rejeitada: reabriria
   exatamente o problema que gerou os 65 registros órfãos (nenhum vínculo
   de competência garantido a um segundo documento).
2. **Consolidar os 2 PDFs num único arquivo físico (merge)** — rejeitada:
   o pedido explicitamente prefere manter os 2 documentos originais
   separados e vinculados, não fisicamente unidos; simplifica auditoria
   e evita reprocessamento de PDF em caso de erro em só um dos dois.
3. **Sistema paralelo (tabela nova, rota nova)** — rejeitada: viola
   "menor alteração coerente com a arquitetura existente" e duplicaria
   toda a lógica de idempotência/carimbo/comprovante já validada.

## Extensão de dado — sem migração de schema

A extensão reaproveita 100% a tabela "Assinaturas Digitais" e os 4 campos
v3.6 já reais no Airtable (`Arquivo Record ID`, `PDF SHA-256`, `Chave de
Idempotência`, `Request ID`). **Nenhum campo novo foi criado ou é
necessário no Airtable** — decisão deliberada para não cruzar o gate de
"migration/schema relevante" (`CLAUDE.md` §12-I, nunca dispensado por
autonomia). Convenção documentada em `app.py` (comentário da constante
`TIPO_PACOTE_HOLERITE_PONTO`): os 2 campos de texto livre passam a conter
os 2 valores separados por `|` (delimitador que nunca aparece num Record
ID do Airtable nem num hex SHA-256):

- `Arquivo Record ID` = `<rec_holerite>|<rec_folha_ponto>`
- `PDF SHA-256` = `<sha256_holerite>|<sha256_folha_ponto>`

Os 6 campos "PLACEHOLDER" já presentes em `app.py` desde antes desta Macro
(`F_ASS_FINALIDADE`, `F_ASS_VERSAO_FLUXO`, `F_ASS_STATUS_ENVIO`,
`F_ASS_TENTATIVAS_ENVIO`, `F_ASS_ULTIMO_ERRO_ENVIO`,
`F_ASS_REGISTRO_DUPLICADO_DE`) continuam sem uso — não fazem parte desta
extensão e não foram tocados.

## Terminologia

O mecanismo é descrito, em código e nos comprovantes gerados, como
**"assinatura eletrônica com evidências"** — nunca "assinatura digital
certificada ICP-Brasil". Não há comprovação técnica de certificado
digital neste mecanismo (confirmação por CPF + IP + timestamp + User-
Agent, base legal MP 2.200-2/2001 + Lei 14.063/2020).

## Risco residual declarado

Airtable não tem transação nem constraint único. Duas chamadas
concorrentes ao mesmo par de documentos podem, em tese, passar a checagem
de idempotência antes de qualquer uma criar o registro, resultando em 2
registros com a mesma chave (duplicidade de *registro*, não de *efeito*
sobre o colaborador, se o disparo de WhatsApp for serializado à parte).
Mitigação completa exigiria um lock externo (Redis, já usado pelo
Celery) — fora do escopo desta fase. O handler de confirmação
(`/assinatura/<hash>`) reduz a janela equivalente do lado da assinatura
com uma releitura do Status imediatamente antes de gravar "Assinado".

## Achado adicional corrigido nesta branch (fora do pacote, mesma função-padrão)

Durante a implementação, o teste do comprovante revelou que o cabeçalho
`"MAGNATA PORTARIA E SERVIÇOS LTDA — CNPJ..."` usa um em-dash (`—`) que
não existe em Latin-1 — `encode('latin-1', 'replace')` o substitui por
`"?"` no PDF final. Isso já acontecia na função de comprovante de
documento único, pré-existente e não tocada por esta Macro (`app.py`,
`_gerar_comprovante_assinatura_pdf`). Corrigido nas 4 ocorrências do
mesmo padrão (2 pré-existentes, 2 novas desta Macro) — troca de `—` por
`-`, sem nenhuma mudança de conteúdo jurídico ou de layout.
