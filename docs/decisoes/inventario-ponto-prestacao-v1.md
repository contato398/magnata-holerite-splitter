# Fonte de inventário de Folha/Cartão de Ponto (v1)

**Data:** 2026-09-03
**Branch:** `fix/inventario-ponto-prestacao-v1`
**Base:** `main @ 91f0eb974a76e07122a147f1b173eb7baa21ec96` (PR #124 mesclado)
**Status:** ✅ Implementado, testado (shadow) — fecha o gap "Folha de Ponto: NECESSITA EVIDÊNCIA — não construído" nomeado em `docs/decisoes/inventario-real-prestacao-v1.md`.

## Motivação

Fechar exclusivamente o gap de Folha/Cartão de Ponto na automação da
Prestação de Contas, reutilizando o motor canônico já existente
(`FonteInventarioPrestacao` → `FonteInventarioPrestacaoComposta` →
`executar_ciclo_prestacao` → readiness → pacote/completude) — sem criar
novo motor, classificador ou orquestrador.

## Auditoria (Fase 0) — o que já existia

| Peça | Onde | Estado antes |
|---|---|---|
| Tipo canônico `'Folha de Ponto'` | `produtores_evidencia_ponto.py::TIPO_FOLHA_DE_PONTO` | pronto, já usado pelo classificador geral e pelo motor de tipo textual/estrutural |
| Perfil de aplicabilidade (granularidade colaborador) | `perfil_aplicabilidade_documental.py` linha 208 | pronto — `'Folha de Ponto': _perfil_granularidade_colaborador(...)` |
| `'Folha de Ponto'` no vocabulário de requisitos | `normalizacao_requisitos_prestacao.py` linha 31 | pronto |
| Adaptador genérico `ResultadoResolucaoSemantico -> ItemInventarioPrestacao` | `adaptador_inventario_prestacao.py` | pronto, genérico — já suporta Ponto sem alteração, para documentos que passam pelo corredor de resolução (texto extraído) |
| **Fonte de inventário por AGREGAÇÃO de registros diários já existentes** (schema real: 1 registro/dia, sem campo de competência) | — | **não existia** — gap real fechado por esta missão |
| Janela de dias do ciclo (competência → intervalo de datas, incl. ciclos não coincidentes com o mês civil) | — | **não existia** |

Schema real confirmado (não inventado): `AT_PONTO = 'tblmgV10s3dZiP8av'`,
campos `F_FUNC`/`F_DATA`/`F_ENTRADA`/`F_SAIDA_AL`/`F_RETORNO_AL`/`F_SAIDA`
— já em uso por `src/ingestao_secullum.py` (espelhamento Secullum, em
produção). Confirma que Ponto é 1 registro POR DIA, nunca 1 registro por
competência como Holerite/Extrato — por isso a peça faltante era
justamente a agregação por janela de dias, nunca um classificador novo.

## O que foi criado

1. **`magnata_os/classificacao/ciclo_ponto_prestacao.py`** — política
   pura da janela de dias do ciclo de Ponto (`PoliticaCicloPontoPrestacao`,
   `JanelaCicloPonto`, `CicloPontoClienteOverride`). Default = mês civil
   da competência; override por cliente representa ciclos deslocados,
   configurado pelo DIA DE FECHAMENTO (`dia_fechamento`) — o ciclo
   termina nesse dia, INCLUSIVE, e começa no dia seguinte ao fechamento
   do ciclo anterior (ex.: fechamento=28, competência junho/2026 ->
   ciclo 29/05/2026 a 28/06/2026 — **correção de uma revisão
   independente**: a v1 original deste módulo modelava incorretamente
   esse mesmo caso como 28/05 a 28/06, sobrepondo 1 dia entre ciclos
   consecutivos; corrigido antes do merge). Mesmo padrão de
   exceção-como-configuração já usado por `DeslocamentoCompetenciaCliente`
   (`competencia_esperada_prestacao.py`). `overrides=()` é o default
   seguro: **nenhuma exceção real de ciclo de Ponto está confirmada
   hoje para nenhum cliente** — o cenário 29/05–28/06 usado nos testes é
   um caso adversarial SINTÉTICO pedido pela missão, nunca uma regra
   real do SKY Tatuí.

2. **`magnata_os/classificacao/fonte_inventario_ponto_prestacao.py`** —
   `FonteInventarioPontoPrestacao`, implementa `FonteInventarioPrestacao`
   (porta já existente, sem alteração). Agrega N `RegistroPontoBruto`
   (1 por dia) dentro da janela do ciclo num único `ItemInventarioPrestacao`
   por colaborador/competência (mesma cardinalidade de item que Holerite).
   Resolve cliente via `resolver_clientes_validado`/`FonteVinculosPrestacao`
   — o MESMO vínculo histórico já usado por Holerite, nunca uma segunda
   resolução. Duplicidade conflitante (2 registros do mesmo dia com
   assinaturas de batida diferentes) descarta o dia como evidência —
   nunca produz falso COMPLETO. Nenhum import de Airtable/requests neste
   módulo (provado por teste AST); nenhum literal de cliente por nome
   (provado pelo mesmo teste).

3. **`magnata_os/documental/importacao_lote/adapters/airtable_ponto_prestacao.py`**
   — `FonteRegistrosPontoAirtableShadow`, adapter READ-ONLY (só
   `listar_registros`, nenhuma escrita) que implementa a porta
   `FonteRegistrosPontoBrutos` do núcleo. IDs de tabela/campo duplicados
   aqui (nunca importados de `src/ingestao_secullum.py` nem de `app.py`)
   — mesma disciplina já registrada em
   `magnata_os/documental/importacao_lote/CLAUDE.md`. Nenhuma regra
   semântica mora neste adapter — só mapeia schema bruto para
   `RegistroPontoBruto`.

## Fora de escopo (registrado, não escondido)

- **Obrigatoriedade por cardinalidade de colaborador** (o mesmo tipo de
  regra que `holerite_obrigatorio_prestacao.py` já tem para Holerite)
  **não foi criada para Ponto** — a missão pediu só a fonte de
  inventário; inventar essa regra de negócio sem evidência confirmada
  violaria a regra pétrea #9. A readiness/pacote hoje trata "Folha de
  Ponto" com `quantidade_minima=1` genérico (1 item de QUALQUER
  colaborador já basta para o tipo aparecer como presente) — se a regra
  real exigir 1 por colaborador esperado, isso é uma missão futura
  própria, no mesmo padrão de `combinar_pacote_com_holerite`.
- **Nenhuma exceção real de ciclo de Ponto está confirmada** para
  nenhum cliente (inclusive SKY Tatuí) — `POLITICA_CICLO_PONTO_PRESTACAO_V1`
  fica com `overrides=()` até que uma exceção real seja confirmada e
  registrada, do mesmo jeito que `DESLOCAMENTO_SKY_TATUI` foi.

## Prova de composição

`test_inventario_ponto_composicao_e2e.py` demonstra, com dados
sintéticos: documentos de ponto → `FonteInventarioPontoPrestacao` →
`FonteInventarioPrestacaoComposta` → `executar_ciclo_prestacao` →
readiness → pacote PRONTO (com Ponto presente) e INCOMPLETO (com Ponto
ausente) — Folha de Ponto agora contribui de verdade para a completude.
Uma validação estrutural adicional usa `REFERENCIA_CLIENTE_SKY_TATUI`
(referência já existente, ciclo default) só para provar que o
comportamento já existente funciona igual para esse cliente — nenhuma
regra nova foi inventada para ele.

## Testes

- `test_magnata_os_classificacao_ciclo_ponto_prestacao.py` (18 testes) —
  política de janela: mês civil, fechamento 28 (junho e julho/2026,
  29/05–28/06 e 29/06–28/07), ausência de sobreposição/lacuna entre
  ciclos consecutivos, virada de ano, fevereiro bissexto e
  não-bissexto, determinismo, validações de construção.
- `test_magnata_os_classificacao_fonte_inventario_ponto_prestacao.py`
  (16 testes) — folha correta/ausente, colaborador errado, período
  errado, ciclo com fechamento 28 (29/05–28/06), duplicidade
  equivalente/conflitante, vínculo histórico presente/ausente,
  determinismo, AST (nenhum import
  de Airtable, nenhum cliente hardcoded).
- `test_inventario_ponto_composicao_e2e.py` (3 testes) — composição
  ponta-a-ponta + validação estrutural SKY.
- `test_airtable_ponto_prestacao.py` (7 testes) — mapeamento de schema,
  descarte de dado corrompido, disciplina read-only.
- Suíte geral: 2002 passed, 45 skipped (skips pré-existentes) — nenhuma
  regressão.

## Governança

- 15 gates de `scripts/ci/validate_governance.sh` aprovados localmente
  contra o intervalo exato `origin/main...HEAD`.
- `app.py` não foi tocado.
- Nenhuma escrita no Airtable; nenhuma dependência nova de Airtable no
  núcleo (`classificacao/`) — só no adapter opcional, substituível.
- Nenhuma ação de produção, migration, envio ou deploy.
