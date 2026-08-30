"""Fila heterogênea E2E (Fase I da missão "CAPACIDADES TRANSVERSAIS DO
MOTOR DOCUMENTAL") -- prova que o MESMO motor + a MESMA engine de
separação + o MESMO compositor atendem, na mesma fila:

  - documentos unitários (Holerite, Guia genérica);
  - 1 master multi-cliente (separado com sucesso pela mesma engine);
  - 1 documento multi-colaborador (detectado como potencialmente
    master via evidência estrutural -- separação por CPF não portada
    nesta missão, gap registrado em `docs/decisoes/capacidades-
    transversais-motor-documental-v1.md`, mas a DETECÇÃO já é
    genérica, funciona igual para CPF ou CNPJ);
  - 1 comprovante de pagamento resolvível (salário);
  - 1 comprovante de pagamento deliberadamente inconclusivo (só
    estrutura bancária, sem descrição específica);
  - 1 documento desconhecido;
  - 1 documento ambíguo.

Todos os textos são SINTÉTICOS -- nunca dado real, nunca filename
influenciando resultado."""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.evidencia_estrutural_documental import analisar_estrutura_documento
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    FINALIDADE_FGTS,
    FINALIDADE_SALARIO,
    OcorrenciaSinalFinalidade,
    SinalFinalidadePagamento,
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.resolucao_master_documental import (
    EstadoGranularidadeDocumento,
    detectar_granularidade_documento,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.separacao_documental import (
    estrategia_por_cnpj_cliente,
    separar_por_carry_forward,
    texto_do_grupo,
)

_CNPJ_MAGNATA = '00111222000133'
_CNPJ_CLIENTE_A = '11222333000181'
_CNPJ_CLIENTE_B = '44555666000172'
_INDICE_CLIENTES = {
    _CNPJ_CLIENTE_A: ('rec_cliente_a', 'Cliente A'),
    _CNPJ_CLIENTE_B: ('rec_cliente_b', 'Cliente B'),
}
_CPF_COLAB_A = '111.444.777-35'
_CPF_COLAB_B = '222.555.888-06'


def _fmt_cnpj(cnpj: str) -> str:
    return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}'


def _resolver_tipo_textual(texto: str, quantidade_entidades_distintas=None):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=quantidade_entidades_distintas)


def test_unitarios_resolvem_normalmente_na_mesma_fila():
    holerite = _resolver_tipo_textual('Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido')
    guia = _resolver_tipo_textual('Guia de Recolhimento\nGPS')
    assert holerite.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert guia.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_master_multi_cliente_e_separado_e_filhos_resolvem():
    paginas = (
        f'Tomador CNPJ {_fmt_cnpj(_CNPJ_CLIENTE_A)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
        'detalhe do cliente A',
        f'Tomador CNPJ {_fmt_cnpj(_CNPJ_CLIENTE_B)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
    )
    evidencia_estrutural = analisar_estrutura_documento(paginas)
    decisao_granularidade = detectar_granularidade_documento(evidencia_estrutural)
    assert decisao_granularidade.estado == EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER

    estrategia = estrategia_por_cnpj_cliente(_INDICE_CLIENTES, cnpj_excluido=_CNPJ_MAGNATA)
    resultado_separacao = separar_por_carry_forward(paginas, estrategia)
    assert len(resultado_separacao.grupos) == 2

    tipos_resolvidos = set()
    for grupo in resultado_separacao.grupos:
        texto_filho = texto_do_grupo(paginas, grupo)
        resolucao = _resolver_tipo_textual(texto_filho, quantidade_entidades_distintas=1)
        assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
        tipos_resolvidos.add(resolucao.valores_confirmados[0])
    assert tipos_resolvidos == {ReferenciaCanonica('TIPO_DOCUMENTAL', 'Extrato da Folha de Pagamento')}


def test_documento_multi_colaborador_e_detectado_como_potencialmente_master():
    """Separação por CPF/colaborador não foi portada nesta missão (gap
    registrado), mas a DETECÇÃO de granularidade é genérica -- funciona
    igual para CPF, sem nenhum código especial."""
    paginas = (
        f'Colaborador CPF {_CPF_COLAB_A}\nFolha de Ponto',
        f'Colaborador CPF {_CPF_COLAB_B}\nFolha de Ponto',
    )
    evidencia_estrutural = analisar_estrutura_documento(paginas)
    decisao = detectar_granularidade_documento(evidencia_estrutural)
    assert decisao.estado == EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER


def test_comprovante_de_pagamento_resolvivel_por_descricao_especifica():
    texto = 'Comprovante de pagamento de salário do mês de referência'
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto)
    resultado = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', FINALIDADE_SALARIO),)


def test_comprovante_de_pagamento_deliberadamente_inconclusivo():
    texto = 'Comprovante de transferência PIX efetuada com sucesso'
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto)
    resultado = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_documento_desconhecido_permanece_desconhecido():
    resultado = _resolver_tipo_textual('texto qualquer sem nenhum padrao de negocio conhecido')
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_documento_ambiguo_permanece_ambiguo():
    resultado = _resolver_tipo_textual('Boleto\nLinha Digitável\nNota Fiscal de Serviço')
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA


def test_fila_completa_produz_estados_heterogeneos_pelo_mesmo_motor():
    """Prova final: a MESMA fila, processada pelas MESMAS funções
    (nenhuma bifurcação por tipo/filename), produz pelo menos 4 estados
    distintos -- heterogeneidade real, nunca um motor por tipo."""
    estados = set()

    estados.add(_resolver_tipo_textual('Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido').estado)
    estados.add(_resolver_tipo_textual('texto qualquer sem nenhum padrao de negocio conhecido').estado)
    estados.add(_resolver_tipo_textual('Boleto\nLinha Digitável\nNota Fiscal de Serviço').estado)

    # Sinais fortes incompatíveis (2+ evidências MODERADA coerentes por
    # lado, reforço já provado em `resolucao_tipo_documental.py`) --
    # nunca escolhe um vencedor arbitrário.
    ocorrencias_conflito = (
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_SALARIO, FINALIDADE_SALARIO, 'ref_1'),
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_SALARIO, FINALIDADE_SALARIO, 'ref_2'),
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_FGTS, FINALIDADE_FGTS, 'ref_3'),
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_FGTS, FINALIDADE_FGTS, 'ref_4'),
    )
    estados.add(resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias_conflito)).estado)

    assert estados == {
        EstadoResolucaoDimensao.RESOLVIDA,
        EstadoResolucaoDimensao.NAO_ENCONTRADA,
        EstadoResolucaoDimensao.AMBIGUA,
        EstadoResolucaoDimensao.CONFLITO,
    }
