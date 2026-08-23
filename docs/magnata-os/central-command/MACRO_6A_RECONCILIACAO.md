# Macro 6A — reconciliação final da conversa como fonte legada

**Etapa 11 da Central Command, 2026-08-23.**

**Objetivo:** provar que a conversa Macro 6A não contém conhecimento
indispensável ainda não preservado no repositório.

**Isto não é resumo da conversa.** É uma tabela de reconciliação: cada
item com valor durável, classificado por onde já está — ou onde passou a
estar nesta etapa.

**Classificação:** `JÁ PRESERVADO` · `DUPLICADO` · `SUPERSEDED` ·
`FALTAVA INCORPORAR` · `AINDA PRECISA DE DECISÃO`

---

## 1. Decisões e arquitetura

| Item | Classificação | Onde está |
|---|---|---|
| Central Command como camada de memória consolidada | JÁ PRESERVADO | mestre · `INDEX.md` |
| Precedência de fontes em conflito | JÁ PRESERVADO | `ORQUESTRADOR.md` §6 |
| Camada de verdade por assunto | JÁ PRESERVADO | `ORQUESTRADOR.md` §3 |
| 8 núcleos de negócio classificados por evidência | JÁ PRESERVADO | `ORQUESTRADOR.md` §1 · mestre §13 |
| Modelo do banco próprio com temporalidade (`Alocação`) | JÁ PRESERVADO | `BANCO_PROPRIO_MODELO.md` |
| Desacoplamento do Airtable em 4 fases | JÁ PRESERVADO | `AIRTABLE_DESACOPLAMENTO.md` |
| Airtable **não** deve ser eliminado — só a dependência crítica | JÁ PRESERVADO | `BANCO_PROPRIO_MODELO.md` topo |
| Camada de memória sensível | JÁ PRESERVADO | `MEMORIA_SENSIVEL.md` |
| Graphify = sensor técnico, **não** memória de decisão | JÁ PRESERVADO | `GRAPHIFY.md` · reafirmado em §5 aqui |
| `Documento` (código) vs. `Item de Ingestão` (docs) | AINDA PRECISA DE DECISÃO | `CLAUDE.md` §5 — ADR pendente |
| `Locais` = `Posto de Trabalho`? | AINDA PRECISA DE DECISÃO | `BANCO_PROPRIO_MODELO.md` §8.3 |

## 2. Bugs, correções e o que não pode se repetir

| Item | Classificação | Onde está |
|---|---|---|
| Correção do vínculo sem PII no motivo (PR #33) | JÁ PRESERVADO | `app.py` + `.gitblob` de autorização |
| CI de testes ativo (PR #34) | JÁ PRESERVADO | `.github/workflows/magnata-testes.yml` |
| **O CI achou o próprio defeito** (`import importlib.util`) | JÁ PRESERVADO | mestre §0-F.2 |
| Falso positivo do detector de acoplamento (adapter ≠ violação) | JÁ PRESERVADO | `scripts/ci/graphify_snapshot.py` |
| Guarda de PII bloqueava CPF sintético — refinada por dígito verificador | JÁ PRESERVADO | `scripts/ci/graphify_regenerar.sh` |
| Meu CPF substituto inicial era **matematicamente válido** | JÁ PRESERVADO | corpo do PR #38 |
| Escorregão de escopo por `git add -A` (PR #35) | JÁ PRESERVADO | mestre §0-F.6 |
| Sensor apagava a baseline de testes em silêncio | **FALTAVA INCORPORAR** | → PR #41, `scripts/ci/test_central_command_sensor.py` |
| **Teste que não pega o defeito que diz cobrir** | **FALTAVA INCORPORAR** | → §4 aqui e corpo do PR #41 |
| Heurístico de PII com falso positivo (`TEXTO_CARTAO_PONTO_REAL`) | **FALTAVA INCORPORAR** | → `PII_HISTORICO_PLANO.md` §1.1 |
| #38 removeu o CPF e **deixou o nome real** | **FALTAVA INCORPORAR** | → corrigido em `b12d94d`; §4 aqui |

## 3. Airtable, integrações e produção

| Item | Classificação | Onde está |
|---|---|---|
| 31 tabelas, 13 automações, densidade de fórmulas | JÁ PRESERVADO | `AIRTABLE_LOGICA_OCULTA.md` §1-§4 |
| 72% de `Folha de Ponto` calculado dentro do Airtable | JÁ PRESERVADO | `BANCO_PROPRIO_MODELO.md` §2 |
| `PROCESSAR ARQUIVOS` → webhook Make.com sem tratamento de erro | JÁ PRESERVADO | ANEXO A §A.1 · ANEXO B §B.2 |
| `Automation 1` — **script vazio**, resolvido por evidência | SUPERSEDED (ANEXO A §A.2) | ANEXO B §B.1 |
| As 8 views — mapeamento completo | JÁ PRESERVADO | ANEXO B §B.3 |
| Filtros de view e condições de ramo | AINDA PRECISA DE DECISÃO | ANEXO B §B.4 — **não observável por API** |
| `480` fixo vs. 12x36 | JÁ PRESERVADO | ANEXO B §B.5 |
| **`480` não existe no código — só na fórmula** | **FALTAVA INCORPORAR** | → ANEXO B §B.5 |
| **Só o Airtable calcula extra, e só ele ignora a escala** | **FALTAVA INCORPORAR** | → ANEXO B §B.5, risco AT-21 |
| `F_FUNC_STATUS` escrito por automação, fora do código | JÁ PRESERVADO | `AIRTABLE_LOGICA_OCULTA.md` §5 · mestre §0-H.7 |
| Batida ímpar → `BLANK()` silencioso | JÁ PRESERVADO | `AIRTABLE_LOGICA_OCULTA.md` §3 |
| Make.com: estado real × decisão documentada | **FALTAVA INCORPORAR** | → ANEXO B §B.6, com 4 opções |
| Produção inalcançável pela rede da sessão | JÁ PRESERVADO | mestre §6 — reconfirmado nesta etapa |

## 4. Erros que não devem se repetir — a lista curta

Estes não são fatos sobre o projeto; são fatos sobre **como este
trabalho falha**. Nenhum estava registrado como lição antes desta etapa.

1. 🔴 **Um teste que exercita só a função isolada não protege a ligação.**
   Reintroduzi o defeito do sensor de propósito e **6 de 6 testes
   continuaram verdes**. Um teste de regressão só vale depois de você ter
   visto ele reprovar.
2. 🔴 **Sanitizar um tipo de PII não sanitiza o registro.** O #38 trocou
   o CPF e deixou o nome real três linhas abaixo. A busca foi por padrão,
   não pelo dado.
3. 🟠 **Detector com falso positivo destrói a própria autoridade.** Meu
   heurístico de nome acusou 42 de 42 branches; o número real era 40.
4. 🟠 **`git add -A` num tree com arquivo de outra frente entrega o que o
   PR não declarou.**
5. 🟠 **"A API não devolve" e "não existe" são coisas diferentes.**
   Registrei `Automation 1` como indeterminada quando um segundo caso na
   mesma sessão já provava que a API devolve corpo de script.
6. 🟡 **Documentar uma regra não a corrige.** `480`, `F_FUNC_STATUS` e
   batida ímpar seguem exatamente como estavam.

## 5. Grande Orquestrador e Graphify

| Item | Classificação | Onde está |
|---|---|---|
| Sensor da Central Command — 1ª automação de memória | JÁ PRESERVADO | `scripts/ci/central_command_sensor.py` |
| Snapshot de arquitetura (1,42 MB → 69 KB, só `EXTRACTED`) | JÁ PRESERVADO | `ARQUITETURA_SNAPSHOT.json` |
| Regeneração code-only, sem LLM e sem chave | JÁ PRESERVADO | `scripts/ci/graphify_regenerar.sh` |
| Papéis: Graphify = sensor · CC = memória · GO = coordenação | JÁ PRESERVADO | reafirmado em `GRAPHIFY.md` |

## 6. Pendências que atravessam a etapa

| Pendência | Estado |
|---|---|
| PR #22 aberto desde etapas anteriores | 🟡 **avaliado na Etapa 11: NÃO é superado.** 489 linhas inexistentes em `main` — plano, adapter de captura de e-mail e 204 linhas de teste. Fechá-lo destruiria conhecimento |
| `DEC-ENT-010/011/012` | 🔴 pendentes |
| Contrato canônico do Financeiro/Fiscal | 🔴 não existe |
| Postgres real (`render.yaml` = `plan: free`) | 🔴 decisão financeira |
| 40 branches com PII na árvore | 🔴 `PII_HISTORICO_PLANO.md` |
| Filtros de view e condições de ramo | 🔴 só pela interface |
| Conteúdo do cenário do Make.com | 🔴 só pela interface do Make |

---

## 7. Veredito

**Depois de incorporados os 7 itens marcados `FALTAVA INCORPORAR`, não
resta na conversa Macro 6A conhecimento único com valor durável.**

O que a conversa ainda tem e o repositório não: a ordem cronológica das
tentativas, os comandos exatos e o texto das missões. Isso é **contexto
de processo**, não conhecimento operacional — reconstituível a partir do
histórico de commits e dos corpos de PR, que continuam no Git.
