# GRAPHIFY — avaliação técnica com prova de conceito executada

**Etapa 6 da Central Command, 2026-08-22.**
**Veredito: 🟡 ADOTAR COM RESTRIÇÕES.**

Esta não é uma avaliação conceitual. O pacote foi instalado em diretório
isolado (`/tmp`, fora do repositório) e executado contra uma **cópia** do
domínio. Nada foi instalado no repositório, em `main` ou em produção.

---

## 1. O que o Graphify realmente é — correção de premissa

**Registro de correção:** rodadas anteriores desta Central Command
descreveram o Graphify como "ferramenta que extrai grafo de
import/dependência direto do código". **Isso estava incompleto.**

`@sentropic/graphify` v0.17.1 (MIT, Node ≥20) é um extrator de **grafo de
conhecimento a partir de um corpus** — código, documentos, papers,
imagens, transcrições. Suas dependências incluem `@ai-sdk/anthropic`,
`@ai-sdk/openai`, `@ai-sdk/google`, `@ai-sdk/mistral`, `@ai-sdk/cohere`,
`ollama-ai-provider`, `web-tree-sitter` e `graphology`.

Ou seja: **tem um backend de LLM**, e por padrão detecta provider pelas
chaves de API do ambiente. Isso é exatamente o tipo de detalhe que muda a
decisão — e que só apareceu porque a avaliação foi feita de verdade.

**Mas** — e este é o achado que salva a adoção — existe um **modo
code-only, por AST, sem nenhuma chave**, que foi o modo testado.

---

## 2. Prova de conceito — o que foi executado

| Item | Valor |
|---|---|
| Instalação | `npm install @sentropic/graphify` em `/tmp/poc-graphify` |
| Peso | **612 MB** de `node_modules` · pacote 42,2 MB |
| Alvo | **cópia** de `magnata_os/` em `/tmp/poc-alvo` (38 arquivos `.py`) |
| Comando | `graphify update` — modo code-only |
| Chave de API | **nenhuma** |
| Dado enviado para fora | **nenhum** |

### Resultado

```
674 nodes · 2085 edges · 35 communities
Extração: 42% EXTRACTED · 58% INFERRED · 0% AMBIGUOUS
INFERRED: 1211 edges (confiança média 0,5)
Token cost: 0 input · 0 output
Edge kinds: uses 1211 · contains 256 · rationale_for 208 · calls 170 ·
            method 159 · inherits 57 · references 11 · imports_from 9
Escopo: 51 arquivos · 0 sensitive · 0 ignored
```

Artefatos: `graph.json` (1,4 MB), `GRAPH_REPORT.md` (17 KB),
`manifest.json`, `scope.json`, `.graphify_detect.json`.

### Qualidade — verificada, não presumida

As "God Nodes" que ele identificou como as abstrações centrais do domínio:

`EtapaEsteira` (48) · `SituacaoEsteira` (48) · `EventoHistorico` (44) ·
`RepositorioHistorico` (42) · `TipoDocumental` (41) · `Documento` (41) ·
`EstadoEsteiraDocumento` (40) · `VersionamentoLogico` (33)

**Estão corretas.** São exatamente as entidades centrais do Módulo 01 e
refletem o princípio de `CLAUDE.md` §4 (etapa/situação/motivo/próxima
ação sempre separados). A ferramenta acertou a arquitetura real sem
nenhuma instrução prévia.

### A ressalva que a própria ferramenta declarou

> `Corpus is ~28,459 words - fits in a single context window.
> You may not need a graph.`

**O Graphify avisou que, nesse tamanho, ele não é necessário.** Isso é
honestidade da ferramenta e precisa constar aqui: para o `magnata_os/`
sozinho, o grafo não paga o custo. O caso real de uso é outro — §5.

---

## 3. Capacidades relevantes para a Central Command

| Comando | O que faz | Relevância |
|---|---|---|
| `serve [graph]` | **Servidor MCP stdio** sobre o `graph.json` | 🔴 **Alta** — o Orquestrador consultaria o grafo como ferramenta, sem carregar arquivo no contexto |
| `check-update` | Reporta se há refresh semântico/lifecycle pendente | 🔴 **Alta** — é literalmente "detectar mudança de arquitetura" |
| `update` | Rebuild code-only, sem LLM | 🟠 Média-alta — barato e reprodutível |
| `watch` | Rebuild automático a cada mudança | 🟡 Média |
| `hook` | Integração com git hooks | 🟡 Média — mas o repositório já tem 3 hooks próprios |
| `merge-graphs` | Une grafos de vários repositórios | 🟡 Futuro — Magnata OS multi-repo |
| `extract` | Modo headless para CI | 🟠 Média-alta |
| `pr` / `prs` | Inspeciona PRs locais via `gh` + worktree | 🟢 Baixa — o `gh` não existe neste ambiente |
| `install <platform>` | Copia a skill para o config do assistente | ⚠️ **Alteraria configuração** — não executado |

---

## 4. Riscos identificados

| Risco | Severidade | Mitigação |
|---|---|---|
| **Backend de LLM por padrão** — detecta provider pelas chaves de ambiente e envia conteúdo | 🔴 **Crítico** | **Sempre** `update`/`extract` code-only, ou `--description-mode assistant`. Nunca `--description-backend` com chave |
| **Apontar para dado sensível** — se rodar sobre `docs/historico/` com LLM externo, envia CPF e nome real | 🔴 **Crítico** | **Proibir** o Graphify sobre qualquer corpus com PII. `CLAUDE.md` §6 |
| **58% das arestas são INFERRED, confiança 0,5** | 🟠 Alto | Tratar `INFERRED` como hipótese, nunca como fato. Só `EXTRACTED` (42%) é evidência |
| **612 MB de dependências** | 🟡 Médio | Manter fora do repositório; nunca virar dependência obrigatória |
| **`graph.json` de 1,4 MB para 38 arquivos** | 🟡 Médio | Não commitar o grafo; regenerar sob demanda. `.gitignore` para `.graphify/` |
| **Comando `install` altera config do assistente** | 🟡 Médio | Não executar sem decisão própria |
| **13 versões em ~um período curto; v0.x** | 🟡 Médio | API instável. Pinar versão exata se adotado |

---

## 5. Onde ele de fato paga o custo neste projeto

O `magnata_os/` **não** justifica (a própria ferramenta disse). O caso
real é o oposto:

1. **`app.py` — 12.301 linhas.** É o legado protegido, o único caminho
   ponta a ponta em produção, e **não cabe num contexto**. Um grafo
   navegável dele é a diferença entre "ler 12 mil linhas" e "perguntar
   quem chama `_status_funcionario_elegivel`". **É aqui que o Graphify
   vale.**
2. **Verificar mecanicamente a regra de acoplamento** — `CLAUDE.md` §3
   exige que o domínio não importe Flask/Airtable/driver. Hoje isso é
   conferido por `grep` manual a cada auditoria. As arestas
   `imports_from` resolvem isso de forma reprodutível.
3. **Detectar divergência doc × código** — `MAGNATA_OS_MODULOS.md` e a
   matriz arquitetural são mantidos à mão e já mostraram desatualização.
   `check-update` sinaliza quando a foto real mudou.
4. **Reduzir consumo de contexto** — via `serve` (MCP), uma sessão nova
   consulta o grafo por pergunta em vez de carregar arquivos inteiros.
   **Esta é a maior economia potencial de tokens**, e não foi medida.

---

## 6. Veredito

# 🟡 ADOTAR COM RESTRIÇÕES

**Restrições, todas obrigatórias e cumulativas:**

1. **Somente modo code-only** (`update` / `extract` sem backend de LLM).
2. **Nunca** apontar para corpus com PII — `docs/historico/`, anexos,
   evidências de assinatura, dado de colaborador.
3. **Nunca** virar dependência obrigatória de build, teste, CI ou deploy.
4. **`.graphify/` no `.gitignore`** — o grafo é derivado, não fonte.
5. **`INFERRED` é hipótese**, nunca evidência. Só `EXTRACTED` sustenta
   afirmação na Central Command.
6. **Versão pinada exata.** É v0.x com API instável.
7. **Não executar `graphify install`** sem decisão própria — altera a
   configuração do assistente.

**Próximo passo concreto sugerido, não executado:** rodar `update`
code-only sobre uma cópia isolada do repositório **inteiro** (incluindo
`app.py`) e medir se o `GRAPH_REPORT.md` responde perguntas que hoje
custam leitura manual. Se responder, adotar com as 7 restrições. Se não,
reclassificar para ADIAR.

**O que a Central Command ganha se for adotado:** a camada que hoje ela
**não** tem — verdade automática sobre o código. A Central Command
continua sendo memória, decisão e proveniência; o Graphify seria a foto
verificável e regenerável da estrutura. Fronteira em
[`ORQUESTRADOR.md`](ORQUESTRADOR.md) §3.

---

## 7. Proposta de integração controlada — Etapa 7, 2026-08-22

Desenho, não implementação. **O Graphify continua não instalado no
repositório** e não deve virar dependência de nada.

### 7.1 Contrato de execução

| Item | Decisão |
|---|---|
| Onde roda | **Fora do repositório** (`/tmp` ou máquina do operador). Nunca em `node_modules/` versionado |
| Comando | `graphify update <caminho>` — code-only, AST |
| Chave de API | **Nenhuma.** Se houver chave no ambiente, passar `--description-mode assistant` |
| Alvo | Cópia do repositório **sem** `docs/historico/` e sem qualquer corpus com PII |
| Versão | Pinada exata (`@sentropic/graphify@0.17.1`) e registrada junto do grafo |
| `.graphify/` | Em `.gitignore` — o grafo é derivado, nunca fonte |

### 7.2 O que a Central Command consome — e o que descarta

Do `GRAPH_REPORT.md`, apenas o que é **evidência**:

| Consumir | Descartar |
|---|---|
| ✅ Arestas `EXTRACTED` (42%) — AST real | ❌ Arestas `INFERRED` (58%, confiança 0,5) |
| ✅ `imports_from` — verifica a regra de acoplamento de `CLAUDE.md` §3 | ❌ "Surprising Connections" — é inferência |
| ✅ God Nodes — abstrações centrais por grau | ❌ Descrições geradas por LLM |
| ✅ Contagem de nós/arestas/comunidades — para detectar mudança estrutural | ❌ Rótulos de comunidade |
| ✅ Componentes novos/removidos entre execuções | |

**Regra dura:** nenhuma afirmação da Central Command pode se apoiar em
aresta `INFERRED`. Inferência a 0,5 de confiança é cara ou coroa.

### 7.3 Como detectar mudança de arquitetura

Comparar duas execuções e reportar apenas:

1. módulos/arquivos que **entraram** ou **saíram**;
2. classes e funções novas ou removidas;
3. arestas `imports_from` novas — **especialmente do domínio para
   fornecedor** (Flask, `psycopg`, `boto3`, cliente Airtable), que é
   violação direta de `CLAUDE.md` §3;
4. variação relevante em nós/arestas/comunidades.

Isso é o mesmo padrão do sensor já implementado
(`scripts/ci/central_command_sensor.py`): **instantâneo + comparação**.
A integração natural é o Graphify virar mais uma fonte lida por ele —
não um segundo mecanismo paralelo.

### 7.4 Evitar duplicidade com a documentação

O Graphify responde **"como o código está"**. A Central Command responde
**"o que foi decidido e por quê"**. Nunca devem descrever a mesma coisa.

Quando divergirem: **o código vence**, e a divergência é registrada —
exatamente a regra de arbitragem de [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §6.1.

### 7.5 Economia de contexto — hipótese não medida

`graphify serve` expõe um servidor MCP sobre o `graph.json`. Uma sessão
poderia perguntar "quem chama `_status_funcionario_elegivel`?" em vez de
carregar 12.301 linhas de `app.py`.

🔍 **Não medido.** É a maior economia potencial e a razão mais forte para
adotar — mas segue sendo hipótese até alguém cronometrar.

### 7.6 Próximo passo concreto

Rodar `update` code-only sobre cópia isolada do repositório **inteiro**
(com `app.py`) e verificar se o `GRAPH_REPORT.md` responde perguntas que
hoje custam leitura manual. Se responder, adotar com as 7 restrições da
§6. Se não, reclassificar para **ADIAR**.
