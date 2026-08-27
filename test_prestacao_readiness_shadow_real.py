import json

from requests import RequestException

import scripts.prestacao_readiness_shadow_real as script
from magnata_os.classificacao.politica_requisitos_prestacao import (
    REQUISITOS_BASE_PRESTACAO,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao


class LeitorFake:
    def __init__(self, api_key):
        assert api_key == "token-sintetico"

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        campo = fields[0]
        if table_id == script.TABLE_EXTRATO:
            ids = ["rec-cliente-z", "rec-cliente-a"]
        else:
            raise AssertionError("tabela inesperada")
        return [{"id": "doc", "fields": {campo: ids}}]


class FonteFake:
    def __init__(self, leitor):
        self._leitor = leitor

    def listar(self, cliente, competencia):
        return tuple(
            ItemInventarioPrestacao(
                documento_id=f"doc-{indice}",
                tipo_documental=requisito.tipo_documental,
                cliente=cliente,
                competencia=competencia,
            )
            for indice, requisito in enumerate(REQUISITOS_BASE_PRESTACAO)
        )


def test_seleciona_menor_cliente_existente_nos_extratos():
    leitor = LeitorFake("token-sintetico")
    assert script._selecionar_cliente_id(leitor, "2026-07") == "rec-cliente-a"


def test_execucao_compoe_shadow_e_retorna_apenas_saida_sanitizada(monkeypatch):
    monkeypatch.setattr(script, "LeitorAirtableSomenteLeitura", LeitorFake)
    monkeypatch.setattr(
        script, "FonteInventarioPrestacaoAirtableShadow", FonteFake
    )
    saida = script.executar("2026-07", "token-sintetico")
    assert set(saida) == {
        "cliente_id",
        "competencia",
        "estado",
        "tipos_encontrados",
        "tipos_faltantes",
    }
    assert saida["cliente_id"] == "rec-cliente-a"
    assert saida["competencia"] == "2026-07"
    assert saida["estado"] == "PRONTO"
    assert saida["tipos_faltantes"] == []


def test_main_sem_credencial_informa_somente_variavel(monkeypatch, capsys):
    monkeypatch.delenv(script.CREDENCIAL_ENV, raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["prestacao_readiness_shadow_real.py", "--competencia", "2026-07"],
    )
    assert script.main() == 2
    assert capsys.readouterr().out == "AIRTABLE_API_KEY\n"


def test_main_imprime_json_sem_payload_bruto(monkeypatch, capsys):
    monkeypatch.setenv(script.CREDENCIAL_ENV, "token-sintetico")
    monkeypatch.setattr(script, "LeitorAirtableSomenteLeitura", LeitorFake)
    monkeypatch.setattr(
        script, "FonteInventarioPrestacaoAirtableShadow", FonteFake
    )
    monkeypatch.setattr(
        "sys.argv",
        ["prestacao_readiness_shadow_real.py", "--competencia", "2026-07"],
    )
    assert script.main() == 0
    saida = json.loads(capsys.readouterr().out)
    assert set(saida) == {
        "cliente_id",
        "competencia",
        "estado",
        "tipos_encontrados",
        "tipos_faltantes",
    }


def test_main_sanitiza_excecao_http_sem_url_ou_traceback(monkeypatch, capsys):
    monkeypatch.setenv(script.CREDENCIAL_ENV, "token-sintetico")
    monkeypatch.setattr(
        script,
        "executar",
        lambda *_: (_ for _ in ()).throw(
            RequestException("falha em https://api.exemplo.invalid/payload")
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["prestacao_readiness_shadow_real.py", "--competencia", "2026-07"],
    )
    assert script.main() == 2
    capturado = capsys.readouterr()
    assert capturado.out == "ERRO_LEITURA_EXTERNA\n"
    assert capturado.err == ""
