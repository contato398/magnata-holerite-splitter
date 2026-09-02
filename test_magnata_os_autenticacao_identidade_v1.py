"""Testes de `magnata_os/autenticacao/identidade.py` (fonte única de
Perfil/Sujeito/exigir_perfil) + confirmação de que os 2 shims
(`documental/modulo01/api/autorizacao.py`,
`documental/alocacao/autorizacao.py`) continuam re-exportando
EXATAMENTE os mesmos objetos, preservando 100% de compatibilidade
(missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1", FASE 0/2)."""
import pytest

from magnata_os.autenticacao.identidade import Perfil, PermissaoNegada, Sujeito, exigir_perfil


def test_sujeito_construido_so_com_perfil_continua_funcionando():
    sujeito = Sujeito(Perfil.GESTOR)  # posicional -- compatibilidade retroativa
    assert sujeito.perfil == Perfil.GESTOR
    assert sujeito.sujeito_id is None
    assert sujeito.email is None
    assert sujeito.autenticado_por is None


def test_sujeito_com_identidade_completa():
    sujeito = Sujeito(
        perfil=Perfil.GESTOR, sujeito_id='sub-123', email='gestor@exemplo.com', autenticado_por='google_oidc')
    assert sujeito.email == 'gestor@exemplo.com'
    assert sujeito.autenticado_por == 'google_oidc'


def test_exigir_perfil_aceita_quando_permitido():
    exigir_perfil(Sujeito(Perfil.GESTOR), frozenset({Perfil.GESTOR}))  # nunca levanta


def test_exigir_perfil_recusa_quando_nao_permitido():
    with pytest.raises(PermissaoNegada):
        exigir_perfil(Sujeito(Perfil.OPERACIONAL), frozenset({Perfil.GESTOR}))


def test_exigir_perfil_aceita_classe_de_erro_customizada():
    class ErroCustomizado(Exception):
        pass

    with pytest.raises(ErroCustomizado):
        exigir_perfil(Sujeito(Perfil.OPERACIONAL), frozenset({Perfil.GESTOR}), classe_erro=ErroCustomizado)


# ============================================================================
# Compatibilidade dos 2 shims -- mesmos objetos, nao so mesma forma
# ============================================================================

def test_shim_modulo01_reexporta_os_mesmos_objetos():
    from magnata_os.documental.modulo01.api.autorizacao import Perfil as P1
    from magnata_os.documental.modulo01.api.autorizacao import Sujeito as S1
    assert P1 is Perfil
    assert S1 is Sujeito


def test_shim_alocacao_reexporta_os_mesmos_objetos():
    from magnata_os.documental.alocacao.autorizacao import Perfil as P2
    from magnata_os.documental.alocacao.autorizacao import Sujeito as S2
    assert P2 is Perfil
    assert S2 is Sujeito


def test_shim_modulo01_exigir_perfil_levanta_seu_proprio_permissaonegada():
    from magnata_os.documental.modulo01.api.autorizacao import exigir_perfil as exigir_modulo01
    from magnata_os.documental.modulo01.api.erros import ApiError
    from magnata_os.documental.modulo01.api.erros import PermissaoNegada as PN_Modulo01

    with pytest.raises(PN_Modulo01) as excinfo:
        exigir_modulo01(Sujeito(Perfil.OPERACIONAL), frozenset({Perfil.GESTOR}))
    # continua sendo um ApiError de verdade -- codigo/status_http preservados
    assert isinstance(excinfo.value, ApiError)
    assert excinfo.value.codigo == 'PERMISSAO_NEGADA'
    assert excinfo.value.status_http == 403


def test_shim_alocacao_exigir_perfil_levanta_permissaonegada_base():
    from magnata_os.documental.alocacao.autorizacao import PermissaoNegada as PN_Alocacao
    from magnata_os.documental.alocacao.autorizacao import exigir_perfil as exigir_alocacao

    assert PN_Alocacao is PermissaoNegada
    with pytest.raises(PermissaoNegada):
        exigir_alocacao(Sujeito(Perfil.OPERACIONAL), frozenset({Perfil.GESTOR}))
