# ADR-001: Nomenclatura — "Item de Ingestão" vs. "Documento"

**Status:** PROPOSTA (Não decidida)
**Data:** 2026-07-25
**Autores:** Magnata OS Architecture
**Impacto:** Alto (afeta código, documentação, contratos)

---

## Contexto

Existe divergência não resolvida entre dois nomes para a mesma entidade:

1. **"Item de Ingestão"** — usado na documentação fundacional (`MAGNATA_OS_MODULO_01_INGESTAO.md`, `MAGNATA_OS_CONTRATOS.md`, etc.)
2. **"Documento"** — usado no código já implementado em `magnata_os/documental/modulo01/dominio.py`

Ambos referem-se ao artefato que entra pelo módulo de Ingestão: um arquivo bruto capturado de e-mail, upload ou API.

Esta divergência foi **registrada explicitamente** em `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` §4.1 com recomendação de criar ADR. Nem renomear código, nem reescrever documentação em silêncio — apenas decidir de forma explícita e auditável.

---

## Alternativa A: Padronizar em "Item de Ingestão"

### Descrição
Renomear a classe `Documento` em `magnata_os/documental/modulo01/dominio.py` para `ItemIngestao`.
Atualizar todo código que a referencia.

### Justificativa
- Alinha código com documentação
- Diferencia o artefato bruto (Item de Ingestão) do artefato processado (Documento, resultado da Classificação)
- Seguir terminologia oficial dos contratos e máquinas de estado

### Desvantagens
- Risco de regressão em código já funcionando em produção
- `ItemIngestao` é nome mais verboso
- Mudança em `magnata_os/` (que é protegido enquanto legado) exige autorização e teste completo
- Nome em português vs. código Python (mescla de linguagens)

### Critérios de sucesso
- Todas as referências renomeadas
- Testes passam em `magnata_os/`
- Rastreabilidade: commit com mensagem clara do motivo
- Nenhuma quebra de contrato com código legado

---

## Alternativa B: Padronizar em "Documento"

### Descrição
Renomear "Item de Ingestão" na documentação para "Documento".
Atualizações ocorrem em: `MAGNATA_OS_MODULO_01_INGESTAO.md`, `MAGNATA_OS_CONTRATOS.md`, `MAGNATA_OS_ESTADOS.md`, e documentos de fase.

### Justificativa
- Código já está funcional com esse nome
- Alinha com terminologia legado do `app.py` (que também usa "Documento")
- Menos código para mudar (documentação é refazível, código é arriscado)
- Reduz divergência com legado

### Desvantagens
- Perde a distinção semântica entre artefato bruto (entrada) e artefato processado (saída)
- Documentação precisa ser reescrita em múltiplos arquivos
- Contratos já publicados precisam de nova versão
- Pode gerar confusão com "Documento" de Holerite, FGTS, etc.

### Critérios de sucesso
- Documentação atualizada e versionada
- Contratos refeitos com nova versão
- Rastreabilidade: changelog em cada documento
- Clareza de que "Documento" no contexto de Ingestão é diferente de "Documento" de Folha

---

## Alternativa C: Usar ambos (com contexto)

### Descrição
Manter "Item de Ingestão" quando se fala do artefato na camada Entrada.
Permitir "Documento" quando o mesmo artefato já passou para Classificação e além.

Define-se em contrato:
- `Item de Ingestão` = artefato bruto em `magnata_os/ingestao/` (Fase 3+)
- `Documento` = artefato processado em `magnata_os/classificacao/` e módulos subsequentes

### Justificativa
- Mantém semântica rica (nomes diferentes para estados diferentes)
- Sem renomeação de código (risco baixo)
- Código já usa `Documento` (alinhado com Alternativa C)
- Documentação usa "Item de Ingestão" na Ingestão, "Documento" depois (alinhado com semanticidade)

### Desvantagens
- Exige treino de operador (dois nomes para "quase a mesma coisa")
- Contratos precisam ser bem claros sobre a transição
- Pode gerar confusão em interfaces web

### Critérios de sucesso
- Contrato define explicitamente a transformação: `ItemIngestao` → `Documento`
- Código e documentação refletem a distinção
- Painel operacional deixa claro qual entidade está em qual módulo

---

## Alternativa D: Modelo de Domínio Aninhado

### Descrição
Na documentação e código, usar:
- **Ingestão:** `Ingestão.Documento` (artefato na Ingestão, irmão da Classificação)
- **Classificação:** `Classificação.Documento` (artefato na Classificação, irmão da Ingestão)
- Cada módulo tem seu próprio conceito de "Documento"

### Justificativa
- Elimina ambiguidade de namespace
- Código Python pode usar `ingestao.Documento` e `classificacao.Documento`
- Documentação fica clara: qual módulo possui o conceito
- Alinha com design de domínio por módulo

### Desvantagens
- Exige refatoração maior de domínio
- Pode gerar complexidade de contrato entre módulos
- Diferente do padrão legado (Airtable tem apenas "Documento", não namespaced)

### Critérios de sucesso
- Schema de domínio redefinido com namespaces
- Contratos de passagem entre módulos mapeiam transformações
- Código refatorado sem quebra de funcionalidade

---

## Recomendação Inicial (não vinculativa)

**Alternativa C** parece equilibrar:
- Baixo risco de regressão (código legado intacto)
- Clareza semântica (nomes refletem estado)
- Suportabilidade (operador sabe qual é qual pelo contexto do módulo)

**Mas** essa é uma recomendação de trade-off, não uma decisão — cabe à Direção/Engenharia da Magnata OS fazer.

---

## Próximas Ações

1. **Direção da Magnata decide** qual alternativa seguir
2. **Registra a decisão** (Alternativa + Motivo) neste mesmo arquivo, marcando Status = `APROVADA`
3. **Se Alternativa A:** criar subtarefa de renomeação de código
4. **Se Alternativa B:** criar subtarefa de reescrita de documentação
5. **Se Alternativa C:** criar subtarefa de mapeamento de transição em contrato
6. **Se Alternativa D:** criar subtarefa de refatoração de domínio

Até lá, nenhuma ação unilateral. Documenta-se a divergência (já feito), não se escolhe em silêncio.

---

## Referências

- `MAGNATA_OS_MODULO_01_INGESTAO.md` — usa "Item de Ingestão"
- `MAGNATA_OS_CONTRATOS.md` § Ingestão — define contrato de Item
- `magnata_os/documental/modulo01/dominio.py` — usa classe `Documento`
- `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` §4.1 — registro original do conflito
- `MAGNATA_OS_MATRIZ_ARQUITETURAL.md` § Rastreabilidade Legado → Canônico — mapeia "Item de Ingestão" → "Documento"
