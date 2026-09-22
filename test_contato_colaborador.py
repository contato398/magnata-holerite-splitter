"""Testes de `contato_colaborador.py` (Contato Canônico de Colaborador
V1) -- domínio puro: dataclass, normalização, cifragem/decifragem,
Protocol/EmMemoria, e a porta de resolução fail-closed."""
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    ConflitoContatoColaborador,
    ContatoColaboradorDescriptografiaFalhou,
    RegistroContatoColaborador,
    RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
    decifrar_valor_contato,
    normalizar_numero_whatsapp_v1,
    resolver_contato_colaborador_para_ordem,
)

AGORA = datetime(2026, 9, 21, tzinfo=timezone.utc)
_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-teste'


def _registro(colaborador_id='colab-1', canal=CANAL_WHATSAPP, numero='5511999998888', versao='v1'):
    valor_cifrado = cifrar_valor_contato(_CHAVE_FERNET, numero)
    hash_auxiliar = calcular_hash_auxiliar_contato(_CHAVE_HMAC, numero)
    return RegistroContatoColaborador(
        colaborador_id=colaborador_id, canal=canal, valor_cifrado=valor_cifrado,
        hash_auxiliar=hash_auxiliar, versao_chave=versao, origem='teste',
        criado_em=AGORA, atualizado_em=AGORA,
    )


# ---------------------------------------------------------------------
# Normalização pura -- sem import de app.py.
# ---------------------------------------------------------------------

@pytest.mark.parametrize('bruto,esperado', [
    ('(11) 99999-8888', '5511999998888'),
    ('11999998888', '5511999998888'),
    ('5511999998888', '5511999998888'),
    ('+55 11 99999-8888', '5511999998888'),
    ('1133334444', '551133334444'),
    (None, None),
    ('', None),
    ('   ', None),
    ('123', None),
    ('55123', None),
    ('551199999888812345', None),
])
def test_normalizar_numero_whatsapp_v1(bruto, esperado):
    assert normalizar_numero_whatsapp_v1(bruto) == esperado


def test_modulo_nao_importa_app_py():
    """Auditoria estática mínima: `app.py` é legado protegido -- este
    módulo nunca cria dependência de import contra ele."""
    import ast
    import inspect

    import magnata_os.documental.alocacao.contato_colaborador as modulo
    arvore = ast.parse(inspect.getsource(modulo))
    modulos_importados = {
        node.module for node in ast.walk(arvore) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name for node in ast.walk(arvore) if isinstance(node, ast.Import) for alias in node.names
    }
    assert not any(m == 'app' or (m or '').startswith('app.') for m in modulos_importados if m)


# ---------------------------------------------------------------------
# Cifragem/decifragem.
# ---------------------------------------------------------------------

def test_cifrar_e_decifrar_roundtrip():
    cifrado = cifrar_valor_contato(_CHAVE_FERNET, '5511999998888')
    assert isinstance(cifrado, bytes)
    assert b'5511999998888' not in cifrado  # nunca em claro no token
    assert decifrar_valor_contato(_CHAVE_FERNET, cifrado) == '5511999998888'


def test_decifrar_com_chave_errada_falha_fail_closed():
    cifrado = cifrar_valor_contato(_CHAVE_FERNET, '5511999998888')
    outra_chave = Fernet.generate_key()
    with pytest.raises(ContatoColaboradorDescriptografiaFalhou):
        decifrar_valor_contato(outra_chave, cifrado)


def test_decifrar_token_corrompido_falha_fail_closed():
    with pytest.raises(ContatoColaboradorDescriptografiaFalhou):
        decifrar_valor_contato(_CHAVE_FERNET, b'token-corrompido-nao-e-fernet')


def test_cifrar_mesmo_valor_duas_vezes_produz_tokens_diferentes_mas_hash_igual():
    """Fernet inclui nonce/timestamp -- tokens diferem; a deduplicação
    nunca compara valor_cifrado, sempre hash_auxiliar (determinístico)."""
    c1 = cifrar_valor_contato(_CHAVE_FERNET, '5511999998888')
    c2 = cifrar_valor_contato(_CHAVE_FERNET, '5511999998888')
    assert c1 != c2
    assert decifrar_valor_contato(_CHAVE_FERNET, c1) == decifrar_valor_contato(_CHAVE_FERNET, c2)
    h1 = calcular_hash_auxiliar_contato(_CHAVE_HMAC, '5511999998888')
    h2 = calcular_hash_auxiliar_contato(_CHAVE_HMAC, '5511999998888')
    assert h1 == h2


def test_hash_auxiliar_e_deterministico_e_nao_reversivel_por_inspecao():
    h = calcular_hash_auxiliar_contato(_CHAVE_HMAC, '5511999998888')
    assert h == calcular_hash_auxiliar_contato(_CHAVE_HMAC, '5511999998888')
    assert '5511999998888' not in h


def test_cifrar_rejeita_valor_vazio():
    with pytest.raises(ValueError):
        cifrar_valor_contato(_CHAVE_FERNET, '')


def test_cifrar_rejeita_chave_vazia():
    with pytest.raises(ValueError):
        cifrar_valor_contato(b'', '5511999998888')


# ---------------------------------------------------------------------
# Dataclass -- validação fail-closed.
# ---------------------------------------------------------------------

def test_registro_rejeita_colaborador_id_vazio():
    with pytest.raises(ValueError):
        _registro(colaborador_id='')


def test_registro_rejeita_valor_cifrado_vazio():
    with pytest.raises(ValueError):
        RegistroContatoColaborador(
            colaborador_id='c1', canal=CANAL_WHATSAPP, valor_cifrado=b'',
            hash_auxiliar='h', versao_chave='v1', origem='teste',
            criado_em=AGORA, atualizado_em=AGORA,
        )


# ---------------------------------------------------------------------
# RepositorioContatoColaboradorEmMemoria -- contato válido / duplicado /
# conflitante / replay.
# ---------------------------------------------------------------------

def test_criar_ou_confirmar_insere_quando_ausente():
    repo = RepositorioContatoColaboradorEmMemoria()
    registro = _registro()
    persistido, criado = repo.criar_ou_confirmar(registro)
    assert criado is True
    assert persistido == registro


def test_criar_ou_confirmar_e_idempotente_mesmo_valor_replay():
    """Replay: reprocessar o MESMO registro (mesmo colaborador_id,
    canal, hash_auxiliar) nunca cria uma segunda linha nem levanta
    erro."""
    repo = RepositorioContatoColaboradorEmMemoria()
    registro = _registro()
    repo.criar_ou_confirmar(registro)
    persistido2, criado2 = repo.criar_ou_confirmar(registro)
    assert criado2 is False
    assert persistido2 == registro
    assert len(repo.listar_todos()) == 1


def test_criar_ou_confirmar_levanta_conflito_quando_numero_diferente():
    """Telefone alterado para o MESMO colaborador_id/canal, sem
    reconciliação explícita -- fail-closed, nunca sobrescreve."""
    repo = RepositorioContatoColaboradorEmMemoria()
    repo.criar_ou_confirmar(_registro(numero='5511999998888'))
    with pytest.raises(ConflitoContatoColaborador) as exc_info:
        repo.criar_ou_confirmar(_registro(numero='5511988887777'))
    assert exc_info.value.colaborador_id == 'colab-1'
    assert exc_info.value.canal == CANAL_WHATSAPP
    # Nunca vaza valor em claro na exceção.
    assert '5511999998888' not in str(exc_info.value)
    assert '5511988887777' not in str(exc_info.value)
    assert len(repo.listar_todos()) == 1


def test_canais_diferentes_para_o_mesmo_colaborador_nao_conflitam():
    repo = RepositorioContatoColaboradorEmMemoria()
    repo.criar_ou_confirmar(_registro(canal='whatsapp'))
    _persistido, criado = repo.criar_ou_confirmar(_registro(canal='email', numero='5511977776666'))
    assert criado is True
    assert len(repo.listar_todos()) == 2


def test_buscar_por_colaborador_ausente_devolve_none():
    repo = RepositorioContatoColaboradorEmMemoria()
    assert repo.buscar_por_colaborador('inexistente', CANAL_WHATSAPP) is None


# ---------------------------------------------------------------------
# resolver_contato_colaborador_para_ordem -- fail-closed: válido /
# ausente / inválido (descriptografia falha).
# ---------------------------------------------------------------------

def test_resolver_contato_valido_devolve_numero_normalizado():
    repo = RepositorioContatoColaboradorEmMemoria()
    repo.criar_ou_confirmar(_registro(colaborador_id='colab-2', numero='5511999998888'))
    resultado = resolver_contato_colaborador_para_ordem(repo, 'colab-2', CANAL_WHATSAPP, _CHAVE_FERNET)
    assert resultado == '5511999998888'


def test_resolver_contato_ausente_devolve_none():
    repo = RepositorioContatoColaboradorEmMemoria()
    assert resolver_contato_colaborador_para_ordem(repo, 'colab-inexistente', CANAL_WHATSAPP, _CHAVE_FERNET) is None


def test_resolver_com_colaborador_id_vazio_devolve_none():
    repo = RepositorioContatoColaboradorEmMemoria()
    assert resolver_contato_colaborador_para_ordem(repo, '', CANAL_WHATSAPP, _CHAVE_FERNET) is None


def test_resolver_com_chave_errada_devolve_none_nunca_propaga():
    """Contato 'inválido' do ponto de vista de resolução: chave de
    decifragem errada -- fail-closed, `None`, nunca uma exceção que
    derrubaria o resolvedor de Ordem para todos os clientes."""
    repo = RepositorioContatoColaboradorEmMemoria()
    repo.criar_ou_confirmar(_registro(colaborador_id='colab-3'))
    chave_errada = Fernet.generate_key()
    assert resolver_contato_colaborador_para_ordem(repo, 'colab-3', CANAL_WHATSAPP, chave_errada) is None


def test_resolver_e_replay_e_deterministico():
    """Chamar a resolução duas vezes para o mesmo colaborador/canal
    devolve sempre o mesmo destinatário -- pré-condição para
    `event_id` estável entre re-execuções (idempotência a montante)."""
    repo = RepositorioContatoColaboradorEmMemoria()
    repo.criar_ou_confirmar(_registro(colaborador_id='colab-4', numero='5511999998888'))
    r1 = resolver_contato_colaborador_para_ordem(repo, 'colab-4', CANAL_WHATSAPP, _CHAVE_FERNET)
    r2 = resolver_contato_colaborador_para_ordem(repo, 'colab-4', CANAL_WHATSAPP, _CHAVE_FERNET)
    assert r1 == r2 == '5511999998888'
