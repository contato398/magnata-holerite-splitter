"""
Fase 1 — Ownership + Bridge Segura.

Auditoria prévia encontrou que `_carregar_e_validar`/`_gerar_assinatura_core`
liam um field ID (`fldxbZwVNa01pchqF`) que nunca existiu no schema real de
`TABLE_ARQUIVOS` — `dict.get(campo_inexistente, [])` sempre retornava `[]`,
e a checagem `if func_arquivo and func_arquivo[0] != funcionario_id` nunca
disparava: qualquer documento podia ser associado a qualquer funcionário
sem bloqueio (bypass silencioso de ownership cross-colaborador).

Esta Fase 1 introduz um campo real (`F_ARQ_FUNCIONARIO_OWNER`,
linked-record -> Funcionários, criado sob gate humano separado) e um
validador central fail-closed (`_validar_owner_arquivo`) reutilizado pelos
dois fluxos legados (assinatura standalone e pacote Holerite+Ponto).

100% dado sintético -- nenhum CPF/nome/telefone real em nenhum lugar deste
arquivo. IDs (recXXXX) são inventados.
"""
import hashlib
from unittest.mock import MagicMock, Mock, patch

import app
from app import (
    F_ARQ_ATTACH,
    F_ARQ_FUNCIONARIO_OWNER,
    _gerar_assinatura_core,
    _gerar_pacote_assinatura_holerite_ponto,
    _montar_e_disparar_kit_admissao,
    _processar_folha_ponto_arquivo,
    _validar_owner_arquivo,
)


def _resp(ok=True, json_dict=None):
    r = Mock()
    r.ok = ok
    r.json.return_value = json_dict or {}
    return r


FUNC_A = 'recFUNCIONARIOA0001'
FUNC_B = 'recFUNCIONARIOB0002'


# ── Contrato de _validar_owner_arquivo (unitário, sem rede) ─────────────

def test_owner_campo_ausente_bloqueia_422():
    erro = _validar_owner_arquivo({}, FUNC_A, 'Arquivo', 'req1')
    assert erro is not None
    assert erro[1] == 422


def test_owner_valor_none_bloqueia_422():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: None}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 422


def test_owner_lista_vazia_bloqueia_422():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: []}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 422


def test_owner_valor_nao_lista_bloqueia_422():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: FUNC_A}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 422


def test_owner_multiplos_bloqueia_422():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: [FUNC_A, FUNC_B]}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 422


def test_owner_item_malformado_bloqueia_422():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: ['nao-e-record-id']}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 422


def test_owner_item_nao_string_bloqueia_422():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: [12345]}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 422


def test_owner_divergente_bloqueia_403():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: [FUNC_B]}, FUNC_A, 'Arquivo', 'req1')
    assert erro[1] == 403
    assert 'outro funcionário' in erro[0]['erro']


def test_owner_igual_prossegue():
    erro = _validar_owner_arquivo({F_ARQ_FUNCIONARIO_OWNER: [FUNC_A]}, FUNC_A, 'Arquivo', 'req1')
    assert erro is None


# ── _gerar_assinatura_core: ownership bloqueia ANTES de qualquer efeito ──

def _config_ok():
    return patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok'))


def test_standalone_owner_divergente_bloqueia_antes_do_download():
    resp_arquivo = _resp(json_dict={'fields': {
        F_ARQ_ATTACH: [{'url': 'https://example.invalid/doc.pdf', 'filename': 'doc.pdf'}],
        F_ARQ_FUNCIONARIO_OWNER: [FUNC_B],
    }})
    with _config_ok(), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=resp_arquivo), \
         patch('app._carregar_documento_url') as mock_download, \
         patch('app.requests.post') as mock_post:
        resultado, status = _gerar_assinatura_core(
            funcionario_id=FUNC_A, tipo_documento='FICHA_EPI',
            arquivo_record_id='recArquivoXPTO0001', disparar_whatsapp=False,
        )
    assert status == 403
    assert 'outro funcionário' in resultado['erro']
    mock_download.assert_not_called()  # nunca baixa PDF de documento de outro dono
    mock_post.assert_not_called()      # nunca cria registro em TABLE_ASSINATURAS


def test_standalone_owner_ausente_bloqueia_422_antes_do_download():
    resp_arquivo = _resp(json_dict={'fields': {
        F_ARQ_ATTACH: [{'url': 'https://example.invalid/doc.pdf', 'filename': 'doc.pdf'}],
        # F_ARQ_FUNCIONARIO_OWNER ausente de propósito
    }})
    with _config_ok(), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=resp_arquivo), \
         patch('app._carregar_documento_url') as mock_download:
        resultado, status = _gerar_assinatura_core(
            funcionario_id=FUNC_A, tipo_documento='FICHA_EPI',
            arquivo_record_id='recArquivoXPTO0001', disparar_whatsapp=False,
        )
    assert status == 422
    mock_download.assert_not_called()


# ── Pacote Holerite+Ponto: grade completa de ownership ──────────────────

def _arquivo_com_owner(owner_id, url='https://static/doc.pdf', filename='doc.pdf'):
    return _resp(json_dict={'fields': {
        F_ARQ_ATTACH: [{'url': url, 'filename': filename}],
        F_ARQ_FUNCIONARIO_OWNER: [owner_id],
    }})


ELEGIVEL = ('app._status_funcionario_elegivel', {'return_value': (True, None)})
TEXTO_HOL = 'MAGNATA PORTARIA E SERVICOS\nMensalista Junho de 2026\nTotal de Vencimentos: 2000,00'
TEXTO_PONTO = 'CARTAO DE PONTO\nJunho de 2026\nEntrada Saida'


def _rodar_pacote(respostas_get):
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=respostas_get), \
         patch('app._carregar_documento_url', return_value=b'%PDF-1.4\nconteudo-sintetico'), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOL, TEXTO_PONTO]):
        return _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_A, arquivo_holerite_id='recARQHOL0001',
            arquivo_ponto_id='recARQPONTO0001', dry_run=True,
        )


def test_pacote_holerite_a_ponto_a_aceita_ownership():
    resultado, status = _rodar_pacote([
        _arquivo_com_owner(FUNC_A), _arquivo_com_owner(FUNC_A),
    ])
    # dry_run=True: se ownership não tivesse bloqueado, chega até a resposta
    # de pré-visualização (nunca 403/422 de ownership).
    assert status not in (403, 422) or 'erro' not in resultado or 'proprietário' not in resultado.get('erro', '')
    assert status != 403


def test_pacote_holerite_a_ponto_b_bloqueia():
    resultado, status = _rodar_pacote([
        _arquivo_com_owner(FUNC_A), _arquivo_com_owner(FUNC_B),
    ])
    assert status == 403
    assert 'outro funcionário' in resultado['erro']


def test_pacote_holerite_b_ponto_b_funcionario_a_bloqueia():
    resultado, status = _rodar_pacote([
        _arquivo_com_owner(FUNC_B), _arquivo_com_owner(FUNC_B),
    ])
    assert status == 403
    assert 'outro funcionário' in resultado['erro']
    # bloqueia já no primeiro documento (Holerite) — nunca processa o
    # segundo (Folha de Ponto) depois de uma falha terminal do primeiro.


def test_pacote_owner_ausente_em_qualquer_documento_bloqueia_pacote_inteiro():
    resp_sem_owner = _resp(json_dict={'fields': {
        F_ARQ_ATTACH: [{'url': 'https://static/doc.pdf', 'filename': 'doc.pdf'}],
    }})
    resultado, status = _rodar_pacote([_arquivo_com_owner(FUNC_A), resp_sem_owner])
    assert status == 422


# ── Materializações autoritativas gravam o owner ────────────────────────

def test_kit_admissao_grava_owner_no_arquivo_criado():
    from app import F_FUNC_CPF, F_FUNC_KIT_CONSOLIDADO

    ctx = {
        'proc_id': 'procFICHA', 'arquivo_id': 'arqFICHA',
        'pdf_bytes': b'ficha-bytes', 'texto': 'Ficha de Registro de Empregado sintetica',
        'email_savian_id': 'recEmailFAKE1',
    }
    func_id = FUNC_A
    r_func = _resp(json_dict={'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})

    posts_capturados = []

    def fake_post(url, headers=None, json=None, **kwargs):
        posts_capturados.append((url, json))
        return _resp(json_dict={'id': 'recArquivoKitNovo'})

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[]), \
         patch('app._gerar_pdf_declaracao_renuncia_vt', return_value=b'vt-fake'), \
         patch('app._montar_pdf_consolidado_kit_admissao', return_value=b'kit-consolidado'), \
         patch('app._anexar_attachment'), \
         patch('app.requests.post', side_effect=fake_post), \
         patch('app._gerar_assinatura_core'), \
         patch('app._atualizar_status_processar'):
        _montar_e_disparar_kit_admissao(ctx, func_id, dry_run=False)

    posts_arquivos = [p for (u, p) in posts_capturados if app.TABLE_ARQUIVOS in u]
    assert posts_arquivos, 'esperava um POST em TABLE_ARQUIVOS'
    assert posts_arquivos[0]['fields'][F_ARQ_FUNCIONARIO_OWNER] == [func_id]


def test_folha_ponto_grava_owner_no_arquivo_criado():
    from app import F_FUNC_PDF_FOLHA

    func_id = FUNC_A
    r_func_check = _resp(json_dict={'fields': {
        F_FUNC_PDF_FOLHA: [{'url': 'https://static/folha.pdf'}],
    }})

    posts_capturados = []

    def fake_post(url, headers=None, json=None, **kwargs):
        posts_capturados.append((url, json))
        if app.TABLE_ARQUIVOS in url:
            return _resp(json_dict={'id': 'recArquivoPontoNovo'})
        return _resp(json_dict={'status': 'ok'})

    with patch('app.construir_mapa_cpf', return_value=({'11111111111': {'nome': 'FULANO', 'paginas': [1]}}, 1)), \
         patch('app.buscar_funcionario_por_cpf', return_value=(func_id, 'FULANO')), \
         patch('app.extrair_pdf_colaborador', return_value=b'pdf-individual'), \
         patch('app._anexar_attachment'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=r_func_check), \
         patch('app.requests.post', side_effect=fake_post), \
         patch('app._gerar_assinatura_core', return_value=({'status': 'ok'}, 200)):
        _processar_folha_ponto_arquivo(
            caminho_pdf='/tmp/fake.pdf', folha_mensal='Junho 2026',
            disparar_assinatura=True, cpfs_excluir=set(),
        )

    posts_arquivos = [p for (u, p) in posts_capturados if app.TABLE_ARQUIVOS in u]
    assert posts_arquivos, 'esperava um POST em TABLE_ARQUIVOS'
    assert posts_arquivos[0]['fields'][F_ARQ_FUNCIONARIO_OWNER] == [func_id]


# ── Drift de schema: F_ARQ_FUNCIONARIO_OWNER faz parte da validação v3.6 ─

def test_field_id_owner_participa_da_validacao_de_configuracao():
    ok, msg = app._validar_configuracao_assinatura_v36()
    assert ok, msg  # o field real configurado deve passar no formato exigido


def test_field_id_morto_nao_e_mais_referenciado_em_codigo_ativo():
    """Guarda de regressão: o field ID antigo (nunca existiu no schema real)
    só pode aparecer em comentário/docstring histórico — nunca de volta
    como literal lido por dict.get(...) em código ativo (era exatamente
    esse padrão que tornava a ausência do campo um bypass silencioso)."""
    with open('app.py', encoding='utf-8') as f:
        conteudo = f.read()
    assert ".get('fldxbZwVNa01pchqF'" not in conteudo
    assert '.get("fldxbZwVNa01pchqF"' not in conteudo
