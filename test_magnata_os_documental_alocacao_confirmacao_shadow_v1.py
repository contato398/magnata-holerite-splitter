"""Testes de `magnata_os/documental/alocacao/confirmacao.py` +
`comparacao_airtable.py` + `magnata_os/documental/importacao_lote/
adapters/airtable_resolver_identidade_alocacao.py` (missão "CONFIRMAÇÃO
DE ALOCAÇÃO SHADOW V1").

Persistência REAL via `RepositorioAlocacaoSQLite` (mesma disciplina de
`test_magnata_os_documental_alocacao_captura_v1.py`) -- nunca produção,
nunca Postgres real fora do job `postgres-real` de CI (ver
`test_magnata_os_documental_alocacao_postgres_real.py` para a
contraparte Postgres desta mesma missão).

`ResolverIdentidadeAlocacaoAirtableShadow` NUNCA é chamado com Airtable
live neste arquivo -- só com `Mock()` de `LeitorAirtableSomenteLeitura`
(mesma disciplina de `test_airtable_colaboradores_esperados_
prestacao.py`). A lógica de `confirmacao.py`/`comparacao_airtable.py`
em si é testada com um resolvedor/snapshot sintético (dict), separado
do adapter real, para isolar as responsabilidades.

CPF/nome/posto usados aqui são 100% sintéticos -- nenhum dado real da
Magnata em nenhum teste deste arquivo."""
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.captura import aplicar_vinculo_iniciado
from magnata_os.documental.alocacao.comparacao_airtable import (
    EstadoComparacaoAirtable,
    comparar_colaborador_shadow_com_airtable,
    comparar_postos,
)
from magnata_os.documental.alocacao.confirmacao import (
    ACAO_ADICIONAR_RATEIO,
    ACAO_ENCERRAR,
    ACAO_INICIAR,
    ACAO_REMOVER_RATEIO,
    ACAO_TRANSFERIR,
    ColaboradorNaoIdentificadoError,
    PostoNaoIdentificadoError,
    SolicitacaoConfirmacaoAlocacao,
    aplicar_confirmacao_alocacao,
)
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.documental.alocacao.eventos import ConflitoTemporalEventoError, EventoForaDeOrdemError, VinculoIniciado
from magnata_os.documental.importacao_lote.adapters.airtable_resolver_identidade_alocacao import (
    ColaboradorAmbiguoError,
    ResolverIdentidadeAlocacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_FUNC,
    TABLE_LOCAIS,
)
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
    """Resolvedor/snapshot de identidade fictício, injetado -- nunca
    chama Airtable. Simula a MESMA superfície que
    `ResolverIdentidadeAlocacaoAirtableShadow` implementa de verdade."""

    def __init__(self, colaboradores_existentes: set, postos_existentes: set, postos_atuais: dict = None):
        self._colaboradores_existentes = colaboradores_existentes
        self._postos_existentes = postos_existentes
        self._postos_atuais = postos_atuais or {}

    def confirmar_colaborador_existe(self, colaborador_id: str) -> bool:
        return colaborador_id in self._colaboradores_existentes

    def confirmar_posto_existe(self, posto_id: str) -> bool:
        return posto_id in self._postos_existentes

    def postos_atuais_do_colaborador(self, colaborador_id: str):
        if colaborador_id not in self._postos_atuais:
            raise KeyError('colaborador sem snapshot configurado no fake')
        return self._postos_atuais[colaborador_id]


@pytest.fixture
def resolver():
    return _ResolverSintetico(
        colaboradores_existentes={_COLABORADOR_ID},
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
            colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=None,
            acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
        )


def test_solicitacao_com_data_como_string_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva='2026-01-01',
            acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
        )


def test_solicitacao_com_acao_invalida_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
            acao='remover_tudo', origem_confirmacao=_ORIGEM,
        )


def test_solicitacao_transferir_sem_posto_destino_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
            acao=ACAO_TRANSFERIR, origem_confirmacao=_ORIGEM,
        )


def test_solicitacao_iniciar_com_posto_destino_falha_na_construcao():
    with pytest.raises(ValueError):
        SolicitacaoConfirmacaoAlocacao(
            colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
            acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM, posto_destino_id=_POSTO_B,
        )


# ============================================================================
# aplicar_confirmacao_alocacao -- iniciar/encerrar/transferir/rateio
# ============================================================================

def test_confirmacao_iniciar_aplica_alocacao(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
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
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    assert id1 == id2


def test_confirmacao_iniciar_com_conflito_temporal_propaga_erro(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    # mesma alocação já aberta, confirmação humana divergente de data --
    # nunca sobrescreve silenciosamente
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
            colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 3, 1),
            acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
        ))


def test_confirmacao_iniciar_sem_vinculo_aberto_e_evento_fora_de_ordem(repo, resolver):
    # nenhum VinculoIniciado aplicado -- colaborador existe no Airtable
    # (segundo o resolver), mas nao tem vinculo aberto no shadow
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(EventoForaDeOrdemError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)


def test_confirmacao_encerrar_sem_alocacao_previa_e_evento_fora_de_ordem(repo, resolver):
    _vinculo_ja_aberto(repo)
    # vinculo aberto, mas nenhuma alocacao foi iniciada neste posto ainda
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_ENCERRAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(EventoForaDeOrdemError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)


def test_confirmacao_adicionar_rateio_abre_segundo_posto_sem_fechar_o_primeiro(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_B, data_efetiva=date(2026, 2, 1),
        acao=ACAO_ADICIONAR_RATEIO, origem_confirmacao=_ORIGEM,
    ))
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    b = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_B)
    # ambos abertos ao mesmo tempo, nenhum fecha o outro -- rateio real
    assert a.vigente_ate is None
    assert b.vigente_ate is None


def test_confirmacao_encerrar_aplica_fechamento(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 30),
        acao=ACAO_ENCERRAR, origem_confirmacao=_ORIGEM,
    ))
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    recente = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    assert recente.vigente_ate == date(2026, 6, 30)


def test_confirmacao_encerrar_e_idempotente(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    solicitacao_encerrar = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 30),
        acao=ACAO_ENCERRAR, origem_confirmacao=_ORIGEM,
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao_encerrar)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao_encerrar)
    assert id1 == id2


def test_confirmacao_remover_rateio_fecha_so_um_posto(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_B, data_efetiva=date(2026, 2, 1),
        acao=ACAO_ADICIONAR_RATEIO, origem_confirmacao=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_B, data_efetiva=date(2026, 5, 1),
        acao=ACAO_REMOVER_RATEIO, origem_confirmacao=_ORIGEM,
    ))
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    b = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_B)
    assert a.vigente_ate is None  # posto A nunca foi tocado
    assert b.vigente_ate == date(2026, 5, 1)


def test_confirmacao_transferir_fecha_origem_e_abre_destino(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao=_ORIGEM, posto_destino_id=_POSTO_B,
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
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    transferencia = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao=_ORIGEM, posto_destino_id=_POSTO_B,
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, transferencia)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, transferencia)
    assert id1 == id2


def test_confirmacao_retry_apos_falha_no_meio_da_transferencia_funciona(repo, resolver):
    """Simula 'falha no meio' via um resolver que quebra na 2a chamada
    de confirmar_posto_existe do destino -- a 1a tentativa deve deixar
    o estado intacto (nunca fechado pela metade), e a 2a tentativa
    (retry, sem a falha) deve completar normalmente."""
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))

    class _ResolverQuebraNoDestino(_ResolverSintetico):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.chamadas_posto_destino = 0

        def confirmar_posto_existe(self, posto_id: str) -> bool:
            if posto_id == _POSTO_B:
                self.chamadas_posto_destino += 1
                if self.chamadas_posto_destino == 1:
                    raise RuntimeError('falha simulada de rede na 1a tentativa')
            return super().confirmar_posto_existe(posto_id)

    resolver_instavel = _ResolverQuebraNoDestino(
        colaboradores_existentes={_COLABORADOR_ID}, postos_existentes={_POSTO_A, _POSTO_B})
    transferencia = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao=_ORIGEM, posto_destino_id=_POSTO_B,
    )
    with pytest.raises(RuntimeError):
        aplicar_confirmacao_alocacao(repo, resolver_instavel, transferencia)

    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a_apos_falha = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    assert a_apos_falha.vigente_ate is None  # origem intacta apos a falha

    # retry -- sem a falha simulada desta vez
    aplicar_confirmacao_alocacao(repo, resolver_instavel, transferencia)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    b = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_B)
    assert a.vigente_ate == date(2026, 6, 15)
    assert b.vigente_de == date(2026, 6, 15)


# ============================================================================
# Identidade não confirmada -- nunca aplica com incerteza (inclui
# resiliência: Airtable indisponível nunca corrompe o domínio/captura)
# ============================================================================

def test_confirmacao_colaborador_nao_identificado_nunca_aplica(repo, resolver):
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id='colab-inexistente', posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(ColaboradorNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    assert repo.vinculo_mais_recente_de(_COLABORADOR_ID) is None


def test_confirmacao_posto_nao_identificado_nunca_aplica(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id='posto-inexistente', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(PostoNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)


def test_confirmacao_transferir_posto_destino_nao_identificado_nunca_aplica(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao=_ORIGEM, posto_destino_id='posto-inexistente',
    )
    with pytest.raises(PostoNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    # origem nunca foi fechada -- falha na identificação do destino
    # nunca deixa a transferencia pela metade (mesma garantia de
    # atomicidade de aplicar_transferencia, ver captura.py)
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    a = repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A)
    assert a.vigente_ate is None


def test_confirmacao_airtable_indisponivel_nunca_corrompe_o_dominio(repo):
    """Resolver que levanta uma falha genuína de indisponibilidade
    (nunca "não encontrado") -- a confirmação deve propagar o erro e
    nada deve ser escrito no shadow (nem parcialmente)."""
    _vinculo_ja_aberto(repo)

    class _ResolverIndisponivel:
        def confirmar_colaborador_existe(self, colaborador_id: str) -> bool:
            raise ConnectionError('Airtable indisponivel (simulado)')

        def confirmar_posto_existe(self, posto_id: str) -> bool:
            raise ConnectionError('Airtable indisponivel (simulado)')

    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(ConnectionError):
        aplicar_confirmacao_alocacao(repo, _ResolverIndisponivel(), solicitacao)

    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    assert repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A) is None


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


def test_confirmar_colaborador_existe_true_e_false():
    leitor = Mock()
    leitor.listar_funcionarios.return_value = [
        CandidatoFuncionario(func_id='func-1', cpf='111.222.333-44', nome_normalizado='FULANO'),
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.confirmar_colaborador_existe('func-1') is True
    assert resolver.confirmar_colaborador_existe('func-inexistente') is False


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


def test_postos_atuais_do_colaborador_le_locais_de_trabalho():
    leitor = Mock()
    leitor.listar_registros.return_value = [
        {'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1', 'local-2']}},
        {'id': 'func-2', 'fields': {F_FUNC_LOCAIS: ['local-3']}},
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.postos_atuais_do_colaborador('func-1') == frozenset({'local-1', 'local-2'})
    leitor.listar_registros.assert_called_once_with(table_id=TABLE_FUNC, fields=[F_FUNC_LOCAIS])


def test_postos_atuais_do_colaborador_vazio_quando_sem_vinculo():
    leitor = Mock()
    leitor.listar_registros.return_value = [
        {'id': 'func-1', 'fields': {F_FUNC_LOCAIS: []}},
    ]
    resolver = ResolverIdentidadeAlocacaoAirtableShadow(leitor)
    assert resolver.postos_atuais_do_colaborador('func-1') == frozenset()


# ============================================================================
# comparacao_airtable.py -- 5 estados diagnósticos, nunca reconciliação
# ============================================================================

def test_comparar_postos_consistente_quando_ambos_vazios():
    assert comparar_postos(frozenset(), frozenset()) == EstadoComparacaoAirtable.CONSISTENTE


def test_comparar_postos_consistente_quando_iguais():
    assert comparar_postos(frozenset({'p1'}), frozenset({'p1'})) == EstadoComparacaoAirtable.CONSISTENTE


def test_comparar_postos_diferente_quando_ambos_tem_dado_mas_divergem():
    assert comparar_postos(frozenset({'p1'}), frozenset({'p2'})) == EstadoComparacaoAirtable.DIFERENTE


def test_comparar_postos_magnata_sem_dado():
    assert comparar_postos(frozenset(), frozenset({'p1'})) == EstadoComparacaoAirtable.MAGNATA_SEM_DADO


def test_comparar_postos_airtable_sem_vinculo():
    assert comparar_postos(frozenset({'p1'}), frozenset()) == EstadoComparacaoAirtable.AIRTABLE_SEM_VINCULO


def test_comparar_postos_ambiguo_quando_airtable_nao_apuravel():
    assert comparar_postos(frozenset({'p1'}), None) == EstadoComparacaoAirtable.AMBIGUO


def test_comparar_colaborador_shadow_com_airtable_consistente(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    snapshot = _ResolverSintetico(
        colaboradores_existentes={_COLABORADOR_ID}, postos_existentes={_POSTO_A},
        postos_atuais={_COLABORADOR_ID: frozenset({_POSTO_A})},
    )
    estado = comparar_colaborador_shadow_com_airtable(repo, snapshot, _COLABORADOR_ID, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.CONSISTENTE


def test_comparar_colaborador_shadow_com_airtable_diferente(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    snapshot = _ResolverSintetico(
        colaboradores_existentes={_COLABORADOR_ID}, postos_existentes={_POSTO_B},
        postos_atuais={_COLABORADOR_ID: frozenset({_POSTO_B})},
    )
    estado = comparar_colaborador_shadow_com_airtable(repo, snapshot, _COLABORADOR_ID, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.DIFERENTE


def test_comparar_colaborador_shadow_com_airtable_magnata_sem_dado(repo):
    # colaborador nunca teve vinculo/alocacao no shadow
    snapshot = _ResolverSintetico(
        colaboradores_existentes={_COLABORADOR_ID}, postos_existentes={_POSTO_A},
        postos_atuais={_COLABORADOR_ID: frozenset({_POSTO_A})},
    )
    estado = comparar_colaborador_shadow_com_airtable(repo, snapshot, _COLABORADOR_ID, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.MAGNATA_SEM_DADO


def test_comparar_colaborador_shadow_com_airtable_airtable_sem_vinculo(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    snapshot = _ResolverSintetico(
        colaboradores_existentes={_COLABORADOR_ID}, postos_existentes=set(),
        postos_atuais={_COLABORADOR_ID: frozenset()},
    )
    estado = comparar_colaborador_shadow_com_airtable(repo, snapshot, _COLABORADOR_ID, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.AIRTABLE_SEM_VINCULO


def test_comparar_colaborador_shadow_com_airtable_ambiguo_quando_snapshot_falha(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))

    class _SnapshotQueFalha:
        def postos_atuais_do_colaborador(self, colaborador_id: str):
            raise ColaboradorAmbiguoError('2 colaboradores com o mesmo CPF no Airtable')

    estado = comparar_colaborador_shadow_com_airtable(repo, _SnapshotQueFalha(), _COLABORADOR_ID, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.AMBIGUO


def test_comparar_colaborador_shadow_com_airtable_nao_derruba_quando_airtable_indisponivel(repo, resolver):
    """FASE 8, caso 16 -- Airtable indisponível nunca corrompe/derruba o
    diagnóstico; vira AMBIGUO, nunca uma exceção propagada."""
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))

    class _SnapshotIndisponivel:
        def postos_atuais_do_colaborador(self, colaborador_id: str):
            raise ConnectionError('Airtable indisponivel (simulado)')

    estado = comparar_colaborador_shadow_com_airtable(
        repo, _SnapshotIndisponivel(), _COLABORADOR_ID, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.AMBIGUO


# ============================================================================
# FASE 5 -- pipeline completo: confirmação humana -> validação de
# identidade -> evento canônico -> captura temporal -> persistência
# shadow -> LEITURA HISTÓRICA PARA CONFERÊNCIA (o corredor real já
# resolve UNIDADE_POSTO a partir do que a confirmação persistiu, via o
# contrato `FonteUnidadePostoPrestacao` que `RepositorioAlocacaoSQLite`
# já implementa -- reaproveitado, nunca reimplementado aqui).
# ============================================================================

def test_confirmacao_alimenta_leitura_historica_do_corredor(repo, resolver):
    _vinculo_ja_aberto(repo, data=date(2025, 1, 1))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 1, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    ))
    resultado = repo.resolver_unidade_posto(
        ReferenciaCanonica('COLABORADOR', _COLABORADOR_ID), ReferenciaCanonica('COMPETENCIA', '2026-06'))
    assert resultado.dimensao == DimensaoResolucao.UNIDADE_POSTO
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', _POSTO_A),)
