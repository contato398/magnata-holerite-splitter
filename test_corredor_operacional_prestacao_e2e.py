"""CORREDOR OPERACIONAL DA PRESTAÇÃO DE CONTAS — E2E multifamília/
multicliente (missão "CORREDOR OPERACIONAL DA PRESTAÇÃO DE CONTAS",
Fases 8/9/13).

UM ÚNICO cenário integrado prova, para MÚLTIPLOS clientes e MÚLTIPLAS
famílias documentais, o corredor completo:

    documentos → reconhecimento geral → master detectado → separação →
    filhos → resolução semântica → vínculo/contexto → competência →
    inventário → readiness → faltantes → pacote lógico por cliente

Nenhuma peça nova de motor -- só orquestra o que já existe (PRs #93,
#94, #95, #96 + os módulos novos desta missão: `adaptador_inventario_
prestacao.py`, `pacote_prestacao.py`). Nenhum `if tipo ==` de
orquestração: cada documento passa pela MESMA sequência de funções,
independente da família.

Todos os dados são SINTÉTICOS -- nunca reais, seguindo LGPD."""
from magnata_os.classificacao.adaptador_inventario_prestacao import (
    itens_para_clientes_broadcast,
    resultado_semantico_para_item_inventario,
)
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.competencia_esperada_prestacao import (
    DESLOCAMENTO_SKY_TATUI,
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
)
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    FINALIDADE_SALARIO,
    OcorrenciaSinalFinalidade,
    SinalFinalidadePagamento,
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    avaliar_e_montar_pacote,
)
from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.produtores_evidencia_fiscal import hipoteses_fiscais_de_texto
from magnata_os.classificacao.produtores_evidencia_ponto import hipoteses_estruturais_de_ponto
from magnata_os.classificacao.produtores_evidencia_temporal import hipoteses_temporais_de_certidao
from magnata_os.classificacao.resolucao_semantica import (
    compor_resolucao_semantica,
    resolucao_competencia_de_validacao,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.separacao_documental import (
    estrategia_por_cnpj_cliente,
    separar_por_carry_forward,
    texto_do_grupo,
)
from magnata_os.classificacao.vinculos_prestacao import resolver_clientes_validado
from magnata_os.documental.importacao_lote.contratos import (
    CompetenciaExtraida,
    StatusExtracaoCompetencia,
)
from magnata_os.documental.importacao_lote.dominio import validar_competencia

# ============================================================================
# Cenário -- clientes, contexto de ciclo, política
# ============================================================================

_CLIENTE_A = ReferenciaCanonica('CLIENTE', 'rec_cliente_a')  # completo
_CLIENTE_B = ReferenciaCanonica('CLIENTE', 'rec_cliente_b')  # faltando
_CLIENTE_C = ReferenciaCanonica('CLIENTE', 'rec_cliente_c')  # em revisão
_SKY = REFERENCIA_CLIENTE_SKY_TATUI

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_COMPETENCIA_BASE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_SKY = ReferenciaCanonica('COMPETENCIA', '2026-06')  # base - 1 mês

_CNPJ_MAGNATA = '00111222000133'
_CNPJ_CLIENTE_A = '11222333000181'
_CNPJ_CLIENTE_B = '44555666000172'
_INDICE_CLIENTES_CNPJ = {
    _CNPJ_CLIENTE_A: (_CLIENTE_A.entidade_id, 'Cliente A'),
    _CNPJ_CLIENTE_B: (_CLIENTE_B.entidade_id, 'Cliente B'),
}


def _fmt_cnpj(cnpj: str) -> str:
    return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}'


_POLITICA_REQUISITOS = PoliticaRequisitosPrestacao(
    version='corredor-operacional-v1',
    requisitos_base=(
        RequisitoDocumentalPrestacao('Holerite'),
        RequisitoDocumentalPrestacao('Extrato da Folha de Pagamento'),
        RequisitoDocumentalPrestacao('FGTS'),
        RequisitoDocumentalPrestacao('DCTFWeb - Declaração'),
    ),
)


class _FonteInventarioMemoria:
    """Fonte de inventário PURA, em memória -- implementa `FonteInventarioPrestacao`
    (Protocol) sem nenhum I/O. Equivalente ao papel de um adapter Airtable
    real, mas 100% local para esta prova (cláusula pétrea #10: nenhuma
    leitura live)."""

    def __init__(self):
        self._itens = []

    def adicionar(self, *itens):
        self._itens.extend(itens)

    def listar(self, cliente, competencia):
        return tuple(
            item for item in self._itens
            if item.cliente == cliente and item.competencia == competencia
        )


class _FonteVinculosFake:
    def __init__(self, cliente):
        self._cliente = cliente

    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(self._cliente,),
        )


def _perfil_documento_cliente():
    return PerfilAplicabilidadeResolucao(
        perfil_id='documento-cliente-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def _perfil_documento_broadcast():
    return PerfilAplicabilidadeResolucao(
        perfil_id='documento-broadcast-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def _perfil_documento_colaborador():
    return PerfilAplicabilidadeResolucao(
        perfil_id='documento-colaborador-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def _resolucao_competencia_confirmada(ano_mes_observado, ano_mes_esperado):
    competencia_observada = CompetenciaExtraida(
        status=StatusExtracaoCompetencia.ENCONTRADA, ano_mes=ano_mes_observado, estrategia='mm_aaaa_numerico',
    )
    resultado = validar_competencia(competencia_observada, *ano_mes_esperado)
    return resolucao_competencia_de_validacao(resultado, ano_mes_esperado)


def _compor(perfil, resolucoes, documento_id):
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='corredor-e2e',
            resolver_version='1', politica_id=perfil.perfil_id, politica_version='1',
            contexto_fontes_fingerprint='corredor-operacional-e2e',
        ),
        perfil=perfil, resolucoes=resolucoes,
    )


def _resolucao_tipo_textual(texto, quantidade_entidades_distintas=None):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=quantidade_entidades_distintas)


def _documento_cliente(documento_id, texto, cliente, competencia_esperada=(2026, 7)):
    """Reconhecimento textual + composição para 1 documento de CLIENTE
    (sem colaborador) -- usado por FGTS/Extrato/DCTF/Guia/Certidão/Ponto."""
    resolucao_tipo = _resolucao_tipo_textual(texto, quantidade_entidades_distintas=1)
    resolucao_competencia = _resolucao_competencia_confirmada(competencia_esperada, competencia_esperada)
    resultado = _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(cliente,)),
            resolucao_competencia,
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        documento_id,
    )
    return resultado, resultado_semantico_para_item_inventario(documento_id, resultado)


def test_corredor_operacional_multifamilia_multicliente():
    fonte_inventario = _FonteInventarioMemoria()
    itens_gerados = []

    # ------------------------------------------------------------------
    # 1) MASTER Extrato Mensal (Cliente A + Cliente B) -> separação real
    # ------------------------------------------------------------------
    paginas_master = (
        f'Tomador CNPJ {_fmt_cnpj(_CNPJ_CLIENTE_A)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
        'detalhe do cliente A',
        f'Tomador CNPJ {_fmt_cnpj(_CNPJ_CLIENTE_B)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
    )
    estrategia = estrategia_por_cnpj_cliente(_INDICE_CLIENTES_CNPJ, cnpj_excluido=_CNPJ_MAGNATA)
    resultado_separacao = separar_por_carry_forward(paginas_master, estrategia)
    assert len(resultado_separacao.grupos) == 2
    for indice, grupo in enumerate(resultado_separacao.grupos):
        texto_filho = texto_do_grupo(paginas_master, grupo)
        cliente = _CLIENTE_A if grupo.entidade_id == _CLIENTE_A.entidade_id else _CLIENTE_B
        _, item = _documento_cliente(f'extrato-filho-{indice}', texto_filho, cliente)
        assert item is not None
        itens_gerados.append(item)

    # ------------------------------------------------------------------
    # 2) Holerite avulso do colaborador (Cliente A, via vínculo)
    # ------------------------------------------------------------------
    fonte_vinculos_a = _FonteVinculosFake(_CLIENTE_A)
    origem_colaborador = ReferenciaCanonica('COLABORADOR', 'func-cliente-a')
    resolucao_vinculo = resolver_clientes_validado(fonte_vinculos_a, origem_colaborador, _COMPETENCIA_BASE)
    resolucao_tipo_holerite = _resolucao_tipo_textual(
        'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido', quantidade_entidades_distintas=1)
    resultado_holerite = _compor(
        _perfil_documento_colaborador(),
        (
            resolucao_tipo_holerite,
            resolucao_vinculo,
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(origem_colaborador,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'holerite-colaborador-a',
    )
    item_holerite = resultado_semantico_para_item_inventario('holerite-colaborador-a', resultado_holerite)
    assert item_holerite is not None
    itens_gerados.append(item_holerite)

    # ------------------------------------------------------------------
    # 3) Folha de Ponto (estrutural, sem a frase literal) -- mesmo colaborador
    # ------------------------------------------------------------------
    texto_ponto = (
        '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '28/04/26 - Ter - C1 08:00 12:00 13:00 17:00\n'
        'Período: 01/07/2026 até 31/07/2026'
    )
    resolucao_tipo_ponto = resolver_tipo_documental(hipoteses_estruturais_de_ponto(texto_ponto))
    assert resolucao_tipo_ponto.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_ponto = _compor(
        _perfil_documento_colaborador(),
        (
            resolucao_tipo_ponto,
            resolucao_vinculo,
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(origem_colaborador,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'ponto-colaborador-a',
    )
    item_ponto = resultado_semantico_para_item_inventario('ponto-colaborador-a', resultado_ponto)
    assert item_ponto is not None
    itens_gerados.append(item_ponto)

    # ------------------------------------------------------------------
    # 4) FGTS (Cliente A) -- resolve, mas Cliente B NUNCA recebe FGTS
    #    (fica FALTANDO para B, de propósito).
    # ------------------------------------------------------------------
    _, item_fgts_a = _documento_cliente('fgts-a', 'FGTS Digital\nGuia do FGTS\nTotal FGTS', _CLIENTE_A)
    assert item_fgts_a is not None
    itens_gerados.append(item_fgts_a)

    # ------------------------------------------------------------------
    # 5) DCTFWeb - Declaração -- BROADCAST para A, B e C (1 identidade,
    #    N itens lógicos, sem duplicação física).
    # ------------------------------------------------------------------
    resolucao_tipo_dctf = _resolucao_tipo_textual('Comprovante emitido pelo sistema DCTFWeb da empresa')
    assert resolucao_tipo_dctf.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_dctf = _compor(
        _perfil_documento_broadcast(),
        (
            resolucao_tipo_dctf,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'dctf-declaracao-global',
    )
    itens_broadcast = itens_para_clientes_broadcast(
        'dctf-declaracao-global', resultado_dctf, (_CLIENTE_A, _CLIENTE_B, _CLIENTE_C))
    assert len(itens_broadcast) == 3
    assert len({item.documento_id for item in itens_broadcast}) == 1  # MESMA identidade, nunca duplicada
    itens_gerados.extend(itens_broadcast)

    # ------------------------------------------------------------------
    # 6) Comprovante de pagamento com finalidade resolvida (Salário) -- A
    # ------------------------------------------------------------------
    ocorrencias_salario = sinais_textuais_de_finalidade_pagamento(
        'Comprovante de pagamento de salário do mês de referência')
    resolucao_tipo_salario = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_salario))
    assert resolucao_tipo_salario.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_salario = _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo_salario,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_CLIENTE_A,)),
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'comprovante-salario-a',
    )
    item_salario = resultado_semantico_para_item_inventario('comprovante-salario-a', resultado_salario)
    assert item_salario is not None
    assert item_salario.tipo_documental == FINALIDADE_SALARIO
    itens_gerados.append(item_salario)

    # ------------------------------------------------------------------
    # 7) Certidão -- Cliente A
    # ------------------------------------------------------------------
    resolucao_tipo_certidao = resolver_tipo_documental(
        hipoteses_temporais_de_certidao('Certidão Negativa de Débitos\nVálida até 31/12/2026'))
    assert resolucao_tipo_certidao.estado == EstadoResolucaoDimensao.RESOLVIDA
    _, item_certidao = None, None
    resultado_certidao = _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo_certidao,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_CLIENTE_A,)),
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'certidao-a',
    )
    item_certidao = resultado_semantico_para_item_inventario('certidao-a', resultado_certidao)
    assert item_certidao is not None
    itens_gerados.append(item_certidao)

    # ------------------------------------------------------------------
    # 8) Benefício VR/VA (abreviação + estrutura bancária reforçando) -- A
    # ------------------------------------------------------------------
    ocorrencias_vr = sinais_textuais_de_finalidade_pagamento('PIX efetuado -- crédito referente a VR do mês')
    resolucao_tipo_vr = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_vr))
    assert resolucao_tipo_vr.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_vr = _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo_vr,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_CLIENTE_A,)),
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'beneficio-vr-a',
    )
    item_vr = resultado_semantico_para_item_inventario('beneficio-vr-a', resultado_vr)
    assert item_vr is not None
    itens_gerados.append(item_vr)

    # ------------------------------------------------------------------
    # 9) Desconhecido e ambíguo -- NUNCA viram item (sem exceção humana
    #    automática, cláusula pétrea #9).
    # ------------------------------------------------------------------
    resolucao_desconhecido = _resolucao_tipo_textual('texto qualquer sem nenhum padrao de negocio conhecido')
    assert resolucao_desconhecido.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    resolucao_ambiguo = _resolucao_tipo_textual('Boleto\nLinha Digitável\nNota Fiscal de Serviço')
    assert resolucao_ambiguo.estado == EstadoResolucaoDimensao.AMBIGUA

    # ------------------------------------------------------------------
    # 10) Cliente C -- documento presente, mas ANCORA em revisão (cliente
    #     ambíguo na própria resolução) -> readiness REVISAR.
    # ------------------------------------------------------------------
    resultado_ambiguo_c = _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo_dctf,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.AMBIGUA, candidatos=(_CLIENTE_A, _CLIENTE_C)),
            _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'documento-ambiguo-c',
    )
    assert resultado_ambiguo_c.necessita_revisao_humana is True

    # ------------------------------------------------------------------
    # 11) SKY Tatuí -- competência deslocada -1 mês, validada pela MESMA
    #     política já provada nos PRs #91/#92.
    # ------------------------------------------------------------------
    tipo_extrato = 'Extrato da Folha de Pagamento'
    competencia_esperada_sky = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        _CONTEXTO, _SKY, tipo_extrato)
    assert competencia_esperada_sky == (2026, 6)  # base (2026,7) - 1 mês
    resolucao_tipo_sky = _resolucao_tipo_textual(
        'Extrato Mensal\nExtrato da Folha de Pagamento', quantidade_entidades_distintas=1)
    resultado_sky = _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo_sky,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_SKY,)),
            _resolucao_competencia_confirmada(competencia_esperada_sky, competencia_esperada_sky),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'extrato-sky',
    )
    item_sky = resultado_semantico_para_item_inventario('extrato-sky', resultado_sky)
    assert item_sky is not None
    assert item_sky.competencia == _COMPETENCIA_SKY
    itens_gerados.append(item_sky)

    # ------------------------------------------------------------------
    # Inventário + Readiness + Pacote lógico -- por cliente
    # ------------------------------------------------------------------
    fonte_inventario.adicionar(*itens_gerados)

    pacote_a = avaliar_e_montar_pacote(
        _CLIENTE_A, _COMPETENCIA_BASE, resultado_holerite, fonte_inventario, _POLITICA_REQUISITOS)
    assert pacote_a.estado == EstadoPacotePrestacao.PRONTO
    assert pacote_a.tipos_faltantes == ()

    pacote_b = avaliar_e_montar_pacote(
        _CLIENTE_B,
        _COMPETENCIA_BASE,
        _compor(
            _perfil_documento_cliente(),
            (
                resolucao_tipo_sky,
                ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_CLIENTE_B,)),
                _resolucao_competencia_confirmada((2026, 7), (2026, 7)),
                ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ),
            'ancora-cliente-b',
        ),
        fonte_inventario, _POLITICA_REQUISITOS,
    )
    assert pacote_b.estado == EstadoPacotePrestacao.INCOMPLETO
    assert set(pacote_b.tipos_faltantes) == {'Holerite', 'FGTS'}  # tem Extrato (separado) + DCTF (broadcast)

    pacote_c = avaliar_e_montar_pacote(
        _CLIENTE_C, _COMPETENCIA_BASE, resultado_ambiguo_c, fonte_inventario, _POLITICA_REQUISITOS)
    assert pacote_c.estado == EstadoPacotePrestacao.EM_REVISAO

    # SKY: pacote próprio, competência DESLOCADA (2026-06), nunca a base.
    pacote_sky = avaliar_e_montar_pacote(
        _SKY, _COMPETENCIA_SKY, resultado_sky, fonte_inventario,
        PoliticaRequisitosPrestacao(version='sky-v1', requisitos_base=(RequisitoDocumentalPrestacao(tipo_extrato),)),
    )
    assert pacote_sky.estado == EstadoPacotePrestacao.PRONTO
    assert pacote_sky.competencia == _COMPETENCIA_SKY

    # Prova final: broadcast nunca duplicou fisicamente -- A, B e C têm,
    # cada um, exatamente 1 item de DCTFWeb (mesma identidade documental).
    for cliente in (_CLIENTE_A, _CLIENTE_B, _CLIENTE_C):
        itens_dctf = [
            item for item in fonte_inventario.listar(cliente, _COMPETENCIA_BASE)
            if item.tipo_documental == 'DCTFWeb - Declaração'
        ]
        assert len(itens_dctf) == 1
        assert itens_dctf[0].documento_id == 'dctf-declaracao-global'
