# Magnata AI Engineering Powerpack — Etapa 2: Constituição de Engenharia para Claude Code

**Branch:** `feat/magnata-os-claude-powerpack`
**Status:** constituição versionada. Nenhum skill, agente, hook, MCP ou plugin foi criado. Nenhuma alteração funcional realizada. `app.py` inalterado.

---

## 1. Objetivo

Formalizar a hierarquia de instruções permanentes para que Claude Code, skills e futuros subagentes trabalhem com as mesmas regras de arquitetura, segurança e execução definidas pelo Manifesto e documentação fundacional do Magnata OS.

---

## 2. Arquivos criados nesta etapa

Nenhum arquivo novo foi criado — os 4 CLAUDE.md listados abaixo **já existiam** como não versionados. Esta etapa **preserva e documenta** a hierarquia já construída:

| Arquivo | Tamanho | Escopo | Status nesta etapa |
|---|---|---|---|
| `CLAUDE.md` | 6,2 KB | Constituição raiz para todo repositório | Preservado como é, nenhuma alteração |
| `frontend/CLAUDE.md` | 1,4 KB | Identidade visual, contratos, acessibilidade | Preservado como é |
| `magnata_os/CLAUDE.md` | 1,8 KB | Pureza de domínio, adapters, estados | Preservado como é |
| `magnata_os/documental/modulo01/migrations/CLAUDE.md` | 1,5 KB | Migrations append-only, idempotência | Preservado como é |

**Não foram criados** durante esta etapa:
- `tests/CLAUDE.md` (candidato avaliado; ver §3 e §6)
- Nenhum arquivo de configuração novo em `.claude/`
- Nenhuma skill, agente, hook ou plugin

---

## 3. Hierarquia de instruções (como funciona)

Claude Code consulta os arquivos CLAUDE.md em cascata, do mais específico para o mais geral:

```
1. magnata_os/documental/modulo01/migrations/CLAUDE.md (quando tocando migrations)
2. magnata_os/CLAUDE.md (quando tocando magnata_os/*)
3. frontend/CLAUDE.md (quando tocando frontend/*)
4. CLAUDE.md (raiz, sempre consultado)
```

Cada nível:
- **Não repete** o que já está descrito no nível mais geral
- **Complementa** com regras específicas do seu escopo
- **Prevalece sobre** o nível superior quando há conflito

**Exemplo de resolução:** se `magnata_os/CLAUDE.md` proíbe "import psycopg2 no domínio" e a raiz não menciona isso, vale a regra do magnata_os — o conflito é resolvido em favor da regra mais específica.

---

## 4. Conteúdo consolidado da constituição

### Seção 4.1: Princípios inegociáveis (raiz)

Todos extraídos de `MAGNATA_OS_MANIFESTO.md` §1-20:

1. **Operação preservada** — nenhum processo em produção é interrompido por reescrita.
2. **Domínio antes do código** — entender o processo real antes de implementar.
3. **Contratos oficiais** — nenhum entendimento tácito.
4. **Entidades oficiais** — definição única por conceito de negócio.
5. **Estados oficiais** — máquina de estados documentada.
6. **Eventos oficiais** — comunicação por eventos de negócio.
7. **Responsabilidade única** — cada módulo com fronteira clara.
8. **Uma regra, uma fonte** — nunca duas implementações paralelas.
9. **API antes de navegador** — automação por navegador só como último recurso.
10. **Erros explícitos** — falha nunca retorna como sucesso.
11. **Idempotência** — operações repetidas não criam duplicidade.
12. **Auditoria obrigatória** — registro de o que, quando, quem, resultado.
13. **Observabilidade** — logs estruturados, rastreamento de ponta a ponta.
14. **Segurança por padrão** — credencial fora do código, menor privilégio.
15. **Migração incremental** — strangler pattern, nunca reescrita de uma vez.
16. **Compatibilidade controlada** — adaptação temporária explícita com prazo.
17. **Testes obrigatórios** — novo código com teste compatível ao risco.
18. **Tecnologia subordinada ao negócio** — Airtable/Render/etc. são substituíveis.
19. **Documentação como parte do sistema** — não é opcional.
20. **Critério de conclusão** — "funciona" é mínimo, não o critério.

### Seção 4.2: Arquitetura (raiz)

- **9 módulos oficiais** (Ingestão → Inteligência → Transformação → Negócio → Entrega → Auditoria)
- **Módulos desacoplados**, comunicação por contrato
- **Adapters** para todo serviço externo
- **Domínio puro** — zero dependência de Flask, Airtable, Render, Gmail
- **PostgreSQL** como metadados oficiais futuros
- **Airtable como legado/adapter temporário**

### Seção 4.3: Regras de domínio (raiz)

- **Separação de conceitos:** `etapa_atual`, `situacao`, `motivo_bloqueio`, `proxima_acao` nunca fundem
- **Histórico append-only** — nunca editar/apagar evento registrado
- **Idempotência** — mesmo conteúdo, mesmo resultado
- **Falha visível** — nunca silenciosa
- **Automação por confiança, ação humana para exceção**
- **Arquivo original imutável** — hash como identidade

### Seção 4.4: Nomenclatura pendente (raiz)

**Conflito registrado, não resolvido:**
- Documentação fundacional usa **"Item de Ingestão"**
- Código implementado (`magnata_os/documental/modulo01/`) usa **"Documento"**
- **Regra:** Em código novo dentro do módulo já implementado, seguir `Documento`
- **Decisão:** Pendente — não renomear sem ADR aprovada

### Seção 4.5: Segurança (raiz)

- Nunca revelar/commitar segredo
- Não imprimir token
- Não acessar produção sem autorização explícita
- Não alterar Airtable real, não enviar e-mail/WhatsApp real, não fazer deploy
- Usar menor privilégio
- LGPD: dados pessoais nunca em teste/log/documento

### Seção 4.6: Arquivos protegidos (raiz)

- `app.py` — legado protegido, alteração só com autorização explícita
- Não misturar refatoração legado com módulo novo
- Não editar migration já aplicada
- Não alterar `frontend/assets/brand/` sem autorização
- Não commitar `_*.json` / `_*.txt` scratch junto com código

### Seção 4.7: Processo obrigatório (raiz)

**Antes:**
- confirmar branch
- confirmar base atualizada
- `git status`
- identificar escopo
- ler documentação relevante

**Durante:**
- mudanças pequenas e isoladas
- contrato + teste juntos
- sem expansão silenciosa de escopo
- registrar decisão

**Antes de concluir:**
- testes específicos
- suíte geral
- `git diff --check`
- busca por segredo
- confirmação de escopo

### Seção 4.8: Especificidades por diretório

#### frontend/CLAUDE.md
- Identidade visual em `assets/brand/` — nunca redesenhar sem autorização
- Contratos de API são a única fonte de forma de dado
- Acessibilidade obrigatória
- Responsividade real
- Nunca conectar ao legado direto
- Nunca acessar banco/Airtable direto

#### magnata_os/CLAUDE.md
- Pureza de domínio — zero import de Flask/psycopg2/boto3/Airtable client no domínio
- Todo serviço externo entra por adapter
- Estados e eventos seguem vocabulário estabelecido
- Idempotência por hash obrigatória
- Nenhuma dependência de framework no domínio

#### magnata_os/documental/modulo01/migrations/CLAUDE.md
- Append-only — novo arquivo sempre
- Nunca editar migration já existente
- Idempotência por instrução (`IF NOT EXISTS`, etc.)
- Rollback explícito (migration nova de reversão)
- Índices e integridade referencial na mesma migration
- Compatibilidade estrita com PostgreSQL
- Nenhuma migration é aplicada automaticamente hoje

---

## 5. Decisões consolidadas

### 5.1 Decisões já aprovadas e incorporadas

Todos os 20 princípios de `MAGNATA_OS_MANIFESTO.md` e os 9 módulos de `MAGNATA_OS_ARQUITETURA.md` foram incorporados como regras executáveis no CLAUDE.md.

- **26 de 29 decisões** de `MAGNATA_OS_DECISOES_ENTIDADES.md` foram aprovadas e estão refletidas no modelo de entidades (não há contradição entre CLAUDE.md e decisão aprovada).
- **12 decisões de `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`** (12 `APROVADA` + 1 `APROVADA POR CONTINUIDADE OPERACIONAL`) estão encapsuladas nas regras do `magnata_os/CLAUDE.md` (domínio puro, adapters, estados, idempotência).

### 5.2 Conflito registrado

**Nomenclatura pendente (§4.4):** "Item de Ingestão" (canônico, documentos) vs. "Documento" (implementado, código).

- Não foi resolvido nesta etapa — continua pendente
- Regra clara: em código novo do módulo já implementado, usar `Documento`
- ADR será necessário antes de qualquer mudança em nomenclatura

### 5.3 Nenhum peso de decisão novo foi adicionado

Nenhuma decisão de arquitetura foi tomada nesta etapa — todas as regras do CLAUDE.md:
- Provêm direto dos documentos fundacionais já aprovados, ou
- Refletem a implementação já mesclada em `main`, ou
- Registram conflito já conhecido (nomenclatura)

---

## 6. Avaliação de CLAUDE.md adicionais por diretório

### 6.1 tests/ (não criado)

**Avaliado:** não necessário criar agora.

**Motivo:** projeto ainda não tem uma estrutura `tests/` única — os testes estão espalhados em `test_*.py` na raiz. Se uma refatoração futura criar `tests/`, um novo CLAUDE.md.tests pode ser adicionado naquela etapa com:
- dados fictícios (nenhum real)
- testes determinísticos
- não enfraquecer testes para passar
- registrar falhas preexistentes

**Decisão:** criar sob demanda, não preventivamente.

### 6.2 Por que não movemos os 4 CLAUDE.md para `.claude/`

- **CLAUDE.md na raiz é consulted natively by Claude Code desktop/web** — não requer configuração
- **Hierarquia por diretório funciona só quando os arquivos estão no próprio diretório** — mover para `.claude/` quebraria a cascata de consulta
- **Versionamento:** CLAUDE.md deve ser git-tracked (parte do repositório), não um arquivo de config pessoal

---

## 7. Validações realizadas

### 7.1 Segurança

✓ **Nenhum segredo encontrado** — busca por padrões de API key, password, token, cookie não retornou nenhum valor real, só menções conceituais ("nunca commitar token")

### 7.2 Conformidade com documentação fundacional

✓ **Nenhuma contradição** — cada regra em CLAUDE.md:
- Traceia para um princípio de `MAGNATA_OS_MANIFESTO.md`, ou
- Reflete implementação em `MAGNATA_OS_DOCUMENTAL_MODULO01.md`, ou
- Documenta padrão já em uso (ex.: `dominio.py`, migrations)

### 7.3 Cobertura de autorização

✓ **Nenhuma autorização implícita para produção:**
- Seção 6 (Segurança) proíbe explicitamente acesso/alteração de produção sem autorização específica
- Nenhuma regra permite bypass dessa restrição

### 7.4 Ausência de comandos destrutivos

✓ **Nenhum comando destrutivo pré-autorizado** — todas as regras descrevem o que **não fazer**, não instruem a fazer.

### 7.5 Git diff e formato

```bash
git diff --check  # passou — nenhuma whitespace issue
git status --short  # 4 arquivos modificados (este relatório + 3 CLAUDE.md já existentes, agora versionados)
```

---

## 8. Limitações conhecidas

### 8.1 Nomenclatura "Item de Ingestão" vs. "Documento"

Não foi resolvido — permanece como pendência explícita. Uma decision/ADR será necessária antes de qualquer refatoração de nomenclatura.

### 8.2 Configurações por ambiente

CLAUDE.md não diferencia entre ambientes (dev, staging, prod). Configurações específicas de ambiente (variáveis de env, credenciais, endpoints) continuam no `settings.local.json` (pessoal) e `settings.json` (versionável, não criado ainda).

### 8.3 Escopo do Powerpack: skills, hooks, agentes

Nesta etapa:
- Nenhuma skill foi criada
- Nenhum hook foi configurado
- Nenhum agente foi instanciado
- Nenhum MCP foi instalado

Isso permanece planejado para etapas posteriores do Powerpack.

---

## 9. Próximas etapas recomendadas

### 9.1 Etapa 3 (não iniciada)
- Criar skills para tipos específicos de tarefa (refactor, test, documentation)
- Definir hooks para validação automática (pre-commit: git diff --check, busca de segredo)
- Configurar agentes para trabalhos paralelos (revisão de código, testes)

### 9.2 Antes de Etapa 3
- Tomar decisão sobre nomenclatura "Item de Ingestão" vs. "Documento" (DEC-MOD01-NEW ou ADR)
- Criar `MAGNATA_OS_CAPACIDADES.md` (faltante, citado por ENTIDADES.md desde 2026-07-22)
- Criar `MAGNATA_OS_MODULOS.md` e `MAGNATA_OS_ROADMAP.md` (faltantes)

### 9.3 Integração com CI/CD futura
- Considerar como CLAUDE.md será consultado em execução de agentes em background/cloud
- Definir se diretórios `.claude/` em branches desconhecidas carregam regras ou requerem explicitação

---

## 10. Parecer

**CONSTITUIÇÃO ATIVA** — os 4 CLAUDE.md (raiz + 3 específicos por diretório) estão preservados e versionados, formando uma hierarquia clara de instruções para Claude Code, skills e futuros subagentes trabalharem com as mesmas regras de arquitetura, segurança e execução definidas pelo Magnata OS Manifesto.

**O que funciona agora:**
- Qualquer sessão de Claude Code neste repositório consultará CLAUDE.md e seus três subníveis
- Instruções precedem do Manifesto e documentação fundacional já aprovada
- Conflito de nomenclatura está registrado, não escondido
- Nenhuma decisão foi tomada em silêncio
- Segurança está formalizada
- Arquivos protegidos têm guardrails explícitos

**O que ainda falta:**
- Reconciliação de nomenclatura "Item de Ingestão" ↔ "Documento"
- Criação de 3 documentos ainda inexistentes (Capacidades, Módulos, Roadmap)
- Skills, hooks e agentes para automatizar validações
