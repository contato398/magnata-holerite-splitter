"""Testes do motor GERAL de compreensão documental multi-evidência
(magnata_os/classificacao/resolucao_tipo_documental.py +
produtores_evidencia_documental.py) — missão "MOTOR GERAL DE
COMPREENSÃO DOCUMENTAL".

Nenhum teste aqui usa PDF real, Airtable, Gmail ou Postgres -- só
funções puras, com textos SINTÉTICOS (frases institucionais genéricas
já usadas pelos próprios regex do classificador -- nunca dado pessoal
real).
"""
import ast
import inspect

import pytest

from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    NivelConfianca,
    ReferenciaCanonica,
)
from magnata_os.classificacao.produtores_evidencia_documental import (
    SinalContextual,
    contar_entidades_distintas_no_texto,
    hipoteses_contextuais,
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.resolucao_tipo_documental import (
    HipoteseTipoDocumental,
    resolver_tipo_documental,
)


def _hipoteses_de(texto):
    return hipoteses_textuais_de_classificacao(classificar_documento(texto))


# ============================================================================
# Fase D -- resolvedor geral, casos básicos
# ============================================================================

def test_uma_hipotese_forte_resolve():
    hipoteses = _hipoteses_de('Recibo de Pagamento\nTotal de Vencimentos')
    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)


def test_nenhuma_hipotese_e_nao_encontrada():
    resultado = resolver_tipo_documental(())
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_hipotese_unica_fraca_e_insuficiente_nunca_resolve():
    hipoteses = (
        HipoteseTipoDocumental(
            tipo_documental='Guia',
            evidencias=(
                _evidencia_fraca(),
            ),
        ),
    )
    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.motivos == ('evidencia_insuficiente',)


def _evidencia_fraca():
    from magnata_os.classificacao.contratos import EvidenciaSanitizada
    return EvidenciaSanitizada(
        tipo_evidencia='TESTE', fonte='teste', referencia_fonte='x', metodo='teste',
        forca=NivelConfianca.FRACA,
    )


def _evidencia(forca, tipo_evidencia='TESTE', referencia='x'):
    from magnata_os.classificacao.contratos import EvidenciaSanitizada
    return EvidenciaSanitizada(
        tipo_evidencia=tipo_evidencia, fonte='teste', referencia_fonte=referencia,
        metodo='teste', forca=forca,
    )


# ============================================================================
# Combinação de força (política documentada no módulo)
# ============================================================================

def test_duas_evidencias_moderadas_combinam_para_forte():
    hipoteses = (
        HipoteseTipoDocumental('TipoX', (
            _evidencia(NivelConfianca.MODERADA, referencia='a'),
            _evidencia(NivelConfianca.MODERADA, referencia='b'),
        )),
    )
    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.confianca.nivel == NivelConfianca.FORTE


def test_duas_evidencias_fracas_combinam_para_moderada_e_resolve():
    hipoteses = (
        HipoteseTipoDocumental('TipoX', (
            _evidencia(NivelConfianca.FRACA, referencia='a'),
            _evidencia(NivelConfianca.FRACA, referencia='b'),
        )),
    )
    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.confianca.nivel == NivelConfianca.MODERADA


def test_evidencias_de_produtores_diferentes_para_o_mesmo_tipo_se_combinam():
    """Fase H -- se a frase mais característica foi removida, mas outra
    evidência real (aqui, um sinal contextual) sustenta o MESMO
    candidato, o documento ainda deve ser reconhecido."""
    texto_fraco = 'documento do funcionario com valores diversos'  # nao bate regex forte nenhuma
    hipoteses_textuais = _hipoteses_de(texto_fraco)
    assert hipoteses_textuais == ()  # nenhuma evidencia textual disponivel

    sinais = (SinalContextual('ASSUNTO_PALAVRA_CHAVE', 'email_metadata', 'assunto:holerite', 'Holerite'),)
    hipoteses_contexto = hipoteses_contextuais(sinais)

    resultado_sozinho = resolver_tipo_documental(hipoteses_contexto)
    assert resultado_sozinho.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA  # 1 fraca sozinha nao basta

    # Agora com DUAS evidencias fracas independentes para o mesmo tipo
    # (contextual + uma segunda, simulando um segundo produtor real).
    hipoteses_reforcadas = hipoteses_contexto + (
        HipoteseTipoDocumental('Holerite', (_evidencia(NivelConfianca.FRACA, referencia='reforco'),)),
    )
    resultado_reforcado = resolver_tipo_documental(hipoteses_reforcadas)
    assert resultado_reforcado.estado == EstadoResolucaoDimensao.RESOLVIDA


# ============================================================================
# Fase I -- conflito e ambiguidade
# ============================================================================

def test_dois_sinais_fortes_incompativeis_gera_conflito():
    hipoteses = (
        HipoteseTipoDocumental('TipoA', (_evidencia(NivelConfianca.FORTE, referencia='a'),)),
        HipoteseTipoDocumental('TipoB', (_evidencia(NivelConfianca.FORTE, referencia='b'),)),
    )
    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.CONFLITO
    assert resultado.motivos == ('sinais_fortes_incompativeis',)
    assert set(resultado.candidatos) == {
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'TipoA'), ReferenciaCanonica('TIPO_DOCUMENTAL', 'TipoB'),
    }


def test_dois_sinais_fracos_empatados_gera_ambigua_nunca_conflito():
    hipoteses = (
        HipoteseTipoDocumental('TipoA', (_evidencia(NivelConfianca.FRACA, referencia='a'),)),
        HipoteseTipoDocumental('TipoB', (_evidencia(NivelConfianca.FRACA, referencia='b'),)),
    )
    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA


def test_sinal_fraco_nunca_derrota_sinal_forte():
    """'remetente sugere fiscal; conteudo forte sugere DP' -- sinal
    fraco nunca vence forte."""
    hipoteses_textuais = _hipoteses_de('Recibo de Pagamento\nValor Líquido')
    sinais = (SinalContextual('REMETENTE_CATEGORIA_FISCAL', 'email_metadata', 'categoria:fiscal', 'Guia DCTFWeb/DARF'),)
    hipoteses_contexto = hipoteses_contextuais(sinais)

    resultado = resolver_tipo_documental(hipoteses_textuais + hipoteses_contexto)

    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)


def test_classificacao_ambigua_do_produtor_textual_vira_hipoteses_fracas():
    resultado_classificacao = classificar_documento('Boleto\nLinha Digitável\nNota Fiscal de Serviço')
    hipoteses = hipoteses_textuais_de_classificacao(resultado_classificacao)
    assert len(hipoteses) == 2
    assert all(h.evidencias[0].forca == NivelConfianca.FRACA for h in hipoteses)

    resultado = resolver_tipo_documental(hipoteses)
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA


# ============================================================================
# Multiplas entidades distintas -- fail-safe genérico (generaliza
# "PDF mestre suspeito", nunca especializado a Holerite)
# ============================================================================

def test_multiplas_entidades_distintas_bloqueia_resolucao_automatica():
    hipoteses = _hipoteses_de('Recibo de Pagamento\nTotal de Vencimentos')
    resultado_sem_bloqueio = resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=1)
    assert resultado_sem_bloqueio.estado == EstadoResolucaoDimensao.RESOLVIDA

    resultado_bloqueado = resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=2)
    assert resultado_bloqueado.estado == EstadoResolucaoDimensao.CONFLITO
    assert resultado_bloqueado.motivos == ('multiplas_entidades_distintas_no_documento',)


def test_contar_entidades_reaproveita_extracao_de_cpf_existente():
    texto = 'CPF: 111.222.333-44\nCPF: 555.666.777-88'
    assert contar_entidades_distintas_no_texto(texto) == 2
    assert contar_entidades_distintas_no_texto('CPF: 111.222.333-44') == 1
    assert contar_entidades_distintas_no_texto('sem cpf nenhum') == 0


# ============================================================================
# Fase G -- robustez contra nome de arquivo (filename NUNCA é parametro
# de nenhuma funcao deste motor -- prova estrutural por assinatura)
# ============================================================================

def test_nenhuma_funcao_do_motor_aceita_filename():
    import magnata_os.classificacao.resolucao_tipo_documental as resolvedor_mod
    import magnata_os.classificacao.produtores_evidencia_documental as produtores_mod

    nomes_proibidos = {'filename', 'nome_arquivo', 'nome_original'}
    for modulo in (resolvedor_mod, produtores_mod):
        for nome, obj in vars(modulo).items():
            if inspect.isfunction(obj) and obj.__module__ == modulo.__name__:
                parametros = set(inspect.signature(obj).parameters)
                assert not (parametros & nomes_proibidos), (
                    f'{modulo.__name__}.{nome} aceita parametro de filename: {parametros}')


def test_mesmo_conteudo_com_filenames_diferentes_produz_mesmo_resultado():
    """Fase G: 'a.pdf', '0001.pdf', 'scan.pdf', 'arquivo-final.pdf' --
    o motor nunca recebe o nome do arquivo, entao o resultado e sempre
    o mesmo, qualquer que seja o nome usado pelo chamador."""
    texto = 'FGTS Digital\nGuia do FGTS'
    resultados = [resolver_tipo_documental(_hipoteses_de(texto)) for _ in range(4)]
    tipos = {r.valores_confirmados for r in resultados}
    assert tipos == {(ReferenciaCanonica('TIPO_DOCUMENTAL', 'FGTS'),)}


def test_filename_enganoso_nunca_vence_conteudo_real():
    """Arquivo chamado 'holerite.pdf' com conteudo de FGTS -- como
    filename nunca e passado a nenhuma funcao do motor, o resultado
    reflete só o conteúdo real."""
    conteudo_real_de_fgts = 'FGTS Digital\nGuia do FGTS\nTotal FGTS'
    # nome_do_arquivo = 'holerite.pdf' -- deliberadamente nunca usado abaixo
    resultado = resolver_tipo_documental(_hipoteses_de(conteudo_real_de_fgts))
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', 'FGTS'),)


# ============================================================================
# Fase J -- generalidade estrutural (AST/grep)
# ============================================================================

def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def _termos_proibidos_em_codigo_executavel(modulo):
    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and _e_docstring(no)
    }
    identificadores, literais = set(), set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Name, ast.arg)):
            identificadores.add(no.id if isinstance(no, ast.Name) else no.arg)
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identificadores.add(no.name)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            if id(no) not in nos_de_docstring:
                literais.add(no.value)
    return {s.lower() for s in identificadores | literais}


def test_resolvedor_geral_e_estruturalmente_generico():
    import magnata_os.classificacao.resolucao_tipo_documental as modulo
    codigo_executavel = _termos_proibidos_em_codigo_executavel(modulo)
    proibidos = ['holerite', 'extrato', 'fgts', 'dctfweb', 'folha de ponto', 'if tipo ==']
    for termo in proibidos:
        achados = {s for s in codigo_executavel if termo in s}
        assert not achados, f'termo proibido em código executável: {termo!r} em {achados!r}'


def test_produtores_nao_hardcodeiam_tipo_especifico_fora_de_delegacao():
    """Os produtores DELEGAM a classificador_documental.py (que, esse
    sim, conhece os 17 tipos) -- mas o resolvedor geral (importado
    aqui) nunca deve ver esses nomes em seu próprio código."""
    import magnata_os.classificacao.resolucao_tipo_documental as resolvedor_mod
    codigo_fonte = inspect.getsource(resolvedor_mod)
    arvore = ast.parse(codigo_fonte)
    modulos_importados = {
        no.module.split('.')[-1] for no in ast.walk(arvore)
        if isinstance(no, ast.ImportFrom) and no.module
    }
    proibidos_modulos = {'classificador_documental', 'politica_identificacao_holerite'}
    assert not (modulos_importados & proibidos_modulos)


# ============================================================================
# Fase E -- integração direta com o compositor do PR #93
# ============================================================================

def test_resultado_alimenta_o_compositor_sem_nenhuma_adaptacao():
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao, Cardinalidade, EntradaResolucaoDocumento,
        EstadoResultadoSemantico, PerfilAplicabilidadeResolucao, RegraAplicabilidadeDimensao,
    )
    from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica

    resolucao_tipo = resolver_tipo_documental(_hipoteses_de('DCTFWeb Digital\nRecibo de Entrega da DCTFWeb'))
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA

    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='doc-broadcast', version='1', escopo_documental='teste',
        regras=(RegraAplicabilidadeDimensao(
            DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),),
    )
    entrada = EntradaResolucaoDocumento(
        documento_id='doc-1', hash_sha256='a' * 64, resolver_id='motor-geral-v1', resolver_version='1',
        politica_id='doc-broadcast', politica_version='1', contexto_fontes_fingerprint='textual',
    )
    resultado = compor_resolucao_semantica(entrada, perfil, (resolucao_tipo,))
    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    assert resultado.pronto_para_routing_logico is True
