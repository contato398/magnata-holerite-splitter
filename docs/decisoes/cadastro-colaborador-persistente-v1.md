# Decisão — Cadastro de Colaborador Persistente V1

**Branch:** `feat/cadastro-colaborador-persistente-v1`
**Data:** 2026-09-30
**Status:** Implementado, testado (unitário + Postgres real efêmero local). Migration PREPARADA, NÃO APLICADA em nenhum ambiente real.

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
- **Migration**
  (`magnata_os/rh_admissao/migrations/0001_criar_tabela_colaboradores.sql`
  + rollback): tabela `rh_admissao_colaboradores`. **PREPARADA, NÃO
  APLICADA** — ver §5.
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
   autor, quando) registrado via log estruturado
   (`EVENTO_CADASTRO_COLABORADOR_LOCAL_TRABALHO_CORRIGIDO`).

O caminho AUTOMÁTICO do gatilho (`wiring_cadastro_colaborador.py`)
NUNCA passa `motivo_correcao` — um conflito encontrado ali (kit
reprocessado trazendo um local de trabalho diferente do já persistido)
é isolado e logado
(`EVENTO_WIRING_CADASTRO_COLABORADOR_CONFLITO`), NUNCA sobrescreve:
corrigir um local de trabalho já definido é sempre o canal manual
(CLI), nunca o caminho automático.

**Limitação declarada:** `EventoCorrecaoLocalTrabalho` hoje só é
registrado via log estruturado (mesmo padrão não-persistido de
`RegistroGatilhoAdmissaoEmMemoria`), não numa tabela de histórico
própria. Promover isso a um *event store* append-only real (no mesmo
espírito de `documentos`/`eventos_documentais` do Módulo 01) é trabalho
futuro, não decidido nem construído nesta missão — risco aceito
conscientemente para manter o escopo do pedido original.

## 5. Migration — PREPARADA, NÃO APLICADA (mesmo gate da J3)

`magnata_os/rh_admissao/migrations/0001_criar_tabela_colaboradores.sql`
foi escrita, testada localmente contra um PostgreSQL 16 efêmero
(cluster local descartável desta sessão — nunca produção, nunca
persistente) e validada pelos 4 testes de
`test_repositorio_colaboradores_postgres_real.py` (que também rodam no
job `postgres-real` de `.github/workflows/magnata-testes.yml`, CI
efêmero). **Ela NÃO foi e NÃO será aplicada a nenhum Postgres real
fora desse efêmero de teste nesta missão.** Aplicar em produção exige
autorização humana específica (`/CLAUDE.md` §6/§8/§12-I — "autorização
por fase", nunca dispensada por §12), registrada em
`.magnata/migration-authorizations/`, exatamente como a J3
(`0011_criar_tabela_indice_documental_prestacao.sql`) ficou.

## 6. Riscos declarados (não escondidos)

- **CPF em texto puro.** Diferente de `contato_colaborador_observado`
  (telefone cifrado com Fernet, `documental/alocacao/migrations/0004`),
  `rh_admissao_colaboradores.cpf` NÃO é cifrado nesta V1 — mesmo
  formato transitório já usado por `DadosColaboradorKitAdmissao`/
  `IntencaoCadastroSecullum` (que hoje só trafegam CPF em memória,
  nunca persistem). Persistir CPF em claro é um risco LGPD real;
  cifragem (mesmo padrão Fernet + HMAC já aprovado para telefone) é
  recomendação explícita para antes de qualquer aplicação real desta
  migration — decisão de produto/segurança que este documento não toma
  sozinho.
- **Sem interface de captura para o caminho automático.** Esta missão
  entrega a peça de domínio/wiring/persistência — não uma rota HTTP ou
  tela que dispare `processar_kit_admissao_com_cadastro` a partir de um
  Kit de Admissão chegando em produção. Mesma pendência já registrada
  em `docs/decisoes/local-trabalho-determinacao-humana-admissao-v1.md`
  §5.
- **`EventoCorrecaoLocalTrabalho` não é persistido** (ver §4) — só
  logado.
- **Nenhum gatilho automático real roda em produção.** Assim como o
  gatilho de admissão em si, esta missão liga "Kit → Cadastro
  persistente" como capacidade testável, não como processo agendado.
- **`interpretar_ordem_operador_v1.py` não foi alterado** (fora de
  escopo, e ainda não mesclado em `main` no momento desta missão) — só
  a fonte real do `diretorio_nomes` que ele já sabe consumir foi
  provida.

## 7. Gates que este documento não dispensa

Tudo que `/CLAUDE.md` §6, §7 e §12-I já listam continua valendo:
nenhuma aplicação real de migration, nenhum merge, nenhum push em
`main` fora desta branch, nenhuma autorização de fase concedida por
este documento. `app.py` e
`magnata_os/orquestrador/autorizacao_transporte_real.py` não foram
tocados.
