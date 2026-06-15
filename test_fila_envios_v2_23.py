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


# ── _gerar_fila_envios_combinado (v2.25 — Holerite + Ponto na mesma mensagem) ──

ANEXO_HOLERITE = {'url': 'https://x/holerite_fulano.pdf', 'filename': 'holerite_fulano.pdf'}
HOLERITE_FUNC1 = {'id': 'recHOL1', 'fields': {
    'Holerite': 'Holerite Fulano',
    'Funcionário': ['recFUNC1'],
    'Folha Mensal': 'Maio 2026',
    'PDF HOLERITE': [ANEXO_HOLERITE],
}}


@patch('app._carregar_envios_pendentes', return_value=(set(), set()))
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS_PONTO))
@patch('app._at_listar_todos')
def test_gerar_fila_combinado_dry_run(mock_listar, mock_contexto, mock_pend):
    mock_listar.return_value = [HOLERITE_FUNC1]  # holerites de Maio

    resultado = app._gerar_fila_envios_combinado(folha_mensal='Maio 2026', dry_run=True)

    assert resultado['dry_run'] is True
    assert len(resultado['envios']) == 1
    envio = resultado['envios'][0]
    assert envio['canal'] == 'WhatsApp'
    assert envio['funcionario_id'] == 'recFUNC1'
    # Ordem importa: Holerite primeiro, Cartão Ponto depois
    assert envio['arquivos'] == ['holerite_fulano.pdf', 'cartao_ponto_fulano.pdf']
    assert envio['acao'] == 'criaria_envio'

    # recFUNC2 não tem WhatsApp nem holerite nem ponto -> ignorado nao_pronto
    assert any(i['funcionario_id'] == 'recFUNC2' and i['motivo'] == 'nao_pronto'
               for i in resultado['ignorados'])
    print('OK: combinado dry_run gera 1 envio WhatsApp com 2 PDFs em sequência (Holerite + Ponto)')


@patch('app._carregar_envios_pendentes', return_value=({'recFUNC1'}, set()))
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS_PONTO))
@patch('app._at_listar_todos')
def test_gerar_fila_combinado_ignora_pendente(mock_listar, mock_contexto, mock_pend):
    mock_listar.return_value = [HOLERITE_FUNC1]

    resultado = app._gerar_fila_envios_combinado(folha_mensal='Maio 2026', dry_run=True)

    assert resultado['envios'] == []
    assert any(i['funcionario_id'] == 'recFUNC1'
               and i['motivo'] == 'ja_possui_envio_combinado_pendente'
               for i in resultado['ignorados'])
    print('OK: combinado ignora colaborador com envio combinado pendente (sem duplicar)')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', return_value=(set(), set()))
@patch('app._carregar_contexto_distribuicao', return_value=(CLIENTES, LOCAIS, FUNCIONARIOS_PONTO))
@patch('app._at_listar_todos')
@patch('app._criar_registro', return_value='recENVIOCOMB')
def test_gerar_fila_combinado_cria_registro_real(mock_criar, mock_listar, mock_contexto, mock_pend):
    mock_listar.return_value = [HOLERITE_FUNC1]

    resultado = app._gerar_fila_envios_combinado(folha_mensal='Maio 2026', dry_run=False)

    assert len(resultado['envios']) == 1
    envio = resultado['envios'][0]
    assert envio['acao'] == 'envio_criado'
    assert envio['link_recibo'] == f'/recibo/{envio["hash_recibo"]}'

    _, campos = mock_criar.call_args[0]
    assert campos[app.F_ENVIO_TIPO] == app.TIPO_ENVIO_COMBINADO
    assert campos[app.F_ENVIO_CANAL] == 'WhatsApp'
    # Os 2 anexos no campo Arquivos, na ordem [Holerite, Ponto]
    assert campos[app.F_ENVIO_ARQUIVOS] == [
        {'url': 'https://x/holerite_fulano.pdf'},
        {'url': 'https://x/cartao_ponto_fulano.pdf'},
    ]
    assert app.F_ENVIO_HASH in campos
    print('OK: combinado real cria 1 envio com os 2 PDFs anexados na ordem correta + Hash Recibo')


# ── classificar_documento (v2.26 — Cartão Ponto Secullum) ─────────────────────

def test_classificar_cartao_ponto_secullum():
    texto = (
        'CARTÃO PONTO\n'
        'Período: 28/04/2026 até 28/05/2026.\n'
        'Secullum Ponto Web | Sonoda Informática\n'
        'HORÁRIO DE TRABALHO  EMPRESA: MAGNATA PORTARIA E SERVIÇOS LTDA'
    )
    tipo, conf = app.classificar_documento(texto)
    assert tipo == 'Folha de Ponto', f'esperava Folha de Ponto, veio {tipo}'
    print('OK: Cartão Ponto (Secullum) classifica como Folha de Ponto')


def test_classificar_holerite_nao_regrediu():
    texto = 'MAGNATA ... Total de Vencimentos 2.290,13 ... Valor Líquido 2.108,34'
    tipo, _ = app.classificar_documento(texto)
    assert tipo == 'Holerite', f'esperava Holerite, veio {tipo}'
    print('OK: Holerite continua classificando como Holerite')


# ── _disparar_fila_combinado (v2.28 — Evolution API) ──────────────────────────

ENVIO_COMB = {'id': 'recENV1', 'fields': {
    'Tipo': app.TIPO_ENVIO_COMBINADO,
    'Status': 'Preparando',
    'Canal': 'WhatsApp',
    'Destinatário': '5515999998888',
    'Arquivos': [
        {'url': 'https://x/hol.pdf', 'filename': 'hol.pdf'},
        {'url': 'https://x/ponto.pdf', 'filename': 'ponto.pdf'},
    ],
    'Funcionário(s) Vinculado(s)': [{'id': 'recF', 'name': 'FULANO DE TAL'}],
}}


def test_normalizar_numero_evolution():
    assert app._normalizar_numero_evolution('15 99830-0552') == '5515998300552'
    assert app._normalizar_numero_evolution('5515997061802') == '5515997061802'
    assert app._normalizar_numero_evolution('011992101916') == '5511992101916'
    assert app._normalizar_numero_evolution('') is None
    print('OK: número normalizado para o formato Evolution (55+DDD+número)')


@patch('app._at_listar_todos', return_value=[ENVIO_COMB])
def test_disparar_dry_run(mock_listar):
    res = app._disparar_fila_combinado(dry_run=True)
    assert res['dry_run'] is True
    assert res['total_enviados'] == 1
    assert res['enviados'][0]['acao'] == 'enviaria'
    assert res['enviados'][0]['destinatario'] == '5515999998888'
    print('OK: disparo dry_run lista 1 envio sem mandar nada')


@patch('app.AIRTABLE_API_KEY', 'fake-key')
@patch('app.EVOLUTION_API_KEY', 'fake-evo-key')
@patch('app._at_throttle', lambda: None)
@patch('app.requests.patch')
@patch('app.requests.post')
@patch('app._at_listar_todos', return_value=[ENVIO_COMB])
def test_disparar_envio_real_com_numero_teste(mock_listar, mock_post, mock_patch):
    mock_post.return_value = _resposta(200, {'key': {'id': 'msg1'}})
    mock_patch.return_value = _resposta(200, {'id': 'recENV1'})

    res = app._disparar_fila_combinado(dry_run=False, numero_teste='5511777776666')

    assert res['total_enviados'] == 1
    assert res['total_falhas'] == 0
    # 2 PDFs enviados via Evolution
    assert mock_post.call_count == 2
    # todos para o número de teste, como documento
    for chamada in mock_post.call_args_list:
        _, kwargs = chamada
        assert kwargs['json']['number'] == '5511777776666'
        assert kwargs['json']['mediatype'] == 'document'
    # 1º documento leva legenda; 2º não
    assert 'caption' in mock_post.call_args_list[0][1]['json']
    assert 'caption' not in mock_post.call_args_list[1][1]['json']
    # marcou Enviado
    _, kwargs_patch = mock_patch.call_args
    assert kwargs_patch['json']['fields'][app.F_ENVIO_STATUS] == 'Enviado'
    print('OK: disparo real envia 2 PDFs pela Evolution e marca "Enviado" (com número de teste)')


@patch('app.EVOLUTION_API_KEY', '')
@patch('app._at_listar_todos', return_value=[ENVIO_COMB])
def test_disparar_sem_chave_evolution_bloqueia(mock_listar):
    res = app._disparar_fila_combinado(dry_run=False)
    assert res.get('status') == 'erro'
    print('OK: disparo real sem EVOLUTION_API_KEY é bloqueado com erro claro')


# ── v2.29 — Fatiador por cliente + fila/SMTP de e-mail ───────────────────────

class _FakePage:
    def __init__(self, texto):
        self._t = texto
    def extract_text(self):
        return self._t


class _FakePdf:
    def __init__(self, textos):
        self.pages = [_FakePage(t) for t in textos]
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_extrair_cnpj():
    assert app.extrair_cnpj('CNPJ: 03.043.067/0001-00 blah') == '03043067000100'
    assert app.extrair_cnpj('sem cnpj aqui') is None
    print('OK: extrair_cnpj normaliza para 14 dígitos')


def test_normalizar_texto_busca():
    assert app._normalizar_texto_busca('Edifício  Sky  Tatuí') == 'EDIFICIO SKY TATUI'
    print('OK: _normalizar_texto_busca remove acentos/caixa/espaços')


@patch('app._at_throttle', lambda: None)
@patch('app._at_listar_todos')
@patch('app.pdfplumber')
def test_construir_mapa_cliente_cnpj_e_nome(mock_pp, mock_listar):
    mock_listar.return_value = [
        {'id': 'recCDG', 'fields': {'Nome': 'CDG CONSTRUTORA', 'CNPJ': '03.043.067/0001-00'}},
        {'id': 'recSKY', 'fields': {'Nome': 'EDIFICIO SKY TATUI', 'CNPJ': ''}},
    ]
    # pág 0 casa por CNPJ; pág 1 casa por nome; pág 2 fica sem cliente
    mock_pp.open.return_value = _FakePdf([
        'Folha ... 03.043.067/0001-00 ... total',
        'EXTRATO EDIFICIO SKY TATUI maio',
        'documento qualquer sem identificacao',
    ])
    mapa, total, sem = app.construir_mapa_cliente('/tmp/x.pdf')
    assert total == 3
    assert mapa['recCDG']['paginas'] == [0]
    assert mapa['recSKY']['paginas'] == [1]
    assert sem == [2]
    print('OK: construir_mapa_cliente casa por CNPJ e por Nome (fallback), e marca sem-cliente')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', lambda tipo: (set(), set()))
@patch('app._carregar_contexto_distribuicao', lambda: ({}, {}, {}))
@patch('app._at_listar_todos')
def test_gerar_fila_email_dry_run(mock_listar):
    def fake(table, fields=None, filtro=None):
        if table == app.TABLE_CLIENTES:
            return [{'id': 'recCLI', 'fields': {
                'Nome': 'COLASO', 'Email': 'cliente@x.com', 'Status': {'name': 'Ativo'}}}]
        return []
    mock_listar.side_effect = fake
    res = app._gerar_fila_envios_email(folha_mensal='Maio 2026', guias_ids=['recG1'], dry_run=True)
    assert res['total_envios'] == 1
    assert res['envios'][0]['acao'] == 'criaria_envio'
    assert res['envios'][0]['email'] == 'cliente@x.com'
    print('OK: _gerar_fila_envios_email (dry_run) monta 1 pacote por cliente ativo')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', lambda tipo: (set(), set()))
@patch('app._carregar_contexto_distribuicao', lambda: ({}, {}, {}))
@patch('app._at_listar_todos')
def test_gerar_fila_email_ignora_sem_email(mock_listar):
    def fake(table, fields=None, filtro=None):
        if table == app.TABLE_CLIENTES:
            return [{'id': 'recCLI', 'fields': {'Nome': 'X', 'Status': {'name': 'Ativo'}}}]
        return []
    mock_listar.side_effect = fake
    res = app._gerar_fila_envios_email(guias_ids=['recG1'], dry_run=True)
    assert res['total_envios'] == 0
    assert res['ignorados'][0]['motivos'] == ['email_ausente']
    print('OK: _gerar_fila_envios_email ignora cliente sem e-mail')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', lambda tipo: (set(), set()))
@patch('app._carregar_contexto_distribuicao', lambda: ({}, {}, {}))
@patch('app._at_listar_todos')
def test_gerar_fila_email_d2_usa_mes_anterior(mock_listar):
    # Cliente com "Exige D-2" deve puxar os documentos de Abril (D-2), não Maio.
    def fake(table, fields=None, filtro=None):
        if table == app.TABLE_EXTRATO and filtro and 'Abril 2026' in filtro:
            return [{'id': 'recEXT', 'fields': {
                'Cliente': [{'id': 'recCLI'}], 'PDF ARQUIVO': [{'url': 'http://x'}]}}]
        if table == app.TABLE_CLIENTES:
            return [{'id': 'recCLI', 'fields': {
                'Nome': 'CONDOMINIO D2', 'Email': 'd2@x.com',
                'Status': {'name': 'Ativo'}, 'Exige D-2': True}}]
        return []
    mock_listar.side_effect = fake
    res = app._gerar_fila_envios_email(
        folha_mensal='Maio 2026', folha_mensal_d2='Abril 2026', dry_run=True)
    assert res['total_envios'] == 1
    assert res['envios'][0]['folha'] == 'Abril 2026'
    assert res['envios'][0]['d2'] is True
    assert res['envios'][0]['qtd_extratos'] == 1
    print('OK: flag Exige D-2 faz o cliente receber os documentos de 2 meses atrás (D-2)')


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', lambda tipo: (set(), set()))
@patch('app._carregar_contexto_distribuicao', lambda: ({}, {}, {}))
@patch('app._at_listar_todos')
def test_gerar_fila_email_d2_sem_folha_d2_ignora(mock_listar):
    def fake(table, fields=None, filtro=None):
        if table == app.TABLE_CLIENTES:
            return [{'id': 'recCLI', 'fields': {
                'Nome': 'X', 'Email': 'c@x.com',
                'Status': {'name': 'Ativo'}, 'Exige D-2': True}}]
        return []
    mock_listar.side_effect = fake
    res = app._gerar_fila_envios_email(folha_mensal='Maio 2026', guias_ids=['recG1'], dry_run=True)
    assert res['total_envios'] == 0
    assert res['ignorados'][0]['motivo'] == 'exige_d2_sem_folha_d2_informada'
    print('OK: cliente Exige D-2 sem folha_mensal_d2 informada é ignorado com motivo claro')


@patch('app._at_throttle', lambda: None)
@patch('app._at_listar_todos')
def test_disparar_fila_email_dry_run(mock_listar):
    mock_listar.return_value = [{'id': 'recENV', 'fields': {
        'Tipo': app.TIPO_ENVIO_EMAIL_CLIENTE, 'Status': 'Preparando', 'Canal': 'E-mail',
        'Email': 'cliente@x.com', 'Cliente': [{'id': 'recCLI', 'name': 'COLASO'}],
        'PDF HOLERITES': [{'url': 'http://a/h.pdf', 'filename': 'h.pdf'}],
    }}]
    res = app._disparar_fila_email(dry_run=True)
    assert res['total_enviados'] == 1
    assert res['enviados'][0]['acao'] == 'enviaria'
    assert res['enviados'][0]['qtd_anexos'] == 1
    print('OK: _disparar_fila_email (dry_run) lista o que enviaria com anexos resolvidos')


def test_disparar_fila_email_sem_credenciais_bloqueia():
    with patch.object(app, 'EMAIL_SENDER', ''), patch.object(app, 'EMAIL_SENDER_PASSWORD', ''):
        res = app._disparar_fila_email(dry_run=False)
    assert res['status'] == 'erro'
    print('OK: disparo real de e-mail sem credenciais é bloqueado com erro claro')


def test_smtp_enviar_email_monta_mensagem():
    with patch.object(app, 'EMAIL_SENDER', 'contato@x.com'), \
         patch.object(app, 'EMAIL_SENDER_PASSWORD', 'senha-app'), \
         patch('smtplib.SMTP') as mock_smtp:
        server = mock_smtp.return_value.__enter__.return_value
        app._smtp_enviar_email('dest@y.com', 'Assunto', 'corpo', [('h.pdf', b'%PDF-1.4 x')])
        server.login.assert_called_once_with('contato@x.com', 'senha-app')
        assert server.send_message.called
    print('OK: _smtp_enviar_email faz login e envia a mensagem com anexo')


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
    test_gerar_fila_combinado_dry_run()
    test_gerar_fila_combinado_ignora_pendente()
    test_gerar_fila_combinado_cria_registro_real()
    test_classificar_cartao_ponto_secullum()
    test_classificar_holerite_nao_regrediu()
    test_normalizar_numero_evolution()
    test_disparar_dry_run()
    test_disparar_envio_real_com_numero_teste()
    test_disparar_sem_chave_evolution_bloqueia()
    test_extrair_cnpj()
    test_normalizar_texto_busca()
    test_construir_mapa_cliente_cnpj_e_nome()
    test_gerar_fila_email_dry_run()
    test_gerar_fila_email_ignora_sem_email()
    test_gerar_fila_email_d2_usa_mes_anterior()
    test_gerar_fila_email_d2_sem_folha_d2_ignora()
    test_disparar_fila_email_dry_run()
    test_disparar_fila_email_sem_credenciais_bloqueia()
    test_smtp_enviar_email_monta_mensagem()
    print('\nTodos os testes (Fase 3 - Fila de Envios) passaram.')
