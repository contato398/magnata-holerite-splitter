"""Testes de `resolucao_documento_prestacao.py` (missão "CORREDOR
AUTÔNOMO PÓS-CLASSIFICAÇÃO V1")."""
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao, avaliar_e_montar_pacote
from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
from magnata_os.classificacao.resolucao_documento_prestacao import (
    ContextoResolucaoDocumentoPrestacao,
    EstadoCorredorDocumentoPrestacao,
    avancar_para_inventario,
    processar_documento_com_separacao_se_necessaria,
    processar_documento_prestacao,
)
from magnata_os.classificacao.separacao_documental import estrategia_por_cpf_colaborador
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_CLIENTE_SKY = ReferenciaCanonica('CLIENTE', 'cli-sky')
_COMPETENCIA_0726 = ReferenciaCanonica('COMPETENCIA', '2026-07')


class _FonteVinculosFake:
    def __init__(self, cliente=_CLIENTE_SKY):
        self._cliente = cliente

    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(self._cliente,),
        )


class _FonteUnidadePostoFake:
    """Fonte fake de UNIDADE_POSTO (missão "EVIDÊNCIA RELACIONAL
    DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS") -- 1 posto por
    padrão, injetável para múltiplos postos quando o teste precisar."""

    def __init__(self, postos=(ReferenciaCanonica('UNIDADE_POSTO', 'posto-1'),)):
        self._postos = postos

    def resolver_unidade_posto(self, colaborador, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=self._postos,
        )


def _candidato(func_id, cpf, nome):
    return CandidatoFuncionario(func_id=func_id, cpf=cpf, nome_normalizado=nome)


def _contexto(**kwargs):
    base = dict(documento_id='doc-1', hash_sha256='a' * 64)
    base.update(kwargs)
    return ContextoResolucaoDocumentoPrestacao(**base)


# ============================================================================
# Gates antes de qualquer composição semântica
# ============================================================================

def test_texto_none_vira_gate_tecnico():
    resultado = processar_documento_prestacao(None, _contexto())
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.TEXTO_NAO_EXTRAIVEL
    assert resultado.resolucao_semantica is None


def test_tipo_desconhecido_vira_gate():
    resultado = processar_documento_prestacao('texto totalmente generico sem nenhum sinal', _contexto())
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.TIPO_DESCONHECIDO


def test_tipo_ambiguo_vira_gate():
    texto = 'Comprovante de recolhimento do FGTS -- Código de Receita: 0561'
    resultado = processar_documento_prestacao(texto, _contexto())
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.TIPO_AMBIGUO


def test_origem_divergente_vira_gate_mesmo_com_tipo_resolvido():
    resultado = processar_documento_prestacao(
        'Comprovante de recolhimento do FGTS', _contexto(tipo_origem='Holerite'),
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.ORIGEM_CONTEUDO_DIVERGENTE


def test_tipo_sem_perfil_cadastrado_vira_gate():
    """'Certidão' é um tipo real do motor semântico (`produtores_
    evidencia_temporal.py`) mas ainda sem perfil de aplicabilidade
    cadastrado nesta missão -- gate honesto, nunca um perfil inventado
    para preencher a lacuna."""
    resultado = processar_documento_prestacao('Certidão Negativa de Débitos -- Válida até 01/01/2027', _contexto())
    assert resultado.tipo_documental == 'Certidão'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.PERFIL_NAO_CADASTRADO


# ============================================================================
# Resolução dimensional completa -- auto-avanço
# ============================================================================

def test_holerite_completo_avanca_automaticamente():
    """Cadeia completa colaborador→posto→cliente→pacote. VINCULO fica
    NAO_APLICAVEL (revertido pelo "ADENDO PRÉ-MERGE AO PR #106" --
    nenhuma fonte real de vínculo existe ainda; nunca fabricar
    resolução para preencher a dimensão)."""
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(), fonte_unidade_posto=_FonteUnidadePostoFake(),
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert resultado.resolucao_semantica.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    assert resultado.resolucao_semantica.pronto_para_routing_logico is True
    resolucao_vinculo = next(
        r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.VINCULO
    )
    resolucao_unidade_posto = next(
        r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.UNIDADE_POSTO
    )
    assert resolucao_vinculo.estado == EstadoResolucaoDimensao.NAO_APLICAVEL
    assert resolucao_unidade_posto.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_competencia_esperada_ausente_vira_revisao_nunca_avanca_silenciosamente():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        candidatos_colaborador=candidatos, fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA


def test_competencia_divergente_impede_auto_avanco():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        competencia_esperada=(2026, 6), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    dimensao_competencia = next(
        r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.COMPETENCIA
    )
    assert dimensao_competencia.estado == EstadoResolucaoDimensao.CONFLITO


def test_colaborador_nao_encontrado_impede_auto_avanco_mas_nunca_crasha():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto(
        competencia_esperada=(2026, 7), candidatos_colaborador=(), fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA


def test_extrato_com_cliente_direto_avanca_sem_colaborador():
    texto = 'Extrato da Folha de Pagamento -- Julho/2026\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto(
        competencia_esperada=(2026, 7), cliente_direto=_CLIENTE_SKY,
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_dctf_broadcast_avanca_sem_cliente_nem_colaborador():
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto(competencia_esperada=(2026, 7)))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    resolucao_cliente = next(
        r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.CLIENTE
    )
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.NAO_APLICAVEL


# ============================================================================
# Inventário + readiness + pacote lógico (Fase 14/15/19)
# ============================================================================

def _resultado_holerite_resolvido():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    return processar_documento_prestacao(texto, _contexto(
        competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(), fonte_unidade_posto=_FonteUnidadePostoFake(),
    ))


def test_avancar_para_inventario_gera_item_e_alimenta_pacote_pronto():
    resultado = _resultado_holerite_resolvido()
    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink)
    assert len(itens) == 1
    assert sink.total_itens() == 1

    politica = PoliticaRequisitosPrestacao(version='v1', requisitos_base=(RequisitoDocumentalPrestacao('Holerite'),))
    pacote = avaliar_e_montar_pacote(_CLIENTE_SKY, _COMPETENCIA_0726, resultado.resolucao_semantica, sink, politica)
    assert pacote.estado == EstadoPacotePrestacao.PRONTO


def test_avancar_para_inventario_e_idempotente():
    resultado = _resultado_holerite_resolvido()
    sink = InventarioPrestacaoEmMemoria()
    avancar_para_inventario(resultado, sink)
    avancar_para_inventario(resultado, sink)
    avancar_para_inventario(resultado, sink)
    assert sink.total_itens() == 1


def test_avancar_para_inventario_nunca_age_sem_auto_avanco():
    texto = 'Comprovante de recolhimento do FGTS -- Código de Receita: 0561'
    resultado = processar_documento_prestacao(texto, _contexto())
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.TIPO_AMBIGUO
    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink)
    assert itens == ()
    assert sink.total_itens() == 0


# ============================================================================
# Separação (Fase 7): "não assumir que 1 PDF = 1 documento lógico"
# ============================================================================

def test_documento_unitario_processa_como_um_so():
    paginas = ['Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44']
    resultados = processar_documento_com_separacao_se_necessaria(
        paginas, _contexto(competencia_esperada=(2026, 7), fonte_vinculos=_FonteVinculosFake()),
    )
    assert len(resultados) == 1


def test_documento_master_separa_por_cpf_e_reentra_cada_filho_no_motor():
    paginas = [
        'CPF: 111.222.333-44\nFolha de Ponto\n29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00',
        'CPF: 555.666.777-88\nFolha de Ponto\n29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00',
    ]
    indice = {'11122233344': ('func-1', 'JOAO'), '55566677788': ('func-2', 'MARIA')}
    resultados = processar_documento_com_separacao_se_necessaria(
        paginas, _contexto(
            competencia_esperada=(2026, 4),
            candidatos_colaborador=[_candidato('func-1', '11122233344', 'JOAO'), _candidato('func-2', '55566677788', 'MARIA')],
            fonte_vinculos=_FonteVinculosFake(),
        ),
        identificar_pagina=estrategia_por_cpf_colaborador(indice),
    )
    assert len(resultados) == 2
    ids = {r.documento_id for r in resultados}
    assert ids == {'doc-1:func-1', 'doc-1:func-2'}
