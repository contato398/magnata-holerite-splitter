"""Testes de `produtores_evidencia_extrato.py` (missão "AUTOMAÇÃO
DOCUMENTAL REAL V1", §9 + ADENDO OBRIGATÓRIO item 3/5.E: rótulo
alternativo é só um SINAL a mais, nunca identidade -- não pode vencer
sozinho uma evidência estrutural/fiscal forte conflitante)."""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.produtores_evidencia_documental import hipoteses_textuais_de_classificacao
from magnata_os.classificacao.produtores_evidencia_extrato import (
    TIPO_EXTRATO,
    hipoteses_de_rotulo_alternativo_de_extrato,
)
from magnata_os.classificacao.produtores_evidencia_fiscal import hipoteses_fiscais_de_texto
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao


def test_resumo_da_folha_gera_hipotese_de_extrato():
    hipoteses = hipoteses_de_rotulo_alternativo_de_extrato('Resumo da Folha de Pagamento -- Julho/2026')
    assert len(hipoteses) == 1
    assert hipoteses[0].tipo_documental == TIPO_EXTRATO


def test_resumo_da_folha_sem_sufixo_tambem_reconhecido():
    hipoteses = hipoteses_de_rotulo_alternativo_de_extrato('Resumo da Folha -- competência 07/2026')
    assert len(hipoteses) == 1


def test_texto_sem_rotulo_alternativo_nao_gera_hipotese():
    assert hipoteses_de_rotulo_alternativo_de_extrato('documento qualquer sem rotulo') == ()


def test_texto_vazio_nunca_gera_hipotese():
    assert hipoteses_de_rotulo_alternativo_de_extrato('') == ()


def test_nunca_altera_classificador_documental_legado():
    """As 17 regras legadas nunca reconhecem 'Resumo da Folha' sozinhas
    -- a hipótese vem SÓ do produtor novo, nunca de uma mudança no
    classificador espelho do legado."""
    resultado_legado = classificar_documento('Resumo da Folha de Pagamento -- Julho/2026')
    assert hipoteses_textuais_de_classificacao(resultado_legado) == ()


def test_combinado_com_hipotese_textual_resolve_extrato():
    """A hipótese nova, somada ao resolvedor já existente (mesmo motor,
    nunca um paralelo), já basta para RESOLVER -- prova que o produtor
    realmente alimenta `resolver_tipo_documental`, não é decorativo."""
    hipoteses = hipoteses_de_rotulo_alternativo_de_extrato('Resumo da Folha de Pagamento -- Julho/2026')
    resolucao = resolver_tipo_documental(hipoteses)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_EXTRATO


def test_e_rotulo_moderado_nunca_vence_evidencia_fiscal_forte_incompatível():
    """ADENDO OBRIGATÓRIO item 3/5.E: "Resumo da Folha" continua
    MODERADA -- nunca identidade. Quando o MESMO texto também carrega
    evidência fiscal (Código de Receita, já MODERADA/estrutural para
    FGTS), o resolvedor já existente decide pela evidência mais forte
    -- este produtor nunca "supera" isso silenciosamente."""
    texto = 'Resumo da Folha de Pagamento -- mas na verdade Guia do FGTS -- Código de Receita: 0561'
    hipoteses = (
        hipoteses_textuais_de_classificacao(classificar_documento(texto))
        + hipoteses_de_rotulo_alternativo_de_extrato(texto)
        + hipoteses_fiscais_de_texto(texto)
    )
    resolucao = resolver_tipo_documental(hipoteses)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    # FGTS vence -- o rótulo alternativo de Extrato NUNCA decide sozinho
    # contra uma evidência fiscal concorrente já comprovada mais forte.
    assert resolucao.valores_confirmados[0].entidade_id == 'FGTS'
