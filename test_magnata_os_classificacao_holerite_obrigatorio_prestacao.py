"""Testes obrigatórios do Adendo de Regra de Negócio — Holerite
(missão "CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO"):

  - ponto 11: cliente com 3 colaboradores esperados, 2 Holerites
    presentes, 1 ausente -> pacote INCOMPLETO, com identificação
    sanitizada de 1 necessidade de Holerite, sem CPF/nome.
  - ponto 12: colaborador vinculado a 2 clientes -> mesmo Holerite
    válido logicamente para ambos os pacotes, 1 identidade documental
    única (nunca duplicada fisicamente).

HISTÓRICO DE 3 DECISÕES (mesmo humano, mensagens distintas, mesmo dia,
todas antes de qualquer PR ser mesclado):
  (a) Adendo original: Holerite universal, cardinalidade colaborador
      (o que este arquivo testa desde o início).
  (b) Missão "FECHAMENTO DA BASE CANÔNICA" instruiu reverter (a) para
      condicional-por-cliente.
  (c) "ADENDO DE CONTINUIDADE" do mesmo dia revogou (b) explicitamente
      e restaurou (a) integralmente -- Holerite nunca chegou a virar
      condicional em produção.
Efeito líquido: nenhuma mudança de comportamento em relação ao Adendo
original. Os testes abaixo continuam testando o MECANISMO universal por
cardinalidade, sem gate por configuração -- ver docs/decisoes/
fechamento-base-canonica-ciclo-piloto-readonly-v1.md para a cronologia
completa e transparente."""
from magnata_os.classificacao.adaptador_inventario_prestacao import (
    itens_para_multiplos_clientes_do_vinculo,
    resultado_semantico_para_item_inventario,
)
from magnata_os.classificacao.ciclo_prestacao import (
    NecessidadeDocumentoPrestacao,
    executar_ciclo_prestacao,
)
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
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
from magnata_os.classificacao.holerite_obrigatorio_prestacao import (
    TIPO_HOLERITE,
    avaliar_obrigatoriedade_holerite,
)
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
    combinar_pacote_com_holerite,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COLAB_A = ReferenciaCanonica('COLABORADOR', 'rec_colab_a')
_COLAB_B = ReferenciaCanonica('COLABORADOR', 'rec_colab_b')
_COLAB_C = ReferenciaCanonica('COLABORADOR', 'rec_colab_c')


# ============================================================================
# Ponto 11 -- cliente com 3 colaboradores esperados, 1 Holerite ausente
# ============================================================================

def test_avaliar_obrigatoriedade_identifica_exatamente_o_colaborador_ausente():
    colaboradores_esperados = (_COLAB_A, _COLAB_B, _COLAB_C)
    inventario = (
        ItemInventarioPrestacao('holerite-a', TIPO_HOLERITE, _CLIENTE, _COMPETENCIA, colaborador=_COLAB_A),
        ItemInventarioPrestacao('holerite-b', TIPO_HOLERITE, _CLIENTE, _COMPETENCIA, colaborador=_COLAB_B),
    )
    resultado = avaliar_obrigatoriedade_holerite(_CLIENTE, _COMPETENCIA, colaboradores_esperados, inventario)
    assert resultado.colaboradores_com_holerite == (_COLAB_A, _COLAB_B)
    assert resultado.colaboradores_faltantes == (_COLAB_C,)
    assert not resultado.completo


def test_pacote_pronto_na_base_vira_incompleto_por_holerite_faltante():
    colaboradores_esperados = (_COLAB_A, _COLAB_B, _COLAB_C)
    inventario = (
        ItemInventarioPrestacao('holerite-a', TIPO_HOLERITE, _CLIENTE, _COMPETENCIA, colaborador=_COLAB_A),
        ItemInventarioPrestacao('holerite-b', TIPO_HOLERITE, _CLIENTE, _COMPETENCIA, colaborador=_COLAB_B),
        ItemInventarioPrestacao('fgts-1', 'FGTS', _CLIENTE, _COMPETENCIA),
    )
    resultado_holerite = avaliar_obrigatoriedade_holerite(_CLIENTE, _COMPETENCIA, colaboradores_esperados, inventario)

    pacote_base = PacotePrestacaoCliente(
        cliente=_CLIENTE, competencia=_COMPETENCIA, estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=inventario, tipos_obrigatorios=('FGTS',),
    )
    pacote_final = combinar_pacote_com_holerite(pacote_base, resultado_holerite)

    assert pacote_final.estado == EstadoPacotePrestacao.INCOMPLETO
    assert TIPO_HOLERITE in pacote_final.tipos_faltantes
    assert pacote_final.holerite.colaboradores_faltantes == (_COLAB_C,)


def test_necessidade_de_holerite_carrega_identificacao_sanitizada_sem_cpf_ou_nome():
    """Identificação SANITIZADA: sempre `ReferenciaCanonica('COLABORADOR',
    id_interno)` -- nunca formato de CPF (com pontuação) nem nome (com
    espaço) em observabilidade."""
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=TIPO_HOLERITE,
        motivo_exigencia='holerite_obrigatorio_por_colaborador_esperado',
        colaborador=_COLAB_C,
    )
    assert necessidade.colaborador == _COLAB_C
    assert necessidade.colaborador.tipo_entidade == 'COLABORADOR'
    # nunca CPF (dígitos+pontuação) nem nome (espaço) no identificador exposto.
    assert '.' not in necessidade.colaborador.entidade_id
    assert '-' not in necessidade.colaborador.entidade_id or necessidade.colaborador.entidade_id == 'rec_colab_c'
    assert ' ' not in necessidade.colaborador.entidade_id


def test_holerite_completo_nunca_rebaixa_um_pacote_ja_pronto():
    colaboradores_esperados = (_COLAB_A,)
    inventario = (ItemInventarioPrestacao('holerite-a', TIPO_HOLERITE, _CLIENTE, _COMPETENCIA, colaborador=_COLAB_A),)
    resultado_holerite = avaliar_obrigatoriedade_holerite(_CLIENTE, _COMPETENCIA, colaboradores_esperados, inventario)
    assert resultado_holerite.completo

    pacote_base = PacotePrestacaoCliente(
        cliente=_CLIENTE, competencia=_COMPETENCIA, estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=inventario, tipos_obrigatorios=(),
    )
    pacote_final = combinar_pacote_com_holerite(pacote_base, resultado_holerite)
    assert pacote_final.estado == EstadoPacotePrestacao.PRONTO
    assert pacote_final.tipos_faltantes == ()
    assert pacote_final.holerite.completo


def test_holerite_faltante_nunca_promove_pacote_ja_bloqueado():
    """Holerite completo/incompleto NUNCA melhora um pacote já pior
    (BLOQUEADO/EM_REVISAO) -- só piora um PRONTO."""
    colaboradores_esperados = (_COLAB_A,)
    inventario = ()
    resultado_holerite = avaliar_obrigatoriedade_holerite(_CLIENTE, _COMPETENCIA, colaboradores_esperados, inventario)
    assert not resultado_holerite.completo

    pacote_bloqueado = PacotePrestacaoCliente(
        cliente=_CLIENTE, competencia=_COMPETENCIA, estado=EstadoPacotePrestacao.BLOQUEADO,
        itens_incluidos=(), tipos_obrigatorios=(),
    )
    pacote_final = combinar_pacote_com_holerite(pacote_bloqueado, resultado_holerite)
    assert pacote_final.estado == EstadoPacotePrestacao.BLOQUEADO  # nunca piora nem melhora o estado em si


# ============================================================================
# Ponto 12 -- colaborador vinculado a 2 clientes, 1 identidade documental
# ============================================================================

def _perfil_holerite_multi_cliente():
    return PerfilAplicabilidadeResolucao(
        perfil_id='holerite-multi-cliente-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, None)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def test_colaborador_vinculado_a_2_clientes_gera_mesmo_holerite_para_ambos():
    cliente_x = ReferenciaCanonica('CLIENTE', 'rec_x')
    cliente_y = ReferenciaCanonica('CLIENTE', 'rec_y')

    resolucao = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='holerite-multi-1', hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste-vinculo-multiplo',
        ),
        perfil=_perfil_holerite_multi_cliente(),
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(cliente_x, cliente_y)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COMPETENCIA,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COLAB_A,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )

    itens = itens_para_multiplos_clientes_do_vinculo('holerite-multi-1', resolucao)
    assert len(itens) == 2
    assert {item.cliente for item in itens} == {cliente_x, cliente_y}
    # MESMA identidade documental -- nunca duplicada fisicamente.
    assert len({item.documento_id for item in itens}) == 1
    assert all(item.documento_id == 'holerite-multi-1' for item in itens)
    assert all(item.colaborador == _COLAB_A for item in itens)
    assert all(item.tipo_documental == 'Holerite' for item in itens)


def test_vinculo_unico_nao_confundido_com_multiplo():
    """Cliente único (RESOLVIDA com 1 valor) -- ainda funciona, devolve
    1 item só, nunca força múltiplos onde não há."""
    resolucao = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='holerite-unico-1', hash_sha256='b' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=_perfil_holerite_multi_cliente(),
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_CLIENTE,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COMPETENCIA,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COLAB_A,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )
    itens = itens_para_multiplos_clientes_do_vinculo('holerite-unico-1', resolucao)
    assert len(itens) == 1
    assert itens[0].cliente == _CLIENTE


def test_cliente_ambiguo_nunca_vira_multiplos_itens():
    """AMBIGUA nunca é confundida com vínculo múltiplo legítimo --
    devolve tupla vazia, nunca inventa itens a partir de candidatos não
    confirmados."""
    resolucao = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='holerite-ambiguo-1', hash_sha256='c' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=_perfil_holerite_multi_cliente(),
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.AMBIGUA,
                               candidatos=(ReferenciaCanonica('CLIENTE', 'rec_x'), ReferenciaCanonica('CLIENTE', 'rec_y'))),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COMPETENCIA,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COLAB_A,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )
    assert itens_para_multiplos_clientes_do_vinculo('holerite-ambiguo-1', resolucao) == ()


# ============================================================================
# E2E -- integração completa via executar_ciclo_prestacao (ponto 10 do
# adendo: "atualizar... testes; E2E").
# ============================================================================

def _perfil_holerite_1_cliente():
    return PerfilAplicabilidadeResolucao(
        perfil_id='holerite-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def _resolucao_holerite(colaborador):
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=f'holerite-{colaborador.entidade_id}', hash_sha256='d' * 64, resolver_id='r',
            resolver_version='1', politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste-e2e',
        ),
        perfil=_perfil_holerite_1_cliente(),
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_CLIENTE,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(_COMPETENCIA,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
                               valores_confirmados=(colaborador,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )


class _FonteClientesUmAtivo:
    def listar_ativos(self, contexto):
        return (_CLIENTE,)


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteInventarioMemoria:
    def __init__(self, itens):
        self._itens = itens

    def listar(self, cliente, competencia):
        return tuple(i for i in self._itens if i.cliente == cliente and i.competencia == competencia)


class _FonteColaboradoresEsperadosFake:
    def __init__(self, colaboradores):
        self._colaboradores = colaboradores

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._colaboradores


def test_e2e_ciclo_completo_com_holerite_por_cardinalidade():
    """Ponto 11 ponta-a-ponta: cliente com 3 colaboradores esperados,
    2 Holerites presentes, 1 ausente -> pacote INCOMPLETO via
    executar_ciclo_prestacao (nunca uma peça isolada). Holerite é
    universal -- nenhuma configuração de `fonte_requisitos` é necessária
    para acionar a avaliação por cardinalidade (basta `fonte_
    colaboradores_esperados` estar disponível)."""
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    resultado_a = _resolucao_holerite(_COLAB_A)
    resultado_b = _resolucao_holerite(_COLAB_B)
    item_a = resultado_semantico_para_item_inventario(f'holerite-{_COLAB_A.entidade_id}', resultado_a)
    item_b = resultado_semantico_para_item_inventario(f'holerite-{_COLAB_B.entidade_id}', resultado_b)
    assert item_a is not None and item_b is not None

    resultado_ciclo = executar_ciclo_prestacao(
        contexto=contexto,
        fonte_clientes=_FonteClientesUmAtivo(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioMemoria((item_a, item_b)),
        requisitos_base=(),
        resolucoes_ancora={_CLIENTE: resultado_a},
        competencias_por_cliente={_CLIENTE: _COMPETENCIA},
        fonte_colaboradores_esperados=_FonteColaboradoresEsperadosFake((_COLAB_A, _COLAB_B, _COLAB_C)),
    )

    assert len(resultado_ciclo.resultados_por_cliente) == 1
    resultado = resultado_ciclo.resultados_por_cliente[0]
    assert resultado.pacote.estado == EstadoPacotePrestacao.INCOMPLETO
    assert TIPO_HOLERITE in resultado.pacote.tipos_faltantes
    assert resultado.pacote.holerite.colaboradores_faltantes == (_COLAB_C,)

    necessidades_holerite = [n for n in resultado.necessidades if n.tipo_documental == TIPO_HOLERITE]
    assert len(necessidades_holerite) == 1
    assert necessidades_holerite[0].colaborador == _COLAB_C


# ============================================================================
# ADENDO DE CONTINUIDADE, item 5 -- teste E2E obrigatório adicional:
# cliente com 4 colaboradores esperados (4/4 completo; 3/4 incompleto
# com exatamente 1 necessidade sanitizada).
# ============================================================================

_COLAB_D = ReferenciaCanonica('COLABORADOR', 'rec_colab_d')


def test_quatro_colaboradores_esperados_quatro_presentes_holerite_completo():
    colaboradores_esperados = (_COLAB_A, _COLAB_B, _COLAB_C, _COLAB_D)
    inventario = tuple(
        ItemInventarioPrestacao(f'holerite-{c.entidade_id}', TIPO_HOLERITE, _CLIENTE, _COMPETENCIA, colaborador=c)
        for c in colaboradores_esperados
    )
    resultado = avaliar_obrigatoriedade_holerite(_CLIENTE, _COMPETENCIA, colaboradores_esperados, inventario)
    assert resultado.completo
    assert resultado.colaboradores_faltantes == ()
    assert set(resultado.colaboradores_com_holerite) == set(colaboradores_esperados)


def test_e2e_quatro_colaboradores_esperados_tres_presentes_pacote_incompleto_com_uma_necessidade():
    """4 colaboradores esperados, 3 Holerites presentes, 1 ausente (o
    4º) -> pacote INCOMPLETO via executar_ciclo_prestacao, com
    EXATAMENTE 1 necessidade sanitizada de Holerite (nunca 1 por tipo
    faltante genérico, nunca CPF/nome)."""
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    colaboradores_esperados = (_COLAB_A, _COLAB_B, _COLAB_C, _COLAB_D)
    resolucoes = [_resolucao_holerite(c) for c in colaboradores_esperados[:3]]  # _COLAB_D fica sem Holerite
    itens = [
        resultado_semantico_para_item_inventario(f'holerite-{c.entidade_id}', r)
        for c, r in zip(colaboradores_esperados[:3], resolucoes)
    ]
    assert all(item is not None for item in itens)

    resultado_ciclo = executar_ciclo_prestacao(
        contexto=contexto,
        fonte_clientes=_FonteClientesUmAtivo(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioMemoria(tuple(itens)),
        requisitos_base=(),
        resolucoes_ancora={_CLIENTE: resolucoes[0]},
        competencias_por_cliente={_CLIENTE: _COMPETENCIA},
        fonte_colaboradores_esperados=_FonteColaboradoresEsperadosFake(colaboradores_esperados),
    )

    assert len(resultado_ciclo.resultados_por_cliente) == 1
    resultado = resultado_ciclo.resultados_por_cliente[0]
    assert resultado.pacote.estado == EstadoPacotePrestacao.INCOMPLETO
    assert resultado.pacote.holerite.colaboradores_faltantes == (_COLAB_D,)

    necessidades_holerite = [n for n in resultado.necessidades if n.tipo_documental == TIPO_HOLERITE]
    assert len(necessidades_holerite) == 1
    assert necessidades_holerite[0].colaborador == _COLAB_D
    # sanitizado -- nunca CPF (pontuação) nem nome (espaço).
    assert '.' not in necessidades_holerite[0].colaborador.entidade_id
    assert ' ' not in necessidades_holerite[0].colaborador.entidade_id
