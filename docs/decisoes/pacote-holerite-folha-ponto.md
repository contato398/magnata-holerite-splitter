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

## Macro de fechamento — correções antes da publicação

Revisão adversarial exigida por comando do usuário encontrou 2 falhas
materiais na entrega inicial e ambas foram corrigidas **antes** do push
(nunca depois — a entrega anterior invertia essa ordem, ver histórico da
sessão):

1. **Vínculo ativo checado nos 3 pontos exigidos**, não só um:
   preparação/dry-run, imediatamente antes do disparo por WhatsApp, e
   imediatamente antes de concluir a assinatura
   (`_status_funcionario_elegivel`). Colaborador
   desligado/inativo/suspenso/status ausente ou desconhecido bloqueia em
   qualquer um dos 3 — nunca por lista fixa de nomes. Mudança de status
   entre pontos invalida o pacote (`Cancelado`) em vez de assinar; a
   idempotência já existente impede que uma reexecução ressuscite ou
   reenvie automaticamente esse pacote depois disso.
2. **Ordem de escrita da confirmação corrigida**: a versão anterior
   gravava `Status=Assinado` incondicionalmente antes de tentar carimbar
   os 2 documentos — uma falha parcial (hash trocado, upload incompleto,
   exceção no carimbo) deixava o pacote marcado como concluído mesmo sem
   ter concluído nada. `_confirmar_assinatura_pacote_holerite_ponto`
   agora grava `Assinado` numa única chamada final, junto com os anexos e
   evidências, só depois que os 2 documentos foram revalidados por hash,
   carimbados, e o comprovante gerado e persistido.

Também fechado nesta revisão:

- **Idempotência com o casing real**: a versão anterior comparava contra
  nomes ALL-CAPS aspiracionais (`ESTADOS_ASSINATURA`) que nenhum caminho
  real do sistema escreve — a proteção contra duplicação nunca disparava
  de fato contra dado real. Corrigido para o casing que a confirmação
  compartilhada e o reenvio genérico realmente gravam (`PREPARADO`,
  `Pendente`, `FALHA_ENVIO`, `Assinado`, `Expirado`, `Cancelado`).
- **Reenvio do pacote** (`_reenviar_pacote_holerite_ponto`): extensão
  isolada do mecanismo genérico já existente
  (`/assinatura/processar-reenvios`) para o tipo `HOLERITE_FOLHA_PONTO` —
  reaproveita a mesma transação/chave (nunca cria uma 2ª assinatura),
  revalida vínculo e os 2 hashes originais antes de reenviar, respeita um
  limite de tentativas (contador embutido em `Evidencias_Assinatura`,
  sem campo novo no Airtable), e não altera nenhuma linha do reenvio de
  Kit Admissão/Rescisão/EPI/Contratos/Folha de Ponto isolada.
- Página de assinatura com `Status=Cancelado` deixa de mostrar o
  formulário de CPF — uma retentativa nunca teria efeito, o vínculo já
  invalidou o pacote.

### Backlog de "34 elegíveis, nunca enviados" — provisório, não confirmado

A auditoria anterior classificou 34 colaboradores como backlog por
"nunca teve nenhum Envio/Assinatura no histórico" — isso **não** é o
mesmo que "nunca recebeu a competência atual". `scripts/
reconciliacao_backlog_holerite_ponto.py` implementa a reconciliação
correta (por colaborador ativo + competência extraída de cada PDF + tipo
+ Record ID + hash íntegro + envio/assinatura **dessa** competência
específica), mas não foi executado contra dado real nesta sessão — o
sandbox não tem `AIRTABLE_API_KEY` real nem acesso de rede ao Render de
produção. O número "34" permanece **provisório** até execução real
(comando exato na docstring de `main()` do script).
