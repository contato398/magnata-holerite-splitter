"""Testes do adapter `postgres_resolucao_temporal.py` (missão
"IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1" + revisão
independente pós-PR #127, Foco 3: atomicidade real). Usa uma conexão
FAKE (nunca rede/Postgres real) que imita a interface DB-API 2.0
mínima — prova o formato exato dos comandos SQL e, principalmente, os
5 casos do gate de atomicidade:

  A) resolução nova + evento sucesso -> commit
  B) resolução nova + evento falha -> rollback de tudo
  C) atualização de resolução existente + evento sucesso -> commit
  D) atualização de resolução existente + evento falha -> rollback
     para o estado anterior
  E) resolução equivalente (idempotente) -> nenhuma escrita, nenhum
     commit de transação vazia
"""
import datetime

import pytest

from magnata_os.classificacao.contratos import EstadoResolucaoDimensao
from magnata_os.classificacao.resolucao_temporal_ponto import (
    TransicaoResolucaoTemporal,
    resolver_documento_ponto,
)
from magnata_os.documental.modulo01.adapters.postgres_resolucao_temporal import (
    RepositorioResolucaoTemporalPostgres,
)
from magnata_os.documental.modulo01.dominio import EventoHistorico, gerar_correlation_id


class _FonteVazia:
    def listar_para_colaborador(self, colaborador_id):
        return ()


def _resolucao(documento_id: str, periodo_inicio_txt: str, periodo_fim_txt: str):
    texto = f'Período: {periodo_inicio_txt} até {periodo_fim_txt}'
    resolucao, _cliente = resolver_documento_ponto(documento_id, texto, 'func-pg-1', _FonteVazia())
    return resolucao


def _linha_da_resolucao(resolucao) -> tuple:
    competencia = (
        resolucao.resolucao_competencia.valores_confirmados[0].entidade_id
        if resolucao.resolucao_competencia.valores_confirmados else None
    )
    return (
        f'restemp:{resolucao.documento_id}', resolucao.documento_id, resolucao.tipo_documental,
        resolucao.colaborador_id, resolucao.periodo_inicio, resolucao.periodo_fim,
        competencia, resolucao.resolucao_competencia.estado.value, '{}',
    )


def _evento(documento_id: str) -> EventoHistorico:
    return EventoHistorico(
        documento_id=documento_id, evento='RESOLUCAO_TEMPORAL_PONTO_REGISTRADA',
        status_anterior=None, status_novo=None,
        timestamp=datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
        correlation_id=gerar_correlation_id(), detalhes={},
    )


def _fabricar_evento(transicao, anterior, novo):
    return _evento(novo.documento_id)


class _CursorFake:
    def __init__(self, conexao):
        self._conexao = conexao
        self._ultima_linha_fetch = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        comando = sql.strip().split()[0]
        self._conexao.execucoes.append((comando, params))
        if comando == 'SELECT':
            self._ultima_linha_fetch = self._conexao.linha_existente
        if self._conexao.falhar_na_execucao_numero is not None:
            if len(self._conexao.execucoes) == self._conexao.falhar_na_execucao_numero:
                raise RuntimeError('falha simulada de execução SQL')

    def fetchone(self):
        return self._ultima_linha_fetch

    def fetchall(self):
        return []


class _ConexaoFake:
    """Conexão DB-API 2.0 mínima, sem rede. `linha_existente` simula o
    que um `SELECT ... FOR UPDATE` encontraria -- `None` = documento
    novo, uma tupla = resolução já persistida."""

    def __init__(self, linha_existente=None, falhar_na_execucao_numero=None):
        self.execucoes = []
        self.commits = 0
        self.rollbacks = 0
        self.linha_existente = linha_existente
        self.falhar_na_execucao_numero = falhar_na_execucao_numero

    def cursor(self):
        return _CursorFake(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


# ---------------------------------------------------------------------------
# A) resolução nova + evento sucesso -> commit
# ---------------------------------------------------------------------------

def test_caso_a_resolucao_nova_com_evento_sucesso_faz_select_insert_insert_e_1_commit():
    conexao = _ConexaoFake(linha_existente=None)
    repo = RepositorioResolucaoTemporalPostgres(conexao)
    transicao = repo.salvar_com_evento(_resolucao('doc-a', '29/05/2026', '28/06/2026'), _fabricar_evento)

    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT', 'INSERT', 'INSERT']
    assert transicao == TransicaoResolucaoTemporal.NOVA
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


# ---------------------------------------------------------------------------
# B) resolução nova + evento falha -> rollback de tudo
# ---------------------------------------------------------------------------

def test_caso_b_resolucao_nova_com_falha_no_evento_reverte_tudo():
    # Execuções: 1=SELECT, 2=INSERT resolução, 3=INSERT evento (falha aqui)
    conexao = _ConexaoFake(linha_existente=None, falhar_na_execucao_numero=3)
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    with pytest.raises(RuntimeError):
        repo.salvar_com_evento(_resolucao('doc-b', '29/05/2026', '28/06/2026'), _fabricar_evento)

    assert conexao.commits == 0  # nunca um commit parcial
    assert conexao.rollbacks == 1


# ---------------------------------------------------------------------------
# C) atualização de resolução existente + evento sucesso -> commit
# ---------------------------------------------------------------------------

def test_caso_c_atualizacao_legitima_com_evento_sucesso_faz_select_update_insert_e_1_commit():
    anterior = _resolucao('doc-c', '', '')  # forca NAO_ENCONTRADA (sem periodo)
    conexao = _ConexaoFake(linha_existente=_linha_da_resolucao(anterior))
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    nova = _resolucao('doc-c', '29/05/2026', '28/06/2026')  # correcao legitima -> ATUALIZACAO
    transicao = repo.salvar_com_evento(nova, _fabricar_evento)

    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT', 'UPDATE', 'INSERT']
    assert transicao == TransicaoResolucaoTemporal.ATUALIZACAO
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


# ---------------------------------------------------------------------------
# D) atualização de resolução existente + evento falha -> rollback
# ---------------------------------------------------------------------------

def test_caso_d_atualizacao_com_falha_no_evento_reverte_tudo():
    anterior = _resolucao('doc-d', '', '')
    # Execuções: 1=SELECT, 2=UPDATE, 3=INSERT evento (falha aqui)
    conexao = _ConexaoFake(linha_existente=_linha_da_resolucao(anterior), falhar_na_execucao_numero=3)
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    nova = _resolucao('doc-d', '29/05/2026', '28/06/2026')
    with pytest.raises(RuntimeError):
        repo.salvar_com_evento(nova, _fabricar_evento)

    assert conexao.commits == 0
    assert conexao.rollbacks == 1


# ---------------------------------------------------------------------------
# E) resolução equivalente (idempotente) -> nenhuma escrita, nenhum commit
# ---------------------------------------------------------------------------

def test_caso_e_resolucao_equivalente_nao_escreve_nem_comita_so_libera_o_lock():
    igual = _resolucao('doc-e', '29/05/2026', '28/06/2026')
    conexao = _ConexaoFake(linha_existente=_linha_da_resolucao(igual))
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    chamado = {'vezes': 0}

    def _fabricar_evento_nao_deveria_ser_chamado(transicao, anterior, novo):
        chamado['vezes'] += 1
        return _evento(novo.documento_id)

    transicao = repo.salvar_com_evento(igual, _fabricar_evento_nao_deveria_ser_chamado)

    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT']  # nenhum INSERT/UPDATE
    assert transicao == TransicaoResolucaoTemporal.EQUIVALENTE
    assert chamado['vezes'] == 0  # fabricar_evento nunca chamado para EQUIVALENTE
    assert conexao.commits == 0  # nunca commit de transacao vazia
    assert conexao.rollbacks == 1  # so libera o lock do SELECT ... FOR UPDATE


def test_falha_no_select_tambem_reverte_e_nunca_tenta_escrever():
    conexao = _ConexaoFake(linha_existente=None, falhar_na_execucao_numero=1)
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    with pytest.raises(RuntimeError):
        repo.salvar_com_evento(_resolucao('doc-f', '29/05/2026', '28/06/2026'), _fabricar_evento)

    assert conexao.commits == 0
    assert conexao.rollbacks == 1
    assert len(conexao.execucoes) == 1
