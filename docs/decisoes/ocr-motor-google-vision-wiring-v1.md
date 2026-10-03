# Wiring do motor real de OCR (Google Cloud Vision) na composição

> ## ATENÇÃO — IMPLICAÇÃO DE CUSTO REAL A PARTIR DO MERGE
>
> **`GOOGLE_VISION_API_KEY` já está configurada no Render (produção),
> confirmado pelo operador.** A partir do merge da PR que contém este
> documento, o **próximo processamento real de um PDF de holerite
> escaneado (sem texto extraível) em produção vai disparar uma chamada
> real e PAGA à Google Cloud Vision API** (~US$ 1,50 a cada 1.000
> páginas processadas por OCR).
>
> Isto não é mais só código de teste ou infraestrutura estrutural — é
> **ativação funcional real**. Antes desta mudança, `motor_ocr` era
> sempre `None` nos dois pontos de composição e nenhuma chamada de OCR
> jamais acontecia, mesmo com a chave configurada. Depois desta
> mudança, com a chave presente no ambiente, o OCR real liga
> **automaticamente**, sem nenhum outro gate.
>
> **O merge desta PR é, por si só, a decisão de ligar o gasto real em
> produção.** Não deve ser um clique automático — é uma decisão
> consciente do operador, exatamente como pedido na missão.

**Data:** 2026-09-30
**Branch:** `fix/ocr-motor-google-vision-v1`
**Complementa:** `docs/decisoes/ocr-motor-google-vision-v1.md` (decisão
de implementação do motor `MotorOcrGoogleVision`; este documento cobre
só o wiring/ativação na composição, que aquele documento explicitamente
deixou de fora do escopo — ver sua seção "Onde plugar o motor real").

## O que foi ligado

Só **um** ponto de composição lê variáveis de ambiente para montar
dependências reais: `compor_dependencias_a_partir_do_ambiente` em
`magnata_os/orquestrador/composicao_prestacao_real_v1.py`. É o mesmo
padrão já usado para Postgres (`DATABASE_URL`), S3
(`ORQUESTRADOR_S3_BUCKET`) e o leitor Airtable (`AIRTABLE_API_KEY`).

`magnata_os/classificacao/composicao_ciclo_persistente_prestacao.py`
**não precisou de nenhuma mudança**: `ContextoComposicaoPrestacao.motor_ocr`
já é preenchido a partir de `DependenciasPrestacaoReal.motor_ocr` dentro
de `montar_contexto_prestacao` (mesmo arquivo, linha
`motor_ocr=d.motor_ocr`) — o campo já existia como ponto de recepção,
não como segundo ponto de leitura de ambiente. Ligar só na origem
(`compor_dependencias_a_partir_do_ambiente`) é seguir o padrão já
existente de "montar dependências reais a partir do ambiente num único
lugar", não inventar um padrão novo.

### Mudança

Em `compor_dependencias_a_partir_do_ambiente`:

```python
chave_google_vision = os.environ.get('GOOGLE_VISION_API_KEY', '').strip()
motor_ocr = MotorOcrGoogleVision() if chave_google_vision else None
```

`motor_ocr` passa a ser injetado em `DependenciasPrestacaoReal`, no
lugar do `None` fixo anterior.

## Por que este é OPCIONAL, diferente do Airtable (decisão deliberada)

`chave_airtable` ausente levanta `RuntimeError` (fail-closed
obrigatório — a ponte Airtable é essencial nesta fase). **OCR não
segue o mesmo padrão de propósito**: é recurso best-effort desde a
Fase de Localização Documental (`ocr.py`, docstring original: "motor
plugável, ausência de motor é o padrão"). Downstream,
`extrair_paginas_com_ocr` já trata `motor_ocr=None` como "não tenta
OCR, segue com a extração normal" — nunca como erro.

Por isso a composição segue o padrão de `MAGNATA_CNPJ_PROPRIO`
(`os.environ.get(...).strip() or None`), não o padrão fail-closed do
Airtable:

- `GOOGLE_VISION_API_KEY` ausente ou em branco -> `motor_ocr=None`,
  **exatamente o comportamento de antes desta mudança** — nenhuma
  regressão, nenhum erro novo;
- `GOOGLE_VISION_API_KEY` presente -> `motor_ocr=MotorOcrGoogleVision()`,
  instanciado sem argumentos (lê a chave de verdade só no momento do
  uso real, dentro de `extrair_paginas` — nunca no import, nunca
  cacheada).

## Testes

`tests/test_composicao_prestacao_real_ocr_wiring.py` (novo) — todas as
dependências de infraestrutura (Postgres, S3, Airtable) substituídas
por fakes via `monkeypatch` nos mesmos pontos de import que a função já
usa; nenhuma chamada de rede real em nenhum teste. Cobre:

- `GOOGLE_VISION_API_KEY` presente -> `motor_ocr` é uma instância real
  de `MotorOcrGoogleVision` (verificação por tipo, sem chamar
  `extrair_paginas`, sem rede);
- `GOOGLE_VISION_API_KEY` ausente -> `motor_ocr is None`, sem erro
  (comportamento idêntico ao pré-existente);
- `GOOGLE_VISION_API_KEY` em branco (só espaços) -> tratada como
  ausente, mesmo padrão de `.strip()` já usado para `AIRTABLE_API_KEY`
  e `MAGNATA_CNPJ_PROPRIO`;
- regressão: `AIRTABLE_API_KEY` ausente continua levantando
  `RuntimeError` independente do estado do OCR (a mudança no OCR não
  afrouxa a obrigatoriedade já existente do Airtable).

**Suíte completa:** `3000 passed, 103 skipped` — zero regressão.
**Gates de governança locais** (`scripts/ci/validate_governance.sh`):
15/15 aprovados.

## O que continua igual (não foi tocado)

- A porta `MotorOcr` (`ocr.py`) e a implementação
  `MotorOcrGoogleVision` (`ocr_google_vision.py`) -- inalteradas.
- O tratamento de falha do motor em `extrair_paginas_com_ocr` (captura
  ampla, `ocr_falhou=True`, nunca propaga) -- inalterado. Erro de rede
  real (timeout, resposta malformada) durante uma tentativa real
  continua isolado por bloco de páginas dentro do próprio motor,
  registrado em log sem a chave.
- `composicao_ciclo_persistente_prestacao.py` -- nenhuma linha
  alterada; o campo `motor_ocr` já existia e já era propagado
  corretamente.

## Gate remanescente / risco declarado

- **Custo real em produção**, já detalhado no aviso no topo deste
  documento: a partir do merge, com `GOOGLE_VISION_API_KEY` já presente
  no Render, o próximo holerite escaneado processado em produção gera
  uma chamada real e paga.
- Nenhuma chamada de rede real à Cloud Vision API foi feita durante
  esta missão (nem em teste, nem em verificação manual) -- fora da
  autonomia concedida; toda a verificação foi feita com fakes/mocks.
- Este documento e a PR que o acompanha **são o checkpoint humano**
  para essa ativação -- o merge é a confirmação consciente pedida.
