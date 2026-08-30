"""Testes do compositor geral de resolução semântica
(magnata_os/classificacao/resolucao_semantica.py) e dos tradutores para
o vocabulário canônico (`ResolucaoDimensao`/`EstadoResolucaoDimensao`)
adicionados aos especialistas já existentes.

Nenhum destes testes usa PDF real, Airtable, Gmail ou Postgres -- só
funções puras.
"""
import ast
import inspect

import pytest

from magnata_os.classificacao.classificador_documental import (
    EstadoClassificacao,
    ResultadoClassificacaoDocumental,
    classificar_documento,
    resultado_classificacao_para_resolucao_dimensao,
)
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.resolucao_semantica import (
    compor_resolucao_semantica,
    resolucao_competencia_de_validacao,
)
from magnata_os.documental.importacao_lote.contratos import ResultadoCompetencia


def _entrada(documento_id='doc-1', hash_sha256='a' * 64):
    return EntradaResolucaoDocumento(
        documento_id=documento_id,
        hash_sha256=hash_sha256,
        resolver_id='resolucao-semantica-v1',
        resolver_version='1',
        politica_id='perfil-teste',
        politica_version='1',
        contexto_fontes_fingerprint='fingerprint-teste',
    )


def _perfil(dimensoes_obrigatorias, dimensoes_nao_aplicaveis=()):
    regras = tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao,
            aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )
        for dimensao in dimensoes_obrigatorias
    ) + tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao,
            aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL,
            cardinalidade=Cardinalidade(0, 0),
        )
        for dimensao in dimensoes_nao_aplicaveis
    )
    return PerfilAplicabilidadeResolucao(
        perfil_id='perfil-teste', version='1', escopo_documental='teste', regras=regras,
    )


# ============================================================================
# CASO 1-4 -- tradução TIPO_DOCUMENTAL (classificador_documental.py)
# ============================================================================

def test_caso1_tipo_resolvido_traduz_para_resolucao_dimensao_resolvida():
    resultado = classificar_documento('Recibo de Pagamento\nTotal de Vencimentos')
    assert resultado.estado == EstadoClassificacao.RESOLVIDA

    resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)

    assert resolucao.dimensao == DimensaoResolucao.TIPO_DOCUMENTAL
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)
    assert resolucao.confianca.nivel == NivelConfianca.FORTE
    assert len(resolucao.evidencias) == len(resultado.regras_matching)


def test_tipo_resolvido_por_precedencia_historica_tem_confianca_moderada():
    # "FGTS Digital" bate FGTS; "Contrato de Trabalho" tambem bate no
    # mesmo texto -- FGTS vence por precedencia historica comprovada.
    resultado = classificar_documento('FGTS Digital\nContrato de Trabalho Verde e Amarelo')
    assert resultado.estado == EstadoClassificacao.RESOLVIDA
    assert resultado.tipos_concorrentes  # colisao real, arbitrada

    resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)

    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.confianca.nivel == NivelConfianca.MODERADA
    assert resolucao.candidatos == (ReferenciaCanonica('TIPO_DOCUMENTAL', 'Contrato de Trabalho'),)


def test_caso2_tipo_ambiguo_traduz_para_ambigua():
    # Duas regras de tipos SEM precedencia historica conhecida entre si.
    resultado = classificar_documento('Boleto\nLinha Digitável\nNota Fiscal de Serviço')
    assert resultado.estado == EstadoClassificacao.AMBIGUA

    resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)

    assert resolucao.estado == EstadoResolucaoDimensao.AMBIGUA
    assert resolucao.valores_confirmados == ()
    assert set(resolucao.candidatos) == {
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Boleto'),
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Nota Fiscal'),
    }
    assert resolucao.motivos == ('classificacao_ambigua',)


def test_caso3_tipo_nao_reconhecido_traduz_para_nao_encontrada():
    resultado = classificar_documento('texto sem nenhum padrao conhecido')
    assert resultado.estado == EstadoClassificacao.NAO_RECONHECIDA

    resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)

    assert resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resolucao.valores_confirmados == ()


def test_caso4_tipo_invalido_traduz_para_invalida():
    resultado = classificar_documento(123)  # não é string
    assert resultado.estado == EstadoClassificacao.INVALIDA

    resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)

    assert resolucao.estado == EstadoResolucaoDimensao.INVALIDA


def test_traducao_tipo_documental_fail_safe_para_estado_desconhecido():
    resultado_fake = ResultadoClassificacaoDocumental.__new__(ResultadoClassificacaoDocumental)
    object.__setattr__(resultado_fake, 'tipo_documental', 'Outro')
    object.__setattr__(resultado_fake, 'estado', 'ESTADO_INVENTADO')
    object.__setattr__(resultado_fake, 'quantidade_hits', 0)
    object.__setattr__(resultado_fake, 'regras_matching', ())
    object.__setattr__(resultado_fake, 'tipos_concorrentes', ())
    object.__setattr__(resultado_fake, 'necessita_revisao_humana', False)
    object.__setattr__(resultado_fake, 'prioridade_revisao', None)
    with pytest.raises(ValueError):
        resultado_classificacao_para_resolucao_dimensao(resultado_fake)


# ============================================================================
# CASO 5/6 -- evidência de competência (resolucao_competencia_de_validacao)
# ============================================================================

def test_competencia_confirmada_traduz_para_resolvida():
    resolucao = resolucao_competencia_de_validacao(ResultadoCompetencia.CONFIRMADA, (2026, 7))
    assert resolucao.dimensao == DimensaoResolucao.COMPETENCIA
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados == (ReferenciaCanonica('COMPETENCIA', '2026-07'),)


def test_competencia_confirmada_exige_ano_mes():
    with pytest.raises(ValueError):
        resolucao_competencia_de_validacao(ResultadoCompetencia.CONFIRMADA, None)


@pytest.mark.parametrize('resultado_esperado,estado_esperado', [
    (ResultadoCompetencia.DIVERGENTE, EstadoResolucaoDimensao.CONFLITO),
    (ResultadoCompetencia.AMBIGUA, EstadoResolucaoDimensao.AMBIGUA),
    (ResultadoCompetencia.NAO_EXTRAIVEL, EstadoResolucaoDimensao.NAO_ENCONTRADA),
])
def test_competencia_nao_confirmada_traduz_estado_correto(resultado_esperado, estado_esperado):
    resolucao = resolucao_competencia_de_validacao(resultado_esperado, None)
    assert resolucao.estado == estado_esperado
    assert resolucao.valores_confirmados == ()


# ============================================================================
# Compositor -- casos obrigatorios 8, 9, 10, 11, 12
# ============================================================================

def test_todas_dimensoes_resolvidas_produz_resultado_resolvido_e_pronto():
    from magnata_os.classificacao.contratos import ConfiancaResolucao
    entrada = _entrada()
    perfil = _perfil(
        [DimensaoResolucao.TIPO_DOCUMENTAL, DimensaoResolucao.COLABORADOR],
        [DimensaoResolucao.UNIDADE_POSTO],
    )
    resolucoes = (
        ResolucaoDimensao(
            dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        ),
        ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('COLABORADOR', 'func-1'),),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        ),
        ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    assert resultado.necessita_revisao_humana is False
    assert resultado.pronto_para_routing_logico is True


def test_caso8_dimensao_obrigatoria_nao_encontrada_nunca_fica_pronto():
    entrada = _entrada()
    perfil = _perfil([DimensaoResolucao.TIPO_DOCUMENTAL, DimensaoResolucao.COLABORADOR])
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                           valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
        ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
                           motivos=('colaborador_nao_encontrado',)),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.PARCIAL
    assert resultado.necessita_revisao_humana is True
    assert resultado.pronto_para_routing_logico is False
    assert 'colaborador_nao_encontrado' in resultado.motivos_consolidados


def test_caso9_dimensao_nao_aplicavel_nao_bloqueia_quando_perfil_permite():
    entrada = _entrada()
    perfil = _perfil(
        [DimensaoResolucao.TIPO_DOCUMENTAL],
        [DimensaoResolucao.UNIDADE_POSTO, DimensaoResolucao.VINCULO],
    )
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                           valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Extrato'),)),
        ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    assert resultado.pronto_para_routing_logico is True


def test_caso10_conflito_em_dimensao_forca_revisao():
    entrada = _entrada()
    perfil = _perfil([DimensaoResolucao.TIPO_DOCUMENTAL, DimensaoResolucao.COMPETENCIA])
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                           valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
        ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.CONFLITO,
                           motivos=('competencia_divergente',)),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.PARCIAL
    assert resultado.necessita_revisao_humana is True
    assert resultado.pronto_para_routing_logico is False


def test_caso11_erro_tecnico_nunca_vira_ausencia():
    entrada = _entrada()
    perfil = _perfil([DimensaoResolucao.TIPO_DOCUMENTAL, DimensaoResolucao.COLABORADOR])
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                           valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
        ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.ERRO_TECNICO,
                           motivos=('erro_tecnico_gate',)),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.ERRO_TECNICO
    assert resultado.estado_consolidado != EstadoResultadoSemantico.INCONCLUSIVA
    assert resultado.necessita_revisao_humana is True
    assert resultado.pronto_para_routing_logico is False


def test_nenhuma_dimensao_resolvida_e_inconclusiva():
    entrada = _entrada()
    perfil = _perfil([DimensaoResolucao.TIPO_DOCUMENTAL])
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.AMBIGUA,
                           motivos=('classificacao_ambigua',)),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.INCONCLUSIVA
    assert resultado.necessita_revisao_humana is True


def test_caso12_determinismo_mesmo_semantic_result_id():
    entrada_a = _entrada()
    entrada_b = _entrada()  # logicamente igual, instância diferente
    perfil = _perfil([DimensaoResolucao.TIPO_DOCUMENTAL])
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                           valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
    )

    resultado_a = compor_resolucao_semantica(entrada_a, perfil, resolucoes)
    resultado_b = compor_resolucao_semantica(entrada_b, perfil, resolucoes)

    assert resultado_a.semantic_result_id == resultado_b.semantic_result_id


def test_dimensao_faltante_no_perfil_e_fail_loud_herdado_do_contrato():
    """Compor com resolucoes que nao cobrem exatamente o perfil precisa
    continuar levantando ValueError -- o compositor NUNCA amortece essa
    checagem, ela ja pertence ao proprio contrato."""
    entrada = _entrada()
    perfil = _perfil([DimensaoResolucao.TIPO_DOCUMENTAL, DimensaoResolucao.COLABORADOR])
    resolucoes = (
        ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
                           valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)),
    )  # falta COLABORADOR
    with pytest.raises(ValueError):
        compor_resolucao_semantica(entrada, perfil, resolucoes)


# ============================================================================
# CASO 13 -- nenhum texto bruto/PII em evidencia
# ============================================================================

def test_evidencia_nunca_carrega_texto_bruto():
    resultado = classificar_documento('Recibo de Pagamento\nCPF: 123.456.789-01\nJOAO DA SILVA')
    resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)
    bruto = str(resolucao)
    assert '123.456.789-01' not in bruto
    assert 'JOAO DA SILVA' not in bruto
    # evidencia so carrega o identificador de regra sanitizado
    for evidencia in resolucao.evidencias:
        assert evidencia.referencia_fonte in resultado.regras_matching


# ============================================================================
# Auditoria de generalidade (macro-objetivo 5) -- o compositor nunca
# conhece nenhum tipo documental especifico nem qualquer sinal solto
# (filename/subject/sender/CPF/CNPJ brutos).
# ============================================================================

def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def test_compositor_e_estruturalmente_generico():
    """Prova estrutural (AST, não busca textual em comentário/docstring
    -- o próprio docstring do módulo PRECISA citar "Holerite" para
    explicar o que o compositor nunca faz; a auditoria de generalidade
    da missão pede para revisar cada ocorrência, não para proibir a
    palavra em prosa). O que nunca pode existir é a palavra em CÓDIGO
    executável: nome de identificador, literal de string usado como
    valor/chave, ou nome de módulo importado."""
    import magnata_os.classificacao.resolucao_semantica as modulo

    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)

    # Todo Expr que é uma string solta (docstring de módulo/função) é
    # ignorado -- coletamos os nós dessas strings para excluí-los abaixo.
    nos_de_docstring = {
        id(no.value)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and _e_docstring(no)
    }

    identificadores = set()
    literais_string = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Name, ast.arg)):
            identificadores.add(no.id if isinstance(no, ast.Name) else no.arg)
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identificadores.add(no.name)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            if id(no) not in nos_de_docstring:
                literais_string.add(no.value)

    codigo_executavel_lower = {s.lower() for s in identificadores | literais_string}

    proibidos = [
        'holerite', 'filename', 'nome_original', 'subject', 'assunto',
        'sender', 'remetente', 'cpf', 'cnpj',
    ]
    for termo in proibidos:
        achados = {s for s in codigo_executavel_lower if termo in s}
        assert not achados, f'termo proibido em código executável: {termo!r} em {achados!r}'

    modulos_importados = {
        no.module.split('.')[-1]
        for no in ast.walk(arvore)
        if isinstance(no, ast.ImportFrom) and no.module
    }
    # nunca importa modulo especifico de Holerite nem da esteira/servicos
    proibidos_modulos = {
        'politica_identificacao_holerite', 'servico_lote',
        'ponte_prestacao_holerite', 'servico_avanco_esteira',
    }
    assert not (modulos_importados & proibidos_modulos)
