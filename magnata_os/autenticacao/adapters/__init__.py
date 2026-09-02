"""Adapters de infraestrutura de `magnata_os/autenticacao/` -- único
lugar deste pacote onde `flask` (e, em `postgres_auditoria.py`, um
driver de banco) são importados. Nada em `identidade.py`/`allowlist.py`/
`provedor_google_oidc.py`/`sessao.py`/`eventos.py` depende deste
subpacote na direção contrária."""
