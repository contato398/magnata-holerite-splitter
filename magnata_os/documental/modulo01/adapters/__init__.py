"""Adapters de infraestrutura do Modulo 01, Fase 2 -- Postgres e S3.

Nenhum destes modulos importa uma biblioteca de driver especifica
(psycopg2/psycopg/boto3). Trabalham contra interfaces (DB-API 2.0 / S3
client) injetadas pelo chamador. Ver
MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md.
"""
