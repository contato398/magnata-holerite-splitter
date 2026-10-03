"""PortaSecullum: sombra por padrão, real só com as três barreiras juntas,
nunca vaza CPF/nome e nunca chama rede em modo sombra."""
import logging
from datetime import date

import pytest

from magnata_os.rh_admissao.porta_secullum import (
    EVENTO_ACAO_SECULLUM_FALHOU,
    EVENTO_ACAO_SECULLUM_REAL,
    EVENTO_ACAO_SECULLUM_SOMBRA,
    ExecutorSecullumReal,
    ExecutorSecullumSombra,
    IntencaoCadastroSecullum,
    IntencaoDesligamentoSecullum,
    compor_porta_secullum,
    transporte_secullum_real_habilitado,
)

CPF_SINTETICO = "900.000.000-01"
NOME_SINTETICO = "colaborador sintetico"


def cadastro(colaborador_id="colab-1", grupo="G1"):
    return IntencaoCadastroSecullum(colaborador_id, CPF_SINTETICO, NOME_SINTETICO, cargo="Vigia", grupo_escala_id=grupo)


def desligamento(colaborador_id="colab-1"):
    return IntencaoDesligamentoSecullum(colaborador_id, CPF_SINTETICO, date(2026, 9, 30))


class _ServicoFake:
    def __init__(self, id_cadastro="secullum-123", func_existente=None, falha=None):
        self.id_cadastro, self.func_existente, self.falha = id_cadastro, func_existente, falha
        self.chamadas = []

    def sincronizar_funcionario(self, cpf, nome=None, numero=None):
        self.chamadas.append(("sincronizar", cpf, nome, numero))
        if self.falha:
            raise self.falha
        return {"id": self.id_cadastro}

    def buscar_funcionario_secullum_por_cpf(self, cpf):
        return self.func_existente

    def _secullum_request(self, metodo, caminho, json):
        self.chamadas.append((metodo, caminho, json))
        if self.falha:
            raise self.falha


# ---- comportamento padrão: sombra ----

def test_sem_autorizacao_nenhuma_variavel_usa_sombra_e_nao_grava_secullum_id():
    porta = compor_porta_secullum()

    assert isinstance(porta, ExecutorSecullumSombra)
    resultado = porta.cadastrar(cadastro())
    assert resultado.executado is False and resultado.secullum_id is None


def test_sombra_nunca_importa_nem_chama_o_servico_real(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "src.services.secullum_ponto", None)  # importar quebraria

    resultado = ExecutorSecullumSombra().cadastrar(cadastro())

    assert resultado.executado is False


def test_evidencia_nunca_carrega_cpf_ou_nome():
    resultado = ExecutorSecullumSombra().cadastrar(cadastro())

    evidencia = resultado.como_evidencia()
    assert CPF_SINTETICO not in repr(evidencia) and NOME_SINTETICO not in repr(evidencia)


# ---- as três barreiras ----

@pytest.mark.parametrize(
    "flag_codigo, env_operacional, env_dry_run, esperado",
    [
        (False, "1", "", False),           # barreira 1 (código) ausente
        (True, None, "", False),           # barreira 2 (env) ausente
        (True, "0", "", False),            # barreira 2 valor errado
        (True, " 1", "", False),           # barreira 2 variante rejeitada
        (True, "1", "1", False),           # barreira 3 veta
        (True, "1", "", True),             # as três juntas: habilitado
    ],
)
def test_tres_barreiras_juntas_sao_obrigatorias(monkeypatch, flag_codigo, env_operacional, env_dry_run, esperado):
    monkeypatch.delenv("MAGNATA_RH_SECULLUM_REAL_AUTORIZADO", raising=False)
    if env_operacional is not None:
        monkeypatch.setenv("MAGNATA_RH_SECULLUM_REAL_AUTORIZADO", env_operacional)
    monkeypatch.setenv("ORQUESTRADOR_DRY_RUN", env_dry_run)

    assert transporte_secullum_real_habilitado(autorizar_secullum_real=flag_codigo) is esperado


def test_autorizar_whatsapp_nunca_autoriza_secullum(monkeypatch):
    """Variáveis independentes: autorizar um transporte não libera o outro."""
    monkeypatch.setenv("ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO", "1")
    monkeypatch.delenv("MAGNATA_RH_SECULLUM_REAL_AUTORIZADO", raising=False)
    monkeypatch.delenv("ORQUESTRADOR_DRY_RUN", raising=False)

    assert transporte_secullum_real_habilitado(autorizar_secullum_real=True) is False


def test_compor_porta_so_devolve_real_com_as_tres_barreiras(monkeypatch):
    monkeypatch.setenv("MAGNATA_RH_SECULLUM_REAL_AUTORIZADO", "1")
    monkeypatch.delenv("ORQUESTRADOR_DRY_RUN", raising=False)

    assert isinstance(compor_porta_secullum(autorizar_secullum_real=True, servico=_ServicoFake()), ExecutorSecullumReal)
    assert isinstance(compor_porta_secullum(autorizar_secullum_real=False, servico=_ServicoFake()), ExecutorSecullumSombra)


# ---- executor real: só a tradução, nunca reimplementa a chamada ----

def test_executor_real_cadastra_via_sincronizar_funcionario_existente():
    servico = _ServicoFake(id_cadastro="secullum-999")

    resultado = ExecutorSecullumReal(servico).cadastrar(cadastro(grupo="G2"))

    assert resultado.executado is True and resultado.secullum_id == "secullum-999"
    assert servico.chamadas == [("sincronizar", CPF_SINTETICO, NOME_SINTETICO, "G2")]


def test_executor_real_desliga_via_mesma_primitiva_de_rota_excluir():
    servico = _ServicoFake(func_existente={"Id": 42, "EmpresaId": 7, "Empresa": "x", "Nome": NOME_SINTETICO})

    resultado = ExecutorSecullumReal(servico).desligar(desligamento())

    assert resultado.executado is True and resultado.secullum_id == "42"
    metodo, caminho, payload = servico.chamadas[0]
    assert metodo == "PUT" and caminho == "Funcionarios/42"
    assert payload["Demissao"] == "2026-09-30" and "Empresa" not in payload


def test_executor_real_falha_isolada_nunca_lanca_e_nao_vaza_mensagem(caplog):
    servico = _ServicoFake(falha=ConnectionError("timeout com credencial no corpo da resposta"))

    with caplog.at_level(logging.ERROR):
        resultado = ExecutorSecullumReal(servico).cadastrar(cadastro())

    assert resultado.executado is False and resultado.erro_tipo == "ConnectionError"
    assert "credencial" not in caplog.text and "timeout com credencial" not in caplog.text


def test_desligar_colaborador_inexistente_na_secullum_nunca_finge_sucesso():
    servico = _ServicoFake(func_existente=None)

    resultado = ExecutorSecullumReal(servico).desligar(desligamento())

    assert resultado.executado is False and resultado.erro_tipo == "FuncionarioNaoEncontrado"


# ---- contrato ----

def test_intencao_rejeita_cpf_ou_colaborador_vazio():
    with pytest.raises(ValueError):
        IntencaoCadastroSecullum("", CPF_SINTETICO, NOME_SINTETICO)
    with pytest.raises(ValueError):
        IntencaoCadastroSecullum("colab-1", "", NOME_SINTETICO)
    with pytest.raises(ValueError):
        IntencaoDesligamentoSecullum("colab-1", "", date(2026, 9, 30))
