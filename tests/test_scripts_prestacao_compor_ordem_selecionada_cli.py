"""Integração ponta a ponta: DIAGNÓSTICO REAL (mesmas fontes/fakes de
`test_orquestrador_prestacao_cliente_competencia_v1.py`) -> SELEÇÃO/
CURADORIA DO OPERADOR (`selecao_envio_operador_v1.py`, PR #210) -> ORDEM
REAL COMPOSTA em modo sombra (PENDING), via `scripts/prestacao_compor_
ordem_selecionada_cli.py` (nova CLI desta missão) e o módulo que ela
usa por baixo (`executar_prestacao_selecionada_contato_ate_pending_
shadow_v1.py`, também novo).

Mesma disciplina de `test_scripts_prestacao_diagnostico_real_cli.py`:
nenhuma chamada de rede real (Airtable, Postgres, S3, OCR) -- só os
mesmos fakes já usados por `test_orquestrador_prestacao_cliente_
competencia_v1.py` (`_LeitorAirtableFake`, repositórios em memória) mais
`RepositorioContatoColaboradorEmMemoria` (mesmo padrão de
`test_integracao_prestacao_contato_ate_pending.py`/`_executar_ate_
pending` daquele módulo). `compor_dependencias_a_partir_do_ambiente`
nunca é chamada real aqui -- `DependenciasPrestacaoReal` é sempre
montada com os fakes."""
import json

import pytest
from unittest.mock import patch

from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP, RegistroContatoColaborador, RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato, cifrar_valor_contato,
)
from magnata_os.orquestrador.adapters.postgres_conclusao_obrigacao_assinatura import (
    RepositorioConclusaoObrigacaoAssinaturaEmMemoria,
)
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.composicao_prestacao_real_v1 import ClienteNaoAtivo
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano, RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.selecao_envio_operador_v1 import SelecaoEnvioOperadorError
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    PrestacaoDistribuicaoDocumentalError,
)
from test_orquestrador_prestacao_cliente_competencia_v1 import (
    AGORA, CHAVE_FERNET, CHAVE_HMAC, CLIENTE, N, OUTRO_CLIENTE, PAGINAS, _com_corredor_fake, _Conexao,
    _dependencias, colab,
)

from scripts.prestacao_compor_ordem_selecionada_cli import _parse_args, executar, main


# ---------------------------------------------------------------------
# Fakes de assinatura -- MESMO padrão em memória de
# `test_wiring_distribuicao_documental_shadow.py` (_MaterializadorFake/
# _PortaAssinaturaFake), reaproveitado aqui (não duplicando lógica de
# domínio, só a fixture) para provar o ramo com assinatura desta CLI
# sem NENHUMA chamada de rede real (Airtable/motor de assinatura).
# ---------------------------------------------------------------------

class _MaterializadorFake:
    def __init__(self):
        self.chamadas = []

    def materializar(self, *, documento, conteudo_bytes, funcionario_id):
        from magnata_os.documental.modulo01.materializador_arquivo import ResultadoMaterializacao
        self.chamadas.append((documento.documento_id, funcionario_id))
        return ResultadoMaterializacao(
            arquivo_record_id=f'recARQ{len(self.chamadas)}',
            documento_id=documento.documento_id, funcionario_id=funcionario_id,
            hash_sha256=documento.hash_sha256, reutilizado=False,
        )


class _PortaAssinaturaFake:
    def __init__(self):
        self._por_correlacao = {}
        self.chamadas_criar = 0

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id, funcionario_id, tipo_documento, arquivo_record_ids):
        self.chamadas_criar += 1
        obrigacao = ObrigacaoAssinatura(
            assinatura_id=f'rec-obg-{self.chamadas_criar}',
            link=f'https://exemplo.invalid/assinatura/{token_reservado}',
            status='Pendente', tem_comprovante=False,
        )
        self._por_correlacao[acao_execucao_id] = obrigacao
        return obrigacao

    def consultar_por_correlacao(self, *, acao_execucao_id):
        return self._por_correlacao.get(acao_execucao_id)

MODULO = "scripts.prestacao_compor_ordem_selecionada_cli"


def _repositorio_contato(colaboradores_com_contato):
    """`RepositorioContatoColaboradorEmMemoria` com contato registrado só
    para os `colab(i)` informados -- os demais ficam SEM contato
    cadastrado (fail-closed do resolvedor real)."""
    repo = RepositorioContatoColaboradorEmMemoria()
    for i in colaboradores_com_contato:
        repo.criar_ou_confirmar(RegistroContatoColaborador(
            colaborador_id=colab(i), canal=CANAL_WHATSAPP,
            valor_cifrado=cifrar_valor_contato(CHAVE_FERNET, f"1199990{i:04d}"),
            hash_auxiliar=calcular_hash_auxiliar_contato(CHAVE_HMAC, f"1199990{i:04d}"),
            versao_chave="v1", origem="teste", criado_em=AGORA, atualizado_em=AGORA,
        ))
    return repo


def _selecao_json(*colaboradores, exigir_assinatura=False):
    return {
        "itens": [
            {
                "cliente_id": CLIENTE.entidade_id, "competencia_id": "2026-09",
                "colaborador_id": colab(i), "tipos_documentais": ["Holerite"],
                "exigir_assinatura_digital_e_comprovante": exigir_assinatura,
            }
            for i in colaboradores
        ]
    }


def _escrever_selecao(tmp_path, selecao_dict):
    caminho = tmp_path / "selecao.json"
    caminho.write_text(json.dumps(selecao_dict), encoding="utf-8")
    return str(caminho)


def _executar_com_ambiente_fake(*, deps, repositorio_contato, selecao_path, preset_id, mensagem,
                                 materializador=None, porta_assinatura=None):
    """Mesmo padrão de composição do núcleo de `executar()`, mas
    substituindo os compositores reais de ambiente (Postgres, Airtable,
    motor de assinatura) pelos fakes -- via `patch`, nunca
    reimplementando a lógica de `executar()`. Os compositores de
    assinatura são sempre substituídos (mesmo com preset sem
    assinatura, quando nunca são chamados) para que NENHUM teste possa
    acidentalmente tentar ler credencial real de ambiente."""
    conexao = _Conexao()
    with patch(f"{MODULO}.compor_repositorio_contato_a_partir_do_ambiente", return_value=repositorio_contato), \
         patch(f"{MODULO}.compor_chave_fernet_contato_a_partir_do_ambiente", return_value=CHAVE_FERNET), \
         patch(f"{MODULO}._compor_repositorio_execucoes_a_partir_do_ambiente", return_value=RepositorioExecucoesEmMemoria()), \
         patch(f"{MODULO}._compor_repositorio_autorizacoes_a_partir_do_ambiente", return_value=RepositorioAutorizacoesGateEmMemoria()), \
         patch(f"{MODULO}._compor_repositorio_acoes_a_partir_do_ambiente", return_value=RepositorioAcoesExecucaoPlanoPostgres(conexao)), \
         patch(f"{MODULO}._compor_materializador_a_partir_do_ambiente", return_value=materializador), \
         patch(f"{MODULO}._compor_obrigacao_assinatura_a_partir_do_ambiente", return_value=porta_assinatura), \
         patch(f"{MODULO}._compor_repositorio_conclusao_a_partir_do_ambiente",
               return_value=RepositorioConclusaoObrigacaoAssinaturaEmMemoria()):
        with _com_corredor_fake():
            saida = executar(
                cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", selecao_path=selecao_path,
                preset_id=preset_id, mensagem=mensagem, tipo_documento="PRESTACAO_CONTAS",
                dependencias=deps, instante=AGORA,
            )
    return saida, conexao


# ---------------------------------------------------------------------
# Caminho feliz: 1x1, Nx1 (N colaboradores selecionados), resto de fora.
# ---------------------------------------------------------------------

def test_so_os_colaboradores_selecionados_viram_ordem_resto_fica_diagnosticado_fora(tmp_path):
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1, 2, 3])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1, 2))  # colab-03 fica de fora

    saida, conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
    )

    assert saida["status"] == "ORDENS_COMPOSTAS_EM_SOMBRA_PENDING"
    assert saida["itens_na_selecao"] == 2
    assert saida["ordens_compostas"] == 2
    assert {o["funcionario_id"] for o in saida["ordens"]} == {colab(1), colab(2)}
    assert {o["estado_acao"] for o in saida["ordens"]} == {"PENDING"}
    assert all(o["assinatura_link"] is None for o in saida["ordens"])
    assert conexao.linhas  # ação persistida de verdade


def test_selecao_vazia_nao_toca_resolvedor_nem_cria_ordem(tmp_path):
    deps = _dependencias(PAGINAS)
    selecao_path = _escrever_selecao(tmp_path, {"itens": []})

    # Nenhum repositório de contato é fornecido -- se o caminho tentasse
    # resolvê-lo, o teste falharia por atributo ausente/None inválido.
    saida, conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=None, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
    )

    assert saida == {
        "status": "SELECAO_VAZIA_NENHUMA_ORDEM", "ordens": [],
        "aviso": (
            "seleção sem itens é o padrão seguro -- nenhuma Ordem foi criada, nenhuma dependência real foi "
            "consultada além do contexto."
        ),
    }
    assert conexao.linhas == {}


# ---------------------------------------------------------------------
# Isolamento fail-closed: contato ausente, preset divergente da seleção.
# ---------------------------------------------------------------------

def test_colaborador_sem_contato_cadastrado_fica_isolado_resto_segue(tmp_path):
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])  # colab-02 sem contato
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1, 2))

    saida, _conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
    )

    assert saida["itens_na_selecao"] == 2
    assert saida["ordens_compostas"] == 1
    assert saida["ordens"][0]["funcionario_id"] == colab(1)


def test_selecao_com_assinatura_e_preset_sem_assinatura_isola_so_esse_colaborador(tmp_path):
    """Operador pede `exigir_assinatura_digital_e_comprovante=True` para
    colab-01, mas a CLI só aceita preset SEM assinatura -- fail-closed
    (`PresetDaOrdemDivergeDaSelecaoOperador`, já existente no wiring,
    reaproveitado): a Ordem de colab-01 NUNCA sai divergente do pedido,
    mas colab-02 (sem exigência de assinatura) chega normalmente."""
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1, 2])
    selecao = {
        "itens": [
            {
                "cliente_id": CLIENTE.entidade_id, "competencia_id": "2026-09", "colaborador_id": colab(1),
                "tipos_documentais": ["Holerite"], "exigir_assinatura_digital_e_comprovante": True,
            },
            {
                "cliente_id": CLIENTE.entidade_id, "competencia_id": "2026-09", "colaborador_id": colab(2),
                "tipos_documentais": ["Holerite"], "exigir_assinatura_digital_e_comprovante": False,
            },
        ]
    }
    selecao_path = _escrever_selecao(tmp_path, selecao)

    saida, _conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
    )

    assert saida["itens_na_selecao"] == 2
    assert saida["ordens_compostas"] == 1
    assert saida["ordens"][0]["funcionario_id"] == colab(2)


# ---------------------------------------------------------------------
# Wiring de assinatura (missão "prestacao-compor-ordem-selecionada-
# assinatura-wiring-v1"): preset COM assinatura agora chega a PENDING
# ponta a ponta, usando os compositores REAIS de `distribuir_
# documento_v1.py` (intocados) -- aqui sempre substituídos por fake em
# memória, nunca rede real.
# ---------------------------------------------------------------------

def test_preset_com_assinatura_e_aceito_e_compoe_materializador_e_porta_assinatura_reais(tmp_path):
    """Antes desta missão, `--preset DOCUMENTO_UNITARIO_COM_ASSINATURA`
    era rejeitado em `_parse_args` (fail-closed antes de qualquer
    dependência). Agora a Ordem chega a PENDING com `assinatura_link`
    preenchido, e os compositores reais de materializador/porta_
    assinatura (aqui, fakes em memória) SÃO chamados -- prova de que a
    ligação existe de ponta a ponta."""
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1, exigir_assinatura=True))
    materializador = _MaterializadorFake()
    porta_assinatura = _PortaAssinaturaFake()

    saida, conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_COM_ASSINATURA", mensagem="Segue seu documento",
        materializador=materializador, porta_assinatura=porta_assinatura,
    )

    assert saida["status"] == "ORDENS_COMPOSTAS_EM_SOMBRA_PENDING"
    assert saida["ordens_compostas"] == 1
    assert saida["ordens"][0]["estado_acao"] == "PENDING"
    assert saida["ordens"][0]["assinatura_link"] is not None
    assert materializador.chamadas  # materializador REAL(fake) foi de fato chamado
    assert porta_assinatura.chamadas_criar == 1  # obrigação de assinatura foi de fato criada
    assert conexao.linhas


def test_selecao_sem_assinatura_e_preset_com_assinatura_isola_so_esse_colaborador(tmp_path):
    """Direção oposta do teste já existente para preset SEM assinatura:
    colab-01 não exigiu assinatura, mas o `--preset` desta execução
    exige -- `PresetDaOrdemDivergeDaSelecaoOperador` isola só colab-01;
    colab-02 (que exigiu assinatura, batendo com o preset) chega a
    PENDING normalmente. Prova a exigência da missão: 'isolamento de
    falha -- um item com problema de assinatura não trava os demais'."""
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1, 2])
    selecao = {
        "itens": [
            {
                "cliente_id": CLIENTE.entidade_id, "competencia_id": "2026-09", "colaborador_id": colab(1),
                "tipos_documentais": ["Holerite"], "exigir_assinatura_digital_e_comprovante": False,
            },
            {
                "cliente_id": CLIENTE.entidade_id, "competencia_id": "2026-09", "colaborador_id": colab(2),
                "tipos_documentais": ["Holerite"], "exigir_assinatura_digital_e_comprovante": True,
            },
        ]
    }
    selecao_path = _escrever_selecao(tmp_path, selecao)

    saida, _conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_COM_ASSINATURA", mensagem="Segue seu documento",
        materializador=_MaterializadorFake(), porta_assinatura=_PortaAssinaturaFake(),
    )

    assert saida["itens_na_selecao"] == 2
    assert saida["ordens_compostas"] == 1
    assert saida["ordens"][0]["funcionario_id"] == colab(2)
    assert saida["ordens"][0]["assinatura_link"] is not None


def test_preset_sem_assinatura_nunca_compoe_materializador_nem_porta_assinatura(tmp_path):
    """Nenhum compositor de assinatura é sequer chamado quando o preset
    não exige assinatura -- garante que a mudança desta missão é
    estritamente aditiva (comportamento antigo, sem assinatura,
    permanece bit a bit o mesmo)."""
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1))

    with patch(f"{MODULO}._compor_materializador_a_partir_do_ambiente") as compor_materializador, \
         patch(f"{MODULO}._compor_obrigacao_assinatura_a_partir_do_ambiente") as compor_porta, \
         patch(f"{MODULO}._compor_repositorio_conclusao_a_partir_do_ambiente") as compor_conclusao, \
         patch(f"{MODULO}.compor_repositorio_contato_a_partir_do_ambiente", return_value=repositorio_contato), \
         patch(f"{MODULO}.compor_chave_fernet_contato_a_partir_do_ambiente", return_value=CHAVE_FERNET), \
         patch(f"{MODULO}._compor_repositorio_execucoes_a_partir_do_ambiente", return_value=RepositorioExecucoesEmMemoria()), \
         patch(f"{MODULO}._compor_repositorio_autorizacoes_a_partir_do_ambiente", return_value=RepositorioAutorizacoesGateEmMemoria()), \
         patch(f"{MODULO}._compor_repositorio_acoes_a_partir_do_ambiente", return_value=RepositorioAcoesExecucaoPlanoPostgres(_Conexao())):
        with _com_corredor_fake():
            saida = executar(
                cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", selecao_path=selecao_path,
                preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
                tipo_documento="PRESTACAO_CONTAS", dependencias=deps, instante=AGORA,
            )

    assert saida["ordens_compostas"] == 1
    compor_materializador.assert_not_called()
    compor_porta.assert_not_called()
    compor_conclusao.assert_not_called()


def test_preset_com_assinatura_sem_credencial_de_ambiente_falha_fail_closed_via_main(tmp_path, capsys):
    """`main()` propaga o `RuntimeError` fail-closed do compositor real
    (`_compor_materializador_a_partir_do_ambiente`/`_compor_obrigacao_
    assinatura_a_partir_do_ambiente`, ambos intocados) como
    `CONFIGURACAO_AUSENTE` -- nunca uma tentativa de inferir/ignorar a
    credencial ausente, e NUNCA chega a tentar rede real."""
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1, exigir_assinatura=True))

    with patch(f"{MODULO}.compor_dependencias_a_partir_do_ambiente", return_value=deps), \
         patch(f"{MODULO}.fechar_dependencias"), \
         patch(f"{MODULO}.compor_repositorio_contato_a_partir_do_ambiente", return_value=repositorio_contato), \
         patch(f"{MODULO}.compor_chave_fernet_contato_a_partir_do_ambiente", return_value=CHAVE_FERNET), \
         patch(f"{MODULO}._compor_repositorio_execucoes_a_partir_do_ambiente", return_value=RepositorioExecucoesEmMemoria()), \
         patch(f"{MODULO}._compor_repositorio_autorizacoes_a_partir_do_ambiente", return_value=RepositorioAutorizacoesGateEmMemoria()), \
         patch(f"{MODULO}._compor_repositorio_acoes_a_partir_do_ambiente", return_value=RepositorioAcoesExecucaoPlanoPostgres(_Conexao())), \
         patch(f"{MODULO}._compor_materializador_a_partir_do_ambiente",
               side_effect=RuntimeError("AIRTABLE_API_KEY não configurada -- materializador nunca infere credencial (fail-closed).")), \
         _com_corredor_fake():
        codigo = main([
            "--cliente", CLIENTE.entidade_id, "--competencia", "2026-09", "--selecao", selecao_path,
            "--preset", "DOCUMENTO_UNITARIO_COM_ASSINATURA", "--mensagem", "Segue seu documento",
        ])

    assert codigo == 2
    assert "CONFIGURACAO_AUSENTE" in capsys.readouterr().out


def test_nenhuma_chamada_de_rede_real_e_feita_pelo_script_com_preset_de_assinatura(monkeypatch, tmp_path):
    """Mesma garantia de `test_nenhuma_chamada_de_rede_real_e_feita_pelo_
    script`, agora exercitando o ramo com assinatura (o mais arriscado
    de introduzir chamada de rede real por engano, já que é o ramo que
    chama `materializador`/`porta_assinatura` de verdade em produção)."""
    import socket

    def _bloqueado(*args, **kwargs):
        raise AssertionError("tentativa de chamada de rede real durante o teste")

    monkeypatch.setattr(socket.socket, "connect", _bloqueado)

    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1, exigir_assinatura=True))

    saida, _conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_COM_ASSINATURA", mensagem="Segue seu documento",
        materializador=_MaterializadorFake(), porta_assinatura=_PortaAssinaturaFake(),
    )
    assert saida["ordens_compostas"] == 1
    assert saida["ordens"][0]["assinatura_link"] is not None


def test_selecao_apontando_para_necessidade_nao_pronta_e_rejeitada(tmp_path):
    """`colab(N + 1)` não existe no pacote pronto deste cliente/competência
    -- a seleção do operador rejeita com erro claro, nunca silencioso."""
    deps = _dependencias(PAGINAS, colaboradores=N + 1)  # colab(N+1) esperado, fora do PDF -> AUSENTE
    repositorio_contato = _repositorio_contato(range(1, N + 2))
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(N + 1))

    with pytest.raises((PrestacaoDistribuicaoDocumentalError, SelecaoEnvioOperadorError)):
        _executar_com_ambiente_fake(
            deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
            preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
        )


# ---------------------------------------------------------------------
# Idempotência.
# ---------------------------------------------------------------------

def test_rodar_a_mesma_selecao_2_vezes_nao_duplica_acao(tmp_path):
    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1))
    conexao = _Conexao()
    repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    def _rodar():
        with patch(f"{MODULO}.compor_repositorio_contato_a_partir_do_ambiente", return_value=repositorio_contato), \
             patch(f"{MODULO}.compor_chave_fernet_contato_a_partir_do_ambiente", return_value=CHAVE_FERNET), \
             patch(f"{MODULO}._compor_repositorio_execucoes_a_partir_do_ambiente", return_value=RepositorioExecucoesEmMemoria()), \
             patch(f"{MODULO}._compor_repositorio_autorizacoes_a_partir_do_ambiente", return_value=RepositorioAutorizacoesGateEmMemoria()), \
             patch(f"{MODULO}._compor_repositorio_acoes_a_partir_do_ambiente", return_value=repositorio_acoes):
            with _com_corredor_fake():
                return executar(
                    cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", selecao_path=selecao_path,
                    preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
                    tipo_documento="PRESTACAO_CONTAS", dependencias=deps, instante=AGORA,
                )

    primeiro = _rodar()
    segundo = _rodar()

    assert primeiro["ordens"][0]["event_id"] == segundo["ordens"][0]["event_id"]
    # 2 linhas reais (texto + documento, Gate J1b), nunca 4 -- a 2a
    # chamada não duplica nada, mesmo padrão de
    # test_integracao_prestacao_contato_ate_pending.py.
    assert len(conexao.linhas) == 2


# ---------------------------------------------------------------------
# main(): erros claros, sem chamada de rede.
# ---------------------------------------------------------------------

def test_main_cliente_nao_encontrado_devolve_erro_claro(tmp_path, capsys):
    deps = _dependencias(PAGINAS)
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1))
    with patch(f"{MODULO}.compor_dependencias_a_partir_do_ambiente", return_value=deps), \
         patch(f"{MODULO}.fechar_dependencias"):
        codigo = main([
            "--cliente", OUTRO_CLIENTE, "--competencia", "2026-09", "--selecao", selecao_path,
            "--preset", "DOCUMENTO_UNITARIO_SEM_ASSINATURA", "--mensagem", "x",
        ])
    assert codigo == 2
    assert "CLIENTE_NAO_ENCONTRADO_OU_INATIVO" in capsys.readouterr().out


def test_main_arquivo_de_selecao_inexistente_devolve_erro_claro(capsys):
    deps = _dependencias(PAGINAS)
    with patch(f"{MODULO}.compor_dependencias_a_partir_do_ambiente", return_value=deps), \
         patch(f"{MODULO}.fechar_dependencias"):
        codigo = main([
            "--cliente", CLIENTE.entidade_id, "--competencia", "2026-09",
            "--selecao", str(tmp_path_inexistente()), "--preset", "DOCUMENTO_UNITARIO_SEM_ASSINATURA",
            "--mensagem", "x",
        ])
    assert codigo == 2
    assert "ARQUIVO_NAO_ENCONTRADO" in capsys.readouterr().out


def tmp_path_inexistente():
    return "/tmp/este-caminho-nao-existe-magnata-teste/selecao.json"


def test_main_preset_invalido_falha_antes_de_compor_dependencias():
    """`--preset` desconhecido de `politica_preset_distribuicao_documental`
    continua fail-closed antes de qualquer composição de dependências --
    `DOCUMENTO_UNITARIO_COM_ASSINATURA` NÃO é mais um caso deste teste
    (ver `test_preset_com_assinatura_e_aceito_e_compoe_materializador_
    e_porta_assinatura_reais`): esta CLI passou a aceitar qualquer
    preset_id conhecido, com ou sem assinatura."""
    with patch(f"{MODULO}.compor_dependencias_a_partir_do_ambiente") as compor:
        with pytest.raises(SystemExit):
            _parse_args([
                "--cliente", "rec1", "--competencia", "2026-09", "--selecao", "x.json",
                "--preset", "PRESET_QUE_NAO_EXISTE", "--mensagem", "x",
            ])
    compor.assert_not_called()


def test_main_configuracao_ausente_devolve_erro_claro_sem_chamar_rede(capsys):
    with patch(
        f"{MODULO}.compor_dependencias_a_partir_do_ambiente",
        side_effect=RuntimeError("AIRTABLE_API_KEY ausente -- ponte somente leitura do Airtable é obrigatória nesta fase"),
    ):
        codigo = main([
            "--cliente", "rec1", "--competencia", "2026-09", "--selecao", "x.json",
            "--preset", "DOCUMENTO_UNITARIO_SEM_ASSINATURA", "--mensagem", "x",
        ])
    assert codigo == 2
    assert "CONFIGURACAO_AUSENTE" in capsys.readouterr().out


def test_parse_args_exige_selecao_preset_e_mensagem():
    with pytest.raises(SystemExit):
        _parse_args(["--cliente", "rec1", "--competencia", "2026-09"])
    with pytest.raises(SystemExit):
        _parse_args([
            "--cliente", "rec1", "--competencia", "2026-09", "--selecao", "x.json",
            "--preset", "DOCUMENTO_UNITARIO_SEM_ASSINATURA",
        ])


def test_nenhuma_chamada_de_rede_real_e_feita_pelo_script(monkeypatch, tmp_path):
    import socket

    def _bloqueado(*args, **kwargs):
        raise AssertionError("tentativa de chamada de rede real durante o teste")

    monkeypatch.setattr(socket.socket, "connect", _bloqueado)

    deps = _dependencias(PAGINAS)
    repositorio_contato = _repositorio_contato([1])
    selecao_path = _escrever_selecao(tmp_path, _selecao_json(1))

    saida, _conexao = _executar_com_ambiente_fake(
        deps=deps, repositorio_contato=repositorio_contato, selecao_path=selecao_path,
        preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", mensagem="Segue seu documento",
    )
    assert saida["ordens_compostas"] == 1


def test_script_e_executavel_via_help_sem_efeito_colateral():
    import subprocess
    import sys

    resultado = subprocess.run(
        [sys.executable, "scripts/prestacao_compor_ordem_selecionada_cli.py", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0
    assert "--selecao" in resultado.stdout and "--preset" in resultado.stdout
