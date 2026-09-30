"""Fabrica do `ContextoApi` (handlers.py) a partir de conexao Postgres
real (Modulo 01, Fase 5 -- "dados reais" do painel operacional).

Isolado de blueprint_esteira.py de proposito: monta so os 4
repositorios Postgres ja existentes (Fase 2/3) sobre UMA conexao aberta
via `conexao.abrir_conexao` (que ja le DATABASE_URL do ambiente e nunca
vaza credencial em excecao -- ver conexao.py). Reexporta
`ConfiguracaoBancoAusente`/`FalhaConexaoBanco` para quem monta o
contexto poder tratar os dois casos sem importar `conexao.py`
diretamente."""
from __future__ import annotations

from ..api.handlers import ContextoApi
from .conexao import ConfiguracaoBancoAusente, FalhaConexaoBanco, abrir_conexao
from .postgres_repositorio import RepositorioDocumentosPostgres, RepositorioHistoricoPostgres
from .postgres_repositorio_esteira import RepositorioEstadosEsteiraPostgres, RepositorioLotesPostgres

__all__ = ['ConfiguracaoBancoAusente', 'FalhaConexaoBanco', 'montar_contexto_api_postgres']


def montar_contexto_api_postgres() -> ContextoApi:
    """Abre uma conexao Postgres real (DATABASE_URL) e monta um
    ContextoApi com os 4 repositorios Postgres. Levanta
    ConfiguracaoBancoAusente se DATABASE_URL nao estiver definida, ou
    FalhaConexaoBanco se a conexao falhar -- nunca devolve um contexto
    parcialmente funcional nem cai para dado em memoria/mockado em
    silencio."""
    conexao = abrir_conexao()
    return ContextoApi(
        repositorio_documentos=RepositorioDocumentosPostgres(conexao),
        repositorio_historico=RepositorioHistoricoPostgres(conexao),
        repositorio_lotes=RepositorioLotesPostgres(conexao),
        repositorio_estados=RepositorioEstadosEsteiraPostgres(conexao),
    )
