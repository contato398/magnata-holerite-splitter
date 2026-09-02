"""Testes de `magnata_os/autenticacao/provedor_google_oidc.py` -- SEM
NENHUMA chamada de rede real, SEM chave pública do Google real. Todo
verificador é `Mock()`/callable fake injetado."""
import pytest

from magnata_os.autenticacao.provedor_google_oidc import (
    EmailNaoVerificadoPeloGoogle,
    GoogleClientIdAusente,
    TokenGoogleInvalido,
    verificar_id_token_google,
)

_CLIENT_ID = 'client-id-sintetico.apps.googleusercontent.com'


def _verificador_ok(email='pessoa@exemplo.com', email_verified=True):
    def _v(token, transporte, audience):
        assert audience == _CLIENT_ID
        return {'email': email, 'email_verified': email_verified, 'sub': 'sub-123'}
    return _v


def test_token_valido_devolve_identidade_verificada_com_sub():
    identidade = verificar_id_token_google(
        'token-fake', client_id=_CLIENT_ID, verificador=_verificador_ok())
    assert identidade.email == 'pessoa@exemplo.com'
    assert identidade.sub == 'sub-123'


def test_token_sem_sub_falha():
    from magnata_os.autenticacao.provedor_google_oidc import ClaimsGoogleIncompletos

    def _v(token, transporte, audience):
        return {'email': 'pessoa@exemplo.com', 'email_verified': True}  # sem 'sub'

    with pytest.raises(ClaimsGoogleIncompletos):
        verificar_id_token_google('token-fake', client_id=_CLIENT_ID, verificador=_v)


def test_client_id_ausente_falha_sem_chamar_verificador():
    chamado = []

    def _v(token, transporte, audience):
        chamado.append(True)
        raise AssertionError('nunca deveria ser chamado')

    with pytest.raises(GoogleClientIdAusente):
        verificar_id_token_google('token-fake', client_id=None, verificador=_v, ambiente={})
    assert chamado == []


def test_token_invalido_propaga_erro_sanitizado():
    def _v(token, transporte, audience):
        raise ValueError('assinatura invalida, token cru: eyJhbGciOi...')  # nunca deveria vazar

    with pytest.raises(TokenGoogleInvalido) as excinfo:
        verificar_id_token_google('token-fake', client_id=_CLIENT_ID, verificador=_v)
    assert 'eyJhbGciOi' not in str(excinfo.value)  # token bruto nunca vaza na mensagem


def test_email_nao_verificado_pelo_google_e_recusado():
    with pytest.raises(EmailNaoVerificadoPeloGoogle):
        verificar_id_token_google(
            'token-fake', client_id=_CLIENT_ID, verificador=_verificador_ok(email_verified=False))


def test_provedor_indisponivel_propaga_como_token_invalido():
    """FASE 8 -- 'indisponibilidade do provedor de identidade':
    qualquer falha do verificador (rede, timeout, chave publica
    indisponivel) vira TokenGoogleInvalido -- login recusado, nunca
    aceito por omissao (ver blueprint_login.py: nunca degrada para
    allow-all)."""
    def _v(token, transporte, audience):
        raise ConnectionError('Google indisponivel (simulado)')

    with pytest.raises(TokenGoogleInvalido):
        verificar_id_token_google('token-fake', client_id=_CLIENT_ID, verificador=_v)
