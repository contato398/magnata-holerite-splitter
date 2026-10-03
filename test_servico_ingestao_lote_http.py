"""Testes de
`magnata_os/documental/importacao_lote/servico_ingestao_lote_http.py`
-- fronteira HTTP da ingestao real em lote (painel operacional).

Todo teste injeta `compor_dependencias`/`fechar`/`ingerir` -- nenhum
toca Airtable, S3 ou Postgres real. Dado sintetico apenas (ver
/CLAUDE.md §6, LGPD)."""
from __future__ import annotations

import pytest

from magnata_os.documental.importacao_lote.ingestao_documentos_lote_real import (
    FalhaIngestaoAnexo,
    ResumoIngestaoLote,
)
from magnata_os.documental.importacao_lote.servico_ingestao_lote_http import (
    ConfiguracaoIngestaoAusente,
    ParametrosIngestaoInvalidos,
    executar_ingestao_lote_http,
)
from magnata_os.documental.modulo01.api.autorizacao import PermissaoNegada, Sujeito
from magnata_os.autenticacao.identidade import Perfil

_SUJEITO_GESTOR = Sujeito(perfil=Perfil.GESTOR)
_SUJEITO_OPERACIONAL = Sujeito(perfil=Perfil.OPERACIONAL)
_SUJEITO_AUDITOR = Sujeito(perfil=Perfil.AUDITOR)


class _DependenciasFake:
    def __init__(self):
        self.leitor_airtable = 'leitor-fake'
        self.armazenamento = 'armazenamento-fake'
        self.repositorio_documentos = 'repo-docs-fake'
        self.repositorio_historico = 'repo-historico-fake'


def _resumo_sucesso(cliente_id='recCLIENTE', competencia='2026-09'):
    return ResumoIngestaoLote(
        cliente_id=cliente_id,
        competencia_base=competencia,
        anexos_encontrados=3,
        documentos_ingeridos=2,
        documentos_ja_existentes=1,
    )


def _compor_ok():
    return _DependenciasFake()


def test_exige_sessao_sem_perfil_adequado_nunca_chama_nucleo():
    chamado = {'ingerir': False}

    def _ingerir(**kwargs):
        chamado['ingerir'] = True
        return _resumo_sucesso()

    with pytest.raises(PermissaoNegada):
        executar_ingestao_lote_http(
            _SUJEITO_AUDITOR, 'recCLIENTE', '2026-09',
            compor_dependencias=_compor_ok, fechar=lambda dep: None, ingerir=_ingerir,
        )
    assert chamado['ingerir'] is False


@pytest.mark.parametrize('sujeito', [_SUJEITO_GESTOR, _SUJEITO_OPERACIONAL])
def test_perfil_operacional_ou_gestor_pode_disparar(sujeito):
    fechado = {'valor': False}

    def _fechar(dep):
        fechado['valor'] = True

    resultado = executar_ingestao_lote_http(
        sujeito, 'recCLIENTE', '2026-09',
        compor_dependencias=_compor_ok, fechar=_fechar, ingerir=lambda **kw: _resumo_sucesso(),
    )
    assert resultado['documentos_ingeridos'] == 2
    assert resultado['documentos_ja_existentes'] == 1
    assert fechado['valor'] is True  # dependencias sempre fechadas, mesmo em sucesso


def test_cliente_ausente_e_parametro_invalido_400():
    with pytest.raises(ParametrosIngestaoInvalidos):
        executar_ingestao_lote_http(
            _SUJEITO_GESTOR, '', '2026-09',
            compor_dependencias=_compor_ok, fechar=lambda dep: None, ingerir=lambda **kw: _resumo_sucesso(),
        )


def test_competencia_fora_do_formato_e_parametro_invalido_400():
    with pytest.raises(ParametrosIngestaoInvalidos):
        executar_ingestao_lote_http(
            _SUJEITO_GESTOR, 'recCLIENTE', '2026/09',
            compor_dependencias=_compor_ok, fechar=lambda dep: None, ingerir=lambda **kw: _resumo_sucesso(),
        )


def test_sem_configuracao_de_ambiente_503_nunca_finge_sucesso():
    def _compor_falha():
        raise RuntimeError('AIRTABLE_API_KEY ausente -- ponte somente leitura do Airtable é obrigatória nesta fase')

    with pytest.raises(ConfiguracaoIngestaoAusente):
        executar_ingestao_lote_http(
            _SUJEITO_GESTOR, 'recCLIENTE', '2026-09',
            compor_dependencias=_compor_falha, fechar=lambda dep: None, ingerir=lambda **kw: _resumo_sucesso(),
        )


def test_nucleo_chamado_com_os_parametros_corretos():
    capturado = {}

    def _ingerir(**kwargs):
        capturado.update(kwargs)
        return _resumo_sucesso()

    executar_ingestao_lote_http(
        _SUJEITO_GESTOR, 'recCLIENTE123', '2026-09',
        compor_dependencias=_compor_ok, fechar=lambda dep: None, ingerir=_ingerir,
    )
    assert capturado['cliente_id'] == 'recCLIENTE123'
    assert capturado['competencia_base'] == '2026-09'
    assert capturado['leitor'] == 'leitor-fake'
    assert capturado['armazenamento'] == 'armazenamento-fake'
    assert capturado['repositorio_documentos'] == 'repo-docs-fake'
    assert capturado['repositorio_historico'] == 'repo-historico-fake'


def test_resposta_com_falhas_parciais_nunca_perde_as_falhas():
    def _ingerir(**kwargs):
        return ResumoIngestaoLote(
            cliente_id='recCLIENTE', competencia_base='2026-09',
            anexos_encontrados=2, documentos_ingeridos=1, documentos_ja_existentes=0,
            falhas=(FalhaIngestaoAnexo(registro_airtable_id='rec1', tabela='Holerites', indice_anexo=0, motivo='falha ao baixar anexo'),),
        )

    resultado = executar_ingestao_lote_http(
        _SUJEITO_GESTOR, 'recCLIENTE', '2026-09',
        compor_dependencias=_compor_ok, fechar=lambda dep: None, ingerir=_ingerir,
    )
    assert resultado['total_falhas'] == 1
    assert resultado['falhas'][0]['registro_airtable_id'] == 'rec1'


def test_resposta_nunca_contem_dado_pessoal():
    resultado = executar_ingestao_lote_http(
        _SUJEITO_GESTOR, 'recCLIENTE', '2026-09',
        compor_dependencias=_compor_ok, fechar=lambda dep: None, ingerir=lambda **kw: _resumo_sucesso(),
    )
    texto = str(resultado)
    assert 'cpf' not in texto.lower()
    assert 'nome_original' not in texto.lower()
