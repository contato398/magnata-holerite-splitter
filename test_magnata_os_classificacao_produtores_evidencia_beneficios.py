"""Testes de `produtores_evidencia_beneficios.py` (Adendo substitutivo
ao PR #105 -- regra canônica de benefícios VR/VA/iFood; corrigido na
2ª revisão pré-merge para nunca resolver por frase/rótulo isolado --
sempre por COMBINAÇÃO de evidências estruturais)."""
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.produtores_evidencia_beneficios import (
    TIPO_RELATORIO_BENEFICIOS,
    dados_correlacao_beneficios,
    derivar_clientes_logicos_do_comprovante_global,
    hipoteses_de_relatorio_beneficios,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.ponte_conteudo_motor_semantico import resolver_tipo_documental_de_texto

_TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS = (
    'CPF: 111.222.333-44   Vale-Refeição   R$ 300,00\n'
    'CPF: 555.666.777-88   Vale-Alimentação   R$ 300,00\n'
    'Competência: 07/2026'
)


def _resolver_isolado(texto):
    return resolver_tipo_documental(hipoteses_de_relatorio_beneficios(texto))


# ============================================================================
# §7.A -- frase isolada, sem tabela/valores/beneficiários, nunca resolve
# ============================================================================

def test_a_apenas_titulo_sem_qualquer_outra_evidencia_nao_resolve_automaticamente():
    resolucao = _resolver_isolado('Relatório de Benefícios')
    assert resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA


def test_a_variantes_de_titulo_tambem_nunca_resolvem_sozinhas():
    for titulo in ('Pedido de Benefícios', 'Crédito de Benefícios', 'Solicitação de Benefícios'):
        resolucao = _resolver_isolado(titulo)
        assert resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA, titulo


# ============================================================================
# §7.B/C/D -- estrutura sem título padrão, reconhecida por combinação
# ============================================================================

def test_b_relatorio_estrutural_vr_sem_titulo_reconhecido():
    texto = (
        'CPF: 111.222.333-44   Vale-Refeição   R$ 300,00\n'
        'CPF: 555.666.777-88   Vale-Refeição   R$ 300,00\n'
        'Competência: 07/2026'
    )
    resolucao = _resolver_isolado(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_c_relatorio_estrutural_va_sem_titulo_reconhecido():
    texto = (
        'CPF: 111.222.333-44   Vale-Alimentação   R$ 300,00\n'
        'CPF: 555.666.777-88   Vale-Alimentação   R$ 300,00\n'
        'Competência: 07/2026'
    )
    resolucao = _resolver_isolado(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_d_relatorio_estrutural_vr_e_va_sem_titulo_nao_forca_escolha_exclusiva():
    resolucao = _resolver_isolado(_TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_uma_unica_linha_de_valor_sozinha_fica_ambigua_via_ponte_nunca_resolve_por_1_evidencia():
    """Sem uma SEGUNDA evidência independente (total do pedido ou 2ª
    linha de beneficiário), 1 única linha de valor (MODERADA) empata
    com a hipótese concorrente 'Comprovante de Pagamento - VR/VA' (já
    existente, MODERADA) -- o motor honestamente fica AMBIGUA, nunca
    decide por 1 evidência isolada. Prova que a correção NÃO reintroduz
    identidade por frase única disfarçada de estrutura."""
    texto = 'CPF: 111.222.333-44   Vale-Refeição   R$ 300,00\nCompetência: 07/2026'
    resolucao = resolver_tipo_documental_de_texto(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.AMBIGUA


# ============================================================================
# §7.E -- fornecedor desconhecido não impede a classificação
# ============================================================================

def test_e_fornecedor_desconhecido_nao_impede_classificacao():
    texto = (
        'CPF: 111.222.333-44   Vale-Refeição   R$ 300,00\n'
        'CPF: 555.666.777-88   Vale-Alimentação   R$ 300,00\n'
        'Fornecedor Benefícios XYZ'
    )
    resolucao = _resolver_isolado(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_mesmo_relatorio_trocando_fornecedor_conhecido_por_desconhecido_mesma_resolucao():
    texto_fornecedor_conhecido = _TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS + '\niFood Benefícios'
    texto_fornecedor_desconhecido = _TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS + '\nFornecedor Benefícios XYZ'
    resolucao_conhecido = _resolver_isolado(texto_fornecedor_conhecido)
    resolucao_desconhecido = _resolver_isolado(texto_fornecedor_desconhecido)
    assert resolucao_conhecido.estado == resolucao_desconhecido.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert (
        resolucao_conhecido.valores_confirmados[0].entidade_id
        == resolucao_desconhecido.valores_confirmados[0].entidade_id
        == TIPO_RELATORIO_BENEFICIOS
    )


# ============================================================================
# §7.F -- fornecedor sozinho, sem nenhuma outra evidência
# ============================================================================

def test_f_texto_com_ifood_beneficios_isoladamente_nunca_classifica_automaticamente():
    resolucao = _resolver_isolado('iFood Benefícios -- Julho 2026\nCPF: 111.222.333-44')
    assert resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA


# ============================================================================
# §7.G -- frase de título dentro de texto não documental
# ============================================================================

def test_g_frase_pedido_de_beneficios_em_texto_nao_documental_nunca_resolve():
    resolucao = _resolver_isolado('Este e-mail contém o Pedido de Benefícios em anexo, favor considerar.')
    assert resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA


# ============================================================================
# Comportamento geral preservado
# ============================================================================

def test_texto_sem_nenhum_sinal_nunca_gera_hipotese():
    assert hipoteses_de_relatorio_beneficios('documento qualquer sem nenhum sinal') == ()


def test_texto_vazio_nunca_gera_hipotese():
    assert hipoteses_de_relatorio_beneficios('') == ()


def test_documento_ifood_beneficios_reconhecido_pelo_mesmo_motor_quando_estrutura_suficiente():
    """§7 (iFood): entra no MESMO motor -- reconhecido quando a
    estrutura (nunca o nome do fornecedor sozinho) for suficiente."""
    texto = _TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS + '\niFood Benefícios'
    resolucao = _resolver_isolado(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_RELATORIO_BENEFICIOS


def test_documento_vr_beneficios_fornecedor_antigo_mesmo_motor_mesmo_tipo():
    """§8: fornecedor antigo (VR Benefícios) produz o MESMO tipo
    documental que o fornecedor novo (iFood) quando a estrutura for
    suficiente -- nunca uma dependência de fornecedor no core."""
    texto_novo = _TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS + '\niFood Benefícios'
    texto_antigo = _TEXTO_ESTRUTURAL_VR_VA_2_BENEFICIARIOS + '\nVR Benefícios'
    tipo_novo = _resolver_isolado(texto_novo).valores_confirmados[0].entidade_id
    tipo_antigo = _resolver_isolado(texto_antigo).valores_confirmados[0].entidade_id
    assert tipo_novo == tipo_antigo == TIPO_RELATORIO_BENEFICIOS


def test_fornecedor_nao_e_import_nem_dependencia_do_core():
    """Nenhuma classe/pipeline por fornecedor -- confirmado por
    inspeção: o módulo só tem 1 função pública de hipóteses, nenhuma
    classe/função com "Ifood"/"iFood" no nome."""
    import magnata_os.classificacao.produtores_evidencia_beneficios as modulo
    nomes_publicos = [nome for nome in dir(modulo) if not nome.startswith('_')]
    assert not any('ifood' in nome.lower() for nome in nomes_publicos)


def test_dados_correlacao_beneficios_extrai_campos_comparaveis():
    """§6 da missão "MERGE PR #105 + EVIDÊNCIA RELACIONAL...": os
    campos usados para relacionar Relatório de Benefícios ↔
    Comprovante -- mesma extração genérica de `relacao_documental`,
    fornecedor injetado da lista já cadastrada aqui."""
    texto = 'Relatório de Benefícios\nPedido no: P-42\nTotal do Pedido: R$ 900,00\niFood Benefícios'
    dados = dados_correlacao_beneficios(texto)
    assert dados.identificador_pedido == 'P-42'
    assert dados.valor_total == '900,00'
    assert dados.fornecedor == 'ifood benefícios'


def test_derivar_clientes_logicos_do_comprovante_global_so_com_relacao_resolvida():
    """§7/§8: comprovante GLOBAL só herda os clientes do relatório
    relacionado quando a relação já está RESOLVIDA -- nunca por
    suposição."""
    clientes = (ReferenciaCanonica('CLIENTE', 'cli-a'), ReferenciaCanonica('CLIENTE', 'cli-b'))
    assert derivar_clientes_logicos_do_comprovante_global(True, clientes) == clientes
    assert derivar_clientes_logicos_do_comprovante_global(False, clientes) == ()
