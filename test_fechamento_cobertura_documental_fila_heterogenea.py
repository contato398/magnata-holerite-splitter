"""Fila heterogênea de regressão AMPLA (missão "FECHAMENTO AMPLO DA
COBERTURA DOCUMENTAL", Fase 2E.3, Fase J) -- maior que as fileiras
anteriores (PR #94, PR #95), cobrindo TODAS as famílias com evidência
suficiente após esta missão, pelo MESMO motor + MESMA engine de
separação + MESMO compositor. O objetivo não é 100% RESOLVIDA -- é
decisão correta (resolver quando há evidência, permanecer explícito
quando não há).

Todos os textos são SINTÉTICOS -- nunca dado real, nunca filename
influenciando resultado (inclusive um caso de filename DELIBERADAMENTE
enganoso, provando que o motor nunca olha para o nome do arquivo)."""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    FINALIDADE_SALARIO,
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.produtores_evidencia_fiscal import hipoteses_fiscais_de_texto
from magnata_os.classificacao.produtores_evidencia_ponto import hipoteses_estruturais_de_ponto
from magnata_os.classificacao.produtores_evidencia_temporal import hipoteses_temporais_de_certidao
from magnata_os.classificacao.resolucao_master_documental import (
    EstadoGranularidadeDocumento,
    detectar_granularidade_documento,
)
from magnata_os.classificacao.evidencia_estrutural_documental import analisar_estrutura_documento
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.separacao_documental import (
    estrategia_por_cpf_colaborador,
    separar_por_carry_forward,
    texto_do_grupo,
)

_CPF_A = '11144477735'
_CPF_B = '22255588806'
_INDICE_COLABORADORES = {_CPF_A: ('rec_colab_a', 'Colaborador A'), _CPF_B: ('rec_colab_b', 'Colaborador B')}


def _fmt_cpf(cpf: str) -> str:
    return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'


def _resolver_textual(texto: str, quantidade_entidades_distintas=None):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=quantidade_entidades_distintas)


def test_holerite_e_guia_unitarios_continuam_resolvendo():
    assert _resolver_textual('Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido').estado \
        == EstadoResolucaoDimensao.RESOLVIDA
    assert _resolver_textual('Guia de Recolhimento\nGPS').estado == EstadoResolucaoDimensao.RESOLVIDA


def test_master_multi_colaborador_agora_e_separado_de_verdade():
    """Diferente da fila da missão anterior (só detecção) -- agora a
    separação por CPF/colaborador existe e é usada de ponta a ponta."""
    paginas = (
        f'Colaborador CPF {_fmt_cpf(_CPF_A)}\nFolha de Ponto',
        f'Colaborador CPF {_fmt_cpf(_CPF_B)}\nFolha de Ponto',
    )
    evidencia = analisar_estrutura_documento(paginas)
    assert detectar_granularidade_documento(evidencia).estado == EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER

    estrategia = estrategia_por_cpf_colaborador(_INDICE_COLABORADORES)
    resultado_separacao = separar_por_carry_forward(paginas, estrategia)
    assert len(resultado_separacao.grupos) == 2
    for grupo in resultado_separacao.grupos:
        resolucao = _resolver_textual(texto_do_grupo(paginas, grupo), quantidade_entidades_distintas=1)
        assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_comprovante_de_pagamento_resolvivel_e_inconclusivo():
    ocorrencias_ok = sinais_textuais_de_finalidade_pagamento('Comprovante de pagamento de salário do mês')
    assert resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_ok)).estado \
        == EstadoResolucaoDimensao.RESOLVIDA

    ocorrencias_inconclusivas = sinais_textuais_de_finalidade_pagamento('Comprovante de transferência PIX')
    assert resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_inconclusivas)).estado \
        == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_folha_de_ponto_reconhecida_por_estrutura_sem_a_frase_literal():
    texto = (
        '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '28/04/26 - Ter - C1 08:00 12:00 13:00 17:00\n'
        'Período: 01/04/2026 até 30/04/2026'
    )
    resultado = resolver_tipo_documental(hipoteses_estruturais_de_ponto(texto))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_certidao_reconhecida_por_conteudo_e_estrutura():
    resultado = resolver_tipo_documental(
        hipoteses_temporais_de_certidao('Certidão Negativa de Débitos\nVálida até 31/12/2026'))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_guia_fiscal_reconhecida_por_sinal_estrutural_sem_frase_textual_forte():
    resultado = resolver_tipo_documental(
        hipoteses_fiscais_de_texto('Código de Receita: 0561\nNúmero de Referência: 123'))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_documento_desconhecido_permanece_desconhecido():
    assert _resolver_textual('texto qualquer sem nenhum padrao de negocio conhecido').estado \
        == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_documento_ambiguo_permanece_ambiguo():
    assert _resolver_textual('Boleto\nLinha Digitável\nNota Fiscal de Serviço').estado \
        == EstadoResolucaoDimensao.AMBIGUA


def test_documento_com_conflito_permanece_explicito():
    """2+ entidades distintas -- mesmo com 1 candidato forte, nunca
    resolve sozinho (fail-safe genérico já provado)."""
    resultado = _resolver_textual('Recibo de Pagamento\nTotal de Vencimentos', quantidade_entidades_distintas=2)
    assert resultado.estado == EstadoResolucaoDimensao.CONFLITO


def test_filename_enganoso_nunca_influencia_o_resultado():
    """O motor nunca recebe filename -- simulado aqui só processando o
    MESMO texto associado a 2 "nomes de arquivo" fictícios diferentes e
    provando que o resultado é idêntico (o motor nem tem parâmetro para
    receber isso)."""
    texto = 'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido'
    nomes_ficticios = ('extrato_mensal_junho.pdf', 'holerite_real.pdf')  # nunca usados no cálculo
    resultados = {nome: _resolver_textual(texto) for nome in nomes_ficticios}
    assert resultados[nomes_ficticios[0]] == resultados[nomes_ficticios[1]]
    assert resultados[nomes_ficticios[0]].valores_confirmados == (
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),
    )


def test_fila_completa_produz_decisao_correta_nao_apenas_resolvida():
    """Prova final: a fila inteira, pelo MESMO motor, produz uma
    mistura real de estados -- nunca "tudo resolvido" artificialmente."""
    estados = set()
    estados.add(_resolver_textual('Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido').estado)
    estados.add(_resolver_textual('texto qualquer sem nenhum padrao de negocio conhecido').estado)
    estados.add(_resolver_textual('Boleto\nLinha Digitável\nNota Fiscal de Serviço').estado)
    estados.add(_resolver_textual('Recibo de Pagamento', quantidade_entidades_distintas=2).estado)
    assert estados == {
        EstadoResolucaoDimensao.RESOLVIDA,
        EstadoResolucaoDimensao.NAO_ENCONTRADA,
        EstadoResolucaoDimensao.AMBIGUA,
        EstadoResolucaoDimensao.CONFLITO,
    }
