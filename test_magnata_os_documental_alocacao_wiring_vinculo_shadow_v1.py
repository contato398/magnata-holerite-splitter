"""Testes de `magnata_os/documental/alocacao/wiring.py` (missão
"WIRING REAL DE VÍNCULO V1 EM MODO SHADOW"). Prova
`DOCUMENTO -> EXTRAÇÃO EXISTENTE -> IDENTIDADE -> EVENTO CANÔNICO ->
CAPTURA` usando o extrator REAL já existente
(`src.sync_new_employees.extrair_dados_holerite`, nunca reimplementado)
contra TEXTO SINTÉTICO (nunca um holerite real da Magnata) -- sempre
persistindo em `RepositorioAlocacaoSQLite` efêmero (shadow), nunca
Postgres de produção.

Formato de texto sintético fiel ao regex real (mesmo padrão já
documentado nos comentários de `sync_new_employees.py`: cabeçalho
"<código> <NOME> <CBO> <depto> <filial>" + linha "<CARGO> Admissão:
DD/MM/AAAA" + CPF mascarado) -- nome/CPF sempre claramente fictícios."""
import tempfile
from datetime import date
from pathlib import Path

import pytest

from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.captura import aplicar_vinculo_iniciado
from magnata_os.documental.alocacao.eventos import ConflitoTemporalEventoError
from magnata_os.documental.alocacao.wiring import (
    ColaboradorNaoIdentificadoError,
    CpfAusenteError,
    DataEfetivaAusenteError,
    construir_vinculo_iniciado_de_holerite,
)


def _texto_holerite_sintetico(
    nome='FULANO DE TAL EXEMPLO', cpf='111.222.333-44',
    admissao='10/01/2026', cargo='CARGO EXEMPLO',
) -> str:
    return (
        f'123 {nome} 999999 1 1\n'
        f'{cargo} Admissão: {admissao}\n'
        f'CPF: {cpf}\n'
    )


def _resolver_sintetico(mapa: dict):
    def _resolver(cpf: str):
        return mapa.get(cpf.strip())
    return _resolver


@pytest.fixture
def repo():
    # tempfile.TemporaryDirectory() em vez do fixture tmp_path do
    # pytest -- mesma disciplina já usada em
    # test_magnata_os_documental_alocacao_{vigencia_historica,captura_v1}.py
    # (o fixture tmp_path do pytest esbarra num PermissionError real
    # deste sandbox Windows ao escanear seu diretório-base compartilhado
    # entre execuções; tempfile.TemporaryDirectory() cria/limpa um
    # diretório isolado por teste, sem esse problema).
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAlocacaoSQLite(Path(tmp) / 'wiring_teste.sqlite3')
        yield r
        r.fechar()


# ============================================================================
# construir_vinculo_iniciado_de_holerite -- extração real + identidade
# ============================================================================

def test_documento_sintetico_produz_vinculo_iniciado_correto():
    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-1'})
    evento = construir_vinculo_iniciado_de_holerite(_texto_holerite_sintetico(), resolver)
    assert evento.colaborador_id == 'colab-wiring-1'
    assert evento.data_efetiva == date(2026, 1, 10)
    assert evento.origem_evidencia == 'holerite_data_admissao'


def test_cpf_ausente_no_documento_falha_explicitamente():
    texto = '123 FULANO DE TAL EXEMPLO 999999 1 1\nCARGO EXEMPLO Admissão: 10/01/2026\n'
    with pytest.raises(CpfAusenteError):
        construir_vinculo_iniciado_de_holerite(texto, _resolver_sintetico({}))


def test_documento_sem_data_efetiva_falha_explicitamente():
    texto = '123 FULANO DE TAL EXEMPLO 999999 1 1\nCPF: 111.222.333-44\n'
    with pytest.raises(DataEfetivaAusenteError):
        construir_vinculo_iniciado_de_holerite(texto, _resolver_sintetico({}))


def test_colaborador_nao_identificado_falha_explicitamente():
    resolver = _resolver_sintetico({})  # nenhum CPF conhecido
    with pytest.raises(ColaboradorNaoIdentificadoError):
        construir_vinculo_iniciado_de_holerite(_texto_holerite_sintetico(), resolver)


def test_nunca_escolhe_candidato_arbitrario_quando_cpf_nao_bate_exato():
    """resolver_colaborador_id devolve None para CPF nao mapeado --
    mesmo com outros colaboradores no mapa, nunca "escolhe o mais
    proximo" nem primeiro disponivel."""
    resolver = _resolver_sintetico({'999.888.777-66': 'colab-outro'})
    with pytest.raises(ColaboradorNaoIdentificadoError):
        construir_vinculo_iniciado_de_holerite(_texto_holerite_sintetico(), resolver)


# ============================================================================
# Fase 8 -- casos adversariais, fim a fim (extração real -> captura real)
# ============================================================================

def test_mesmo_documento_processado_2x_e_idempotente(repo):
    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-2'})
    texto = _texto_holerite_sintetico(cpf='111.222.333-44')

    evento1 = construir_vinculo_iniciado_de_holerite(texto, resolver)
    evento2 = construir_vinculo_iniciado_de_holerite(texto, resolver)
    id1 = aplicar_vinculo_iniciado(repo, evento1)
    id2 = aplicar_vinculo_iniciado(repo, evento2)
    assert id1 == id2
    assert repo.vinculo_mais_recente_de('colab-wiring-2').id == id1


def test_dois_documentos_com_mesma_admissao_sao_idempotentes(repo):
    """2 "holerites" sintéticos diferentes (arquivos distintos, mesmo
    colaborador/mesma Data de Admissão -- cenário real de reenvio)
    produzem o MESMO vínculo, nunca duplicado."""
    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-3'})
    texto_a = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='10/01/2026')
    texto_b = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='10/01/2026', cargo='CARGO EXEMPLO 2')

    id_a = aplicar_vinculo_iniciado(repo, construir_vinculo_iniciado_de_holerite(texto_a, resolver))
    id_b = aplicar_vinculo_iniciado(repo, construir_vinculo_iniciado_de_holerite(texto_b, resolver))
    assert id_a == id_b


def test_duas_datas_de_admissao_conflitantes_levantam_conflito(repo):
    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-4'})
    texto_a = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='10/01/2026')
    texto_b = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='15/03/2026')

    aplicar_vinculo_iniciado(repo, construir_vinculo_iniciado_de_holerite(texto_a, resolver))
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_vinculo_iniciado(repo, construir_vinculo_iniciado_de_holerite(texto_b, resolver))


def test_readmissao_via_documentos_reais_cria_novo_vinculo(repo):
    from magnata_os.documental.alocacao.captura import aplicar_vinculo_encerrado
    from magnata_os.documental.alocacao.eventos import VinculoEncerrado

    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-5'})
    texto_admissao_1 = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='10/01/2025')
    id1 = aplicar_vinculo_iniciado(repo, construir_vinculo_iniciado_de_holerite(texto_admissao_1, resolver))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado('colab-wiring-5', date(2025, 6, 30), 'sintetico_teste'))

    texto_admissao_2 = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='05/01/2026')
    id2 = aplicar_vinculo_iniciado(repo, construir_vinculo_iniciado_de_holerite(texto_admissao_2, resolver))
    assert id1 != id2
    assert repo.vinculo_mais_recente_de('colab-wiring-5').id == id2


def test_falha_do_repositorio_e_retry_apos_falha(repo, monkeypatch):
    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-6'})
    texto = _texto_holerite_sintetico(cpf='111.222.333-44')
    evento = construir_vinculo_iniciado_de_holerite(texto, resolver)

    original = repo.registrar_vinculo

    def _falha(*args, **kwargs):
        raise RuntimeError('falha simulada do repositorio')

    monkeypatch.setattr(repo, 'registrar_vinculo', _falha)
    with pytest.raises(RuntimeError):
        aplicar_vinculo_iniciado(repo, evento)

    monkeypatch.setattr(repo, 'registrar_vinculo', original)
    vinculo_id = aplicar_vinculo_iniciado(repo, evento)  # retry real, sem mock
    assert repo.vinculo_mais_recente_de('colab-wiring-6').id == vinculo_id


def test_sequencia_completa_documento_real_ate_persistencia_shadow(repo):
    """DOCUMENTO (sintético) -> EXTRAÇÃO EXISTENTE -> IDENTIDADE ->
    EVENTO CANÔNICO -> CAPTURA -- fim a fim, contra o repositório
    shadow (SQLite efêmero, nunca Postgres de produção)."""
    resolver = _resolver_sintetico({'111.222.333-44': 'colab-wiring-7'})
    texto = _texto_holerite_sintetico(cpf='111.222.333-44', admissao='02/02/2026')
    evento = construir_vinculo_iniciado_de_holerite(texto, resolver)
    aplicar_vinculo_iniciado(repo, evento)

    recente = repo.vinculo_mais_recente_de('colab-wiring-7')
    assert recente.data_admissao == date(2026, 2, 2)
    assert recente.data_desligamento is None
