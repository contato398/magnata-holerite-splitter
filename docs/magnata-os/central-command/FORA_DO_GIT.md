# FORA DO GIT — fontes conhecidas que não estão versionadas

**Etapa 5 da Central Command, 2026-08-22.**

Este arquivo existe para que **nenhuma fonte desapareça em silêncio**. Uma
fonte que não pode ser versionada continua sendo memória do projeto: aqui
ficam sua existência, identificação, finalidade, proveniência, resumo
sanitizado e **o motivo exato** de não estar no Git.

Ausência de arquivo nunca é prova de ausência de conhecimento.

---

## 1. ARQUIVO HISTÓRICO SENSÍVEL — bloqueado por LGPD

| Campo | Valor |
|---|---|
| **Identificação** | `docs/historico/` — 29 dos 31 arquivos |
| **Proveniência** | `origin/fix/recibos-outros-documentos`, commit `1027fc8a0c774de88715e6fecc447fc3ae1a94f4`, 2026-07-23 |
| **Finalidade** | Memória operacional diária de 12/06 a 01/07/2026 |
| **Motivo de não versionar** | **8 arquivos com CPF real de funcionário; 29 com nome completo real.** `CLAUDE.md` §6 proíbe dado pessoal em commit; §12-I não dispensa |
| **Resumo sanitizado** | [`HISTORICO.md`](HISTORICO.md) — lição, decisão e blob SHA de cada um dos 30 registros |
| **Identificador** | blob SHA de cada arquivo registrado em `HISTORICO.md` §2 |
| **Recuperável?** | ✅ Sim, enquanto a branch existir — **não apagar** |
| **Gate** | Desidentificação exige revisão humana arquivo a arquivo |

**Os 2 arquivos livres de PII foram preservados na íntegra** em
`docs/magnata-os/historico/`.

---

## 2. Bloqueado por `ALLOWED_PATHS` — decisão de governança pendente

Conteúdo real, sem PII, sem segredo, que **não pode ser commitado** porque
o caminho não está na lista canônica de `.magnata/patterns.sh`. Resolver
exige alterar a política de caminhos — decisão própria, não efeito
colateral de um PR documental.

| Arquivo | Proveniência | Finalidade | Por que fora |
|---|---|---|---|
| `.claude/skills/*` (5) | `feat/magnata-os-claude-powerpack` | Procedimentos de engenharia read-only | `^\.claude/` não está em `ALLOWED_PATHS` |
| `.claude/agents/*` (5) | idem | Subagentes especializados read-only | idem |
| `.claude/MATRIX_DE_RESPONSABILIDADES.md` | idem | Matriz de responsabilidades entre skills e agentes | idem — **é o alvo do único link que o `README.md` não pôde resolver** |
| `MAGNATA_AI_ENGINEERING_POWERPACK_INVENTARIO.md` | idem | Inventário do ambiente na Etapa 1 do Powerpack | Nome não bate com `^MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA[0-9]+.*\.md$` nem com `^MAGNATA_OS_.*\.md$` |
| `MAGNATA_ETAPA5B_VALIDACAO_MANUAL.md` | idem | Validação manual da Etapa 5B | idem |

**Conteúdo já incorporado por outra via:** o essencial do `INVENTARIO`
está em [`SOURCES_AND_PROVENANCE.md`](SOURCES_AND_PROVENANCE.md) e
[`COBERTURA.md`](COBERTURA.md); os 5 skills e 5 subagentes estão descritos
em `docs/magnata-os/MAGNATA_AI_SKILLS_E_SUBAGENTES.md`, que **foi**
resgatado. Falta o código deles, não a descrição.

---

## 3. Fora por coerência com o código — não é lacuna

| Arquivo | Por que fora |
|---|---|
| `MAGNATA_OS_DOCUMENTAL_MODULO01_FASE5.md` | A Fase 5 (painel visual) **não foi mesclada**. Trazer só o documento afirmaria que existe algo que o código não sustenta — o contrário da regra de precedência do `README.md` |

---

## 4. Referenciado mas nunca criado

| Arquivo | Onde é citado | Situação |
|---|---|---|
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_FIXTURE.md` | `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_PLANO.md` | **Não existe em nenhuma branch.** Artefato planejado que nunca foi produzido. A citação é histórica e fica como está — o plano registra a intenção da época, não um arquivo perdido |

---

## 5. Efêmero — some quando o container for recuperado

| Conteúdo | Onde | Risco |
|---|---|---|
| 7 relatórios da Recuperação Macro 6A | scratch de sessão | 🟠 O conteúdo técnico está em `main` (PR #19); o **registro de como a recuperação foi feita**, não. Ver [`MACRO_6A.md`](MACRO_6A.md) |
| `macro-6a-fix-bundle.git` (1,4 MB) | scratch | 🟢 Plano B nunca usado; SHA-256 registrado em `MACRO_6A.md` |
| Scripts e CSVs do disparo de Julho/2026 | scratch | 🟡 Operacionais, com dado pessoal — **não versionar** |

---

## 6. Permanentemente perdido — aceitar formalmente

Nunca versionado em lugar nenhum. Nenhuma auditoria futura recupera.

| Conteúdo | Situação |
|---|---|
| `RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md` | Citado por documentos do Powerpack; nunca esteve em nenhuma branch |
| Cluster `ENTREGA_FASES_A_B_C_D` / `FASE_A..D` | idem |
| Transcrições `.jsonl` de sessões | Existiram numa máquina local; fora do alcance de qualquer sessão em container remoto |
| Toda conversa que nunca virou documento | Por definição irrecuperável |

⚠️ Isto **não** pode ser declarado "aceito" por uma auditoria. Só a
Direção tem autoridade para registrar formalmente essa perda como aceita.
Até lá, permanece uma lacuna aberta — declarada, não escondida.

---

## 7. Requisito arquitetural futuro — camada de memória segura

**Registro de requisito, não implementação.** Nada disto foi construído,
e nada deve ser construído sem decisão própria.

A auditoria de LGPD desta fase expôs uma lacuna **estrutural**, não
pontual: o Magnata OS tem memória canônica (versionada, pública dentro do
repositório) e **não tem** memória segura para fonte sensível. Hoje o
resultado é binário — ou o conhecimento entra no Git com dado pessoal
junto (proibido), ou fica só numa branch frágil (o que quase aconteceu
com 31 arquivos).

O Grande Orquestrador precisa das duas camadas, separadas por desenho:

| Camada | Conteúdo | Onde vive | Quem lê |
|---|---|---|---|
| **Memória canônica** | Decisão, arquitetura, proveniência, lição — livre de dado pessoal | Git (é o que este PR consolida) | Qualquer sessão, qualquer agente |
| **Memória segura** | Fonte histórica com PII, registro operacional nominal, evidência de assinatura | 🚫 **Não existe** | Acesso restrito, com trilha de auditoria |

**Requisitos mínimos que a camada segura precisará cumprir**, derivados
das regras que já existem — não inventados aqui:

1. **Fora do Git.** Versionamento distribuído e direito ao esquecimento
   são incompatíveis: `git` não esquece.
2. **Referenciável pela memória canônica.** A Central Command precisa
   poder apontar para um registro sensível por identificador, sem expor
   o conteúdo — exatamente o que [`HISTORICO.md`](HISTORICO.md) faz hoje
   de forma manual.
3. **Trilha de acesso append-only** (`CLAUDE.md` §4).
4. **Retenção e descarte explícitos** — LGPD exige prazo, o Git não tem.
5. **Sanitização na saída, não na entrada** — o dado entra íntegro e é
   mascarado ao ser lido por quem não tem direito, para não repetir a
   escolha entre "perder a lição" e "expor a pessoa".

**Nada disto autoriza construir a camada agora.** É requisito registrado
para que a arquitetura documental de hoje não impeça a de amanhã.
