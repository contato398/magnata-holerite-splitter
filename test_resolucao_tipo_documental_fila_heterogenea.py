"""Prova de fila heterogênea (Fase F/G/H da missão "MOTOR GERAL DE
COMPREENSÃO DOCUMENTAL"): o MESMO motor (`resolver_tipo_documental` +
`hipoteses_textuais_de_classificacao`), aplicado a documentos
DIFERENTES, produz resoluções DIFERENTES baseadas em evidência
disponível -- nunca por filename, nunca obrigatoriamente por uma frase
exata específica.

Todos os textos são SINTÉTICOS -- frases institucionais genéricas já
usadas pelos próprios regex de `classificador_documental.py` (a mesma
fonte usada pelos testes já existentes desse módulo), nunca dado
pessoal real. Nenhum PDF real, nenhum filename real influencia o
resultado -- o motor nunca recebe nome de arquivo (ver
test_magnata_os_classificacao_resolucao_tipo_documental.py::
test_nenhuma_funcao_do_motor_aceita_filename).
"""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental


def _resolver(texto: str):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses)


# Fila heterogênea representativa -- 11 documentos, cobrindo os tipos
# mínimos exigidos pela missão (Fase F) + desconhecido + ambíguo.
_FILA = {
    'holerite': (
        'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido',
        EstadoResolucaoDimensao.RESOLVIDA, 'Holerite',
    ),
    'extrato_mensal': (
        'Extrato Mensal\nExtrato da Folha de Pagamento',
        EstadoResolucaoDimensao.RESOLVIDA, 'Extrato da Folha de Pagamento',
    ),
    'fgts_digital': (
        'FGTS Digital\nGuia do FGTS\nTotal FGTS',
        EstadoResolucaoDimensao.RESOLVIDA, 'FGTS',
    ),
    'dctfweb_declaracao': (
        'Comprovante emitido pelo sistema DCTFWeb da empresa',
        EstadoResolucaoDimensao.RESOLVIDA, 'DCTFWeb - Declaração',
    ),
    'dctfweb_recibo': (
        'Recibo de Entrega da DCTFWeb referente à competência',
        EstadoResolucaoDimensao.RESOLVIDA, 'DCTFWeb - Recibo de Entrega',
    ),
    'guia_dctf_darf': (
        'Guia de Recolhimento da DCTFWeb\nDARF da DCTFWeb',
        EstadoResolucaoDimensao.RESOLVIDA, 'Guia DCTFWeb/DARF',
    ),
    'folha_de_ponto': (
        'Folha de Ponto\nEspelho de Ponto\nSecullum',
        EstadoResolucaoDimensao.RESOLVIDA, 'Folha de Ponto',
    ),
    'nota_fiscal': (
        'NFS-e emitida\nNota Fiscal de Serviço',
        EstadoResolucaoDimensao.RESOLVIDA, 'Nota Fiscal',
    ),
    'guia_generica': (
        'Guia de Recolhimento\nGPS',
        EstadoResolucaoDimensao.RESOLVIDA, 'Guia',
    ),
    'desconhecido': (
        'texto qualquer sem nenhum padrao de negocio conhecido pela prestacao',
        EstadoResolucaoDimensao.NAO_ENCONTRADA, None,
    ),
    'ambiguo_boleto_nota_fiscal': (
        'Boleto\nLinha Digitável\nNota Fiscal de Serviço',
        EstadoResolucaoDimensao.AMBIGUA, None,
    ),
}


def test_fila_heterogenea_produz_resultados_diferentes_pelo_mesmo_motor():
    resultados = {chave: _resolver(texto) for chave, (texto, _, _) in _FILA.items()}

    for chave, (_texto, estado_esperado, tipo_esperado) in _FILA.items():
        resultado = resultados[chave]
        assert resultado.estado == estado_esperado, (
            f'{chave}: esperado {estado_esperado}, obtido {resultado.estado}')
        if tipo_esperado is not None:
            assert resultado.valores_confirmados == (
                ReferenciaCanonica('TIPO_DOCUMENTAL', tipo_esperado),), chave

    # Heterogeneidade real: nem todos resolvem, nem todos falham do
    # mesmo jeito -- o motor produz pelo menos 3 estados distintos na
    # mesma fila.
    estados_distintos = {resultado.estado for resultado in resultados.values()}
    assert estados_distintos == {
        EstadoResolucaoDimensao.RESOLVIDA,
        EstadoResolucaoDimensao.NAO_ENCONTRADA,
        EstadoResolucaoDimensao.AMBIGUA,
    }

    # 9 tipos distintos resolvidos automaticamente na mesma fila -- nunca
    # um motor "de Holerite" com um fallback para os outros.
    tipos_resolvidos = {
        resultado.valores_confirmados[0].entidade_id
        for resultado in resultados.values()
        if resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    }
    assert len(tipos_resolvidos) == 9


def test_documento_desconhecido_nunca_vira_falso_positivo():
    resultado = _resolver(_FILA['desconhecido'][0])
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.valores_confirmados == ()


def test_documento_ambiguo_nunca_escolhe_um_vencedor_arbitrario():
    resultado = _resolver(_FILA['ambiguo_boleto_nota_fiscal'][0])
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA
    assert resultado.valores_confirmados == ()
    assert set(resultado.candidatos) == {
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Boleto'),
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Nota Fiscal'),
    }
