"""
Testes locais (offline, sem tocar o Airtable real) para as mudanças da v2.20:
  - AirtableError: extrai a mensagem exata retornada pela API do Airtable.
  - criar_registro_holerite: typecast=True, omite "Mês Contabilidade Vinculada"
    quando mes_cont_id é None, e aceita status="Revisão Manual".
  - _processar_documento_sem_automacao: marca itens sem handler como
    "Revisão Manual" + Pendência em vez de ficarem invisíveis.
  - _processar_holerite: sanitização ao criar holerite (payload completo
    rejeitado -> payload mínimo + "Revisão Manual").

Rodar: python test_sanitizacao_v2_20.py
"""

import json
from unittest.mock import patch, MagicMock

import app


def test_airtable_error_mensagem_com_json():
    body = json.dumps({
        "error": {
            "type": "INVALID_VALUE_FOR_COLUMN",
            "message": 'Field "Mês Contabilidade Vinculada" cannot accept the provided value.',
        }
    })
    exc = app.AirtableError(422, body, context='criar holerite (Fulano)')
    msg = str(exc)
    assert 'INVALID_VALUE_FOR_COLUMN' in msg
    assert 'Mês Contabilidade Vinculada' in msg
    assert '[criar holerite (Fulano)]' in msg
    assert 'Airtable HTTP 422' in msg
    print('OK: AirtableError extrai tipo + mensagem do JSON do Airtable')
    print('    ->', msg)


def test_airtable_error_mensagem_sem_json():
    exc = app.AirtableError(500, '<html>Internal Server Error</html>', context='create tblXXXX')
    msg = str(exc)
    assert 'Airtable HTTP 500' in msg
    assert 'Internal Server Error' in msg
    print('OK: AirtableError funciona mesmo com corpo não-JSON')
    print('    ->', msg)


def test_processar_documento_sem_automacao_dry_run():
    # Correção (Macro 6A — fechamento autônomo, achado: teste desatualizado):
    # ctx faltava a chave 'texto', que _processar_documento_sem_automacao
    # sempre exige (extrai nome/CPF do texto do PDF). A rota real
    # (/processar-fila) sempre popula 'texto' no ctx antes de chamar
    # qualquer handler — o fixture deste teste nunca foi atualizado quando
    # esse campo passou a ser obrigatório. Texto 100% sintético.
    ctx = {
        'proc_id': 'recPROC123',
        'arquivo_id': 'recARQ123',
        'nome_arquivo': 'FGTS Digital - Junho 2026.pdf',
        'tipo_documento': 'FGTS',
        'texto': 'FGTS Digital\nCompetência: 06/2026\nSem funcionário identificável neste texto sintético.',
    }
    resultado = app._processar_documento_sem_automacao(ctx, dry_run=True)
    assert resultado['status_final'] == 'Revisão Manual'
    assert resultado['pendencia'] is None
    assert resultado['acao'] == 'marcaria_para_revisao_manual'
    print('OK: dry_run de tipo sem automação (FGTS) não cria Pendência, só simula')


def test_processar_documento_sem_automacao_real():
    # Mesma correção de fixture do teste acima — ver comentário lá.
    ctx = {
        'proc_id': 'recPROC123',
        'arquivo_id': 'recARQ123',
        'nome_arquivo': 'FGTS Digital - Junho 2026.pdf',
        'tipo_documento': 'FGTS',
        'texto': 'FGTS Digital\nCompetência: 06/2026\nSem funcionário identificável neste texto sintético.',
    }
    resultado = app._processar_documento_sem_automacao(ctx, dry_run=False)
    assert resultado['status_final'] == 'Revisão Manual'
    assert resultado['acao'] == 'marcado_para_revisao_manual'
    assert resultado['pendencia']['tipo'] == 'Sem automação: FGTS'
    assert 'recPROC123' in resultado['pendencia']['observacao']
    assert 'recARQ123' in resultado['pendencia']['observacao']
    print('OK: tipo sem automação (FGTS) gera Pendência com referência ao Arquivo/Processar')


def _resposta(status_code, body_dict):
    r = MagicMock()
    r.ok = 200 <= status_code < 300
    r.status_code = status_code
    r.text = json.dumps(body_dict)
    r.json.return_value = body_dict
    return r


@patch('app._at_throttle', lambda: None)
@patch('app.requests.post')
def test_criar_registro_holerite_sem_mes_cont(mock_post):
    mock_post.return_value = _resposta(200, {'id': 'recHOL123'})

    record_id = app.criar_registro_holerite(
        'Fulano de Tal', 'recFUNC1', 'Junho 2026', '2026-06-01',
        mes_cont_id=None, valores=None,
    )

    assert record_id == 'recHOL123'
    _, kwargs = mock_post.call_args
    payload = kwargs['json']
    assert payload['typecast'] is True
    assert app.F_HOL_MES_CONT not in payload['fields'], (
        'mes_cont_id=None não deve gerar campo de link [None] (causa 422 no Airtable)'
    )
    print('OK: criar_registro_holerite com mes_cont_id=None omite o campo de link e usa typecast=True')


@patch('app._at_throttle', lambda: None)
@patch('app.requests.post')
def test_criar_registro_holerite_revisao_manual(mock_post):
    mock_post.return_value = _resposta(200, {'id': 'recHOL999'})

    app.criar_registro_holerite(
        'Fulano de Tal', 'recFUNC1', 'Junho 2026', '2026-06-01',
        mes_cont_id='recMES1', valores=None, status='Revisão Manual',
    )

    _, kwargs = mock_post.call_args
    payload = kwargs['json']
    assert payload['fields'][app.F_HOL_STATUS] == 'Revisão Manual'
    assert payload['typecast'] is True
    print('OK: criar_registro_holerite aceita status="Revisão Manual" (typecast cria a opção no Airtable)')


@patch('app._at_throttle', lambda: None)
@patch('app.anexar_pdf_holerite')
@patch('app.requests.post')
def test_processar_holerite_sanitiza_quando_payload_completo_rejeitado(mock_post, mock_anexar):
    # 1ª chamada (payload completo, com valores) -> 422
    # 2ª chamada (payload mínimo, status="Revisão Manual") -> 200
    erro_422 = _resposta(422, {
        'error': {
            'type': 'INVALID_VALUE_FOR_COLUMN',
            'message': 'Field "Total de Vencimentos" cannot accept the provided value.',
        }
    })
    ok_200 = _resposta(200, {'id': 'recHOLNOVO'})
    mock_post.side_effect = [erro_422, ok_200]
    mock_anexar.return_value = {'id': 'attXXXX'}

    ctx = {
        'proc_id': 'recPROC1',
        'arquivo_id': 'recARQ1',
        'pdf_bytes': b'%PDF-1.4 fake',
        'pdf_hash': 'hash123',
        'nome_arquivo': 'Holerite Junho 2026 - Fulano.pdf',
        # Correção (Macro 6A — fechamento autônomo, achado: teste desatualizado):
        # faltava marcador de competência ("Mês de AAAA") no texto sintético.
        # extrair_competencia_holerite() não encontrava nenhuma competência,
        # então a guarda de segurança 0b de _processar_holerite (já
        # existente, correta, não introduzida por esta rodada) roteava
        # corretamente para 'competencia_nao_detectada' — o teste nunca
        # chegava a exercitar seu objetivo real (sanitização de payload
        # 422). Com o marcador presente, o fluxo sob teste é alcançado.
        'texto': (
            'Holerite Mensalista Junho de 2026\n'
            'CPF\n123.456.789-00\n'
            'Nome do Funcionário\n12345 FULANO DE TAL\n'
            'Total de Vencimentos  Total de Descontos\n2.000,00\n'
            'Valor Líquido  2.000,00\n'
        ),
        'folha_mensal': 'Junho 2026',
        'mes_cont_id': 'recMES1',
        'data_holerite': '2026-06-01',
        'tipo_documento': 'Holerite',
        'status_atual': 'Processando',
    }

    with patch('app.buscar_funcionario_por_cpf', return_value=('recFUNC1', 'Fulano de Tal')), \
         patch('app._buscar_holerite_existente', return_value=None):
        resultado = app._processar_holerite(ctx, dry_run=False)

    assert resultado['acao'] == 'holerite_criado_revisao_manual'
    assert resultado['status_final'] == 'Concluído'
    assert resultado['detalhes']['holerite_id'] == 'recHOLNOVO'
    assert resultado['pendencia']['tipo'] == 'Holerite criado em Revisão Manual'
    assert 'INVALID_VALUE_FOR_COLUMN' in resultado['pendencia']['observacao']
    assert mock_post.call_count == 2
    print('OK: holerite com payload completo rejeitado -> recriado com payload mínimo + Revisão Manual + Pendência')


if __name__ == '__main__':
    test_airtable_error_mensagem_com_json()
    test_airtable_error_mensagem_sem_json()
    test_processar_documento_sem_automacao_dry_run()
    test_processar_documento_sem_automacao_real()
    test_criar_registro_holerite_sem_mes_cont()
    test_criar_registro_holerite_revisao_manual()
    test_processar_holerite_sanitiza_quando_payload_completo_rejeitado()
    print('\nTodos os testes passaram.')
