"""CICLO DA PRESTAÇÃO sem hardcode de cliente (missão "POLÍTICA
OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fases 8/14).

Diferença central em relação a `test_corredor_operacional_prestacao_e2e.py`
(missão anterior): ali os clientes A/B/C eram injetados manualmente no
teste. Aqui, `executar_ciclo_prestacao` obtém a lista de clientes e os
requisitos de FONTES substituíveis (`FonteClientesPrestacao`/
`FonteRequisitosPrestacao`) -- as MESMAS interfaces que um adapter
Airtable real usaria (`FonteClientesPrestacaoAirtable`, já criado e
testado à parte). Nenhum `if` por nome/identidade de cliente em
`ciclo_prestacao.py` -- só neste teste, para MONTAR o cenário
(exatamente onde é aceitável: dados de fixture, não lógica de motor).

5 clientes: completo, incompleto, em revisão, com requisito condicional
(Certidão) e SKY (competência deslocada). Inclui broadcast (DCTFWeb) e
1 master (Extrato Mensal) separado."""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.adaptador_inventario_prestacao import (
    itens_para_clientes_broadcast,
    resultado_semantico_para_item_inventario,
)
from magnata_os.classificacao.ciclo_prestacao import executar_ciclo_prestacao
from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
)
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.normalizacao_requisitos_prestacao import RegistroRequisitoExterno
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
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
from magnata_os.documental.importacao_lote.contratos import (
    CompetenciaExtraida,
    StatusExtracaoCompetencia,
)
from magnata_os.documental.importacao_lote.dominio import validar_competencia

# ============================================================================
# Fixture -- fontes canônicas SUBSTITUÍVEIS (mesma arquitetura de um
# adapter Airtable real, nunca hardcode dentro de ciclo_prestacao.py)
# ============================================================================

_CLIENTE_COMPLETO = ReferenciaCanonica('CLIENTE', 'rec_completo')
_CLIENTE_INCOMPLETO = ReferenciaCanonica('CLIENTE', 'rec_incompleto')
_CLIENTE_REVISAO = ReferenciaCanonica('CLIENTE', 'rec_revisao')
_CLIENTE_CONDICIONAL = ReferenciaCanonica('CLIENTE', 'rec_condicional')
_SKY = REFERENCIA_CLIENTE_SKY_TATUI

_TODOS_OS_CLIENTES = (_CLIENTE_COMPLETO, _CLIENTE_INCOMPLETO, _CLIENTE_REVISAO, _CLIENTE_CONDICIONAL, _SKY)

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_COMPETENCIA_BASE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_SKY = ReferenciaCanonica('COMPETENCIA', '2026-06')

_REQUISITOS_BASE = (RequisitoDocumentalPrestacao('Holerite'),)


class _FonteClientesFake:
    """MESMA interface que `FonteClientesPrestacaoAirtable` implementa
    -- só a origem dos dados muda (fixture local vs. Airtable real)."""

    def listar_ativos(self, contexto):
        return _TODOS_OS_CLIENTES


class _FonteRequisitosFake:
    """MESMA interface que um adapter Airtable de requisitos usaria --
    devolve registros BRUTOS, nunca já validados (a normalização
    acontece em `ciclo_prestacao.py`, nunca aqui)."""

    def __init__(self, registros_por_cliente):
        self._registros_por_cliente = registros_por_cliente

    def registros_para(self, cliente, contexto):
        return self._registros_por_cliente.get(cliente, ())


class _FonteInventarioMemoria:
    def __init__(self):
        self._itens = []

    def adicionar(self, *itens):
        self._itens.extend(itens)

    def listar(self, cliente, competencia):
        return tuple(
            item for item in self._itens
            if item.cliente == cliente and item.competencia == competencia
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


def _resolucao_competencia_confirmada(ano_mes):
    competencia_observada = CompetenciaExtraida(
        status=StatusExtracaoCompetencia.ENCONTRADA, ano_mes=ano_mes, estrategia='mm_aaaa_numerico',
    )
    resultado = validar_competencia(competencia_observada, *ano_mes)
    return resolucao_competencia_de_validacao(resultado, ano_mes)


def _compor(perfil, resolucoes, documento_id):
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='ciclo-e2e',
            resolver_version='1', politica_id=perfil.perfil_id, politica_version='1',
            contexto_fontes_fingerprint='ciclo-prestacao-multicliente-e2e',
        ),
        perfil=perfil, resolucoes=resolucoes,
    )


def _resolucao_tipo_textual(texto, quantidade_entidades_distintas=None):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=quantidade_entidades_distintas)


def _resultado_documento_cliente(documento_id, texto, cliente, ano_mes, resolucao_tipo=None):
    if resolucao_tipo is None:
        resolucao_tipo = _resolucao_tipo_textual(texto, quantidade_entidades_distintas=1)
    return _compor(
        _perfil_documento_cliente(),
        (
            resolucao_tipo,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(cliente,)),
            _resolucao_competencia_confirmada(ano_mes),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        documento_id,
    )


def test_ciclo_prestacao_multicliente_sem_hardcode():
    fonte_inventario = _FonteInventarioMemoria()

    # ------------------------------------------------------------------
    # Master Extrato Mensal (Completo + Incompleto) -- separação real.
    # ------------------------------------------------------------------
    cnpj_completo, cnpj_incompleto, cnpj_magnata = '11222333000181', '44555666000172', '00111222000133'

    def _fmt(cnpj):
        return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}'

    paginas_master = (
        f'Tomador CNPJ {_fmt(cnpj_completo)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
        f'Tomador CNPJ {_fmt(cnpj_incompleto)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
    )
    indice = {cnpj_completo: (_CLIENTE_COMPLETO.entidade_id, 'Completo'), cnpj_incompleto: (_CLIENTE_INCOMPLETO.entidade_id, 'Incompleto')}
    estrategia = estrategia_por_cnpj_cliente(indice, cnpj_excluido=cnpj_magnata)
    resultado_separacao = separar_por_carry_forward(paginas_master, estrategia)
    assert len(resultado_separacao.grupos) == 2
    for grupo in resultado_separacao.grupos:
        cliente = _CLIENTE_COMPLETO if grupo.entidade_id == _CLIENTE_COMPLETO.entidade_id else _CLIENTE_INCOMPLETO
        texto_filho = texto_do_grupo(paginas_master, grupo)
        resultado = _resultado_documento_cliente(f'extrato-{cliente.entidade_id}', texto_filho, cliente, (2026, 7))
        item = resultado_semantico_para_item_inventario(f'extrato-{cliente.entidade_id}', resultado)
        assert item is not None
        fonte_inventario.adicionar(item)

    # ------------------------------------------------------------------
    # Holerite -- Completo (satisfaz o requisito base 'Holerite').
    # ------------------------------------------------------------------
    resultado_holerite = _resultado_documento_cliente(
        'holerite-completo', 'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido', _CLIENTE_COMPLETO, (2026, 7))
    item_holerite = resultado_semantico_para_item_inventario('holerite-completo', resultado_holerite)
    assert item_holerite is not None
    fonte_inventario.adicionar(item_holerite)

    # Incompleto NUNCA recebe Holerite -- fica faltando, de propósito.

    # ------------------------------------------------------------------
    # Certidão -- só para o Condicional (satisfaz o requisito condicional).
    # ------------------------------------------------------------------
    texto_certidao = 'Certidão Negativa de Débitos\nVálida até 31/12/2026'
    resolucao_tipo_certidao = resolver_tipo_documental(hipoteses_temporais_de_certidao(texto_certidao))
    assert resolucao_tipo_certidao.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_certidao = _resultado_documento_cliente(
        'certidao-condicional', texto_certidao, _CLIENTE_CONDICIONAL, (2026, 7), resolucao_tipo=resolucao_tipo_certidao)
    item_certidao = resultado_semantico_para_item_inventario('certidao-condicional', resultado_certidao)
    assert item_certidao is not None
    fonte_inventario.adicionar(item_certidao)

    # ------------------------------------------------------------------
    # Extrato -- Condicional também precisa do requisito BASE (Holerite);
    # dá a ele um Holerite avulso para ficar PRONTO junto com a Certidão.
    # ------------------------------------------------------------------
    resultado_holerite_condicional = _resultado_documento_cliente(
        'holerite-condicional', 'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido', _CLIENTE_CONDICIONAL, (2026, 7))
    item_holerite_condicional = resultado_semantico_para_item_inventario('holerite-condicional', resultado_holerite_condicional)
    fonte_inventario.adicionar(item_holerite_condicional)

    # ------------------------------------------------------------------
    # DCTFWeb - Declaração -- BROADCAST para os 4 clientes normais
    # (nunca duplicado fisicamente).
    # ------------------------------------------------------------------
    resolucao_tipo_dctf = _resolucao_tipo_textual('Comprovante emitido pelo sistema DCTFWeb da empresa')
    resultado_dctf = _compor(
        _perfil_documento_broadcast(),
        (
            resolucao_tipo_dctf,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            _resolucao_competencia_confirmada((2026, 7)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        'dctf-global',
    )
    itens_broadcast = itens_para_clientes_broadcast(
        'dctf-global', resultado_dctf,
        (_CLIENTE_COMPLETO, _CLIENTE_INCOMPLETO, _CLIENTE_REVISAO, _CLIENTE_CONDICIONAL),
    )
    fonte_inventario.adicionar(*itens_broadcast)

    # ------------------------------------------------------------------
    # SKY -- Holerite na competência DESLOCADA (base - 1 mês).
    # ------------------------------------------------------------------
    competencia_esperada_sky = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        _CONTEXTO, _SKY, 'Holerite')
    assert competencia_esperada_sky == (2026, 6)
    resultado_holerite_sky = _resultado_documento_cliente(
        'holerite-sky', 'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido', _SKY, competencia_esperada_sky)
    item_holerite_sky = resultado_semantico_para_item_inventario('holerite-sky', resultado_holerite_sky)
    fonte_inventario.adicionar(item_holerite_sky)

    # ------------------------------------------------------------------
    # Fontes canônicas -- clientes + requisitos (condicional só para
    # rec_condicional; nenhum outro cliente exige Certidão).
    # ------------------------------------------------------------------
    fonte_clientes = _FonteClientesFake()
    fonte_requisitos = _FonteRequisitosFake({
        _CLIENTE_CONDICIONAL: (RegistroRequisitoExterno('Certidão'),),
    })

    resolucoes_ancora = {
        _CLIENTE_COMPLETO: resultado_holerite,
        _CLIENTE_INCOMPLETO: _resultado_documento_cliente(
            'ancora-incompleto', 'Extrato Mensal\nExtrato da Folha de Pagamento', _CLIENTE_INCOMPLETO, (2026, 7)),
        _CLIENTE_REVISAO: _compor(
            _perfil_documento_cliente(),
            (
                resolucao_tipo_dctf,
                ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.AMBIGUA, candidatos=(_CLIENTE_COMPLETO, _CLIENTE_REVISAO)),
                _resolucao_competencia_confirmada((2026, 7)),
                ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ),
            'ancora-revisao',
        ),
        _CLIENTE_CONDICIONAL: resultado_holerite_condicional,
        _SKY: resultado_holerite_sky,
    }
    competencias_por_cliente = {
        _CLIENTE_COMPLETO: _COMPETENCIA_BASE,
        _CLIENTE_INCOMPLETO: _COMPETENCIA_BASE,
        _CLIENTE_REVISAO: _COMPETENCIA_BASE,
        _CLIENTE_CONDICIONAL: _COMPETENCIA_BASE,
        _SKY: _COMPETENCIA_SKY,
    }

    # ------------------------------------------------------------------
    # Execução do ciclo -- SEM nenhum if por nome de cliente aqui.
    # ------------------------------------------------------------------
    resultado_ciclo = executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=fonte_clientes,
        fonte_requisitos=fonte_requisitos,
        fonte_inventario=fonte_inventario,
        requisitos_base=_REQUISITOS_BASE,
        resolucoes_ancora=resolucoes_ancora,
        competencias_por_cliente=competencias_por_cliente,
    )

    assert len(resultado_ciclo.resultados_por_cliente) == 5
    assert set(resultado_ciclo.prontos) == {_CLIENTE_COMPLETO, _CLIENTE_CONDICIONAL, _SKY}
    assert set(resultado_ciclo.incompletos) == {_CLIENTE_INCOMPLETO}
    assert set(resultado_ciclo.em_revisao) == {_CLIENTE_REVISAO}
    assert resultado_ciclo.bloqueados == ()

    # Faltantes estruturados (Fase 12) -- nunca "não existe", sempre
    # "não localizado no inventário consultado".
    resultado_incompleto = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_INCOMPLETO)
    assert resultado_incompleto.pacote.tipos_faltantes == ('Holerite',)
    assert len(resultado_incompleto.necessidades) == 1
    necessidade = resultado_incompleto.necessidades[0]
    assert necessidade.tipo_documental == 'Holerite'
    assert necessidade.cliente == _CLIENTE_INCOMPLETO
    assert 'gmail' in necessidade.fontes_ainda_nao_consultadas

    # SKY: competência efetiva é a deslocada, nunca a base.
    resultado_sky = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _SKY)
    assert resultado_sky.competencia == _COMPETENCIA_SKY
    assert resultado_sky.pacote.estado == EstadoPacotePrestacao.PRONTO

    # Broadcast: presente em todos os 4 clientes normais, mesma identidade.
    for cliente in (_CLIENTE_COMPLETO, _CLIENTE_INCOMPLETO, _CLIENTE_REVISAO, _CLIENTE_CONDICIONAL):
        itens_dctf = [item for item in fonte_inventario.listar(cliente, _COMPETENCIA_BASE) if item.tipo_documental == 'DCTFWeb - Declaração']
        assert len(itens_dctf) == 1
        assert itens_dctf[0].documento_id == 'dctf-global'
