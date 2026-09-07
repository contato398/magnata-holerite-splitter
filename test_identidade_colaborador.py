"""Testes do domínio `identidade_colaborador.py` (Identidade Canônica
de Colaborador V1) -- puro, sem Postgres/Airtable/rede."""
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.contratos import EstadoResolucaoDimensao
from magnata_os.documental.alocacao.identidade_colaborador import (
    ConflitoIdentidadeColaborador,
    IdentidadeColaboradorObservada,
    RepositorioIdentidadeColaboradorEmMemoria,
    calcular_identificador_hash,
    resolver_identidade_colaborador,
)

CHAVE_TESTE = b'chave-de-teste-nunca-usar-em-producao'


def _agora():
    return datetime(2026, 9, 6, tzinfo=timezone.utc)


def _identidade(colaborador_id: str, hash_: str, versao_chave: str = 'v1') -> IdentidadeColaboradorObservada:
    agora = _agora()
    return IdentidadeColaboradorObservada(
        tipo_identificador='CPF', identificador_hash=hash_, colaborador_id=colaborador_id,
        origem='teste', versao_chave=versao_chave, criado_em=agora, atualizado_em=agora,
    )


# ---------------------------------------------------------------------------
# calcular_identificador_hash
# ---------------------------------------------------------------------------

def test_hash_e_deterministico_para_mesma_chave_e_valor():
    h1 = calcular_identificador_hash(CHAVE_TESTE, '12345678900')
    h2 = calcular_identificador_hash(CHAVE_TESTE, '12345678900')
    assert h1 == h2
    assert len(h1) == 64  # hex de SHA-256


def test_hash_difere_para_chaves_diferentes_mesmo_valor():
    h_v1 = calcular_identificador_hash(b'chave-v1', '12345678900')
    h_v2 = calcular_identificador_hash(b'chave-v2', '12345678900')
    assert h_v1 != h_v2


def test_hash_difere_para_valores_diferentes_mesma_chave():
    h1 = calcular_identificador_hash(CHAVE_TESTE, '12345678900')
    h2 = calcular_identificador_hash(CHAVE_TESTE, '98765432100')
    assert h1 != h2


def test_hash_nunca_reversivel_trivialmente_para_o_cpf_original():
    h = calcular_identificador_hash(CHAVE_TESTE, '12345678900')
    assert '12345678900' not in h


def test_hash_rejeita_chave_vazia():
    with pytest.raises(ValueError):
        calcular_identificador_hash(b'', '12345678900')


def test_hash_rejeita_valor_vazio():
    with pytest.raises(ValueError):
        calcular_identificador_hash(CHAVE_TESTE, '')


# ---------------------------------------------------------------------------
# RepositorioIdentidadeColaboradorEmMemoria
# ---------------------------------------------------------------------------

def test_criar_se_ausente_cria_na_primeira_vez():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    identidade = _identidade('func_1', 'hash_a')

    persistida, criada = repo.criar_se_ausente(identidade)

    assert criada is True
    assert persistida.colaborador_id == 'func_1'
    assert repo.buscar_por_identificador('CPF', 'hash_a') == persistida


def test_criar_se_ausente_e_idempotente_para_mesmo_colaborador():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    identidade = _identidade('func_1', 'hash_a')

    _p1, criada1 = repo.criar_se_ausente(identidade)
    _p2, criada2 = repo.criar_se_ausente(identidade)

    assert criada1 is True
    assert criada2 is False
    assert len(repo.listar_todos()) == 1


def test_criar_se_ausente_levanta_conflito_para_colaborador_diferente():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    repo.criar_se_ausente(_identidade('func_1', 'hash_a'))

    with pytest.raises(ConflitoIdentidadeColaborador) as exc_info:
        repo.criar_se_ausente(_identidade('func_2', 'hash_a'))

    assert exc_info.value.colaborador_id_existente == 'func_1'
    assert exc_info.value.colaborador_id_tentativa == 'func_2'
    # Nunca sobrescreve -- linha original permanece intacta.
    assert repo.buscar_por_identificador('CPF', 'hash_a').colaborador_id == 'func_1'


def test_buscar_por_identificador_devolve_none_quando_ausente():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    assert repo.buscar_por_identificador('CPF', 'hash_inexistente') is None


def test_identidade_observada_rejeita_campos_vazios():
    agora = _agora()
    with pytest.raises(ValueError):
        IdentidadeColaboradorObservada(
            tipo_identificador='', identificador_hash='h', colaborador_id='c',
            origem='o', versao_chave='v1', criado_em=agora, atualizado_em=agora,
        )


# ---------------------------------------------------------------------------
# resolver_identidade_colaborador
# ---------------------------------------------------------------------------

def test_resolver_identidade_colaborador_resolvida_quando_encontrado():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    hash_ = calcular_identificador_hash(CHAVE_TESTE, '12345678900')
    repo.criar_se_ausente(_identidade('func_1', hash_))

    resolucao = resolver_identidade_colaborador(repo, 'CPF', hash_)

    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert len(resolucao.valores_confirmados) == 1
    assert resolucao.valores_confirmados[0].tipo_entidade == 'COLABORADOR'
    assert resolucao.valores_confirmados[0].entidade_id == 'func_1'


def test_resolver_identidade_colaborador_nao_encontrada_quando_ausente():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    hash_ = calcular_identificador_hash(CHAVE_TESTE, '00000000000')

    resolucao = resolver_identidade_colaborador(repo, 'CPF', hash_)

    assert resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resolucao.valores_confirmados == ()


def test_resolver_identidade_colaborador_rejeita_parametros_vazios():
    repo = RepositorioIdentidadeColaboradorEmMemoria()
    with pytest.raises(ValueError):
        resolver_identidade_colaborador(repo, '', 'hash_qualquer')
    with pytest.raises(ValueError):
        resolver_identidade_colaborador(repo, 'CPF', '')


def test_resolver_identidade_colaborador_nunca_recebe_cpf_em_claro():
    """Prova estrutural: a assinatura de resolver_identidade_colaborador
    só aceita um hash já calculado -- nunca um campo `cpf`/`valor_
    observado` cru. Se alguém adicionar um parâmetro de CPF em claro no
    futuro, este teste de assinatura falha e chama atenção."""
    import inspect
    parametros = list(inspect.signature(resolver_identidade_colaborador).parameters)
    assert parametros == ['repositorio', 'tipo_identificador', 'identificador_hash']
