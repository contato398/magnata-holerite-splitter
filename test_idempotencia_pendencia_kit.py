"""
Macro 6A — Idempotência da Pendência de rejeição de identidade do Kit de
Admissão (último fechamento).

Achado do Ultrareview: reprocessar o mesmo documento rejeitado pelo
controle de identidade do kit (ver test_kit_admissao_identidade.py) podia
criar uma Pendência duplicada a cada reprocessamento, porque
`_criar_pendencia` era chamada incondicionalmente, sem nenhuma checagem
prévia.

Correção: chave determinística (funcionário-alvo + processo de origem +
arquivo rejeitado + categoria da rejeição — nunca CPF/nome/texto de PDF),
usada para buscar uma Pendência já existente ANTES de criar. Se existir,
reaproveita o mesmo pendencia_id (atualização não destrutiva, só o
carimbo de data); se não existir, cria uma nova. A busca nunca usa
filterByFormula (nome de exibição real do campo não é conhecido com
segurança nesta sessão) — pagina por Field IDs e compara no lado do
Python.

100% dado sintético -- nenhum CPF/nome real em nenhum lugar deste arquivo.
"""
from unittest.mock import Mock, patch

import pytest

from app import (
    F_PEND_DATA,
    F_PEND_NOME,
    _buscar_pendencia_kit_identidade_existente,
    _chave_pendencia_kit_identidade,
    _criar_ou_reaproveitar_pendencia_kit_identidade,
    _marcar_pendencia_kit_identidade_vista_novamente,
    _montar_e_disparar_kit_admissao,
)


def _resposta(json_dict, ok=True):
    r = Mock()
    r.ok = ok
    r.json.return_value = json_dict
    return r


# ── _chave_pendencia_kit_identidade — determinismo e distinguibilidade ──

def test_mesma_combinacao_produz_sempre_a_mesma_chave():
    chave1 = _chave_pendencia_kit_identidade('recFUNC1', 'procA', 'arqA', 'cpf_divergente')
    chave2 = _chave_pendencia_kit_identidade('recFUNC1', 'procA', 'arqA', 'cpf_divergente')
    assert chave1 == chave2


def test_categorias_diferentes_permanecem_distinguiveis():
    """'Categorias diferentes permanecem distinguíveis': mesmo
    funcionário/processo/arquivo, motivo diferente -> chave diferente."""
    chave_divergente = _chave_pendencia_kit_identidade('recFUNC1', 'procA', 'arqA', 'cpf_divergente')
    chave_ausente = _chave_pendencia_kit_identidade('recFUNC1', 'procA', 'arqA', 'cpf_candidato_ausente')
    assert chave_divergente != chave_ausente


def test_documentos_diferentes_permanecem_distinguiveis():
    """'Documentos diferentes permanecem distinguíveis': mesmo
    funcionário/categoria, arquivo/processo diferente -> chave diferente."""
    chave_doc_a = _chave_pendencia_kit_identidade('recFUNC1', 'procA', 'arqA', 'cpf_divergente')
    chave_doc_b = _chave_pendencia_kit_identidade('recFUNC1', 'procB', 'arqB', 'cpf_divergente')
    assert chave_doc_a != chave_doc_b


def test_funcionarios_alvo_diferentes_permanecem_distinguiveis():
    """'Funcionários-alvo diferentes permanecem distinguíveis': mesmo
    documento candidato, funcionário-alvo diferente -> chave diferente
    (ex.: o mesmo arquivo suspeito avaliado contra dois kits distintos)."""
    chave_func_1 = _chave_pendencia_kit_identidade('recFUNC1', 'procA', 'arqA', 'cpf_divergente')
    chave_func_2 = _chave_pendencia_kit_identidade('recFUNC2', 'procA', 'arqA', 'cpf_divergente')
    assert chave_func_1 != chave_func_2


def test_chave_nunca_contem_cpf_ou_nome():
    """A chave só é construída a partir de IDs técnicos e da categoria --
    nunca recebe CPF ou nome como parâmetro (prova estrutural: a
    assinatura da função não tem parâmetro nenhum desse tipo)."""
    import inspect
    parametros = list(inspect.signature(_chave_pendencia_kit_identidade).parameters.keys())
    assert parametros == ['func_id', 'proc_id', 'arquivo_id', 'motivo_sanitizado']
    assert 'cpf' not in ' '.join(parametros).lower()
    assert 'nome' not in ' '.join(parametros).lower()


# ── _buscar_pendencia_kit_identidade_existente ───────────────────────────

def test_busca_nunca_usa_filterbyformula():
    """Decisão de desenho documentada: sem conector Airtable para
    confirmar o nome de exibição real do campo, a busca nunca arrisca uma
    fórmula com nome errado -- pagina e compara no lado do Python."""
    with patch('app.requests.get', return_value=_resposta({'records': []})) as mock_get, \
         patch('app._at_throttle'):
        _buscar_pendencia_kit_identidade_existente('chave-qualquer')

    for chamada in mock_get.call_args_list:
        params = chamada.kwargs.get('params', {})
        assert 'filterByFormula' not in params
        assert params.get('returnFieldsByFieldId') == 'true'


def test_busca_encontra_pendencia_com_chave_identica():
    resp = _resposta({'records': [
        {'id': 'recPEND_EXISTENTE', 'fields': {F_PEND_NOME: 'chave-alvo'}},
        {'id': 'recPEND_OUTRA', 'fields': {F_PEND_NOME: 'chave-diferente'}},
    ]})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle'):
        encontrada = _buscar_pendencia_kit_identidade_existente('chave-alvo')
    assert encontrada == 'recPEND_EXISTENTE'


def test_busca_sem_pendencia_correspondente_devolve_none():
    resp = _resposta({'records': [
        {'id': 'recPEND_OUTRA', 'fields': {F_PEND_NOME: 'chave-diferente'}},
    ]})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle'):
        encontrada = _buscar_pendencia_kit_identidade_existente('chave-alvo')
    assert encontrada is None


def test_busca_pagina_ate_encontrar():
    resp_pagina_1 = _resposta({
        'records': [{'id': 'recPEND_OUTRA', 'fields': {F_PEND_NOME: 'chave-diferente'}}],
        'offset': 'offsetFAKE',
    })
    resp_pagina_2 = _resposta({
        'records': [{'id': 'recPEND_ALVO', 'fields': {F_PEND_NOME: 'chave-alvo'}}],
    })
    with patch('app.requests.get', side_effect=[resp_pagina_1, resp_pagina_2]), \
         patch('app._at_throttle'):
        encontrada = _buscar_pendencia_kit_identidade_existente('chave-alvo')
    assert encontrada == 'recPEND_ALVO'


def test_falha_de_rede_na_busca_devolve_none_nao_levanta():
    """Falha na consulta nunca derruba o chamador -- devolve None
    (tratado como 'não encontrada', segue para tentar criar)."""
    with patch('app.requests.get', side_effect=Exception('timeout sintetico')), \
         patch('app._at_throttle'):
        encontrada = _buscar_pendencia_kit_identidade_existente('chave-alvo')
    assert encontrada is None


def test_falha_http_na_busca_devolve_none_nao_levanta():
    with patch('app.requests.get', return_value=_resposta({}, ok=False)), \
         patch('app._at_throttle'):
        encontrada = _buscar_pendencia_kit_identidade_existente('chave-alvo')
    assert encontrada is None


def test_concorrencia_duas_pendencias_com_mesma_chave_pega_a_primeira_deterministicamente():
    """'Concorrência ou resposta duplicada da API não resulta em
    associação incorreta': se, por qualquer motivo (corrida antiga,
    antes desta correção), houver DUAS Pendências com a mesma chave, a
    busca nunca tenta mesclar nem associa a rejeição à Pendência errada
    -- pega a primeira encontrada, de forma determinística e estável."""
    resp = _resposta({'records': [
        {'id': 'recPEND_PRIMEIRA', 'fields': {F_PEND_NOME: 'chave-duplicada'}},
        {'id': 'recPEND_SEGUNDA', 'fields': {F_PEND_NOME: 'chave-duplicada'}},
    ]})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle'):
        encontrada = _buscar_pendencia_kit_identidade_existente('chave-duplicada')
    assert encontrada == 'recPEND_PRIMEIRA'


# ── _marcar_pendencia_kit_identidade_vista_novamente — não destrutivo ───

def test_marcar_vista_novamente_so_atualiza_o_carimbo_de_data():
    with patch('app.requests.patch', return_value=_resposta({'id': 'recPEND1'})) as mock_patch, \
         patch('app._at_throttle'):
        ok = _marcar_pendencia_kit_identidade_vista_novamente('recPEND1')

    assert ok is True
    payload = mock_patch.call_args.kwargs['json']['fields']
    # SÓ o carimbo de data -- nunca Status, Tipo, Nome ou Observação
    assert list(payload.keys()) == [F_PEND_DATA]


def test_marcar_vista_novamente_falha_devolve_false_nao_levanta():
    with patch('app.requests.patch', side_effect=Exception('erro sintetico')), \
         patch('app._at_throttle'):
        ok = _marcar_pendencia_kit_identidade_vista_novamente('recPEND1')
    assert ok is False


# ── _criar_ou_reaproveitar_pendencia_kit_identidade — orquestração ──────

def test_primeira_rejeicao_cria_pendencia():
    """'Primeira rejeição cria uma Pendência.'"""
    with patch('app._buscar_pendencia_kit_identidade_existente', return_value=None), \
         patch('app._criar_pendencia', return_value='recPENDNOVA') as mock_criar, \
         patch('app._marcar_pendencia_kit_identidade_vista_novamente') as mock_marcar:
        resultado = _criar_ou_reaproveitar_pendencia_kit_identidade(
            'recFUNC1', 'procA', 'arqA', 'cpf_divergente')

    assert resultado == {'pendencia_id': 'recPENDNOVA', 'reaproveitada': False}
    mock_criar.assert_called_once()
    mock_marcar.assert_not_called()
    # a chave determinística foi passada como `nome` -- vira o rótulo real
    assert mock_criar.call_args.kwargs['nome'] == _chave_pendencia_kit_identidade(
        'recFUNC1', 'procA', 'arqA', 'cpf_divergente')


def test_reprocessamento_identico_nao_cria_outra():
    """'Reprocessamento idêntico não cria outra': quando já existe uma
    Pendência com a mesma chave, reaproveita o mesmo id -- nunca chama
    _criar_pendencia de novo."""
    with patch('app._buscar_pendencia_kit_identidade_existente', return_value='recPENDEXISTENTE'), \
         patch('app._criar_pendencia') as mock_criar, \
         patch('app._marcar_pendencia_kit_identidade_vista_novamente', return_value=True) as mock_marcar:
        resultado = _criar_ou_reaproveitar_pendencia_kit_identidade(
            'recFUNC1', 'procA', 'arqA', 'cpf_divergente')

    assert resultado == {'pendencia_id': 'recPENDEXISTENTE', 'reaproveitada': True}
    mock_criar.assert_not_called()
    mock_marcar.assert_called_once_with('recPENDEXISTENTE')


def test_falha_na_criacao_devolve_pendencia_id_none_nao_levanta():
    """'Falha na consulta/criação não derruba os demais documentos do
    kit': erro ao criar é capturado, devolve pendencia_id=None em vez de
    propagar a exceção."""
    with patch('app._buscar_pendencia_kit_identidade_existente', return_value=None), \
         patch('app._criar_pendencia', side_effect=Exception('erro sintetico de rede')):
        resultado = _criar_ou_reaproveitar_pendencia_kit_identidade(
            'recFUNC1', 'procA', 'arqA', 'cpf_divergente')

    assert resultado == {'pendencia_id': None, 'reaproveitada': False}


def test_log_de_falha_na_criacao_nunca_vaza_cpf_ou_nome(caplog):
    import logging
    with patch('app._buscar_pendencia_kit_identidade_existente', return_value=None), \
         patch('app._criar_pendencia', side_effect=Exception('erro sintetico')), \
         caplog.at_level(logging.WARNING):
        _criar_ou_reaproveitar_pendencia_kit_identidade(
            'recFUNC1', 'procA', 'arqA', 'cpf_divergente')

    mensagens = ' '.join(r.getMessage() for r in caplog.records)
    assert '111.111.111-11' not in mensagens
    assert 'FULANO' not in mensagens.upper()
    # só IDs técnicos aparecem
    assert 'procA' in mensagens
    assert 'arqA' in mensagens


# ── Integração com _montar_e_disparar_kit_admissao ───────────────────────

def _ctx_ficha_sintetica():
    return {
        'proc_id': 'procFICHA', 'arquivo_id': 'arqFICHA',
        'pdf_bytes': b'ficha-bytes', 'texto': 'Ficha de Registro de Empregado sintetica',
        'email_savian_id': 'recEmailFAKE1',
    }


def test_dry_run_nunca_consulta_nem_cria_pendencia_externa():
    """'Dry-run não consulta nem cria Pendência externa': _montar_e_
    disparar_kit_admissao devolve cedo em dry_run=True, antes de qualquer
    chamada de rede -- nem busca, nem criação de Pendência."""
    ctx = _ctx_ficha_sintetica()
    with patch('app._buscar_pendencia_kit_identidade_existente') as mock_buscar, \
         patch('app._criar_pendencia') as mock_criar, \
         patch('app.requests.get') as mock_get:
        resultado = _montar_e_disparar_kit_admissao(ctx, 'recFUNCALVO', dry_run=True)

    mock_buscar.assert_not_called()
    mock_criar.assert_not_called()
    mock_get.assert_not_called()
    assert resultado['kit_montado'] is False


def test_kit_reprocessado_reaproveita_pendencia_existente_nunca_duplica():
    """Teste de integração ponta a ponta: o mesmo documento candidato
    rejeitado, processado duas vezes (simulando reprocessamento do
    mesmo Processar Arquivos), nunca cria uma segunda Pendência -- a
    segunda chamada encontra e reaproveita a Pendência da primeira."""
    ctx = _ctx_ficha_sintetica()
    func_id = 'recFUNCALVO'
    irmao = {'proc_id': 'procREJEITADO', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqREJEITADO'}

    from app import F_FUNC_CPF, F_FUNC_KIT_CONSOLIDADO
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})

    # Simula um "banco" de Pendências em memória entre as duas execuções.
    pendencias_criadas = {}

    def criar_pendencia_fake(arquivo_id, tipo_problema, observacao, nome=None):
        rec_id = f'recPEND_{len(pendencias_criadas) + 1}'
        pendencias_criadas[nome] = rec_id
        return rec_id

    def buscar_existente_fake(chave):
        return pendencias_criadas.get(chave)

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[irmao]), \
         patch('app._baixar_e_classificar_papel_kit',
               return_value=('contrato', b'contrato-bytes', 'CPF: 222.222.222-22')), \
         patch('app._vincular_documento_ao_funcionario'), \
         patch('app._criar_pendencia', side_effect=criar_pendencia_fake), \
         patch('app._buscar_pendencia_kit_identidade_existente', side_effect=buscar_existente_fake), \
         patch('app._marcar_pendencia_kit_identidade_vista_novamente', return_value=True) as mock_marcar, \
         patch('app._gerar_pdf_declaracao_renuncia_vt', return_value=b'vt-fake'), \
         patch('app._montar_pdf_consolidado_kit_admissao', return_value=b'kit-consolidado'), \
         patch('app._anexar_attachment'), \
         patch('app.requests.post', return_value=_resposta({'id': 'recArquivoKitNovo'})), \
         patch('app._gerar_assinatura_core'), \
         patch('app._atualizar_status_processar'):
        resultado_1 = _montar_e_disparar_kit_admissao(ctx, func_id, dry_run=False)
        resultado_2 = _montar_e_disparar_kit_admissao(ctx, func_id, dry_run=False)

    assert len(pendencias_criadas) == 1  # nunca criou uma segunda
    assert resultado_1['pendencias_identidade_kit'][0]['reaproveitada'] is False
    assert resultado_2['pendencias_identidade_kit'][0]['reaproveitada'] is True
    assert (resultado_1['pendencias_identidade_kit'][0]['pendencia_id']
            == resultado_2['pendencias_identidade_kit'][0]['pendencia_id'])
    mock_marcar.assert_called_once()
