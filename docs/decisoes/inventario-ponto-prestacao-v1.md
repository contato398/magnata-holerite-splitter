# Fonte de inventário de Folha/Cartão de Ponto — REVERTIDA após gate semântico (v1)

**Data:** 2026-09-03
**Branch:** `fix/inventario-ponto-prestacao-v1`
**Base:** `main @ 91f0eb974a76e07122a147f1b173eb7baa21ec96` (PR #124 mesclado)
**Status:** ❌ **Implementação original REVERTIDA nesta mesma branch/PR**, após revisão
independente identificar um erro semântico de fundo. Este documento
registra a tentativa original, o erro encontrado, a auditoria completa
da segunda revisão e a conclusão final — nada foi apagado da história,
só corrigido por escrito.

## Tentativa original (revertida)

A primeira versão desta missão implementou `FonteInventarioPontoPrestacao`
sobre os registros DIÁRIOS já espelhados do Secullum
(`AT_PONTO = 'tblmgV10s3dZiP8av'`, confirmado em `src/ingestao_secullum.py`):
presença de ≥1 dia com batida dentro da janela do ciclo (mês civil ou
override por dia de fechamento) era tratada como "Folha de Ponto
presente" para efeito de completude do pacote.

## Erro identificado (revisão independente)

Isso confunde dois conceitos genuinamente distintos:

- **(A) dados brutos de ponto existem** — o Secullum registrou batidas
  daquele colaborador naquele dia;
- **(B) o DOCUMENTO Folha/Cartão de Ponto existe** — o artefato que
  efetivamente compõe o pacote entregável da prestação de contas.

Para completude documental, **B é o requisito relevante — nunca A**.
Um cliente com batidas do Secullum mas sem o cartão de ponto realmente
gerado/entregue apareceria, com a implementação original, como
"Folha de Ponto: PRONTO" — um falso positivo de completude,
exatamente o risco que este gate semântico existe para prevenir.

## Auditoria da segunda revisão — o que existe de verdade

| Peça | Onde | O que realmente é |
|---|---|---|
| `AT_PONTO`/`tblmgV10s3dZiP8av` (Secullum) | `src/ingestao_secullum.py` | Registros DIÁRIOS de batida — DADO BRUTO, nunca documento. Confirmado: sem campo de competência, 1 linha por dia. |
| `PDF Folha Ponto` (campo `F_FUNC_PDF_FOLHA` = `fldgBhXpEFmy20yxd`, tabela `Funcionários`) | `app.py` linhas 119, 3813, 3869, 4933, 6132, 6221, 6826, 8699 | **O documento REAL** — anexo de PDF no prontuário do Funcionário, já usado em produção como evidência de "Cartão de Ponto entregue" (`motivos.append('pdf_folha_ponto_ausente')`). Mesmo papel documental que o Holerite. |
| Granularidade de competência do campo acima | `app.py::_classificar_folha_ponto_distribuicao`, docstring literal | **Confirmado, por escrito no próprio legado**: "não há 1 registro por mês como em Holerites" — o campo é uma lista de anexos que só CRESCE; `anexos[-1]` (último) é usado sem checagem de a qual mês pertence. **Não existe hoje nenhuma forma confiável de saber, a partir deste campo, se o anexo mais recente é da competência pedida.** |
| `extrair_cartao_ponto` (extrai "Período: dd/mm/aaaa até dd/mm/aaaa" do TEXTO do PDF real) | `app.py` linha 768 | Existe, extrai período real do documento — mas está **explicitamente marcado "ainda NÃO usado em produção"** e "precisa ser revisada... antes de ser usada em `_processar_folha_ponto`". Não está ligado a nenhum lugar que persista esse período por anexo. |
| Corredor documental genérico (`ResultadoResolucaoSemantico -> ItemInventarioPrestacao`) | `magnata_os/classificacao/adaptador_inventario_prestacao.py` | Já pronto e genérico — se um PDF de Folha de Ponto for ingerido pelo pipeline moderno de classificação/resolução (o mesmo usado por Holerite/Extrato quando chegam por e-mail), a COMPETÊNCIA já resolvida do documento produz um `ItemInventarioPrestacao` correto, sem nenhum código novo. O gap real não está aqui. |

## Conclusão

**Não existe hoje, em nenhum lugar do código (novo ou legado), uma
fonte de "documento Folha de Ponto real, com competência confiável"
pronta para reaproveitar.** Fechar esse gap de verdade exigiria uma de
duas coisas, nenhuma no escopo desta missão:

1. alterar `app.py` (legado protegido, CLAUDE.md §7) para persistir a
   competência de cada anexo de `PDF Folha Ponto` (ex.: ativar
   `extrair_cartao_ponto` e gravar o período junto do anexo) — decisão
   de produto/arquitetura que precisa de autorização humana explícita
   e uma branch própria, por ser alteração de legado protegido; **ou**
2. confirmar que documentos de Folha de Ponto para fins de prestação
   sempre chegam pelo corredor documental moderno (e-mail → classificação
   → resolução) — caso em que **nenhum código novo é necessário**: o
   adaptador genérico já existente resolve isso, e o gap nomeado no ADR
   anterior (`inventario-real-prestacao-v1.md`) seria, na prática, falso
   (só faltava confirmar, não construir).

Por isso a implementação original desta missão foi **revertida por
completo** (arquivos removidos nesta mesma branch, listados abaixo) —
construir sobre dado bruto do Secullum seria consertar o sintoma errado,
e construir sobre o campo `PDF Folha Ponto` sem competência confiável
seria inventar uma relação que a regra pétrea #8 proíbe explicitamente
("em caso de falta de informação, retornar INDETERMINADO, nunca
inventar relacionamento").

### Arquivos removidos nesta reversão

- `magnata_os/classificacao/ciclo_ponto_prestacao.py`
- `magnata_os/classificacao/fonte_inventario_ponto_prestacao.py`
- `magnata_os/documental/importacao_lote/adapters/airtable_ponto_prestacao.py`
- `test_magnata_os_classificacao_ciclo_ponto_prestacao.py`
- `test_magnata_os_classificacao_fonte_inventario_ponto_prestacao.py`
- `test_inventario_ponto_composicao_e2e.py`
- `test_airtable_ponto_prestacao.py`

### Cardinalidade (Holerite-like) — não avaliada

Como nenhuma fonte de documento real foi entregue, a pergunta "Folha de
Ponto deve exigir 1 documento por colaborador esperado, como Holerite"
fica **sem objeto nesta missão** — só faz sentido decidir isso depois
que existir uma fonte real de documento com competência confiável. Se/
quando essa fonte existir, o mecanismo já pronto de
`holerite_obrigatorio_prestacao.py`/`combinar_pacote_com_holerite`
deve ser reaproveitado (mesmo padrão, nunca um segundo motor de
obrigatoriedade).

## Governança

- Nenhuma alteração em `app.py` — só leitura/auditoria para confirmar
  os IDs de tabela/campo já em uso (§7 do `CLAUDE.md` respeitado: leitura
  do legado é permitida, escrita não).
- Nenhuma dependência nova de Airtable (a reversão remove a única que
  havia sido introduzida).
- 15 gates de `scripts/ci/validate_governance.sh` aprovados localmente
  contra o intervalo exato `origin/main...HEAD`.
- Suíte geral sem regressão — apenas os testes desta funcionalidade
  revertida deixam de existir; nada mais foi tocado.

## Próximo passo recomendado (decisão humana, fora desta missão)

Confirmar qual dos dois caminhos da seção "Conclusão" é o real antes de
qualquer nova tentativa de fechar este gap:
(1) autorizar uma missão específica, com branch própria, para persistir
competência por anexo de `PDF Folha Ponto` em `app.py` (legado protegido);
ou (2) confirmar que Folha de Ponto sempre entra pelo corredor moderno,
caso em que o gap está fechado por definição e nenhuma nova fonte é
necessária.
