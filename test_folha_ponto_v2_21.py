"""
Testes locais (offline, sem tocar o Airtable real) para a v2.21:
  - _processar_folha_ponto: identifica o funcionário pelo CPF no PDF e anexa
    o arquivo ao campo "PDF Folha Ponto" (prontuário) em Funcionários
    (Fase 1 da automação de Folha de Ponto — sem extração de horários ainda).

Rodar: python test_folha_ponto_v2_21.py
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


CTX_BASE = {
    'proc_id': 'recPROC1',
    'arquivo_id': 'recARQ1',
    'pdf_bytes': b'%PDF-1.4 fake',
    'pdf_hash': 'hash123',
    'nome_arquivo': 'Folha de Ponto Junho 2026 - Fulano.pdf',
    'texto': 'CPF\n123.456.789-00\nFolha de Ponto - Junho 2026\n',
    'folha_mensal': 'Junho 2026',
    'mes_cont_id': 'recMES1',
    'data_holerite': '2026-06-01',
    'tipo_documento': 'Folha de Ponto',
    'status_atual': 'Processando',
}


@patch('app._at_throttle', lambda: None)
def test_funcionario_nao_encontrado_dry_run():
    with patch('app.buscar_funcionario_por_cpf', return_value=(None, None)):
        resultado = app._processar_folha_ponto(CTX_BASE, dry_run=True)

    assert resultado['status_final'] == 'Revisão Manual'
    assert resultado['acao'] == 'funcionario_nao_encontrado'
    assert resultado['pendencia'] is None
    print('OK: dry_run sem funcionário encontrado -> Revisão Manual sem Pendência')


@patch('app._at_throttle', lambda: None)
def test_funcionario_nao_encontrado_real():
    with patch('app.buscar_funcionario_por_cpf', return_value=(None, None)):
        resultado = app._processar_folha_ponto(CTX_BASE, dry_run=False)

    assert resultado['status_final'] == 'Revisão Manual'
    assert resultado['pendencia']['tipo'] == 'Funcionário não encontrado (Folha de Ponto)'
    assert 'recPROC1' in resultado['pendencia']['observacao']
    print('OK: funcionário não encontrado (real) -> Revisão Manual + Pendência')


@patch('app._at_throttle', lambda: None)
@patch('app.requests.get')
@patch('app.buscar_funcionario_por_cpf', return_value=('recFUNC1', 'Fulano de Tal'))
def test_anexa_folha_ponto_novo_arquivo(mock_busca, mock_get):
    # GET do registro do funcionário -> sem anexos ainda
    mock_get.return_value = _resposta(200, {'fields': {app.F_FUNC_PDF_FOLHA: []}})

    with patch('app._anexar_attachment', return_value={'id': 'attXXXX'}) as mock_anexar:
        resultado = app._processar_folha_ponto(CTX_BASE, dry_run=False)

    assert resultado['acao'] == 'folha_ponto_anexada_ao_prontuario'
    assert resultado['status_final'] == 'Concluído'
    assert resultado['pendencia'] is None
    mock_anexar.assert_called_once_with(
        app.TABLE_FUNC, 'recFUNC1', app.F_FUNC_PDF_FOLHA, CTX_BASE['pdf_bytes'], CTX_BASE['nome_arquivo'],
    )
    print('OK: funcionário encontrado + arquivo novo -> anexado ao prontuário')


@patch('app._at_throttle', lambda: None)
@patch('app.requests.get')
@patch('app.buscar_funcionario_por_cpf', return_value=('recFUNC1', 'Fulano de Tal'))
def test_anexo_identico_nao_duplica(mock_busca, mock_get):
    # GET do registro do funcionário -> já existe anexo com mesmo nome
    mock_get.side_effect = [
        _resposta(200, {'fields': {app.F_FUNC_PDF_FOLHA: [
            {'filename': CTX_BASE['nome_arquivo'], 'url': 'https://example.com/a.pdf'},
        ]}}),
        MagicMock(content=CTX_BASE['pdf_bytes']),
    ]

    with patch('app.hashlib.sha256') as mock_sha:
        mock_sha.return_value.hexdigest.return_value = CTX_BASE['pdf_hash']
        with patch('app._anexar_attachment') as mock_anexar:
            resultado = app._processar_folha_ponto(CTX_BASE, dry_run=False)

    assert resultado['acao'] == 'folha_ponto_ja_anexada'
    assert resultado['status_final'] == 'Concluído'
    mock_anexar.assert_not_called()
    print('OK: anexo idêntico já existente -> não duplica')


CTX_CARTAO_PONTO = dict(CTX_BASE, texto=(
    'CPF: ADMISSÃO:\n326.052.678-14\n'
    'Período: 28/04/2026 até 28/05/2026\n'
    '28/04/26 - Ter - C2 FOLGA FOLGA FOLGA FOLGA FOLGA FOLGA\n'
    '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
))


@patch('app._at_throttle', lambda: None)
@patch('app.requests.get')
@patch('app.buscar_funcionario_por_cpf', return_value=('recFUNC1', 'Fulano de Tal'))
def test_atualiza_resumo_cartao_ponto_quando_ha_dias(mock_busca, mock_get):
    mock_get.return_value = _resposta(200, {'fields': {app.F_FUNC_PDF_FOLHA: []}})

    with patch('app._anexar_attachment', return_value={'id': 'attXXXX'}):
        with patch('app._atualizar_resumo_ponto_funcionario') as mock_resumo:
            resultado = app._processar_folha_ponto(CTX_CARTAO_PONTO, dry_run=False)

    assert resultado['detalhes']['cartao_ponto_dias_extraidos'] == 2
    mock_resumo.assert_called_once()
    func_id_chamado, texto_resumo = mock_resumo.call_args[0]
    assert func_id_chamado == 'recFUNC1'
    assert 'FOLGA' in texto_resumo
    assert '18:56' in texto_resumo
    print('OK: dias extraídos do Cartão Ponto -> resumo atualizado no prontuário')


@patch('app._at_throttle', lambda: None)
@patch('app.requests.get')
@patch('app.buscar_funcionario_por_cpf', return_value=('recFUNC1', 'Fulano de Tal'))
def test_dry_run_nao_atualiza_resumo(mock_busca, mock_get):
    mock_get.return_value = _resposta(200, {'fields': {app.F_FUNC_PDF_FOLHA: []}})

    with patch('app._atualizar_resumo_ponto_funcionario') as mock_resumo:
        resultado = app._processar_folha_ponto(CTX_CARTAO_PONTO, dry_run=True)

    assert resultado['detalhes']['cartao_ponto_dias_extraidos'] == 2
    mock_resumo.assert_not_called()
    print('OK: dry_run não grava resumo do Cartão Ponto (apenas simula)')


if __name__ == '__main__':
    test_funcionario_nao_encontrado_dry_run()
    test_funcionario_nao_encontrado_real()
    test_anexa_folha_ponto_novo_arquivo()
    test_anexo_identico_nao_duplica()
    test_atualiza_resumo_cartao_ponto_quando_ha_dias()
    test_dry_run_nao_atualiza_resumo()
    print('\nTodos os testes passaram.')
