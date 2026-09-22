"""Testes de `bootstrap_contato_colaborador_airtable.py` -- mesmo
padrão de `test_bootstrap_identidade_colaborador_airtable.py`. Fonte
sempre um fake/mock -- Airtable real nunca executado nesta sessão."""
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RepositorioContatoColaboradorEmMemoria,
    decifrar_valor_contato,
)
from magnata_os.documental.importacao_lote.adapters.bootstrap_contato_colaborador_airtable import (
    CandidatoFuncionarioContato,
    executar_bootstrap_contato_colaborador_whatsapp,
)

_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-bootstrap-teste'
_RELOGIO_FIXO = lambda: datetime(2026, 9, 21, tzinfo=timezone.utc)  # noqa: E731


class _FonteFake:
    def __init__(self, *candidatos):
        self._candidatos = candidatos

    def listar_funcionarios_contato(self):
        return list(self._candidatos)


def test_bootstrap_cria_contato_para_cada_whatsapp_valido():
    fonte = _FonteFake(
        CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='(11) 99999-8888'),
        CandidatoFuncionarioContato(func_id='func_2', whatsapp_bruto='11988887777'),
    )
    repo = RepositorioContatoColaboradorEmMemoria()

    resultado = executar_bootstrap_contato_colaborador_whatsapp(
        fonte, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    assert resultado.processados == 2
    assert resultado.criados == 2
    assert resultado.ja_existentes == 0
    assert resultado.ignorados_sem_whatsapp == 0
    assert resultado.ignorados_invalidos == 0
    assert resultado.conflitos == ()
    assert len(repo.listar_todos()) == 2

    registro1 = repo.buscar_por_colaborador('func_1', CANAL_WHATSAPP)
    assert decifrar_valor_contato(_CHAVE_FERNET, registro1.valor_cifrado) == '5511999998888'


def test_bootstrap_ignora_candidatos_sem_whatsapp():
    fonte = _FonteFake(
        CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto=None),
        CandidatoFuncionarioContato(func_id='func_2', whatsapp_bruto=''),
    )
    repo = RepositorioContatoColaboradorEmMemoria()

    resultado = executar_bootstrap_contato_colaborador_whatsapp(
        fonte, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    assert resultado.processados == 2
    assert resultado.ignorados_sem_whatsapp == 2
    assert resultado.criados == 0
    assert len(repo.listar_todos()) == 0


def test_bootstrap_ignora_whatsapp_nao_normalizavel_como_invalido():
    fonte = _FonteFake(CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='123'))
    repo = RepositorioContatoColaboradorEmMemoria()

    resultado = executar_bootstrap_contato_colaborador_whatsapp(
        fonte, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    assert resultado.ignorados_invalidos == 1
    assert resultado.criados == 0
    assert len(repo.listar_todos()) == 0


def test_bootstrap_e_idempotente_ao_rodar_duas_vezes():
    fonte = _FonteFake(CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='11999998888'))
    repo = RepositorioContatoColaboradorEmMemoria()

    r1 = executar_bootstrap_contato_colaborador_whatsapp(
        fonte, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )
    r2 = executar_bootstrap_contato_colaborador_whatsapp(
        fonte, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    assert r1.criados == 1
    assert r2.criados == 0
    assert r2.ja_existentes == 1
    assert len(repo.listar_todos()) == 1


def test_bootstrap_reporta_conflito_sem_abortar_os_demais():
    """func_1 tem telefone alterado entre duas fontes (simulado por 2
    rodadas) -- conflito reportado, mas func_2 (novo, sem conflito)
    ainda é processado normalmente na mesma rodada."""
    repo = RepositorioContatoColaboradorEmMemoria()
    executar_bootstrap_contato_colaborador_whatsapp(
        _FonteFake(CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='11999998888')),
        repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    fonte_com_mudanca = _FonteFake(
        CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='11988887777'),  # mudou
        CandidatoFuncionarioContato(func_id='func_2', whatsapp_bruto='11977776666'),  # novo
    )
    resultado = executar_bootstrap_contato_colaborador_whatsapp(
        fonte_com_mudanca, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    assert resultado.processados == 2
    assert len(resultado.conflitos) == 1
    assert resultado.conflitos[0].func_id_tentativa == 'func_1'
    assert resultado.criados == 1  # func_2
    # func_1 continua com o valor ORIGINAL -- nunca sobrescrito.
    registro_func1 = repo.buscar_por_colaborador('func_1', CANAL_WHATSAPP)
    assert decifrar_valor_contato(_CHAVE_FERNET, registro_func1.valor_cifrado) == '5511999998888'


def test_bootstrap_nunca_persiste_whatsapp_em_claro():
    fonte = _FonteFake(CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='11999998888'))
    repo = RepositorioContatoColaboradorEmMemoria()

    executar_bootstrap_contato_colaborador_whatsapp(
        fonte, repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )

    registro = repo.buscar_por_colaborador('func_1', CANAL_WHATSAPP)
    assert b'5511999998888' not in registro.valor_cifrado
    assert '5511999998888' not in registro.hash_auxiliar


def test_bootstrap_rejeita_chave_fernet_vazia():
    with pytest.raises(ValueError):
        executar_bootstrap_contato_colaborador_whatsapp(
            _FonteFake(), RepositorioContatoColaboradorEmMemoria(), b'', _CHAVE_HMAC, 'v1',
        )


def test_bootstrap_rejeita_chave_hmac_vazia():
    with pytest.raises(ValueError):
        executar_bootstrap_contato_colaborador_whatsapp(
            _FonteFake(), RepositorioContatoColaboradorEmMemoria(), _CHAVE_FERNET, b'', 'v1',
        )


def test_bootstrap_rejeita_versao_chave_vazia():
    with pytest.raises(ValueError):
        executar_bootstrap_contato_colaborador_whatsapp(
            _FonteFake(), RepositorioContatoColaboradorEmMemoria(), _CHAVE_FERNET, _CHAVE_HMAC, '',
        )


def test_bootstrap_pode_rodar_sob_versao_nova_sem_tocar_versao_existente():
    """Rotação: backfill sob 'v2' nunca colide com a linha já
    persistida sob 'v1' para outro colaborador -- cada linha carrega
    sua própria versao_chave."""
    repo = RepositorioContatoColaboradorEmMemoria()
    executar_bootstrap_contato_colaborador_whatsapp(
        _FonteFake(CandidatoFuncionarioContato(func_id='func_1', whatsapp_bruto='11999998888')),
        repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v1', relogio=_RELOGIO_FIXO,
    )
    executar_bootstrap_contato_colaborador_whatsapp(
        _FonteFake(CandidatoFuncionarioContato(func_id='func_2', whatsapp_bruto='11988887777')),
        repo, _CHAVE_FERNET, _CHAVE_HMAC, 'v2', relogio=_RELOGIO_FIXO,
    )
    assert repo.buscar_por_colaborador('func_1', CANAL_WHATSAPP).versao_chave == 'v1'
    assert repo.buscar_por_colaborador('func_2', CANAL_WHATSAPP).versao_chave == 'v2'


def test_modulo_bootstrap_nunca_importa_app_py():
    import ast
    import inspect

    import magnata_os.documental.importacao_lote.adapters.bootstrap_contato_colaborador_airtable as modulo
    arvore = ast.parse(inspect.getsource(modulo))
    modulos_importados = {
        node.module for node in ast.walk(arvore) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name for node in ast.walk(arvore) if isinstance(node, ast.Import) for alias in node.names
    }
    assert not any(m == 'app' or (m or '').startswith('app.') for m in modulos_importados if m)
