"""GET /assinatura/consulta -- somente leitura, sem efeito colateral.

Cobre exatamente os requisitos do Bloqueio 2: nunca cria, nunca dispara
Evolution, GET puro, reaproveita `_buscar_por_campo`, resposta mínima sem
PII nem URL sensível.

Gate 2 (defeito confirmado por leitura live): a rota lê `fields` por
Field ID (`F_ASS_*`), mas não pedia `returnFieldsByFieldId=true` -- o
Airtable real devolve os campos por NOME, e `status`/`link`/comprovante
voltavam sempre vazios. Os mocks anteriores devolviam os campos já por ID,
um formato que a chamada real nunca produz sem o parâmetro, e por isso
mascaravam o defeito (teste falso-positivo). Aqui o Airtable é EMULADO de
forma honesta: por padrão `fields` vem indexado por nome, e só vem por ID
quando a requisição pede `returnFieldsByFieldId=true`.
"""
import ast
import inspect
from unittest.mock import Mock, patch

import app
from magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http import (
    AdapterObrigacaoAssinaturaLegadoHttp,
)

ACAO_ID = 'a' * 64
TOKEN = 'dummy'

# Nome real do campo no Airtable -> Field ID usado pelo app.py.
_ID_POR_NOME = {
    'Status': app.F_ASS_STATUS,
    'Hash Token': app.F_ASS_HASH,
    'Documento PDF': app.F_ASS_DOCUMENTO_PDF,
    'CPF Informado': app.F_ASS_CPF_INFORMADO,
    'Tipo de Documento': 'fldTIPODOCSINTETIC',
}


def _cliente():
    app.app.testing = True
    return app.app.test_client()


def _resposta_airtable(records):
    resposta = Mock()
    resposta.ok = True
    resposta.status_code = 200
    resposta.raise_for_status = Mock()
    resposta.json.return_value = {'records': records}
    return resposta


class _AirtableEmulado:
    """Emula o GET do Airtable: `fields` por NOME por padrão; por Field ID
    só com `returnFieldsByFieldId=true` -- exatamente a semântica da API
    real (e a observada na verificação live do Gate 2)."""

    def __init__(self, *registros_por_nome):
        self._registros = registros_por_nome
        self.chamadas = []

    def __call__(self, url, headers=None, params=None, timeout=None):
        params = dict(params or {})
        self.chamadas.append((url, params))
        por_id = params.get('returnFieldsByFieldId') == 'true'
        records = [
            {
                'id': registro['id'],
                'fields': {
                    (_ID_POR_NOME[nome] if por_id else nome): valor
                    for nome, valor in registro['fields'].items()
                },
            }
            for registro in self._registros
        ]
        return _resposta_airtable(records)


def _registro(status='Pendente', anexos=None, **extras):
    return {
        'id': 'recASSINATURASINTETICA',
        'fields': {
            'Status': status, 'Hash Token': TOKEN,
            'Documento PDF': anexos if anexos is not None else [
                {'id': 'attHOLERITE', 'filename': 'Holerite - ASSINADO.pdf'},
            ],
            **extras,
        },
    }


def _consultar(emulado, query):
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=emulado), \
         patch('app.requests.post') as post, \
         patch('app._criar_registro') as criar:
        resposta = cliente.get(f'/assinatura/consulta?{query}', headers={'X-API-KEY': 'dummy'})
    post.assert_not_called()
    criar.assert_not_called()
    return resposta


# ---------------------------------------------------------------------
# Comportamentos pré-existentes (preservados)
# ---------------------------------------------------------------------

def test_options_nao_consulta_nada():
    cliente = _cliente()
    with patch('app.requests.get') as get:
        resposta = cliente.options('/assinatura/consulta')
    assert resposta.status_code == 204
    get.assert_not_called()


def test_chave_ausente_retorna_401_sem_consultar():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app.requests.get') as get:
        resposta = cliente.get(f'/assinatura/consulta?acao_execucao_id={ACAO_ID}')
    assert resposta.status_code == 401
    get.assert_not_called()


def test_exige_exatamente_um_parametro():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app.requests.get') as get:
        nenhum = cliente.get('/assinatura/consulta', headers={'X-API-KEY': 'dummy'})
        ambos = cliente.get(
            f'/assinatura/consulta?acao_execucao_id={ACAO_ID}&token_reservado={TOKEN}',
            headers={'X-API-KEY': 'dummy'},
        )
    assert nenhum.status_code == 400
    assert ambos.status_code == 400
    get.assert_not_called()


def test_obrigacao_inexistente_retorna_existe_false_sem_criar():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=_AirtableEmulado()), \
         patch('app._criar_registro') as criar, \
         patch('app._evolution_enviar_texto') as enviar_texto, \
         patch('app._evolution_enviar_documento') as enviar_documento:
        resposta = cliente.get(
            f'/assinatura/consulta?acao_execucao_id={ACAO_ID}',
            headers={'X-API-KEY': 'dummy'},
        )
    assert resposta.status_code == 200
    assert resposta.get_json() == {
        'existe': False, 'status': None, 'assinatura_id': None,
        'link': None, 'comprovante_existe': False, 'evidencia_hash': None,
    }
    criar.assert_not_called()
    enviar_texto.assert_not_called()
    enviar_documento.assert_not_called()


def test_consulta_usa_apenas_requests_get_nunca_post():
    _consultar(_AirtableEmulado(), f'acao_execucao_id={ACAO_ID}')  # asserts de POST/criação dentro


def test_falha_de_consulta_retorna_503_sem_expor_detalhe():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=RuntimeError('falha de rede sintetica')):
        resposta = cliente.get(f'/assinatura/consulta?acao_execucao_id={ACAO_ID}', headers={'X-API-KEY': 'dummy'})
    assert resposta.status_code == 503
    assert 'falha de rede sintetica' not in resposta.get_data(as_text=True)


# ---------------------------------------------------------------------
# Gate 2 -- leitura por Field ID
# ---------------------------------------------------------------------

def test_rota_pede_return_fields_by_field_id():
    emulado = _AirtableEmulado(_registro())
    _consultar(emulado, f'acao_execucao_id={ACAO_ID}')
    ((url, params),) = emulado.chamadas
    assert url.endswith(app.TABLE_ASSINATURAS)
    assert params['returnFieldsByFieldId'] == 'true'
    assert params['filterByFormula'] == f'{{{app.F_ASS_REQUEST_ID}}}="{ACAO_ID}"'


def test_obrigacao_existente_pendente_sem_comprovante():
    corpo = _consultar(_AirtableEmulado(_registro(status='Pendente')), f'acao_execucao_id={ACAO_ID}').get_json()
    assert corpo['existe'] is True
    assert corpo['status'] == 'Pendente'
    assert corpo['assinatura_id'] == 'recASSINATURASINTETICA'
    assert corpo['link'].endswith(f'/assinatura/{TOKEN}')
    assert corpo['comprovante_existe'] is False
    assert corpo['evidencia_hash'] is None


def test_obrigacao_assinada_com_comprovante_por_token():
    registro = _registro(status='Assinado', anexos=[
        {'id': 'attHOLERITE', 'filename': 'Holerite - ASSINADO.pdf'},
        {'id': 'attCOMPROVANTE', 'filename': 'Comprovante Assinatura - X.pdf',
         'url': 'https://airtable-signed-url.invalid/segredo'},
    ])
    emulado = _AirtableEmulado(registro)
    corpo = _consultar(emulado, f'token_reservado={TOKEN}').get_json()
    assert corpo['status'] == 'Assinado'
    assert corpo['comprovante_existe'] is True
    assert corpo['evidencia_hash'] == 'attCOMPROVANTE'
    ((_url, params),) = emulado.chamadas
    assert params['filterByFormula'] == f'{{{app.F_ASS_HASH}}}="{TOKEN}"'


def test_resposta_nunca_contem_url_assinada_nem_cpf():
    registro = _registro(status='Assinado', anexos=[
        {'id': 'attC', 'filename': 'Comprovante Assinatura - X.pdf',
         'url': 'https://airtable-signed-url.invalid/segredo-nao-pode-vazar'},
    ], **{'CPF Informado': '11111111111'})
    bruto = _consultar(_AirtableEmulado(registro), f'token_reservado={TOKEN}').get_data(as_text=True)
    assert 'segredo-nao-pode-vazar' not in bruto
    assert '11111111111' not in bruto


def test_resposta_por_nome_nunca_e_lida_como_se_fosse_por_id():
    """Se o Airtable devolver `fields` por nome (o que acontece sem o
    parâmetro), a leitura por Field ID não encontra nada -- este teste
    trava a semântica do emulador que desmascarou o falso-positivo."""
    emulado = _AirtableEmulado(_registro(status='Assinado'))
    resposta_por_nome = emulado('url', params={'filterByFormula': 'x'}).json()['records'][0]['fields']
    assert app.F_ASS_STATUS not in resposta_por_nome and resposta_por_nome['Status'] == 'Assinado'


# ---------------------------------------------------------------------
# Não regressão: os callers que leem por NOME continuam iguais
# ---------------------------------------------------------------------

def test_buscar_por_campo_por_padrao_nao_pede_field_ids():
    emulado = _AirtableEmulado(_registro())
    with patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=emulado):
        registro = app._buscar_por_campo(app.TABLE_ASSINATURAS, 'Hash Token', TOKEN)
    ((_url, params),) = emulado.chamadas
    assert 'returnFieldsByFieldId' not in params
    assert registro['fields']['Status'] == 'Pendente'  # continua indexado por nome


def test_somente_a_rota_de_consulta_pede_field_ids_ao_helper():
    """Todos os outros callers de `_buscar_por_campo` seguem sem
    `por_field_id` -- continuam recebendo os campos por nome."""
    arvore = ast.parse(inspect.getsource(app))
    chamadas = {}
    for funcao in ast.walk(arvore):
        if isinstance(funcao, ast.FunctionDef):
            for no in ast.walk(funcao):
                if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                        and no.func.id == '_buscar_por_campo'):
                    por_id = any(k.arg == 'por_field_id' and getattr(k.value, 'value', None) is True
                                 for k in no.keywords)
                    chamadas.setdefault(funcao.name, []).append(por_id)
    com_field_id = sorted(nome for nome, flags in chamadas.items() if any(flags))
    assert com_field_id == ['assinatura_consulta']
    assert sum(len(flags) for flags in chamadas.values()) >= 7


def test_rota_do_proxy_de_documento_continua_lendo_por_nome():
    registro = {
        'id': 'recPACOTE',
        'fields': {
            'Tipo de Documento': app.TIPO_PACOTE_HOLERITE_PONTO,
            'Documento PDF': [
                {'id': 'att1', 'filename': 'Holerite.pdf', 'url': 'https://x.invalid/1'},
                {'id': 'att2', 'filename': 'Folha.pdf', 'url': 'https://x.invalid/2'},
            ],
        },
    }
    emulado = _AirtableEmulado(registro)
    cliente = _cliente()
    with patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=emulado), \
         patch('app._carregar_documento_url', return_value=b'%PDF-sintetico'):
        resposta = cliente.get(f'/assinatura/{TOKEN}/doc/0')
    assert resposta.status_code == 200
    assert resposta.data == b'%PDF-sintetico'
    ((_url, params),) = emulado.chamadas
    assert 'returnFieldsByFieldId' not in params


# ---------------------------------------------------------------------
# Contrato de ponta a ponta com o adapter do Orquestrador
# ---------------------------------------------------------------------

def test_adapter_do_orquestrador_recebe_status_e_link_reais():
    """`AdapterObrigacaoAssinaturaLegadoHttp.consultar_por_correlacao` ->
    rota real (Flask test client) -> Airtable emulado. O observador de
    assinatura depende de `status` (Assinado/Pendente) e `tem_comprovante`
    -- antes da correção chegavam '' e False."""
    emulado = _AirtableEmulado(_registro(status='Assinado', anexos=[
        {'id': 'attCOMPROVANTE', 'filename': 'Comprovante Assinatura - X.pdf'},
    ]))
    cliente = _cliente()
    adapter = AdapterObrigacaoAssinaturaLegadoHttp(base_url='https://legado.invalid', api_key='dummy')

    def _despachar(url, headers=None, params=None, timeout=None):
        if url.startswith('https://api.airtable.com/'):
            return emulado(url, headers=headers, params=params, timeout=timeout)
        assert url == 'https://legado.invalid/assinatura/consulta'
        resposta_flask = cliente.get('/assinatura/consulta', query_string=params, headers=headers)
        resposta = Mock()
        resposta.status_code = resposta_flask.status_code
        resposta.json.return_value = resposta_flask.get_json()
        return resposta

    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('requests.get', side_effect=_despachar), \
         patch('requests.post') as post:
        obrigacao = adapter.consultar_por_correlacao(acao_execucao_id=ACAO_ID)

    post.assert_not_called()
    assert obrigacao.status == 'Assinado'
    assert obrigacao.link.endswith(f'/assinatura/{TOKEN}')
    assert obrigacao.tem_comprovante is True
    assert obrigacao.assinatura_id == 'recASSINATURASINTETICA'
