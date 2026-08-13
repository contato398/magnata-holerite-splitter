# ADR — Fiação HTTP do Módulo 01 (Documental) ao motor principal

**Branch:** `fix/adr-modulo01-http-wiring`
**Data:** 2026-08-13
**Status:** PROPOSTA — não aprovada, não implementada.

## Contexto

Auditoria arquitetônica desta sessão (ver relatório em conversa) encontrou:
`magnata_os/documental/modulo01/` e `magnata_os/documental/importacao_lote/`
existem como domínio completo e testado (5.051 linhas, 267 testes passando:
133 em `modulo01`, 134 em `importacao_lote`), mas **nenhuma rota Flask, nenhum
Blueprint, nenhum import a partir de `app.py`** — confirmado por
`grep -rn "magnata_os" app.py` (zero resultados) e
`grep -rn "Blueprint(" magnata_os/` (zero resultados). O módulo é
inatingível por qualquer requisição HTTP em produção hoje.

Duas descobertas adicionais, lendo o próprio código do módulo, tornam esta
decisão mais delicada do que "registrar um blueprint":

1. **`api/handlers.py` é deliberadamente framework-agnóstico.** Do próprio
   docstring: *"recebe tipos Python simples..., nunca um `Request` do Flask
   ou de qualquer outro framework, e devolve sempre um contrato de
   contratos.py... Um adapter web futuro (fora do escopo desta fase) é quem
   traduz HTTP <-> estes tipos."* Ou seja: os próprios autores do módulo já
   decidiram, por escrito, que a tradução HTTP é trabalho de uma fase
   futura ainda não construída — não é um passo mecânico de registrar algo
   que já existe pronto.
2. **`api/autorizacao.py` não tem autenticação real.** Do próprio
   docstring: *"SEM AUTENTICAÇÃO REAL NESTA FASE: `Sujeito` é um portador
   de perfil declarado pelo chamador, não o resultado de validar uma
   sessão, token ou senha."* Cada handler exige um `Perfil` (ex.:
   `GESTOR`), mas nada impede hoje que um adapter web ingênuo construa um
   `Sujeito` com o perfil que quiser. Expor isto via HTTP sem construir
   autenticação real primeiro seria um buraco de segurança trivial de
   explorar — qualquer chamador se autodeclara `GESTOR` e passa.

Adicionalmente: `render.yaml` declara um banco Postgres (`magnata-os-db`)
para os adapters de `modulo01`/`importacao_lote`, mas o próprio arquivo
documenta que ele **não foi provisionado** ("nenhum Blueprint foi rodado").
Não há `DATABASE_URL` real disponível hoje para os adapters de persistência
deste módulo funcionarem em produção, independentemente da fiação HTTP.

## Decisão a ser tomada

**Não decidida nesta ADR.** Este documento registra o problema, as opções e
uma recomendação — a aprovação da opção escolhida é um gate humano
separado (`CLAUDE.md` §2, §12-I), não algo que esta ADR resolve sozinha.

### Opções consideradas

**A — Blueprint novo, aditivo, namespace HTTP próprio (`/modulo01/*` ou
equivalente), coexistindo com as rotas legadas sem substituir nenhuma.**
Exige construir, como trabalho novo e explícito:
  - o "adapter web" que o próprio `handlers.py` já previu como fase futura
    (tradução `Request` Flask <-> `ContextoApi`/`Sujeito`/contratos);
  - autenticação real para `Sujeito` (ex.: reaproveitar o padrão
    `X-API-KEY` já usado no resto de `app.py`, mapeado para um `Perfil`
    fixo por chave, ou algo mais forte — decisão própria, não coberta
    aqui);
  - registro do Blueprint em `app.py` com um prefixo de URL isolado.

  Risco: baixo. Reversível: sim — remover a linha de registro do Blueprint
  não afeta nenhuma rota existente, porque nada legado é tocado.

**B — Uma rota legada existente (ex.: `/processar-holerites`) passa a
delegar parte da sua lógica para o domínio de `modulo01`.**
  Risco: alto — toca código de produção já validado por anos de uso real,
  sem necessidade técnica (o domínio novo não precisa substituir nada para
  ficar acessível). Não recomendada como primeiro passo.

**C — Serviço/processo separado para `modulo01`, fora do `app.py`/gunicorn
atual.**
  Risco: mudança de infraestrutura maior (novo processo, novo deploy, novo
  ponto de rede) sem benefício claro dado o estágio atual do projeto (um
  único worker gunicorn, sem service mesh). Não recomendada agora.

### Recomendação

**Opção A**, e só depois que 3 pré-condições estiverem satisfeitas:

1. Autenticação real para `Sujeito` implementada e testada (não apenas o
   Blueprint registrado) — sem isso, a Opção A reabre o mesmo risco que a
   Opção B, só que num namespace novo.
2. `DATABASE_URL` do Postgres declarado em `render.yaml` efetivamente
   provisionado — ou a primeira fase da fiação roda só contra o adapter
   Airtable existente (`airtable_leitura.py`/`airtable_escrita.py`),
   adiando Postgres para uma fase seguinte, decisão a registrar à parte.
3. Esta ADR aprovada por uma pessoa, numa mensagem distinta de quem a
   redigiu — mesmo princípio do gate de autorização por fase do `CLAUDE.md`
   §6-e, aplicado por analogia a decisão arquitetural (§2: "nenhuma decisão
   arquitetural é tomada em silêncio").

A implementação, quando autorizada, deve ocorrer em branch própria —
nem a branch desta ADR, nem `fix/lgpd-purga-mascara-cpf-tmp-cleanup`, nem
`fix/holerite-ponto-pacote-assinatura` — para não misturar 3 propósitos
distintos (`CLAUDE.md` §7, §9).

## Rollback

Opção A é aditiva por desenho: rollback = remover o registro do Blueprint
em `app.py` (1 linha) + a própria branch da implementação. Nenhuma rota
legada é alterada, então nenhum rollback de comportamento existente é
necessário.

## Risco residual declarado

Mesmo com autenticação real implementada, qualquer endpoint novo exposto
publicamente precisa da mesma revisão de segurança que qualquer rota de
`app.py` (rate limiting onde aplicável, validação de entrada, tratamento de
erro sem vazar detalhe interno — `erros.py` já cobre parte disso do lado do
domínio, mas o lado HTTP ainda não existe para revisar). Isto não é
"ligar um interruptor" — é construir e revisar uma superfície nova.
