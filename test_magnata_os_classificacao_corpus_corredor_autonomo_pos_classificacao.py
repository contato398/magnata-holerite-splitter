"""Corpus E2E heterogêneo do corredor pós-classificação (missão
"CORREDOR AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fase 24) -- os 10 casos
especificados (A-J), provando ponta a ponta: texto -> tipo -> perfil ->
identificação -> competência -> cliente -> inventário -> readiness ->
pacote lógico, tudo automático quando não há gate real, e parada
explícita em cada gate (conflito/ambiguidade/técnico/competência
ausente).

Métrica (Fase 23): distingue AUTO_CLASSIFICADOS (tipo resolvido) de
AUTO_AVANCOU_COMPLETO (RESOLVIDO_E_AVANCOU -- corredor inteiro
automático até o item de inventário) -- a segunda é a métrica mais
importante (Fase 23: "a segunda é a métrica mais importante"), nunca
confundida com a primeira."""
import dataclasses

from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao
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
from magnata_os.classificacao.separacao_documental import estrategia_por_cnpj_cliente
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_CLIENTE_SKY = ReferenciaCanonica('CLIENTE', 'cli-sky')
_CLIENTE_ACME = ReferenciaCanonica('CLIENTE', 'cli-acme')
_COMPETENCIA_0726 = ReferenciaCanonica('COMPETENCIA', '2026-07')


class _FonteVinculosFake:
    def __init__(self, cliente=_CLIENTE_SKY):
        self._cliente = cliente

    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(self._cliente,),
        )


def _candidato(func_id, cpf, nome):
    return CandidatoFuncionario(func_id=func_id, cpf=cpf, nome_normalizado=nome)


def _contexto(documento_id, **kwargs):
    base = dict(documento_id=documento_id, hash_sha256='a' * 64)
    base.update(kwargs)
    return ContextoResolucaoDocumentoPrestacao(**base)


# ============================================================================
# CASO A -- Holerite completo -> inventário -> readiness -> pacote PRONTO
# ============================================================================

def test_caso_a_holerite_completo_ate_pacote_pronto():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-a', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU

    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink)
    assert len(itens) == 1 and itens[0].colaborador.entidade_id == 'func-1'

    politica = PoliticaRequisitosPrestacao(version='v1', requisitos_base=(RequisitoDocumentalPrestacao('Holerite'),))
    pacote = avaliar_e_montar_pacote(_CLIENTE_SKY, _COMPETENCIA_0726, resultado.resolucao_semantica, sink, politica)
    assert pacote.estado == EstadoPacotePrestacao.PRONTO


# ============================================================================
# CASO B -- Folha de Ponto sem título, estruturalmente resolvida
# ============================================================================

def test_caso_b_ponto_sem_titulo_estrutural_ate_inventario():
    texto = (
        'CPF: 111.222.333-44\n29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00\nCompetência: 04/2026'
    )
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-b', competencia_esperada=(2026, 4), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.tipo_documental == 'Folha de Ponto'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU

    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink)
    assert len(itens) == 1


# ============================================================================
# CASO C -- Extrato "master" (multi-cliente) -> separação -> filho ->
# MESMO motor -> cliente -> inventário
# ============================================================================

def test_caso_c_extrato_master_separa_e_reentra_cada_filho_no_motor():
    paginas = [
        'CNPJ: 12.345.678/0001-99\nExtrato da Folha de Pagamento -- Julho/2026\nCompetência: 07/2026',
        'CNPJ: 98.765.432/0001-11\nExtrato da Folha de Pagamento -- Julho/2026\nCompetência: 07/2026',
    ]
    indice = {
        '12345678000199': ('cli-sky', 'SKY'),
        '98765432000111': ('cli-acme', 'ACME'),
    }
    identificar = estrategia_por_cnpj_cliente(indice)

    def _injetar_cliente_direto(contexto_filho, grupo):
        # A separação por CNPJ de cliente já resolveu QUAL cliente --
        # o hook (genérico, ver docstring) traduz isso para o campo que
        # a família "granularidade cliente" (Extrato) precisa.
        return dataclasses.replace(
            contexto_filho, cliente_direto=ReferenciaCanonica('CLIENTE', grupo.entidade_id),
        )

    resultados = processar_documento_com_separacao_se_necessaria(
        paginas, _contexto('doc-c', competencia_esperada=(2026, 7)), identificar_pagina=identificar,
        personalizar_contexto_do_grupo=_injetar_cliente_direto,
    )
    assert len(resultados) == 2
    assert {r.documento_id for r in resultados} == {'doc-c:cli-sky', 'doc-c:cli-acme'}

    sink = InventarioPrestacaoEmMemoria()
    total_itens = 0
    for r in resultados:
        assert r.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
        total_itens += len(avancar_para_inventario(r, sink, clientes_broadcast=()))
    assert total_itens == 2
    assert sink.total_itens() == 2


# ============================================================================
# CASO D -- DCTF -> broadcast lógico -> inventário dos clientes aplicáveis
# ============================================================================

def test_caso_d_dctf_broadcast_para_multiplos_clientes():
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto('doc-d', competencia_esperada=(2026, 7)))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU

    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink, clientes_broadcast=(_CLIENTE_SKY, _CLIENTE_ACME))
    assert len(itens) == 2
    assert {item.cliente for item in itens} == {_CLIENTE_SKY, _CLIENTE_ACME}
    assert sink.total_itens() == 2


# ============================================================================
# CASO E -- Comprovante Salário -> finalidade -> colaborador -> cliente
# ============================================================================

def test_caso_e_comprovante_salario_finalidade_colaborador_cliente():
    texto = 'Comprovante de transferência -- pagamento de salário\nCompetência: 07/2026\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-e', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.tipo_documental == 'Comprovante de Pagamento - Salário'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


# ============================================================================
# CASO F -- Conflito (origem × conteúdo) -> para imediatamente
# ============================================================================

def test_caso_f_conflito_para_imediatamente_nunca_avanca():
    resultado = processar_documento_prestacao(
        'Comprovante de recolhimento do FGTS', _contexto('doc-f', tipo_origem='Holerite'),
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.ORIGEM_CONTEUDO_DIVERGENTE
    sink = InventarioPrestacaoEmMemoria()
    assert avancar_para_inventario(resultado, sink) == ()


# ============================================================================
# CASO G -- Ambiguidade -> revisão humana
# ============================================================================

def test_caso_g_ambiguidade_vira_revisao():
    resultado = processar_documento_prestacao(
        'Comprovante de recolhimento do FGTS -- Código de Receita: 0561', _contexto('doc-g'),
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.TIPO_AMBIGUO


# ============================================================================
# CASO H -- PDF sem texto -> necessidade técnica/OCR futuro
# ============================================================================

def test_caso_h_pdf_sem_texto_nunca_inventa_classificacao():
    resultado = processar_documento_prestacao(None, _contexto('doc-h'))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.TEXTO_NAO_EXTRAIVEL
    assert resultado.tipo_documental is None


# ============================================================================
# CASO I -- Competência necessária mas não resolvida -> nunca valida
# silenciosamente
# ============================================================================

def test_caso_i_competencia_necessaria_nao_resolvida_nunca_valida_silenciosamente():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-i', candidatos_colaborador=candidatos, fonte_vinculos=_FonteVinculosFake(),
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    assert resultado.resolucao_semantica.pronto_para_routing_logico is False


# ============================================================================
# CASO J -- Execução dupla -> idempotência
# ============================================================================

def test_caso_j_execucao_dupla_nunca_duplica_inventario():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    contexto = _contexto(
        'doc-j', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
        fonte_vinculos=_FonteVinculosFake(),
    )
    sink = InventarioPrestacaoEmMemoria()
    for _ in range(3):
        resultado = processar_documento_prestacao(texto, contexto)
        avancar_para_inventario(resultado, sink)
    assert sink.total_itens() == 1


# ============================================================================
# Fase 23 -- métricas do corredor completo
# ============================================================================

@dataclasses.dataclass(frozen=True)
class MetricasCorredorPosClassificacao:
    total: int
    auto_classificados: int
    auto_avancou_completo: int
    revisao: int
    ambiguos: int
    conflitos: int
    erros_tecnicos: int
    desconhecidos: int
    sem_perfil: int

    @property
    def percentual_auto_classificacao(self) -> float:
        return round(100.0 * self.auto_classificados / self.total, 2) if self.total else 0.0

    @property
    def percentual_auto_corredor_completo(self) -> float:
        return round(100.0 * self.auto_avancou_completo / self.total, 2) if self.total else 0.0


def _medir(resultados) -> MetricasCorredorPosClassificacao:
    contagem = {estado: 0 for estado in EstadoCorredorDocumentoPrestacao}
    for r in resultados:
        contagem[r.estado] += 1
    auto_classificados = sum(
        v for k, v in contagem.items() if k not in (
            EstadoCorredorDocumentoPrestacao.TEXTO_NAO_EXTRAIVEL,
            EstadoCorredorDocumentoPrestacao.TIPO_DESCONHECIDO,
            EstadoCorredorDocumentoPrestacao.TIPO_AMBIGUO,
            EstadoCorredorDocumentoPrestacao.TIPO_CONFLITO,
        )
    )
    return MetricasCorredorPosClassificacao(
        total=len(resultados),
        auto_classificados=auto_classificados,
        auto_avancou_completo=contagem[EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU],
        revisao=contagem[EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA],
        ambiguos=contagem[EstadoCorredorDocumentoPrestacao.TIPO_AMBIGUO],
        conflitos=(
            contagem[EstadoCorredorDocumentoPrestacao.TIPO_CONFLITO]
            + contagem[EstadoCorredorDocumentoPrestacao.ORIGEM_CONTEUDO_DIVERGENTE]
        ),
        erros_tecnicos=contagem[EstadoCorredorDocumentoPrestacao.TEXTO_NAO_EXTRAIVEL],
        desconhecidos=contagem[EstadoCorredorDocumentoPrestacao.TIPO_DESCONHECIDO],
        sem_perfil=contagem[EstadoCorredorDocumentoPrestacao.PERFIL_NAO_CADASTRADO],
    )


def test_metricas_do_corredor_distinguem_classificacao_de_corredor_completo():
    """Reexecuta os 10 casos (sem separação -- a granularidade de
    métrica é por resultado, não por documento pai) e mede a diferença
    entre "classificado" e "corredor inteiro automático", provando que
    a segunda é sempre <= primeira, nunca confundidas."""
    candidatos = [_candidato('func-1', '11122233344', 'JOAO')]
    fv = _FonteVinculosFake()
    resultados = [
        processar_documento_prestacao(
            'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44',
            _contexto('m-a', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fv),
        ),
        processar_documento_prestacao(
            'CPF: 111.222.333-44\n29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
            '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00\nCompetência: 04/2026',
            _contexto('m-b', competencia_esperada=(2026, 4), candidatos_colaborador=candidatos, fonte_vinculos=fv),
        ),
        processar_documento_prestacao(
            'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026', _contexto('m-d', competencia_esperada=(2026, 7)),
        ),
        processar_documento_prestacao(
            'Comprovante de transferência -- pagamento de salário\nCompetência: 07/2026\nCPF: 111.222.333-44',
            _contexto('m-e', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fv),
        ),
        processar_documento_prestacao(
            'Comprovante de recolhimento do FGTS', _contexto('m-f', tipo_origem='Holerite'),
        ),
        processar_documento_prestacao(
            'Comprovante de recolhimento do FGTS -- Código de Receita: 0561', _contexto('m-g'),
        ),
        processar_documento_prestacao(None, _contexto('m-h')),
        processar_documento_prestacao(
            'Recibo de Pagamento -- Total de Vencimentos\nCPF: 111.222.333-44',
            _contexto('m-i', candidatos_colaborador=candidatos, fonte_vinculos=fv),
        ),
        processar_documento_prestacao(
            'texto totalmente generico sem nenhum sinal', _contexto('m-desconhecido'),
        ),
        processar_documento_prestacao(
            'Certidão Negativa de Débitos -- Válida até 01/01/2027', _contexto('m-sem-perfil'),
        ),
    ]
    metricas = _medir(resultados)
    assert metricas.total == 10
    assert metricas.auto_avancou_completo <= metricas.auto_classificados
    assert metricas.auto_avancou_completo == 4  # m-a, m-b, m-d, m-e
    assert metricas.revisao == 1  # m-i (competência ausente)
    assert metricas.ambiguos == 1  # m-g
    assert metricas.conflitos == 1  # m-f (origem x conteudo)
    assert metricas.erros_tecnicos == 1  # m-h
    assert metricas.desconhecidos == 1  # m-desconhecido
    assert metricas.sem_perfil == 1  # m-sem-perfil
    assert metricas.percentual_auto_corredor_completo == 40.0
