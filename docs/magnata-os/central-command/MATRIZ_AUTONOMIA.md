# MATRIZ DE AUTONOMIA — o que age sozinho, o que propõe, o que para

**Etapa 14, 2026-08-24.** Reconciliada contra o código real em `main` após o merge do PR #52.

A regra operacional permanente é **automação por padrão, humano por exceção**: sempre que uma ação puder ser executada de forma interna, reversível, testável, auditável e dentro de um perímetro já autorizado, o sistema deve preferir executar sozinho. Humano entra apenas em gates reais — não como etapa obrigatória por hábito.

Essa preferência por automação **não elimina gates**. Produção, decisão humana formal, dados reais sensíveis, escrita estrutural em sistemas externos, secrets, migrações e ações destrutivas continuam exigindo autorização quando a política assim definir.

---

## 1. Os 6 níveis

| Nível | Nome | Regra | Reversível exigido? |
|---|---|---|---|
| **0** | Observar | Lê estado, não registra nada | N/A |
| **1** | Detectar | Lê estado, registra divergência num snapshot próprio (AUTO_FACT/DERIVED) | N/A — é leitura |
| **2** | Classificar | Atribui severidade/categoria a uma divergência já detectada | N/A — é julgamento sobre dado já público |
| **3** | Propor | Redige a correção (diff, PR, texto), mas não a aplica | N/A — nada muda até alguém aceitar |
| **4** | Executar ação segura/reversível | Aplica a mudança sozinho, **dentro de perímetro pré-autorizado e nunca em HUMAN_DECISION** | **Sim, obrigatório** |
| **5** | Exigir autorização humana | Não executa sem confirmação específica quando a política exigir | Geralmente não reversível, HUMAN_DECISION, produção ou dado real |

**Regra que nunca se dobra:** nenhuma ação de nível 4 pode escrever em `DECISIONS.md`/`DIRECTIVES.md`, tocar produção, `app.py`, migration, secret ou outro caminho protegido. O próprio motor valida caminhos proibidos em tempo de execução.

## 2. Mapeamento contra capacidades reais

| Capacidade | Nível hoje | Evidência |
|---|---|---|
| `central_command_sensor.py` sem atualização | **0-1** | Lê `git`, compara com `ESTADO.json`, detecta divergência |
| `central_command_sensor.py --atualizar --com-testes` | **4** | Atualiza AUTO_FACT e preserva baseline; reversível |
| Medição de contexto / stale detection | **1-4** | `medir_contexto.py` + sensor; AUTO_FACT compacto integrado ao Orquestrador no PR #52 |
| `graphify_regenerar.sh --salvar` | **4** | Atualiza DERIVED estrutural; uso seletivo, fora do CI |
| Auditoria de PR / diff / CI / governança | **1-2** | Lê e classifica sem alterar produção |
| Rebase de branch e correções internas na própria branch | **4** | Reversível e limitado ao escopo autorizado |
| Merge de PR documental/sensor/teste isolado, CI+governança verdes | **4 quando previamente autorizado** | Reversível por `git revert`; não cruza HUMAN_DECISION |
| Merge de mudança funcional de negócio ou decisão de direção | **5** | Introduz capacidade/decisão nova |
| Correção de `app.py` | **5**, sempre | Arquivo protegido |
| Escrita real no Airtable, envio de e-mail/WhatsApp, deploy, migration, provisionamento de banco | **5**, por padrão | Dados/produção externos; só muda se existir autorização explícita e política específica mais restrita |
| **Motor que recebe evento e decide ação** | ✅ **Existe** | `magnata_os/orquestrador/motor.py`: recebe `Evento`, deduplica, classifica autonomia, executa `EXECUTE_SAFE`, valida caminhos, registra estado e evidencia |
| **Persistência de execuções / idempotência / retry** | ✅ **Existe** | `repositorio_execucoes.py`, máquina de estados, classificação de falha e backoff |
| **Observabilidade / auditoria** | ✅ **Existe** | observador do motor + `AUDITORIA_ORQUESTRADOR.jsonl` |
| **Gatilho sem sessão humana** | ✅ **Existe parcialmente** | `.github/workflows/orquestrador-sensor.yml`: `schedule` a cada 6h + `workflow_dispatch`, executa `orquestrador_sensor_ci.py` |
| **Abertura automática de PR de AUTO_FACT** | 🟡 **Implementada, dependente de configuração externa** | workflow cria branch/commit/push e tenta `gh pr create`; o caminho depende da permissão do GitHub Actions para criar PR |

## 3. Casos reais que validam a matriz

1. **EXECUTE_SAFE real:** o motor processa `GIT_MAIN_AVANCOU` e atualiza AUTO_FACT usando ação registrada, sem escrever HUMAN_DECISION.
2. **Fail-safe real:** se a política disser `EXECUTE_SAFE` mas não houver ação registrada, o motor vai para `WAITING_GATE` em vez de inventar comportamento.
3. **Proteção em runtime:** se uma ação declarar escrita em caminho proibido, o motor marca falha final e levanta `AcaoProibida`.
4. **Idempotência:** evento terminal duplicado é ignorado; retry não reinicia o fluxo inteiro.
5. **Contexto progressivo:** após o PR #52, o Orquestrador persiste apenas resumo compacto de contexto; telemetria completa fica sob demanda para não auto-inflar o bootstrap.

## 4. Estado real da automação sem sessão

A afirmação antiga de que “não existe gatilho automático” está **SUPERADA**.

Hoje existe `orquestrador-sensor.yml`, com:

- `schedule` a cada 6 horas;
- `workflow_dispatch` para prova controlada;
- execução do motor real via `scripts/ci/orquestrador_sensor_ci.py`;
- detecção de mudança;
- branch/commit/push automáticos;
- tentativa de abrir PR de AUTO_FACT;
- concorrência serializada para evitar duas execuções simultâneas;
- idempotência entre execuções para não abrir PR duplicado do mesmo `main_sha`.

O que **ainda não está completo** não é o motor nem o gatilho. São os próximos níveis de autonomia operacional:

1. provar continuamente a abertura automática de PR no ambiente real do GitHub;
2. eliminar dependência de configuração externa que impeça o `gh pr create`;
3. tornar health/recovery persistentes onde ainda forem apenas memória de processo;
4. provar um E2E único: evento → motor → ação → validação → persistência → auditoria → atualização de memória;
5. adicionar novas fontes/eventos gradualmente, sempre com política explícita e fail-safe;
6. manter merge, produção e ações externas sensíveis como gates enquanto não houver política mais específica aprovada.

## 5. Princípio de desenho permanente — humano por exceção

Para o Magnata OS finalizado, o objetivo operacional não é “pedir aprovação para tudo”. É:

> **detectar sozinho → entender sozinho → agir sozinho quando seguro → validar sozinho → registrar sozinho → chamar humano apenas quando a decisão, o risco ou a irreversibilidade realmente exigirem.**

Consequências práticas:

- rotina repetitiva deve migrar para sensores, eventos e jobs;
- consultas devem preferir fontes canônicas e roteamento seletivo;
- ações seguras devem ser `EXECUTE_SAFE`, não “propor por padrão”;
- falha deve produzir evidência e estado, nunca silêncio;
- ausência de informação ou ação registrada deve virar gate seguro, nunca comportamento inventado;
- automação deve ser idempotente, observável e reversível;
- o humano deve receber **exceções e decisões**, não tarefas mecânicas.

## 6. Próximo marco de autonomia

A prioridade é consolidar **autonomia operacional contínua**, nesta ordem:

1. health persistente;
2. E2E completo e repetível do Orquestrador;
3. desbloqueio/prova da abertura automática de PR pelo GitHub Actions;
4. reconciliação automática de AUTO_FACT após mudanças em `main`;
5. novas integrações em modo sombra/read-only antes de qualquer escrita externa;
6. expansão gradual de tipos de evento com políticas de autonomia testadas.

Essa ordem prioriza capacidade permanente usada no dia a dia, não apenas facilidade de construção.