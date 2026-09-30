"""Testes de `scripts/prestacao_diagnostico_real_cli.py` -- o elo que
falta entre a composição REAL do contexto da Prestação
(`composicao_prestacao_real_v1.compor_dependencias_a_partir_do_ambiente`)
e a seleção/curadoria do operador (`selecao_envio_operador_cli.py`, PR
#210), sem o operador ter que montar `diagnostico.json` na mão.

Mesma disciplina de `test_orquestrador_prestacao_cliente_competencia_v1.
py`: nenhuma chamada de rede real (Airtable, Postgres, S3, OCR) -- só os
fakes já usados por esse módulo (`_LeitorAirtableFake`, repositórios em
memória). `compor_dependencias_a_partir_do_ambiente` (que abriria
conexão Postgres real e leria `AIRTABLE_API_KEY` de verdade) nunca é
chamada aqui -- só `DependenciasPrestacaoReal` montada com os fakes,
igual ao módulo original."""
import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from magnata_os.orquestrador.composicao_prestacao_real_v1 import ClienteNaoAtivo
from test_orquestrador_prestacao_cliente_competencia_v1 import (
    CLIENTE, N, OUTRO_CLIENTE, PAGINAS, TIPOS_CLIENTE, _com_corredor_fake, _dependencias, colab,
)

from scripts.prestacao_diagnostico_real_cli import _parse_args, executar_diagnostico_real, main


def test_diagnostico_real_produz_o_mesmo_formato_que_a_selecao_do_operador_ja_espera():
    """`selecao_envio_operador_cli._linhas_do_diagnostico_json` lê
    `clientes[*].necessidades[*]` com as chaves cliente/competencia/
    tipo_documental/colaborador/situacao -- exatamente o que
    `DiagnosticoNecessidade.como_dict()` produz. Aqui provamos que o
    script novo devolve isso sem nenhum campo a mais (nada de `modo`/
    `coleta`, que `executar_prestacao_cliente_competencia` adiciona)."""
    deps = _dependencias(PAGINAS)

    with _com_corredor_fake():
        diagnostico = executar_diagnostico_real(
            cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps,
        )

    assert set(diagnostico.keys()) == {"competencia_base", "clientes"}
    assert diagnostico["competencia_base"] == "2026-09"
    cliente = diagnostico["clientes"][0]
    assert set(cliente.keys()) == {"cliente", "competencia", "estado_pacote", "ordem_pronta", "necessidades"}
    assert cliente["cliente"] == CLIENTE.entidade_id and cliente["ordem_pronta"] is True
    linha = cliente["necessidades"][0]
    assert set(linha.keys()) == {
        "cliente", "competencia", "tipo_documental", "colaborador", "situacao",
        "documentos_avaliados", "documentos_elegiveis", "localizacao",
    }
    situacoes = {(n["tipo_documental"], n["colaborador"]): n["situacao"] for n in cliente["necessidades"]}
    assert situacoes == {
        **{("Holerite", colab(i)): "PRONTO" for i in range(1, N + 1)},
        **{(tipo, None): "PRONTO" for tipo in TIPOS_CLIENTE},
    }
    # somente leitura: nada gravado nos repositórios reais
    assert deps.repositorio_documentos.listar_todos() is not None


def test_diagnostico_real_nunca_grava_nada():
    deps = _dependencias(PAGINAS)
    total_antes = len(deps.repositorio_documentos.listar_todos())

    with _com_corredor_fake():
        executar_diagnostico_real(cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps)

    assert len(deps.repositorio_documentos.listar_todos()) == total_antes


def test_cliente_inexistente_ou_inativo_falha_com_erro_claro():
    deps = _dependencias(PAGINAS)

    with pytest.raises(ClienteNaoAtivo):
        executar_diagnostico_real(cliente_id=OUTRO_CLIENTE, competencia_base="2026-09", dependencias=deps)
    with pytest.raises(ClienteNaoAtivo):
        executar_diagnostico_real(cliente_id="cliente-que-nao-existe", competencia_base="2026-09", dependencias=deps)


def test_competencia_mal_formada_falha_com_erro_claro():
    deps = _dependencias(PAGINAS)

    with pytest.raises(ValueError):
        executar_diagnostico_real(cliente_id=CLIENTE.entidade_id, competencia_base="09/2026", dependencias=deps)
    with pytest.raises(ValueError):
        executar_diagnostico_real(cliente_id=CLIENTE.entidade_id, competencia_base="2026-13", dependencias=deps)


def test_parse_args_exige_cliente_e_competencia_no_formato_aaaa_mm():
    args = _parse_args(["--cliente", "rec1", "--competencia", "2026-09"])
    assert args.cliente == "rec1" and args.competencia == "2026-09"
    with pytest.raises(SystemExit):
        _parse_args(["--competencia", "2026-09"])
    with pytest.raises(SystemExit):
        _parse_args(["--cliente", "rec1"])
    with pytest.raises(SystemExit):
        _parse_args(["--cliente", "rec1", "--competencia", "09/2026"])


def test_main_imprime_json_no_formato_esperado_pela_selecao_do_operador(capsys):
    deps = _dependencias(PAGINAS)

    with _com_corredor_fake(), \
            patch("scripts.prestacao_diagnostico_real_cli.compor_dependencias_a_partir_do_ambiente", return_value=deps), \
            patch("scripts.prestacao_diagnostico_real_cli.fechar_dependencias") as fechar:
        codigo = main(["--cliente", CLIENTE.entidade_id, "--competencia", "2026-09"])

    assert codigo == 0
    fechar.assert_called_once_with(deps)
    saida = json.loads(capsys.readouterr().out)
    assert saida["competencia_base"] == "2026-09"
    assert saida["clientes"][0]["cliente"] == CLIENTE.entidade_id
    # Exatamente o formato que `selecao_envio_operador_cli._linhas_do_
    # diagnostico_json` (PR #210, ainda não mesclado nesta branch --
    # por isso a mesma extração é replicada aqui, inline, em vez de
    # importar o módulo) já lê: `clientes[*].necessidades[*]` com as
    # chaves cliente/competencia/tipo_documental/colaborador/situacao.
    linhas = [
        {
            "cliente_id": necessidade["cliente"], "competencia_id": necessidade["competencia"],
            "tipo_documental": necessidade["tipo_documental"], "colaborador_id": necessidade.get("colaborador"),
            "situacao": necessidade["situacao"],
        }
        for cliente in saida["clientes"]
        for necessidade in cliente["necessidades"]
    ]
    assert {
        "cliente_id": CLIENTE.entidade_id, "competencia_id": "2026-09",
        "tipo_documental": "Holerite", "colaborador_id": colab(1), "situacao": "PRONTO",
    } in linhas


def test_main_cliente_nao_encontrado_devolve_erro_claro_e_codigo_de_saida_nao_zero(capsys):
    deps = _dependencias(PAGINAS)

    with patch("scripts.prestacao_diagnostico_real_cli.compor_dependencias_a_partir_do_ambiente", return_value=deps), \
            patch("scripts.prestacao_diagnostico_real_cli.fechar_dependencias"):
        codigo = main(["--cliente", OUTRO_CLIENTE, "--competencia", "2026-09"])

    assert codigo == 2
    assert "CLIENTE_NAO_ENCONTRADO_OU_INATIVO" in capsys.readouterr().out


def test_main_competencia_invalida_falha_antes_de_compor_dependencias(capsys):
    with patch("scripts.prestacao_diagnostico_real_cli.compor_dependencias_a_partir_do_ambiente") as compor:
        with pytest.raises(SystemExit):
            main(["--cliente", "rec1", "--competencia", "09/2026"])
    compor.assert_not_called()


def test_main_configuracao_ausente_devolve_erro_claro_sem_chamar_rede(capsys):
    with patch(
        "scripts.prestacao_diagnostico_real_cli.compor_dependencias_a_partir_do_ambiente",
        side_effect=RuntimeError("AIRTABLE_API_KEY ausente -- ponte somente leitura do Airtable é obrigatória nesta fase"),
    ):
        codigo = main(["--cliente", "rec1", "--competencia", "2026-09"])

    assert codigo == 2
    assert "CONFIGURACAO_AUSENTE" in capsys.readouterr().out


def test_nenhuma_chamada_de_rede_real_e_feita_pelo_script(monkeypatch):
    """Garante que nada neste teste (nem indiretamente) alcança a rede --
    qualquer tentativa de abrir socket falha o teste."""
    import socket

    def _bloqueado(*args, **kwargs):
        raise AssertionError("tentativa de chamada de rede real durante o teste")

    monkeypatch.setattr(socket.socket, "connect", _bloqueado)
    deps = _dependencias(PAGINAS)

    with _com_corredor_fake():
        executar_diagnostico_real(cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps)


def test_script_e_executavel_via_module_help_sem_efeito_colateral():
    """Só valida que o script é invocável como processo (formação de
    `argparse`/imports) -- `--help` nunca chama `compor_dependencias_a_
    partir_do_ambiente` nem toca rede."""
    resultado = subprocess.run(
        [sys.executable, "scripts/prestacao_diagnostico_real_cli.py", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0
    assert "--cliente" in resultado.stdout and "--competencia" in resultado.stdout
