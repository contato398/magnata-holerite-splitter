# Wiring real da Folha/Cartão de Ponto no inventário da Prestação (v1)

**Data:** 2026-09-03
**Branch:** `fix/wiring-ponto-inventario-v1`
**Base:** `main @ f56990c777d3aea78a5f2cf257a1d9215314b6d5` (PR #127 mesclado)
**Status:** ✅ Implementado, testado (sintético) — fecha o corredor real entre a identidade temporal documental (PR #127) e o motor canônico de inventário/completude da Prestação de Contas.

## Motivação

O PR #127 implementou a identidade temporal real de um documento de
Folha/Cartão de Ponto (`ResolucaoDocumentalTemporalPonto`), mas nunca
foi lida por nenhuma `FonteInventarioPrestacao` — o motor de
readiness/completude não "enxergava" Ponto de verdade ainda. Esta
missão fecha exatamente esse corredor, sem criar novo motor.

## Auditoria (Gate Pétreo 0)

Confirmado no HEAD `f56990c`: nenhuma implementação de
`FonteInventarioPrestacao` para Ponto existia ainda (`grep` por
`class Fonte.*Ponto` em `magnata_os/` não encontrou nada) — gap real
comprovado, não coberto por mecanismo existente.

Mecanismos reutilizados sem alteração: `ResolucaoDocumentalTemporalPonto`,
`resolver_clientes_por_periodo`/`FonteAlocacaoHistorica` (interseção de
período, já corrigido na revisão do PR #127), `ItemInventarioPrestacao`
(`prestacao_readiness.py`), `FonteInventarioPrestacaoComposta`
(`fonte_inventario_composta.py`), `avaliar_prestacao_readiness`
(`prestacao_readiness.py`), `TIPO_FOLHA_DE_PONTO`
(`produtores_evidencia_ponto.py`).

## O que foi criado

`magnata_os/classificacao/fonte_inventario_prestacao_ponto_temporal.py`
— `FonteInventarioPrestacaoPontoTemporal`, implementa `FonteInventarioPrestacao`
(Protocol já existente, sem alteração). Para cada resolução temporal já
persistida:

1. confirma que o `Documento` canônico existe (`FonteExistenciaDocumento`,
   porta neutra e mínima — nunca produz item para resolução órfã);
2. exige `resolucao_competencia.estado == RESOLVIDA` e que o valor bata
   com a competência pedida — `CONFLITO`/`AMBIGUA`/`NAO_ENCONTRADA`
   nunca viram item "presente";
3. exige `colaborador_id` e período confiável;
4. resolve cliente(s) por interseção com alocação histórica
   (`resolver_clientes_por_periodo`, reaproveitado sem alteração) — 0
   vínculos nunca vira item; 2+ vínculos legítimos (transferência
   intra-período) produzem 1 item lógico por cliente, mesmo
   `documento_id`, nunca escolha arbitrária.

Nenhuma coluna de cliente/posto é lida como fato persistido — sempre
recalculada a cada `listar()`, mesma disciplina do PR #127.

## Camadas — decisão de dependência

`classificacao/` continua nunca importando `documental/modulo01/`
diretamente (é `documental/modulo01` que importa `classificacao/`,
nunca o inverso). Por isso `FonteResolucoesTemporaisPonto` e
`FonteExistenciaDocumento` são Protocols NEUTROS declarados neste
módulo — compatíveis por duck typing com
`RepositorioResolucaoTemporal`/`RepositorioDocumentos` (`modulo01`),
mas sem import cruzado. A injeção real acontece na borda de composição
(fora do escopo desta missão — hoje só testes sintéticos).

## Cardinalidade — fora de escopo (registrado, não escondido)

Esta missão só prova PRESENÇA documental real — não implementa "1
Folha de Ponto por colaborador esperado" (padrão já usado por Holerite,
`holerite_obrigatorio_prestacao.py`). Fica para missão própria.

## Testes

`test_wiring_ponto_inventario_e2e.py` (14 testes) cobrindo os 15 casos
pedidos: documento válido/1 cliente, transferência entre 2 clientes,
sem competência, CONFLITO, sem alocação, resolução inexistente,
documento órfão, reprocessamento sem duplicar, ordem determinística,
composição com outra fonte via `FonteInventarioPrestacaoComposta`,
readiness usando o motor existente (PRONTO e FALTANDO), nenhum item
fabricado para resolução insuficiente, isolamento de Airtable/`app.py`/
SKY (AST).

Suíte geral: 2040 passed, 45 skipped — nenhuma regressão.

## Governança

- Nenhuma migration nova, nenhuma escrita de domínio, nenhuma alteração
  na API de atomicidade do PR #127.
- `app.py` não tocado.
- 15 gates de `scripts/ci/validate_governance.sh` aprovados localmente
  contra o intervalo exato `origin/main...HEAD`.
