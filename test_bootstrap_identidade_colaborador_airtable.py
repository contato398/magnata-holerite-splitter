"""Testes de `bootstrap_identidade_colaborador_airtable.py` -- SEMPRE
com fonte de funcionários FAKE, nunca Airtable real (autorização desta
missão cobre só código + testes com fakes/mocks; nenhuma execução real
contra Airtable acontece nesta sessão nem é permitida por este
módulo)."""
from typing import List

import pytest

from magnata_os.documental.alocacao.identidade_colaborador import (
    RepositorioIdentidadeColaboradorEmMemoria,
    calcular_identificador_hash,
)
from magnata_os.documental.importacao_lote.adapters.bootstrap_identidade_colaborador_airtable import (
    TIPO_IDENTIFICADOR_CPF,
    executar_bootstrap_identidade_colaborador_cpf,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

CHAVE_TESTE = b'chave-de-teste-nunca-usar-em-producao'


class _FonteFuncionariosFake:
    """Nunca fala com Airtable -- lista fixa injetada pelo teste."""

    def __init__(self, candidatos: List[CandidatoFuncionario]):
        self._candidatos = candidatos

    def listar_funcionarios(self) -> List[CandidatoFuncionario]:
        return self._candidatos


def test_bootstrap_cria_identidade_para_cada_cpf_valido():
    fonte = _FonteFuncionariosFake([
        CandidatoFuncionario(func_id='func_1', cpf='123.456.789-00', nome_normalizado='ana'),
        CandidatoFuncionario(func_id='func_2', cpf='987.654.321-00', nome_normalizado='bruno'),
    ])
    repo = RepositorioIdentidadeColaboradorEmMemoria()

    resultado = executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, 'v1')

    assert resultado.processados == 2
    assert resultado.criados == 2
    assert resultado.ja_existentes == 0
    assert resultado.ignorados_sem_cpf == 0
    assert resultado.conflitos == ()
    assert len(repo.listar_todos()) == 2

    hash_ana = calcular_identificador_hash(CHAVE_TESTE, '12345678900')
    resolucao = repo.buscar_por_identificador(TIPO_IDENTIFICADOR_CPF, hash_ana)
    assert resolucao.colaborador_id == 'func_1'


def test_bootstrap_ignora_candidatos_sem_cpf():
    fonte = _FonteFuncionariosFake([
        CandidatoFuncionario(func_id='func_1', cpf=None, nome_normalizado='ana'),
        CandidatoFuncionario(func_id='func_2', cpf='', nome_normalizado='bruno'),
    ])
    repo = RepositorioIdentidadeColaboradorEmMemoria()

    resultado = executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, 'v1')

    assert resultado.processados == 2
    assert resultado.criados == 0
    assert resultado.ignorados_sem_cpf == 2
    assert repo.listar_todos() == []


def test_bootstrap_e_idempotente_ao_rodar_duas_vezes():
    fonte = _FonteFuncionariosFake([
        CandidatoFuncionario(func_id='func_1', cpf='123.456.789-00', nome_normalizado='ana'),
    ])
    repo = RepositorioIdentidadeColaboradorEmMemoria()

    executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, 'v1')
    resultado2 = executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, 'v1')

    assert resultado2.criados == 0
    assert resultado2.ja_existentes == 1
    assert len(repo.listar_todos()) == 1


def test_bootstrap_reporta_conflito_sem_abortar_os_demais():
    """2 candidatos com CPFs DIFERENTES nunca colidem entre si (hashes
    diferentes); o conflito real testado aqui é forçar 2 func_ids
    distintos para o MESMO CPF normalizado (ex.: erro de cadastro no
    Airtable) -- o bootstrap reporta e segue para os demais, nunca
    aborta."""
    fonte = _FonteFuncionariosFake([
        CandidatoFuncionario(func_id='func_1', cpf='123.456.789-00', nome_normalizado='ana'),
        CandidatoFuncionario(func_id='func_1_duplicado', cpf='123.456.789-00', nome_normalizado='ana errada'),
        CandidatoFuncionario(func_id='func_2', cpf='987.654.321-00', nome_normalizado='bruno'),
    ])
    repo = RepositorioIdentidadeColaboradorEmMemoria()

    resultado = executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, 'v1')

    assert resultado.processados == 3
    assert resultado.criados == 2  # func_1 e func_2
    assert len(resultado.conflitos) == 1
    assert resultado.conflitos[0].func_id_tentativa == 'func_1_duplicado'
    assert resultado.conflitos[0].colaborador_id_ja_registrado == 'func_1'
    # func_2 (processado DEPOIS do conflito) ainda foi criado -- conflito
    # isolado nunca aborta o restante do bootstrap.
    assert len(repo.listar_todos()) == 2


def test_bootstrap_nunca_persiste_cpf_em_claro():
    fonte = _FonteFuncionariosFake([
        CandidatoFuncionario(func_id='func_1', cpf='123.456.789-00', nome_normalizado='ana'),
    ])
    repo = RepositorioIdentidadeColaboradorEmMemoria()

    executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, 'v1')

    for identidade in repo.listar_todos():
        assert '123456789' not in identidade.identificador_hash
        assert '123.456.789-00' not in identidade.identificador_hash


def test_bootstrap_rejeita_chave_vazia():
    fonte = _FonteFuncionariosFake([])
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    with pytest.raises(ValueError):
        executar_bootstrap_identidade_colaborador_cpf(fonte, repo, b'', 'v1')


def test_bootstrap_rejeita_versao_chave_vazia():
    fonte = _FonteFuncionariosFake([])
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    with pytest.raises(ValueError):
        executar_bootstrap_identidade_colaborador_cpf(fonte, repo, CHAVE_TESTE, '')


def test_bootstrap_pode_rodar_sob_versao_nova_sem_tocar_versao_atual():
    """Simula o passo de rotação autorizado: backfill sob a versão nova
    (v2) produz identidades com versao_chave='v2', distintas por hash
    das que já existem sob 'v1' -- nunca sobrescreve nem depende de
    qual versão está 'atual' em configuração."""
    fonte = _FonteFuncionariosFake([
        CandidatoFuncionario(func_id='func_1', cpf='123.456.789-00', nome_normalizado='ana'),
    ])
    repo = RepositorioIdentidadeColaboradorEmMemoria()

    executar_bootstrap_identidade_colaborador_cpf(fonte, repo, b'chave-v1', 'v1')
    executar_bootstrap_identidade_colaborador_cpf(fonte, repo, b'chave-v2', 'v2')

    todas = repo.listar_todos()
    assert len(todas) == 2  # hashes diferentes sob chaves diferentes -- 2 linhas, nunca 1 sobrescrita
    versoes = sorted(i.versao_chave for i in todas)
    assert versoes == ['v1', 'v2']
    assert all(i.colaborador_id == 'func_1' for i in todas)
