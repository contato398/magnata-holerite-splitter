"""Integração das dimensões por família (missão "FECHAMENTO AMPLO DA
COBERTURA DOCUMENTAL", Fase 2E.3, Fase I).

Prova que `ResultadoResolucaoSemantico` acomoda perfis DIFERENTES por
família de documento -- nunca exige todas as 6 dimensões para todo
documento (`PerfilAplicabilidadeResolucao` já suporta isso desde o
compositor do PR #93; esta missão só PROVA a diversidade real):

  - Holerite: COLABORADOR obrigatória (documento é do colaborador).
  - Guia fiscal (DCTF/DARF/FGTS): COLABORADOR e CLIENTE NAO_APLICAVEL
    (obrigação da própria Magnata perante o fisco, não de um cliente
    nem de um colaborador específico) -- "DCTF: sem colaborador",
    exatamente como a missão pede.

Nenhuma peça nova de produção -- reaproveita compor_resolucao_semantica
(PR #93) e os produtores já existentes, só demonstra a composição."""
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
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.produtores_evidencia_fiscal import hipoteses_fiscais_de_texto
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental

_NAO_APLICAVEL = lambda dimensao: ResolucaoDimensao(  # noqa: E731
    dimensao=dimensao, estado=EstadoResolucaoDimensao.NAO_APLICAVEL,
)
_REGRA_OBRIGATORIA = lambda dimensao: RegraAplicabilidadeDimensao(  # noqa: E731
    dimensao=dimensao, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA, cardinalidade=Cardinalidade(1, 1),
)
_REGRA_NAO_APLICAVEL = lambda dimensao: RegraAplicabilidadeDimensao(  # noqa: E731
    dimensao=dimensao, aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL, cardinalidade=Cardinalidade(0, 0),
)


def test_holerite_exige_colaborador_guia_fiscal_nao_exige():
    """MESMO compositor, perfis DIFERENTES por família -- nunca uma
    dimensão obrigatória universal."""
    perfil_holerite = PerfilAplicabilidadeResolucao(
        perfil_id='holerite-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            _REGRA_OBRIGATORIA(DimensaoResolucao.TIPO_DOCUMENTAL),
            _REGRA_OBRIGATORIA(DimensaoResolucao.COLABORADOR),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.CLIENTE),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.COMPETENCIA),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.UNIDADE_POSTO),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.VINCULO),
        ),
    )
    perfil_guia_fiscal = PerfilAplicabilidadeResolucao(
        perfil_id='guia-fiscal-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            _REGRA_OBRIGATORIA(DimensaoResolucao.TIPO_DOCUMENTAL),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.COLABORADOR),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.CLIENTE),
            _REGRA_OBRIGATORIA(DimensaoResolucao.COMPETENCIA),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.UNIDADE_POSTO),
            _REGRA_NAO_APLICAVEL(DimensaoResolucao.VINCULO),
        ),
    )

    # -- Holerite: TIPO_DOCUMENTAL real, COLABORADOR obrigatória (aqui
    # simplificado como NAO_APLICAVEL nas demais para isolar o ponto).
    resolucao_tipo_holerite = resolver_tipo_documental(
        hipoteses_textuais_de_classificacao(classificar_documento(
            'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido')))
    assert resolucao_tipo_holerite.estado == EstadoResolucaoDimensao.RESOLVIDA

    resolucao_colaborador = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('COLABORADOR', 'func-1'),),
    )
    resultado_holerite = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='holerite-1', hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='holerite-v1', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil_holerite,
        resolucoes=(
            resolucao_tipo_holerite, resolucao_colaborador,
            _NAO_APLICAVEL(DimensaoResolucao.CLIENTE), _NAO_APLICAVEL(DimensaoResolucao.COMPETENCIA),
            _NAO_APLICAVEL(DimensaoResolucao.UNIDADE_POSTO), _NAO_APLICAVEL(DimensaoResolucao.VINCULO),
        ),
    )
    assert resultado_holerite.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA

    # -- Guia fiscal (DCTF/DARF/FGTS): "sem colaborador" -- prova
    # literal do exemplo da missão.
    resolucao_tipo_guia = resolver_tipo_documental(
        hipoteses_fiscais_de_texto('Código de Receita: 0561\nNúmero de Referência: 998877'))
    assert resolucao_tipo_guia.estado == EstadoResolucaoDimensao.RESOLVIDA

    resolucao_competencia = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(_referencia_competencia(),),
    )
    resultado_guia = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='guia-1', hash_sha256='b' * 64, resolver_id='r', resolver_version='1',
            politica_id='guia-fiscal-v1', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil_guia_fiscal,
        resolucoes=(
            resolucao_tipo_guia, _NAO_APLICAVEL(DimensaoResolucao.COLABORADOR),
            _NAO_APLICAVEL(DimensaoResolucao.CLIENTE), resolucao_competencia,
            _NAO_APLICAVEL(DimensaoResolucao.UNIDADE_POSTO), _NAO_APLICAVEL(DimensaoResolucao.VINCULO),
        ),
    )
    assert resultado_guia.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    # Prova central da Fase I: nenhuma resolução de COLABORADOR foi
    # sequer tentada para a guia fiscal -- perfil diferente, nunca a
    # mesma exigência universal.
    colaborador_na_guia = next(
        r for r in resultado_guia.resolucoes if r.dimensao == DimensaoResolucao.COLABORADOR)
    assert colaborador_na_guia.estado == EstadoResolucaoDimensao.NAO_APLICAVEL


def _referencia_competencia():
    return ReferenciaCanonica('COMPETENCIA', '2026-07')
