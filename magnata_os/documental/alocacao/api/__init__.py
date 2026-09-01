"""
Camada de aplicação/API da Confirmação de Alocação (missão "ENTRADA
OPERACIONAL + POSTGRES PRÓPRIO V1").

Desacoplada do legado (Flask/`app.py`) de propósito -- nada aqui
importa `flask`, `app`, nem qualquer coisa fora de `magnata_os/`. Um
adapter web futuro (fora do escopo desta missão -- ver FASE 6 do ADR,
gate de autenticação real) é quem vai expor estes handlers como rotas
HTTP de fato.

Mesmo desenho de `magnata_os/documental/modulo01/api/` -- reaplicado
aqui, não importado de lá (ver `../autorizacao.py` para o porquê da
duplicação deliberada).
"""
