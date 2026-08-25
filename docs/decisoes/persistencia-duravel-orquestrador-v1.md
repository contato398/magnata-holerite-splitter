# Persistencia duravel V1 do Grande Orquestrador

**Data:** 2026-08-25

**Base:** `main@52acf68d33c177e940ef7c1f8d6bdf2804919ed0` (PR #60)

**Estado:** capacidade inerte em codigo; nenhum banco provisionado, migration
aplicada, secret criado, workflow ativado ou deploy realizado.

## 1. Decisao

O backend duravel implementa a interface existente `RepositorioExecucoes`.
Motor, health, DLQ, autorrecuperacao e supervisor continuam dependendo do
mesmo contrato e nao conhecem PostgreSQL, Render ou qualquer fornecedor.

O adapter recebe uma conexao DB-API pronta. Ele nunca:

- le variavel de ambiente ou secret;
- abre conexao por conta propria;
- aplica migration;
- cai silenciosamente para SQLite;
- ativa o supervisor `ACTIVE`;
- acessa um sistema externo durante import ou teste.

## 2. Organograma final

O repositorio e infraestrutura compartilhada do Grande Orquestrador, nao de
um setor especifico. Futuros gerentes virtuais, agentes, checkers e agentes
adversariais publicam e observam eventos pelo mesmo nucleo. Nenhum deles ganha
banco, memoria ou fila paralela.

O contrato de snapshot do supervisor recebe versao explicita
`magnata_os.orquestrador.supervisor.v1`. Isso permite que painel e agentes de
checagem evoluam sem interpretar formatos informais de log.

## 3. Garantias

- `event_id` continua sendo a chave de idempotencia;
- claim inicial usa `ON CONFLICT DO NOTHING`;
- retry usa compare-and-swap `FAILED_RETRYABLE -> EXECUTING`;
- claim do retry e auditoria pertencem a uma unica instrucao/transacao;
- toda escrita faz rollback em falha;
- auditoria de transicoes e de recovery e append-only por trigger;
- schema `magnata_orquestrador` evita colisao com dominios operacionais;
- configuracao ambigua ou incompleta falha explicitamente.

## 4. Perimetro preservado

Esta fase nao modifica nem conecta:

- esteira documental e suas migrations;
- captura Gmail/Apps Script e remetentes DP/Fiscal;
- Secullum/PontoWeb;
- WhatsApp/Evolution;
- Airtable;
- Render;
- `app.py`, frontend ou assets;
- GRAPHIFY.

Esses componentes continuam sendo fontes, adapters e dominios coordenados por
eventos. O adapter Postgres do Orquestrador nao absorve regras de negocio
deles.

## 5. Gates ainda obrigatorios

Exigem decisao humana separada:

1. escolher e contratar/provisionar o Postgres;
2. criar e armazenar secret de conexao;
3. revisar e aplicar a migration;
4. definir backup, restauracao, retencao e monitoramento;
5. conectar um ambiente shadow ao backend;
6. comparar SQLite e Postgres com eventos sinteticos;
7. autorizar qualquer deploy;
8. autorizar supervisor `ACTIVE` por tipo de evento.

O arquivo de rollback existe para revisao e contingencia, mas e destrutivo e
nunca pode ser executado automaticamente.
