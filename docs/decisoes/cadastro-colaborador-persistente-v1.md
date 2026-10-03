# Decisão — Cadastro de Colaborador Persistente V1

**Branch:** `feat/cadastro-colaborador-persistente-v1`
**Data:** 2026-09-30
**Status:** Implementado, testado (unitário + Postgres real efêmero local). Migrations (0001-0003) PREPARADAS, NÃO APLICADAS em nenhum ambiente real. Correção pré-merge do PR #215 (cifra de CPF + histórico append-only real) concluída -- ver §3.1.

## 1. Objetivo

Quando um e-mail/Kit de Admissão com contrato de experiência cita um
colaborador novo, o operador quer que o Magnata OS já o cadastre num
registro PRÓPRIO (não Airtable, não Secullum). Se o documento trouxer
local de trabalho, o cadastro nasce completo; se não trouxer, fica
pendente até determinação humana — a mesma regra de negócio já
registrada em
`docs/decisoes/local-trabalho-determinacao-humana-admissao-v1.md`, não
reaberta aqui.

Objetivo secundário explícito na missão: prover a fonte REAL do
`diretorio_nomes` que
`magnata_os/orquestrador/interpretar_ordem_operador_v1.py` (PR #214,
ainda não mesclado em `main` no momento desta missão) já espera como
parâmetro opcional.

## 2. O que já existia e foi reaproveitado, não duplicado

| Peça | Onde | Reaproveitado como |
|---|---|---|
| `DadosColaboradorKitAdmissao` / `DeterminacaoLocalTrabalho` | `magnata_os/rh_admissao/gatilho_admissao.py` (INTOCADO) | entrada de `compor_colaborador_a_partir_do_kit` |
| Chave de idempotência por `colaborador_id` | `RegistroGatilhoAdmissaoEmMemoria` (mesmo arquivo) | mesma chave usada como PK de `rh_admissao_colaboradores` |
| `magnata_os.documental.modulo01.adapters.conexao` (`abrir_conexao`/`ConfiguracaoBancoAusente`) | `documental/modulo01/adapters/conexao.py` | reaproveitado pela CLI de determinação manual — mesma exceção deliberada já registrada em `magnata_os/documental/alocacao/fabrica_repositorio_alocacao.py` (reduzir a superfície de código que lê `DATABASE_URL`, em vez de duplicar essa lógica sensível a segredo em mais um lugar) |
| Padrão de adapter Postgres DB-API 2.0 (upsert, `ON CONFLICT`, `commit`/`rollback` explícitos) | `documental/modulo01/adapters/postgres_indice_documental_prestacao.py`, `documental/alocacao/adapters/postgres_*.py` | `RepositorioColaboradoresPostgres` |
| Formato `Mapping[colaborador_id, nome]` de `diretorio_nomes` | `interpretar_ordem_operador_v1.py` (branch `feat/interpretar-ordem-operador-v1`) | `montar_diretorio_nomes` produz exatamente esse formato |

## 3. O que foi construído

- **Domínio** (`magnata_os/rh_admissao/dominio_cadastro_colaborador.py`,
  puro — nenhum import de Flask/driver de banco/boto3/Airtable):
  `Colaborador`, `SituacaoCadastroColaborador`
  (`AGUARDANDO_LOCAL_TRABALHO` / `CADASTRO_COMPLETO`),
  `compor_colaborador_a_partir_do_kit`,
  `aplicar_determinacao_local_trabalho`, `EventoCorrecaoLocalTrabalho`,
  `LocalTrabalhoJaDefinidoError`.
- **Porta** (`magnata_os/rh_admissao/repositorio_colaboradores.py`):
  `RepositorioColaboradores` (Protocol) — `salvar`/`buscar_por_id`/`listar`.
- **Adapter Postgres real**
  (`magnata_os/rh_admissao/adapters/repositorio_colaboradores_postgres.py`):
  DB-API 2.0 duck-typed, upsert idempotente por `colaborador_id`.
- **Migrations**
  (`magnata_os/rh_admissao/migrations/0001_criar_tabela_colaboradores.sql`,
  `0002_cifrar_cpf_colaboradores.sql`,
  `0003_criar_historico_correcao_local_trabalho.sql` + rollbacks):
  tabela `rh_admissao_colaboradores` (CPF cifrado desde 0002) e
  `rh_admissao_historico_correcao_local_trabalho` (histórico
  append-only, 0003). **PREPARADAS, NÃO APLICADAS** — ver §5.
- **Wiring** (`magnata_os/rh_admissao/wiring_cadastro_colaborador.py`):
  `processar_kit_admissao_com_cadastro` /
  `processar_lote_kits_admissao_com_cadastro` — FUNÇÕES NOVAS que
  envolvem `processar_kit_admissao`/`processar_lote_kits_admissao`
  (INTOCADOS), nunca os alteram diretamente (`/CLAUDE.md` §8, "mudanças
  pequenas e isoladas"). `repositorio_colaboradores` é opcional e
  injetado.
- **Canal de determinação manual**
  (`scripts/determinar_local_trabalho_colaborador_cli.py`): CLI que
  recebe `colaborador_id` + local de trabalho, valida existência,
  aplica `aplicar_determinacao_local_trabalho` e persiste.
- **Diretório de nomes**
  (`magnata_os/rh_admissao/diretorio_nomes_colaboradores.py`):
  `montar_diretorio_nomes(repositorio) -> Dict[colaborador_id, nome]`.

## 3.1. Correção pré-merge do PR #215 (cifra de CPF + histórico append-only real)

O relato final do agente que construiu este PR declarou duas lacunas a
corrigir ANTES de qualquer merge/aplicação de migration -- §6 (versão
anterior deste documento) as listava como riscos declarados. Ambas
foram corrigidas nesta correção, na MESMA branch:

**CPF cifrado em repouso** (antes: texto puro, §6 anterior):
- `rh_admissao_colaboradores.cpf` (TEXT) foi substituído por
  `cpf_cifrado` (BYTEA) -- mesmo mecanismo Fernet (AES-128-CBC + HMAC
  autenticado, biblioteca `cryptography`) já aprovado e em produção
  local para telefone/WhatsApp
  (`documental/alocacao/contato_colaborador.py`/`configuracao_
  contato_colaborador.py`, migration 0004).
- Cifra/decifra acontece SÓ dentro de
  `adapters/repositorio_colaboradores_postgres.py` -- o domínio
  (`dominio_cadastro_colaborador.py`) continua sem saber que existe
  cifra, `Colaborador.cpf` continua um `str` em claro na memória do
  processo.
- Chave lida de `configuracao_cpf_colaborador.py`, variável de
  ambiente `MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE`, nunca hardcoded,
  nunca logada. Ausência da variável é FAIL-CLOSED
  (`SegredoCpfColaboradorAusente`) -- nenhuma escrita/leitura de `cpf`
  acontece sem cifra (testado explicitamente, mocado e contra Postgres
  real -- ver §5).
- **Decisão: SEM versionamento de chave** (diferente do padrão do
  telefone, que versiona para suportar rotação com backfill). O CPF
  cifrado aqui nunca é usado para deduplicação/comparação entre
  colaboradores -- `colaborador_id` já é a chave de idempotência --
  então não existe, hoje, um fluxo de bootstrap em lote que precise
  cifrar sob uma versão nova antes de promovê-la. Adicionar rotação de
  chave sem um caso de uso real seria complexidade não pedida por esta
  missão; decisão registrada, não uma omissão (ver
  `configuracao_cpf_colaborador.py`, docstring do módulo).
- **Decisão: migration NOVA (0002), não edição de 0001.** A missão
  original permitia editar `0001_criar_tabela_colaboradores.sql`
  diretamente (nunca aplicada em ambiente real) ou criar uma 0002. Esta
  correção escolheu uma migration NOVA
  (`0002_cifrar_cpf_colaboradores.sql`) porque o próprio repositório já
  tem uma regra explícita mais forte para o caso "migration commitada,
  mas nunca aplicada em produção" --
  `magnata_os/documental/modulo01/migrations/CLAUDE.md`: "nunca editar
  uma migration já aplicada... mesmo que ainda não tenha sido aplicada
  em nenhum ambiente real -- se já foi commitado, trate como
  aplicado". `0001` já estava commitada nesta branch antes desta
  correção; editá-la quebraria esse precedente por conveniência local.
  0002 é idempotente por instrução (`ADD COLUMN IF NOT EXISTS`, `DROP
  COLUMN` guardado por checagem em `information_schema.columns`) e não
  faz backfill de dado real (não existe nenhum -- 0001 nunca rodou fora
  de Postgres efêmero de teste).

**Histórico append-only real de correção de local de trabalho** (antes:
só log estruturado, §4/§6 anteriores):
- Nova tabela `rh_admissao_historico_correcao_local_trabalho`
  (`0003_criar_historico_correcao_local_trabalho.sql`), FK para
  `rh_admissao_colaboradores.colaborador_id`, uma linha por
  `EventoCorrecaoLocalTrabalho` (mesmos campos do domínio, sem cifra --
  local de trabalho/motivo não são CPF/nome).
- Append-only imposto A NÍVEL DE BANCO, não só disciplina de código:
  trigger que bloqueia `UPDATE`/`DELETE`, mesmo padrão exato de
  `eventos_documentais`/migration 0003 do Módulo 01 (reproduzido, não
  importado -- é SQL).
- `RepositorioColaboradores` (porta) ganhou dois métodos:
  `registrar_evento_correcao_local_trabalho` (só `INSERT`) e
  `listar_historico_correcao_local_trabalho` (só leitura, por
  `colaborador_id`, ordenada por `evento_id`).
- `scripts/determinar_local_trabalho_colaborador_cli.py` passou a
  chamar `registrar_evento_correcao_local_trabalho` sempre que há
  correção (depois de `salvar` persistir o `Colaborador` atualizado) --
  o log estruturado (`EVENTO_CADASTRO_COLABORADOR_LOCAL_TRABALHO_
  CORRIGIDO`) continua existindo, só deixou de ser a única fonte de
  verdade.
- **"Quem registrou":** `determinado_por` já era um campo OBRIGATÓRIO
  no domínio (`DeterminacaoLocalTrabalho`/`EventoCorrecaoLocalTrabalho`,
  validado como texto não vazio) -- reaproveitado como `NOT NULL` na
  tabela nova, não criado como campo novo opcional (o conceito de
  "quem" já existia). Continua sendo um identificador de texto livre
  (ex.: e-mail do operador) -- não existe, hoje, no Magnata OS, um
  conceito de usuário/operador autenticado mais forte (ex.: FK para
  uma tabela de operadores); essa é uma limitação já aceita pelo
  domínio antes desta correção, não uma omissão nova introduzida aqui.
- **Limitação declarada:** `salvar` (atualização do `Colaborador`) e
  `registrar_evento_correcao_local_trabalho` (gravação do histórico)
  são DUAS transações separadas no adapter atual -- não há uma
  transação única cobrindo as duas escritas. Uma falha entre as duas
  chamadas (ex.: Postgres cai depois de `salvar` e antes de
  `registrar_evento_correcao_local_trabalho`) deixaria o
  `local_trabalho` corrigido sem o evento correspondente no histórico.
  Não construído nesta correção (exigiria uma transação explícita
  compartilhada entre os dois métodos da porta, ou um método
  combinado) -- risco aceito conscientemente, registrado, não
  escondido; candidato a trabalho futuro se a disciplina de atomicidade
  entre as duas escritas se tornar um requisito real.

## 4. Critério de correção de local de trabalho já definido (item 6)

Mesmo princípio de "arquivo original é imutável" (`/CLAUDE.md` §4)
adaptado a cadastro: uma mudança de valor JÁ definido é um evento novo
registrado, nunca uma edição silenciosa. Critério exato adotado
(`aplicar_determinacao_local_trabalho`):

1. `local_trabalho` ainda `None` → determinação normal, completa o
   cadastro, sem evento.
2. `local_trabalho` já definido e o NOVO valor é IGUAL → idempotência
   (reprocessar o mesmo kit/comando não é correção); só `atualizado_em`
   avança, sem evento.
3. `local_trabalho` já definido e o NOVO valor é DIFERENTE, SEM
   `motivo_correcao` → RECUSADO (`LocalTrabalhoJaDefinidoError`),
   nenhuma escrita acontece.
4. `local_trabalho` já definido e o NOVO valor é DIFERENTE, COM
   `motivo_correcao` (texto não vazio) → aceito; produz um
   `EventoCorrecaoLocalTrabalho` (valor anterior, valor novo, motivo,
   autor, quando) registrado numa tabela append-only real
   (`rh_admissao_historico_correcao_local_trabalho`, migration 0003 --
   ver §3.1) E via log estruturado
   (`EVENTO_CADASTRO_COLABORADOR_LOCAL_TRABALHO_CORRIGIDO`, mantido
   como sinal operacional, não mais como única fonte de verdade).

O caminho AUTOMÁTICO do gatilho (`wiring_cadastro_colaborador.py`)
NUNCA passa `motivo_correcao` — um conflito encontrado ali (kit
reprocessado trazendo um local de trabalho diferente do já persistido)
é isolado e logado
(`EVENTO_WIRING_CADASTRO_COLABORADOR_CONFLITO`), NUNCA sobrescreve:
corrigir um local de trabalho já definido é sempre o canal manual
(CLI), nunca o caminho automático.

## 5. Migrations — PREPARADAS, NÃO APLICADAS (mesmo gate da J3)

`magnata_os/rh_admissao/migrations/0001_criar_tabela_colaboradores.sql`,
`0002_cifrar_cpf_colaboradores.sql` e
`0003_criar_historico_correcao_local_trabalho.sql` foram escritas,
testadas localmente contra um PostgreSQL 16 efêmero (cluster local
descartável desta sessão — nunca produção, nunca persistente) e
validadas pelos testes de `test_repositorio_colaboradores_postgres_real.py`
(13 testes após a correção do PR #215 -- cobrem também cifra de CPF e
histórico append-only, ver §3.1; que também rodam no job
`postgres-real` de `.github/workflows/magnata-testes.yml`, CI efêmero).
**Nenhuma delas foi ou será aplicada a nenhum Postgres real fora desse
efêmero de teste nesta missão.** Aplicar em produção exige autorização
humana específica (`/CLAUDE.md` §6/§8/§12-I — "autorização por fase",
nunca dispensada por §12), registrada em
`.magnata/migration-authorizations/`, exatamente como a J3
(`0011_criar_tabela_indice_documental_prestacao.sql`) ficou.

## 6. Riscos declarados (não escondidos)

Os dois riscos anteriormente listados aqui -- CPF em texto puro e
`EventoCorrecaoLocalTrabalho` não persistido -- foram corrigidos na
correção pré-merge do PR #215 (ver §3.1) e removidos desta lista.
Riscos que permanecem:

- **Sem interface de captura para o caminho automático.** Esta missão
  entrega a peça de domínio/wiring/persistência — não uma rota HTTP ou
  tela que dispare `processar_kit_admissao_com_cadastro` a partir de um
  Kit de Admissão chegando em produção. Mesma pendência já registrada
  em `docs/decisoes/local-trabalho-determinacao-humana-admissao-v1.md`
  §5.
- **Nenhum gatilho automático real roda em produção.** Assim como o
  gatilho de admissão em si, esta missão liga "Kit → Cadastro
  persistente" como capacidade testável, não como processo agendado.
- **`interpretar_ordem_operador_v1.py` não foi alterado** (fora de
  escopo, e ainda não mesclado em `main` no momento desta missão) — só
  a fonte real do `diretorio_nomes` que ele já sabe consumir foi
  provida.
- **Duas escritas não atômicas na correção manual** (ver §3.1): `salvar`
  do `Colaborador` e `registrar_evento_correcao_local_trabalho` são
  transações separadas -- risco novo, pequeno e registrado, introduzido
  pela própria correção do histórico append-only.

## 7. Gates que este documento não dispensa

Tudo que `/CLAUDE.md` §6, §7 e §12-I já listam continua valendo:
nenhuma aplicação real de migration, nenhum merge, nenhum push em
`main` fora desta branch, nenhuma autorização de fase concedida por
este documento. `app.py` e
`magnata_os/orquestrador/autorizacao_transporte_real.py` não foram
tocados.
