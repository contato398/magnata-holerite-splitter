"""Testes do Adendo substitutivo ao PR #105 -- benefícios VR/VA/iFood,
correção de granularidade FGTS/Guia/DCTF, dedupe por identidade lógica
(§16/§17 do adendo)."""
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
from magnata_os.classificacao.separacao_documental import estrategia_por_cnpj_cliente, estrategia_por_cpf_colaborador
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_CLIENTE_X = ReferenciaCanonica('CLIENTE', 'cli-condominio-x')
_CLIENTE_Y = ReferenciaCanonica('CLIENTE', 'cli-condominio-y')
_CLIENTE_A = ReferenciaCanonica('CLIENTE', 'cli-a')
_CLIENTE_B = ReferenciaCanonica('CLIENTE', 'cli-b')
_COMPETENCIA_0726 = ReferenciaCanonica('COMPETENCIA', '2026-07')


def _candidato(func_id, cpf, nome):
    return CandidatoFuncionario(func_id=func_id, cpf=cpf, nome_normalizado=nome)


def _contexto(documento_id, **kwargs):
    base = dict(documento_id=documento_id, hash_sha256='a' * 64)
    base.update(kwargs)
    return ContextoResolucaoDocumentoPrestacao(**base)


class _FonteVinculosPorColaborador:
    """Vínculo real por colaborador -- cada colaborador resolve para o
    cliente correspondente ao seu índice, nunca um valor fixo."""

    def __init__(self, mapa_colaborador_para_cliente):
        self._mapa = mapa_colaborador_para_cliente

    def resolver_clientes(self, origem, competencia):
        cliente = self._mapa[origem.entidade_id]
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(cliente,),
        )


# ============================================================================
# §16 -- Corpus de benefícios (VR/VA/iFood)
# ============================================================================

def test_caso_a_relatorio_beneficios_3_colaboradores_2_condominios_3_itens_pacotes_corretos():
    """3 colaboradores / 2 condomínios -- 3 itens individuais, cada um
    no pacote do condomínio correto (nunca um documento global
    despejado em todos)."""
    # Cada página traz 2 evidências estruturais independentes (linha de
    # valor por rubrica + total do pedido, MODERADA cada) -- combinação
    # real, nunca depende do título/rótulo sozinho (correção pré-merge:
    # nenhuma frase isolada resolve sozinha).
    paginas = [
        'CPF: 111.222.333-44\nRelatório de Benefícios\nVale-Refeição   R$ 250,00\nVale-Alimentação   R$ 250,00\n'
        'Total do Pedido: R$ 500,00\nCompetência: 07/2026',
        'CPF: 555.666.777-88\nRelatório de Benefícios\nVale-Refeição   R$ 250,00\nVale-Alimentação   R$ 250,00\n'
        'Total do Pedido: R$ 500,00\nCompetência: 07/2026',
        'CPF: 999.888.777-66\nRelatório de Benefícios\nVale-Refeição   R$ 250,00\nVale-Alimentação   R$ 250,00\n'
        'Total do Pedido: R$ 500,00\nCompetência: 07/2026',
    ]
    indice_cpf = {
        '11122233344': ('func-1', 'COLAB 1'),
        '55566677788': ('func-2', 'COLAB 2'),
        '99988877766': ('func-3', 'COLAB 3'),
    }
    candidatos = [
        _candidato('func-1', '11122233344', 'COLAB 1'),
        _candidato('func-2', '55566677788', 'COLAB 2'),
        _candidato('func-3', '99988877766', 'COLAB 3'),
    ]
    fonte_vinculos = _FonteVinculosPorColaborador({
        'func-1': _CLIENTE_X, 'func-2': _CLIENTE_X, 'func-3': _CLIENTE_Y,
    })
    resultados = processar_documento_com_separacao_se_necessaria(
        paginas,
        _contexto('doc-beneficios', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
                   fonte_vinculos=fonte_vinculos),
        identificar_pagina=estrategia_por_cpf_colaborador(indice_cpf),
    )
    assert len(resultados) == 3
    for r in resultados:
        assert r.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
        assert r.tipo_documental == 'Relatório de Benefícios'

    sink = InventarioPrestacaoEmMemoria()
    for r in resultados:
        avancar_para_inventario(r, sink)
    assert sink.total_itens() == 3

    politica = PoliticaRequisitosPrestacao(
        version='v1', requisitos_base=(RequisitoDocumentalPrestacao('Relatório de Benefícios'),),
    )
    # cada pacote só vê os itens do SEU cliente -- readiness/pacote já
    # filtram por (cliente, competencia), reaproveitados sem alteração.
    resolucao_qualquer = next(
        r.resolucao_semantica for r in resultados if r.resolucao_semantica.resolucoes
    )
    pacote_x = avaliar_e_montar_pacote(_CLIENTE_X, _COMPETENCIA_0726, resolucao_qualquer, sink, politica)
    pacote_y = avaliar_e_montar_pacote(_CLIENTE_Y, _COMPETENCIA_0726, resolucao_qualquer, sink, politica)
    assert len(pacote_x.itens_incluidos) == 2
    assert len(pacote_y.itens_incluidos) == 1


def test_caso_b_relatorio_apenas_vr_reconhecido():
    texto = (
        'Relatório de Benefícios\nVale-Refeição   R$ 300,00\nTotal do Pedido: R$ 300,00\n'
        'CPF: 111.222.333-44\nCompetência: 07/2026'
    )
    candidatos = [_candidato('func-1', '11122233344', 'COLAB 1')]
    fonte_vinculos = _FonteVinculosPorColaborador({'func-1': _CLIENTE_X})
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-vr', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fonte_vinculos,
    ))
    assert resultado.tipo_documental == 'Relatório de Benefícios'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_caso_c_relatorio_apenas_va_reconhecido():
    texto = (
        'Relatório de Benefícios\nVale-Alimentação   R$ 300,00\nTotal do Pedido: R$ 300,00\n'
        'CPF: 111.222.333-44\nCompetência: 07/2026'
    )
    candidatos = [_candidato('func-1', '11122233344', 'COLAB 1')]
    fonte_vinculos = _FonteVinculosPorColaborador({'func-1': _CLIENTE_X})
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-va', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fonte_vinculos,
    ))
    assert resultado.tipo_documental == 'Relatório de Benefícios'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_caso_d_relatorio_vr_e_va_nao_forca_escolha_exclusiva():
    texto = (
        'Relatório de Benefícios\nVale-Refeição   R$ 150,00\nVale-Alimentação   R$ 150,00\n'
        'Total do Pedido: R$ 300,00\nCPF: 111.222.333-44\nCompetência: 07/2026'
    )
    candidatos = [_candidato('func-1', '11122233344', 'COLAB 1')]
    fonte_vinculos = _FonteVinculosPorColaborador({'func-1': _CLIENTE_X})
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-vr-va', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fonte_vinculos,
    ))
    assert resultado.tipo_documental == 'Relatório de Benefícios'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_caso_e_comprovante_beneficios_com_colaboradores_identificados():
    """Comprovante de pagamento de VR/VA que TRAZ identificação de
    colaborador (CPF) -- relação lógica só para o cliente do colaborador
    efetivamente identificado (nunca inventado). O caso de um
    comprovante GLOBAL sem NENHUMA decomposição, relacionável só por
    vínculo com um documento de pedido separado, permanece limitação
    registrada (ver ADR) -- inventar esse vínculo sem evidência violaria
    a Fase 20/§20 do adendo ("não inventar vínculos")."""
    texto = 'Comprovante de transferência -- pagamento de vale-refeição\nCPF: 111.222.333-44\nCompetência: 07/2026'
    candidatos = [_candidato('func-1', '11122233344', 'COLAB 1')]
    fonte_vinculos = _FonteVinculosPorColaborador({'func-1': _CLIENTE_X})
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-comprovante-vr', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos,
        fonte_vinculos=fonte_vinculos,
    ))
    assert resultado.tipo_documental == 'Comprovante de Pagamento - VR/VA'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink)
    assert len(itens) == 1
    assert itens[0].cliente == _CLIENTE_X


def test_caso_f_comprovante_sem_relacao_suficiente_nunca_inventa():
    """Comprovante sem CPF identificável e sem cliente direto -- nunca
    inventa cliente nem finalidade; fica em revisão."""
    texto = 'Comprovante de transferência -- pagamento de vale-refeição\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto('doc-comprovante-sem-relacao', competencia_esperada=(2026, 7)))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    sink = InventarioPrestacaoEmMemoria()
    assert avancar_para_inventario(resultado, sink) == ()


def test_caso_g_documento_ifood_beneficios_entra_no_mesmo_motor():
    texto = (
        'Relatório de Benefícios -- iFood Benefícios\nVale-Refeição   R$ 300,00\n'
        'Total do Pedido: R$ 300,00\nCPF: 111.222.333-44\nCompetência: 07/2026'
    )
    candidatos = [_candidato('func-1', '11122233344', 'COLAB 1')]
    fonte_vinculos = _FonteVinculosPorColaborador({'func-1': _CLIENTE_X})
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-ifood', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fonte_vinculos,
    ))
    assert resultado.tipo_documental == 'Relatório de Benefícios'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_caso_h_documento_vr_beneficios_fornecedor_antigo_continua_no_mesmo_motor():
    texto = (
        'Relatório de Benefícios -- VR Benefícios\nVale-Refeição   R$ 300,00\n'
        'Total do Pedido: R$ 300,00\nCPF: 111.222.333-44\nCompetência: 07/2026'
    )
    candidatos = [_candidato('func-1', '11122233344', 'COLAB 1')]
    fonte_vinculos = _FonteVinculosPorColaborador({'func-1': _CLIENTE_X})
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-vr-antigo', competencia_esperada=(2026, 7), candidatos_colaborador=candidatos, fonte_vinculos=fonte_vinculos,
    ))
    assert resultado.tipo_documental == 'Relatório de Benefícios'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_caso_i_troca_de_fornecedor_nao_exige_alteracao_no_core():
    """Mesmo perfil, mesma política, mesmo orquestrador -- só o texto
    muda (fornecedor é metadado/evidência, nunca identidade)."""
    from magnata_os.classificacao.perfil_aplicabilidade_documental import perfil_para_tipo
    assert perfil_para_tipo('Relatório de Benefícios') is not None
    # nenhuma entrada de cadastro nem código soube "iFood"/"VR Benefícios"
    # -- confirmado pelo teste arquitetural dedicado
    # (test_fornecedor_nao_e_import_nem_dependencia_do_core).


# ============================================================================
# §17 -- FGTS / Guia genérica / DCTF (correção de granularidade)
# ============================================================================

def test_fgts_cliente_a_avanca_somente_para_a():
    texto = 'Guia do FGTS Digital -- Total FGTS\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto(
        'doc-fgts-a', competencia_esperada=(2026, 7), cliente_direto=_CLIENTE_A,
    ))
    assert resultado.tipo_documental == 'FGTS'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink)
    assert len(itens) == 1
    assert itens[0].cliente == _CLIENTE_A


def test_fgts_master_a_e_b_nunca_espalha_para_c():
    """FGTS master (2 CNPJs distintos) -- separa por cliente, cada
    filho vai SÓ para o cliente correto, nunca para um terceiro cliente
    C não comprovado."""
    paginas = [
        'CNPJ: 12.345.678/0001-99\nGuia do FGTS Digital -- Total FGTS\nCompetência: 07/2026',
        'CNPJ: 98.765.432/0001-11\nGuia do FGTS Digital -- Total FGTS\nCompetência: 07/2026',
    ]
    indice = {'12345678000199': ('cli-a', 'A'), '98765432000111': ('cli-b', 'B')}

    def _injetar_cliente_direto(contexto_filho, grupo):
        return dataclasses.replace(contexto_filho, cliente_direto=ReferenciaCanonica('CLIENTE', grupo.entidade_id))

    resultados = processar_documento_com_separacao_se_necessaria(
        paginas, _contexto('doc-fgts-master', competencia_esperada=(2026, 7)),
        identificar_pagina=estrategia_por_cnpj_cliente(indice),
        personalizar_contexto_do_grupo=_injetar_cliente_direto,
    )
    assert len(resultados) == 2
    sink = InventarioPrestacaoEmMemoria()
    clientes_gerados = set()
    for r in resultados:
        assert r.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
        for item in avancar_para_inventario(r, sink):
            clientes_gerados.add(item.cliente)
    assert clientes_gerados == {_CLIENTE_A, _CLIENTE_B}
    assert ReferenciaCanonica('CLIENTE', 'cli-c-nunca-comprovado') not in clientes_gerados


def test_comprovante_fgts_sem_cliente_nunca_espalha():
    texto = 'Comprovante de recolhimento do FGTS\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto('doc-comp-fgts-sem-cliente', competencia_esperada=(2026, 7)))
    assert resultado.tipo_documental == 'Comprovante de Pagamento - FGTS'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    sink = InventarioPrestacaoEmMemoria()
    assert avancar_para_inventario(resultado, sink) == ()


def test_guia_generica_nunca_broadcast_permanece_sem_perfil():
    texto = 'Código de Receita: 1234'  # resolve para 'Guia' (fiscal, fallback genérico)
    resultado = processar_documento_prestacao(texto, _contexto('doc-guia-generica'))
    assert resultado.tipo_documental == 'Guia'
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.PERFIL_NAO_CADASTRADO
    sink = InventarioPrestacaoEmMemoria()
    assert avancar_para_inventario(resultado, sink) == ()


def test_dctf_competencia_level_continua_broadcast():
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    resultado = processar_documento_prestacao(texto, _contexto('doc-dctf', competencia_esperada=(2026, 7)))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    sink = InventarioPrestacaoEmMemoria()
    itens = avancar_para_inventario(resultado, sink, clientes_broadcast=(_CLIENTE_A, _CLIENTE_B))
    assert len(itens) == 2
