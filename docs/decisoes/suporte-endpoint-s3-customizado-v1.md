# Decisão — Suporte a endpoint S3 customizado (Cloudflare R2 e equivalentes) V1

**Branch:** `fix/s3-endpoint-customizado-r2-v1`
**Data:** 2026-10-01
**Status:** Implementado e testado (mock/spy em `boto3.client`, zero
rede real, zero credencial real).

## 1. Objetivo

Permitir que `_compor_armazenamento_a_partir_do_ambiente()` (em
`magnata_os/orquestrador/ciclo_producao_v1.py`) componha o cliente S3
contra **qualquer provedor compatível com a API S3** — em particular
Cloudflare R2, que o usuário (dono do produto) decidiu adotar como
provedor real por ter egress sempre gratuito — sem acoplar o código a
esse provedor específico e sem quebrar quem já depende do
comportamento atual (AWS S3 real).

O adapter `ArmazenamentoArquivosS3`
(`magnata_os/documental/modulo01/adapters/s3_armazenamento.py`) já era
duck-typed contra qualquer cliente compatível com S3 — isso já estava
documentado no próprio docstring do módulo antes desta mudança. O que
faltava era a função que **compõe** esse cliente a partir do ambiente:
ela só sabia criar `boto3.client('s3')` puro, sem `endpoint_url`, o
que a AWS real não exige mas R2 exige.

## 2. O que mudou

Duas variáveis de ambiente novas, ambas opcionais:

- `ORQUESTRADOR_S3_ENDPOINT_URL`: se presente, passada como
  `endpoint_url=` para `boto3.client('s3', ...)`.
- `ORQUESTRADOR_S3_REGION`: se presente, passada como `region_name=`.
  Se ausente mas `ORQUESTRADOR_S3_ENDPOINT_URL` estiver presente,
  default `'us-east-1'` — a mesma região que a AWS já assume
  implicitamente hoje quando nenhuma é informada, para não introduzir
  um comportamento de região diferente do atual.

`ORQUESTRADOR_S3_BUCKET` continua obrigatório e fail-closed, sem
nenhuma mudança nesse ponto.

**Isto não é uma dependência de provedor nova.**
`boto3.client('s3', endpoint_url=..., region_name=...)` já aceita
esses dois parâmetros desde sempre — a mudança só torna explícito, via
variável de ambiente, o que a biblioteca já suportava. O adapter
`ArmazenamentoArquivosS3` não foi tocado: continua duck-typed, não sabe
e não precisa saber quem é o provedor por trás do cliente injetado.

Credenciais (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, ou as
equivalentes de um provedor compatível, ex. as chaves de acesso S3 do
R2) continuam vindo do jeito padrão que o próprio `boto3` já lê do
ambiente sozinho — nenhuma leitura ou reimplementação de credencial foi
adicionada.

## 3. Retrocompatibilidade (obrigatória, garantida)

Se `ORQUESTRADOR_S3_ENDPOINT_URL` estiver ausente, o comportamento é
**exatamente** o de antes desta mudança: `boto3.client('s3')`, sem
`endpoint_url` nem `region_name` — AWS S3 real, sem alteração.

Evidência de teste (`test_ciclo_producao_v1.py`):

- `test_compor_armazenamento_sem_endpoint_customizado_e_identico_a_antes`
  — com mock em `boto3.client`, confirma a chamada exata
  `boto3.client('s3')`, sem nenhum argumento extra, quando
  `ORQUESTRADOR_S3_ENDPOINT_URL` está ausente.
- `test_compor_armazenamento_com_endpoint_customizado_usa_region_default`
  — com `ORQUESTRADOR_S3_ENDPOINT_URL` presente e
  `ORQUESTRADOR_S3_REGION` ausente, confirma
  `boto3.client('s3', endpoint_url=..., region_name='us-east-1')`.
- `test_compor_armazenamento_com_endpoint_customizado_usa_region_configurada`
  — com as duas variáveis presentes, confirma que o valor configurado
  de região é o que é passado.
- `test_compor_armazenamento_a_partir_do_ambiente_falha_sem_bucket`
  (já existia) — continua passando sem alteração: `ORQUESTRADOR_S3_BUCKET`
  ausente continua `RuntimeError` fail-closed.

Suíte completa (`python -m pytest -q`) executada sem nenhuma
regressão.

## 4. Outros pontos de composição de cliente S3 no repositório

Busca por `boto3.client('s3'` em todo o repositório encontrou um único
ponto de composição real: `_compor_armazenamento_a_partir_do_ambiente()`
em `ciclo_producao_v1.py`. Os demais módulos que usam armazenamento
(`executar_canario_v1.py`, `composicao_prestacao_real_v1.py`,
`distribuir_documento_v1.py`) importam e delegam para essa mesma
função — nenhum deles instancia `boto3.client('s3', ...)` por conta
própria. Não há, portanto, nenhum outro local a estender.

## 5. Escopo e limites

- Nenhuma credencial real foi configurada ou usada nesta missão.
- Nenhuma chamada de rede real foi feita — todos os testes usam
  mock/spy em `boto3.client`.
- `app.py` não foi tocado.
- Nenhum provisionamento de infraestrutura real (bucket R2 real,
  credencial R2 real) foi feito — isso fica para quando o usuário
  (dono do produto) decidir configurar `ORQUESTRADOR_S3_ENDPOINT_URL` e
  as credenciais no seu próprio ambiente de produção, fora desta
  sessão.

## 6. Risco remanescente

Nenhum risco novo identificado: a mudança é puramente aditiva (duas
variáveis opcionais, comportamento default idêntico ao anterior) e não
altera nenhum caminho já exercitado pelos testes existentes do ciclo de
produção.
