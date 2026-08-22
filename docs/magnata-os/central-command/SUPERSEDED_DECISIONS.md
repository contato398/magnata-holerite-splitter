# SUPERSEDED_DECISIONS — Magnata OS

Trilha explícita de decisões antigas substituídas por decisões novas.
Nada aqui foi apagado dos registros de origem — este arquivo só torna a
substituição rastreável num único lugar, no formato pedido:

```
DECISÃO ANTIGA
→ SUPERADA POR
→ DECISÃO NOVA
```

---

## SUP-001

```
DIR-001 (2026-06-13) — pré-cadastro deve seguir 4 ramos de decisão
(cadastrar_ativo_automaticamente / criar_pre_cadastro_seguro /
enviar_para_revisao / ignorar_documento), com 2 limiares de confiança.
Código da época (v2.16) só implementava 3 saídas mais simples.
→ SUPERADA POR
DIR-001b (v2.66, 2026-07-01) — "aprovação por exceção": contrato cria
cadastro IMEDIATO como Status="Validação Pendente"; inativação/ajuste
manual fica com o humano. Não é exatamente os 4 ramos originais, mas
cumpre o objetivo de fundo da diretiva original (máxima automação,
revisão manual só em exceção) por um caminho mais simples.
```
**Confiabilidade:** 🔍 a versão v2.66 é a mais recente confirmada nesta
auditoria; não há evidência de mudança posterior, mas também não há
reconfirmação contra o `app.py` de hoje (2026-08-21).

---

## SUP-002

```
Rótulo Horario.Descricao (PAR/ÍMPAR) da Secullum tratado inicialmente
como fonte confiável de paridade de escala (uso implícito em
[[automacao_cadastro_holerite_sync_new_employees]], campo "Grupo de
Escala", 2026-06-25).
→ SUPERADA POR
v2_53_folga_bonus_assiduidade.md (2026-06-25, mesmo dia/ciclo) —
3 achados provam que Horario.Descricao não é confiável para nada
preciso (paridade invertida, coluna Normais sempre vazia em ~27/88
contas, faixa de horário do texto não bate com a real).
→ SUPERADA POR
v2_65_saneamento_final_escalas_jun2026.md (2026-06-29) — metodologia
final: paridade determinada pela primeira batida real de entrada num
dos dois dias-base fixos (28/05 ou 29/05), nunca pelo rótulo de texto.
```
**Confiabilidade:** ✅ confirmado dentro do próprio conjunto de
documentos auditados — é uma correção de metodologia bem documentada,
com 3 estágios claros.

---

## SUP-003

```
Rascunho da Etapa 4 do Powerpack (MAGNATA_OS_CAPACIDADES.md §3.10,
versão bloqueada) — "Segurança" tratado como módulo com 5 capacidades
próprias, criando conflito com MAGNATA_OS_MODULOS.md (10 módulos, sem
Segurança). Registrado como Bloqueador 1 em
MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA4_DIVERGENCIAS_REVISAO.md
(2026-07-25).
→ SUPERADA POR (🔍 inferido, sem ADR-002 confirmando)
Versão hoje em `main`: MAGNATA_OS_MODULOS.md §0
"Responsabilidades Transversais" e MAGNATA_OS_CAPACIDADES.md §3.10
"Responsabilidades Transversais (Segurança, Observabilidade,
Governança)" — Segurança tratada como requisito não funcional
transversal a todos os módulos, não como módulo próprio (Opção C do
próprio relatório de bloqueio).
```
**Confiabilidade:** 🔍 PRECISA SER VALIDADO — ver DEC-004/PEN-015.

---

## SUP-004

```
Rascunho da Etapa 4 — MAGNATA_OS_CAPACIDADES.md declarava 6 camadas em
§1, mas usava 8-9 na prática (+Segurança, +Plataforma, +Governança) em
§3.10. Registrado como Bloqueador 2.
→ SUPERADA POR (🔍 inferido, sem ADR-002 confirmando)
Versão hoje em `main`: 6 camadas consistentes (Entrada, Inteligência,
Transformação, Negócio, Entrega, Auditoria) + Plataforma explicitamente
tratada como camada transversal separada, não uma 7ª camada do mesmo
tipo.
```
**Confiabilidade:** 🔍 PRECISA SER VALIDADO — mesma ressalva de SUP-003.

---

## SUP-005

```
Rascunho da Etapa 4 — MAGNATA_OS_ROADMAP.md declarava "Nível de
autonomia: 70%" para a Fase 1, violando a "Regra de ouro" do próprio
MAGNATA_OS_MATRIZ_ARQUITETURAL.md ("nenhuma fase concede > 50% antes da
Fase 10"). Registrado como Bloqueador 3.
→ SUPERADA POR (🔍 inferido, sem ADR-002 confirmando)
Versão hoje em `main`: sistema de níveis qualitativos (Nenhuma
autonomia → Leitura local → Análise assistida → Execução controlada →
Execução supervisionada → Produção autorizada), sem percentuais. Fase 1
= "Análise assistida" em ambos os documentos, consistente. "Regra de
ouro" reformulada em torno de "Produção autorizada" (só Fase 11+),
eliminando a comparação numérica que gerava o conflito original.
```
**Confiabilidade:** 🔍 PRECISA SER VALIDADO — mesma ressalva de SUP-003/004.

---

## SUP-006

```
ARQUITETURA_FASE_2_DECISAO_FINAL.md (2026-07-20) — modelo de decisão
arquitetural pontual, documento avulso, não versionado como sistema
(citado pelo próprio docs/magnata-os/README.md §"Documentos
históricos" com essa descrição exata).
→ SUPERADA POR
MAGNATA_OS_MANIFESTO.md (2026-07-22 em diante) — fundação versionada,
com regra de precedência e changelog formal, iniciada pela diretiva
DIR-003.
```
**Confiabilidade:** ✅ confirmado — é a própria leitura que o índice
oficial (`docs/magnata-os/README.md`) já faz.

---

## SUP-007

```
Diretiva original de e-mails (v2_29_distribuicao_email.md, 2026-06-15)
— ambiguidade não resolvida entre contato@magnataservicos.com.br e
depessoalcontabilidade@hotmail.com / dpessoal.contabilidade1@hotmail.com
como remetente de recebimento (DEC-010).
→ PARCIALMENTE SUPERADA POR
docs/decisoes/remetentes-dp-fiscal.md (2026-08-03, DEC-007) — corrige
o endereço configurado para dp.contabilidade1@hotmail.com →
dpessoal.contabilidade1@hotmail.com, mas não há confirmação nesta
auditoria de que toda a ambiguidade original (env vars vs. Apps
Script) foi fechada.
```
**Confiabilidade:** 🔍 PRECISA SER VALIDADO.
