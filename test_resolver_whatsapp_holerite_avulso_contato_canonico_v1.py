"""Testes de `resolver_whatsapp_holerite_avulso_contato_canonico_v1.py`
-- fonte sempre `RepositorioContatoColaboradorEmMemoria` (fake de
teste), nunca Postgres real."""
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RegistroContatoColaborador,
    RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
)
from magnata_os.documental.alocacao.resolver_whatsapp_holerite_avulso_contato_canonico_v1 import (
    resolver_whatsapp_holerite_avulso_via_contato_canonico,
)

_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-resolver-holerite-avulso-teste'


def _repositorio_com_contato(func_id: str, whatsapp_normalizado: str) -> RepositorioContatoColaboradorEmMemoria:
    repo = RepositorioContatoColaboradorEmMemoria()
    agora = datetime(2026, 10, 3, tzinfo=timezone.utc)
    repo.criar_ou_confirmar(RegistroContatoColaborador(
        colaborador_id=func_id, canal=CANAL_WHATSAPP,
        valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, whatsapp_normalizado),
        hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, whatsapp_normalizado),
        versao_chave='v1', origem='teste', criado_em=agora, atualizado_em=agora,
    ))
    return repo


def test_resolve_whatsapp_quando_habilitado_e_contato_existente():
    repo = _repositorio_com_contato('recFUNC1', '5511999998888')

    resultado = resolver_whatsapp_holerite_avulso_via_contato_canonico(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, funcionario_id='recFUNC1', habilitado=True,
    )

    assert resultado == '5511999998888'


def test_nunca_resolve_quando_gate_desabilitado_mesmo_com_contato_existente():
    repo = _repositorio_com_contato('recFUNC1', '5511999998888')

    resultado = resolver_whatsapp_holerite_avulso_via_contato_canonico(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, funcionario_id='recFUNC1', habilitado=False,
    )

    assert resultado is None


def test_retorna_none_quando_contato_nao_existe():
    repo = RepositorioContatoColaboradorEmMemoria()

    resultado = resolver_whatsapp_holerite_avulso_via_contato_canonico(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, funcionario_id='recFUNC_SEM_CONTATO', habilitado=True,
    )

    assert resultado is None


def test_retorna_none_quando_funcionario_id_vazio():
    repo = RepositorioContatoColaboradorEmMemoria()

    assert resolver_whatsapp_holerite_avulso_via_contato_canonico(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, funcionario_id='', habilitado=True,
    ) is None
    assert resolver_whatsapp_holerite_avulso_via_contato_canonico(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, funcionario_id=None, habilitado=True,
    ) is None


def test_retorna_none_quando_chave_fernet_errada_nunca_levanta():
    """Chave errada -> descriptografia falha dentro de
    `resolver_contato_colaborador_para_ordem` -> `None`, nunca uma
    exceção propagada para o chamador (app.py)."""
    repo = _repositorio_com_contato('recFUNC1', '5511999998888')
    chave_errada = Fernet.generate_key()

    resultado = resolver_whatsapp_holerite_avulso_via_contato_canonico(
        repositorio=repo, chave_fernet=chave_errada, funcionario_id='recFUNC1', habilitado=True,
    )

    assert resultado is None


def test_modulo_nao_importa_airtable_nem_app():
    import ast
    import inspect

    import magnata_os.documental.alocacao.resolver_whatsapp_holerite_avulso_contato_canonico_v1 as modulo
    arvore = ast.parse(inspect.getsource(modulo))
    modulos_importados = {
        node.module for node in ast.walk(arvore) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name for node in ast.walk(arvore) if isinstance(node, ast.Import) for alias in node.names
    }
    proibidos = {'app', 'requests', 'psycopg2', 'psycopg'}
    assert not any(
        m in proibidos or (m or '').startswith('app.') for m in modulos_importados if m
    )
