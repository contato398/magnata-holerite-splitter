# MATRIZ DE AUTONOMIA — o que age sozinho, o que propõe, o que para

**Etapa 12, 2026-08-23.** Requisito formalizado. Os 6 níveis abaixo não
são aspiração — cada um é mapeado contra uma capacidade que **já existe
e já foi exercitada** nesta linha de trabalho, ou marcado explicitamente
como não existente ainda.

---

## 1. Os 6 níveis

| Nível | Nome | Regra | Reversível exigido? |
|---|---|---|---|
| **0** | Observar | Lê estado, não registra nada | N/A |
| **1** | Detectar | Lê estado, registra divergência num snapshot próprio (AUTO_FACT/DERIVED) | N/A — é leitura |
| **2** | Classificar | Atribui severidade/categoria a uma divergência já detectada | N/A — é julgamento sobre dado já público |
| **3** | Propor | Redige a correção (diff, PR, texto), mas não a aplica | N/A — nada muda até alguém aceitar |
| **4** | Executar ação seguro/reversível | Aplica a mudança sozinho, **dentro de um perímetro pré-autorizado e nunca em HUMAN_DECISION** | **Sim, obrigatório** — só entra aqui o que um `git revert`/nova execução desfaz sem perda |
| **5** | Exigir autorização humana | Não executa sem confirmação em mensagem distinta (`CLAUDE.md` §6-e) | Geralmente não reversível, ou é HUMAN_DECISION/produção/dado real |

**Regra que nunca se dobra:** nenhuma ação de nível 4 pode escrever em
`DECISIONS.md`/`DIRECTIVES.md` (ver `TAXONOMIA_MEMORIA.md` §2), tocar
produção, Airtable, `app.py`, migration, secret ou qualquer item da
lista de `CLAUDE.md` §12-I. Cruzar qualquer um desses rebaixa a ação
para nível 5, sempre — não é uma exceção rara, é a definição do limite
do nível 4.

## 2. Mapeamento contra capacidades reais (não hipotéticas)

| Capacidade | Nível hoje | Evidência |
|---|---|---|
| `central_command_sensor.py` (sem `--atualizar`) | **0-1** | Lê `git`, compara com `ESTADO.json`, imprime divergência — nunca escreve |
| `central_command_sensor.py --atualizar --com-testes` | **4** | Escreve só `ESTADO.json` (AUTO_FACT), roda a suíte, nunca toca `app.py`/produção. Exercitado nesta sessão e na anterior (PR #41), sempre revertível por nova execução |
| `graphify_regenerar.sh --salvar` | **4** | Escreve só `ARQUITETURA_SNAPSHOT.json` (DERIVED), roda fora do repositório, trava sozinho se achar CPF real. Exercitado nesta sessão |
| Auditoria de PR (revalidar diff/CI/governança) | **1-2** | Lê e classifica; não altera nada |
| Rebase de branch + push para a própria branch do PR | **4** | Reversível (a branch pode ser recriada do commit original); nunca mexe em `main` diretamente; exercitado em PR #41 e #22 |
| Merge de PR **documental/sensor/teste isolado**, CI+governança verdes | **4** | Perímetro pré-autorizado explicitamente pelo usuário nesta linha de trabalho (§13/§19 das missões anteriores) — sempre revertível (`git revert` do merge commit). Exercitado em PR #41, #22, #44 |
| Merge de PR com mudança funcional de negócio, novo adapter de capacidade, ou decisão de direção formalizada | **5** | Mesmo tecnicamente seguro e reversível, cruza HUMAN_DECISION (introduz capacidade nova / registra decisão). Exercitado como nível 5 no PR #22 — parou para autorização mesmo estando `clean` e verde |
| Correção de `app.py` | **5**, sempre | `CLAUDE.md` §7 — sem exceção, nenhum nível abaixo de 5 é possível aqui por desenho |
| Escrita real no Airtable, envio de e-mail/WhatsApp, deploy, migration, provisionamento de banco | **5**, sempre | `CLAUDE.md` §6/§12-I — nunca dispensado por autonomia de fase |
| Um "motor" que recebe evento externo e decide ação sozinho | **Não existe** | Ver `ORQUESTRADOR.md` §6.2 — nenhum componente deste repositório hoje observa um evento de produção e reage sem uma sessão no meio |

## 3. Onde a matriz já foi testada nesta linha de trabalho — 3 casos reais

1. **Nível 4 correto:** PR #41 (correção do sensor) — aditivo, isolado,
   sem HUMAN_DECISION nova, mesclado sem pedir autorização adicional
   após o usuário autorizar a missão.
2. **Nível 5 corretamente identificado apesar de tecnicamente igual ao
   nível 4:** PR #22 (adapter de e-mail) — mesmo `clean`, CI verde,
   zero risco de produção, **não foi mesclado automaticamente** porque
   introduzia capacidade nova + formalizava uma decisão de direção.
   Ficou explícito no PR por quê. O usuário autorizou em mensagem
   distinta na missão seguinte.
3. **Nível 0-1 correto:** a resposta à mensagem "RETOMADA OFICIAL" desta
   mesma sessão — antes de agir sobre as afirmações da mensagem
   (PR #41, `central-command/`, Graphify), o estado real foi
   revalidado ao vivo (`git fetch`, `pull_request_read`) antes de
   qualquer ação de nível 4+.

## 4. O que falta para um nível 4 automático de verdade (sem sessão no meio)

Hoje **todo** nível 4 exercitado teve uma sessão (humana + assistida)
no meio decidindo quando rodar o script e quando dar push. Não existe
gatilho (cron, GitHub Action, webhook) que dispare
`central_command_sensor.py --atualizar` ou `graphify_regenerar.sh`
sozinho. Isso é uma lacuna real, registrada, não escondida:

- **O que impede hoje:** nenhum workflow de CI faz commit de volta em
  `main` — o padrão estabelecido é sempre PR + merge explícito (por
  sessão ou por decisão humana), nunca commit automático de bot. Mudar
  isso é uma decisão de governança nova (quem aprova um commit que
  ninguém revisou?), não uma correção técnica — fica registrado como
  gate humano em aberto, não implementado nesta etapa.
- **Onde entraria, se autorizado:** um novo job no
  `.github/workflows/`, rodando `--atualizar --com-testes` (nunca o
  Graphify, que não pode virar dependência de CI — `GRAPHIFY.md` §6
  restrição 3) em `push` para `main`, abrindo um PR automático (nunca
  commitando direto) para revisão humana do snapshot. Desenho, não
  implementado — decisão de arquitetura de CI nova, fora da autonomia
  desta missão.
