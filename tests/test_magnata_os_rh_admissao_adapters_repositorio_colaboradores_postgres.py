"""Testes do adapter `repositorio_colaboradores_postgres.py`. Usa uma
conexão FAKE (nunca rede/Postgres real) que imita a interface DB-API
2.0 mínima -- mesmo padrão de `test_postgres_contato_colaborador.py`.

Cobre a correção da lacuna 1 do PR #215 (cifra de CPF em repouso):
- valor enviado ao banco (`cpf_cifrado`) nunca é o CPF em texto puro;
- leitura de volta (`buscar_por_id`/`listar`) decifra corretamente;
- ausência da variável de ambiente da chave é fail-closed -- erro
  explícito, nenhuma escrita/leitura chega a tocar o cursor.

E a correção da lacuna 2 (histórico append-only real de correção de
local de trabalho):
- `registrar_evento_correcao_local_trabalho` grava um INSERT puro
  (nunca UPDATE/DELETE) e comita;
- `listar_historico_correcao_local_trabalho` só lê, reconstruindo
  `EventoCorrecaoLocalTrabalho` a partir das linhas.
"""
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from magnata_os.rh_admissao.adapters.repositorio_colaboradores_postgres import (
    RepositorioColaboradoresPostgres,
)
from magnata_os.rh_admissao.configuracao_cpf_colaborador import (
    ConfiguracaoSegredoCpfColaborador,
    SegredoCpfColaboradorAusente,
    carregar_configuracao_segredo_cpf,
)
from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    Colaborador,
    EventoCorrecaoLocalTrabalho,
    SituacaoCadastroColaborador,
)

CPF_SINTETICO = '900.000.000-01'
NOME_SINTETICO = 'colaborador sintetico teste'
_AGORA = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

_CONFIGURACAO_TESTE = ConfiguracaoSegredoCpfColaborador(
    ambiente={'MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE': 'chave-sintetica-de-teste-nao-usar-em-producao'},
)
_CONFIGURACAO_SEM_CHAVE = ConfiguracaoSegredoCpfColaborador(ambiente={})


class _CursorFake:
    def __init__(self, conexao):
        self._conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        comando = sql.strip().split()[0]
        self._conexao.execucoes.append((comando, sql, params))

    def fetchone(self):
        return self._conexao.linha_retornada

    def fetchall(self):
        return self._conexao.linhas_retornadas


class _ConexaoFake:
    def __init__(self, linha_retornada=None, linhas_retornadas=None):
        self.execucoes = []
        self.commits = 0
        self.rollbacks = 0
        self.linha_retornada = linha_retornada
        self.linhas_retornadas = linhas_retornadas or []

    def cursor(self):
        return _CursorFake(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _colaborador(colaborador_id='colab-1', cpf=CPF_SINTETICO):
    return Colaborador(
        colaborador_id=colaborador_id, cpf=cpf, nome=NOME_SINTETICO,
        situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
    )


def _evento(colaborador_id='colab-1'):
    return EventoCorrecaoLocalTrabalho(
        colaborador_id=colaborador_id,
        local_trabalho_anterior='Escala A - Dias Pares',
        local_trabalho_novo='Escala B - Dias Impares',
        motivo_correcao='Colaborador transferido de posto',
        determinado_por='operador.rh@magnataservicos.com.br',
        determinado_em=_AGORA,
    )


# ---- Cifra de CPF em repouso ----

class _ConexaoFakeComReturning(_ConexaoFake):
    """Simula o `RETURNING` do INSERT real: o que foi enviado na
    chamada é exatamente o que volta em `fetchone` (mesma disciplina do
    Postgres real, que devolve a linha efetivamente gravada)."""

    def cursor(self):
        return _CursorFakeComReturning(self)


class _CursorFakeComReturning(_CursorFake):
    def execute(self, sql, params=None):
        super().execute(sql, params)
        if sql.strip().split()[0] == 'INSERT' and params is not None and len(params) == 8:
            self._conexao.linha_retornada = (
                params[0], params[1], params[2], params[3], params[4], params[5],
                params[6] or _AGORA, params[7] or _AGORA,
            )


def test_salvar_envia_cpf_cifrado_nunca_texto_puro():
    conexao = _ConexaoFakeComReturning()
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_TESTE)

    persistido = repo.salvar(_colaborador())

    comandos = [c for c, _, _ in conexao.execucoes]
    assert comandos == ['INSERT']
    _, _, params = conexao.execucoes[0]
    cpf_cifrado_enviado = params[1]

    assert isinstance(cpf_cifrado_enviado, bytes)
    assert cpf_cifrado_enviado != CPF_SINTETICO.encode('utf-8')
    assert CPF_SINTETICO.encode('utf-8') not in cpf_cifrado_enviado
    # Leitura de volta (mesma chamada, via RETURNING simulado) decifra
    # corretamente.
    assert persistido.cpf == CPF_SINTETICO
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


def test_buscar_por_id_decifra_o_cpf_lido_do_banco():
    chave = _CONFIGURACAO_TESTE.obter_chave_fernet()
    cpf_cifrado = Fernet(chave).encrypt(CPF_SINTETICO.encode('utf-8'))
    linha = (
        'colab-1', cpf_cifrado, NOME_SINTETICO, 'Vigia', None,
        SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO.value, _AGORA, _AGORA,
    )
    conexao = _ConexaoFake(linha_retornada=linha)
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_TESTE)

    persistido = repo.buscar_por_id('colab-1')

    assert persistido is not None
    assert persistido.cpf == CPF_SINTETICO


def test_listar_decifra_todas_as_linhas():
    chave = _CONFIGURACAO_TESTE.obter_chave_fernet()
    linhas = [
        (
            f'colab-{i}', Fernet(chave).encrypt(f'90000000{i}01'.encode('utf-8')), NOME_SINTETICO, None, None,
            SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO.value, _AGORA, _AGORA,
        )
        for i in range(3)
    ]
    conexao = _ConexaoFake(linhas_retornadas=linhas)
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_TESTE)

    resultado = repo.listar()

    assert len(resultado) == 3
    assert {c.cpf for c in resultado} == {f'90000000{i}01' for i in range(3)}


def test_sem_variavel_de_ambiente_e_fail_closed_e_nunca_toca_o_cursor():
    conexao = _ConexaoFake()
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_SEM_CHAVE)

    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.salvar(_colaborador())
    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.buscar_por_id('colab-1')
    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.listar()

    # Fail-closed de verdade: nenhuma operação chegou a executar SQL --
    # nunca grava/lê sem cifra.
    assert conexao.execucoes == []
    assert conexao.commits == 0


def test_repositorio_sem_configuracao_injetada_usa_ambiente_real(monkeypatch):
    """Default de produção: sem `configuracao_segredo_cpf` explícita,
    o adapter lê `os.environ` no momento da operação (nunca cacheado em
    `__init__`) -- mesma disciplina de `carregar_configuracao_segredo_cpf`."""
    monkeypatch.delenv('MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE', raising=False)
    conexao = _ConexaoFake()
    repo = RepositorioColaboradoresPostgres(conexao)

    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.salvar(_colaborador())

    monkeypatch.setenv('MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE', 'chave-sintetica-via-ambiente-real')
    assert carregar_configuracao_segredo_cpf().obter_chave_fernet()  # nao levanta mais


# ---- Histórico append-only de correção de local de trabalho ----

def test_registrar_evento_correcao_grava_insert_puro_e_comita():
    conexao = _ConexaoFake()
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_TESTE)

    resultado = repo.registrar_evento_correcao_local_trabalho(_evento())

    comandos = [c for c, _, _ in conexao.execucoes]
    assert comandos == ['INSERT']
    assert 'UPDATE' not in [c for c, _, _ in conexao.execucoes]
    assert 'DELETE' not in [c for c, _, _ in conexao.execucoes]
    assert conexao.commits == 1
    assert resultado.motivo_correcao == 'Colaborador transferido de posto'


def test_registrar_evento_correcao_falha_reverte_transacao():
    class _ConexaoComFalha(_ConexaoFake):
        def cursor(self):
            raise RuntimeError('falha de conexao simulada')

    conexao = _ConexaoComFalha()
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_TESTE)

    with pytest.raises(RuntimeError):
        repo.registrar_evento_correcao_local_trabalho(_evento())

    assert conexao.rollbacks == 1
    assert conexao.commits == 0


def test_listar_historico_correcao_reconstroi_eventos():
    linha = (
        'colab-1', 'Escala A - Dias Pares', 'Escala B - Dias Impares',
        'Colaborador transferido de posto', 'operador.rh@magnataservicos.com.br', _AGORA,
    )
    conexao = _ConexaoFake(linhas_retornadas=[linha])
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CONFIGURACAO_TESTE)

    historico = repo.listar_historico_correcao_local_trabalho('colab-1')

    assert len(historico) == 1
    assert historico[0].colaborador_id == 'colab-1'
    assert historico[0].local_trabalho_anterior == 'Escala A - Dias Pares'
    assert historico[0].local_trabalho_novo == 'Escala B - Dias Impares'
    assert historico[0].determinado_por == 'operador.rh@magnataservicos.com.br'
    comandos = [c for c, _, _ in conexao.execucoes]
    assert comandos == ['SELECT']
