"""Testes de `composicao_corredor_readonly.py` (missão "CONSTRUIR
ORQUESTRADOR REAL READ-ONLY DO CORREDOR V2"). Prova que os adapters
REAIS (já construídos em missões anteriores desta sessão) compõem,
sem nenhum ajuste, através de `ExecucaoCorredorReadonly` -- só
`Mock()` local para o transporte Airtable, nunca rede real. Casos
mapeados aos §25/§27/§28/§30/§31 da missão (nível de borda)."""
from unittest.mock import Mock

from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
)
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import F_EXT_CLIENTE, TABLE_EXTRATO
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import F_FUNC_LOCAIS, TABLE_FUNC
from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly
from magnata_os.documental.importacao_lote.contratos import CandidatoCliente, CandidatoFuncionario

_CNPJ_A = '11.222.333/0001-44'
_CLIENTE_A_ID = 'recCLIENTE_A'


def _leitor_vazio():
    leitor = Mock()
    leitor.listar_registros.return_value = []
    leitor.listar_clientes.return_value = []
    return leitor


def test_dctf_broadcast_via_adapters_reais_avanca():
    leitor = _leitor_vazio()
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    resultados = execucao.processar_documento(
        'doc-dctf-1', 'a' * 64, texto=texto, clientes_broadcast=(ReferenciaCanonica('CLIENTE', 'cli-x'),),
    )
    assert resultados[0].resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert len(resultados[0].itens_inventario) == 1
    # Nenhuma chamada ao Airtable foi necessária para um documento
    # broadcast (nenhuma dimensão consulta fonte real aqui).
    leitor.listar_registros.assert_not_called()


def test_extrato_com_cnpj_real_resolve_cliente_direto_via_adapter_real():
    leitor = Mock()
    leitor.listar_registros.return_value = []
    leitor.listar_clientes.return_value = [
        CandidatoCliente(cliente_id=_CLIENTE_A_ID, cnpj=_CNPJ_A, nome_normalizado='CLIENTE A LTDA'),
    ]
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    texto = f'Extrato Mensal\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026'
    resultados = execucao.processar_documento('doc-ext-1', 'b' * 64, texto=texto)
    resultado = resultados[0]
    assert resultado.resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert resultado.itens_inventario[0].cliente == ReferenciaCanonica('CLIENTE', _CLIENTE_A_ID)
    leitor.listar_clientes.assert_called_once_with()


def test_sky_ciclo_base_julho_snapshot_comprovado_julho_unidade_posto_junho_nao_encontrada():
    """Caso obrigatório (§30 da missão) via composição de borda com
    adapters reais: `competencia_snapshot_comprovada` só para Julho
    nunca prova UNIDADE_POSTO para Junho (competência esperada real do
    SKY Tatuí, base Julho -1). Nenhum override."""
    leitor = Mock()
    leitor.listar_registros.side_effect = lambda **kwargs: (
        [{'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}}] if kwargs.get('table_id') == TABLE_FUNC else []
    )
    leitor.listar_clientes.return_value = []
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), competencia_snapshot_comprovada=(2026, 7),
    )
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: 111.222.333-44'
    resultados = execucao.processar_documento(
        'doc-hol-sky', 'c' * 64, texto=texto, cliente_do_ciclo=REFERENCIA_CLIENTE_SKY_TATUI,
        candidatos_colaborador=[CandidatoFuncionario(func_id='func-1', cpf='11122233344', nome_normalizado='JOAO')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r.estado for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.COMPETENCIA] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_idempotencia_reprocessar_documento_via_borda_nao_duplica_inventario():
    leitor = Mock()
    leitor.listar_registros.return_value = []
    leitor.listar_clientes.return_value = [
        CandidatoCliente(cliente_id=_CLIENTE_A_ID, cnpj=_CNPJ_A, nome_normalizado='CLIENTE A LTDA'),
    ]
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    texto = f'Extrato Mensal\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026'
    execucao.processar_documento('doc-ext-dup', 'd' * 64, texto=texto)
    execucao.processar_documento('doc-ext-dup', 'd' * 64, texto=texto)
    competencia_ref = ReferenciaCanonica('COMPETENCIA', '2026-07')
    itens = execucao.sink.listar(ReferenciaCanonica('CLIENTE', _CLIENTE_A_ID), competencia_ref)
    assert len(itens) == 1


def test_rejeita_pdf_e_texto_ao_mesmo_tempo():
    import pytest

    execucao = ExecucaoCorredorReadonly(_leitor_vazio(), ContextoCicloPrestacao((2026, 7)))
    with pytest.raises(ValueError):
        execucao.processar_documento('doc-x', 'e' * 64, pdf_bytes=b'x', texto='y')


def test_rejeita_nem_pdf_nem_texto():
    import pytest

    execucao = ExecucaoCorredorReadonly(_leitor_vazio(), ContextoCicloPrestacao((2026, 7)))
    with pytest.raises(ValueError):
        execucao.processar_documento('doc-x', 'e' * 64)
