# Comando manual — Outros Documentos → Envio

Integração manual e controlada de `_dry_run_outros_documentos_para_envios` e
`_aplicar_outros_documentos_no_envio` (Fix v3.01, `app.py`). Sem rota HTTP,
sem job, sem cron — execução manual apenas, por quem tem acesso ao ambiente
onde `AIRTABLE_API_KEY`/`BASE_ID` já estão configurados (ex.: shell do
Render).

## Uso

```bash
python -m scripts.outros_documentos_cli dry-run --competencia "Junho 2026"
python -m scripts.outros_documentos_cli aplicar  --competencia "Junho 2026" --envio-id recXXXXXXXXXXXXXX
```

- **`dry-run`**: só leitura. Lista os `envio_id`s afetados, quantidade de
  anexos atuais e novos, duplicidades evitadas, conflitos e registros
  rejeitados (sem PDF ou sem Envio vinculado). Nunca escreve.
- **`aplicar`**: escreve em **um único `envio_id` por chamada** (sem modo
  lote). Refaz o dry-run internamente antes de agir — nunca confia num
  relatório anterior. Se houver conflito (mesmo nome, tamanho diferente)
  para esse `envio_id`, interrompe sem escrever e sem oferecer override.
  Se não houver novidade após deduplicação, encerra sem `PATCH`. Só escreve
  depois que o operador digitar exatamente `CONFIRMAR` no prompt.

## Pré-requisito de segurança: validação do campo `Arquivos`

Antes de qualquer aplicação, o comando confirma — por leitura via Meta API,
nunca por escrita — que o campo `Arquivos` de `Envios de Documentos`
corresponde ao Field ID `F_ENVIO_ARQUIVOS`. Esse campo também é usado hoje
por Cartão Ponto; a equivalência nome↔Field ID nunca é assumida em
silêncio. Se a confirmação falhar por qualquer motivo (rede, schema
mudou, campo não encontrado), o comando aborta e imprime
`CAMPO_ARQUIVOS_NAO_CONFIRMADO` — nenhuma escrita ocorre.

## Rollback

Não há desfazer automático. Antes de cada `PATCH`, o comando registra em
log (evento `pre_patch`, com o `correlation_id` da execução) os
`attachment_id`s que já estavam no campo `Arquivos` do Envio. Para
reverter, um humano com acesso ao Airtable deve restaurar manualmente esse
campo para essa lista, localizando a linha pelo `correlation_id`.

## O que este comando não faz

Não cria rota, não abre porta HTTP, não agenda execução (job/cron), não
aplica em lote, não remove os anexos duplicados já existentes em produção
(caso conhecido da Unimed Itapetininga, fora de escopo desta integração),
não lê `.env.txt` — usa só `AIRTABLE_API_KEY`/`BASE_ID` já carregados pelo
próprio `app.py` via variável de ambiente.

## Testes

```bash
pytest test_dedup_outros_documentos.py -v
pytest test_outros_documentos_cli.py -v
```

Todos os testes mockam `requests.get`/`requests.patch`/`_at_throttle`/
`input`/`logger` — nenhum acesso real ao Airtable.
