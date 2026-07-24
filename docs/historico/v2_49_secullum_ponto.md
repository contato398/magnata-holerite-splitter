---
name: v2_49_secullum_ponto
description: "Integração Secullum Ponto Web (módulo /secullum) — endpoints reais, rate limit, 3 travas de negócio (v2.50)"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Integração com **Secullum Ponto Web**, Banco ID **149582**. Módulo isolado
`src/services/secullum_ponto.py` (Blueprint Flask, prefixo `/secullum`),
registrado no `app.py`. Trabalhar no repo de produção [[repo_producao_caminho_oficial]].

## Endpoints REAIS (confirmados via Swagger oficial, não chutar)
- Auth: `POST https://autenticador.secullum.com.br/Token` (grant_type=password, client_id=3) → Bearer.
- Base API: `https://pontowebintegracaoexterna.secullum.com.br/IntegracaoExterna`
  (o `pontowebapi.secullum.com.br` que chutei **não existe**).
- Header obrigatório: `secullumidbancoselecionado: 149582`.
- Funcionários: `GET /Funcionarios` (lista 88). Campos reais: `Id`, `Cpf` (com máscara),
  `Nome`, `NumeroPis`, `Admissao`, **`Demissao`** (null=ativo; NÃO existe campo "Demitido"),
  `Horario.Descricao` (ex.: "12x36 19h - 07h IMPAR").
- Cálculo: `POST /Calcular` body `{funcionarioCpf, dataInicial, dataFinal}` (date-time).
  **Não existe** endpoint "Calculos". Resposta é COLUNAR:
  `{'Colunas':[...], 'Linhas':[{'Key':dataISO,'Value':[...]}]}`. Colunas incluem
  Entrada/Saída 1..3, Normais, Faltas, Extras, Carga, T+/-, etc.

## RATE LIMIT (importante)
Secullum retorna **429 Too Many Requests** sob rajada (88 chamadas seguidas estouram
a cota; bloqueio dura janela longa, min/hora). Mitigação v2.49.8: `_secullum_throttle`
(`SECULLUM_MIN_INTERVAL`=1.2s entre chamadas) + retry com backoff respeitando
Retry-After (`SECULLUM_RETRIES`=4). NÃO testar com scans completos repetidos; usar
`limit` pequeno. Scan completo de 88 leva ~110s.

## Regras de negócio (v2.50 — decididas 24/06/2026)
- **Desvio de carga**: base `faltas` (default `SECULLUM_DESVIO_BASE`). Só horas
  FALTANTES > 02:00; ignora extras de escala 12x36 (com `ambos` dava 604 falsos
  positivos/mês vs ~44 com faltas). Override por request: body `desvio_base`.
- **#1 Virada de dia (12x36)**: o /Calcular já agrega marcações pós-meia-noite na
  linha do plantão; a varredura lê por jornada (1 linha=1 plantão), nunca trata
  batida do dia seguinte como isolada. `_horario_noturno` detecta entrada >= 18h.
- **#2 Troca/substituição**: varredura em 2 passadas. Passada 1 monta `presenca[data]=set(cpf)`
  + mapa funcionário↔local do Airtable (Funcionários."Locais de trabalho"). Falta
  coberta por colega do MESMO local presente no dia vira **"Troca de Plantão a Confirmar"**,
  não falta pura. Sem chamadas extras à Secullum.
- **#3 Batida ímpar noturna**: distingue se faltou ENTRADA (início, noite) ou SAÍDA
  (manhã seguinte) antes de descrever a pendência.

## Saída
Alertas gravados em **Pendências/Revisar** (`tblRkJBL6Wwf4fxVC`), vinculados ao
Funcionário por CPF, título determinístico `[Ponto] <tipo> — <nome> — <data>` (dedup),
typecast nos singleSelect. Tipos: TIPO_BATIDA_IMPAR, TIPO_DESVIO_CARGA, TIPO_TROCA_PLANTAO.
Rotas: `POST /secullum/sincronizar` (CPF obrig.), `POST /secullum/varrer`
(dry_run/limit/desvio_base; resumo traz alertas_por_tipo + contadores de confiabilidade),
`GET /secullum/health`, `GET /secullum/debug` (diagnóstico, temporário).

## Status (24/06/2026)
v2.50 deployado. Dry_run validado (limit:20): 3 regras disparam corretamente em dados
reais de Maio (incl. troca real Diego cobrindo). **Nada gravado ainda** — tudo dry_run.
Falta: scan completo dry_run + decisão de tirar o dry_run p/ gravar de verdade.
ENVs Render: `SECULLUM_USUARIO`/`SECULLUM_SENHA` (Bia), reusa `AIRTABLE_API_KEY`.
Possível refino futuro: suprimir falta em dias de Férias/Licença/Abono. Ver
[[padrao_deploy_render_confirmar_versao]].
