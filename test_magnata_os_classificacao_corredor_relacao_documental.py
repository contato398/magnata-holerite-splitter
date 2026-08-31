"""Suíte E2E obrigatória (§23 da missão "CORRIGIR METADADOS + MERGE
PR #106 + COSTURA AUTOMÁTICA DE RELAÇÃO DOCUMENTO↔DOCUMENTO NO
CORREDOR V1") -- casos A a J, cada um mapeado 1:1 ao texto da missão.
Exercita `corredor_relacao_documental.resolver_relacao_e_avancar`, o
ponto de entrada único da costura automática."""
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.corredor_relacao_documental import (
    ContextoRelacaoDocumentoPrestacao,
    medir_relacoes,
    resolver_relacao_e_avancar,
)
from magnata_os.classificacao.fonte_candidatos_relacao_documental import CandidatoRelacaoDocumental
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from magnata_os.classificacao.produtores_evidencia_beneficios import dados_correlacao_beneficios
from magnata_os.classificacao.relacao_documental import DadosCorrelacaoDocumental

_COMPETENCIA = (2026, 6)


class _FonteCandidatosFake:
    def __init__(self, candidatos=()):
        self._candidatos = candidatos

    def candidatos_para_relacao(self, documento_id_atual, tipo_atual, tipo_candidato, competencia, tipo_relacao):
        return tuple(c for c in self._candidatos if c.tipo_documental == tipo_candidato)


def _contexto_comprovante_beneficios(candidatos, identificador='PED-1', valor='900,00'):
    return ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-beneficios-1', tipo_documental='Comprovante de Pagamento - VR/VA',
        competencia=_COMPETENCIA,
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido=identificador, valor_total=valor, competencia=_COMPETENCIA),
        fonte_candidatos=_FonteCandidatosFake(candidatos),
    )


def _relatorio_candidato(documento_id, referencias, identificador='PED-1', valor='900,00'):
    return CandidatoRelacaoDocumental(
        documento_id=documento_id, tipo_documental='Relatório de Benefícios',
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido=identificador, valor_total=valor, competencia=_COMPETENCIA),
        referencias_logicas=referencias,
    )


# --- Caso A: relatório + comprovante global correto -- encontra, resolve, clientes corretos ---

def test_caso_a_beneficios_candidato_correto_resolve_e_gera_inventario():
    cli_a, cli_b = ReferenciaCanonica('CLIENTE', 'cli-a'), ReferenciaCanonica('CLIENTE', 'cli-b')
    candidato = _relatorio_candidato('rel-a', (cli_a, cli_b))
    contexto = _contexto_comprovante_beneficios((candidato,))
    sink = InventarioPrestacaoEmMemoria()

    resultado = resolver_relacao_e_avancar(contexto, sink)

    assert resultado.regra_aplicavel is True
    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.resolucao_relacao.documento_b_id == 'rel-a'
    assert set(item.cliente for item in resultado.itens_gerados) == {cli_a, cli_b}
    assert sink.total_itens() == 2
    # readiness/pacote continuam automáticos a partir do inventário --
    # nenhuma mudança nesse mecanismo (§19); provado aqui só pela
    # presença dos itens no MESMO sink que o resto do corredor usa.
    itens_cli_a = sink.listar(cli_a, ReferenciaCanonica('COMPETENCIA', '2026-06'))
    assert len(itens_cli_a) == 1


# --- Caso B: comprovante com 2 relatórios fortes -- AMBIGUA, nenhum pacote automático ---

def test_caso_b_dois_relatorios_fortes_ambigua_nenhum_item_gerado():
    cli_a = ReferenciaCanonica('CLIENTE', 'cli-a')
    cli_c = ReferenciaCanonica('CLIENTE', 'cli-c')
    candidato_1 = _relatorio_candidato('rel-1', (cli_a,))
    candidato_2 = _relatorio_candidato('rel-2', (cli_c,))
    contexto = _contexto_comprovante_beneficios((candidato_1, candidato_2))
    sink = InventarioPrestacaoEmMemoria()

    resultado = resolver_relacao_e_avancar(contexto, sink)

    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.AMBIGUA
    assert resultado.itens_gerados == ()
    assert sink.total_itens() == 0


# --- Caso C: mesmo valor somente -- NÃO resolve ---

def test_caso_c_apenas_valor_igual_nao_resolve():
    candidato = CandidatoRelacaoDocumental(
        documento_id='rel-fraco', tipo_documental='Relatório de Benefícios',
        dados_correlacao=DadosCorrelacaoDocumental(valor_total='900,00'),
        referencias_logicas=(ReferenciaCanonica('CLIENTE', 'cli-a'),),
    )
    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-1', tipo_documental='Comprovante de Pagamento - VR/VA', competencia=_COMPETENCIA,
        dados_correlacao=DadosCorrelacaoDocumental(valor_total='900,00'),
        fonte_candidatos=_FonteCandidatosFake((candidato,)),
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.itens_gerados == ()


# --- Caso D: candidato errado + candidato correto -- correto resolve ---

def test_caso_d_candidato_errado_nao_impede_candidato_correto():
    cli_certo = ReferenciaCanonica('CLIENTE', 'cli-certo')
    candidato_errado = _relatorio_candidato('rel-errado', (ReferenciaCanonica('CLIENTE', 'cli-errado'),), identificador='PED-OUTRO')
    candidato_certo = _relatorio_candidato('rel-certo', (cli_certo,))
    contexto = _contexto_comprovante_beneficios((candidato_errado, candidato_certo))
    sink = InventarioPrestacaoEmMemoria()

    resultado = resolver_relacao_e_avancar(contexto, sink)

    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.resolucao_relacao.documento_b_id == 'rel-certo'
    assert set(item.cliente for item in resultado.itens_gerados) == {cli_certo}


# --- Caso E: nenhum candidato -- NAO_ENCONTRADA ---

def test_caso_e_nenhum_candidato_nao_encontrada():
    contexto = _contexto_comprovante_beneficios(())
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.itens_gerados == ()


# --- Caso F: FGTS guia + comprovante cliente A -- somente pacote A ---

def test_caso_f_fgts_comprovante_herda_somente_cliente_da_guia():
    cli_a = ReferenciaCanonica('CLIENTE', 'cli-a')
    guia = CandidatoRelacaoDocumental(
        documento_id='guia-fgts-1', tipo_documental='FGTS',
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido='GUIA-1', valor_total='500,00', competencia=_COMPETENCIA),
        referencias_logicas=(cli_a,),
    )
    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-fgts-1', tipo_documental='Comprovante de Pagamento - FGTS', competencia=_COMPETENCIA,
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido='GUIA-1', valor_total='500,00', competencia=_COMPETENCIA),
        fonte_candidatos=_FonteCandidatosFake((guia,)),
    )
    sink = InventarioPrestacaoEmMemoria()
    resultado = resolver_relacao_e_avancar(contexto, sink)

    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert len(resultado.itens_gerados) == 1
    assert resultado.itens_gerados[0].cliente == cli_a
    # Nunca vaza para outro cliente.
    assert all(item.cliente == cli_a for item in resultado.itens_gerados)


# --- Caso G: DCTF guia + comprovante -- broadcast preservado ---

def test_caso_g_dctf_relacao_resolve_mas_nao_gera_item_broadcast_preservado():
    guia = CandidatoRelacaoDocumental(
        documento_id='guia-dctf-1', tipo_documental='Guia DCTFWeb/DARF',
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido='DCTF-1', valor_total='300,00', competencia=_COMPETENCIA),
        referencias_logicas=(ReferenciaCanonica('CLIENTE', 'cli-x'),),
    )
    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-dctf-1', tipo_documental='Comprovante de Pagamento - DCTF/DARF', competencia=_COMPETENCIA,
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido='DCTF-1', valor_total='300,00', competencia=_COMPETENCIA),
        fonte_candidatos=_FonteCandidatosFake((guia,)),
    )
    sink = InventarioPrestacaoEmMemoria()
    resultado = resolver_relacao_e_avancar(contexto, sink)

    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    # Broadcast é decidido pela política DCTF já canônica (fora deste
    # módulo), nunca pela relação -- nenhum item gerado aqui.
    assert resultado.itens_gerados == ()
    assert sink.total_itens() == 0


# --- Caso H: documento relacionado executado 2x -- idempotente ---

def test_caso_h_execucao_dupla_nunca_duplica():
    cli_a = ReferenciaCanonica('CLIENTE', 'cli-a')
    candidato = _relatorio_candidato('rel-a', (cli_a,))
    contexto = _contexto_comprovante_beneficios((candidato,))
    sink = InventarioPrestacaoEmMemoria()

    resultado_1 = resolver_relacao_e_avancar(contexto, sink)
    resultado_2 = resolver_relacao_e_avancar(contexto, sink)

    assert resultado_1.resolucao_relacao == resultado_2.resolucao_relacao
    assert sink.total_itens() == 1  # nunca duplicado


# --- Caso I: relação não encontrada -- classificação (fora deste módulo) não é desfeita ---

def test_caso_i_relacao_nao_encontrada_nunca_levanta_nem_afeta_nada_alem_do_proprio_resultado():
    """Este orquestrador é puramente ADITIVO -- nunca recebe, nunca
    devolve, nunca toca em `tipo_documental`/classificação; a ausência
    de relação só afeta o próprio resultado desta função."""
    contexto = _contexto_comprovante_beneficios(())
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.tipo_documental == 'Comprovante de Pagamento - VR/VA'  # classificação intacta
    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


# --- Caso J: fornecedor de benefício desconhecido -- relação funciona por outras evidências ---

def test_caso_j_fornecedor_desconhecido_relacao_resolve_por_outras_evidencias():
    texto_relatorio = 'Relatório de Benefícios\nPedido no: PED-9\nTotal do Pedido: R$ 700,00\nFornecedor Novo Ltda'
    texto_comprovante = 'Comprovante de Pagamento\nPedido no: PED-9\nTotal do Pedido: R$ 700,00'
    dados_relatorio = dados_correlacao_beneficios(texto_relatorio)
    dados_comprovante = dados_correlacao_beneficios(texto_comprovante)
    assert dados_relatorio.fornecedor is None

    cli_a = ReferenciaCanonica('CLIENTE', 'cli-a')
    candidato = CandidatoRelacaoDocumental(
        documento_id='rel-fornecedor-novo', tipo_documental='Relatório de Benefícios',
        dados_correlacao=dados_relatorio, referencias_logicas=(cli_a,),
    )
    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-fornecedor-novo', tipo_documental='Comprovante de Pagamento - VR/VA', competencia=_COMPETENCIA,
        dados_correlacao=dados_comprovante, fonte_candidatos=_FonteCandidatosFake((candidato,)),
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA


# --- Tipo sem regra cadastrada -- este módulo nem tenta ---

def test_tipo_sem_regra_cadastrada_nao_avalia_relacao():
    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='hol-1', tipo_documental='Holerite', competencia=_COMPETENCIA,
        fonte_candidatos=_FonteCandidatosFake(()),
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.regra_aplicavel is False
    assert resultado.resolucao_relacao is None


def test_sem_fonte_candidatos_nao_avalia_relacao():
    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-1', tipo_documental='Comprovante de Pagamento - VR/VA', competencia=_COMPETENCIA,
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.regra_aplicavel is False
    assert resultado.resolucao_relacao is None


# --- Métricas (§22) ---

def test_medir_relacoes_agrega_estados_corretamente():
    cli_a = ReferenciaCanonica('CLIENTE', 'cli-a')
    sink = InventarioPrestacaoEmMemoria()
    resultados = (
        resolver_relacao_e_avancar(_contexto_comprovante_beneficios((_relatorio_candidato('rel-a', (cli_a,)),)), sink),
        resolver_relacao_e_avancar(_contexto_comprovante_beneficios(()), sink),
        resolver_relacao_e_avancar(
            ContextoRelacaoDocumentoPrestacao(
                documento_id='hol-1', tipo_documental='Holerite', competencia=_COMPETENCIA,
                fonte_candidatos=_FonteCandidatosFake(()),
            ),
            sink,
        ),
    )
    metricas = medir_relacoes(resultados)
    assert metricas.total_relacoes_avaliadas == 2  # Holerite nunca conta (regra_aplicavel=False)
    assert metricas.auto_relacoes_resolvidas == 1
    assert metricas.relacoes_nao_encontradas == 1
    assert metricas.auto_relacoes_aplicadas_a_inventario == 1
    assert metricas.percentual_auto_relacao == 0.5


def test_medir_relacoes_percentual_none_sem_avaliacao():
    metricas = medir_relacoes(())
    assert metricas.total_relacoes_avaliadas == 0
    assert metricas.percentual_auto_relacao is None
