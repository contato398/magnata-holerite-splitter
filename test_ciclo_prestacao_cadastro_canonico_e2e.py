"""CICLO DA PRESTAÇÃO com CADASTRO CANÔNICO REAL (missão "CADASTRO
CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO", Fases 12/16).

Diferença central em relação a `test_ciclo_prestacao_multicliente_e2e.py`
(missão anterior): ali `FonteRequisitosPrestacao` era uma fixture
totalmente artificial. Aqui, a base universal vem do CADASTRO CANÔNICO
REAL (`REQUISITOS_BASE_CANONICOS_V1`, a interseção comprovada das 2
fontes auditadas) via `FonteRequisitosPrestacaoCanonica` -- a MESMA
classe que rodará em produção. Só a lista de CLIENTES e a configuração
condicional de 1 cliente sintético são fixture (nenhum cliente real
existe ainda) -- exatamente o que a missão autoriza ("IDs de clientes
no teste podem ser sintéticos. Mas os requisitos devem vir da mesma
fonte canônica").

6 clientes: completo, incompleto, em revisão, condicional (Certidão,
configurado via cadastro), política-não-configurada (base OK, mas os
tipos divergentes continuam NAO_CONFIGURADO -- provado distinto de
"faltando"), e SKY. Inclui broadcast, 1 master, 1 benefício (VR/VA) e
1 reforço fiscal↔finalidade (FGTS)."""
from magnata_os.classificacao.adaptador_inventario_prestacao import (
    itens_para_clientes_broadcast,
    resultado_semantico_para_item_inventario,
)
from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    REQUISITOS_BASE_CANONICOS_V1,
    REQUISITOS_DIVERGENTES_ENTRE_FONTES,
    CadastroRequisitosPrestacao,
    ConfiguracaoCondicionalCliente,
    EstadoConfiguracaoRequisito,
    FonteRequisitosPrestacaoCanonica,
)
from magnata_os.classificacao.classificador_documental import classificar_documento
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
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.produtores_evidencia_fiscal import (
    reconciliar_evidencia_fiscal_com_finalidade,
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

_CLIENTE_COMPLETO = ReferenciaCanonica('CLIENTE', 'rec_completo')
_CLIENTE_INCOMPLETO = ReferenciaCanonica('CLIENTE', 'rec_incompleto')
_CLIENTE_REVISAO = ReferenciaCanonica('CLIENTE', 'rec_revisao')
_CLIENTE_CONDICIONAL = ReferenciaCanonica('CLIENTE', 'rec_condicional')
_CLIENTE_POLITICA_NAO_CONFIGURADA = ReferenciaCanonica('CLIENTE', 'rec_politica_nao_configurada')
_SKY = REFERENCIA_CLIENTE_SKY_TATUI

_TODOS_OS_CLIENTES = (
    _CLIENTE_COMPLETO, _CLIENTE_INCOMPLETO, _CLIENTE_REVISAO,
    _CLIENTE_CONDICIONAL, _CLIENTE_POLITICA_NAO_CONFIGURADA, _SKY,
)

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_COMPETENCIA_BASE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_SKY = ReferenciaCanonica('COMPETENCIA', '2026-06')

# Cadastro para este E2E: base REAL (comprovada, v1) + 1 condicional
# SINTÉTICO (nenhum cliente real ainda existe -- só o cliente é
# sintético, a base e a estrutura de configuração são as reais).
_CADASTRO_E2E = CadastroRequisitosPrestacao(
    versao='e2e-teste', requisitos_base=REQUISITOS_BASE_CANONICOS_V1,
    condicionais=(
        ConfiguracaoCondicionalCliente(
            _CLIENTE_CONDICIONAL.entidade_id, 'Certidão', EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE,
            evidencia='configuracao sintetica de teste -- nenhum cliente real confirmado ainda',
        ),
    ),
)
_TIPOS_DIVERGENTES = tuple(tipo for tipo, _motivo in REQUISITOS_DIVERGENTES_ENTRE_FONTES)


class _FonteClientesFake:
    def listar_ativos(self, contexto):
        return _TODOS_OS_CLIENTES


class _FonteInventarioMemoria:
    def __init__(self):
        self._itens = []

    def adicionar(self, *itens):
        self._itens.extend(i for i in itens if i is not None)

    def listar(self, cliente, competencia):
        return tuple(i for i in self._itens if i.cliente == cliente and i.competencia == competencia)


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
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='ciclo-cadastro-e2e',
            resolver_version='1', politica_id=perfil.perfil_id, politica_version='1',
            contexto_fontes_fingerprint='ciclo-prestacao-cadastro-canonico-e2e',
        ),
        perfil=perfil, resolucoes=resolucoes,
    )


def _resolucao_tipo_textual(texto, quantidade_entidades_distintas=None):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=quantidade_entidades_distintas)


def _resultado_documento_cliente(documento_id, cliente, ano_mes, resolucao_tipo):
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


def _item_textual(documento_id, texto, cliente, ano_mes=(2026, 7)):
    resolucao_tipo = _resolucao_tipo_textual(texto, quantidade_entidades_distintas=1)
    resultado = _resultado_documento_cliente(documento_id, cliente, ano_mes, resolucao_tipo)
    return resultado, resultado_semantico_para_item_inventario(documento_id, resultado)


def test_ciclo_com_cadastro_canonico_real_sem_hardcode_de_requisito():
    fonte_inventario = _FonteInventarioMemoria()

    # ---- 1) Master Extrato Mensal (Completo + Incompleto) ----------
    cnpj_completo, cnpj_incompleto, cnpj_magnata = '11222333000181', '44555666000172', '00111222000133'

    def _fmt(cnpj):
        return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}'

    paginas_master = (
        f'Tomador CNPJ {_fmt(cnpj_completo)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
        f'Tomador CNPJ {_fmt(cnpj_incompleto)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
    )
    indice = {cnpj_completo: (_CLIENTE_COMPLETO.entidade_id, 'Completo'), cnpj_incompleto: (_CLIENTE_INCOMPLETO.entidade_id, 'Incompleto')}
    resultado_separacao = separar_por_carry_forward(paginas_master, estrategia_por_cnpj_cliente(indice, cnpj_excluido=cnpj_magnata))
    assert len(resultado_separacao.grupos) == 2
    for grupo in resultado_separacao.grupos:
        cliente = _CLIENTE_COMPLETO if grupo.entidade_id == _CLIENTE_COMPLETO.entidade_id else _CLIENTE_INCOMPLETO
        texto_filho = texto_do_grupo(paginas_master, grupo)
        _, item = _item_textual(f'extrato-{cliente.entidade_id}', texto_filho, cliente)
        fonte_inventario.adicionar(item)

    # ---- 2) FGTS -- Completo tem, Incompleto NUNCA recebe (de propósito) ----
    resultado_fgts_completo, item_fgts_completo = _item_textual(
        'fgts-completo', 'FGTS Digital\nGuia do FGTS\nTotal FGTS', _CLIENTE_COMPLETO)
    fonte_inventario.adicionar(item_fgts_completo)

    # ---- 3) FGTS com REFORÇO FISCAL↔FINALIDADE (Fase 10) -- Condicional ----
    texto_fgts_fiscal = 'Guia do FGTS -- Código de Receita: 0561'
    ocorrencias_fgts = sinais_textuais_de_finalidade_pagamento(texto_fgts_fiscal) + reconciliar_evidencia_fiscal_com_finalidade(texto_fgts_fiscal)
    resolucao_tipo_fgts_fiscal = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_fgts))
    assert resolucao_tipo_fgts_fiscal.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_fgts_fiscal = _resultado_documento_cliente('fgts-fiscal-condicional', _CLIENTE_CONDICIONAL, (2026, 7), resolucao_tipo_fgts_fiscal)
    fonte_inventario.adicionar(resultado_semantico_para_item_inventario('fgts-fiscal-condicional', resultado_fgts_fiscal))
    # 'Comprovante de Pagamento - FGTS' (finalidade) e 'FGTS' (a Guia em
    # si) sao tipos DIFERENTES -- o reforço fiscal só prova a finalidade
    # do comprovante; o requisito de base exige a Guia, dada aqui à parte.
    _, item_fgts_guia_condicional = _item_textual(
        'fgts-guia-condicional', 'FGTS Digital\nGuia do FGTS\nTotal FGTS', _CLIENTE_CONDICIONAL)
    fonte_inventario.adicionar(item_fgts_guia_condicional)
    # Condicional também precisa da base inteira (Extrato) para ficar PRONTO.
    _, item_extrato_condicional = _item_textual(
        'extrato-condicional', 'Extrato Mensal\nExtrato da Folha de Pagamento', _CLIENTE_CONDICIONAL)
    fonte_inventario.adicionar(item_extrato_condicional)

    # ---- 4) Certidão -- só Condicional (satisfaz o requisito condicional real do cadastro) ----
    texto_certidao = 'Certidão Negativa de Débitos\nVálida até 31/12/2026'
    resolucao_tipo_certidao = resolver_tipo_documental(hipoteses_temporais_de_certidao(texto_certidao))
    resultado_certidao = _resultado_documento_cliente('certidao-condicional', _CLIENTE_CONDICIONAL, (2026, 7), resolucao_tipo_certidao)
    fonte_inventario.adicionar(resultado_semantico_para_item_inventario('certidao-condicional', resultado_certidao))

    # ---- 5) Benefício VR/VA -- Completo (extra, não exigido, mas reconhecido) ----
    ocorrencias_vr = sinais_textuais_de_finalidade_pagamento('PIX efetuado -- crédito referente a VR do mês')
    resolucao_tipo_vr = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_vr))
    resultado_vr = _resultado_documento_cliente('beneficio-vr-completo', _CLIENTE_COMPLETO, (2026, 7), resolucao_tipo_vr)
    fonte_inventario.adicionar(resultado_semantico_para_item_inventario('beneficio-vr-completo', resultado_vr))

    # ---- 6) DCTFWeb - Declaração + Recibo -- BROADCAST p/ 5 clientes normais ----
    resolucao_tipo_dctf_decl = _resolucao_tipo_textual('Comprovante emitido pelo sistema DCTFWeb da empresa')
    resolucao_tipo_dctf_recibo = _resolucao_tipo_textual('Recibo de Entrega da DCTFWeb referente à competência')
    clientes_normais = (_CLIENTE_COMPLETO, _CLIENTE_INCOMPLETO, _CLIENTE_REVISAO, _CLIENTE_CONDICIONAL, _CLIENTE_POLITICA_NAO_CONFIGURADA)
    for doc_id, resolucao_tipo in (('dctf-declaracao-global', resolucao_tipo_dctf_decl), ('dctf-recibo-global', resolucao_tipo_dctf_recibo)):
        resultado_broadcast = _compor(
            _perfil_documento_broadcast(),
            (
                resolucao_tipo,
                ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                _resolucao_competencia_confirmada((2026, 7)),
                ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ),
            doc_id,
        )
        fonte_inventario.adicionar(*itens_para_clientes_broadcast(doc_id, resultado_broadcast, clientes_normais))

    # ---- 7) Política-não-configurada -- tem TUDO da base, mas nenhum condicional configurado ----
    for doc_id, texto in (
        ('extrato-politica-nc', 'Extrato Mensal\nExtrato da Folha de Pagamento'),
        ('fgts-politica-nc', 'FGTS Digital\nGuia do FGTS\nTotal FGTS'),
    ):
        _, item = _item_textual(doc_id, texto, _CLIENTE_POLITICA_NAO_CONFIGURADA)
        fonte_inventario.adicionar(item)

    # ---- 8) SKY -- FGTS na competência DESLOCADA ----
    competencia_esperada_sky = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(_CONTEXTO, _SKY, 'FGTS')
    assert competencia_esperada_sky == (2026, 6)
    resultado_fgts_sky, item_fgts_sky = _item_textual('fgts-sky', 'FGTS Digital\nGuia do FGTS\nTotal FGTS', _SKY, competencia_esperada_sky)
    fonte_inventario.adicionar(item_fgts_sky)
    resultado_extrato_sky, item_extrato_sky = _item_textual(
        'extrato-sky', 'Extrato Mensal\nExtrato da Folha de Pagamento', _SKY, competencia_esperada_sky)
    fonte_inventario.adicionar(item_extrato_sky)
    # SKY tambem precisa do broadcast na sua propria competencia deslocada.
    for doc_id, resolucao_tipo in (('dctf-declaracao-sky', resolucao_tipo_dctf_decl), ('dctf-recibo-sky', resolucao_tipo_dctf_recibo)):
        resultado_broadcast_sky = _compor(
            _perfil_documento_broadcast(),
            (
                resolucao_tipo,
                ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                _resolucao_competencia_confirmada(competencia_esperada_sky),
                ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ),
            doc_id,
        )
        item_sky_broadcast = resultado_semantico_para_item_inventario(doc_id, resultado_broadcast_sky, cliente_broadcast=_SKY)
        fonte_inventario.adicionar(item_sky_broadcast)

    # ------------------------------------------------------------------
    # Fontes + ciclo -- FonteRequisitosPrestacaoCanonica REAL (cadastro
    # canônico), nunca uma fixture de requisitos artificiais.
    # ------------------------------------------------------------------
    fonte_clientes = _FonteClientesFake()
    fonte_requisitos = FonteRequisitosPrestacaoCanonica(_CADASTRO_E2E)

    resolucoes_ancora = {
        _CLIENTE_COMPLETO: resultado_fgts_completo,
        _CLIENTE_INCOMPLETO: _resultado_documento_cliente(
            'ancora-incompleto', _CLIENTE_INCOMPLETO, (2026, 7),
            _resolucao_tipo_textual('Extrato Mensal\nExtrato da Folha de Pagamento')),
        _CLIENTE_REVISAO: _compor(
            _perfil_documento_cliente(),
            (
                resolucao_tipo_dctf_decl,
                ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.AMBIGUA, candidatos=(_CLIENTE_COMPLETO, _CLIENTE_REVISAO)),
                _resolucao_competencia_confirmada((2026, 7)),
                ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
                ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ),
            'ancora-revisao',
        ),
        _CLIENTE_CONDICIONAL: resultado_fgts_fiscal,
        _CLIENTE_POLITICA_NAO_CONFIGURADA: _resultado_documento_cliente(
            'ancora-politica-nc', _CLIENTE_POLITICA_NAO_CONFIGURADA, (2026, 7),
            _resolucao_tipo_textual('FGTS Digital\nGuia do FGTS\nTotal FGTS')),
        _SKY: resultado_fgts_sky,
    }
    competencias_por_cliente = {
        _CLIENTE_COMPLETO: _COMPETENCIA_BASE, _CLIENTE_INCOMPLETO: _COMPETENCIA_BASE,
        _CLIENTE_REVISAO: _COMPETENCIA_BASE, _CLIENTE_CONDICIONAL: _COMPETENCIA_BASE,
        _CLIENTE_POLITICA_NAO_CONFIGURADA: _COMPETENCIA_BASE, _SKY: _COMPETENCIA_SKY,
    }

    resultado_ciclo = executar_ciclo_prestacao(
        contexto=_CONTEXTO, fonte_clientes=fonte_clientes, fonte_requisitos=fonte_requisitos,
        fonte_inventario=fonte_inventario, requisitos_base=_CADASTRO_E2E.requisitos_base_documentais(),
        resolucoes_ancora=resolucoes_ancora, competencias_por_cliente=competencias_por_cliente,
        tipos_condicionais_para_auditoria=_TIPOS_DIVERGENTES,
    )

    assert len(resultado_ciclo.resultados_por_cliente) == 6
    assert set(resultado_ciclo.prontos) == {_CLIENTE_COMPLETO, _CLIENTE_CONDICIONAL, _CLIENTE_POLITICA_NAO_CONFIGURADA, _SKY}
    assert set(resultado_ciclo.incompletos) == {_CLIENTE_INCOMPLETO}
    assert set(resultado_ciclo.em_revisao) == {_CLIENTE_REVISAO}
    assert resultado_ciclo.bloqueados == ()

    # Fase 13: faltando != não configurado -- nunca aparecem juntos.
    resultado_incompleto = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_INCOMPLETO)
    assert resultado_incompleto.pacote.tipos_faltantes == ('FGTS',)
    assert set(resultado_incompleto.requisitos_nao_configurados) == set(_TIPOS_DIVERGENTES)
    assert not (set(resultado_incompleto.pacote.tipos_faltantes) & set(resultado_incompleto.requisitos_nao_configurados))

    resultado_nc = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_POLITICA_NAO_CONFIGURADA)
    assert resultado_nc.pacote.estado == EstadoPacotePrestacao.PRONTO
    assert resultado_nc.pacote.tipos_faltantes == ()
    assert set(resultado_nc.requisitos_nao_configurados) == set(_TIPOS_DIVERGENTES)

    resultado_condicional = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_CONDICIONAL)
    assert resultado_condicional.pacote.estado == EstadoPacotePrestacao.PRONTO
    assert 'Certidão' not in resultado_condicional.requisitos_nao_configurados  # foi configurado, nao "nao configurado"

    resultado_sky = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _SKY)
    assert resultado_sky.competencia == _COMPETENCIA_SKY
    assert resultado_sky.pacote.estado == EstadoPacotePrestacao.PRONTO

    # Broadcast: DCTFWeb Declaração + Recibo presentes nos 5 clientes normais.
    for cliente in clientes_normais:
        tipos_no_inventario = {item.tipo_documental for item in fonte_inventario.listar(cliente, _COMPETENCIA_BASE)}
        assert {'DCTFWeb - Declaração', 'DCTFWeb - Recibo de Entrega'} <= tipos_no_inventario
