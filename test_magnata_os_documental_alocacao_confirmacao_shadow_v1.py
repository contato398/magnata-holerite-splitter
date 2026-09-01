"""Testes de `magnata_os/documental/alocacao/confirmacao.py` +
`magnata_os/documental/importacao_lote/adapters/
airtable_resolver_identidade_alocacao.py` (missão "CONFIRMAÇÃO DE
ALOCAÇÃO SHADOW V1").

Persistência REAL via `RepositorioAlocacaoSQLite` (mesma disciplina de
`test_magnata_os_documental_alocacao_captura_v1.py`) -- nunca produção,
nunca Postgres real fora do job `postgres-real` de CI.

`ResolverIdentidadeAlocacaoAirtableShadow` NUNCA é chamado com Airtable
live neste arquivo -- só com `Mock()` de `LeitorAirtableSomenteLeitura`
(mesma disciplina de `test_airtable_colaboradores_esperados_
prestacao.py`). A lógica de `confirmacao.py` em si é testada com um
resolvedor sintético (dict), separado do adapter real, para isolar as
duas responsabilidades (mesmo padrão de `test_magnata_os_documental_
alocacao_wiring_vinculo_shadow_v1.py`).

CPF/nome/posto usados aqui são 100% sintéticos -- nenhum dado real da
Magnata em nenhum teste deste arquivo."""
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.captura import aplicar_vinculo_iniciado
from magnata_os.documental.alocacao.confirmacao import (
    TIPO_ENCERRAR,
    TIPO_INICIAR,
    TIPO_TRANSFERIR,
    ColaboradorNaoIdentificadoError,
    PostoNaoIdentificadoError,
    SolicitacaoConfirmacaoAlocacao,
    aplicar_confirmacao_alocacao,
)
from magnata_os.documental.alocacao.eventos import ConflitoTemporalEventoError, VinculoIniciado
from magnata_os.documental.importacao_lote.adapters.airtable_resolver_identidade_alocacao import (
    ColaboradorAmbiguoError,
    ResolverIdentidadeAlocacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import F_LOCAL_CLIENTE, TABLE_LOCAIS
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_CPF = '111.222.333-44'
_COLABORADOR_ID = 'colab-confirmacao-1'
_POSTO_A = 'posto-confirmacao-A'
_POSTO_B = 'posto-confirmacao-B'
_ORIGEM = 'confirmacao_humana_shadow'


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAlocacaoSQLite(Path(tmp) / 'confirmacao_teste.sqlite3')
        yield r
        r.fechar()


class _ResolverSintetico:
    """Resolvedor de identidade fictício, injetado -- nunca chama
    Airtable. Simula a MESMA superfície (`resolver_colaborador_id`,
    `confirmar_posto_existe`) que `ResolverIdentidadeAlocacaoAirtableShadow`
    implementa de verdade."""

    def __init__(self, cpf_para_colaborador_id: dict, postos_existentes: set):
        self._cpf_para_colaborador_id = cpf_para_colaborador_id
        self._postos_existentes = postos_existentes

    def resolver_colaborador_id(self, cpf: str):
        return self._cpf_para_colaborador_id.get(cpf)

    def confirmar_posto_existe(self, posto_id: str) -> bool:
        return posto_id in self._postos_existentes


@pytest.fixture
def resolver():
    return _ResolverSintetico(
        cpf_para_colaborador_id={_CPF: _COLABORADOR_ID},
        postos_existentes={_POSTO_A, _POSTO_B},
    )


def _vinculo_ja_aberto(repo, data=date(2026, 1, 1)):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLABORADOR_ID, data, _ORIGEM))


# ============================================================================
# SolicitacaoConfirmacaoAlocacao -- nunca deduz a data, nunca aceita entrada
# malformada (validação na construção)
# ============================================================================

def test_solicitacao_sem_data_efetiva_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=None,
            tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
        )


def test_solicitacao_com_data_como_string_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva='2026-01-01',
            tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
        )


def test_solicitacao_com_tipo_invalido_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
            tipo='remover_tudo', origem_evidencia=_ORIGEM,
        )


def test_solicitacao_transferir_sem_posto_destino_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
            tipo=TIPO_TRANSFERIR, origem_evidencia=_ORIGEM,
        )


def test_solicitacao_iniciar_com_posto_destino_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
            tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM, posto_destino_id=_POSTO_B,
        )


# ============================================================================
# aplicar_confirmacao_alocacao -- iniciar/encerrar/transferir
# ============================================================================

def test_confirmacao_iniciar_aplica_alocacao(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    )
    aloc_id = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)

    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    recente = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    assert recente.id == aloc_id
    assert recente.vigente_de == date(2026, 2, 1)
    assert recente.vigente_ate is None


def test_confirmacao_iniciar_e_idempotente(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    assert id1 == id2


def test_confirmacao_iniciar_com_conflito_temporal_propaga_erro(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    # mesma alocação já aberta, confirmação humana divergente de data --
    # nunca sobrescreve silenciosamente
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
            colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 3, 1),
            tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
        ))


def test_confirmacao_iniciar_dois_postos_e_rateio_legitimo(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_B, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    b = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_B)
    # ambos abertos ao mesmo tempo, nenhum encerra o outro -- rateio real
    assert a.vigente_ate is None
    assert b.vigente_ate is None


def test_confirmacao_encerrar_aplica_fechamento(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 30),
        tipo=TIPO_ENCERRAR, origem_evidencia=_ORIGEM,
    ))
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    recente = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    assert recente.vigente_ate == date(2026, 6, 30)


def test_confirmacao_encerrar_e_idempotente(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    solicitacao_encerrar = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 30),
        tipo=TIPO_ENCERRAR, origem_evidencia=_ORIGEM,
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao_encerrar)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao_encerrar)
    assert id1 == id2


def test_confirmacao_transferir_fecha_origem_e_abre_destino(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        tipo=TIPO_TRANSFERIR, origem_evidencia=_ORIGEM, posto_destino_id=_POSTO_B,
    ))
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    b = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_B)
    assert a.vigente_ate == date(2026, 6, 15)
    assert b.vigente_de == date(2026, 6, 15)
    assert b.vigente_ate is None


def test_confirmacao_transferir_e_idempotente(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    transferencia = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        tipo=TIPO_TRANSFERIR, origem_evidencia=_ORIGEM, posto_destino_id=_POSTO_B,
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, transferencia)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, transferencia)
    assert id1 == id2


# ============================================================================
# Identidade não confirmada -- nunca aplica com incerteza
# ============================================================================

def test_confirmacao_colaborador_nao_identificado_nunca_aplica(repo, resolver):
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf='999.999.999-99', posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    )
    with pytest.raises(ColaboradorNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    assert repo.vinculo_mais_recente_de(_COLABORADOR_ID) is None


def test_confirmacao_posto_nao_identificado_nunca_aplica(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id='posto-inexistente', data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    )
    with pytest.raises(PostoNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)


def test_confirmacao_transferir_posto_destino_nao_identificado_nunca_aplica(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        tipo=TIPO_INICIAR, origem_evidencia=_ORIGEM,
    ))
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_cpf=_CPF, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        tipo=TIPO_TRANSFERIR, origem_evidencia=_ORIGEM, posto_destino_id='posto-inexistente',
    )
    with pytest.raises(PostoNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    # origem nunca foi fechada -- falha na identificação do destino
    # nunca deixa a transferencia pela metade (mesma garantia de
    # atomicidade de aplicar_transferencia, ver captura.py)
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    assert a.vigente_ate is None


# ============================================================================
# ResolverIdentidadeAlocacaoAirtableShadow -- adapter REAL, testado só com
# Mock() de leitor, nunca Airtable live
# ============================================================================

def test_resolver_colaborador_id_por_cpf_exato():
    leitor = Mock()
    leitor.listar_funcionarios.return_value = [
        CandidatoFuncionario(func_id='func-1', cpf='111.222.333-44', nome_normalizado='FULANO'),
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.resolver_colaborador_id('111.222.333-44') == 'func-1'
    # normalização -- mesmo CPF em formato diferente ainda resolve
    assert resolver.resolver_colaborador_id('11122233344') == 'func-1'


def test_resolver_colaborador_id_nao_encontrado_devolve_none():
    leitor = Mock()
    leitor.listar_funcionarios.return_value = [
        CandidatoFuncionario(func_id='func-1', cpf='111.222.333-44', nome_normalizado='FULANO'),
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.resolver_colaborador_id('000.000.000-00') is None


def test_resolver_colaborador_id_ambiguo_levanta_erro():
    leitor = Mock()
    leitor.listar_funcionarios.return_value = [
        CandidatoFuncionario(func_id='func-1', cpf='111.222.333-44', nome_normalizado='FULANO'),
        CandidatoFuncionario(func_id='func-2', cpf='111.222.333-44', nome_normalizado='FULANO DUPLICADO'),
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    with pytest.raises(ColaboradorAmbiguoError):
        resolver.resolver_colaborador_id('111.222.333-44')


def test_confirmar_posto_existe_true():
    leitor = Mock()
    leitor.listar_registros.return_value = [
        {'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.confirmar_posto_existe('local-1') is True
    leitor.listar_registros.assert_called_once_with(table_id=TABLE_LOCAIS, fields=[F_LOCAL_CLIENTE])


def test_confirmar_posto_existe_false_quando_nao_encontrado():
    leitor = Mock()
    leitor.listar_registros.return_value = [
        {'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.confirmar_posto_existe('local-inexistente') is False
