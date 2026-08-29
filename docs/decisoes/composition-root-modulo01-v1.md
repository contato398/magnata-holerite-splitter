# Composition root V1 do Módulo 01 — implementação concluída

**Data:** 2026-08-29
**Branch:** `feat/composition-root-modulo01-v1`
**Status:** ✅ Implementado, testado, pronto para revisão

## Resumo executivo

Antes desta mudança, o Módulo 01 (Documental) era **intencionalmente inerte**:
`ServicoCriacaoLote`, `AdapterCapturaEmail` e `LeitorAirtableSomenteLeitura` real
só eram instanciados em testes; nenhum processo de produção os montava (ver
auditoria prévia — `render.yaml`/`Procfile` só rodam `gunicorn app:app` e o
worker Celery, nenhum dos dois importa `magnata_os`).

Este trabalho cria o **primeiro composition root oficial** do módulo —
`magnata_os/documental/modulo01/composicao.py::construir_pipeline_modulo01` —
que monta explicitamente:

```
FonteMensagensEmail
  -> AdapterCapturaEmail
  -> ServicoCriacaoLote
  -> ServicoEntradaDocumental / ServicoAvancoEsteira
  -> repositórios (Documentos, Histórico, Lotes, Estados da Esteira)
  -> FonteCandidatosFuncionario (opcional)
```

a partir de dependências **já construídas**, recebidas por injeção — nunca
decide backend, nunca lê variável de ambiente, nunca abre conexão/rede.

## O que isto NÃO faz (por desenho, não por esquecimento)

- **Não ativa produção externa.** Construir o pipeline nunca chama
  `capturar_novas_mensagens()` sozinho, nunca abre Gmail real, nunca consulta
  Airtable real.
- **Não lê nenhuma variável de ambiente** (`DATABASE_URL`, `AIRTABLE_API_KEY`,
  credencial Gmail) — isso continua sendo responsabilidade de um bootstrap
  externo separado, ainda não construído.
- **Não altera** `app.py`, `render.yaml`, `Procfile`, `celery_app.py`,
  `tarefas_processar_pdf.py` — o legado continua produzindo exatamente como
  antes (strangler pattern preservado).
- **Não cria implementação Postgres nova** para `RepositorioLotes`/
  `RepositorioEstadosEsteira` (Fase 3) — hoje só existe versão em memória para
  esses dois; uma implementação Postgres real é trabalho futuro, fora desta
  missão (nenhuma migration/schema foi criada aqui).
- **Não cria nenhum segredo, credencial ou variável de ambiente nova.**

## Auditoria que motivou o design

- `ServicoCriacaoLote`/`AdapterCapturaEmail`: só instanciados em testes antes
  desta mudança.
- `LeitorAirtableSomenteLeitura` real: só instanciado em
  `scripts/prestacao_readiness_shadow_real.py` (fluxo de readiness da
  Prestação de Contas, não relacionado à esteira de ingestão) — já satisfaz
  `FonteCandidatosFuncionario` por duck typing, sem adapter novo.
- `ClienteGmailReadOnly` (Gmail real) constrói o recurso Gmail dentro do
  próprio `__init__` (`construir_recurso(credenciais)`) — por isso o
  composition root nunca a instancia; quem tiver credencial autorizada monta
  `ClienteGmailReadOnly` primeiro e passa a instância pronta como
  `fonte_mensagens`.
- `magnata_os/orquestrador/fabrica_repositorio_execucoes.py` já estabelece o
  padrão de composição explícita reutilizado aqui: sem fallback silencioso,
  exige dependências já autenticadas/construídas, nunca decide backend
  sozinha.
- `AIRTABLE_API_KEY`/`DATABASE_URL` continuam as variáveis canônicas
  conhecidas para um bootstrap futuro (confirmadas em `app.py` e
  `scripts/prestacao_readiness_shadow_real.py`/`adapters/conexao.py`) — nada
  disso é lido por este composition root.

## Testes (6 novos, adicionados a `test_magnata_os_documental_modulo01_email_captura.py`)

Os 10 testes já existentes desse arquivo foram adaptados para montar o
adapter via `construir_pipeline_modulo01` em vez de montagem manual —
passam a validar o composition root automaticamente, sem duplicação.

Testes novos, provando cada garantia pedida:

1. `test_importar_o_modulo_de_composicao_nao_exige_nenhuma_credencial` —
   importa `composicao.py` sem `DATABASE_URL`/`AIRTABLE_API_KEY` no ambiente.
2. `test_adapter_capturado_e_servico_lote_sao_o_mesmo_objeto` — o
   `AdapterCapturaEmail` devolvido usa exatamente a mesma instância de
   `ServicoCriacaoLote` exposta em `PipelineModulo01`.
3. `test_fonte_candidatos_funcionario_chega_ao_servico_lote` — a fonte
   injetada no composition root é a mesma que chega a `ServicoCriacaoLote`.
4. `test_sem_fonte_candidatos_o_default_seguro_none_e_preservado` — sem
   fonte, o comportamento off-by-default já existente continua intacto.
5. `test_holerite_elegivel_alcanca_identificacao_via_pipeline_completo` —
   ponta a ponta (fakes na fronteira): Holerite avulso RESOLVIDO recebido
   via `FonteMensagensEmail` fake atravessa todo o pipeline e chega a
   `IDENTIFICACAO/CONCLUIDO`; fonte de candidatos lida no máximo 1 vez.
6. `test_nenhum_acesso_externo_durante_construcao_ou_captura` — prova
   estática (AST) de que `composicao.py` nunca importa `requests`,
   `psycopg`/`psycopg2`, `googleapiclient`/`google` ou `boto3`.

## Próxima ação: bootstrap operacional (bloqueado até autorização)

Para ativar isto de verdade em produção, uma missão futura e separada
precisaria (nenhuma parte disto foi feita aqui):

1. **Autorização de fase explícita**, cumprindo `CLAUDE.md` §6(a)-(f) —
   Gmail real e Airtable real são ações externas de produção.
2. Um script/entrypoint novo (ex.: `scripts/executar_captura_email_shadow.py`,
   mesmo padrão de `scripts/prestacao_readiness_shadow_real.py`) que:
   - lê `AIRTABLE_API_KEY`/`DATABASE_URL`/credencial Gmail do ambiente;
   - constrói `LeitorAirtableSomenteLeitura(api_key)`,
     `ClienteGmailReadOnly(label, credenciais)`, e os repositórios Postgres
     reais (Documentos/Histórico já têm implementação; Lotes/Estados da
     Esteira ainda precisariam de uma — gate de migration/schema separado);
   - chama `construir_pipeline_modulo01(...)` com tudo isso já pronto;
   - é disparado por um agendador/cron externo (decisão de operação, fora
     de código).
3. Confirmação humana distinta da que aprovar este PR (`CLAUDE.md` §6-e).

Até lá, o Módulo 01 continua **100% inerte** em produção. Nenhum teste,
nenhum processo de produção, nenhuma integração contínua toca Gmail ou
Airtable de verdade.

## Documentação relacionada

- `docs/decisoes/fase1-gmail-readonly-inerte.md` — mesmo padrão de inércia
  deliberada, aplicado ao cliente Gmail.
- `docs/decisoes/plano-consolidacao-ingestao-distribuicao.md` — plano geral
  de consolidação de ingestão.
- `magnata_os/orquestrador/fabrica_repositorio_execucoes.py` — padrão de
  composição explícita reutilizado aqui.
- `CLAUDE.md` §6 — autorização de fase para escrita/ativação externa.
