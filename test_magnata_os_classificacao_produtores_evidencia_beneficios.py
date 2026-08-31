"""Testes de `produtores_evidencia_beneficios.py` (Adendo substitutivo
ao PR #105 -- regra canônica de benefícios VR/VA/iFood)."""
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao
from magnata_os.classificacao.produtores_evidencia_beneficios import (
    TIPO_RELATORIO_BENEFICIOS,
    hipoteses_de_relatorio_beneficios,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental


def test_relatorio_com_vr_e_va_juntos_nao_forca_escolha_exclusiva():
    """§2: um documento com VR + VA no mesmo relatório NUNCA é forçado
    a escolher exclusivamente entre os dois -- só existe 1 candidato
    ('Relatório de Benefícios'), nunca 'VR'/'VA' concorrentes."""
    texto = (
        'Relatório de Benefícios -- Julho/2026\n'
        'CPF: 111.222.333-44   Vale-Refeição   Vale-Alimentação   R$ 500,00\n'
        'Total do Pedido: R$ 500,00'
    )
    hipoteses = hipoteses_de_relatorio_beneficios(texto)
    assert len(hipoteses) == 1
    assert hipoteses[0].tipo_documental == TIPO_RELATORIO_BENEFICIOS
    resolucao = resolver_tipo_documental(hipoteses)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_relatorio_apenas_vr_reconhecido():
    hipoteses = hipoteses_de_relatorio_beneficios('Pedido de Benefícios\nVale-Refeição\nCPF: 111.222.333-44')
    resolucao = resolver_tipo_documental(hipoteses)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_relatorio_apenas_va_reconhecido():
    hipoteses = hipoteses_de_relatorio_beneficios('Pedido de Benefícios\nVale-Alimentação\nCPF: 111.222.333-44')
    resolucao = resolver_tipo_documental(hipoteses)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_texto_sem_frase_de_relatorio_nunca_gera_hipotese():
    assert hipoteses_de_relatorio_beneficios('documento qualquer sem nenhum sinal') == ()


def test_texto_vazio_nunca_gera_hipotese():
    assert hipoteses_de_relatorio_beneficios('') == ()


def test_nome_de_fornecedor_sozinho_nunca_basta():
    """§9: "iFood" (ou qualquer fornecedor) sozinho NÃO prova que é
    relatório de prestação -- sem a frase de relatório/pedido, nenhuma
    hipótese é gerada por este produtor."""
    assert hipoteses_de_relatorio_beneficios('iFood Benefícios -- Julho 2026\nCPF: 111.222.333-44') == ()


def test_documento_ifood_beneficios_reconhecido_pelo_mesmo_motor():
    """§7: iFood é provedor/origem, nunca uma classe/pipeline separada
    -- o MESMO produtor reconhece o relatório independentemente do
    fornecedor citado."""
    texto = 'Relatório de Benefícios -- iFood Benefícios\nVale-Refeição\nCPF: 111.222.333-44'
    resolucao = resolver_tipo_documental(hipoteses_de_relatorio_beneficios(texto))
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_documento_vr_beneficios_fornecedor_antigo_mesmo_motor_mesmo_tipo():
    """§8: fornecedor antigo (VR Benefícios) produz o MESMO tipo
    documental que o fornecedor novo (iFood) -- nunca uma dependência
    de fornecedor no core."""
    texto_novo = 'Relatório de Benefícios -- iFood Benefícios\nVale-Refeição\nCPF: 111.222.333-44'
    texto_antigo = 'Relatório de Benefícios -- VR Benefícios\nVale-Refeição\nCPF: 111.222.333-44'
    tipo_novo = resolver_tipo_documental(hipoteses_de_relatorio_beneficios(texto_novo)).valores_confirmados[0].entidade_id
    tipo_antigo = resolver_tipo_documental(
        hipoteses_de_relatorio_beneficios(texto_antigo)).valores_confirmados[0].entidade_id
    assert tipo_novo == tipo_antigo == TIPO_RELATORIO_BENEFICIOS


def test_fornecedor_nao_e_import_nem_dependencia_do_core():
    """Nenhuma classe/pipeline por fornecedor -- confirmado por
    inspeção: o módulo só tem 1 função pública de hipóteses, nenhuma
    classe/função com "Ifood"/"iFood" no nome."""
    import magnata_os.classificacao.produtores_evidencia_beneficios as modulo
    nomes_publicos = [nome for nome in dir(modulo) if not nome.startswith('_')]
    assert not any('ifood' in nome.lower() for nome in nomes_publicos)
