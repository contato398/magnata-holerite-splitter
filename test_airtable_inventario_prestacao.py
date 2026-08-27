from unittest.mock import Mock

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
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
    leitor.listar_registros.return_value = [
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
    ]

    itens = _consumir(FonteInventarioPrestacaoAirtableShadow(leitor))

    leitor.listar_registros.assert_called_once_with(
        table_id=TABLE_EXTRATO,
        fields=[F_EXT_CLIENTE],
        filter_by_formula='{Folha Mensal}="Julho 2026"',
    )
    assert tuple(item.documento_id for item in itens) == (
        "recEXTRATO1",
        "recEXTRATO2",
    )
    assert all(item.tipo_documental == "extrato_cliente" for item in itens)
    assert all(
        not hasattr(item, atributo)
        for item in itens
        for atributo in ("url", "anexo", "conteudo_bruto", "pii")
    )
