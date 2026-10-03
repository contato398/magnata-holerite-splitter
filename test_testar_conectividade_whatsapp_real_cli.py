"""Testes do CLI de teste de conectividade WhatsApp real (missão
"TESTE DE CONECTIVIDADE WHATSAPP REAL V1"). Nenhuma chamada de rede
real -- o transporte é sempre um dublê em memória, injetado via
`compor_transporte`."""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

from scripts import testar_conectividade_whatsapp_real_cli as cli

NUMERO_VALIDO = '+5511999998888'


class _TransporteFake:
    """Dublê de `PortaTransporteWhatsapp`. Conta chamadas e registra os
    argumentos exatos recebidos -- nenhuma rede real."""

    def __init__(self, resposta=None):
        self.chamadas_enviar_texto = []
        self._resposta = resposta if resposta is not None else {'key': {'id': 'EVO-ID-123'}}

    def enviar_texto(self, *, numero, texto):
        self.chamadas_enviar_texto.append({'numero': numero, 'texto': texto})
        return self._resposta

    def enviar_video(self, **kw):  # pragma: no cover - nunca chamado por este script
        raise AssertionError('enviar_video nunca deveria ser chamado por este CLI')

    def enviar_documento(self, **kw):  # pragma: no cover - nunca chamado por este script
        raise AssertionError('enviar_documento nunca deveria ser chamado por este CLI')


def _compor_transporte_fake(transporte):
    return lambda: transporte


# ---------------------------------------------------------------------
# Validação de número -- fail-closed antes de qualquer tentativa
# ---------------------------------------------------------------------

@pytest.mark.parametrize('numero_invalido', [
    '', '123', 'abc', '+55 11 99999-8888', '11999998888abc', '+',
    '55119999988881234567',  # mais de 15 dígitos
])
def test_numero_invalido_recusa_antes_de_qualquer_tentativa(numero_invalido):
    transporte = _TransporteFake()
    with patch.object(cli, 'transporte_real_habilitado', return_value=True):
        with pytest.raises(cli.NumeroInvalidoError):
            cli.executar_teste_conectividade(
                numero=numero_invalido, texto='teste',
                compor_transporte=_compor_transporte_fake(transporte),
            )
    assert transporte.chamadas_enviar_texto == []


def test_numero_valido_com_mais_de_15_digitos_e_rejeitado():
    with pytest.raises(cli.NumeroInvalidoError):
        cli.validar_numero('1234567890123456')


def test_numero_valido_aceita_com_e_sem_sinal_de_mais():
    assert cli.validar_numero('5511999998888') == '5511999998888'
    assert cli.validar_numero('+5511999998888') == '+5511999998888'


# ---------------------------------------------------------------------
# Barreira 2 ausente -- recusa, zero tentativa de rede
# ---------------------------------------------------------------------

def test_barreira_2_ausente_recusa_sem_tentar_rede():
    transporte = _TransporteFake()
    with patch.object(cli, 'transporte_real_habilitado', return_value=False) as mock_barreira:
        with pytest.raises(cli.TransporteRealNaoHabilitadoError):
            cli.executar_teste_conectividade(
                numero=NUMERO_VALIDO, texto='teste',
                compor_transporte=_compor_transporte_fake(transporte),
            )
    mock_barreira.assert_called_once_with(autorizar_transporte_real=True)
    assert transporte.chamadas_enviar_texto == []


# ---------------------------------------------------------------------
# Barreira 3 (dry-run) vetando -- recusa mesmo com barreira 2 presente
# ---------------------------------------------------------------------

def test_barreira_3_dry_run_recusa_mesmo_com_barreira_2_presente(monkeypatch):
    # Usa a função REAL `transporte_real_habilitado` (não mockada) para
    # provar que o veto de dry-run é respeitado de ponta a ponta, não
    # só simulado -- mesmo com a barreira 2 (env var) presente.
    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', '1')
    monkeypatch.setenv('ORQUESTRADOR_DRY_RUN', 'true')
    transporte = _TransporteFake()
    with pytest.raises(cli.TransporteRealNaoHabilitadoError):
        cli.executar_teste_conectividade(
            numero=NUMERO_VALIDO, texto='teste',
            compor_transporte=_compor_transporte_fake(transporte),
        )
    assert transporte.chamadas_enviar_texto == []


def test_barreira_1_estrutural_false_recusa_mesmo_com_barreira_2_presente(monkeypatch):
    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', '1')
    monkeypatch.delenv('ORQUESTRADOR_DRY_RUN', raising=False)
    transporte = _TransporteFake()
    with pytest.raises(cli.TransporteRealNaoHabilitadoError):
        cli.executar_teste_conectividade(
            numero=NUMERO_VALIDO, texto='teste', autorizar_transporte_real=False,
            compor_transporte=_compor_transporte_fake(transporte),
        )
    assert transporte.chamadas_enviar_texto == []


# ---------------------------------------------------------------------
# As duas barreiras liberadas -- exatamente 1 chamada, args exatos
# ---------------------------------------------------------------------

def test_as_duas_barreiras_liberadas_chama_enviar_texto_exatamente_uma_vez(monkeypatch):
    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', '1')
    monkeypatch.delenv('ORQUESTRADOR_DRY_RUN', raising=False)
    transporte = _TransporteFake(resposta={'key': {'id': 'EVO-ID-999'}})

    identificador = cli.executar_teste_conectividade(
        numero=NUMERO_VALIDO, texto='Teste de conectividade Magnata OS — ignore esta mensagem',
        compor_transporte=_compor_transporte_fake(transporte),
    )

    assert len(transporte.chamadas_enviar_texto) == 1
    assert transporte.chamadas_enviar_texto[0] == {
        'numero': NUMERO_VALIDO,
        'texto': 'Teste de conectividade Magnata OS — ignore esta mensagem',
    }
    assert identificador == 'EVO-ID-999'


def test_barreira_2_valor_nao_exato_nao_habilita(monkeypatch):
    # '1 ' / 'true' / '01' etc. não são o valor exato '1' -- barreira 2
    # continua fechada (comportamento de `transporte_real_habilitado`,
    # não reimplementado aqui -- só exercido ponta a ponta).
    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', 'true')
    monkeypatch.delenv('ORQUESTRADOR_DRY_RUN', raising=False)
    transporte = _TransporteFake()
    with pytest.raises(cli.TransporteRealNaoHabilitadoError):
        cli.executar_teste_conectividade(
            numero=NUMERO_VALIDO, texto='teste',
            compor_transporte=_compor_transporte_fake(transporte),
        )
    assert transporte.chamadas_enviar_texto == []


# ---------------------------------------------------------------------
# Resposta sem ID externo confirmável -- identificador vazio, nunca inventado
# ---------------------------------------------------------------------

def test_resposta_sem_id_externo_retorna_string_vazia(monkeypatch):
    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', '1')
    monkeypatch.delenv('ORQUESTRADOR_DRY_RUN', raising=False)
    transporte = _TransporteFake(resposta={'status': 'ok'})

    identificador = cli.executar_teste_conectividade(
        numero=NUMERO_VALIDO, texto='teste',
        compor_transporte=_compor_transporte_fake(transporte),
    )
    assert identificador == ''


# ---------------------------------------------------------------------
# Número nunca em texto puro na saída/log -- só mascarado
# ---------------------------------------------------------------------

def test_mascarar_numero_mantem_so_os_2_ultimos_digitos():
    assert cli.mascarar_numero('+5511999998888') == '***********88'
    assert cli.mascarar_numero('') == '****'
    assert cli.mascarar_numero(None) == '****'


def test_numero_completo_nunca_aparece_em_texto_puro_na_saida_capturada(monkeypatch, caplog):
    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', '1')
    monkeypatch.delenv('ORQUESTRADOR_DRY_RUN', raising=False)
    transporte = _TransporteFake(resposta={'key': {'id': 'EVO-ID-777'}})

    buffer = io.StringIO()
    with caplog.at_level('INFO'):
        with redirect_stdout(buffer):
            with patch.object(cli, 'compor_transporte_evolution_real', _compor_transporte_fake(transporte)):
                codigo = cli.main(['--numero', NUMERO_VALIDO, '--texto', 'teste'])

    assert codigo == 0
    saida_stdout = buffer.getvalue()
    saida_log = caplog.text
    assert NUMERO_VALIDO not in saida_stdout
    assert NUMERO_VALIDO not in saida_log
    assert '5511999998888' not in saida_stdout
    assert '5511999998888' not in saida_log
    # O identificador externo (evidência), não o número, é o que aparece.
    assert 'EVO-ID-777' in saida_stdout


def test_numero_invalido_via_main_recusa_com_saida_diferente_de_zero(capsys):
    codigo = cli.main(['--numero', 'abc'])
    assert codigo == 1
    saida_erro = capsys.readouterr().err
    assert 'abc' not in saida_erro


def test_barreira_ausente_via_main_recusa_com_saida_diferente_de_zero(monkeypatch, capsys):
    monkeypatch.delenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', raising=False)
    codigo = cli.main(['--numero', NUMERO_VALIDO])
    assert codigo == 1
    assert 'não habilitado' in capsys.readouterr().err
