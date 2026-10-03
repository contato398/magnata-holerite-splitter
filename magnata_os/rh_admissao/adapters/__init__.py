"""Adapters de infraestrutura do RH/Admissão -- Postgres.

Nenhum destes módulos importa uma biblioteca de driver específica
(psycopg2/psycopg) por nome no topo do arquivo. Trabalham contra a
interface DB-API 2.0 injetada pelo chamador (mesma disciplina de
`magnata_os/documental/modulo01/adapters/`).
"""
