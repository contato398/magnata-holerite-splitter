"""Testes dos produtores FISCAL, PONTO e TEMPORAL/CERTIDÃO (missão
"FECHAMENTO AMPLO DA COBERTURA DOCUMENTAL", Fase 2E.3, Fase C). Todos
os textos são SINTÉTICOS."""
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.produtores_evidencia_fiscal import (
    TIPO_GUIA_GENERICA,
    hipoteses_fiscais_de_texto,
)
from magnata_os.classificacao.produtores_evidencia_ponto import (
    TIPO_FOLHA_DE_PONTO,
    contar_linhas_de_marcacao_ponto,
    hipoteses_estruturais_de_ponto,
)
from magnata_os.classificacao.produtores_evidencia_temporal import (
    TIPO_CERTIDAO,
    hipoteses_temporais_de_certidao,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental


# ============================================================================
# Produtor FISCAL
# ============================================================================

def test_codigo_de_receita_isolado_ja_resolve_para_guia():
    resultado = resolver_tipo_documental(hipoteses_fiscais_de_texto('Código de Receita: 0561'))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', TIPO_GUIA_GENERICA),)


def test_linha_digitavel_de_guia_isolada_e_inconclusiva():
    resultado = resolver_tipo_documental(hipoteses_fiscais_de_texto('Autenticação Bancária pendente'))
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_dois_sinais_fracos_fiscais_se_reforcam():
    texto = 'Autenticação Bancária\nNúmero de Referência: 12345'
    resultado = resolver_tipo_documental(hipoteses_fiscais_de_texto(texto))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_texto_sem_nenhum_sinal_fiscal_nao_produz_hipotese():
    assert hipoteses_fiscais_de_texto('texto qualquer sem nenhum sinal fiscal') == ()
    assert hipoteses_fiscais_de_texto('') == ()


# ============================================================================
# Produtor de PONTO
# ============================================================================

_LINHAS_MARCACAO = (
    '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
    '28/04/26 - Ter - C1 08:00 12:00 13:00 17:00\n'
    '27/04/26 - Seg - C1 08:05 12:10 13:05 17:15'
)


def test_estrutura_de_marcacao_reconhece_ponto_sem_a_frase_literal():
    """Nenhuma menção a "Folha de Ponto"/"Secullum"/"Ponto Web" no
    texto -- só a estrutura repetida de linhas de marcação já basta."""
    resultado = resolver_tipo_documental(hipoteses_estruturais_de_ponto(_LINHAS_MARCACAO))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', TIPO_FOLHA_DE_PONTO),)


def test_uma_unica_linha_de_marcacao_isolada_nunca_basta():
    texto = '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05'
    assert contar_linhas_de_marcacao_ponto(texto) == 1
    assert hipoteses_estruturais_de_ponto(texto) == ()


def test_periodo_reforca_estrutura_de_marcacao():
    """Estrutura (MODERADA) + período (FRACA) -- continua RESOLVIDA,
    nunca derrubado por um sinal fraco adicional (regra já existente:
    1 MODERADA já é suficiente para vencer)."""
    texto = _LINHAS_MARCACAO + '\nPeríodo: 01/04/2026 até 30/04/2026'
    resultado = resolver_tipo_documental(hipoteses_estruturais_de_ponto(texto))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.confianca.nivel.value == 'MODERADA'


# ============================================================================
# Produtor TEMPORAL/CERTIDÃO
# ============================================================================

def test_palavra_certidao_isolada_nunca_resolve_sozinha():
    """Cláusula pétrea #6: palavra isolada nunca é identidade
    suficiente -- mesmo sendo exatamente a palavra do tipo."""
    resultado = resolver_tipo_documental(hipoteses_temporais_de_certidao('Este documento é uma Certidão simples'))
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_certidao_mais_validade_resolve():
    texto = 'Certidão Negativa de Débitos\nVálida até 31/12/2026'
    resultado = resolver_tipo_documental(hipoteses_temporais_de_certidao(texto))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', TIPO_CERTIDAO),)


def test_documento_sem_a_palavra_certidao_nunca_produz_hipotese():
    """Nunca infere Certidão só por ter data de validade -- isso
    colidiria com qualquer outro documento com prazo (nunca inventar
    identidade, cláusula pétrea #10)."""
    assert hipoteses_temporais_de_certidao('Válido até 31/12/2026, sem mais informações') == ()
