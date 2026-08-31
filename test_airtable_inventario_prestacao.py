from unittest.mock import Mock

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
    F_FGTS_CLIENTE,
    F_GUIA_TIPO,
    TABLE_FGTS,
    TABLE_GUIAS,
    FonteEscopoClientesPorInventarioAirtableShadow,
    FonteInventarioPrestacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (
    F_EXT_CLIENTE,
    TABLE_EXTRATO,
)


def _consumir(fonte: FonteInventarioPrestacao):
    return fonte.listar(
        ReferenciaCanonica("CLIENTE", "recCLIENTE"),
        ReferenciaCanonica("COMPETENCIA", "2026-07"),
    )


def test_adapter_lista_somente_extrato_do_cliente_e_competencia():
    leitor = Mock()
    leitor.listar_registros.side_effect = [
        [
            {
                "id": "recEXTRATO2",
                "fields": {
                    F_EXT_CLIENTE: [{"id": "recCLIENTE"}],
                    "URL": "https://exemplo.invalid/nao-deve-vazar",
                    "conteudo_bruto": "nao-deve-vazar",
                },
            },
            {
                "id": "recOUTROCLIENTE",
                "fields": {F_EXT_CLIENTE: ["recOUTRO"]},
            },
            {
                "id": "recEXTRATO1",
                "fields": {F_EXT_CLIENTE: ["recCLIENTE"]},
            },
        ],
        [
            {
                "id": "recFGTS1",
                "fields": {
                    F_FGTS_CLIENTE: ["recCLIENTE"],
                    "anexo": ["nao-deve-vazar"],
                },
            },
            {
                "id": "recFGTSOUTRO",
                "fields": {F_FGTS_CLIENTE: ["recOUTRO"]},
            },
        ],
        [
            {
                "id": "recDCTFDECLARACAO",
                "fields": {
                    F_GUIA_TIPO: "DCTFWeb - Declaração",
                    "PDF GUIA": [{"url": "nao-deve-vazar"}],
                },
            },
            {
                "id": "recDCTFRECIBO",
                "fields": {F_GUIA_TIPO: "DCTFWeb - Recibo de Entrega"},
            },
            {
                "id": "recGUIADCTFWEB",
                "fields": {
                    F_GUIA_TIPO: "Guia DCTFWeb/DARF",
                    "comprovante": "nao-deve-vazar",
                },
            },
            {
                "id": "recDCTFGENERICO",
                "fields": {F_GUIA_TIPO: "DCTFWEB"},
            },
            {
                "id": "recCOMPROVANTEDCTFWEB",
                "fields": {F_GUIA_TIPO: "Comprovante Guia DCTFWeb/DARF"},
            },
        ],
    ]

    itens = _consumir(FonteInventarioPrestacaoAirtableShadow(leitor))

    assert leitor.listar_registros.call_args_list == [
        (( ), {
            "table_id": TABLE_EXTRATO,
            "fields": [F_EXT_CLIENTE],
            "filter_by_formula": '{Folha Mensal}="Julho 2026"',
        }),
        (( ), {
            "table_id": TABLE_FGTS,
            "fields": [F_FGTS_CLIENTE],
            "filter_by_formula": '{Folha Mensal}="Julho 2026"',
        }),
        (( ), {
            "table_id": TABLE_GUIAS,
            "fields": [F_GUIA_TIPO],
            "filter_by_formula": (
                'AND({Mês Contabilidade}="Julho 2026",'
                'OR({Tipo}="DCTFWeb - Declaração",'
                '{Tipo}="DCTFWeb - Recibo de Entrega",'
                '{Tipo}="Guia DCTFWeb/DARF"))'
            ),
        }),
    ]
    assert tuple(item.documento_id for item in itens) == (
        "recDCTFDECLARACAO",
        "recDCTFRECIBO",
        "recEXTRATO1",
        "recEXTRATO2",
        "recFGTS1",
        "recGUIADCTFWEB",
    )
    assert tuple(item.tipo_documental for item in itens) == (
        "DCTFWeb - Declaração",
        "DCTFWeb - Recibo de Entrega",
        "extrato_cliente",
        "extrato_cliente",
        "FGTS",
        "Guia DCTFWeb/DARF",
    )
    assert all(
        not hasattr(item, atributo)
        for item in itens
        for atributo in ("url", "anexo", "conteudo_bruto", "pii")
    )


# --- FonteEscopoClientesPorInventarioAirtableShadow (missão "MERGE PR #108 +
# FECHAR BLOQUEIOS REAIS DO CORREDOR LIVE V2" -- escopo histórico real) ---

def test_escopo_agrega_clientes_reais_de_extrato_e_fgts_da_folha():
    leitor = Mock()
    leitor.listar_registros.side_effect = [
        [
            {"id": "recEXTRATO1", "fields": {F_EXT_CLIENTE: ["recCLIENTE_A"]}},
            {"id": "recEXTRATO2", "fields": {F_EXT_CLIENTE: ["recCLIENTE_B"]}},
        ],
        [
            {"id": "recFGTS1", "fields": {F_FGTS_CLIENTE: ["recCLIENTE_A"]}},
            {"id": "recFGTS2", "fields": {F_FGTS_CLIENTE: ["recCLIENTE_C"]}},
        ],
    ]
    fonte = FonteEscopoClientesPorInventarioAirtableShadow(leitor)
    escopo = fonte.escopo_para_competencia(ReferenciaCanonica("COMPETENCIA", "2026-07"))

    assert leitor.listar_registros.call_args_list == [
        (( ), {
            "table_id": TABLE_EXTRATO, "fields": [F_EXT_CLIENTE],
            "filter_by_formula": '{Folha Mensal}="Julho 2026"',
        }),
        (( ), {
            "table_id": TABLE_FGTS, "fields": [F_FGTS_CLIENTE],
            "filter_by_formula": '{Folha Mensal}="Julho 2026"',
        }),
    ]
    # NUNCA consulta TABLE_GUIAS -- Guias/DCTFWeb não carrega vínculo de
    # cliente no Airtable (broadcast por desenho), nunca usado para
    # inventar escopo de cliente.
    assert leitor.listar_registros.call_count == 2
    assert escopo == (
        ReferenciaCanonica("CLIENTE", "recCLIENTE_A"),
        ReferenciaCanonica("CLIENTE", "recCLIENTE_B"),
        ReferenciaCanonica("CLIENTE", "recCLIENTE_C"),
    )


def test_escopo_deduplica_cliente_com_registro_em_extrato_e_fgts():
    leitor = Mock()
    leitor.listar_registros.side_effect = [
        [{"id": "recEXTRATO1", "fields": {F_EXT_CLIENTE: ["recCLIENTE_A"]}}],
        [{"id": "recFGTS1", "fields": {F_FGTS_CLIENTE: ["recCLIENTE_A"]}}],
    ]
    fonte = FonteEscopoClientesPorInventarioAirtableShadow(leitor)
    escopo = fonte.escopo_para_competencia(ReferenciaCanonica("COMPETENCIA", "2026-06"))
    assert escopo == (ReferenciaCanonica("CLIENTE", "recCLIENTE_A"),)


def test_escopo_competencia_sem_nenhum_registro_devolve_vazio():
    leitor = Mock()
    leitor.listar_registros.side_effect = [[], []]
    fonte = FonteEscopoClientesPorInventarioAirtableShadow(leitor)
    escopo = fonte.escopo_para_competencia(ReferenciaCanonica("COMPETENCIA", "2026-01"))
    assert escopo == ()


def test_escopo_rejeita_referencia_que_nao_e_competencia():
    import pytest

    fonte = FonteEscopoClientesPorInventarioAirtableShadow(Mock())
    with pytest.raises(ValueError):
        fonte.escopo_para_competencia(ReferenciaCanonica("CLIENTE", "x"))


def test_escopo_cliente_hoje_inativo_mas_com_registro_historico_e_encontrado():
    """Prova central: o escopo NUNCA consulta `Status` (ativo hoje) --
    um cliente com registro de Extrato numa competência histórica
    aparece no escopo daquela competência independente de qualquer
    coisa sobre o cadastro dele hoje (a fonte nem lê o campo Status)."""
    leitor = Mock()
    leitor.listar_registros.side_effect = [
        [{"id": "recEXTRATO_HIST", "fields": {F_EXT_CLIENTE: ["recCLIENTE_INATIVO_HOJE"]}}],
        [],
    ]
    fonte = FonteEscopoClientesPorInventarioAirtableShadow(leitor)
    escopo = fonte.escopo_para_competencia(ReferenciaCanonica("COMPETENCIA", "2025-01"))
    assert escopo == (ReferenciaCanonica("CLIENTE", "recCLIENTE_INATIVO_HOJE"),)
    for chamada in leitor.listar_registros.call_args_list:
        assert "Status" not in str(chamada)
