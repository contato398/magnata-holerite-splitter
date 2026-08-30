"""E2E do primeiro CICLO PILOTO real, READ-ONLY (missão "FECHAMENTO DA
BASE CANÔNICA + PREPARAÇÃO DO PRIMEIRO CICLO PILOTO REAL READ-ONLY").

Usa o CADASTRO CANÔNICO V2 (`CADASTRO_REQUISITOS_PRESTACAO_V2`) -- Guia
DCTFWeb/DARF já na base universal. Holerite é universal (ADENDO DE
CONTINUIDADE revogou, no mesmo dia, a instrução intermediária desta
missão que o tornaria condicional -- ver docs/decisoes/
fechamento-base-canonica-ciclo-piloto-readonly-v1.md), avaliado por
CARDINALIDADE colaborador para TODO cliente com `fonte_colaboradores_
esperados` disponível -- por isso, nesta suíte, a fonte fake devolve
zero colaboradores esperados para os clientes que não são o foco do
teste de Holerite (vacuamente satisfeito, sem impacto no pacote) e só
popula colaboradores reais para `_CLIENTE_HOLERITE_INCOMPLETO`.

5 clientes sintéticos (nenhum cliente real ainda existe -- mesma
disciplina já usada em `test_ciclo_prestacao_cadastro_canonico_e2e.py`):

  - `_CLIENTE_COMUM`: zero condicionais, base V2 inteira presente,
    zero colaboradores esperados -> PRONTO. Prova "sem configuração de
    benefício -> NAO_CONFIGURADO, nunca requisito universal".
  - `_CLIENTE_HOLERITE_INCOMPLETO`: 3 colaboradores esperados / 2
    Holerites presentes / 1 ausente -> INCOMPLETO por cardinalidade
    (nunca contagem plana, nunca gateado por configuração condicional).
  - `_CLIENTE_GUIA_AUSENTE`: zero condicionais, zero colaboradores
    esperados (Holerite vacuamente satisfeito), base completa EXCETO
    Guia DCTFWeb/DARF (documento realmente ausente) -> INCOMPLETO só
    por Guia DCTFWeb/DARF.
  - `_CLIENTE_BENEFICIO_CONDICIONAL`: CONFIGURADO_EXIGE para "Horas
    Extras", documento presente -> PRONTO, benefício nunca NAO_
    CONFIGURADO (foi configurado).
  - `_SKY`: competência efetiva = base - 1 mês (regra já provada,
    inalterada), base completa na competência deslocada.

Ao final, roda pelo runner READ-ONLY (`ciclo_piloto_prestacao.py`) e
prova que a saída DRY-RUN nunca carrega CPF, nome, texto de documento,
token ou payload -- só os 7 campos sanitizados especificados."""
import re

from magnata_os.classificacao.adaptador_inventario_prestacao import (
    itens_para_clientes_broadcast,
    resultado_semantico_para_item_inventario,
)
from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    CADASTRO_REQUISITOS_PRESTACAO_V2,
    HOLERITE_TIPO_DOCUMENTAL,
    CadastroRequisitosPrestacao,
    ConfiguracaoCondicionalCliente,
    EstadoConfiguracaoRequisito,
    FonteRequisitosPrestacaoCanonica,
)
from magnata_os.classificacao.ciclo_piloto_prestacao import (
    LinhaDryRunCicloPiloto,
    executar_ciclo_piloto_readonly,
)
from magnata_os.classificacao.classificador_documental import classificar_documento
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
from magnata_os.classificacao.resolucao_semantica import (
    compor_resolucao_semantica,
    resolucao_competencia_de_validacao,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.documental.importacao_lote.contratos import (
    CompetenciaExtraida,
    StatusExtracaoCompetencia,
)
from magnata_os.documental.importacao_lote.dominio import validar_competencia

_CLIENTE_COMUM = ReferenciaCanonica('CLIENTE', 'rec_comum')
_CLIENTE_HOLERITE_INCOMPLETO = ReferenciaCanonica('CLIENTE', 'rec_holerite_incompleto')
_CLIENTE_GUIA_AUSENTE = ReferenciaCanonica('CLIENTE', 'rec_guia_ausente')
_CLIENTE_BENEFICIO_CONDICIONAL = ReferenciaCanonica('CLIENTE', 'rec_beneficio_condicional')
_SKY = REFERENCIA_CLIENTE_SKY_TATUI

_TODOS_OS_CLIENTES = (
    _CLIENTE_COMUM, _CLIENTE_HOLERITE_INCOMPLETO, _CLIENTE_GUIA_AUSENTE,
    _CLIENTE_BENEFICIO_CONDICIONAL, _SKY,
)

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_COMPETENCIA_BASE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_SKY = ReferenciaCanonica('COMPETENCIA', '2026-06')

_COLAB_A = ReferenciaCanonica('COLABORADOR', 'rec_colab_a')
_COLAB_B = ReferenciaCanonica('COLABORADOR', 'rec_colab_b')
_COLAB_C = ReferenciaCanonica('COLABORADOR', 'rec_colab_c')

_TIPO_HORAS_EXTRAS = 'Comprovante de Pagamento - Horas Extras'

_TIPOS_PARA_AUDITORIA = (_TIPO_HORAS_EXTRAS,)
# Holerite não entra na auditoria de "não configurado": desde o ADENDO
# DE CONTINUIDADE, sua obrigatoriedade nunca passa por
# `ConfiguracaoCondicionalCliente` -- é universal, avaliada à parte por
# cardinalidade (ver docstring do módulo).

# Cadastro do E2E: base REAL V2 (comprovada) + 1 condicional SINTÉTICO
# (só o cliente é sintético -- base e mecanismo são os reais). Holerite
# nunca é um `ConfiguracaoCondicionalCliente` (não é mais o mecanismo
# usado para ele, ver docstring do módulo).
_CADASTRO_E2E = CadastroRequisitosPrestacao(
    versao='e2e-ciclo-piloto', requisitos_base=CADASTRO_REQUISITOS_PRESTACAO_V2.requisitos_base,
    condicionais=(
        ConfiguracaoCondicionalCliente(
            _CLIENTE_BENEFICIO_CONDICIONAL.entidade_id, _TIPO_HORAS_EXTRAS,
            EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE,
            evidencia='configuracao sintetica de teste -- cliente confirmado a exigir Horas Extras',
        ),
    ),
)


class _FonteClientesFake:
    def listar_ativos(self, contexto):
        return _TODOS_OS_CLIENTES


class _FonteColaboradoresEsperadosFake:
    """Holerite é universal (avaliado por cardinalidade sempre que esta
    fonte está disponível, ADENDO DE CONTINUIDADE) -- para manter o
    teste focado, só `_CLIENTE_HOLERITE_INCOMPLETO` tem colaboradores
    esperados de fato; para os demais, a fonte devolve `()` (vacuamente
    satisfeito, sem impacto algum no pacote)."""

    def colaboradores_esperados_para(self, cliente, contexto):
        if cliente == _CLIENTE_HOLERITE_INCOMPLETO:
            return (_COLAB_A, _COLAB_B, _COLAB_C)
        return ()


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
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='ciclo-piloto-e2e',
            resolver_version='1', politica_id=perfil.perfil_id, politica_version='1',
            contexto_fontes_fingerprint='ciclo-piloto-prestacao-readonly-e2e',
        ),
        perfil=perfil, resolucoes=resolucoes,
    )


def _resolucao_tipo_textual(texto):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=1)


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
    resolucao_tipo = _resolucao_tipo_textual(texto)
    resultado = _resultado_documento_cliente(documento_id, cliente, ano_mes, resolucao_tipo)
    return resultado, resultado_semantico_para_item_inventario(documento_id, resultado)


def _item_holerite_colaborador(documento_id, cliente, colaborador, ano_mes=(2026, 7)):
    """Holerite construído diretamente (mesma técnica do adendo original
    -- granularidade colaborador não passa pelo classificador textual
    genérico de cliente, exige o perfil próprio com COLABORADOR
    obrigatório)."""
    resultado = _compor(
        _perfil_documento_colaborador(),
        (
            ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', HOLERITE_TIPO_DOCUMENTAL),)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(cliente,)),
            _resolucao_competencia_confirmada(ano_mes),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(colaborador,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
        documento_id,
    )
    return resultado_semantico_para_item_inventario(documento_id, resultado)


def test_ciclo_piloto_readonly_e2e_com_cadastro_v2():
    fonte_inventario = _FonteInventarioMemoria()

    # ---- Cliente COMUM: base V2 inteira presente, zero condicionais ----
    for doc_id, texto in (
        ('extrato-comum', 'Extrato Mensal\nExtrato da Folha de Pagamento'),
        ('fgts-comum', 'FGTS Digital\nGuia do FGTS\nTotal FGTS'),
        ('guia-dctf-darf-comum', 'Guia de Recolhimento DCTFWeb'),
    ):
        _, item = _item_textual(doc_id, texto, _CLIENTE_COMUM)
        fonte_inventario.adicionar(item)

    # ---- Cliente HOLERITE_CONFIGURADO: base completa + 2/3 Holerites ----
    for doc_id, texto in (
        ('extrato-holerite-cfg', 'Extrato Mensal\nExtrato da Folha de Pagamento'),
        ('fgts-holerite-cfg', 'FGTS Digital\nGuia do FGTS\nTotal FGTS'),
        ('guia-dctf-darf-holerite-cfg', 'Guia de Recolhimento DCTFWeb'),
    ):
        _, item = _item_textual(doc_id, texto, _CLIENTE_HOLERITE_INCOMPLETO)
        fonte_inventario.adicionar(item)
    fonte_inventario.adicionar(_item_holerite_colaborador('holerite-a', _CLIENTE_HOLERITE_INCOMPLETO, _COLAB_A))
    fonte_inventario.adicionar(_item_holerite_colaborador('holerite-b', _CLIENTE_HOLERITE_INCOMPLETO, _COLAB_B))
    # _COLAB_C nunca recebe Holerite -- de propósito, prova a lacuna.

    # ---- Cliente GUIA_AUSENTE_HOLERITE_NC: tudo OK, SEM Guia DCTFWeb/DARF, SEM Holerite ----
    for doc_id, texto in (
        ('extrato-guia-ausente', 'Extrato Mensal\nExtrato da Folha de Pagamento'),
        ('fgts-guia-ausente', 'FGTS Digital\nGuia do FGTS\nTotal FGTS'),
    ):
        _, item = _item_textual(doc_id, texto, _CLIENTE_GUIA_AUSENTE)
        fonte_inventario.adicionar(item)

    # ---- Cliente BENEFICIO_CONDICIONAL: base completa + Horas Extras presente ----
    for doc_id, texto in (
        ('extrato-beneficio', 'Extrato Mensal\nExtrato da Folha de Pagamento'),
        ('fgts-beneficio', 'FGTS Digital\nGuia do FGTS\nTotal FGTS'),
        ('guia-dctf-darf-beneficio', 'Guia de Recolhimento DCTFWeb'),
    ):
        _, item = _item_textual(doc_id, texto, _CLIENTE_BENEFICIO_CONDICIONAL)
        fonte_inventario.adicionar(item)
    ocorrencias_he = sinais_textuais_de_finalidade_pagamento('PIX efetuado -- pagamento de horas extras do mes')
    resolucao_tipo_he = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_he))
    assert resolucao_tipo_he.estado == EstadoResolucaoDimensao.RESOLVIDA
    resultado_he = _resultado_documento_cliente('horas-extras-beneficio', _CLIENTE_BENEFICIO_CONDICIONAL, (2026, 7), resolucao_tipo_he)
    fonte_inventario.adicionar(resultado_semantico_para_item_inventario('horas-extras-beneficio', resultado_he))

    # ---- Broadcast DCTFWeb Declaração + Recibo para os 4 clientes normais ----
    resolucao_tipo_dctf_decl = _resolucao_tipo_textual('Comprovante emitido pelo sistema DCTFWeb da empresa')
    resolucao_tipo_dctf_recibo = _resolucao_tipo_textual('Recibo de Entrega da DCTFWeb referente à competência')
    clientes_normais = (_CLIENTE_COMUM, _CLIENTE_HOLERITE_INCOMPLETO, _CLIENTE_GUIA_AUSENTE, _CLIENTE_BENEFICIO_CONDICIONAL)
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

    # ---- SKY: base completa na competência deslocada (base - 1 mês) ----
    competencia_esperada_sky = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(_CONTEXTO, _SKY, 'FGTS')
    assert competencia_esperada_sky == (2026, 6)
    resultado_fgts_sky, item_fgts_sky = _item_textual('fgts-sky', 'FGTS Digital\nGuia do FGTS\nTotal FGTS', _SKY, competencia_esperada_sky)
    fonte_inventario.adicionar(item_fgts_sky)
    _, item_extrato_sky = _item_textual('extrato-sky', 'Extrato Mensal\nExtrato da Folha de Pagamento', _SKY, competencia_esperada_sky)
    fonte_inventario.adicionar(item_extrato_sky)
    _, item_guia_sky = _item_textual('guia-dctf-darf-sky', 'Guia de Recolhimento DCTFWeb', _SKY, competencia_esperada_sky)
    fonte_inventario.adicionar(item_guia_sky)
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
        fonte_inventario.adicionar(resultado_semantico_para_item_inventario(doc_id, resultado_broadcast_sky, cliente_broadcast=_SKY))

    # ------------------------------------------------------------------
    fonte_clientes = _FonteClientesFake()
    fonte_requisitos = FonteRequisitosPrestacaoCanonica(_CADASTRO_E2E)

    resolucoes_ancora = {
        _CLIENTE_COMUM: _resultado_documento_cliente(
            'ancora-comum', _CLIENTE_COMUM, (2026, 7), _resolucao_tipo_textual('FGTS Digital\nGuia do FGTS\nTotal FGTS')),
        _CLIENTE_HOLERITE_INCOMPLETO: _resultado_documento_cliente(
            'ancora-holerite-cfg', _CLIENTE_HOLERITE_INCOMPLETO, (2026, 7),
            _resolucao_tipo_textual('FGTS Digital\nGuia do FGTS\nTotal FGTS')),
        _CLIENTE_GUIA_AUSENTE: _resultado_documento_cliente(
            'ancora-guia-ausente', _CLIENTE_GUIA_AUSENTE, (2026, 7),
            _resolucao_tipo_textual('FGTS Digital\nGuia do FGTS\nTotal FGTS')),
        _CLIENTE_BENEFICIO_CONDICIONAL: _resultado_documento_cliente(
            'ancora-beneficio', _CLIENTE_BENEFICIO_CONDICIONAL, (2026, 7),
            _resolucao_tipo_textual('FGTS Digital\nGuia do FGTS\nTotal FGTS')),
        _SKY: resultado_fgts_sky,
    }
    competencias_por_cliente = {
        _CLIENTE_COMUM: _COMPETENCIA_BASE, _CLIENTE_HOLERITE_INCOMPLETO: _COMPETENCIA_BASE,
        _CLIENTE_GUIA_AUSENTE: _COMPETENCIA_BASE, _CLIENTE_BENEFICIO_CONDICIONAL: _COMPETENCIA_BASE,
        _SKY: _COMPETENCIA_SKY,
    }

    linhas = executar_ciclo_piloto_readonly(
        contexto=_CONTEXTO, fonte_clientes=fonte_clientes, fonte_requisitos=fonte_requisitos,
        fonte_inventario=fonte_inventario, requisitos_base=_CADASTRO_E2E.requisitos_base_documentais(),
        resolucoes_ancora=resolucoes_ancora, competencias_por_cliente=competencias_por_cliente,
        tipos_condicionais_para_auditoria=_TIPOS_PARA_AUDITORIA,
        fonte_colaboradores_esperados=_FonteColaboradoresEsperadosFake(),
    )

    assert len(linhas) == 5
    assert all(isinstance(linha, LinhaDryRunCicloPiloto) for linha in linhas)
    por_cliente = {linha.cliente_id: linha for linha in linhas}

    # ---- Cliente comum: PRONTO (zero colaboradores esperados -> Holerite vacuamente OK); Horas Extras NAO_CONFIGURADO ----
    comum = por_cliente[_CLIENTE_COMUM.entidade_id]
    assert comum.estado == EstadoPacotePrestacao.PRONTO.value
    assert comum.faltantes == ()
    assert set(comum.nao_configurados) == {_TIPO_HORAS_EXTRAS}
    assert not comum.em_revisao

    # ---- Cliente Holerite incompleto: INCOMPLETO por cardinalidade (universal, nunca gateado por configuração) ----
    holerite_incompleto = por_cliente[_CLIENTE_HOLERITE_INCOMPLETO.entidade_id]
    assert holerite_incompleto.estado == EstadoPacotePrestacao.INCOMPLETO.value
    assert HOLERITE_TIPO_DOCUMENTAL in holerite_incompleto.faltantes
    assert HOLERITE_TIPO_DOCUMENTAL not in holerite_incompleto.nao_configurados  # nunca via cadastro condicional

    # ---- Cliente Guia ausente: INCOMPLETO SÓ por Guia DCTFWeb/DARF; Holerite vacuamente OK (zero esperados) ----
    guia_ausente = por_cliente[_CLIENTE_GUIA_AUSENTE.entidade_id]
    assert guia_ausente.estado == EstadoPacotePrestacao.INCOMPLETO.value
    assert guia_ausente.faltantes == ('Guia DCTFWeb/DARF',)
    assert HOLERITE_TIPO_DOCUMENTAL not in guia_ausente.faltantes
    assert HOLERITE_TIPO_DOCUMENTAL not in guia_ausente.nao_configurados  # Holerite nunca aparece via este mecanismo

    # ---- Cliente benefício condicional: PRONTO, Horas Extras NUNCA "nao configurado" ----
    beneficio = por_cliente[_CLIENTE_BENEFICIO_CONDICIONAL.entidade_id]
    assert beneficio.estado == EstadoPacotePrestacao.PRONTO.value
    assert _TIPO_HORAS_EXTRAS not in beneficio.nao_configurados
    assert HOLERITE_TIPO_DOCUMENTAL not in beneficio.nao_configurados  # Holerite nunca passa pelo cadastro condicional

    # ---- SKY: competência efetiva deslocada, PRONTO ----
    sky = por_cliente[_SKY.entidade_id]
    assert sky.competencia_efetiva == '2026-06'
    assert sky.estado == EstadoPacotePrestacao.PRONTO.value

    # ---- Restrição de segurança do dry-run: nunca CPF/nome/token/payload ----
    _PADRAO_CPF = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}')
    for linha in linhas:
        texto_serializado = repr(linha)
        assert not _PADRAO_CPF.search(texto_serializado)
        assert 'token' not in texto_serializado.lower()
        assert 'fields' not in texto_serializado.lower()  # nunca payload cru do Airtable (chave "fields")
        # cliente_id nunca é um nome (nenhum espaço) -- sempre um id de registro
        assert ' ' not in linha.cliente_id
        for tipo in linha.presentes + linha.faltantes + linha.nao_configurados:
            assert ' ' not in tipo or tipo in (
                'DCTFWeb - Declaração', 'DCTFWeb - Recibo de Entrega', 'Extrato da Folha de Pagamento',
                'Guia DCTFWeb/DARF', HOLERITE_TIPO_DOCUMENTAL, _TIPO_HORAS_EXTRAS,
            )  # só vocabulário fixo do motor, nunca texto livre de documento
