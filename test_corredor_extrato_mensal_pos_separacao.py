"""Corredor da Prestação para uma SEGUNDA família (Extrato Mensal, pós-
separação) -- missão "FECHAMENTO AMPLO DA COBERTURA DOCUMENTAL",
Fase 2E.3, Fase M.

Prova, sem criar nenhum corredor especial: documento master → separação
→ reconhecimento (mesmo motor) → `ResultadoResolucaoSemantico` (mesmo
compositor, PR #93) → `ItemInventarioPrestacao`/`avaliar_prestacao_
readiness` (mesmo módulo genérico já usado pelo corredor de Holerite,
`ponte_prestacao_holerite.py`) -- nenhuma peça nova de infraestrutura,
só reaproveitamento."""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.prestacao_readiness import (
    EntradaPrestacaoReadiness,
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
    avaliar_prestacao_readiness,
)
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.separacao_documental import (
    estrategia_por_cnpj_cliente,
    separar_por_carry_forward,
    texto_do_grupo,
)

_CNPJ_MAGNATA = '00111222000133'
_CNPJ_CLIENTE_A = '11222333000181'
_INDICE_CLIENTES = {_CNPJ_CLIENTE_A: ('rec_cliente_a', 'Cliente A')}


def _fmt(cnpj: str) -> str:
    return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}'


def _regra(dimensao, aplicabilidade):
    cardinalidade = Cardinalidade(1, 1) if aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA else Cardinalidade(0, 0)
    return RegraAplicabilidadeDimensao(dimensao=dimensao, aplicabilidade=aplicabilidade, cardinalidade=cardinalidade)


def test_extrato_mensal_pos_separacao_chega_a_readiness_pelo_mesmo_caminho_generico():
    # 1) Master de 1 cliente (o suficiente para provar o corredor; a
    # separação multi-cliente já está provada em
    # test_magnata_os_classificacao_separacao_documental.py).
    paginas = (
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_A)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
        'detalhe do cliente A',
    )
    estrategia = estrategia_por_cnpj_cliente(_INDICE_CLIENTES, cnpj_excluido=_CNPJ_MAGNATA)
    resultado_separacao = separar_por_carry_forward(paginas, estrategia)
    assert len(resultado_separacao.grupos) == 1
    grupo = resultado_separacao.grupos[0]

    # 2) Reentrada no MESMO motor (Fase F, já provada -- repetida aqui
    # só como base do corredor completo).
    texto_filho = texto_do_grupo(paginas, grupo)
    resolucao_tipo = resolver_tipo_documental(
        hipoteses_textuais_de_classificacao(classificar_documento(texto_filho)),
        quantidade_entidades_distintas=1,
    )
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
    tipo_documental = resolucao_tipo.valores_confirmados[0].entidade_id

    # 3) Composição -- MESMO compor_resolucao_semantica do PR #93,
    # perfil "cliente sem colaborador" (Extrato é do cliente, não do
    # colaborador -- mesma lógica de perfil já provada na Fase I).
    referencia_cliente = ReferenciaCanonica('CLIENTE', grupo.entidade_id)
    referencia_competencia = ReferenciaCanonica('COMPETENCIA', '2026-07')
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='extrato-mensal-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            _regra(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA),
            _regra(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA),
            _regra(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA),
            _regra(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL),
            _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL),
            _regra(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL),
        ),
    )
    resultado_semantico = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='extrato-cliente-a-1', hash_sha256='c' * 64, resolver_id='r',
            resolver_version='1', politica_id='extrato-mensal-v1', politica_version='1',
            contexto_fontes_fingerprint='classificacao+separacao',
        ),
        perfil=perfil,
        resolucoes=(
            resolucao_tipo,
            ResolucaoDimensao(
                dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(referencia_cliente,),
            ),
            ResolucaoDimensao(
                dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(referencia_competencia,),
            ),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )
    assert resultado_semantico.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA

    # 4) MESMO módulo de readiness já usado pelo corredor de Holerite --
    # nenhum corredor especial para Extrato.
    item = ItemInventarioPrestacao(
        documento_id='extrato-cliente-a-1', tipo_documental=tipo_documental,
        cliente=referencia_cliente, competencia=referencia_competencia,
    )
    resultado_readiness = avaliar_prestacao_readiness(EntradaPrestacaoReadiness(
        cliente=referencia_cliente, competencia=referencia_competencia,
        requisitos=(RequisitoDocumentalPrestacao(tipo_documental=tipo_documental, quantidade_minima=1),),
        inventario=(item,), resolucao=resultado_semantico,
    ))
    assert resultado_readiness.estado == EstadoPrestacaoReadiness.PRONTO
