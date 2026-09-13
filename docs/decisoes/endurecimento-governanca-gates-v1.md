# Endurecimento da governança contra autocontorno — V1

**Data:** 2026-09-12

**Base:** `main@48801350cc978e1695a26873744cfad12cbdba22` (PR #154)

**Estado:** código publicado em PR (#155), aguardando revisão humana —
nenhum required status check adicionado ao ruleset, nenhuma configuração de
GitHub alterada, nenhum merge realizado por esta sessão. A criação e
proteção do Environment `governance-approval` (required reviewer
`@contato398`, `Prevent self-review` desligado, ausência de secret) foi
**confirmada humanamente no Chat Projeto** — essa confirmação **não foi
verificada pela sessão automatizada** (nenhuma ferramenta de leitura de
Environments/Settings do GitHub esteve disponível nela); é registrada
aqui como confirmação humana, não como checagem técnica desta sessão. O
ruleset `Protect main` continua sem o novo check — isso só acontece depois
da PR de teste real (seção 9, passos 6-12).

## 1. Problema

Os 16 gates de `scripts/ci/validate_governance.sh`, acionados por
`.github/workflows/magnata-governance.yml` (evento `pull_request`), são hoje
a única camada de governança não contornável **por um agente local** — não
podem ser puladas com um simples `git commit --no-verify`, porque rodam
server-side. Mas nenhum desses gates, nem o próprio workflow, nem
`.magnata/patterns.sh` que os alimenta, protegem **a si mesmos**: nenhum
arquivo de governança tem hoje um gate dedicado que impeça sua própria
alteração silenciosa.

## 2. Ameaça de autocontorno

`magnata-governance.yml` dispara por `pull_request` simples. Para esse
evento, quando a PR é da mesma repositório (não de um fork externo), o
GitHub executa a versão do workflow **presente no `head` da própria PR** —
não a versão de `main`. Isso significa que uma PR que altere
`validate_governance.sh` (por exemplo, para sempre retornar sucesso),
`.magnata/patterns.sh` (para retirar caminhos protegidos) ou o próprio
`magnata-governance.yml` (para não executar um gate) passaria a ser avaliada
**pela própria versão alterada** — o verificador e o verificado mudando
juntos no mesmo commit.

Seis cenários concretos foram usados como critério de aceite desta decisão:

1. PR altera `validate_governance.sh` para sempre retornar sucesso.
2. PR altera `magnata-governance.yml` para não executar o gate.
3. PR altera `.magnata/patterns.sh` para retirar caminhos protegidos.
4. PR altera o próprio mecanismo de autorização.
5. PR altera testes para mascarar regressões.
6. PR altera verificador + autorização + testes simultaneamente, tentando
   ficar verde sozinha.

## 3. Por que `pull_request` normal não basta para proteger o próprio verificador

Qualquer gate escrito **dentro** de `validate_governance.sh` (rodando sob
`pull_request`) herda o mesmo problema: se ele avalia o `head`, e o `head`
pode alterar o próprio gate que o avalia, a garantia é circular. Não existe
extensão dos 16 gates existentes que resolva isso sozinha — a proteção
precisa vir de **fora** do que o diff da PR controla.

## 4. Decisão: detector separado em `pull_request_target`

Criado `.github/workflows/governance-gate.yml`, um workflow pequeno e
independente, disparado por `pull_request_target` (nunca `pull_request`).
Para este evento, o GitHub executa o workflow definido na **base** (branch
padrão) — nunca a versão do `head` — por desenho da própria plataforma, não
por uma convenção interna deste repositório.

O detector:

- nunca faz checkout do `head` da PR;
- só compara **nomes de arquivo** entre `base` e `head`, via `git diff
  --no-renames --name-only` — dado textual, nunca código executado
  (`--no-renames` é obrigatório: sem essa flag, um rename de alta
  similaridade colapsaria a saída numa única linha só com o caminho
  novo, deixando o caminho crítico antigo de aparecer como alterado —
  achado de uma Ultrareview posterior a esta decisão, corrigido
  diretamente no workflow);
- usa uma lista de caminhos críticos **hardcoded no próprio arquivo**
  (garantido vir da base pelo mecanismo do `pull_request_target`), nunca
  lida de `.magnata/patterns.sh` do `head` — isso resolve especificamente o
  cenário 3;
- se nenhum caminho crítico mudou, aprova sem fricção — PRs comuns não
  ganham nenhuma barreira nova;
- se algum caminho crítico mudou, exige aprovação humana externa ao diff
  (seção 6).

## 5. Regra absoluta de não executar código do `head`

Dentro de `governance-gate.yml`, é proibido, sem exceção:

- checkout do `head`;
- `run:` de script, Python, shell, Makefile ou Action local vindos do
  `head`;
- `source` de arquivo do `head`;
- `eval`;
- interpolação de conteúdo arbitrário da PR diretamente como comando shell;
- dependência cuja definição venha do `head`;
- uso de `secrets.*`;
- qualquer permissão além de `contents: read`.

Os dois únicos valores vindos do evento da PR usados no workflow —
`base.sha` e `head.sha` — são hashes de commit (40 caracteres hexadecimais,
formato fechado do Git), passados via bloco `env:` para variáveis de
ambiente do shell, nunca interpolados diretamente dentro do corpo do script
`run:` — prática recomendada para `pull_request_target` mesmo quando o
valor é tecnicamente um formato fechado, para não depender dessa garantia
sozinha.

**Correção explícita de uma ideia anterior**: uma versão anterior deste
plano (Ultraplan) cogitava rodar `test_governance.sh` de `main` **contra**
`validate_governance.sh` do `head`, como sinal cruzado. Isso foi
**descartado nesta implementação**, por instrução expressa do Chat Projeto:
rodar `test_governance.sh` significa **executar** um script Bash — mesmo
que a cópia de `main` seja "confiável", o alvo da execução
(`validate_governance.sh` do `head`) continuaria sendo código do `head`
executado em contexto do `pull_request_target`, exatamente o que a regra
desta seção proíbe. O detector final não executa nada do `head` — só
compara texto.

## 6. Autorização humana externa ao diff — Environment `governance-approval`

Um arquivo de autorização (`.gitblob`, manifesto, label commitada) versionado
**dentro da mesma PR** não é prova independente suficiente: a mesma PR que
altera a governança poderia, no mesmo commit, criar sua própria autorização.
Esse é exatamente o padrão hoje usado para `.magnata/migration-authorizations/`
— aceitável ali porque migrations reais têm camadas externas próprias
(confirmação de PITR, decisão registrada, DDL aplicado manualmente sob
autorização de fase separada), mas **não generalizável** para a governança
do próprio repositório, que não tem esse tipo de camada externa equivalente.

A autorização escolhida vive **fora do conteúdo versionado**: um GitHub
**Environment** chamado `governance-approval`, com **required reviewers**.
Diferença técnica decisiva frente a "Require review from Code Owners"
(seção 7): o GitHub **não** aplica a regra "não pode aprovar a própria PR"
às aprovações de Environment — um único reviewer cadastrado pode aprovar
sua própria execução. Isso resolve o problema de autorização externa **sem**
exigir um segundo humano que hoje não existe.

Configuração planejada (não executada nesta missão):

- Environment: `governance-approval`;
- required reviewer: `@contato398`;
- `prevent_self_review = false` (deliberado — increment 12 explica por
  quê: com 1 humano, `true` causaria lockout total);
- nenhum secret associado ao Environment.

## 7. CODEOWNERS — auditabilidade, não separação de deveres

`.github/CODEOWNERS` foi criado cobrindo os mesmos caminhos críticos,
apontando para `@contato398`. Sua função nesta fase é **exclusivamente**
notificação automática de review e o selo "Code Owner" visível na PR —
**não** ativa "Require review from Code Owners" no ruleset `Protect main`,
e não deveria ser lido como se isso já estivesse em vigor.

**Limitação explícita, não escondida**: com um único mantenedor real,
CODEOWNERS não cria separação de deveres nenhuma — o dono de todos os
caminhos é a mesma pessoa que abre qualquer PR. Ligar "Require review from
Code Owners" hoje causaria lockout total sobre exatamente os caminhos mais
importantes (o GitHub recusa a aprovação de um usuário sobre a própria PR).
Essa flag só deveria ser considerada quando existir um segundo revisor real
e distinto — humano adicional ou um mecanismo de revisão automatizada cuja
aprovação não dependa do mesmo ator que fez o commit — nunca antes disso.

## 8. Interação com o ruleset `Protect main`

Nenhuma mudança na regra de PR obrigatório, no bloqueio de force-push ou no
bloqueio de exclusão de `main` — todas permanecem como já configuradas
(fora do escopo desta missão, que não altera configuração de GitHub). O
novo workflow **não é**, nesta implementação, marcado como required status
check — isso é parte da sequência de ativação (seção 9), posterior e
externa a esta missão.

## 9. Sequência segura de ativação (documentada, não executada nesta missão)

**Correção aplicada nesta revisão**: a ordem original desta seção previa
mesclar o workflow em `main` *antes* de criar o Environment
`governance-approval`. Isso é inseguro: o GitHub **cria automaticamente**
um Environment inexistente na primeira vez que um workflow o referencia —
e esse Environment nasce **sem nenhuma protection rule**, ou seja, sem
required reviewer, aprovando sozinho, sem fricção nenhuma. Se o workflow
fosse mesclado primeiro, a primeira PR real que tocasse um caminho crítico
criaria `governance-approval` desprotegido e passaria verde sem nenhuma
aprovação humana — exatamente o oposto do que esta decisão pretende
garantir. A ordem corrigida abaixo elimina essa janela: o Environment
existe e já está protegido **antes** de o workflow que o referencia sequer
chegar à `main`.

1. Criar previamente, nas Settings do GitHub, o Environment
   `governance-approval` — **antes** de qualquer merge do código desta
   missão.
2. Configurar `@contato398` como required reviewer desse Environment.
3. Confirmar `Prevent self-review` **desligado** para esse Environment.
4. Confirmar que nenhum secret está associado a esse Environment.
5. **Só então** publicar/mesclar o workflow `governance-gate.yml` (junto
   com CODEOWNERS, esta decisão e o doc de CI) em `main` — o Environment
   já protegido está pronto para recebê-lo desde a primeira execução.
6. Abrir uma PR de teste controlada que toque um caminho de governança
   (por exemplo, um comentário inofensivo em `.magnata/patterns.sh`).
7. Confirmar que o job `governance-approval` fica em estado `Waiting`
   (aguardando aprovação) na aba Actions — nunca verde sozinho.
8. Realizar a aprovação humana manualmente, para essa execução específica.
9. Confirmar que o check só fica verde depois da aprovação.
10. Testar uma PR comum (que não toque caminho crítico) — deve passar sem
    nenhuma aprovação pendente.
11. Testar uma PR de governança sem aprovar o Environment — deve
    permanecer pendente/vermelha até a aprovação.
12. **Só então** adicionar `governance-gate / governance-approval` (ou o
    nome exato do job) à lista de required status checks do ruleset
    `Protect main`.

Esta ordem evita dois riscos distintos, ambos de lockout inverso (governança
ausente, não travada): (a) o Environment nascer desprotegido por
autocriação do GitHub, se o workflow chegasse à `main` primeiro; e (b) um
check ser marcado obrigatório antes de provar, com uma PR real, que o
fluxo completo (Environment protegido → detecção → `Waiting` → aprovação →
verde) funciona de ponta a ponta (risco já descrito na versão anterior
desta seção, mantido).

## 10. O que este endurecimento não faz (perímetro preservado)

Esta fase não modifica nem conecta:

- `app.py`;
- `.magnata/patterns.sh`, `scripts/ci/validate_governance.sh`,
  `scripts/ci/test_governance.sh` (lidos, nunca alterados);
- `.githooks/**` (lidos, nunca alterados);
- qualquer migration real (0001-0006, todas continuam no mesmo estado);
- frontend, Render, Airtable, WhatsApp/Evolution, Postgres funcional;
- o ruleset `Protect main` em si (nenhuma configuração de GitHub foi
  tocada nesta missão).

## 11. Caminhos considerados e deliberadamente deixados de fora

- `requirements.txt` / cadeia de dependências Python: risco real de
  supply-chain, mas de natureza diferente (execução de código de terceiro
  via `pip install`, não alteração de lógica de gate) — fora do escopo
  desta decisão, registrado como possível fase futura separada.
- `docs/magnata-os/*.md` (incluindo o próprio
  `MAGNATA_AI_CI_GOVERNANCA.md`): documentação normativa, não enforcement
  executável — alterar prosa não enfraquece nenhum gate tecnicamente.
  Mantido fora da lista crítica do detector.

## 12. Risco de lockout

- **PRs comuns**: nenhum — o detector nem aciona o job de aprovação se
  nenhum caminho crítico mudou.
- **PRs de governança, com o único humano existente**: nenhum — aprovação
  de Environment não tem a trava "não pode aprovar a própria PR" que existe
  para review de PR; o mesmo `@contato398` pode aprovar seu próprio job,
  sempre, com um clique explícito.
- **Cenário de pane** (Environment mal configurado, reviewer errado): não é
  lockout permanente — corrigível a qualquer momento nas Settings do
  GitHub, sem depender de nenhum PR ou commit.
- **Estado da criação/proteção do Environment**: confirmado humanamente no
  Chat Projeto que o Environment `governance-approval` foi criado e
  protegido (required reviewer `@contato398`, `Prevent self-review`
  desligado, sem secret) — **esta confirmação não foi verificada pela
  sessão automatizada** (nenhuma ferramenta de leitura de
  Environments/Settings do GitHub esteve disponível nela); é uma
  confirmação humana, registrada aqui como tal, não uma checagem técnica
  desta sessão. O ruleset `Protect main` **ainda não foi alterado** — o
  novo check só passa a ser required depois da PR de teste real (seção 9,
  passos 6-12).

## 13. Rollback

- `governance-gate.yml`: desativável via "Disable workflow" na aba Actions
  do GitHub, sem reverter nenhum código; remoção definitiva por PR normal.
- `.github/CODEOWNERS`: removível por PR normal — nunca é bloqueante
  nesta fase (sem "Require review from Code Owners" ligado).
- Se o check chegar a ser marcado "required" (fase futura) e precisar ser
  revertido: removível da lista de required checks nas Settings do
  GitHub, sem tocar em nenhum arquivo do repositório.
- Nenhuma mudança desta decisão é destrutiva a dado, histórico Git ou
  funcionalidade.

## 14. Gates ainda obrigatórios (decisão humana separada, fora desta missão)

Ordem vinculante — ver seção 9 para o porquê de cada precedência:

1. Criar o Environment `governance-approval` nas Settings do GitHub —
   **antes** de mesclar qualquer código desta missão em `main`, para que
   ele nunca seja autocriado desprotegido pelo próprio GitHub.
2. Configurar `@contato398` como required reviewer.
3. Confirmar `Prevent self-review` desligado.
4. Confirmar ausência de secret associado ao Environment.
5. **Só então** mesclar `governance-gate.yml` (+ CODEOWNERS + esta decisão
   + doc de CI) em `main`.
6. Executar a PR de teste controlada (seção 9, passos 6-9).
7. Adicionar o novo check à lista de required status checks do ruleset
   `Protect main`.
8. Testar os dois cenários finais (PR comum e PR de governança sem
   aprovação, seção 9 passos 10-11) antes de considerar a ativação
   completa.
