# Confirmação de Alocação Shadow — V1

Documento de decisão da missão "CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1".
Baseline: `main @ ce341906e193768ad5663719aa1ce0e46809ad3a` (PR #114
mergeado). Branch: `fix/confirmacao-alocacao-shadow-v1` (PR #116 —
reaproveitada de uma primeira rodada de implementação nesta mesma
branch; esta rodada a refina para o desenho completo abaixo, sem abrir
PR novo).

Autorização recebida (mensagem distinta da que descreveu o escopo),
com a regra pétrea explícita:

> Continuar usando o Airtable durante a transição, mas toda evolução
> nova deve reduzir — nunca aumentar — a dependência estrutural dele.
> Magnata OS = autoridade histórica de alocação; Airtable = fotografia
> operacional temporária; nenhuma nova verdade histórica deve nascer
> exclusivamente no Airtable; nenhuma dependência nova deve amarrar o
> domínio ao schema Airtable; qualquer leitura do Airtable deve passar
> por adapter substituível.

## FASE 0 — Preflight

- `main @ ce341906e193768ad5663719aa1ce0e46809ad3a` confirmado (`git
  rev-parse origin/main`).
- PR #114 mergeado — confirmado (`gh pr view 114` → `MERGED`).
- Worktree limpa antes de iniciar.
- `eventos.py`/`captura.py`/`resolucao.py` + adapters temporais
  (SQLite/Postgres) já existentes e reaproveitados integralmente,
  nenhum reimplementado.
- Mecanismo de transação/atomicidade (`repo.transacao()`, ambos os
  adapters) já existente e reaproveitado por `aplicar_transferencia`
  sem alteração.
- Fontes Airtable atuais de colaboradores/locais: `TABLE_FUNC`
  (`listar_funcionarios()`), `TABLE_LOCAIS`/`F_LOCAL_CLIENTE`,
  `F_FUNC_LOCAIS` — todos já confirmados por auditoria real de schema
  em missões anteriores, nenhum novo.

## FASE 1 — Arqueologia de entrada

Auditado antes de escrever qualquer código novo: as 38 rotas Flask de
`app.py` (`grep '@app.route'`), ausência de CLI/`argparse`/`click` em
`magnata_os/`, e todo uso de "Locais de trabalho" em `app.py` (8+
pontos). Achado, com evidência de código: "Locais de trabalho" é **só
lido** em `app.py` — nunca escrito por um formulário próprio. O próprio
código já documenta (`app.py:3524`): *"campo 'Locais de trabalho' [...]
não é preenchido automaticamente; requer associação manual"* — mesmo
achado já registrado na missão anterior desta série, agora confirmado
de novo, sem nenhuma superfície nova encontrada.

```text
PONTO_DE_ENTRADA_REUTILIZAVEL=Nenhum -- nenhuma rota Flask, nenhum comando CLI, nenhuma tela/formulario existente associa colaborador<->posto
FONTE_COLABORADOR=Airtable TABLE_FUNC, via listar_funcionarios() (ja existente, mesmo metodo ja usado por wiring.py)
FONTE_POSTO=Airtable TABLE_LOCAIS, via F_LOCAL_CLIENTE (ja confirmado por auditoria real de schema)
ADAPTER_AIRTABLE_REUTILIZAVEL=LeitorAirtableSomenteLeitura (airtable_leitura.py, so GET) -- reaproveitado integralmente, nenhum cliente HTTP novo
NOVO_COMPONENTE_REALMENTE_NECESSARIO=Sim -- confirmacao.py, comparacao_airtable.py e o adapter de identificacao/snapshot nao existiam; nenhuma superficie reaproveitavel foi encontrada para nenhum dos tres
APP_PY_PRECISA_SER_MODIFICADO=Nao para o mecanismo (servico/contrato/testes); so no futuro, se/quando uma UI final for construida -- decisao explicitamente adiada (FASE 10)
```

## FASE 2 — Contrato da confirmação

`SolicitacaoConfirmacaoAlocacao` (`magnata_os/documental/alocacao/
confirmacao.py`): `colaborador_id`, `posto_id`, `data_efetiva`, `acao`,
`origem_confirmacao`, `posto_destino_id` (só para `transferir`).
**Ambos os identificadores já chegam resolvidos** (nunca CPF/nome cru)
— resolver CPF → `colaborador_id` é responsabilidade de BORDA, de quem
monta a solicitação, nunca deste contrato (ver FASE 3).

`acao` tem 5 valores (`iniciar`, `encerrar`, `transferir`,
`adicionar_rateio`, `remover_rateio`) — nenhum evento novo criado para
eles: `iniciar`/`adicionar_rateio` traduzem para a MESMA primitiva já
existente (`captura.aplicar_alocacao_iniciada`, correta tanto para a
primeira alocação quanto para uma adicional sem fechar as demais);
`encerrar`/`remover_rateio` traduzem para `captura.
aplicar_alocacao_encerrada` (fecha só aquele posto). **Decisão
registrada:** os 2 pares de ações não têm validação de estado
diferenciada entre si (ex.: `iniciar` não exige que nenhum outro posto
esteja aberto) — a distinção existe para auditoria/intenção humana,
nunca para o schema; nenhuma coluna nova foi criada para persistir
qual `acao` foi usada (o registro resultante — aberto ou fechado — já
é a verdade persistida; "iniciar" vs "adicionar rateio" não muda o
formato do dado, só o rótulo de intenção no momento da confirmação).

## FASE 3 — Airtable somente como leitura transitória

Único ponto de leitura Airtable desta missão:
`ResolverIdentidadeAlocacaoAirtableShadow`
(`magnata_os/documental/importacao_lote/adapters/
airtable_resolver_identidade_alocacao.py`), com 3 responsabilidades
separadas, cada uma com seu próprio método:

1. **Resolução de borda** — `resolver_colaborador_id(cpf)`: CPF →
   `colaborador_id`, usada só por quem MONTA a solicitação, fora de
   `confirmacao.py`.
2. **Re-confirmação no momento da aplicação** —
   `confirmar_colaborador_existe`/`confirmar_posto_existe`: valida que
   um id já selecionado ainda existe no snapshot atual — é só isto que
   `aplicar_confirmacao_alocacao` de fato chama.
3. **Snapshot para comparação** — `postos_atuais_do_colaborador`
   (FASE 6, diagnóstico read-only).

Nenhuma escrita Airtable em nenhum método. `data_efetiva`/vigência
NUNCA vem do Airtable — só do humano confirmando (FASE 4). Todo o
subsistema (`confirmacao.py`, `comparacao_airtable.py`) só conhece o
`resolver`/`snapshot_airtable` injetado, duck-typed — zero import de
Airtable no domínio, exatamente como pedido ("contratos genéricos de
fonte... injetar o adapter Airtable na borda").

**Decisão registrada sobre identificação de posto:** `posto_id` é
sempre o record id do Airtable — nunca resolvido por nome livre. Um
Field ID de "Nome" para a tabela Locais não está confirmado em nenhum
documento nem código deste repositório; fabricar um sem prova real
seria uma dependência NOVA e não verificável do schema Airtable —
exatamente o que a regra pétrea desta missão proíbe. Resolver por id
já selecionado (nunca por busca textual) é, por si, uma escolha que
REDUZ superfície de acoplamento ao schema, não aumenta.

**Decisão registrada sobre "colaborador atual":** `confirmar_colaborador_
existe` não filtra por Status Airtable (Ativo/Inativo) — a garantia de
"não alocar quem já foi desligado" já vem inteiramente do PRÓPRIO
Magnata OS (`captura.aplicar_alocacao_iniciada` exige vínculo aberto;
um colaborador com `vinculo.data_desligamento` preenchido dispara
`EventoForaDeOrdemError`, nunca silenciosamente aceito). Depender do
campo de Status do Airtable para essa garantia seria uma dependência
estrutural NOVA do domínio ao schema Airtable — a regra pétrea desta
missão pede o oposto: a autoridade sobre "pode alocar ou não" já é,
deliberadamente, 100% do Magnata OS.

## FASE 4 — Confirmação humana obrigatória

`SolicitacaoConfirmacaoAlocacao.__post_init__` recusa `data_efetiva`
que não seja `datetime.date` real (nunca `None`, nunca string, nunca
inferida) — mesma disciplina de `eventos.py::_exigir_data`. Nenhum
caminho deste módulo produz uma data sozinho; um chamador sem data
confirmada por uma pessoa não consegue construir o objeto.

## FASE 5 — Shadow

`repo` é sempre injetado — `RepositorioAlocacaoSQLite` (testes locais)
ou `RepositorioAlocacaoPostgres` (job `postgres-real` efêmero de CI).
Nenhum Postgres de produção é assumido em nenhum ponto. Pipeline
completo, provado ponta a ponta por
`test_confirmacao_alimenta_leitura_historica_do_corredor`:

```text
confirmação humana → validação de identidade → evento canônico
→ captura temporal → persistência shadow → leitura histórica para conferência
```

O último passo (leitura histórica) reaproveita o contrato
`FonteUnidadePostoPrestacao` já implementado por
`RepositorioAlocacaoSQLite`/`Postgres` (`resolver_unidade_posto`) —
nunca reimplementado.

## FASE 6 — Comparação com Airtable

`magnata_os/documental/alocacao/comparacao_airtable.py` (novo, puro):
`EstadoComparacaoAirtable` (`CONSISTENTE`, `DIFERENTE`,
`MAGNATA_SEM_DADO`, `AIRTABLE_SEM_VINCULO`, `AMBIGUO`) +
`comparar_postos` (pura, 2 conjuntos → estado) +
`comparar_colaborador_shadow_com_airtable` (única função com I/O,
delega a `repo` shadow + `snapshot_airtable` injetado). **Diagnóstico
apenas — nunca reconciliação automática**: nenhuma escrita em nenhum
dos 2 lados em nenhum caminho desta função. Qualquer exceção do lado
Airtable (`ColaboradorAmbiguoError`, indisponibilidade de rede) vira
`AMBIGUO` — a função de diagnóstico nunca propaga uma falha do
Airtable como se fosse um erro do Magnata OS.

## FASE 7 — Semântica de ações

Todas as 5 ações validadas contra `RepositorioAlocacaoSQLite` (21+21
cenários, ver FASE 8) e replicadas contra Postgres real (FASE 9):
iniciar primeira alocação, transferir A→B atomicamente, rateio A+B
(2 postos abertos simultâneos, nenhum fecha o outro), remover só A
(rateio parcial), encerrar, repetir mesma confirmação (idempotência),
conflito com confirmação anterior, confirmação fora de ordem (iniciar
sem vínculo aberto, encerrar sem alocação prévia). Todas as regras já
aprovadas preservadas — nenhuma reimplementada, todas herdadas de
`captura.py`.

## FASE 8 — Testes adversariais

`test_magnata_os_documental_alocacao_confirmacao_shadow_v1.py` (42
testes) cobre os 16 cenários pedidos: 1 primeira alocação; 2 mesma
confirmação 2x; 3 transferência; 4 falha no meio da transferência
(resolver que quebra na 2ª chamada de identificação do destino); 5
retry após falha; 6 rateio; 7 remoção parcial; 8 data ausente; 9
colaborador inexistente; 10 posto inexistente; 11 snapshot Airtable
divergente (`DIFERENTE`); 12 Airtable sem vínculo
(`AIRTABLE_SEM_VINCULO`); 13 conflito temporal; 14 evento fora de
ordem (2 casos); 15 consulta histórica posterior (via
`resolver_unidade_posto`); 16 Airtable indisponível — domínio/captura
nunca corrompidos (propaga a falha, shadow permanece intocado;
`comparacao_airtable` nunca derruba, vira `AMBIGUO`).

## FASE 9 — Postgres real efêmero

Reaproveitado o MESMO job `postgres-real` já existente
(`.github/workflows/magnata-testes.yml`) — nenhum job novo.
`test_magnata_os_documental_alocacao_postgres_real.py` estendido (não
duplicado) com 7 testes novos: confirmação idempotente, rateio (2
postos abertos), transferência atômica, transferência com falha real
simulada + rollback real do Postgres + retry completo, conflito
temporal real, colaborador não identificado nunca escreve nada,
comparação Airtable consistente. Tudo sintético.

## FASE 10 — Não feito nesta missão (registrado, não escondido)

- `app.py` não foi tocado.
- Nenhum campo novo no Airtable, nenhuma escrita Airtable, nenhuma
  execução live contra Airtable real.
- Nenhum Postgres de produção provisionado/tocado, nenhuma migration
  em produção, nenhum deploy, Render, WhatsApp, Gmail.
- Nenhum dado real usado em nenhum teste.
- Nenhuma UI final — só o serviço/contrato/composição, chamável por
  qualquer front-end futuro.
- Nenhum backfill.

## FASE 11 — Duas revisões adversariais (autocorrigidas nesta rodada)

**Primeira (temporalidade/identidade/atomicidade/idempotência/
rateio/conflito/ausência de data):** encontrado e corrigido — faltava
cobertura explícita de "confirmação fora de ordem"
(`EventoForaDeOrdemError`) via a camada de confirmação (só existia via
`captura.py` diretamente); adicionados 2 testes (iniciar sem vínculo
aberto, encerrar sem alocação prévia).

**Segunda (independência do Airtable/acoplamento/duplicação/
persistência/produção/segurança/substituibilidade futura):** nenhum
import de Airtable em `confirmacao.py`/`comparacao_airtable.py`
confirmado; nenhum Field ID novo fabricado; nenhuma migration nova;
`posto_id`/`colaborador_id` tratados como identificadores opacos em
todo o subsistema (nenhum acoplamento ao formato de id do Airtable);
CPF nunca retornado/logado (mesma disciplina já estabelecida no
pacote). Nenhum problema técnico novo encontrado nesta segunda
passada — só a adição, já registrada acima, da FASE 5 fechando o
pipeline completo até a leitura histórica.

## FASE 12 — Testes/Governança

Suíte completa local: 1811 passed, 5 failed, 34 errors (mesma baseline
pré-existente de sandbox Windows, sem regressão nova). Governança
local: 15/15 gates. `git diff --check` limpo. Busca manual por padrão
de segredo no diff: nenhum encontrado.

## Resultado

Ver relatório estruturado na entrega do PR #116.
