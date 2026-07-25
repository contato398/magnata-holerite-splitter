# Magnata OS — Módulo 01: Decisões de Implementação

**Status:** DECISÕES DE IMPLEMENTAÇÃO — documento curto, sem código.
**Versão:** 1.1 (consolidada)
**Data original:** 2026-07-22
**Data desta consolidação:** 2026-07-22
**Origem:** decisões fechadas diretamente pela Direção da Magnata, em
resposta às "Decisões Necessárias Antes do Código" listadas em
`MAGNATA_OS_MODULO_01_INGESTAO.md` §22, mais a consolidação que fecha os
itens que a primeira rodada havia deixado em aberto.
**Escopo:** todas as decisões necessárias para planejar as Fases 0 e 1 do
Módulo 01. Nenhuma decisão funcional já aprovada foi reaberta nesta
consolidação — só numeração, contagem e os itens explicitamente marcados
como pendentes na versão anterior foram tratados.

**Contagem auditada nesta consolidação (contagem física, não estimada):**

- **Total de decisões numeradas:** **13** (`DEC-MOD01-001` a
  `DEC-MOD01-013`), sequenciais, sem lacuna e sem identificador duplicado.
- **`APROVADA`:** 12 (001, 002, 003, 004, 005, 006, 007, 008, 009, 011,
  012, 013).
- **`APROVADA POR CONTINUIDADE OPERACIONAL`:** 1 (010).
- **`PENDENTE`:** **0** — nenhuma decisão indispensável para planejar as
  Fases 0 e 1 permanece pendente após esta consolidação.
- Nenhuma decisão está marcada simultaneamente como aprovada e pendente.
- Nenhuma decisão aparece no resumo sem seção correspondente abaixo (cada
  uma das 13 tem seu próprio bloco `## DEC-MOD01-0XX`).

Duas notas técnicas residuais, que **não bloqueiam** nenhuma decisão
funcional, seguem identificadas como `DECISÃO TÉCNICA DE IMPLEMENTAÇÃO`
(§ ao final) — biblioteca exata de geração de UUIDv7 e mecanismo concreto
de configuração por ambiente do limite de tamanho.

Nenhum arquivo além deste foi criado ou alterado nesta consolidação. Nenhum
código, Airtable, configuração ou memória foi tocado.

---

## DEC-MOD01-001 — Primeira origem a migrar

**Decisão:** **upload manual** é a primeira origem a passar pelo Módulo 01,
em shadow mode.

**Justificativa:** é o caminho mais controlável para validar o núcleo novo
(Item de Ingestão, Arquivo, hash, idempotência, auditoria, estados,
eventos, compatibilidade com o Airtable legado) sem depender de e-mail,
gatilho do Apps Script, Make.com ou qualquer processamento automático de
terceiros. Uma falha aqui não compromete a entrada normal de documentos.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §16 (Fase 1
passa a ter uma origem concreta, não genérica), §22 (item resolvido).

---

## DEC-MOD01-002 — Ordem de migração das demais origens

**Decisão:** a sequência de origens, alinhada às fases já definidas em
`MAGNATA_OS_MODULO_01_INGESTAO.md` §16, é:

1. **Upload manual** — shadow mode (Fase 1).
2. **Make.com → `/separar`** — shadow mode, depois porta principal para
   essa origem específica.
3. **Gmail → Apps Script → Render** — shadow mode, depois porta principal.
4. **Consolidação das portas antigas** — as três origens já convergindo
   para o núcleo canônico, rotas legadas mantidas só como fallback.
5. **Ingestão canônica como porta principal** — todas as origens entram
   primeiro pelo Módulo 01; adaptador alimenta o legado (Fase 2 completa).

**Justificativa:** cada origem entra só depois que a anterior já provou o
núcleo em produção-sombra, do caminho mais controlável (upload manual) para
os mais dependentes de terceiros (Make.com, depois Gmail/Apps Script).

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §16 (a
estratégia strangler passa a ter ordem concreta de origem por fase, não
só o nome das fases).

---

## DEC-MOD01-003 — Armazenamento inicial

**Decisão:** **Airtable attachment**, mantido na primeira fase — sem
mudança de infraestrutura de armazenamento agora.

**Justificativa:** é o que já funciona hoje; evita risco de migração de
dado desnecessário; consistente com o princípio de operação preservada
(Manifesto, princípio 1) e com a recomendação já registrada em
`MAGNATA_OS_MODULO_01_INGESTAO.md` §10.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §10, §22
(item resolvido — a recomendação vira decisão).

---

## DEC-MOD01-004 — Tipos de arquivo permitidos inicialmente

**Decisão:** **PDF**, exclusivamente, na primeira fase.

**Justificativa:** é o único tipo tratado com robustez no legado hoje
(extração de texto, classificação); ampliar para outros tipos antes de
validar o núcleo com PDF introduziria variável demais de uma vez.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §11 (tabela de
segurança), §22 (item resolvido).

---

## DEC-MOD01-005 — Regra para mesmo hash

**Decisão:** mesmo hash **não é rejeitado automaticamente**. O módulo
verifica origem e contexto antes de classificar como duplicado — hash
igual é sinal forte, não veredito automático.

**Justificativa:** consistente com o que já estava registrado em
`MAGNATA_OS_MODULO_01_INGESTAO.md` §9 ("mesmo hash não significa
necessariamente mesmo Documento") — a decisão agora formaliza que isso vale
também para a própria dedupliação técnica de Arquivo, não só para a relação
com Documento.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §9 (regra de
"duplicidade legítima" passa a ter critério explícito: verificar origem e
contexto, não só o hash).

---

## DEC-MOD01-006 — Papel do Airtable na Fase 1

**Decisão:** o Airtable **continua sendo a fonte operacional** durante a
Fase 1 (shadow mode). O Módulo 01 grava **por adaptador** — nenhuma tabela
ou campo do Airtable é alterado nesta fase.

**Justificativa:** shadow mode, por definição, não pode ter efeito
operacional (DEC-MOD01-007) — o Airtable legado segue sendo a única fonte
que a operação real utiliza; o módulo novo só observa e compara.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §15 (o
adaptador de saída é, nesta fase, o único ponto de contato do módulo novo
com o Airtable), §22 (item resolvido).

---

## DEC-MOD01-007 — Natureza do shadow mode

**Decisão:** o shadow mode é **sem efeito operacional** — só comparação e
auditoria. O Módulo 01 processa uma cópia da entrada, produz seu próprio
resultado (Item de Ingestão, Arquivo, hash, estado), e **compara** com o
que o legado produziu para a mesma entrada, sem que esse resultado
alimente qualquer fluxo real.

**Justificativa:** é a definição de Fase 1 já registrada em
`MAGNATA_OS_MODULO_01_INGESTAO.md` §16 — esta decisão a confirma
explicitamente como decisão fechada, não só proposta.

**Nota (atualizada nesta consolidação):** esta decisão fecha a
**natureza** do shadow mode. O **critério de saída** (duração, volume e
qualidade) foi consolidado separadamente em **DEC-MOD01-012**, e as
situações que **prorrogam** o shadow mode em **DEC-MOD01-013** — nenhuma
lacuna permanece entre esta decisão e aquelas duas.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §16, §19
(métricas de divergência shadow×legado — critério de saída detalhado em
DEC-MOD01-012).

---

## DEC-MOD01-008 — Destino de itens rejeitados

**Decisão:** itens rejeitados são **registrados separadamente**, e o
**arquivo recebido não é apagado**.

**Justificativa:** preserva evidência para auditoria e para investigar
falsos positivos de rejeição, sem manter o item rejeitado misturado ao
fluxo normal de itens válidos.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §8 (o estado
`REJEITADO` já previa isso implicitamente — agora está explícito que o
Arquivo associado, se já tiver sido recebido, não é descartado), §22 (item
resolvido).

---

## DEC-MOD01-009 — Política de rollback

**Decisão:** rollback significa **desativar a porta canônica e voltar
integralmente ao fluxo legado** — não um rollback parcial por origem ou por
funcionalidade nesta primeira versão.

**Justificativa:** simplicidade e segurança na primeira fase — um rollback
parcial exigiria lógica adicional de coexistência que não se justifica
antes de o módulo provar estabilidade.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §16 (Fase 4,
"plano de rollback disponível a cada etapa" — agora com a política
concreta: reversão integral, não parcial), §18 (critério de pronto
"rollback testado" passa a testar especificamente esse comportamento).

---

## DEC-MOD01-010 — Limite Inicial de Tamanho

**Decisão:** o limite inicial **permanece em 50 MB**, por continuidade com
a operação atual (`MAX_CONTENT_LENGTH`, `app.py:62`) — **nenhuma mudança de
valor em produção nesta etapa**.

**Natureza da decisão:** **provisória e operacional**, não um limite
arquitetural permanente. O valor pode mudar no futuro — o que esta decisão
fixa é que, hoje, ele não muda, e que quando mudar, muda por análise
explícita, não por ajuste pontual de configuração.

**Configurabilidade:** o limite deve ser **configurável por ambiente** (ex.:
variável de ambiente ou equivalente), nunca fixo dentro da regra de
negócio — a regra de negócio verifica um limite configurado, não um número
codificado diretamente na lógica de validação.

**Alterações futuras exigem análise de:** Airtable (limite de anexo e de
armazenamento por base); Render (memória disponível, timeout de
requisição); memória do processo; tempo de upload percebido pelo usuário;
timeout de rede; Apps Script (limite de payload/tempo de execução do
Google); Make.com (limite do scenario); armazenamento (custo e capacidade,
`MAGNATA_OS_MODULO_01_INGESTAO.md` §10); segurança (superfície de ataque de
uploads maiores).

**Arquivos acima do limite:** são **rejeitados de forma explícita** —
nunca truncados silenciosamente, nunca aceitos parcialmente — preservando
auditoria completa da rejeição (§13 do plano de ingestão) e retornando
mensagem segura ao solicitante (sem detalhe técnico interno).

**Decisão da Magnata:** `APROVADA POR CONTINUIDADE OPERACIONAL`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22 (decisão original); consolidada em 2026-07-22
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §11 (tabela
de segurança — o limite passa a ser descrito como configurável, não fixo),
§12 (erro `INGESTAO_ARQUIVO_EXCEDE_LIMITE` a incluir no catálogo de erros
do módulo, se ainda não coberto por `INGESTAO_TIPO_NAO_PERMITIDO`/outro
código existente).

**`DECISÃO TÉCNICA DE IMPLEMENTAÇÃO` (não bloqueia a decisão acima):** o
mecanismo exato de configuração por ambiente (variável de ambiente,
arquivo de configuração, ou outro) será escolhido na implementação.

---

## DEC-MOD01-011 — Estratégia de Identificadores

**Decisão:** toda entidade criada pelo núcleo novo possui **identificador
canônico interno próprio**. Adota-se conceitualmente **UUIDv7** para novos
identificadores internos.

**Aplicação inicial:** Item de Ingestão; Arquivo; evento; erro; tentativa
ou operação auditável que exija identidade própria.

**Registrado expressamente:**
- Airtable Record ID **não é** a identidade canônica de nenhuma entidade —
  consistente com o princípio já fixado em `MAGNATA_OS_CONTRATOS.md` §2.1.
- Message ID, Request ID, hash SHA-256, e-mail, telefone e nome **não são**
  identificadores internos — cada um continua tendo seu papel próprio
  (correlação técnica, deduplicação de conteúdo, contato), nunca substitui
  a identidade canônica da entidade.
- Identificadores externos (Airtable Record ID, Gmail Message ID, ID do
  Make.com, quando existir) são **preservados separadamente**, com
  indicação explícita do sistema de origem — nunca fundidos ao
  identificador canônico.
- O módulo **gera o identificador antes** de qualquer escrita no adaptador
  legado — a existência da entidade, no vocabulário canônico, não depende
  de o Airtable já ter respondido.
- **A indisponibilidade do Airtable não pode obrigar a troca da identidade
  interna** — se a gravação no Airtable falhar e for repetida depois, a
  entidade mantém o mesmo `item_ingestao_id`/`arquivo_id` já gerado.

**Escopo desta decisão:** só entidades **criadas pelo núcleo novo** a
partir de agora. **Não há geração ou migração de IDs de registros já
existentes** no Airtable nesta etapa.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22 (consolidação)
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §22 (item
antes pendente, agora fechado); `MAGNATA_OS_CONTRATOS.md` §2.1 (recebe a
escolha concreta de esquema — UUIDv7 — sobre o princípio já registrado ali).

**`DECISÃO TÉCNICA DE IMPLEMENTAÇÃO` (não bloqueia a decisão acima):** a
biblioteca/implementação exata de geração de UUIDv7 será escolhida na
implementação.

---

## DEC-MOD01-012 — Critério de Saída do Shadow Mode

**Decisão:** o shadow mode **não termina só por passagem de tempo**. A
saída exige, **cumulativamente**, os critérios abaixo.

### Volume mínimo (todos obrigatórios, cumulativamente)
- Pelo menos **14 dias consecutivos** de observação.
- Pelo menos **100 itens reais** processados em shadow mode.
- Representação das origens que participarão da fase seguinte (não sair do
  shadow mode de uma origem sem volume real daquela origem específica).
- Presença de casos com múltiplos anexos, repetição, falha e arquivo
  inválido — quando ocorrerem naturalmente ou por teste controlado (não é
  aceitável sair do shadow mode sem nenhum desses casos ter sido
  observado, mesmo que artificialmente).

### Critérios obrigatórios (todos, cumulativamente)
- Zero perda de Arquivo.
- Zero interrupção do fluxo legado.
- Zero duplicidade crítica produzida pelo núcleo novo.
- 100% dos itens com `correlation_id`.
- 100% dos itens com hash calculado ou erro explícito (nunca ausência
  silenciosa de hash).
- 100% das falhas registradas sem falso sucesso.
- Todas as divergências entre shadow e legado classificadas (nenhuma
  divergência "sem categoria").
- Nenhuma divergência crítica sem explicação.
- Adaptador legado validado em ambiente de teste.
- Rollback testado (não só documentado).
- Métricas e logs disponíveis.
- **Aprovação formal da Direção da Magnata e do responsável técnico** —
  os critérios acima sendo satisfeitos é condição necessária, não
  suficiente; a saída exige decisão humana explícita, não é automática.

### Critério de comparação (categorias a avaliar separadamente)
Paridade de recebimento; paridade de Arquivo; paridade de metadados;
divergência de hash; divergência de quantidade de anexos; divergência de
origem; divergência de resultado; falhas exclusivas do legado; falhas
exclusivas do shadow.

**Registrado expressamente:** **não se exige que o núcleo novo reproduza
um erro do legado para atingir "paridade".** Se o legado falha onde o
núcleo novo teria sucesso (ou vice-versa, de forma justificável), isso é
uma divergência a classificar e entender — não um defeito do lado que
"acertou".

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22 (consolidação)
**Documentos impactados:** `MAGNATA_OS_MODULO_01_INGESTAO.md` §16 (Fase 1
ganha critério de saída numérico), §18 (critérios de pronto), §19
(métricas — os itens acima viram a fonte das métricas obrigatórias),
`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md` §22 (reproduz
integralmente estes números, sem alterá-los).

---

## DEC-MOD01-013 — Situações que Prorrogam o Shadow Mode

**Decisão:** o shadow mode **continua** (não é promovido à Fase 2) quando
houver qualquer uma das situações abaixo, mesmo que os critérios
numéricos de DEC-MOD01-012 já estejam nominalmente satisfeitos:

Perda de Arquivo; duplicidade não explicada; divergência crítica; falha de
correlação (`correlation_id` ausente ou quebrado); erro silencioso (falha
que retornou como sucesso); impossibilidade de rollback; ausência de
métricas; diferença estrutural ainda não tratada pelo adaptador; volume
insuficiente; origem prioritária não representada.

**Justificativa:** os critérios de DEC-MOD01-012 definem o piso para
**considerar** a saída — esta decisão define o que **impede** a saída
mesmo que o piso pareça atingido, evitando que uma leitura mecânica dos
números ignore um problema real ainda não resolvido.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-22 (consolidação)
**Documentos impactados:** mesmos de DEC-MOD01-012.

---

## Confirmação de Escopo

Nenhum arquivo existente foi alterado além deste, nesta consolidação.
Nenhum código, tabela do Airtable, configuração ou memória foi tocado.

**Resultado da consolidação:** o documento termina com **0 decisões
pendentes indispensáveis** para planejar as Fases 0 e 1. Duas notas de
`DECISÃO TÉCNICA DE IMPLEMENTAÇÃO` permanecem identificadas (biblioteca de
UUIDv7; mecanismo de configuração por ambiente do limite de tamanho) —
nenhuma delas altera as decisões funcionais já aprovadas, e nenhuma
bloqueia o planejamento técnico das Fases 0/1
(`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`).
