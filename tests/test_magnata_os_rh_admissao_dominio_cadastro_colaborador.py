"""Domínio do Cadastro de Colaborador PERSISTENTE V1.

Cobre: composição a partir do Kit (com/sem determinação), separação das
dimensões situacao_cadastro/local_trabalho (nunca fundidas), e o
critério de correção de local de trabalho já definido (idempotência x
recusa sem motivo x correção explícita com evento). Dados 100%
sintéticos.
"""
from datetime import datetime, timezone

import pytest

from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    CadastroColaboradorError,
    Colaborador,
    EventoCorrecaoLocalTrabalho,
    LocalTrabalhoJaDefinidoError,
    SituacaoCadastroColaborador,
    aplicar_determinacao_local_trabalho,
    compor_colaborador_a_partir_do_kit,
)
from magnata_os.rh_admissao.gatilho_admissao import (
    DadosColaboradorKitAdmissao,
    DeterminacaoLocalTrabalho,
)

CPF_SINTETICO = '900.000.000-01'
NOME_SINTETICO = 'colaborador sintetico teste'
_AGORA = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def _dados(colaborador_id='colab-1'):
    return DadosColaboradorKitAdmissao(colaborador_id, CPF_SINTETICO, NOME_SINTETICO, 'Vigia')


def _determinacao(grupo='Escala A - Dias Pares', por='operador.rh@magnataservicos.com.br', em=None):
    return DeterminacaoLocalTrabalho(grupo, por, em or _AGORA)


# ---- Colaborador: invariante situacao_cadastro <-> local_trabalho ----

def test_colaborador_aguardando_local_trabalho_exige_local_trabalho_none():
    colaborador = Colaborador(
        colaborador_id='c1', cpf=CPF_SINTETICO, nome=NOME_SINTETICO,
        situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
    )
    assert colaborador.local_trabalho is None


def test_colaborador_aguardando_com_local_trabalho_preenchido_e_invalido():
    with pytest.raises(CadastroColaboradorError):
        Colaborador(
            colaborador_id='c1', cpf=CPF_SINTETICO, nome=NOME_SINTETICO,
            situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
            local_trabalho='Escala A',
        )


def test_colaborador_completo_sem_local_trabalho_e_invalido():
    with pytest.raises(CadastroColaboradorError):
        Colaborador(
            colaborador_id='c1', cpf=CPF_SINTETICO, nome=NOME_SINTETICO,
            situacao_cadastro=SituacaoCadastroColaborador.CADASTRO_COMPLETO,
        )


def test_colaborador_como_evidencia_nunca_expoe_cpf_nem_nome():
    colaborador = Colaborador(
        colaborador_id='c1', cpf=CPF_SINTETICO, nome=NOME_SINTETICO,
        situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
    )
    evidencia = colaborador.como_evidencia()
    assert 'cpf' not in evidencia
    assert 'nome' not in evidencia


# ---- compor_colaborador_a_partir_do_kit ----

def test_compor_sem_determinacao_fica_aguardando_local_trabalho():
    colaborador = compor_colaborador_a_partir_do_kit(_dados(), None, agora=_AGORA)
    assert colaborador.situacao_cadastro == SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO
    assert colaborador.local_trabalho is None
    assert colaborador.colaborador_id == 'colab-1'


def test_compor_com_determinacao_fica_cadastro_completo():
    colaborador = compor_colaborador_a_partir_do_kit(_dados(), _determinacao(), agora=_AGORA)
    assert colaborador.situacao_cadastro == SituacaoCadastroColaborador.CADASTRO_COMPLETO
    assert colaborador.local_trabalho == 'Escala A - Dias Pares'


# ---- aplicar_determinacao_local_trabalho: completar, idempotência, recusa, correção ----

def test_aplicar_determinacao_completa_cadastro_pendente():
    pendente = compor_colaborador_a_partir_do_kit(_dados(), None, agora=_AGORA)
    atualizado, evento = aplicar_determinacao_local_trabalho(pendente, _determinacao())
    assert atualizado.situacao_cadastro == SituacaoCadastroColaborador.CADASTRO_COMPLETO
    assert atualizado.local_trabalho == 'Escala A - Dias Pares'
    assert evento is None


def test_reaplicar_mesmo_local_trabalho_e_idempotente_sem_evento():
    completo = compor_colaborador_a_partir_do_kit(_dados(), _determinacao(), agora=_AGORA)
    atualizado, evento = aplicar_determinacao_local_trabalho(
        completo, _determinacao(em=datetime(2026, 10, 1, tzinfo=timezone.utc)),
    )
    assert atualizado.local_trabalho == completo.local_trabalho
    assert atualizado.situacao_cadastro == SituacaoCadastroColaborador.CADASTRO_COMPLETO
    assert evento is None


def test_mudar_local_trabalho_ja_definido_sem_motivo_e_recusado():
    completo = compor_colaborador_a_partir_do_kit(_dados(), _determinacao(), agora=_AGORA)
    with pytest.raises(LocalTrabalhoJaDefinidoError):
        aplicar_determinacao_local_trabalho(completo, _determinacao(grupo='Escala B - Dias Impares'))


def test_mudar_local_trabalho_ja_definido_com_motivo_gera_evento_de_correcao():
    completo = compor_colaborador_a_partir_do_kit(_dados(), _determinacao(), agora=_AGORA)
    nova = _determinacao(grupo='Escala B - Dias Impares', em=datetime(2026, 10, 1, tzinfo=timezone.utc))

    atualizado, evento = aplicar_determinacao_local_trabalho(
        completo, nova, motivo_correcao='Colaborador transferido de posto',
    )

    assert atualizado.local_trabalho == 'Escala B - Dias Impares'
    assert isinstance(evento, EventoCorrecaoLocalTrabalho)
    assert evento.local_trabalho_anterior == 'Escala A - Dias Pares'
    assert evento.local_trabalho_novo == 'Escala B - Dias Impares'
    assert evento.motivo_correcao == 'Colaborador transferido de posto'


def test_evidencia_evento_correcao_nunca_expoe_cpf_nem_nome():
    completo = compor_colaborador_a_partir_do_kit(_dados(), _determinacao(), agora=_AGORA)
    _, evento = aplicar_determinacao_local_trabalho(
        completo, _determinacao(grupo='Escala B', em=datetime(2026, 10, 1, tzinfo=timezone.utc)),
        motivo_correcao='correcao teste',
    )
    evidencia = evento.como_evidencia()
    assert 'cpf' not in evidencia
    assert 'nome' not in evidencia
