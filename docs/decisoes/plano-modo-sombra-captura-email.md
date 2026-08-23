# Plano — Modo sombra: validar `AdapterCapturaEmail` contra dado real

**Branch:** `fix/plano-modo-sombra-captura-email`
**Data:** 2026-08-24
**Status:** Proposta de plano — **não implementado, nenhuma conexão real
feita**. Aguardando autorização de fase (`CLAUDE.md` §6) antes de
qualquer ligação a Gmail real.

## Por que isto, agora

`AdapterCapturaEmail` (`magnata_os/documental/modulo01/adapters/email_captura.py`,
mesclado no PR #22) está em `main` desde 2026-08-23, testado com 10
casos, auditado adversarialmente — e **nunca foi exercitado contra
dado real**. É o único componente do Módulo 01 pronto para essa prova.

O risco de não fazer isto agora: o Magnata OS acumula fundação
(Central Command, sensores, Graphify, motor do Orquestrador — Etapas
1-12) sem nunca provar que o *strangler pattern* funciona de verdade
em pelo menos um caso. Modo sombra é o menor passo possível que gera
essa prova, sem qualquer risco ao caminho que já funciona (Gmail Apps
Script → `app.py`).

## Objetivo

Confirmar, com dado real, que `AdapterCapturaEmail` captura os mesmos
e-mails/anexos que o Apps Script captura hoje — **sem produzir nenhum
efeito colateral**: nenhuma escrita no Airtable, nenhum WhatsApp,
nenhum e-mail de saída, nenhuma mudança no comportamento do Apps
Script, nenhuma rota nova em `app.py`.

## O que "modo sombra" significa aqui, exatamente

| | Apps Script (legado, hoje) | Adapter (modo sombra, proposto) |
|---|---|---|
| Lê Gmail | Sim, escopo de leitura+label | Sim, **só leitura** (`gmail.readonly`) |
| Aplica label `Processado-Render` | Sim | **Nunca** |
| Chama `/email/webhook` (`app.py`) | Sim | **Nunca** |
| Escreve no Airtable | Sim (via `app.py`) | **Nunca** |
| Envia WhatsApp/e-mail | Não (é só captura) | **Nunca** |
| Onde persiste o resultado | Airtable (`Arquivos`, `Emails Savian`) | Só no Módulo 01 (Postgres/S3 quando ligado, ou repositório local de teste enquanto não houver Postgres real) |
| Pode ser desligado sem afetar produção | N/A | **Sim, a qualquer momento** — é 100% aditivo |

O adapter roda **em paralelo**, lê os mesmos e-mails, e o resultado só
é usado para **comparar contagens** — nunca para agir.

## Passo a passo proposto

### Fase 0 — decisão de fonte (Direção + esta sessão, antes de codificar)

Duas opções, ambas só leitura:

1. **Label dedicada no mesmo Gmail** que o Apps Script já usa — o
   adapter lê pelo filtro/label que hoje já chega ao Apps Script,
   nunca aplica nem remove nenhum label.
2. **Encaminhamento/BCC para uma caixa separada** dedicada ao teste —
   isola completamente do Gmail de produção, mas não reflete 100% o
   mesmo fluxo (mensagens encaminhadas podem perder cabeçalho
   original).

**Recomendação desta sessão: opção 1**, com escopo OAuth
estritamente `gmail.readonly` (nunca `gmail.modify` ou superior) — é
o que mais fielmente reproduz o que o Apps Script vê, com o menor
escopo de permissão tecnicamente possível.

### Fase 1 — implementar o `FonteMensagensEmail` real (código, sem conexão)

Uma implementação concreta do `Protocol` já definido em
`email_captura.py`, usando a Gmail API (`google-api-python-client`
ou equivalente), que:
- autentica com credencial de escopo `gmail.readonly` apenas;
- nunca chama nenhum metodo de escrita da API (`modify`, `trash`,
  `delete`, `send` — nenhum deles é sequer importado);
- converte mensagens em `MensagemEmailRecebida`/`AnexoEmailRecebido`
  (os tipos já existentes, sem mudança).

Isto **pode ser escrito e testado com um duplo de teste** (mesmo
padrão de `FonteMensagensEmailFalsa` já usado nos testes existentes)
**sem nenhuma credencial real** — só a implementação concreta, código
revisável, sem execução contra Gmail de verdade. Esta fase não cruza
nenhum gate — é código novo isolado, mesmo padrão de todo o Módulo 01.

### Fase 2 — execução real, controlada (GATE HUMANO — `CLAUDE.md` §6)

Só depois da Fase 1 revisada e com autorização de fase explícita,
cumprindo (a)-(f) de `CLAUDE.md` §6:

- **Objetivo e sistema autorizado:** especificamente Gmail, especificamente
  leitura (`gmail.readonly`) — não autoriza Airtable, WhatsApp, e-mail
  de saída, nem qualquer escrita, mesmo que pareça relacionado.
- **Limites:** um credential próprio, escopo mínimo, sem acesso a
  enviar/apagar/rotular; execução manual ou agendada, nunca contínua
  sem revisão nesta fase.
- **Critério de avanço:** N execuções sem erro, contagem batendo (ou
  divergência explicada) contra o Apps Script para a mesma janela.
- **Critério de interrupção:** qualquer chamada de escrita detectada
  (não deveria existir — o código não importa esses métodos, mas o
  critério fica explícito), qualquer erro de autenticação repetido,
  qualquer sinal de que o Apps Script foi afetado.
- **Rollback:** revogar o credential OAuth (paineis do Google Cloud/
  Workspace) — encerra o acesso de leitura imediatamente. Nada foi
  escrito, então não há dado para reverter.
- **O que continua proibido dentro desta fase, mesmo autorizada:**
  aplicar/remover label, chamar `/email/webhook`, escrever no
  Airtable, desligar ou modificar o Apps Script, enviar qualquer
  mensagem real.

### Fase 3 — comparação

Rodar por uma janela definida (ex.: 1-2 semanas), depois comparar:

```
contagem do Adapter (Documentos criados no Módulo 01, origem='email')
  x
contagem do Apps Script (linhas processadas com sucesso, mesma janela)
```

Divergência esperada e aceitável: zero. Qualquer divergência real vira
investigação — nunca "resolvida" ajustando um dos dois lados sem
entender a causa.

### Fase 4 — decisão (fora deste plano)

Com a prova em mãos, decisão separada e humana: o Módulo 01 assume a
captura de e-mail de verdade (desliga o Apps Script, gate de
`CLAUDE.md` §12-I — decisão empresarial/arquitetural irreversível), ou
o modo sombra continua rodando como verificação contínua, ou é
descontinuado. Este plano **não** decide isso — só produz a evidência
para decidir.

## Riscos e limites, declarados

- **Retry/backoff continua fora do adapter** (`PENDING.md` PEN-020) —
  quem chamar `capturar_novas_mensagens()` em produção/agendado decide
  a política; o adapter propaga falha de rede sem tratamento, por
  desenho.
- **PII no envelope de evento**: `remetente` e `assunto` são dado
  pessoal em potencial (endereço de e-mail, texto livre). Hoje ficam
  como metadados do lote/Documento no Módulo 01 — mesmo tratamento que
  o Airtable já dá para dado similar, mas **não auditado
  especificamente para LGPD nesta fase**. Se o modo sombra avançar
  além da Fase 3, isso precisa de revisão própria.
- **Onde isto roda**: não em produção (Render) — nenhum deploy novo
  necessário. Roda a partir de uma sessão/execução controlada, mesmo
  padrão já usado para o handoff de ativação do lote de Julho/2026.
- **Nível de autonomia** (`MATRIZ_AUTONOMIA.md`): qualquer evento que
  toque Gmail real é `TipoEvento` novo, sem política declarada — por
  desenho do fail-safe, **HUMAN_REQUIRED sempre**. O motor do
  Orquestrador (PR #46) nunca executaria isto sozinho, mesmo se
  alguém tentasse registrar essa Acao nele.

## O que este plano NÃO autoriza

Escrita real no Airtable, envio de e-mail/WhatsApp, alteração do Apps
Script, desligamento de qualquer caminho legado, deploy, migration,
qualquer escopo OAuth além de `gmail.readonly`. Nada disso está
autorizado por este documento — cada um exige autorização de fase
própria, separada, no momento em que for proposto.

## Próxima ação concreta

Se a Direção aprovar a Fase 0 (opção 1, label dedicada + escopo
`gmail.readonly`): implementar a Fase 1 (código, sem conexão real) em
branch própria, com testes — isso **não** exige autorização de fase
nova, é código isolado como qualquer outro no Módulo 01. A Fase 2
(execução real) fica para depois, com autorização própria.
