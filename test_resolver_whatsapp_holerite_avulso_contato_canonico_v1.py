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
    construir_resolvedor_whatsapp_holerite_avulso_contato_canonico_v1,
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


# ---------------------------------------------------------------------
# Fábrica reutilizável -- resolve o risco de "conexão nova por chamada"
# registrado em pacote-autorizacao-app-py.md, item 6.
# ---------------------------------------------------------------------

def test_resolvedor_composto_resolve_varios_funcionarios_sem_reabrir_nada():
    """Mesmo repositório/conexão injetado UMA VEZ serve N chamadas --
    prova de que a fábrica nunca reconstrói/reabre nada por chamada."""
    repo = _repositorio_com_contato('recFUNC1', '5511999998888')
    agora = datetime(2026, 10, 3, tzinfo=timezone.utc)
    repo.criar_ou_confirmar(RegistroContatoColaborador(
        colaborador_id='recFUNC2', canal=CANAL_WHATSAPP,
        valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, '5511988887777'),
        hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, '5511988887777'),
        versao_chave='v1', origem='teste', criado_em=agora, atualizado_em=agora,
    ))

    resolvedor = construir_resolvedor_whatsapp_holerite_avulso_contato_canonico_v1(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, habilitado=True,
    )

    assert resolvedor('recFUNC1') == '5511999998888'
    assert resolvedor('recFUNC2') == '5511988887777'
    assert resolvedor('recFUNC1') == '5511999998888'  # chamada repetida -- mesmo resultado, mesmo objeto


def test_resolvedor_composto_respeita_gate_desabilitado_em_todas_as_chamadas():
    repo = _repositorio_com_contato('recFUNC1', '5511999998888')

    resolvedor = construir_resolvedor_whatsapp_holerite_avulso_contato_canonico_v1(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, habilitado=False,
    )

    assert resolvedor('recFUNC1') is None
    assert resolvedor('recFUNC1') is None


def test_resolvedor_composto_e_funcao_pura_reutilizavel_do_mesmo_objeto():
    """A fábrica devolve uma função -- não um novo objeto repositório/
    conexão por chamada. Chamar o resolvedor N vezes nunca invoca
    `construir_resolvedor_...` de novo nem reconstrói `repositorio`."""
    repo = _repositorio_com_contato('recFUNC1', '5511999998888')
    chamadas_buscar = []
    buscar_original = repo.buscar_por_colaborador

    def _buscar_instrumentado(colaborador_id, canal):
        chamadas_buscar.append(colaborador_id)
        return buscar_original(colaborador_id, canal)

    repo.buscar_por_colaborador = _buscar_instrumentado

    resolvedor = construir_resolvedor_whatsapp_holerite_avulso_contato_canonico_v1(
        repositorio=repo, chave_fernet=_CHAVE_FERNET, habilitado=True,
    )
    resolvedor('recFUNC1')
    resolvedor('recFUNC1')
    resolvedor('recFUNC1')

    # 3 chamadas ao resolvedor -> 3 buscas no MESMO repositório, nunca
    # um repositório/conexão novo por chamada.
    assert chamadas_buscar == ['recFUNC1', 'recFUNC1', 'recFUNC1']


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
