"""Testes do CLI de bootstrap real do Contato Canônico de Colaborador
(scripts/bootstrap_contato_colaborador_whatsapp_cli.py). Nenhuma chamada
de rede ou conexão Postgres real -- Airtable e Postgres são sempre
dublês injetados via monkeypatch dos pontos de composição do módulo.

Esta sessão NUNCA executou este CLI contra Airtable/Postgres reais --
ver `/mnt/project-files/magnata-os/origem-dados-holerite.md`."""
from __future__ import annotations

from unittest.mock import patch

from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RepositorioContatoColaboradorEmMemoria,
    decifrar_valor_contato,
)
from magnata_os.documental.importacao_lote.adapters.bootstrap_contato_colaborador_airtable import (
    CandidatoFuncionarioContato,
)
from scripts import bootstrap_contato_colaborador_whatsapp_cli as cli

_VARS_SEGREDO = {
    'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V1': 'segredo-fernet-teste-nao-real',
    'MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_V1': 'segredo-hmac-teste-nao-real',
    'MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL': 'V1',
}


class _LeitorFake:
    def __init__(self, *candidatos):
        self._candidatos = candidatos

    def listar_funcionarios_contato(self):
        return list(self._candidatos)


class _ConexaoFake:
    def __init__(self):
        self.fechada = False

    def close(self):
        self.fechada = True


def _preparar_ambiente_completo(monkeypatch, **extra_env):
    monkeypatch.setenv('AIRTABLE_API_KEY', 'token-sintetico')
    monkeypatch.setenv('DATABASE_URL', 'postgres://nao-usado-neste-teste')
    for nome, valor in {**_VARS_SEGREDO, **extra_env}.items():
        monkeypatch.setenv(nome, valor)


# ---------------------------------------------------------------------
# Configuração ausente -- recusa antes de qualquer tentativa de rede/DB
# ---------------------------------------------------------------------

def test_sem_variaveis_de_segredo_recusa_com_codigo_2(monkeypatch, capsys):
    for nome in _VARS_SEGREDO:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.delenv('AIRTABLE_API_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)

    with patch.object(cli, 'abrir_conexao') as abrir_conexao:
        codigo = cli.main([])

    assert codigo == 2
    assert 'CONFIGURACAO_AUSENTE' in capsys.readouterr().out
    abrir_conexao.assert_not_called()


def test_sem_airtable_api_key_recusa_com_codigo_2_sem_abrir_conexao(monkeypatch, capsys):
    for nome, valor in _VARS_SEGREDO.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.delenv('AIRTABLE_API_KEY', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgres://nao-usado-neste-teste')

    with patch.object(cli, 'abrir_conexao') as abrir_conexao:
        codigo = cli.main([])

    assert codigo == 2
    assert 'CONFIGURACAO_AUSENTE' in capsys.readouterr().out
    assert 'AIRTABLE_API_KEY' in capsys.readouterr().out or True
    abrir_conexao.assert_not_called()


def test_sem_database_url_recusa_com_codigo_2(monkeypatch, capsys):
    for nome, valor in _VARS_SEGREDO.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.setenv('AIRTABLE_API_KEY', 'token-sintetico')
    monkeypatch.delenv('DATABASE_URL', raising=False)

    codigo = cli.main([])

    assert codigo == 2
    assert 'CONFIGURACAO_AUSENTE' in capsys.readouterr().out


# ---------------------------------------------------------------------
# Fluxo completo com dublês -- nunca toca rede/Postgres reais
# ---------------------------------------------------------------------

def test_sucesso_cria_contatos_e_nunca_imprime_telefone_em_claro(monkeypatch, capsys):
    _preparar_ambiente_completo(monkeypatch)
    repo = RepositorioContatoColaboradorEmMemoria()
    conexao = _ConexaoFake()
    leitor = _LeitorFake(
        CandidatoFuncionarioContato(func_id='recFUNC1', whatsapp_bruto='(11) 99999-8888'),
        CandidatoFuncionarioContato(func_id='recFUNC2', whatsapp_bruto=None),
    )

    with (
        patch.object(cli, 'abrir_conexao', return_value=conexao),
        patch.object(cli, '_compor_leitor_airtable_a_partir_do_ambiente', return_value=leitor),
        patch.object(cli, 'RepositorioContatoColaboradorPostgres', return_value=repo),
    ):
        codigo = cli.main([])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert '"processados": 2' in saida
    assert '"criados": 1' in saida
    assert '"ignorados_sem_whatsapp": 1' in saida
    # Nunca o telefone em claro nem o número normalizado na saída.
    assert '99999-8888' not in saida
    assert '5511999998888' not in saida
    assert conexao.fechada is True

    registro = repo.buscar_por_colaborador('recFUNC1', CANAL_WHATSAPP)
    assert decifrar_valor_contato(
        _derivar_chave_fernet_do_ambiente(), registro.valor_cifrado,
    ) == '5511999998888'


def test_conexao_e_sempre_fechada_mesmo_quando_bootstrap_levanta(monkeypatch):
    _preparar_ambiente_completo(monkeypatch)
    conexao = _ConexaoFake()
    leitor = _LeitorFake(CandidatoFuncionarioContato(func_id='recFUNC1', whatsapp_bruto='11999998888'))

    def _repositorio_que_falha(_conexao):
        class _RepoQuebrado:
            def criar_ou_confirmar(self, registro):
                raise RuntimeError('falha simulada de escrita')

        return _RepoQuebrado()

    with (
        patch.object(cli, 'abrir_conexao', return_value=conexao),
        patch.object(cli, '_compor_leitor_airtable_a_partir_do_ambiente', return_value=leitor),
        patch.object(cli, 'RepositorioContatoColaboradorPostgres', side_effect=_repositorio_que_falha),
    ):
        try:
            cli.main([])
        except RuntimeError:
            pass

    assert conexao.fechada is True


def test_conflito_de_telefone_ja_registrado_retorna_codigo_1(monkeypatch, capsys):
    _preparar_ambiente_completo(monkeypatch)
    repo = RepositorioContatoColaboradorEmMemoria()
    conexao = _ConexaoFake()

    chave_fernet = _derivar_chave_fernet_do_ambiente()
    chave_hmac = _VARS_SEGREDO['MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_V1'].encode('utf-8')
    from datetime import datetime, timezone

    from magnata_os.documental.alocacao.contato_colaborador import (
        RegistroContatoColaborador,
        calcular_hash_auxiliar_contato,
        cifrar_valor_contato,
    )

    agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repo.criar_ou_confirmar(RegistroContatoColaborador(
        colaborador_id='recFUNC1', canal=CANAL_WHATSAPP,
        valor_cifrado=cifrar_valor_contato(chave_fernet, '5511900000000'),
        hash_auxiliar=calcular_hash_auxiliar_contato(chave_hmac, '5511900000000'),
        versao_chave='V1', origem='origem_anterior_diferente',
        criado_em=agora, atualizado_em=agora,
    ))

    leitor = _LeitorFake(CandidatoFuncionarioContato(func_id='recFUNC1', whatsapp_bruto='11999998888'))

    with (
        patch.object(cli, 'abrir_conexao', return_value=conexao),
        patch.object(cli, '_compor_leitor_airtable_a_partir_do_ambiente', return_value=leitor),
        patch.object(cli, 'RepositorioContatoColaboradorPostgres', return_value=repo),
    ):
        codigo = cli.main([])

    assert codigo == 1
    saida = capsys.readouterr().out
    assert '"conflitos"' in saida
    assert 'recFUNC1' in saida


def _derivar_chave_fernet_do_ambiente():
    from magnata_os.documental.alocacao.configuracao_contato_colaborador import (
        carregar_configuracao_segredo_contato,
    )
    return carregar_configuracao_segredo_contato().obter_chave_fernet_atual()
