"""Gatilho Kit de Admissão -> Preview/pendência de cadastro na Secullum.

Cobre: local de trabalho determinado -> intenção composta em modo
sombra; local de trabalho ausente -> pendência explícita, nunca
adivinha, nunca lança; múltiplos kits isolados entre si; idempotência
(reprocessar o mesmo kit não duplica). Dados 100% sintéticos.
"""
from datetime import datetime

import pytest

from magnata_os.rh_admissao.gatilho_admissao import (
    EVENTO_GATILHO_ADMISSAO_FALHOU,
    EVENTO_GATILHO_ADMISSAO_IDEMPOTENTE,
    EVENTO_GATILHO_ADMISSAO_PENDENTE,
    MOTIVO_LOCAL_TRABALHO_NAO_DETERMINADO,
    DadosColaboradorKitAdmissao,
    DeterminacaoLocalTrabalho,
    RegistroGatilhoAdmissaoEmMemoria,
    ResultadoGatilhoAdmissao,
    SituacaoGatilhoAdmissao,
    processar_kit_admissao,
    processar_lote_kits_admissao,
)
from magnata_os.rh_admissao.porta_secullum import ExecutorSecullumSombra

CPF_SINTETICO_1 = "900.000.000-01"
CPF_SINTETICO_2 = "900.000.000-02"
NOME_SINTETICO_1 = "colaborador sintetico um"
NOME_SINTETICO_2 = "colaborador sintetico dois"


def dados(colaborador_id="colab-1", cpf=CPF_SINTETICO_1, nome=NOME_SINTETICO_1, cargo="Vigia"):
    return DadosColaboradorKitAdmissao(colaborador_id, cpf, nome, cargo)


def determinacao(grupo="Escala A - Dias Pares", por="operador.rh@magnataservicos.com.br"):
    return DeterminacaoLocalTrabalho(grupo, por, datetime(2026, 9, 30, 10, 0, 0))


# ---- caminho feliz: local de trabalho determinado ----

def test_com_local_trabalho_determinado_compoe_intencao_em_modo_sombra():
    resultado = processar_kit_admissao(dados(), determinacao())

    assert resultado.situacao == SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA
    assert resultado.motivo_bloqueio is None
    assert resultado.resultado_secullum is not None
    assert resultado.resultado_secullum.executado is False  # sempre sombra nesta missão


def test_usa_compor_porta_secullum_com_autorizar_real_false_por_padrao(monkeypatch):
    chamadas = {}

    def _fake_compor(*, autorizar_secullum_real):
        chamadas['autorizar_secullum_real'] = autorizar_secullum_real
        return ExecutorSecullumSombra()

    import magnata_os.rh_admissao.gatilho_admissao as mod
    monkeypatch.setattr(mod, 'compor_porta_secullum', _fake_compor)

    processar_kit_admissao(dados(), determinacao())

    assert chamadas['autorizar_secullum_real'] is False


def test_intencao_carrega_grupo_escala_determinado_pela_pessoa():
    class _PortaEspiao:
        def __init__(self):
            self.intencoes = []

        def cadastrar(self, intencao):
            self.intencoes.append(intencao)
            from magnata_os.rh_admissao.porta_secullum import ResultadoAcaoSecullum
            return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=False)

    porta = _PortaEspiao()
    processar_kit_admissao(dados(), determinacao(grupo="Escala B - Dias Ímpares"), porta=porta)

    assert porta.intencoes[0].grupo_escala_id == "Escala B - Dias Ímpares"


# ---- local de trabalho ausente: pendência, nunca adivinhação ----

def test_sem_determinacao_humana_produz_pendencia_explicita(caplog):
    import logging
    with caplog.at_level(logging.INFO):
        resultado = processar_kit_admissao(dados(), None)

    assert resultado.situacao == SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO
    assert resultado.motivo_bloqueio == MOTIVO_LOCAL_TRABALHO_NAO_DETERMINADO
    assert resultado.proxima_acao
    assert resultado.resultado_secullum is None
    assert EVENTO_GATILHO_ADMISSAO_PENDENTE in caplog.text


def test_sem_determinacao_nunca_chama_a_porta_secullum():
    class _PortaQueExplode:
        def cadastrar(self, intencao):
            raise AssertionError('nunca deveria ser chamada sem local de trabalho determinado')

    resultado = processar_kit_admissao(dados(), None, porta=_PortaQueExplode())

    assert resultado.situacao == SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO


def test_determinacao_sem_grupo_escala_e_rejeitada_na_construcao():
    with pytest.raises(ValueError):
        DeterminacaoLocalTrabalho("", "operador.rh@magnataservicos.com.br", datetime(2026, 9, 30))


def test_determinacao_sem_autoria_e_rejeitada_na_construcao():
    with pytest.raises(ValueError):
        DeterminacaoLocalTrabalho("Escala A - Dias Pares", "", datetime(2026, 9, 30))


# ---- falha isolada nunca lança, nunca derruba o lote ----

def test_falha_na_porta_nunca_propaga_excecao_ao_chamador():
    class _PortaQueFalha:
        def cadastrar(self, intencao):
            raise ConnectionError("timeout sintético")

    resultado = processar_kit_admissao(dados(), determinacao(), porta=_PortaQueFalha())

    assert resultado.situacao == SituacaoGatilhoAdmissao.FALHOU
    assert resultado.erro_tipo == "ConnectionError"


def test_falha_isolada_nao_vaza_mensagem_crua_no_log(caplog):
    import logging

    class _PortaQueFalha:
        def cadastrar(self, intencao):
            raise ConnectionError("timeout com CPF no corpo da resposta")

    with caplog.at_level(logging.ERROR):
        processar_kit_admissao(dados(), determinacao(), porta=_PortaQueFalha())

    assert EVENTO_GATILHO_ADMISSAO_FALHOU in caplog.text
    assert "timeout com CPF" not in caplog.text


def test_lote_com_um_kit_falhando_nao_trava_os_demais():
    class _PortaAlternada:
        def __init__(self):
            self.chamadas = 0

        def cadastrar(self, intencao):
            self.chamadas += 1
            if intencao.colaborador_id == "colab-falha":
                raise RuntimeError("falha sintética isolada")
            from magnata_os.rh_admissao.porta_secullum import ResultadoAcaoSecullum
            return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=False)

    itens = [
        (dados(colaborador_id="colab-ok-1", cpf=CPF_SINTETICO_1, nome=NOME_SINTETICO_1), determinacao()),
        (dados(colaborador_id="colab-falha", cpf=CPF_SINTETICO_2, nome=NOME_SINTETICO_2), determinacao()),
        (dados(colaborador_id="colab-ok-2", cpf=CPF_SINTETICO_1, nome=NOME_SINTETICO_1), None),
    ]

    resultados = processar_lote_kits_admissao(itens, porta=_PortaAlternada())

    situacoes = {r.colaborador_id: r.situacao for r in resultados}
    assert situacoes["colab-ok-1"] == SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA
    assert situacoes["colab-falha"] == SituacaoGatilhoAdmissao.FALHOU
    assert situacoes["colab-ok-2"] == SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO


# ---- idempotência: reprocessar o mesmo kit não duplica ----

def test_reprocessar_mesmo_kit_com_registro_nao_chama_a_porta_de_novo():
    class _PortaContadora:
        def __init__(self):
            self.chamadas = 0

        def cadastrar(self, intencao):
            self.chamadas += 1
            from magnata_os.rh_admissao.porta_secullum import ResultadoAcaoSecullum
            return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=False, secullum_id=None)

    porta = _PortaContadora()
    registro = RegistroGatilhoAdmissaoEmMemoria()

    primeiro = processar_kit_admissao(dados(), determinacao(), porta=porta, registro=registro)
    segundo = processar_kit_admissao(dados(), determinacao(), porta=porta, registro=registro)

    assert porta.chamadas == 1
    assert primeiro.reaproveitado is False
    assert segundo.reaproveitado is True
    assert segundo.situacao == primeiro.situacao == SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA


def test_reprocessar_pendencia_com_registro_tambem_nao_duplica(caplog):
    import logging
    registro = RegistroGatilhoAdmissaoEmMemoria()

    processar_kit_admissao(dados(), None, registro=registro)
    with caplog.at_level(logging.INFO):
        segundo = processar_kit_admissao(dados(), None, registro=registro)

    assert segundo.reaproveitado is True
    assert segundo.situacao == SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO
    assert EVENTO_GATILHO_ADMISSAO_IDEMPOTENTE in caplog.text


def test_sem_registro_cada_chamada_reprocessa_de_verdade():
    class _PortaContadora:
        def __init__(self):
            self.chamadas = 0

        def cadastrar(self, intencao):
            self.chamadas += 1
            from magnata_os.rh_admissao.porta_secullum import ResultadoAcaoSecullum
            return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=False)

    porta = _PortaContadora()
    processar_kit_admissao(dados(), determinacao(), porta=porta)
    processar_kit_admissao(dados(), determinacao(), porta=porta)

    assert porta.chamadas == 2  # sem registro injetado, não há garantia de dedup


# ---- LGPD: evidência nunca carrega CPF/nome ----

def test_como_evidencia_nunca_carrega_cpf_ou_nome():
    resultado = processar_kit_admissao(dados(), determinacao())

    evidencia = resultado.como_evidencia()
    assert CPF_SINTETICO_1 not in repr(evidencia)
    assert NOME_SINTETICO_1 not in repr(evidencia)


def test_pendencia_como_evidencia_tambem_nunca_carrega_cpf_ou_nome():
    resultado = processar_kit_admissao(dados(), None)

    evidencia = resultado.como_evidencia()
    assert CPF_SINTETICO_1 not in repr(evidencia)
    assert NOME_SINTETICO_1 not in repr(evidencia)


# ---- contrato dos dataclasses ----

def test_dados_colaborador_rejeita_campos_vazios():
    with pytest.raises(ValueError):
        DadosColaboradorKitAdmissao("", CPF_SINTETICO_1, NOME_SINTETICO_1)
    with pytest.raises(ValueError):
        DadosColaboradorKitAdmissao("colab-1", "", NOME_SINTETICO_1)
    with pytest.raises(ValueError):
        DadosColaboradorKitAdmissao("colab-1", CPF_SINTETICO_1, "")
