# FOUNDATION — conteúdo da fundação documental do Magnata OS

**Etapa 3, 2026-08-22.** Fecha a lacuna nº 1 declarada em
[`COBERTURA.md`](COBERTURA.md) §7: até aqui a Central Command só tinha
confirmado que estes documentos **existem**. Agora tem o que eles
**dizem**.

**Proveniência única de tudo nesta página:** branch
`origin/feat/magnata-os-claude-powerpack`, PR **#12 — fechado sem merge
em 2026-08-03T17:16:01Z**, dois minutos antes de o PR #13 ser mesclado.
Nenhum destes arquivos existe em `main`.

**Método:** leitura estrutural de 9.600 linhas — cabeçalhos, tabelas de
decisão, status declarado e seções de fechamento de cada documento.
Não é transcrição integral; é o inventário de decisões e a localização
exata de cada uma. 🔍 Onde uma afirmação depende de prosa não lida
integralmente, está marcada.

---

## 1. Os documentos, nominalmente

| Documento | Linhas | Caminho na branch | O que carrega |
|---|---|---|---|
| `MAGNATA_OS_ARQUITETURA.md` | 324 | raiz | Linha de base 2026-07-22, princípios não-negociáveis, mapa de **9 módulos**, contratos, execução, plano strangler, débitos técnicos, changelog |
| `MAGNATA_OS_ENTIDADES.md` | 1.317 | raiz | Modelo canônico de entidades, glossário do legado, mapa de tabelas, matriz canônico×legado, identidade e chaves, modelo mínimo de migração |
| `MAGNATA_OS_DECISOES_ENTIDADES.md` | 1.750 | raiz | **29 decisões `DEC-ENT-001` a `DEC-ENT-029`** + 4 Modelos Conceituais aprovados |
| `MAGNATA_OS_EVENTOS.md` | 1.361 | raiz | Catálogo canônico, envelope de evento, **96 nomes de evento avaliados**, eventos×estados×comandos, idempotência, causalidade |
| `MAGNATA_OS_CONTRATOS.md` | 1.569 | raiz | **15 contratos canônicos** + envelope de evento + contrato de erro + versionamento + validações cruzadas |
| `MAGNATA_OS_ESTADOS.md` | 1.360 | raiz | **12 máquinas de estado canônicas** + estados incertos, terminais, migração |
| `MAGNATA_OS_MODULO_01_INGESTAO.md` | 902 | raiz | Missão, portas de entrada, fronteira, idempotência, estratégia strangler, critérios de pronto, riscos |
| `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` | 404 | raiz | **13 decisões `DEC-MOD01-001` a `DEC-MOD01-013`** |
| `MAGNATA_OS_ADR_001_...md` | 158 | `docs/magnata-os/` | 4 alternativas para a divergência de nomenclatura, recomendação **não vinculativa** |
| `MAGNATA_AI_SKILLS_E_SUBAGENTES.md` | 455 | `docs/magnata-os/` | 5 skills + 5 subagentes, todos read-only |

---

## 2. O achado de maior valor — Modelos Conceituais aprovados pela Direção

**Data da aprovação: 2026-07-22.** Fonte:
`MAGNATA_OS_DECISOES_ENTIDADES.md`, seção "Modelo Conceitual Aprovado"
e §12. Isto **não é proposta** — é decisão de negócio tomada pela
Direção da Magnata, e é o vocabulário oficial da plataforma.

```text
Empresa Magnata
└── Cliente
    └── Contrato Comercial
        └── Posto de Trabalho

Colaborador
└── Vínculo Trabalhista
    └── Alocação
        └── Posto de Trabalho
```

Citação do próprio documento, preservada: *"`Contrato Comercial`,
`Vínculo Trabalhista` e `Alocação` passam a fazer parte do modelo
conceitual oficial do Magnata OS a partir de agora — mesmo que nenhum
dos três integre o núcleo técnico mínimo da primeira migração
documental. Ou seja: o vocabulário é oficial e deve orientar qualquer
decisão futura, mas a implementação técnica desses três conceitos como
tabelas/campos no Airtable continua sendo trabalho de fases
posteriores."*

Outros **três** Modelos Conceituais foram aprovados na mesma data e têm
o mesmo peso: **Documental**, **Distribuição e Entrega**, e
**Assinatura**. 🔍 O texto integral dos três não foi extraído nesta
etapa — só a confirmação, na §12 do documento, de que estão `APROVADA`.

**Por que isto importa mais do que qualquer outro item desta página:**
`Vínculo Trabalhista` já é regra viva em produção hoje — é o que
`_status_funcionario_elegivel` verifica antes de liberar o pacote de
assinatura. O conceito está implementado no legado enquanto sua
definição oficial está presa numa branch fechada sem merge.

---

## 3. As 29 decisões de entidade

**26 `APROVADA` (2026-07-22) · 3 `PENDENTE`.**

⚠️ **Inconsistência interna do próprio documento, registrada:** o
cabeçalho ainda diz *"pauta aberta. Nenhuma decisão abaixo é definitiva
— todas aguardam resposta"*, mas a §12 lista nominalmente as 26
aprovadas. O cabeçalho nunca foi atualizado. **A §12 é que vale** — é
posterior, nominal e específica. O índice em `main` está correto.

### As 3 que continuam `PENDENTE`

| ID | Pergunta em aberto | Por que trava |
|---|---|---|
| `DEC-ENT-010` | Natureza do Alerta de Ponto: vira Pendência Documental? | Define se o Ponto gera item na esteira documental ou é trilha separada |
| `DEC-ENT-011` | Significado de negócio de `Fechamento` e `SBJ` | Vocabulário do legado sem definição canônica |
| `DEC-ENT-012` | Existência real de `Finalizado` e `Pronto` no Airtable | Estado do Envio depende disso (`DEC-ENT-020` referencia como pendente) |

Estão pendentes desde 2026-07-22 — **um mês**. Só a Direção da Magnata
pode resolvê-las; nenhuma sessão as marca aprovadas em nome dela.

### As 26 aprovadas, por tema

- **Cliente / Posto / Vínculo:** `001` correspondência Cliente↔Condomínio · `002` vínculo simultâneo em mais de um Cliente · `003` Posto compartilhado e rateio · `016` Alocação distinta de Vínculo
- **Documento / Arquivo / Competência:** `004` documento em mais de uma Competência · `005` titularidade do Holerite · `006` documento comum a vários Clientes · `015` Documento × Arquivo · `017` versões de Arquivo, histórico e vigência
- **Distribuição / Envio:** `007` reenvio é novo Envio ou nova Tentativa · `013` Distribuição × Envio · `018` destinatário e endereço · `019` canal e provedor · `020` estados do Envio · `021` auditoria do Envio · `009` evidência mínima de entrega
- **Assinatura:** `008` múltiplos signatários · `014` Solicitação × Assinatura · `022` quando a Solicitação é exigida · `023` Signatário como papel próprio · `024` Link como credencial temporária, não a Solicitação · `025` evidência e limites de suficiência jurídica · `026` Arquivo Assinado é sempre novo Arquivo, **nunca sobrescrita** · `027` estados da Solicitação · `028` estados da Assinatura · `029` idempotência da criação da Solicitação

**Aderência do código a essas decisões — verificada, não presumida:**
`026` (nunca sobrescrever) e `029` (idempotência) são exatamente o que
`CLAUDE.md` §4 exige e o que o Módulo 01 implementa. O sistema em
produção obedece a decisões cujo registro formal não está em `main`.

---

## 4. As 13 decisões de implementação do Módulo 01

`DEC-MOD01-001` primeira origem a migrar · `002` ordem das demais
origens · `003` armazenamento inicial · `004` tipos de arquivo
permitidos · `005` **regra para mesmo hash** · `006` papel do Airtable
na Fase 1 · `007` natureza do shadow mode · `008` destino de itens
rejeitados · `009` política de rollback · `010` limite inicial de
tamanho *(a única `APROVADA POR CONTINUIDADE OPERACIONAL`)* · `011`
estratégia de identificadores · `012` critério de saída do shadow mode
· `013` situações que prorrogam o shadow mode.

`005` e `007` são a base da idempotência por SHA-256 e do modo paralelo
que o PR #22 (aberto) propõe para o adapter de e-mail — a decisão que o
destrava já existe.

---

## 5. Contratos, estados e eventos — o que está especificado

**15 contratos canônicos** (`CONTRATOS.md`): Item de Ingestão · Arquivo
· Documento · Classificação · Distribuição · Destinatário · Envio ·
Tentativa de Envio · Evidência de Entrega · contratos opcionais de
Assinatura · Envelope de Evento · Erro — mais compatibilidade com
campos legados, regras de versionamento, contratos mínimos da primeira
migração e validações cruzadas.

**12 máquinas de estado** (`ESTADOS.md`): Item de Ingestão · Documento
· Distribuição · Envio · Tentativa de Envio · Solicitação de Assinatura
· Assinatura Individual · Link de Assinatura · Pendência Documental ·
Alerta de Ponto *(candidata)* — mais regras de falha/recuperação,
estados incertos, terminais e estratégia de migração.

**96 nomes de evento avaliados** (`EVENTOS.md`), com envelope canônico,
separação evento×estado×comando, eventos de falha, idempotência e
ordenação/causalidade.

**Consequência prática:** `CLAUDE.md` §2 manda usar `CONTRATOS.md` e
`ESTADOS.md` como critério de desempate para tudo que ainda não foi
implementado. Esse material existe e é substancial — 2.929 linhas. Ele
simplesmente não está em `main`, então a regra de precedência aponta
hoje para o vazio.

---

## 6. ADR-001 — continua sem decisão

Quatro alternativas para a divergência de nomenclatura entre
documentação e código: **A** padronizar num termo · **B** padronizar no
outro · **C** usar ambos com contexto · **D** modelo de domínio
aninhado.

Recomendação registrada: **Alternativa C**, explicitamente marcada
*"recomendação de trade-off, não uma decisão — cabe à Direção/Engenharia
da Magnata OS fazer"*. O documento fecha com: *"Até lá, nenhuma ação
unilateral. Documenta-se a divergência (já feito), não se escolhe em
silêncio."*

É exatamente a postura que `CLAUDE.md` §5 codificou e que a
`VALIDAÇÃO 12` do `pre-commit` protege mecanicamente. **A ADR está
íntegra e continua em aberto** — nada foi decidido por omissão.

---

## 7. Skills e subagentes — existem, todos read-only

5 skills (`magnata-repository-safety`, `-architecture-governance`,
`-legacy-preservation`, `-documentation-consistency`,
`-validation-gate`) e 5 subagentes (`repository-cartographer`,
`architecture-reviewer`, `legacy-guardian`, `documentation-auditor`,
`quality-gate-reviewer`), mais `.claude/MATRIX_DE_RESPONSABILIDADES.md`.

Limite declarado no próprio documento: leitura segura do repositório,
nenhum acesso autônomo a produção, nenhuma alteração de código. Nada
disso está em `main` — as sessões atuais trabalham sem essas barreiras.

---

## 8. Validade atual — documento por documento

| Documento | Superado? | Conhecimento único? | Risco de perda |
|---|---|---|---|
| `ARQUITETURA.md` | 🟡 **Parcial** — o mapa de 9 módulos foi superado pelo de 10 (`MODULOS.md`, em `main`). O resto (princípios, plano strangler, débitos) **não** | ✅ Sim — princípios, débitos técnicos, changelog | **Alto** |
| `DECISOES_ENTIDADES.md` | ❌ Não | ✅ **Sim, o maior** — 26 decisões aprovadas + 4 Modelos Conceituais | **Crítico** |
| `ENTIDADES.md` | ❌ Não | ✅ Sim — matriz canônico×legado | **Alto** |
| `CONTRATOS.md` | ❌ Não | ✅ Sim — citado por `CLAUDE.md` §2 como critério de desempate | **Crítico** |
| `ESTADOS.md` | ❌ Não | ✅ Sim — idem | **Crítico** |
| `EVENTOS.md` | ❌ Não | ✅ Sim — 96 eventos | **Alto** |
| `MODULO_01_INGESTAO.md` | 🟡 Parcial — Fases 1-4 implementadas divergem em detalhe | ✅ Sim — critérios de pronto, riscos | Médio |
| `MODULO_01_DECISOES_IMPLEMENTACAO.md` | ❌ Não | ✅ Sim — 13 decisões | **Alto** |
| `ADR_001` | ❌ Não — segue em aberto | ✅ Sim | **Alto** |
| `SKILLS_E_SUBAGENTES` | 🔍 A confirmar | ✅ Sim | Médio |

**Nenhum destes documentos está obsoleto.** Um está parcialmente
superado num único capítulo. Os demais carregam conhecimento que não
existe em nenhum outro lugar do repositório.

---

## 9. Estratégia de reconciliação documental — proposta, não executada

`CLAUDE.md` §9 e a instrução desta missão são explícitas: **não resgatar
automaticamente**. O que segue é proposta para decisão humana.

**Por que não é um merge simples:** a branch divergiu de `main` em
2026-07-30; `main` avançou ~70 commits desde então. Um merge direto traz
20 commits de história e conflita com o que `main` já reorganizou.

**Rota recomendada — resgate documental puro, em 4 passos:**

1. **Branch nova a partir de `main` atual.** Nada de merge da branch
   antiga: só `git checkout <branch> -- <arquivo>` dos 10 documentos.
   Zero conflito de história, zero arquivo funcional tocado.
2. **Reconciliar as 3 divergências já conhecidas antes de commitar** —
   e cada uma vira nota no próprio arquivo, nunca edição silenciosa:
   (a) mapa de 9 módulos → nota apontando `MODULOS.md` como vigente;
   (b) cabeçalho de `DECISOES_ENTIDADES.md` contradizendo a §12 → nota
   apontando a §12; (c) `MODULO_01_INGESTAO.md` × Fases 1-4 já
   implementadas → nota de que o código prevalece (`README.md`,
   precedência item 1).
3. **Verificar `ALLOWED_PATHS` antes.** `^MAGNATA_OS_.*\.md$` e
   `^docs/magnata-os/` já cobrem tudo. **Exceção:**
   `.claude/skills/*`, `.claude/agents/*` e
   `.claude/MATRIX_DE_RESPONSABILIDADES.md` **não** são cobertos —
   entram em PR separado ou exigem entrada nova em `patterns.sh`.
4. **Corrigir os 13 links quebrados de `docs/magnata-os/README.md`** no
   mesmo PR — é a razão de o problema ser visível.

**Ordem sugerida, se for fatiado:** `DECISOES_ENTIDADES` →
`CONTRATOS` + `ESTADOS` → `ENTIDADES` + `EVENTOS` → `ARQUITETURA` →
Módulo 01 + ADR-001 → skills/subagentes.

**O que a proposta deliberadamente não decide:** se os documentos entram
como estão (com nota de divergência) ou revisados. Isso é decisão de
quem tem autoridade sobre a documentação oficial.
