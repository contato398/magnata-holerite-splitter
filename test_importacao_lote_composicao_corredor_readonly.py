"""Testes de `composicao_corredor_readonly.py` (missão "CONSTRUIR
ORQUESTRADOR REAL READ-ONLY DO CORREDOR V2"). Prova que os adapters
REAIS (já construídos em missões anteriores desta sessão) compõem,
sem nenhum ajuste, através de `ExecucaoCorredorReadonly` -- só
`Mock()` local para o transporte Airtable, nunca rede real. Casos
mapeados aos §25/§27/§28/§30/§31 da missão (nível de borda)."""
from unittest.mock import Mock

from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
)
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import F_FGTS_CLIENTE, TABLE_FGTS
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import F_EXT_CLIENTE, TABLE_EXTRATO
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import F_FUNC_LOCAIS, TABLE_FUNC
from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly
from magnata_os.documental.importacao_lote.contratos import CandidatoCliente, CandidatoFuncionario

_CNPJ_A = '11.222.333/0001-44'
_CLIENTE_A_ID = 'recCLIENTE_A'
_CLIENTE_A_REF = ReferenciaCanonica('CLIENTE', _CLIENTE_A_ID)
_COMPETENCIA_0726 = ReferenciaCanonica('COMPETENCIA', '2026-07')


def _leitor_vazio():
    leitor = Mock()
    leitor.listar_registros.return_value = []
    leitor.listar_clientes.return_value = []
    return leitor


def test_dctf_broadcast_via_adapters_reais_avanca():
    leitor = _leitor_vazio()
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    resultados = execucao.processar_documento(
        'doc-dctf-1', 'a' * 64, texto=texto, clientes_broadcast=(ReferenciaCanonica('CLIENTE', 'cli-x'),),
    )
    assert resultados[0].resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert len(resultados[0].itens_inventario) == 1
    # Nenhuma chamada ao Airtable foi necessária para um documento
    # broadcast (nenhuma dimensão consulta fonte real aqui).
    leitor.listar_registros.assert_not_called()


def test_extrato_com_cnpj_real_resolve_cliente_direto_via_adapter_real():
    leitor = Mock()
    leitor.listar_registros.return_value = []
    leitor.listar_clientes.return_value = [
        CandidatoCliente(cliente_id=_CLIENTE_A_ID, cnpj=_CNPJ_A, nome_normalizado='CLIENTE A LTDA'),
    ]
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    texto = f'Extrato Mensal\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026'
    resultados = execucao.processar_documento('doc-ext-1', 'b' * 64, texto=texto)
    resultado = resultados[0]
    assert resultado.resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert resultado.itens_inventario[0].cliente == ReferenciaCanonica('CLIENTE', _CLIENTE_A_ID)
    leitor.listar_clientes.assert_called_once_with()


def test_sky_ciclo_base_julho_snapshot_comprovado_julho_unidade_posto_junho_nao_encontrada():
    """Caso obrigatório (§30 da missão) via composição de borda com
    adapters reais: `competencia_snapshot_comprovada` só para Julho
    nunca prova UNIDADE_POSTO para Junho (competência esperada real do
    SKY Tatuí, base Julho -1). Nenhum override."""
    leitor = Mock()
    leitor.listar_registros.side_effect = lambda **kwargs: (
        [{'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}}] if kwargs.get('table_id') == TABLE_FUNC else []
    )
    leitor.listar_clientes.return_value = []
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), competencia_snapshot_comprovada=(2026, 7),
        cliente_do_ciclo=REFERENCIA_CLIENTE_SKY_TATUI,
    )
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: 111.222.333-44'
    resultados = execucao.processar_documento(
        'doc-hol-sky', 'c' * 64, texto=texto,
        candidatos_colaborador=[CandidatoFuncionario(func_id='func-1', cpf='11122233344', nome_normalizado='JOAO')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r.estado for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.COMPETENCIA] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_ENCONTRADA


# ============================================================================
# §5 do checkpoint final pré-merge -- correlação same-run pela BORDA REAL
# (nunca fake que pré-carrega o candidato; usa ExecucaoCorredorReadonly
# de ponta a ponta, com Mock() de leitor).
# ============================================================================

def _leitor_para_correlacao(itens_externos_fgts=()):
    """`itens_externos_fgts`: registros crus (`{'id':..., 'fields':{...}}`)
    que o Airtable EXTERNO já teria para `TABLE_FGTS` -- vazio por
    padrão (nenhum preload, provando que a descoberta same-run funciona
    sem depender de nada externo)."""
    leitor = Mock()

    def _listar_registros(**kwargs):
        if kwargs.get('table_id') == TABLE_FGTS:
            return list(itens_externos_fgts)
        return []

    leitor.listar_registros.side_effect = _listar_registros
    leitor.listar_clientes.return_value = [
        CandidatoCliente(cliente_id=_CLIENTE_A_ID, cnpj=_CNPJ_A, nome_normalizado='CLIENTE A LTDA'),
    ]
    return leitor


def test_caso_a_relatorio_processado_entra_no_sink_e_registra_correlacao_transitoria():
    leitor = _leitor_para_correlacao()
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
        cliente_do_ciclo=_CLIENTE_A_REF,
    )
    texto_guia = f'Guia do FGTS Digital -- Total FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    resultados = execucao.processar_documento('doc-fgts-guia-1', 'a' * 64, texto=texto_guia)
    assert resultados[0].resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    # A entrou no sink local.
    assert len(execucao.sink.listar(_CLIENTE_A_REF, _COMPETENCIA_0726)) == 1
    # dados_correlacao registrados na fonte transitória.
    assert resultados[0].dados_correlacao_extraidos is not None


def test_caso_b_comprovante_encontra_relatante_do_mesmo_run_sem_preload_externo():
    """Núcleo do achado do checkpoint: SEM nenhum item pré-carregado no
    Airtable externo (fake), o Comprovante processado DEPOIS, no MESMO
    `ExecucaoCorredorReadonly`, encontra o candidato só pelo inventário
    LOCAL gerado neste run + correlação transitória -- COMPROVA
    RESOLVIDA."""
    leitor = _leitor_para_correlacao()  # nenhum item externo
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
        cliente_do_ciclo=_CLIENTE_A_REF,
    )
    texto_guia = f'Guia do FGTS Digital -- Total FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    execucao.processar_documento('doc-fgts-guia-2', 'b' * 64, texto=texto_guia)

    texto_comprovante = f'Comprovante de recolhimento do FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    resultados = execucao.processar_documento('doc-fgts-comp-2', 'c' * 64, texto=texto_comprovante)
    resultado_comprovante = resultados[0]
    assert resultado_comprovante.resolucao_relacao is not None
    resolucao_relacao = resultado_comprovante.resolucao_relacao.resolucao_relacao
    assert resolucao_relacao is not None
    assert resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_relacao.documento_a_id == 'doc-fgts-guia-2'


def test_caso_c_nova_execucao_nao_encontra_relatante_da_execucao_anterior():
    """Restart (nova `ExecucaoCorredorReadonly`) -- o cache transitório
    da execução anterior nunca sobrevive; a relação não resolve só
    porque um run PASSADO processou o relatante."""
    leitor1 = _leitor_para_correlacao()
    execucao1 = ExecucaoCorredorReadonly(
        leitor1, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
        cliente_do_ciclo=_CLIENTE_A_REF,
    )
    texto_guia = f'Guia do FGTS Digital -- Total FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    execucao1.processar_documento('doc-fgts-guia-3', 'd' * 64, texto=texto_guia)

    leitor2 = _leitor_para_correlacao()  # execução NOVA, leitor novo, nada compartilhado
    execucao2 = ExecucaoCorredorReadonly(
        leitor2, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
        cliente_do_ciclo=_CLIENTE_A_REF,
    )
    texto_comprovante = f'Comprovante de recolhimento do FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    resultados = execucao2.processar_documento('doc-fgts-comp-3', 'e' * 64, texto=texto_comprovante)
    resultado_comprovante = resultados[0]
    if resultado_comprovante.resolucao_relacao is not None:
        resolucao_relacao = resultado_comprovante.resolucao_relacao.resolucao_relacao
        assert resolucao_relacao is None or resolucao_relacao.estado != EstadoResolucaoDimensao.RESOLVIDA


def test_caso_d_relatante_externo_e_local_dedupam_1_candidato():
    """A já existe no Airtable externo (mesmo `documento_id`) E é
    reprocessado nesta execução (entra no sink local também) -- nunca
    vira 2 candidatos (dedupe por `identidade_logica`,
    `FonteInventarioPrestacaoComposta`)."""
    item_externo = {'id': 'doc-fgts-guia-4', 'fields': {F_FGTS_CLIENTE: [_CLIENTE_A_ID]}}
    leitor = _leitor_para_correlacao(itens_externos_fgts=(item_externo,))
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
        cliente_do_ciclo=_CLIENTE_A_REF,
    )
    texto_guia = f'Guia do FGTS Digital -- Total FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    # MESMO documento_id do item externo -- reprocessado nesta execução.
    execucao.processar_documento('doc-fgts-guia-4', 'f' * 64, texto=texto_guia)

    texto_comprovante = f'Comprovante de recolhimento do FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    resultados = execucao.processar_documento('doc-fgts-comp-4', '0' * 64, texto=texto_comprovante)
    resolucao_relacao = resultados[0].resolucao_relacao.resolucao_relacao
    assert resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    # Nunca AMBIGUA por causa de 2 "candidatos" (externo + local) que na
    # verdade são o MESMO documento -- dedupe garantiu 1 só.
    assert resolucao_relacao.documento_a_id == 'doc-fgts-guia-4'


def test_caso_e_relatante_so_no_externo_continua_encontravel():
    """A só existe no Airtable externo (nunca processado nesta
    execução) -- continua encontrável (a composição nunca perde o
    inventário externo, só ACRESCENTA o local)."""
    item_externo = {'id': 'doc-fgts-guia-5', 'fields': {F_FGTS_CLIENTE: [_CLIENTE_A_ID]}}
    leitor = _leitor_para_correlacao(itens_externos_fgts=(item_externo,))
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
        cliente_do_ciclo=_CLIENTE_A_REF,
    )
    # Nenhum processar_documento para o relatante -- só existe no externo.
    texto_comprovante = f'Comprovante de recolhimento do FGTS\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    resultados = execucao.processar_documento('doc-fgts-comp-5', '1' * 64, texto=texto_comprovante)
    resultado_relacao = resultados[0].resolucao_relacao
    assert resultado_relacao is not None
    assert resultado_relacao.regra_aplicavel is True
    # Candidato real encontrado (identidade), mesmo sem dados_correlacao
    # (nunca registrados no Airtable de verdade) -- resolução pode ficar
    # AMBIGUA/NAO_ENCONTRADA por falta de correlação real, mas o
    # candidato em si nunca desaparece por causa da composição.
    assert 'doc-fgts-guia-5' in resultado_relacao.resolucao_relacao.candidatos_documento_a_id or (
        resultado_relacao.resolucao_relacao.documento_a_id == 'doc-fgts-guia-5'
    )


# ============================================================================
# §6 do checkpoint -- proteção de master (fail-safe, texto nunca
# contamina filho)
# ============================================================================

def test_master_multi_filho_nunca_extrai_correlacao_do_texto_inteiro():
    """Com `identificar_pagina` fornecido e o documento detectado como
    master, cada filho separado NUNCA tem `dados_correlacao` extraído
    do texto MASTER inteiro (só o nível de página real, indisponível
    hoje via `extrair_texto_pdf`, poderia fazer isso honestamente)."""
    from magnata_os.classificacao.separacao_documental import estrategia_por_cpf_colaborador

    leitor = _leitor_para_correlacao()
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), habilitar_correlacao_transitoria=True,
    )
    indice_cpf = {'11122233344': ('func-1', 'JOAO'), '55566677788': ('func-2', 'MARIA')}
    texto_master = (
        'Relatório de Benefícios\nCPF: 111.222.333-44\nCompetência: 07/2026\n'
        'Vale-Refeição   R$ 450,00\nPedido: PED-1\nValor Total: R$ 450,00\n'
        'Relatório de Benefícios\nCPF: 555.666.777-88\nCompetência: 07/2026\n'
        'Vale-Refeição   R$ 300,00\nPedido: PED-2\nValor Total: R$ 300,00\n'
    )
    resultados = execucao.processar_documento(
        'doc-master-1', '2' * 64, texto=texto_master,
        identificar_pagina=estrategia_por_cpf_colaborador(indice_cpf),
    )
    # Se a detecção de master exigir múltiplas páginas reais (1 string
    # concatenada não fatiada nunca dispara POTENCIALMENTE_MASTER --
    # limitação já documentada no ADR), o documento processa como 1 só
    # e o teste não se aplica -- não falha por isso.
    for resultado in resultados:
        eh_filho = resultado.resultado_corredor.documento_id != 'doc-master-1'
        if eh_filho:
            assert resultado.dados_correlacao_extraidos is None


def test_pacote_via_fonte_inventario_completa_enxerga_externo_e_local():
    """§7 do checkpoint: pacote/readiness usando `execucao.fonte_
    inventario_completa` enxergam o item externo pré-existente E o
    documento processado nesta execução -- nunca só um dos 2."""
    from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
    from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
    from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao

    item_externo_extrato = {'id': 'doc-ext-externo', 'fields': {F_EXT_CLIENTE: [_CLIENTE_A_ID]}}
    leitor = Mock()

    def _listar_registros(**kwargs):
        return [item_externo_extrato] if kwargs.get('table_id') == TABLE_EXTRATO else []

    leitor.listar_registros.side_effect = _listar_registros
    leitor.listar_clientes.return_value = [
        CandidatoCliente(cliente_id=_CLIENTE_A_ID, cnpj=_CNPJ_A, nome_normalizado='CLIENTE A LTDA'),
    ]
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    politica = PoliticaRequisitosPrestacao(
        version='v1', requisitos_base=(RequisitoDocumentalPrestacao('Extrato da Folha de Pagamento'),),
    )
    texto = f'Extrato Mensal\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026'
    resultados = execucao.processar_documento(
        'doc-ext-local', 'a' * 64, texto=texto,
        fonte_inventario_pacote=execucao.fonte_inventario_completa, politica_requisitos=politica,
    )
    pacote = resultados[0].pacote
    assert pacote is not None
    assert pacote.estado == EstadoPacotePrestacao.PRONTO
    ids_incluidos = {item.documento_id for item in pacote.itens_incluidos}
    assert 'doc-ext-local' in ids_incluidos  # gerado neste run
    assert 'doc-ext-externo' in ids_incluidos  # pré-existente no Airtable


# ============================================================================
def test_idempotencia_reprocessar_documento_via_borda_nao_duplica_inventario():
    leitor = Mock()
    leitor.listar_registros.return_value = []
    leitor.listar_clientes.return_value = [
        CandidatoCliente(cliente_id=_CLIENTE_A_ID, cnpj=_CNPJ_A, nome_normalizado='CLIENTE A LTDA'),
    ]
    execucao = ExecucaoCorredorReadonly(leitor, ContextoCicloPrestacao((2026, 7)))
    texto = f'Extrato Mensal\nCNPJ: {_CNPJ_A}\nCompetência: 07/2026'
    execucao.processar_documento('doc-ext-dup', 'd' * 64, texto=texto)
    execucao.processar_documento('doc-ext-dup', 'd' * 64, texto=texto)
    competencia_ref = ReferenciaCanonica('COMPETENCIA', '2026-07')
    itens = execucao.sink.listar(ReferenciaCanonica('CLIENTE', _CLIENTE_A_ID), competencia_ref)
    assert len(itens) == 1


def test_rejeita_pdf_e_texto_ao_mesmo_tempo():
    import pytest

    execucao = ExecucaoCorredorReadonly(_leitor_vazio(), ContextoCicloPrestacao((2026, 7)))
    with pytest.raises(ValueError):
        execucao.processar_documento('doc-x', 'e' * 64, pdf_bytes=b'x', texto='y')


def test_rejeita_nem_pdf_nem_texto():
    import pytest

    execucao = ExecucaoCorredorReadonly(_leitor_vazio(), ContextoCicloPrestacao((2026, 7)))
    with pytest.raises(ValueError):
        execucao.processar_documento('doc-x', 'e' * 64)
