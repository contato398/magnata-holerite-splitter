"""
Testes locais (offline, sem tocar o Airtable real) para a v2.23:
  - _normalizar_nome_busca / _buscar_funcionario_por_nome: matching fuzzy de
    nomes (maiúsculas/minúsculas, acentos, espaços extras, sufixos LTDA/ME).
  - _classificar_holerite_distribuicao / _gerar_fila_envios: fila de envios
    (WhatsApp para colaborador, E-mail para cliente) com Hash Recibo.
  - /recibo/<hash>: marca leitura e redireciona para o PDF.

Rodar: python test_fila_envios_v2_23.py
"""

import json
from unittest.mock import patch, MagicMock

import app


def _resposta(status_code, body_dict):
    r = MagicMock()
    r.ok = 200 <= status_code < 300
    r.status_code = status_code
    r.text = json.dumps(body_dict)
    r.json.return_value = body_dict
    return r


# ── _normalizar_nome_busca ────────────────────────────────────────────────────

def test_normalizar_nome_ignora_caixa_acentos_espacos():
    assert app._normalizar_nome_busca('joão  da  Silva') == 'JOAO DA SILVA'
    assert app._normalizar_nome_busca('JOÃO DA SILVA') == 'JOAO DA SILVA'
    print('OK: normalização ignora maiúsculas/minúsculas, acentos e espaços extras')


def test_normalizar_nome_remove_sufixos_societarios():
    assert app._normalizar_nome_busca('Magnata Serviços LTDA') == 'MAGNATA SERVICOS'
    assert app._normalizar_nome_busca('Magnata Serviços LTDA ME') == 'MAGNATA SERVICOS'
    assert app._normalizar_nome_busca('Fulano de Tal EIRELI') == 'FULANO DE TAL'
    print('OK: normalização remove sufixos LTDA/ME/EIRELI')


# ── _buscar_funcionario_por_nome (fuzzy) ─────────────────────────────────────

@patch('app._at_throttle', lambda: None)
@patch('app._at_listar_todos')
def test_buscar_funcionario_por_nome_fuzzy(mock_listar):
    mock_listar.return_value = [
        {'id': 'recFUNC1', 'fields': {'Nome Completo': 'José da Silva'}},
        {'id': 'recFUNC2', 'fields': {'Nome Completo': 'Maria Souza'}},
    ]
    func_id, nome = app._buscar_funcionario_por_nome('jose   DA SILVA')
    assert func_id == 'recFUNC1'
    assert nome == 'José da Silva'
    print('OK: _buscar_funcionario_por_nome encontra registro com nome equivalente (fuzzy)')


@patch('app._at_throttle', lambda: None)
@patch('app._at_listar_todos')
def test_buscar_funcionario_por_nome_sem_match(mock_listar):
    mock_listar.return_value = [
        {'id': 'recFUNC1', 'fields': {'Nome Completo': 'José da Silva'}},
    ]
    func_id, nome = app._buscar_funcionario_por_nome('Fulano Inexistente')
    assert func_id is None
    assert nome is None
    print('OK: _buscar_funcionario_por_nome retorna (None, None) sem correspondência')


# ── _classificar_holerite_distribuicao / _gerar_fila_envios ──────────────────

CLIENTES = {'recCLI1': {'nome': 'Cliente Exemplo', 'email': 'financeiro@cliente.com'}}
LOCAIS = {'recLOC1': {'nome': 'Posto 1', 'cliente_ids': ['recCLI1']}}
FUNCIONARIOS = {
    'recFUNC1': {'nome': 'Fulano de Tal', 'whatsapp': '+5511999999999', 'locais_ids': ['recLOC1']},
    'recFUNC2': {'nome': 'Ciclano', 'whatsapp': None, 'locais_ids': ['recLOC1']},
}


def test_classificar_pronto_ambos():
    rec = {'id': 'recHOL1', 'fields': {
        'Holerite': 'Holerite Fulano',
        'Funcionário': ['recFUNC1'],
        'Folha Mensal': 'Junho 2026',
        'PDF HOLERITE': [{'url': 'https://x/h1.pdf'}],
    }}
    c = app._classificar_holerite_distribuicao(rec, CLIENTES, LOCAIS, FUNCIONARIOS)
    assert c['situacao'] == 'pronto_ambos'
    assert c['ok_whatsapp'] and c['ok_cliente']
    print('OK: holerite com WhatsApp + Cliente/Email -> pronto_ambos')


def test_classificar_pendente_sem_whatsapp():
    rec = {'id': 'recHOL2', 'fields': {
        'Holerite': 'Holerite Ciclano',
        'Funcionário': ['recFUNC2'],
        'Folha Mensal': 'Junho 2026',
        'PDF HOLERITE': [{'url': 'https://x/h2.pdf'}],
    }}
    c = app._classificar_holerite_distribuicao(rec, CLIENTES, LOCAIS, FUNCIONARIOS)
    assert c['situacao'] == 'pronto_pacote_cliente'
    assert 'whatsapp_ausente' in c['motivos']
    print('OK: funcionário sem WhatsApp -> apenas pronto_pacote_cliente, com motivo registrado')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS))
@patch('app._at_listar_todos')
def test_gerar_fila_envios_dry_run(mock_listar, mock_contexto):
    mock_listar.return_value = [{'id': 'recHOL1', 'fields': {
        'Holerite': 'Holerite Fulano',
        'Funcionário': ['recFUNC1'],
        'Folha Mensal': 'Junho 2026',
        'PDF HOLERITE': [{'url': 'https://x/h1.pdf'}],
        'Envios de Documentos': [],
    }}]

    resultado = app._gerar_fila_envios(dry_run=True)

    assert resultado['dry_run'] is True
    assert len(resultado['envios']) == 2  # WhatsApp colaborador + E-mail cliente
    canais = {e['canal'] for e in resultado['envios']}
    assert canais == {'WhatsApp', 'E-mail'}
    assert all(e['acao'] == 'criaria_envio' for e in resultado['envios'])
    print('OK: dry_run simula 2 envios (WhatsApp + E-mail) sem gravar nada')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS))
@patch('app._at_listar_todos')
def test_gerar_fila_envios_ignora_holerite_com_envio_vinculado(mock_listar, mock_contexto):
    mock_listar.return_value = [{'id': 'recHOL1', 'fields': {
        'Holerite': 'Holerite Fulano',
        'Funcionário': ['recFUNC1'],
        'Folha Mensal': 'Junho 2026',
        'PDF HOLERITE': [{'url': 'https://x/h1.pdf'}],
        'Envios de Documentos': ['recENVIOEXISTENTE'],
    }}]

    resultado = app._gerar_fila_envios(dry_run=True)

    assert resultado['envios'] == []
    assert resultado['holerites_ignorados'][0]['motivo'] == 'ja_possui_envio_vinculado'
    print('OK: holerite com envio já vinculado é ignorado (sem duplicar fila)')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS))
@patch('app._at_listar_todos')
@patch('app._criar_registro', return_value='recENVIONOVO')
def test_gerar_fila_envios_cria_registro_real(mock_criar, mock_listar, mock_contexto):
    mock_listar.return_value = [{'id': 'recHOL1', 'fields': {
        'Holerite': 'Holerite Fulano',
        'Funcionário': ['recFUNC1'],
        'Folha Mensal': 'Junho 2026',
        'PDF HOLERITE': [{'url': 'https://x/h1.pdf'}],
        'Envios de Documentos': [],
    }}]

    resultado = app._gerar_fila_envios(dry_run=False)

    assert len(resultado['envios']) == 2
    for envio in resultado['envios']:
        assert envio['acao'] == 'envio_criado'
        assert envio['envio_id'] == 'recENVIONOVO'
        assert envio['hash_recibo']
        assert envio['link_recibo'] == f'/recibo/{envio["hash_recibo"]}'

    # Confere que o Hash Recibo foi incluído nos campos enviados ao Airtable
    for chamada in mock_criar.call_args_list:
        _, campos = chamada[0]
        assert app.F_ENVIO_HASH in campos
        assert campos[app.F_ENVIO_STATUS] == 'Preparando'
    print('OK: envio real cria registro com Hash Recibo único e link /recibo/<hash>')


# ── _classificar_folha_ponto_distribuicao / _gerar_fila_envios_folha_ponto ───

ANEXO_PONTO = {'url': 'https://x/cartao_ponto_fulano.pdf', 'filename': 'cartao_ponto_fulano.pdf'}

FUNCIONARIOS_PONTO = {
    'recFUNC1': {
        'nome': 'Fulano de Tal', 'whatsapp': '+5511999999999', 'locais_ids': ['recLOC1'],
        'pdf_folha_ponto': [ANEXO_PONTO], 'resumo_ponto': 'Período: 28/04 até 28/05...',
    },
    'recFUNC2': {
        'nome': 'Ciclano', 'whatsapp': None, 'locais_ids': ['recLOC1'],
        'pdf_folha_ponto': [], 'resumo_ponto': '',
    },
}


def test_classificar_folha_ponto_pronto_ambos():
    c = app._classificar_folha_ponto_distribuicao(FUNCIONARIOS_PONTO['recFUNC1'], CLIENTES, LOCAIS)
    assert c['situacao'] == 'pronto_ambos'
    assert c['ok_whatsapp'] and c['ok_cliente']
    assert c['pdf_anexo'] == ANEXO_PONTO
    print('OK: funcionário com Cartão Ponto + WhatsApp + Cliente/Email -> pronto_ambos')


def test_classificar_folha_ponto_sem_pdf():
    c = app._classificar_folha_ponto_distribuicao(FUNCIONARIOS_PONTO['recFUNC2'], CLIENTES, LOCAIS)
    assert c['situacao'] == 'pendente'
    assert 'pdf_folha_ponto_ausente' in c['motivos']
    print('OK: funcionário sem PDF Folha Ponto -> pendente, motivo pdf_folha_ponto_ausente')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS_PONTO))
@patch('app._at_listar_todos', return_value=[])  # Envios de Documentos vazio -> sem pendentes
def test_gerar_fila_envios_folha_ponto_dry_run(mock_listar, mock_contexto):
    resultado = app._gerar_fila_envios_folha_ponto(dry_run=True)

    assert resultado['dry_run'] is True
    canais = {e['canal'] for e in resultado['envios']}
    assert canais == {'WhatsApp', 'E-mail'}
    assert all(e['acao'] == 'criaria_envio' for e in resultado['envios'])

    envio_whats = next(e for e in resultado['envios'] if e['canal'] == 'WhatsApp')
    assert envio_whats['funcionario_id'] == 'recFUNC1'

    envio_email = next(e for e in resultado['envios'] if e['canal'] == 'E-mail')
    assert envio_email['funcionarios'] == ['Fulano de Tal']  # lote por cliente

    assert any(i['motivo'] == 'pdf_folha_ponto_ausente' for i in resultado['ignorados'])
    print('OK: dry_run da fila de Cartão Ponto simula WhatsApp individual + E-mail em lote por cliente')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS_PONTO))
@patch('app._at_listar_todos')
def test_gerar_fila_envios_folha_ponto_ignora_pendentes(mock_listar, mock_contexto):
    # Já existe um envio "Cartão Ponto Mensal" pendente para recFUNC1
    mock_listar.return_value = [{'id': 'recENVIOPEND', 'fields': {
        'Tipo': app.TIPO_ENVIO_PONTO, 'Status': 'Preparando', 'Canal': 'WhatsApp',
        'Funcionário(s) Vinculado(s)': ['recFUNC1'],
    }}]

    resultado = app._gerar_fila_envios_folha_ponto(dry_run=True)

    assert resultado['envios'] == []
    assert any(
        i['funcionario_id'] == 'recFUNC1' and i['motivo'] == 'ja_possui_envio_ponto_pendente'
        for i in resultado['ignorados']
    )
    print('OK: funcionário com envio de Cartão Ponto pendente é ignorado (sem duplicar)')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS_PONTO))
@patch('app._at_listar_todos', return_value=[])
@patch('app._criar_registro', return_value='recENVIOPONTO')
def test_gerar_fila_envios_folha_ponto_cria_registro_real(mock_criar, mock_listar, mock_contexto):
    resultado = app._gerar_fila_envios_folha_ponto(dry_run=False)

    assert len(resultado['envios']) == 2
    for envio in resultado['envios']:
        assert envio['acao'] == 'envio_criado'
        assert envio['hash_recibo']
        assert envio['link_recibo'] == f'/recibo/{envio["hash_recibo"]}'

    for chamada in mock_criar.call_args_list:
        _, campos = chamada[0]
        assert campos[app.F_ENVIO_TIPO] == app.TIPO_ENVIO_PONTO
        assert app.F_ENVIO_ARQUIVOS in campos
        assert app.F_ENVIO_HASH in campos
    print('OK: envio real (Cartão Ponto) cria WhatsApp individual + E-mail em lote, com anexos e Hash Recibo')


# ── /recibo/<hash> ────────────────────────────────────────────────────────────

@patch('app.AIRTABLE_API_KEY', 'fake-key-para-teste')
@patch('app._at_throttle', lambda: None)
@patch('app.requests.get')
@patch('app.requests.patch')
@patch('app._buscar_por_campo')
def test_recibo_marca_lido_e_redireciona(mock_buscar, mock_patch, mock_get, ):
    mock_buscar.return_value = {
        'id': 'recENVIO1',
        'fields': {'Hash Recibo': 'abc123', 'Holerites': ['recHOL1']},
    }
    mock_patch.return_value = _resposta(200, {'id': 'recENVIO1'})
    mock_get.return_value = _resposta(200, {'fields': {'PDF HOLERITE': [{'url': 'https://x/h1.pdf'}]}})

    with app.app.test_request_context():
        resposta = app.recibo_leitura('abc123')

    assert resposta.status_code == 302
    assert resposta.headers['Location'] == 'https://x/h1.pdf'
    # Confirma que o PATCH marcou "Recibo Lido em" e Status="Lido"
    _, kwargs = mock_patch.call_args
    campos_patch = kwargs['json']['fields']
    assert app.F_ENVIO_LIDO_EM in campos_patch
    assert campos_patch[app.F_ENVIO_STATUS] == 'Lido'
    print('OK: /recibo/<hash> marca leitura e redireciona (302) para o PDF do Holerite')


@patch('app.AIRTABLE_API_KEY', 'fake-key-para-teste')
@patch('app._at_throttle', lambda: None)
@patch('app._buscar_por_campo', return_value=None)
def test_recibo_hash_invalido(mock_buscar):
    with app.app.test_request_context():
        resposta, status = app.recibo_leitura('hash-invalido')
    assert status == 404
    print('OK: /recibo/<hash> com hash inválido -> 404')


@patch('app.AIRTABLE_API_KEY', 'fake-key-para-teste')
@patch('app._at_throttle', lambda: None)
@patch('app.requests.patch')
@patch('app._buscar_por_campo')
def test_recibo_redireciona_anexo_direto_cartao_ponto(mock_buscar, mock_patch):
    mock_buscar.return_value = {
        'id': 'recENVIOPONTO',
        'fields': {
            'Hash Recibo': 'abc123',
            'Arquivos': [{'url': 'https://x/cartao_ponto_fulano.pdf'}],
        },
    }
    mock_patch.return_value = _resposta(200, {'id': 'recENVIOPONTO'})

    with app.app.test_request_context():
        resposta = app.recibo_leitura('abc123')

    assert resposta.status_code == 302
    assert resposta.headers['Location'] == 'https://x/cartao_ponto_fulano.pdf'
    print('OK: /recibo/<hash> de Cartão Ponto redireciona via anexo direto (campo "Arquivos")')


@patch('app.AIRTABLE_API_KEY', 'fake-key-para-teste')
@patch('app._at_throttle', lambda: None)
@patch('app.requests.get')
@patch('app.requests.patch')
@patch('app._buscar_por_campo')
def test_recibo_ja_lido_nao_repete_patch(mock_buscar, mock_patch, mock_get):
    mock_buscar.return_value = {
        'id': 'recENVIO1',
        'fields': {'Hash Recibo': 'abc123', 'Holerites': ['recHOL1'], 'Recibo Lido em': '2026-06-10T10:00:00'},
    }
    mock_get.return_value = _resposta(200, {'fields': {'PDF HOLERITE': [{'url': 'https://x/h1.pdf'}]}})

    with app.app.test_request_context():
        resposta = app.recibo_leitura('abc123')

    assert resposta.status_code == 302
    mock_patch.assert_not_called()
    print('OK: /recibo/<hash> já lido anteriormente -> não repete o PATCH, apenas redireciona')


# ── _normalizar_telefone_br / /normalizar-whatsapp ────────────────────────────

def test_normalizar_telefone_adiciona_55():
    assert app._normalizar_telefone_br('11999998888') == '5511999998888'
    assert app._normalizar_telefone_br('(11) 99999-8888') == '5511999998888'
    assert app._normalizar_telefone_br('1199998888') == '551199998888'
    print('OK: normalização adiciona DDI 55 a números sem DDI')


def test_normalizar_telefone_ja_normalizado_retorna_none():
    assert app._normalizar_telefone_br('5511999998888') == None
    assert app._normalizar_telefone_br('+55 11 99999-8888') == None
    print('OK: número já normalizado retorna None (sem alteração)')


def test_normalizar_telefone_vazio_ou_invalido_retorna_none():
    assert app._normalizar_telefone_br('') == None
    assert app._normalizar_telefone_br(None) == None
    assert app._normalizar_telefone_br('123') == None
    print('OK: número vazio/inválido retorna None')


FUNCIONARIOS_WHATS = [
    {'id': 'recFUNC1', 'fields': {'Nome Completo': 'Fulano de Tal', 'WhatsApp': '11999998888'}},
    {'id': 'recFUNC2', 'fields': {'Nome Completo': 'Beltrano', 'WhatsApp': '5521988887777'}},
    {'id': 'recFUNC3', 'fields': {'Nome Completo': 'Ciclano', 'WhatsApp': None}},
]


@patch('app._at_listar_todos')
def test_normalizar_whatsapp_dry_run(mock_listar):
    mock_listar.return_value = FUNCIONARIOS_WHATS

    resultado = app._normalizar_whatsapp_funcionarios(dry_run=True)

    assert resultado['total_funcionarios_atualizados'] == 1
    item = resultado['atualizados'][0]
    assert item['funcionario_id'] == 'recFUNC1'
    assert item['whatsapp_antes'] == '11999998888'
    assert item['whatsapp_depois'] == '5511999998888'
    assert item['acao'] == 'atualizaria'

    motivos = {i['funcionario_id']: i['motivo'] for i in resultado['ignorados']}
    assert motivos['recFUNC2'] == 'ja_normalizado_ou_invalido'
    assert motivos['recFUNC3'] == 'whatsapp_ausente'
    print('OK: /normalizar-whatsapp dry_run identifica apenas o número não normalizado')


@patch('app._at_throttle', lambda: None)
@patch('app.requests.patch')
@patch('app._at_listar_todos')
def test_normalizar_whatsapp_cria_patch_real(mock_listar, mock_patch):
    mock_listar.return_value = FUNCIONARIOS_WHATS
    mock_patch.return_value = _resposta(200, {'id': 'recFUNC1', 'fields': {}})

    resultado = app._normalizar_whatsapp_funcionarios(dry_run=False)

    assert resultado['total_funcionarios_atualizados'] == 1
    assert resultado['atualizados'][0]['acao'] == 'atualizado'
    mock_patch.assert_called_once()
    args, kwargs = mock_patch.call_args
    assert kwargs['json']['fields']['WhatsApp'] == '5511999998888'
    print('OK: /normalizar-whatsapp grava o número normalizado via PATCH')


if __name__ == '__main__':
    test_normalizar_nome_ignora_caixa_acentos_espacos()
    test_normalizar_nome_remove_sufixos_societarios()
    test_buscar_funcionario_por_nome_fuzzy()
    test_buscar_funcionario_por_nome_sem_match()
    test_classificar_pronto_ambos()
    test_classificar_pendente_sem_whatsapp()
    test_gerar_fila_envios_dry_run()
    test_gerar_fila_envios_ignora_holerite_com_envio_vinculado()
    test_gerar_fila_envios_cria_registro_real()
    test_classificar_folha_ponto_pronto_ambos()
    test_classificar_folha_ponto_sem_pdf()
    test_gerar_fila_envios_folha_ponto_dry_run()
    test_gerar_fila_envios_folha_ponto_ignora_pendentes()
    test_gerar_fila_envios_folha_ponto_cria_registro_real()
    test_recibo_marca_lido_e_redireciona()
    test_recibo_hash_invalido()
    test_recibo_redireciona_anexo_direto_cartao_ponto()
    test_recibo_ja_lido_nao_repete_patch()
    test_normalizar_telefone_adiciona_55()
    test_normalizar_telefone_ja_normalizado_retorna_none()
    test_normalizar_telefone_vazio_ou_invalido_retorna_none()
    test_normalizar_whatsapp_dry_run()
    test_normalizar_whatsapp_cria_patch_real()
    print('\nTodos os testes (Fase 3 - Fila de Envios) passaram.')
