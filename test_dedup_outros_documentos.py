"""
Teste de regressao para o bug de deduplicacao encontrado em 2026-07-21 no
Envio da Unimed Itapetininga: _aplicar_outros_documentos_no_envio() usava
(filename, url) como chave de dedup, mas a URL de anexo do Airtable e
assinada e muda a cada leitura — o dedup falhava silenciosamente e
duplicava os recibos de Joao Batista e Teodolino que ja estavam la.

A correcao troca a chave para filename normalizado + comparacao de
tamanho (bytes), que sao estaveis entre leituras.
"""
from unittest.mock import patch, Mock

import pytest

from app import (
    AirtableError,
    _normalizar_filename,
    _classificar_novos_vs_existentes,
    _dry_run_outros_documentos_para_envios,
    _aplicar_outros_documentos_no_envio,
    F_OD_DOCUMENTO,
    F_OD_PDF,
    F_OD_ENVIO,
)


# Tamanhos reais dos PDFs fatiados nesta rodada (MANIFESTO_FINAL.json)
TAM_JOAO = 55429
TAM_TEODOLINO = 55420
TAM_ALCIONE = 55413
TAM_EMILEIDE = 55427


def _attachment_existente(filename, size, url):
    return {'id': f'att_{filename}', 'filename': filename, 'size': size, 'url': url}


def _candidato(filename, size, url):
    return {'filename': filename, 'size': size, 'url': url, 'documento': filename}


def test_normalizar_filename_ignora_espacos_e_caixa():
    assert _normalizar_filename('  Recibo.pdf  ') == 'recibo.pdf'
    assert _normalizar_filename('RECIBO.PDF') == 'recibo.pdf'
    assert _normalizar_filename(None) == ''


def test_caso_real_unimed_nao_duplica_joao_e_teodolino():
    """Reproduz exatamente o cenario do Envio da Unimed Itapetininga em
    2026-07-21: Joao Batista e Teodolino ja estavam anexados (de uma
    aplicacao anterior, com uma URL assinada X); a nova leitura de "Outros
    documentos" traz os 4 candidatos (Joao, Teodolino, Alcione, Emileide)
    com uma URL assinada DIFERENTE (Y) para os mesmos arquivos de Joao e
    Teodolino — simulando a rotacao real de URL do Airtable.
    Resultado esperado: so Alcione e Emileide devem ser adicionados.
    """
    arquivos_existentes = [
        {'id': 'att1', 'filename': 'Folha de Ponto Junho 2026 - JOAO BATISTA SALES JUNIOR - ASSINADO.pdf',
         'size': 188000, 'url': 'https://airtable-attachments/urlX/folha_joao.pdf'},
        {'id': 'att2', 'filename': 'Comprovante Assinatura - Joao Batista Sales Junior.pdf',
         'size': 2300, 'url': 'https://airtable-attachments/urlX/comp_joao.pdf'},
        _attachment_existente(
            'Assiduidade Junho 2026 - TEODOLINO MUNIS FERNANDES JUNIOR.pdf',
            TAM_TEODOLINO, 'https://airtable-attachments/urlX/teodolino.pdf'),
        _attachment_existente(
            'Assiduidade Junho 2026 - JOAO BATISTA SALES JUNIOR.pdf',
            TAM_JOAO, 'https://airtable-attachments/urlX/joao.pdf'),
    ]

    candidatos = [
        _candidato('Assiduidade Junho 2026 - ALCIONE GISELE DE OLIVEIRA LEME.pdf',
                   TAM_ALCIONE, 'https://airtable-attachments/urlY/alcione.pdf'),
        _candidato('Assiduidade Junho 2026 - TEODOLINO MUNIS FERNANDES JUNIOR.pdf',
                   TAM_TEODOLINO, 'https://airtable-attachments/urlY/teodolino.pdf'),  # URL Y, diferente da urlX
        _candidato('Assiduidade Junho 2026 - EMILEIDE SIMOES CORREA LEITE.pdf',
                   TAM_EMILEIDE, 'https://airtable-attachments/urlY/emileide.pdf'),
        _candidato('Assiduidade Junho 2026 - JOAO BATISTA SALES JUNIOR.pdf',
                   TAM_JOAO, 'https://airtable-attachments/urlY/joao.pdf'),  # URL Y, diferente da urlX
    ]

    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes(
        arquivos_existentes, candidatos)

    nomes_a_adicionar = sorted(n['filename'] for n in a_adicionar)
    assert nomes_a_adicionar == sorted([
        'Assiduidade Junho 2026 - ALCIONE GISELE DE OLIVEIRA LEME.pdf',
        'Assiduidade Junho 2026 - EMILEIDE SIMOES CORREA LEITE.pdf',
    ]), f'Esperado somente Alcione e Emileide, obtido: {nomes_a_adicionar}'

    nomes_ja_existentes = sorted(n['filename'] for n in ja_existentes)
    assert nomes_ja_existentes == sorted([
        'Assiduidade Junho 2026 - TEODOLINO MUNIS FERNANDES JUNIOR.pdf',
        'Assiduidade Junho 2026 - JOAO BATISTA SALES JUNIOR.pdf',
    ]), f'Joao e Teodolino deveriam ser reconhecidos como ja existentes, obtido: {nomes_ja_existentes}'

    assert conflitos == []


def test_mesmo_nome_tamanho_diferente_gera_conflito_e_nao_adiciona():
    """Nome igual mas conteudo (tamanho) diferente = conflito real. Nao
    deve ser adicionado nem tratado como duplicata silenciosa."""
    arquivos_existentes = [
        _attachment_existente('Assiduidade Junho 2026 - FULANO.pdf', 50000, 'https://x/a.pdf'),
    ]
    candidatos = [
        _candidato('Assiduidade Junho 2026 - FULANO.pdf', 99999, 'https://y/a.pdf'),
    ]
    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes(
        arquivos_existentes, candidatos)
    assert a_adicionar == []
    assert ja_existentes == []
    assert len(conflitos) == 1
    assert conflitos[0]['motivo'] == 'mesmo_nome_tamanho_diferente'


def test_arquivo_novo_sem_conflito_e_adicionado():
    arquivos_existentes = []
    candidatos = [_candidato('Assiduidade Junho 2026 - NOVO.pdf', 1234, 'https://y/n.pdf')]
    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes(
        arquivos_existentes, candidatos)
    assert [n['filename'] for n in a_adicionar] == ['Assiduidade Junho 2026 - NOVO.pdf']
    assert ja_existentes == []
    assert conflitos == []


def test_mesmo_nome_duplicado_dentro_dos_proprios_candidatos():
    """Se a propria leitura de 'Outros documentos' trouxer 2 registros com
    o mesmo filename (ex.: reprocessamento acidental), o segundo deve ser
    sinalizado como conflito, nao silenciosamente ignorado ou duplicado."""
    candidatos = [
        _candidato('Assiduidade Junho 2026 - X.pdf', 100, 'https://y/1.pdf'),
        _candidato('Assiduidade Junho 2026 - X.pdf', 100, 'https://y/2.pdf'),
    ]
    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes([], candidatos)
    assert len(a_adicionar) == 1
    assert len(conflitos) == 1
    assert conflitos[0]['motivo'] == 'duplicado_dentro_dos_proprios_candidatos'


# ============================================================================
# Testes de _dry_run_outros_documentos_para_envios e
# _aplicar_outros_documentos_no_envio (integracao manual da PR #4).
# Nomes de colaboradores nestes testes sao sinteticos ("COLABORADOR X"),
# nao reproduzem o caso real da Unimed usado nos testes acima.
# ============================================================================

def _registro_outros_doc(record_id, documento, filename, size, envio_id,
                          url='https://airtable-attachments/x.pdf'):
    return {
        'id': record_id,
        'fields': {
            F_OD_DOCUMENTO: documento,
            F_OD_PDF: [{'filename': filename, 'url': url, 'size': size}],
            F_OD_ENVIO: [{'id': envio_id}],
        },
    }


def _registro_outros_doc_sem_pdf(record_id, documento, envio_id):
    return {
        'id': record_id,
        'fields': {
            F_OD_DOCUMENTO: documento,
            F_OD_PDF: [],
            F_OD_ENVIO: [{'id': envio_id}],
        },
    }


def _registro_outros_doc_sem_envio(record_id, documento, filename, size):
    return {
        'id': record_id,
        'fields': {
            F_OD_DOCUMENTO: documento,
            F_OD_PDF: [{'filename': filename, 'url': 'https://x/a.pdf', 'size': size}],
            F_OD_ENVIO: [],
        },
    }


def _mock_get_envio(fields_por_envio):
    """side_effect para requests.get que resolve o envio_id pelo final da URL."""
    def _fake(url, **kwargs):
        for envio_id, fields in fields_por_envio.items():
            if url.endswith(f'/{envio_id}'):
                return Mock(ok=True, status_code=200,
                            json=lambda fields=fields: {'fields': fields},
                            raise_for_status=lambda: None)
        raise AssertionError(f'GET inesperado para envio nao mapeado: {url}')
    return _fake


def test_dry_run_agrupa_por_envio_e_calcula_quantidade_a_adicionar():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
        _registro_outros_doc('recOD2', 'Assiduidade Junho 2026 - COLABORADOR DOIS.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR DOIS.pdf', 2000, 'recEnvioB'),
    ]
    fields_por_envio = {
        'recEnvioA': {'Name': 'Envio A', 'Status': 'Pendente', 'Cliente': [], 'Arquivos': []},
        'recEnvioB': {'Name': 'Envio B', 'Status': 'Pendente', 'Cliente': [], 'Arquivos': []},
    }
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=_mock_get_envio(fields_por_envio)):
        resultado = _dry_run_outros_documentos_para_envios('Junho 2026')

    assert len(resultado['envios']) == 2
    assert {e['envio_id'] for e in resultado['envios']} == {'recEnvioA', 'recEnvioB'}
    for e in resultado['envios']:
        assert e['qtd_a_adicionar'] == 1
    assert resultado['rejeitados'] == []


def test_dry_run_nunca_faz_patch():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
    ]
    fields_por_envio = {'recEnvioA': {'Name': 'Envio A', 'Status': 'Pendente', 'Cliente': [], 'Arquivos': []}}
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=_mock_get_envio(fields_por_envio)), \
         patch('app.requests.patch') as mock_patch:
        _dry_run_outros_documentos_para_envios('Junho 2026')

    mock_patch.assert_not_called()


def test_dry_run_retorna_rejeitados_sem_pdf_ou_sem_envio():
    registros = [
        _registro_outros_doc_sem_pdf('recOD1', 'Assiduidade Junho 2026 - SEM PDF.pdf', 'recEnvioA'),
        _registro_outros_doc_sem_envio('recOD2', 'Assiduidade Junho 2026 - SEM ENVIO.pdf',
                                        'Assiduidade Junho 2026 - SEM ENVIO.pdf', 500),
    ]
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get') as mock_get:
        resultado = _dry_run_outros_documentos_para_envios('Junho 2026')

    mock_get.assert_not_called()  # nenhum envio valido para consultar
    assert resultado['envios'] == []
    assert sorted(r['motivo'] for r in resultado['rejeitados']) == [
        'sem_envio_vinculado', 'sem_pdf_anexado',
    ]


def test_dry_run_competencia_sem_match_retorna_vazio():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Maio 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Maio 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
    ]
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get') as mock_get:
        resultado = _dry_run_outros_documentos_para_envios('Junho 2026')

    mock_get.assert_not_called()
    assert resultado == {'envios': [], 'rejeitados': []}


def test_aplica_preserva_existentes_e_adiciona_somente_novos():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR NOVO.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR NOVO.pdf', 1000, 'recEnvioA'),
    ]
    envio_fields = {
        'Arquivos': [{'id': 'attExistente', 'filename': 'Holerite Junho 2026 - OUTRO.pdf', 'size': 900}],
    }
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=Mock(ok=True, json=lambda: {'fields': envio_fields},
                                                       raise_for_status=lambda: None)), \
         patch('app.requests.patch', return_value=Mock(ok=True, status_code=200, text='{}')) as mock_patch:
        resultado = _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')

    assert resultado['status'] == 'aplicado'
    assert resultado['adicionados'] == ['Assiduidade Junho 2026 - COLABORADOR NOVO.pdf']
    mock_patch.assert_called_once()
    payload = mock_patch.call_args.kwargs['json']['fields']['Arquivos']
    assert {'id': 'attExistente'} in payload
    assert any(a.get('filename') == 'Assiduidade Junho 2026 - COLABORADOR NOVO.pdf' for a in payload)


def test_aplica_nao_duplica_arquivo_ja_existente():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
    ]
    envio_fields = {
        'Arquivos': [{'id': 'att1', 'filename': 'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 'size': 1000}],
    }
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=Mock(ok=True, json=lambda: {'fields': envio_fields},
                                                       raise_for_status=lambda: None)), \
         patch('app.requests.patch') as mock_patch:
        resultado = _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')

    assert resultado['status'] == 'sem_novidade_apos_dedup'
    mock_patch.assert_not_called()


def test_aplica_com_conflito_nao_escreve():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 9999, 'recEnvioA'),
    ]
    envio_fields = {
        'Arquivos': [{'id': 'att1', 'filename': 'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 'size': 1000}],
    }
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=Mock(ok=True, json=lambda: {'fields': envio_fields},
                                                       raise_for_status=lambda: None)), \
         patch('app.requests.patch') as mock_patch:
        resultado = _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')

    assert resultado['status'] == 'conflito_nao_aplicado'
    assert len(resultado['conflitos']) == 1
    mock_patch.assert_not_called()


def test_aplica_sem_novidade_nao_faz_patch():
    with patch('app._at_listar_todos', return_value=[]), \
         patch('app._at_throttle'), \
         patch('app.requests.get') as mock_get, \
         patch('app.requests.patch') as mock_patch:
        resultado = _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')

    assert resultado['status'] == 'nada_a_fazer'
    mock_get.assert_not_called()
    mock_patch.assert_not_called()


def test_aplica_erro_get_propaga():
    import requests
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
    ]
    resposta_falha = Mock(ok=False, status_code=500, text='erro interno')
    resposta_falha.raise_for_status.side_effect = requests.exceptions.HTTPError('500')
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=resposta_falha), \
         patch('app.requests.patch') as mock_patch:
        with pytest.raises(requests.exceptions.HTTPError):
            _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')

    mock_patch.assert_not_called()


def test_aplica_erro_patch_propaga():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
    ]
    envio_fields = {'Arquivos': []}
    resposta_patch_falha = Mock(ok=False, status_code=422,
                                 text='{"error":{"type":"INVALID","message":"x"}}')
    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=Mock(ok=True, json=lambda: {'fields': envio_fields},
                                                       raise_for_status=lambda: None)), \
         patch('app.requests.patch', return_value=resposta_patch_falha):
        with pytest.raises(AirtableError):
            _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')


def test_aplica_segunda_execucao_e_idempotente():
    registros = [
        _registro_outros_doc('recOD1', 'Assiduidade Junho 2026 - COLABORADOR UM.pdf',
                              'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 1000, 'recEnvioA'),
    ]
    envio_fields_antes = {'Arquivos': []}
    envio_fields_depois = {
        'Arquivos': [{'id': 'attNovo', 'filename': 'Assiduidade Junho 2026 - COLABORADOR UM.pdf', 'size': 1000}],
    }

    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=Mock(ok=True, json=lambda: {'fields': envio_fields_antes},
                                                       raise_for_status=lambda: None)), \
         patch('app.requests.patch', return_value=Mock(ok=True, status_code=200, text='{}')) as mock_patch:
        resultado1 = _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')
    assert resultado1['status'] == 'aplicado'
    assert mock_patch.call_count == 1

    with patch('app._at_listar_todos', return_value=registros), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=Mock(ok=True, json=lambda: {'fields': envio_fields_depois},
                                                       raise_for_status=lambda: None)), \
         patch('app.requests.patch') as mock_patch2:
        resultado2 = _aplicar_outros_documentos_no_envio('recEnvioA', 'Junho 2026')
    assert resultado2['status'] == 'sem_novidade_apos_dedup'
    mock_patch2.assert_not_called()
