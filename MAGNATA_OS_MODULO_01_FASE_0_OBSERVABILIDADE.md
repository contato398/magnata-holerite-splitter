# Módulo 01 (Ingestão) — Fase 0: Observabilidade

Documentação operacional da implementação de código da Fase 0, conforme
`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`. Esta fase **não é
shadow mode** — não persiste nenhum dado novo, não cria entidade, não
altera Airtable, não altera resposta HTTP de nenhuma rota. É só medição do
que já acontece hoje.

## O que foi feito

- **`src/observability.py`** (novo módulo): um decorator,
  `observar_ingestao(nome_rota)`, que envolve uma view Flask existente e
  registra logs estruturados antes e depois de chamá-la, sem nunca alterar
  o valor retornado pela view nem engolir uma exceção real.
- **`app.py`**: duas linhas adicionadas — um import do decorator e
  `@observar_ingestao('/separar')` diretamente acima de `def separar():`.
  Nenhuma outra linha de `app.py` foi tocada.
- **`test_observabilidade_fase0.py`** (novo): 15 testes que comprovam que
  o comportamento de `/separar` (status HTTP, corpo de resposta, ausência
  de escrita real) é idêntico com e sem a instrumentação.

## Porta instrumentada

Apenas **`/separar`** (`app.py`, função `separar()`). É a única rota real
de upload documental usada tanto pelo upload manual quanto pelo Make.com
(mesma função, mesmo contrato — ver `MAGNATA_OS_MODULO_01_INGESTAO.md`,
achado sobre a integração Make.com). `/email/webhook` (caminho Gmail) usa
uma função interna diferente e **não foi instrumentada** nesta fase;
`/processar-fila` e `/processar-doc-cliente` não recebem upload de
arquivo (JSON apenas) e também ficam fora do escopo desta fase.

## Como ativar/desativar

Variável de ambiente `MAGNATA_INGESTION_OBSERVABILITY_ENABLED`.

- Ausente ou qualquer valor não reconhecido como "desligado" → **ativado**
  (padrão seguro, é o objetivo desta fase).
- Valores que desativam: `0`, `false`, `no`, `off`, `nao`, `não`
  (case-insensitive).
- Com a flag desativada, `observar_ingestao` chama a view original
  diretamente, sem nenhum overhead nem log adicional — resposta idêntica.

## Campos registrados

Todos os logs são uma linha JSON precedida de `ingestion_observability`,
via o logger `ingestion.observability`.

**Evento `inicio`:** `rota`, `metodo`, `correlation_id`,
`correlation_preexistente` (bool — se veio de header ou foi gerado agora),
`arquivo_nome` (sanitizado, ver abaixo), `arquivo_mime_informado`,
`arquivo_extensao`, `quantidade_arquivos`, `tamanho_bytes_content_length`.

**Evento `fim`:** `rota`, `correlation_id`, `duracao_ms`, `status_http`,
`success_corpo` (valor do campo `success` no JSON de resposta, se houver),
`codigo_erro` (`error_code` do corpo, se houver), `registro_referenciado`
(`processar_arquivo_record_id` do corpo, se houver),
`classificacao_observacional` (ver seção seguinte).

**Evento `excecao`:** `rota`, `correlation_id`, `duracao_ms`,
`excecao_tipo` (nome da classe da exceção — nunca a mensagem completa nem
stack trace no log estruturado; o traceback completo só aparece no log
padrão do Python/Flask, como já acontecia antes desta fase).

**Nunca registrado:** token, header de autorização, cookie, conteúdo do
arquivo, payload completo, corpo de e-mail, telefone, CPF, URL assinada
completa, stack trace dentro do JSON estruturado. O nome do arquivo é
sanitizado por `nome_arquivo_seguro()` (mantém apenas
`[A-Za-z0-9._-]`, corta em 80 caracteres) antes de ir para o log.

## Identificador de correlação

Reaproveita `X-Request-ID` ou `X-Correlation-ID` do header da requisição,
se presente; caso contrário gera `obs<16 hex>` via `secrets.token_hex(8)`.
**Não é UUIDv7 e não é identidade canônica persistida** — é puramente
observacional, para conseguir juntar o log de início com o de fim (ou
exceção) da mesma requisição. A estratégia de identidade canônica real
(DEC-MOD01-011, DEC-MOD01-014) é assunto de fase futura.

## Como identificar HTTP 200 com falha funcional

O achado documentado em `MAGNATA_OS_MODULO_01_INGESTAO.md` — `/separar`
retorna HTTP 200 mesmo quando `success: false` — **não foi corrigido**
nesta fase (fora de escopo). A observabilidade só **nomeia** o que já
acontece, através do campo `classificacao_observacional` no evento `fim`:

| Classificação | Condição |
|---|---|
| `sucesso_real` | status 200/202 **e** corpo com `success: true` |
| `falha_funcional_http_200` | status 200 **e** corpo com `success: false` |
| `falha_http` | status fora de 200/202 (ex.: 400, 500) |
| `resultado_incerto` | corpo ausente/não-JSON ou combinação não coberta acima |

Para levantar quantas requisições reais caem em
`falha_funcional_http_200`, hoje a única forma é **grep nos logs** (não há
mecanismo de métricas agregadas no projeto — ver limitação abaixo).

## Métricas

**Nenhum mecanismo de métricas agregadas (contador, histograma, dashboard)
foi encontrado no projeto** durante a auditoria desta fase — não há
Prometheus, StatsD, nem equivalente já integrado a `app.py`. Por isso esta
fase se limita a log estruturado, sem publicar métricas agregadas.
**Limitação registrada, não resolvida aqui**: para ter contagem/série
temporal de `classificacao_observacional`, hoje é necessário processar os
logs (ex.: pelo provedor de log do Render) — não existe um contador
in-process nesta fase.

## Testes

`test_observabilidade_fase0.py` — 15 testes, todos mockando integrações
externas (Airtable, upload, fila); nenhuma escrita real ocorre. Cobrem:
upload manual válido (202), `/separar` com falha funcional (200,
`success: false`, para os 3 códigos de erro validados antes do upload),
`record_id` inválido (400), exceção não tratada (500 — comprovando que a
observabilidade não engole nem mascara a exceção), reaproveitamento de
`X-Request-ID`, consistência do `correlation_id` entre início e fim,
ausência de vazamento de segredo/CPF no log, e equivalência de
comportamento com a flag desativada.

Rodar: `python -m unittest test_observabilidade_fase0 -v`

## Rollback

Duas formas, da mais simples à mais completa:

1. **Sem deploy**: setar `MAGNATA_INGESTION_OBSERVABILITY_ENABLED=false`
   no ambiente — a rota volta a se comportar exatamente como antes desta
   fase, sem nenhum log adicional.
2. **Reverter o commit**: como a mudança em `app.py` é de 2 linhas (um
   import e um decorator) e `src/observability.py` é um arquivo novo e
   isolado, reverter o(s) commit(s) desta fase remove a instrumentação
   por completo, sem tocar em nenhuma outra lógica.

## O que esta fase explicitamente NÃO faz

Não implementa shadow mode; não persiste Item de Ingestão nem Arquivo
shadow; não cria tabela nova no Airtable nem em nenhum banco; não altera
nenhum status HTTP retornado por `/separar`; não corrige o achado
HTTP-200-com-`success:false`; não altera classificação, distribuição nem
assinatura; não usa UUIDv7 nem gera identidade canônica; não implementa as
5 decisões técnicas de Fase 1 registradas em
`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md` §26
(DEC-MOD01-014 a DEC-MOD01-018) — essas ficam para quando a Fase 1 for
autorizada.
