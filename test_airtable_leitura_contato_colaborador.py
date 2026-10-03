"""Testes de `LeitorAirtableSomenteLeitura.listar_funcionarios_contato`
(adapters/airtable_leitura.py) -- único método deste adapter que lê o
campo `WhatsApp` de `Funcionários`, para alimentar o bootstrap do
Contato Canônico de Colaborador V1. Nenhuma chamada de rede real --
`requests.get` é sempre um dublê."""
from __future__ import annotations

from unittest.mock import Mock, patch

from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (
    TABLE_FUNC,
    LeitorAirtableSomenteLeitura,
)
from magnata_os.documental.importacao_lote.adapters.bootstrap_contato_colaborador_airtable import (
    CandidatoFuncionarioContato,
)

_MODULO_REQUESTS = 'magnata_os.documental.importacao_lote.adapters.airtable_leitura.requests'


def test_listar_funcionarios_contato_le_so_o_campo_whatsapp_da_tabela_funcionarios():
    resposta = Mock()
    resposta.raise_for_status.return_value = None
    resposta.json.return_value = {
        'records': [
            {'id': 'recFUNC1', 'fields': {'WhatsApp': '(11) 99999-8888'}},
            {'id': 'recFUNC2', 'fields': {'WhatsApp': ''}},
            {'id': 'recFUNC3', 'fields': {}},
        ],
    }

    with patch(f'{_MODULO_REQUESTS}.get', return_value=resposta) as get:
        candidatos = LeitorAirtableSomenteLeitura('token-sintetico').listar_funcionarios_contato()

    assert candidatos == [
        CandidatoFuncionarioContato(func_id='recFUNC1', whatsapp_bruto='(11) 99999-8888'),
        CandidatoFuncionarioContato(func_id='recFUNC2', whatsapp_bruto=''),
        CandidatoFuncionarioContato(func_id='recFUNC3', whatsapp_bruto=None),
    ]
    get.assert_called_once()
    chamada = get.call_args
    assert chamada.args[0].endswith(f'/{TABLE_FUNC}')
    assert chamada.kwargs['params']['fields[]'] == ['WhatsApp']
    # Nunca usa returnFieldsByFieldId para este método -- mesmo padrão já
    # usado por `listar_funcionarios`/`listar_clientes` (campos lidos por
    # nome, não por field id).
    assert 'returnFieldsByFieldId' not in chamada.kwargs['params']


def test_listar_funcionarios_contato_percorre_paginacao():
    primeira = Mock()
    primeira.raise_for_status.return_value = None
    primeira.json.return_value = {
        'records': [{'id': 'recFUNC1', 'fields': {'WhatsApp': '11988887777'}}],
        'offset': 'pagina-2',
    }
    segunda = Mock()
    segunda.raise_for_status.return_value = None
    segunda.json.return_value = {
        'records': [{'id': 'recFUNC2', 'fields': {'WhatsApp': '11977776666'}}],
    }

    with patch(f'{_MODULO_REQUESTS}.get', side_effect=[primeira, segunda]) as get:
        candidatos = LeitorAirtableSomenteLeitura('token-sintetico').listar_funcionarios_contato()

    assert [c.func_id for c in candidatos] == ['recFUNC1', 'recFUNC2']
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs['params']['offset'] == 'pagina-2'


def test_listar_funcionarios_contato_nunca_chama_metodo_de_escrita():
    resposta = Mock()
    resposta.raise_for_status.return_value = None
    resposta.json.return_value = {'records': []}

    with (
        patch(f'{_MODULO_REQUESTS}.get', return_value=resposta),
        patch(f'{_MODULO_REQUESTS}.post') as post,
        patch(f'{_MODULO_REQUESTS}.patch') as patch_request,
        patch(f'{_MODULO_REQUESTS}.put') as put,
        patch(f'{_MODULO_REQUESTS}.delete') as delete,
    ):
        LeitorAirtableSomenteLeitura('token-sintetico').listar_funcionarios_contato()

    post.assert_not_called()
    patch_request.assert_not_called()
    put.assert_not_called()
    delete.assert_not_called()
