from unittest.mock import Mock

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
    F_FGTS_CLIENTE,
    F_GUIA_TIPO,
    TABLE_FGTS,
    TABLE_GUIAS,
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
                "id": "recDCTFGENERICO",
                "fields": {F_GUIA_TIPO: "DCTFWEB"},
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
                '{Tipo}="DCTFWeb - Recibo de Entrega"))'
            ),
        }),
    ]
    assert tuple(item.documento_id for item in itens) == (
        "recDCTFDECLARACAO",
        "recDCTFRECIBO",
        "recEXTRATO1",
        "recEXTRATO2",
        "recFGTS1",
    )
    assert tuple(item.tipo_documental for item in itens) == (
        "DCTFWeb - Declaração",
        "DCTFWeb - Recibo de Entrega",
        "extrato_cliente",
        "extrato_cliente",
        "FGTS",
    )
    assert all(
        not hasattr(item, atributo)
        for item in itens
        for atributo in ("url", "anexo", "conteudo_bruto", "pii")
    )
