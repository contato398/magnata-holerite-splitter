"""
Camada de aplicacao/API de consulta da esteira documental (Modulo 01,
Fase 4).

Desacoplada do legado (Flask/app.py) de proposito -- nada aqui importa
`flask`, `app`, nem qualquer coisa fora de `magnata_os/`. Um adapter web
futuro (fora do escopo desta fase) e quem vai expor estes handlers como
rotas HTTP de fato, traduzindo query string/JSON de entrada para os
tipos definidos em `filtros.py` e a resposta dos handlers (`contratos.py`)
para JSON via `serializacao.para_json`.

Ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE4.md.
"""
