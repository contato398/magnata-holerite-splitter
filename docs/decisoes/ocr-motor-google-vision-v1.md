# Motor OCR real: Google Cloud Vision API (Fase 1 -- estrutural)

**Data:** 2026-09-30
**Branch:** `fix/ocr-motor-google-vision-v1`
**Status:** Implementado e testado (rede real NUNCA exercitada nesta fase) -- gate remanescente declarado abaixo.

## Contexto

`magnata_os/documental/ocr.py` já define a porta plugável `MotorOcr`
desde a Fase de Localização Documental (PDF composto), com o
docstring registrando explicitamente que "Nenhum motor de OCR existe
no repositório". Esta missão fecha essa lacuna com o PRIMEIRO motor
real, sem alterar a porta.

## Decisão de negócio (operador, já tomada -- registrada aqui, não decidida por este documento)

- Motor escolhido: **Google Cloud Vision API**, por custo
  (~US$1,50/1.000 páginas) e por já estar no mesmo projeto Google
  Cloud usado para o login do painel.
- Credencial: **Chave de API** (API Key), não conta de serviço -- a
  organização **bloqueia criação de chave de conta de serviço** por
  política de segurança. A chave já foi criada no Google Cloud
  Console, restrita à Cloud Vision API.
- A chave será configurada como variável de ambiente
  `GOOGLE_VISION_API_KEY` no Render (produção). **Não está disponível
  neste ambiente de desenvolvimento** e não foi mockada como se
  existisse.

## O que foi implementado

- **`magnata_os/documental/ocr_google_vision.py`** (novo) --
  `MotorOcrGoogleVision`, implementação real da porta `MotorOcr`
  (`extrair_paginas(conteudo_pdf: bytes) -> Tuple[str, ...]`), sem
  tocar `ocr.py`.
  - Lê `GOOGLE_VISION_API_KEY` só no momento do uso
    (`ler_chave_google_vision`), nunca no import, nunca cacheada,
    nunca logada (nem parcialmente).
  - Ausência de chave -> `ConfiguracaoGoogleVisionAusente` (mesmo
    padrão de `ConfiguracaoBancoAusente` em
    `magnata_os/documental/modulo01/adapters/conexao.py`) --
    fail-closed: o motor nunca finge que fez OCR nem inventa texto.
    `extrair_paginas_com_ocr` (ocr.py) já trata qualquer exceção do
    motor como `ocr_falhou=True`/mantém a extração normal -- esse é o
    contrato já existente, reaproveitado sem alteração.
  - Cliente HTTP injetável (`ClienteHttp`, interface mínima com
    `.post(url, params, json, timeout)`). Nenhum teste faz chamada de
    rede real. A implementação real (`_ClienteRequests`) usa
    `requests` (já em `requirements.txt`), import local só quando o
    motor de fato tenta enviar uma chamada.
  - Timeout configurado (`timeout_segundos`, default 30s). Erro de
    rede/timeout/resposta malformada da API DURANTE uma tentativa real
    nunca propaga para quem chamou `extrair_paginas`: isolado por
    bloco de páginas (mesma disciplina de
    `orquestrador/coleta_fontes_externas_v1.py`), registrado em log
    (nunca com a chave, nunca com a query string) e a(s) página(s)
    afetada(s) volta(m) como texto vazio -- nunca texto inventado.
    Como `extrair_paginas_com_ocr` só aceita OCR quando ele devolve
    MAIS texto que a extração normal, texto vazio nunca piora o
    resultado.

## Escolha de endpoint: `files:annotate`, não `images:annotate`

A missão mencionava literalmente o endpoint `images:annotate`. Ao
confirmar o formato exato na documentação oficial do Google (via
busca -- acesso direto a `docs.cloud.google.com` está bloqueado pelo
proxy de rede deste ambiente), ficou claro que:

- `images:annotate` espera **uma imagem rasterizada por requisição**
  (JPEG/PNG/...). Um PDF de várias páginas precisaria ser convertido
  página a página para imagem antes do envio.
- Este repositório **não tem nenhuma biblioteca de conversão PDF ->
  imagem** instalada (nem `PyMuPDF`/`fitz`, nem `pdf2image` + Poppler
  binário). Adicionar uma é uma dependência de sistema nova, fora do
  escopo desta missão (que pediu para implementar o MOTOR, não somar
  infraestrutura de conversão de imagem).
- `files:annotate` (`POST
  https://vision.googleapis.com/v1/files:annotate`) aceita o PDF
  inteiro (bytes) inline via `inputConfig.content` (base64) com
  `mimeType: application/pdf`, com `features:
  [{"type": "DOCUMENT_TEXT_DETECTION"}]`, e devolve texto por página
  -- exatamente o formato que `MotorOcr.extrair_paginas` já precisa
  (bytes -> texto por página), sem nenhuma conversão.
- Limite conhecido da API: no máximo 5 páginas por
  `AnnotateFileRequest` síncrono. O motor agrupa páginas em blocos de
  até 5 dentro do MESMO corpo HTTP (`requests: [...]`), então um PDF
  de N páginas sai como `ceil(N/5)` chamadas HTTP, nunca uma por
  página.
- Autenticação: chave de API na query string (`?key=<chave>`), que é
  exatamente como chave de API funciona nessa API (sem OAuth, sem
  conta de serviço) -- coerente com a decisão do operador.

Esta é uma decisão técnica local e reversível dentro do escopo já
aprovado (implementar o motor real); registrada aqui por divergir da
menção literal da missão, conforme `/CLAUDE.md` §2 ("nenhuma decisão
arquitetural é tomada em silêncio").

## Testes

`tests/test_magnata_os_documental_ocr_google_vision.py` -- cliente
HTTP fake, nenhuma chamada de rede real em nenhum teste. Cobre:

- chave ausente/em branco -> `ConfiguracaoGoogleVisionAusente`, sem
  chamar rede;
- via `extrair_paginas_com_ocr`: chave ausente marca `ocr_falhou`
  coerentemente com o contrato de falha de motor já existente;
- chave presente: chamada HTTP correta (URL, `params={'key': ...}`,
  corpo com `inputConfig`/`features`/`pages`) e tradução correta da
  resposta para texto por página;
- integração real com `extrair_paginas_com_ocr` (substitui só a
  página deficiente, quando o OCR devolve mais texto);
- PDF com mais de 5 páginas -> múltiplos blocos de requisição;
- erro de rede/timeout: nunca propaga, página(s) afetada(s) ficam
  vazias, `ocr_falhou` continua `False` no nível de `ocr.py` porque o
  motor devolveu com sucesso (texto vazio nunca supera o original);
- resposta malformada (corpo vazio, contagem de páginas divergente,
  status HTTP != 200/erro da API) -- nunca quebra, mesma degradação
  para texto vazio;
- nenhuma chave aparece em nenhuma mensagem de log/erro capturada
  pelos testes.

Suíte completa: `2996 passed, 103 skipped` -- zero regressão.

## Onde plugar o motor real (fora do escopo desta missão -- fica registrado, não feito)

`motor_ocr: Optional[object] = None` já existe como campo em dois
pontos de composição, hoje sempre `None`:

- `magnata_os/orquestrador/composicao_prestacao_real_v1.py` --
  `DependenciasPrestacaoReal.motor_ocr`;
- `magnata_os/classificacao/composicao_ciclo_persistente_prestacao.py`
  -- `ContextoComposicaoPrestacao.motor_ocr`.

Ativar o OCR real em qualquer um desses pontos é trocar `None` por
`MotorOcrGoogleVision()` (sem argumentos -- lê a chave do ambiente em
tempo de uso). Essa troca **não foi feita nesta missão** -- é decisão
de composição/wiring separada, e só tem efeito quando
`GOOGLE_VISION_API_KEY` existir de fato no ambiente que a executa.

## Gate remanescente (declarado, não escondido)

- `GOOGLE_VISION_API_KEY` **não está configurada** neste ambiente de
  desenvolvimento nem, até onde este documento sabe, no Render de
  produção. O motor está estruturalmente pronto e testado (com
  cliente HTTP fake), mas **nenhum OCR real acontece em produção até
  essa variável existir de fato no Render** -- essa ativação é gate
  humano/infra, fora do escopo e da autonomia desta missão.
- A troca de `motor=None` para `MotorOcrGoogleVision()` num dos dois
  pontos de composição acima também não foi feita -- é uma mudança de
  comportamento funcional (liga OCR real onde antes não rodava nada),
  que merece revisão e decisão à parte, não incluída silenciosamente
  aqui.
- Nenhuma chamada de rede real à Cloud Vision API foi feita durante
  esta missão (nem de teste, nem de verificação manual) -- fora da
  autonomia concedida.
