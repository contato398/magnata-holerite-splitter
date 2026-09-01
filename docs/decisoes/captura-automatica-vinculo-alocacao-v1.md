# Captura Automática de Vínculo e Alocação — V1

Documento de decisão da missão "CAPTURA AUTOMÁTICA DE VÍNCULO E
ALOCAÇÃO V1". Contexto: PR #113 (validação real Postgres da entidade
`alocacao`) mergeado; o mecanismo de persistência temporal está
provado, mas vazio -- esta missão ataca a captura automática que
alimentaria essa memória a partir de agora. Branch:
`fix/captura-alocacao-vinculo-v1`.

## FASE 1 — Arqueologia do ponto de captura

Auditado, antes de criar qualquer mecanismo novo: `app.py`
(read-only), `src/sync_new_employees.py`, `src/services/secullum_ponto.py`,
`src/ingestao_secullum.py`. Achado central, com evidência de código:

**Vínculo (admissão/desligamento) tem data efetiva real e confiável —
mas a mutação em si é sempre gated por confirmação humana, por
desenho.**

- Admissão: `sync_new_employees.py` já extrai "Data de Admissão" real
  de holerites reais (regex sobre PDF) e já cria/completa o registro
  do Funcionário no Airtable com essa data. Fonte confiável e já
  testada em produção.
- Desligamento: `app.py::_processar_rescisao_stub` já extrai "Data da
  rescisão" real de TRCTs reais (mesma disciplina), mas **nunca altera
  o Status automaticamente** — o próprio código documenta o motivo:
  *"não existe campo 'Data de Desligamento' em Funcionários, e
  inativar alguém por engano tem custo alto — folha de pagamento,
  FGTS, benefícios"* — sempre cria uma Pendência para confirmação
  humana de 1 clique.

**Alocação (posto) não tem NENHUMA fonte de data efetiva hoje — achado
já confirmado, honestamente, pelo próprio código legado.**

`app.py::_montar_campos_pre_cadastro` (fluxo de Kit Admissão), ao
sugerir um Local/Posto extraído do documento de admissão, documenta
explicitamente: *"campo 'Locais de trabalho' é um vínculo para a
tabela Locais e não é preenchido automaticamente; requer associação
manual"* — nunca escrito automaticamente, nunca com data registrada.
Confirma, com evidência de código (não suposição), o mesmo achado já
registrado na missão de arqueologia do legado (turno anterior): não
existe, em lugar nenhum do sistema, um momento em que "colaborador X
foi alocado no posto Y" é registrado com uma data confiável.

```
EVENTO_REAL_JA_EXISTE=Parcial -- SIM para admissão/desligamento (data extraída de documento real), NÃO para alocação/posto
FONTE_MAIS_CONFIAVEL_DA_MUDANCA=Vínculo: Data de Admissão/Rescisão extraída de Holerite/TRCT reais (sync_new_employees.py / app.py). Alocação: nenhuma
DATA_EFETIVA_DISPONIVEL=Sim para vínculo; Não para alocação
IDENTIDADE_COLABORADOR_DISPONIVEL=Sim (CPF, já usado para casar registros em todo o legado)
IDENTIDADE_POSTO_DISPONIVEL=Parcial -- "Local/Posto sugerido" é só uma sugestão textual do documento, nunca associação confirmada/datada
MECANISMO_DE_WIRING_EXISTENTE=Para vínculo: dado de entrada já existe e é confiável, mas nunca escreve em vinculo_trabalhista hoje (falta wiring). Para alocação: não é wiring faltando -- é ausência genuína de dado
PRECISA_NOVO_ADAPTER=Não (RepositorioAlocacaoPostgres/SQLite já existem; só precisavam de operações de fechamento -- ver Fase 5)
PRECISA_NOVO_EVENTO=Sim -- vocabulário de evento canônico não existia (ver Fase 2)
```

## FASE 2 — Evento canônico

4 primitivas, nunca uma por cenário de negócio (`eventos.py`):
`VinculoIniciado`, `VinculoEncerrado`, `AlocacaoIniciada`,
`AlocacaoEncerrada`. Transferência = compõe Encerrada+Iniciada na mesma
data; rateio = 2× Iniciada sem fechar nenhuma; remoção parcial = 1×
Encerrada só daquele posto. `data_efetiva` é **obrigatória e validada
na construção** (`__post_init__`, nunca `None`, nunca string) — a
"regra central" da missão (*"mudança detectada ≠ data histórica
provada"*) é imposta estruturalmente: quem não tem uma data confiável
simplesmente não consegue construir um evento válido.

## FASE 3/4 — Semântica temporal e idempotência

`captura.py` implementa as 4 funções de aplicação
(`aplicar_vinculo_iniciado/encerrado`, `aplicar_alocacao_iniciada/encerrada`)
+ `aplicar_transferencia` (composição). Idempotência por **identificador
já existente** (colaborador_id + estado aberto/fechado + data), nunca
uma chave paralela nova. Reprocessar o mesmo evento nunca duplica nem
fecha 2×. Readmissão sempre cria vínculo novo (nunca reaproveita).
Conflito temporal e evento fora de ordem **sempre levantam exceção
explícita** (`ConflitoTemporalEventoError`/`EventoForaDeOrdemError`) —
nunca mascarados, nunca resolvidos silenciosamente por esta camada.

## FASE 5 — Persistência

`RepositorioAlocacaoPostgres`/`RepositorioAlocacaoSQLite` estendidos
com `vinculo_mais_recente_de`, `encerrar_vinculo`,
`alocacao_mais_recente_de`, `encerrar_alocacao` — **zero alteração de
schema/migration** (mesmas colunas já existentes, só novas queries
SELECT/UPDATE). Nenhum repositório novo criado.

## FASE 6 — Airtable / fonte atual

Confirmado (Fase 1): não é possível observar a mudança de "Locais de
trabalho" com data confiável hoje — o campo é editado manualmente, sem
timestamp de efetivação em lugar nenhum do schema Airtable auditado.

**Menor mecanismo seguro proposto para o futuro (não implementado
nesta missão):** o momento mais confiável para capturar a data efetiva
de uma alocação é o mesmo já usado para vínculo — o momento da
CONFIRMAÇÃO HUMANA (quando alguém de fato associa o Local em
"Locais de trabalho", ou confirma uma Pendência de admissão/mudança de
posto). Isso exigiria um campo novo no Airtable (ex.: "Alocação —
Data Efetiva", preenchido no mesmo clique que associa o Local) —
**mudança de schema Airtable, fora do escopo autorizado desta missão**,
proposta para decisão humana separada.

## FASE 7 — Integração (parada deliberada, não um mecanismo faltando)

`sync_new_employees.py` e `app.py` são os únicos pontos reais onde a
data de admissão/rescisão já é extraída de documento real. Ambos:

- **`app.py`**: protegido por `/CLAUDE.md` §7 — nunca tocado nesta
  missão, conforme regra explícita.
- **`src/sync_new_employees.py`**: não está na lista de arquivos
  protegidos por nome, mas é código de **produção real** (escreve
  Airtable de verdade quando executado) — a mesma cautela de "app.py"
  se aplica por analogia de risco, não por nome do arquivo. Wiring
  automático da captura de vínculo para dentro deste script criaria
  uma escrita real em Postgres a partir de um fluxo de produção sem
  gate humano no meio — decisão de integração, não de implementação.

**Decisão desta missão: construir e provar o MECANISMO por inteiro
(eventos.py + captura.py + extensão dos repositórios), nunca ligar a
chamada real dentro de `sync_new_employees.py`/`app.py`.** Isso não é
"faltou terminar" — é o mesmo padrão de parada já usado nas 2 missões
anteriores (schema/migration como gate humano; produção como gate
humano). Adicionalmente, **nem há Postgres de produção provisionado
ainda** — wiring real seria prematuro mesmo que os arquivos não fossem
tocados.

## Correção da revisão independente (PR #114) — atomicidade da transferência

A revisão humana do PR #114 encontrou um blocker técnico real: a
primeira versão de `aplicar_transferencia` chamava
`aplicar_alocacao_encerrada` (commit próprio) e depois
`aplicar_alocacao_iniciada` (outro commit próprio) — uma falha entre
os dois deixava estado parcial real: posto antigo fechado, posto novo
nunca aberto. Achado válido, corrigido.

**Correção:** `RepositorioAlocacaoPostgres`/`RepositorioAlocacaoSQLite`
ganharam um contexto transacional real, `repo.transacao()`
(`contextlib.contextmanager`) — reaproveita a MESMA conexão já
existente (nenhum repositório/motor/schema novo). Enquanto o contexto
está ativo (`self._em_transacao = True`), cada método de escrita
individual (`registrar_vinculo`, `encerrar_vinculo`,
`registrar_alocacao`, `encerrar_alocacao`) deixa de commitar/rollback
sozinho — o commit (sucesso) ou rollback (qualquer exceção) acontece
1 única vez, no fim do bloco `with`. Fora de uma `transacao()`, cada
escrita continua se autoconfirmando exatamente como antes (100% dos
testes pré-existentes, que chamam os métodos isoladamente, seguem
passando sem alteração).

`aplicar_transferencia` passou a envolver as 2 primitivas em
`with repo.transacao(): ...` — agora genuinamente tudo-ou-nada: uma
falha ao abrir o posto novo reverte TAMBÉM o fechamento do posto
antigo já feito na mesma chamada, nunca deixando estado parcial real
no banco. Idempotência preservada sem alteração — cada primitiva
continua checando o estado real antes de agir, então um retry completo
após uma falha funciona normalmente.

**Nenhum rollback compensatório** foi usado como substituto de
transação — ambos os adapters (Postgres real via `conexao.commit()`/
`rollback()`; SQLite via `sqlite3.Connection.commit()`/`rollback()`)
já suportavam transação real nativa; o `contextlib.contextmanager`
só organiza QUANDO cada um é chamado, nunca simula atomicidade por
cima de escritas já confirmadas.

6 testes novos (SQLite) + 2 testes novos (Postgres real, CI): falha
simulada (`unittest.mock.patch.object` no método de escrita, erro real
propagado através de uma conexão real) mantém o posto antigo aberto e
o novo inexistente; retry completo após a falha funciona; transferência
ainda idempotente quando chamada 2× com sucesso; transação aninhada
rejeitada explicitamente (`RuntimeError`); não-regressão explícita do
corredor histórico após a mudança.

```
TRANSFERENCIA_ATOMICA=True
POSTGRES_ATOMICIDADE_VALIDADA=True (transação real do driver psycopg 3, container efêmero de CI)
SQLITE_ATOMICIDADE_VALIDADA=True (transação real do módulo sqlite3)
FALHA_PARCIAL_TESTADA=True (falha simulada via mock no método de escrita, dentro de uma transação real)
RETRY_APOS_FALHA_VALIDADO=True
```

**Duas revisões adversariais da correção:**

*Primeira (a correção resolve exatamente o blocker, nada além):*
nenhuma regra de negócio nova; nenhum repositório/schema/motor novo;
os 4 métodos de escrita continuam com a MESMA assinatura pública,
comportamento idêntico fora de uma transação; `transacao()` é
estritamente aditiva (opt-in), nunca muda o caminho já usado por
`aplicar_vinculo_iniciado`/`encerrado`/`alocacao_iniciada`/`encerrada`
quando chamados isoladamente (fora de `aplicar_transferencia`).

*Segunda (nenhuma regressão introduzida):* suíte completa
re-executada -- 1772 passed (1766 antes + 6 novos SQLite), mesmos 5
failed/34 errors pré-existentes, zero regressão; job `postgres-real`
de CI validou os 2 novos testes contra Postgres de verdade (transação
real, não simulada); teste dedicado de não-regressão do corredor
histórico (sequência completa admissão->alocação->transferência,
resolução por competência) confirma que a mudança de atomicidade
nunca alterou nenhum resultado de LEITURA, só a segurança da escrita
composta.

## FASE 8/9 — Testes

25 testes novos: 21 em
`test_magnata_os_documental_alocacao_captura_v1.py` (os 15 cenários da
missão + variações, todos contra `RepositorioAlocacaoSQLite` real) + 4
em `test_magnata_os_documental_alocacao_postgres_real.py` (subconjunto
--admissão idempotente, transferência, readmissão, conflito -- contra
Postgres real em CI). Prova central da Fase 9 (via SQLite, e
estruturalmente idêntica em espírito ao que a suíte Postgres real já
teria provado): sequência admissão → alocação A → transferência B →
corredor real resolve A para competência anterior, B para posterior, e
os 2 legitimamente para a competência de transição — usando a memória
histórica via `fonte_unidade_posto_override`, nunca reescrevendo o
passado.

## FASE 11 — Duas revisões adversariais

**Primeira (temporalidade, idempotência, cardinalidade, rateio,
reentrada, ordem, conflito, ausência de data):** `data_efetiva`
impossível de omitir (validada na construção); reentrada sempre cria
vínculo novo, provado por teste; rateio nunca fecha o posto irmão,
provado; conflito e fora-de-ordem sempre levantam exceção, nunca
silenciosos; falha parcial reprocessada não duplica nem sobrescreve
(teste 14).

**Segunda (integração, duplicação de motor, dependência do Airtable,
regressões, segurança, produção, persistência, readiness):** nenhum
motor duplicado (reaproveita 100% do repositório já existente);
Airtable nunca consultado por `captura.py`/`eventos.py` (módulos
puros/persistência direta, zero acoplamento); suíte completa idêntica
ao baseline (1766 passed = 1745 anteriores + 21 novos, mesmos 5
failed/34 errors pré-existentes); zero produção tocada; zero escrita
Airtable; `app.py` intocado.

## Preservado

`app.py` intocado. `src/sync_new_employees.py` intocado (decisão
deliberada, Fase 7). Nenhuma migration/schema alterado. Zero produção.
Zero dado real (todos os testes usam colaborador/posto sintéticos).
Zero escrita externa.
