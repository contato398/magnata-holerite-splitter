"""Testes de `magnata_os/autenticacao/allowlist.py` -- Airtable nunca é
tocado (nenhum import), só a variável de ambiente `MAGNATA_ADMIN_ALLOWLIST`.
E-mails 100% sintéticos."""
import pytest

from magnata_os.autenticacao.allowlist import AllowlistMalFormada, ResolvedorAllowlistAmbiente
from magnata_os.autenticacao.identidade import Perfil


def test_allowlist_vazia_nunca_reconhece_ninguem():
    resolvedor = ResolvedorAllowlistAmbiente(ambiente={})
    assert resolvedor.perfil_para_email('quemquer@exemplo.com') is None


def test_allowlist_resolve_perfil_correto():
    resolvedor = ResolvedorAllowlistAmbiente(
        ambiente={'MAGNATA_ADMIN_ALLOWLIST': 'gestor@exemplo.com:GESTOR,operador@exemplo.com:OPERACIONAL'})
    assert resolvedor.perfil_para_email('gestor@exemplo.com') == Perfil.GESTOR
    assert resolvedor.perfil_para_email('operador@exemplo.com') == Perfil.OPERACIONAL


def test_allowlist_case_insensitive_no_email():
    resolvedor = ResolvedorAllowlistAmbiente(ambiente={'MAGNATA_ADMIN_ALLOWLIST': 'Gestor@Exemplo.com:GESTOR'})
    assert resolvedor.perfil_para_email('gestor@exemplo.com') == Perfil.GESTOR


def test_email_fora_da_allowlist_devolve_none():
    resolvedor = ResolvedorAllowlistAmbiente(ambiente={'MAGNATA_ADMIN_ALLOWLIST': 'gestor@exemplo.com:GESTOR'})
    assert resolvedor.perfil_para_email('estranho@exemplo.com') is None


def test_allowlist_mal_formada_sem_dois_pontos_falha():
    with pytest.raises(AllowlistMalFormada):
        ResolvedorAllowlistAmbiente(ambiente={'MAGNATA_ADMIN_ALLOWLIST': 'gestor@exemplo.com'})


def test_allowlist_com_perfil_desconhecido_falha():
    with pytest.raises(AllowlistMalFormada):
        ResolvedorAllowlistAmbiente(ambiente={'MAGNATA_ADMIN_ALLOWLIST': 'x@exemplo.com:SUPERADMIN'})


def test_allowlist_com_email_duplicado_falha():
    with pytest.raises(AllowlistMalFormada):
        ResolvedorAllowlistAmbiente(
            ambiente={'MAGNATA_ADMIN_ALLOWLIST': 'x@exemplo.com:GESTOR,x@exemplo.com:OPERACIONAL'})
