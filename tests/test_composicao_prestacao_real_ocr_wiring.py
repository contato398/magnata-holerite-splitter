"""Testa a composição do motor de OCR real (`MotorOcrGoogleVision`) a
partir do ambiente, em `compor_dependencias_a_partir_do_ambiente`
(`magnata_os/orquestrador/composicao_prestacao_real_v1.py`).

Cobre exatamente o que a missão de wiring pediu:

- com `GOOGLE_VISION_API_KEY` presente, o motor real é instanciado e
  injetado (verificável por tipo, sem nenhuma chamada de rede real);
- sem a variável, o comportamento continua EXATAMENTE como antes --
  `motor_ocr=None`, nenhuma regressão.

Nenhum teste aqui faz I/O real: Postgres, S3 e Airtable são
substituídos por fakes/no-ops via monkeypatch nos mesmos pontos de
import que a função já usa (imports locais dentro dela).
"""
from __future__ import annotations

import pytest

from magnata_os.documental.ocr_google_vision import MotorOcrGoogleVision
from magnata_os.orquestrador import composicao_prestacao_real_v1 as composicao


class _ConexaoFake:
    def close(self) -> None:
        pass


class _ArmazenamentoFake:
    pass


class _RepositorioFake:
    def __init__(self, conexao) -> None:
        self.conexao = conexao


class _LeitorAirtableFake:
    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self.api_key = api_key


def _remendar_dependencias_de_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Substitui TODAS as dependências reais de infraestrutura que
    `compor_dependencias_a_partir_do_ambiente` monta, exceto o motor de
    OCR (o alvo do teste) -- nenhuma delas deve tocar rede/disco real."""
    monkeypatch.setattr(
        'magnata_os.documental.alocacao.adapters.postgres_alocacao.RepositorioAlocacaoPostgres',
        _RepositorioFake,
    )
    monkeypatch.setattr(
        'magnata_os.documental.importacao_lote.adapters.airtable_leitura.LeitorAirtableSomenteLeitura',
        _LeitorAirtableFake,
    )
    monkeypatch.setattr(
        'magnata_os.documental.modulo01.adapters.conexao.abrir_conexao',
        lambda: _ConexaoFake(),
    )
    monkeypatch.setattr(
        'magnata_os.documental.modulo01.adapters.postgres_repositorio.RepositorioDocumentosPostgres',
        _RepositorioFake,
    )
    monkeypatch.setattr(
        'magnata_os.documental.modulo01.adapters.postgres_repositorio.RepositorioHistoricoPostgres',
        _RepositorioFake,
    )
    monkeypatch.setattr(
        'magnata_os.documental.modulo01.adapters.postgres_repositorio_esteira.RepositorioEstadosEsteiraPostgres',
        _RepositorioFake,
    )
    monkeypatch.setattr(
        'magnata_os.documental.modulo01.adapters.postgres_repositorio_esteira.RepositorioLotesPostgres',
        _RepositorioFake,
    )
    monkeypatch.setattr(
        'magnata_os.classificacao.adapters.postgres_execucoes_prestacao.RepositorioExecucoesPrestacaoPostgres',
        _RepositorioFake,
    )
    monkeypatch.setattr(
        'magnata_os.orquestrador.ciclo_producao_v1._compor_armazenamento_a_partir_do_ambiente',
        lambda: _ArmazenamentoFake(),
    )
    monkeypatch.setenv('AIRTABLE_API_KEY', 'chave-airtable-fake-de-teste')


def test_com_chave_google_vision_presente_motor_real_e_instanciado(monkeypatch):
    _remendar_dependencias_de_ambiente(monkeypatch)
    monkeypatch.setenv('GOOGLE_VISION_API_KEY', 'chave-vision-fake-de-teste')

    dependencias = composicao.compor_dependencias_a_partir_do_ambiente()
    try:
        assert isinstance(dependencias.motor_ocr, MotorOcrGoogleVision)
    finally:
        composicao.fechar_dependencias(dependencias)


def test_sem_chave_google_vision_motor_ocr_continua_none_sem_erro(monkeypatch):
    _remendar_dependencias_de_ambiente(monkeypatch)
    monkeypatch.delenv('GOOGLE_VISION_API_KEY', raising=False)

    dependencias = composicao.compor_dependencias_a_partir_do_ambiente()
    try:
        assert dependencias.motor_ocr is None
    finally:
        composicao.fechar_dependencias(dependencias)


def test_chave_google_vision_em_branco_e_tratada_como_ausente(monkeypatch):
    _remendar_dependencias_de_ambiente(monkeypatch)
    monkeypatch.setenv('GOOGLE_VISION_API_KEY', '   ')

    dependencias = composicao.compor_dependencias_a_partir_do_ambiente()
    try:
        assert dependencias.motor_ocr is None
    finally:
        composicao.fechar_dependencias(dependencias)


def test_ausencia_de_airtable_key_continua_falhando_independente_do_ocr(monkeypatch):
    """Regressão: a mudança no OCR não pode afrouxar a obrigatoriedade
    já existente do Airtable (comportamento fail-closed preservado)."""
    _remendar_dependencias_de_ambiente(monkeypatch)
    monkeypatch.delenv('AIRTABLE_API_KEY', raising=False)
    monkeypatch.setenv('GOOGLE_VISION_API_KEY', 'chave-vision-fake-de-teste')

    with pytest.raises(RuntimeError):
        composicao.compor_dependencias_a_partir_do_ambiente()
