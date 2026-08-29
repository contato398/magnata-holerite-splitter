# Primeiro corredor automatizado E2E da Prestação de Contas — Holerite primeiro

**Data:** 2026-08-29
**Branch:** `fix/corredor-prestacao-holerite-e2e`
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

Antes desta mudança, o Módulo 01 (Documental) e a Prestação de Contas
(`magnata_os/classificacao/`) eram dois mundos que só se encontravam
através de `FonteInventarioPrestacaoResultadosShadow`/`_converter_resultado`
(`inventario_prestacao_resultados.py`) — um conversor 100% acoplado ao
contrato `ResultadoItem` da Família B (`importacao_lote/contratos.py`,
fluxo ZIP/manifesto), nunca ao pipeline real de esteira do Módulo 01
(`EstadoEsteiraDocumento`/`ItemResumoLote`).

Este trabalho fecha o primeiro corredor **automatizado, ponta a ponta,
em shadow mode**, para Holerite avulso:

```
e-mail (ou qualquer FonteMensagensEmail)
  -> AdapterCapturaEmail -> ServicoCriacaoLote
  -> CLASSIFICACAO/CONCLUIDO -> IDENTIFICACAO/CONCLUIDO
  -> HoleriteConfirmadoDTO (fato OBSERVADO: colaborador + competência
     extraída do próprio documento)
  -> ponte_prestacao_holerite.confirmar_holerite(s)_para_inventario
     (competência ESPERADA independente + FonteVinculosPrestacao)
  -> ItemInventarioPrestacao -> avaliar_prestacao_shadow
  -> PRONTO / FALTANDO (com tipos_faltantes explícitos)
```

Sem nenhuma escrita externa real (Gmail/Airtable/Postgres) e sem
qualquer alteração de `app.py`/`render.yaml`/`Procfile`/`celery_app.py`.

## Seam novo: Módulo 01 -> Prestação de Contas

O gate de identificação (`politica_identificacao_holerite.py`,
`ServicoCriacaoLote._processar_um_arquivo`) já decidia se um Holerite
avulso tinha colaborador RESOLVIDO — mas o resultado nunca saía do
Módulo 01 em forma consumível pela Prestação. Esta mudança adiciona:

- **`HoleriteConfirmadoDTO`** (`dtos_esteira.py`) — DTO sanitizado,
  populado em `ServicoCriacaoLote._processar_um_arquivo` SÓ quando a
  identificação termina de fato RESOLVIDA (nunca AMBIGUA,
  NAO_ENCONTRADA, MESTRE_SUSPEITO ou erro técnico). Carrega só fatos
  OBSERVADOS: `documento_id`, `hash_sha256`, `colaborador_entidade_id`
  (record id, não é PII) e a competência OBSERVADA no próprio
  documento (reaproveitando `extrair_competencia_de_texto`,
  `importacao_lote/dominio.py`, já pura e já existente). Nunca carrega
  competência esperada nem cliente — essas duas decisões pertencem
  exclusivamente à ponte, nunca ao Módulo 01.
- **`ponte_prestacao_holerite.py`** (módulo novo, pura) —
  `confirmar_holerite_para_inventario`/`confirmar_holerites_do_lote`
  traduzem um `HoleriteConfirmadoDTO` num `ItemInventarioPrestacao`
  (contrato neutro já existente, `prestacao_readiness.py`) reaproveitando,
  sem alteração: `validar_competencia` (importacao_lote/dominio.py) e
  `resolver_clientes_validado`/`FonteVinculosPrestacao`
  (vinculos_prestacao.py).

Nenhum novo `FonteInventarioPrestacao` de produção foi criado — a saída
da ponte é uma tupla pura de `ItemInventarioPrestacao`, plugável em
qualquer `FonteInventarioPrestacao` já existente (inclusive um fake de
teste simples, como já provado pelo E2E de PR #82).

## Competência esperada: origem independente, nunca circular

`confirmar_holerite_para_inventario` recebe `competencia_esperada:
Optional[Tuple[int, int]]` como parâmetro **explícito** — nunca inferida
do próprio documento, nunca um default. Este é o seam deliberado pedido
pela missão (§5): quando `None` (nenhuma competência esperada
configurada ainda para este ciclo), a função devolve `None` imediatamente,
sem tentar nenhuma comparação — o documento fica de fora do inventário,
resultado explicitamente pendente, nunca um `PRONTO` por ausência de
evidência.

Quando presente, a comparação é sempre `observada == esperada`
(`validar_competencia`, já existente) — nunca o inverso
(`esperada = observada`), que seria validação circular. O mesmo padrão
de "competência esperada como parâmetro externo" já existia em
`scripts/prestacao_readiness_shadow_real.py --competencia` e no próprio
parâmetro obrigatório `competencia` de `avaliar_prestacao_shadow` — esta
mudança só estende o mesmo princípio até a fronteira do Módulo 01.

Um bootstrap operacional futuro (fora de escopo desta missão) decidiria
de onde essa competência esperada viria de fato em produção (ex.: ciclo
de fechamento da folha, parâmetro de execução) — este corredor só prova
que, uma vez fornecida, o fluxo automatizado funciona ponta a ponta.

## Colaborador -> cliente: sem default, nunca arbitrário

`ponte_prestacao_holerite.py` usa `ReferenciaCanonica("COLABORADOR",
entidade_id)` (nunca `"FUNCIONARIO"`, convenção já estabelecida em
`politica_identificacao_holerite.py`) e `resolver_clientes_validado`
(já existente) exige resolução `RESOLVIDA` com exatamente 1 valor
confirmado — qualquer ambiguidade, conflito ou falha técnica da fonte
de vínculos devolve `None`, nunca associa um cliente por aproximação.

## O que isto NÃO faz (por desenho)

- Não ativa Gmail real, Airtable real ou Postgres real — todos os
  testes usam fakes na fronteira (mesmo padrão de
  `test_prestacao_shadow_e2e.py` e `test_magnata_os_documental_modulo01_
  email_captura.py`).
- Não cria uma segunda implementação de `FonteInventarioPrestacao` de
  produção nem um segundo sistema de readiness — reaproveita
  `avaliar_prestacao_shadow`/`avaliar_prestacao_readiness` sem alteração.
- Não altera `FonteInventarioPrestacaoResultadosShadow` (o conversor
  Família B) — esse caminho legado continua intacto e em paralelo;
  migrá-lo ou aposentá-lo é decisão futura separada.
- Não estende este corredor aos outros 16 tipos documentais — estratégia
  Holerite-primeiro, deliberada.
- Não decide de onde a competência esperada real virá em produção — só
  prova que, uma vez fornecida, o corredor inteiro funciona.

## Testes (9 casos obrigatórios, `test_corredor_prestacao_holerite_e2e.py`)

1. Caminho feliz — PRONTO.
2. Holerite válido, outro tipo obrigatório ausente — FALTANDO explícito.
3. Colaborador ambíguo — nunca confirma Holerite.
4. Vínculo de cliente ambíguo — nunca associa arbitrariamente.
5. Competência observada divergente da esperada — nunca confirma.
6. Competência esperada ausente (`None`) — nunca inventa, pendente.
7. Documento duplicado — nunca duplica contribuição no inventário.
8. Outro tipo documental — nunca passa pelo corredor de Holerite.
9. Falha técnica da fonte de vínculos — ingestão preservada, nunca um
   falso PRONTO.

## Documentação relacionada

- `docs/decisoes/composition-root-modulo01-v1.md` — composition root
  reaproveitado sem alteração por este corredor.
- `magnata_os/classificacao/inventario_prestacao_resultados.py` —
  precedente Família B da mesma tradução, mantido intacto.
- `CLAUDE.md` §4 — separação de dimensões (`etapa_atual`/`situacao`/
  `motivo_bloqueio`/`proxima_acao`), princípio já preservado aqui.
