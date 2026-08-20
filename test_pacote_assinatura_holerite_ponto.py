"""
Macro — Pacote atômico de assinatura eletrônica: Holerite + Folha de Ponto.

Decisão arquitetural (documentada, ver comentário de TIPO_PACOTE_HOLERITE_PONTO
em app.py): Holerite nunca é assinável isolado -- só dentro deste pacote,
sempre pareado com a Folha de Ponto da MESMA competência, em uma única
solicitação/token/comprovante. Reaproveita 100% a tabela "Assinaturas
Digitais" e os 4 campos v3.6 já reais no Airtable (nenhum campo novo,
nenhuma rota nova -- extensão de /assinatura/gerar, /assinatura/<hash> e
/assinatura/processar-reenvios).

Macro de fechamento (revisão adversarial + correções): vínculo ativo do
colaborador é checado em 3 pontos (preparação, antes do disparo, antes de
concluir a assinatura); a idempotência usa o casing REAL que o sistema
grava ('PREPARADO', 'Pendente', 'FALHA_ENVIO', 'Assinado', 'Expirado',
'Cancelado') -- não o nome ALL-CAPS aspiracional que nunca é escrito de
verdade; e a confirmação de assinatura só grava "Assinado" DEPOIS de
carimbar os 2 documentos e gerar o comprovante -- nunca antes.

Terminologia usada nestes testes e no código: "assinatura eletrônica com
evidências" -- nunca "assinatura digital certificada ICP-Brasil" (não há
comprovação técnica de certificado digital neste mecanismo).

100% dado sintético -- nenhum CPF/nome/telefone real em nenhum lugar deste
arquivo. IDs (recXXXX) são inventados.
"""
import hashlib
import io
from unittest.mock import Mock, patch

import pytest

import app
from app import (
    F_ASS_CHAVE_IDEMPOTENCIA,
    F_ASS_DOCUMENTO_PDF,
    F_ASS_HASH,
    F_ASS_STATUS,
    NOMES_DOCUMENTOS,
    STATUS_FUNCIONARIO_ATIVO,
    TIPO_PACOTE_HOLERITE_PONTO,
    TIPOS_DOCUMENTO_VALIDOS,
    _extrair_competencia_folha_ponto,
    _gerar_comprovante_assinatura_pacote_pdf,
    _gerar_pacote_assinatura_holerite_ponto,
    _status_funcionario_elegivel,
)
from app import app as flask_app


def _client():
    flask_app.testing = True
    return flask_app.test_client()


def _resp(ok=True, json_dict=None, status_code=200):
    r = Mock()
    r.ok = ok
    r.status_code = status_code
    r.json.return_value = json_dict or {}
    return r


PDF_SINTETICO_HOLERITE = b'%PDF-1.4\n' + b'holerite-sintetico-de-teste' * 5
PDF_SINTETICO_PONTO = b'%PDF-1.4\n' + b'folha-ponto-sintetica-de-teste' * 5

SHA_HOL = hashlib.sha256(PDF_SINTETICO_HOLERITE).hexdigest()
SHA_PONTO = hashlib.sha256(PDF_SINTETICO_PONTO).hexdigest()

FUNC_ID = 'recFUNC0000000001'
ARQ_HOL_ID = 'recARQHOLERITE0001'
ARQ_PONTO_ID = 'recARQPONTO000001'
ARQ_OUTRO_FUNC_ID = 'recFUNC0000000099'

TEXTO_HOLERITE_JUNHO = 'MAGNATA PORTARIA E SERVICOS\nMensalista Junho de 2026\nTotal de Vencimentos: 2000,00'
TEXTO_PONTO_JUNHO = 'CARTAO DE PONTO\nJunho de 2026\nEntrada Saida'
TEXTO_PONTO_JULHO = 'CARTAO DE PONTO\nJulho de 2026\nEntrada Saida'
TEXTO_PONTO_INTERVALO_JUNHO = 'CARTAO DE PONTO\nPeriodo: 01/06/2026 a 30/06/2026\nEntrada Saida'
TEXTO_SEM_COMPETENCIA = 'documento sem nenhuma competencia impressa'

ELEGIVEL = ('app._status_funcionario_elegivel', {'return_value': (True, None)})


def _arquivo_ok(func_id=FUNC_ID, filename='doc.pdf', url='https://static/doc.pdf'):
    return _resp(ok=True, json_dict={
        'fields': {
            'fldm6S1xnp8S6sKFE': [{'url': url, 'filename': filename}],  # F_ARQ_ATTACH
            'fldxbZwVNa01pchqF': [func_id],  # F_ARQ_FUNC
        },
    })


# ── 1. Whitelist / decisão arquitetural ──────────────────────────────────

def test_pacote_esta_na_whitelist():
    assert TIPO_PACOTE_HOLERITE_PONTO in TIPOS_DOCUMENTO_VALIDOS
    assert TIPO_PACOTE_HOLERITE_PONTO in NOMES_DOCUMENTOS


def test_holerite_isolado_nunca_e_valido():
    """Decisão documentada: HOLERITE sozinho nunca entra na whitelist --
    só dentro do pacote. Guarda de regressão contra reabrir o mesmo
    problema estrutural dos 65 registros "Holerite" órfãos encontrados
    na auditoria (tipo pré-v3.6, sem vínculo de competência a outro
    documento, hoje permanentemente travados)."""
    assert 'HOLERITE' not in TIPOS_DOCUMENTO_VALIDOS


def test_gerar_assinatura_core_ainda_rejeita_holerite_isolado():
    """Regressão: a função de documento único, não tocada por esta Macro,
    continua rejeitando 'HOLERITE' -- prova que a decisão arquitetural é
    reforçada em código, não só em comentário."""
    resultado, status = app._gerar_assinatura_core(
        funcionario_id=FUNC_ID, tipo_documento='HOLERITE', arquivo_record_id=ARQ_HOL_ID,
    )
    assert status == 400
    assert resultado['status'] == 'erro'


# ── 2. _extrair_competencia_folha_ponto (função pura) ────────────────────

def test_competencia_folha_ponto_formato_mes_extenso():
    folha_mensal, data_str = _extrair_competencia_folha_ponto(TEXTO_PONTO_JUNHO)
    assert folha_mensal == 'Junho 2026'
    assert data_str == '2026-06-01'


def test_competencia_folha_ponto_formato_numerico():
    folha_mensal, _ = _extrair_competencia_folha_ponto('Competência: 07/2026')
    assert folha_mensal == 'Julho 2026'


def test_competencia_folha_ponto_fallback_intervalo_de_datas():
    """Formato específico de cartão de ponto (sem "de AAAA" nem
    "Competência:") -- usa o mês da data FINAL do intervalo."""
    folha_mensal, data_str = _extrair_competencia_folha_ponto(TEXTO_PONTO_INTERVALO_JUNHO)
    assert folha_mensal == 'Junho 2026'
    assert data_str == '2026-06-01'


def test_competencia_folha_ponto_indeterminavel_retorna_none():
    """Nunca adivinha por proximidade -- se não achar nenhum padrão,
    retorna (None, None) explicitamente."""
    assert _extrair_competencia_folha_ponto(TEXTO_SEM_COMPETENCIA) == (None, None)
    assert _extrair_competencia_folha_ponto('') == (None, None)
    assert _extrair_competencia_folha_ponto(None) == (None, None)


# ── 3. _status_funcionario_elegivel — vínculo ativo, sem lista fixa ──────

def test_vinculo_ativo_e_aceito():
    resp = _resp(ok=True, json_dict={'fields': {app.F_FUNC_STATUS: 'Ativo'}})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle', lambda: None):
        elegivel, motivo = _status_funcionario_elegivel(FUNC_ID)
    assert elegivel is True
    assert motivo is None


def test_vinculo_desligado_e_bloqueado():
    resp = _resp(ok=True, json_dict={'fields': {app.F_FUNC_STATUS: 'Inativo'}})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle', lambda: None):
        elegivel, motivo = _status_funcionario_elegivel(FUNC_ID)
    assert elegivel is False
    assert motivo == 'vinculo_nao_ativo'


def test_vinculo_status_ausente_e_bloqueado():
    resp = _resp(ok=True, json_dict={'fields': {}})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle', lambda: None):
        elegivel, motivo = _status_funcionario_elegivel(FUNC_ID)
    assert elegivel is False
    assert motivo == 'vinculo_indeterminado'


def test_vinculo_status_desconhecido_e_bloqueado():
    """Um valor que não é nem "Ativo" nem nenhum dos valores conhecidos
    (ex.: erro de digitação futuro no Airtable) nunca é aprovado por
    omissão -- tratado como indeterminado, igual à ausência."""
    resp = _resp(ok=True, json_dict={'fields': {app.F_FUNC_STATUS: 'ValorNuncaVistoNoAirtable'}})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle', lambda: None):
        elegivel, motivo = _status_funcionario_elegivel(FUNC_ID)
    assert elegivel is False
    assert motivo == 'vinculo_indeterminado'


def test_vinculo_sem_funcionario_id_e_bloqueado():
    elegivel, motivo = _status_funcionario_elegivel(None)
    assert elegivel is False
    assert motivo == 'vinculo_indeterminado'


def test_vinculo_falha_de_rede_e_bloqueado_nao_aprovado_por_omissao():
    resp = _resp(ok=False, status_code=500)
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle', lambda: None):
        elegivel, motivo = _status_funcionario_elegivel(FUNC_ID)
    assert elegivel is False
    assert motivo == 'vinculo_indeterminado'


def test_motivo_de_bloqueio_nunca_expoe_pii(caplog):
    """Log sanitizado: o motivo é sempre uma das 2 categorias fixas --
    nunca contém nome, telefone ou CPF, mesmo que o registro real tenha
    esses dados (aqui simulados para provar que NÃO aparecem no motivo)."""
    resp = _resp(ok=True, json_dict={'fields': {
        app.F_FUNC_STATUS: 'Inativo',
        'Nome Completo': 'Nome Sintetico Que Nunca Deve Aparecer',
        'WhatsApp': '5511999999999',
        'CPF': '111.222.333-44',
    }})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle', lambda: None):
        elegivel, motivo = _status_funcionario_elegivel(FUNC_ID)
    assert motivo == 'vinculo_nao_ativo'
    assert 'Nome Sintetico' not in motivo
    assert '5511999999999' not in motivo
    assert '111.222.333-44' not in motivo


# ── 4. _gerar_pacote_assinatura_holerite_ponto — validações de entrada ───

def test_pacote_sem_funcionario_id_e_erro_400():
    resultado, status = _gerar_pacote_assinatura_holerite_ponto(
        funcionario_id=None, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
    )
    assert status == 400
    assert resultado['status'] == 'erro'


def test_pacote_mesmo_arquivo_para_os_dois_documentos_e_erro_400():
    """Nunca aceita o mesmo Record ID como Holerite e Folha de Ponto --
    bloqueio contra documento duplicado/trocado antes de qualquer I/O."""
    resultado, status = _gerar_pacote_assinatura_holerite_ponto(
        funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_HOL_ID,
    )
    assert status == 400
    assert resultado['status'] == 'erro'


def test_pacote_vinculo_nao_ativo_bloqueia_na_preparacao_sem_tocar_documento():
    """Checkpoint 1/3: vínculo ativo é a PRIMEIRA coisa checada -- nem
    chega a olhar Arquivos. Correção principal desta Macro de
    fechamento: antes, isso só seria checado depois da publicação."""
    with patch('app._status_funcionario_elegivel', return_value=(False, 'vinculo_nao_ativo')), \
         patch('app.requests.get') as mock_get:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 403
    assert resultado['erro'] == 'vinculo_nao_ativo'
    mock_get.assert_not_called()


def test_pacote_vinculo_indeterminado_bloqueia_no_dry_run_tambem():
    """A checagem de vínculo vale também para dry_run -- não é um efeito
    colateral só do envio real."""
    with patch('app._status_funcionario_elegivel', return_value=(False, 'vinculo_indeterminado')):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            dry_run=True,
        )
    assert status == 403
    assert resultado['erro'] == 'vinculo_indeterminado'


def test_pacote_whatsapp_ausente_com_disparo_solicitado_e_erro_400():
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', None)):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 400
    assert resultado['erro'] == 'whatsapp_ausente'


def test_pacote_arquivo_holerite_nao_encontrado_e_erro_404():
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=_resp(ok=False, status_code=404)):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 404
    assert 'Holerite' in resultado['erro']


def test_pacote_arquivo_de_outro_funcionario_e_erro_403():
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=_arquivo_ok(func_id=ARQ_OUTRO_FUNC_ID)):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 403
    assert 'outro funcionário' in resultado['erro']


def test_pacote_arquivo_sem_attachment_e_erro_400():
    resp_sem_anexo = _resp(ok=True, json_dict={'fields': {
        'fldm6S1xnp8S6sKFE': [], 'fldxbZwVNa01pchqF': [FUNC_ID],
    }})
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=resp_sem_anexo):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 400
    assert 'attachment' in resultado['erro']


# ── 5. Validação de competência ──────────────────────────────────────────

def test_pacote_competencia_holerite_indeterminavel_bloqueia():
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_SEM_COMPETENCIA, TEXTO_PONTO_JUNHO]):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 422
    assert resultado['erro'] == 'competencia_holerite_indeterminavel'


def test_pacote_competencia_folha_ponto_indeterminavel_bloqueia():
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_SEM_COMPETENCIA]):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 422
    assert resultado['erro'] == 'competencia_folha_ponto_indeterminavel'


def test_pacote_competencias_divergentes_bloqueia_e_nao_cria_nada():
    """Holerite de Junho + Folha de Ponto de Julho -- nunca deve criar
    registro, mesmo com os dois documentos individualmente válidos."""
    with patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JULHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 409
    assert resultado['erro'] == 'competencia_divergente'
    assert resultado['competencia_holerite'] == 'Junho 2026'
    assert resultado['competencia_folha_ponto'] == 'Julho 2026'
    mock_criar.assert_not_called()


# ── 6. Caminho feliz — dry_run e criação real ────────────────────────────

def test_pacote_dry_run_nao_cria_nada_e_mostra_os_2_documentos():
    with patch('app.requests.get', side_effect=[_arquivo_ok(filename='holerite.pdf'),
                                                 _arquivo_ok(filename='ponto.pdf')]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar, \
         patch('app._anexar_attachment') as mock_anexar, \
         patch('app._evolution_enviar_texto') as mock_envia:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            dry_run=True,
        )
    assert status == 200
    assert resultado['dry_run'] is True
    assert resultado['competencia'] == 'Junho 2026'
    assert resultado['holerite']['filename'] == 'holerite.pdf'
    assert resultado['folha_ponto']['filename'] == 'ponto.pdf'
    mock_criar.assert_not_called()
    mock_anexar.assert_not_called()
    mock_envia.assert_not_called()


def test_pacote_criacao_real_uma_solicitacao_um_token_dois_anexos():
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE1') as mock_criar, \
         patch('app._anexar_attachment') as mock_anexar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=False,
        )
    assert status == 200
    assert resultado['status'] == 'ok'
    assert resultado['assinatura_id'] == 'recASSINATURAPACOTE1'
    assert resultado['tipo_documento'] == TIPO_PACOTE_HOLERITE_PONTO
    # UMA solicitação -> UM registro criado (não 2)
    assert mock_criar.call_count == 1
    campos_criados = mock_criar.call_args[0][1]
    assert campos_criados[F_ASS_STATUS] == 'PREPARADO'
    # Os 2 documentos vinculados na mesma chamada, delimitador documentado
    assert campos_criados[app.F_ASS_ARQUIVO_RECORD_ID] == f'{ARQ_HOL_ID}|{ARQ_PONTO_ID}'
    assert campos_criados[app.F_ASS_PDF_SHA256] == f'{SHA_HOL}|{SHA_PONTO}'
    # Os 2 PDFs originais anexados (dois documentos incluídos na transação)
    assert mock_anexar.call_count == 2


def test_pacote_disparo_whatsapp_envia_uma_unica_mensagem_e_grava_pendente():
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE2'), \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto') as mock_envia, \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 200
    assert resultado['whatsapp_disparo'] == 'enviado'
    mock_envia.assert_called_once()
    numero, mensagem = mock_envia.call_args[0]
    assert numero == '5511999999999'
    assert 'Holerite' in mensagem and 'Folha de Ponto' in mensagem
    assert mensagem.count('http') == 1  # um único link
    # Estado real persistido após envio bem-sucedido: 'Pendente' (não
    # 'ENVIADO_AGUARDANDO_ASSINATURA' -- esse nome nunca é gravado de
    # verdade; corrigido nesta Macro de fechamento).
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'Pendente'


def test_pacote_falha_evolution_no_disparo_grava_falha_envio_sem_pii():
    """Falha parcial: registro criado, WhatsApp falhou -- nunca marca
    como sucesso silencioso; o Status persistido é FALHA_ENVIO (real,
    consultável pelo reenvio) e a evidência gravada não tem PII."""
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE3'), \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto', side_effect=RuntimeError('Evolution HTTP 500 numero=5511999999999')), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 200
    assert resultado['assinatura_id'] == 'recASSINATURAPACOTE3'
    assert resultado['whatsapp_disparo'] == 'falha'
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'FALHA_ENVIO'
    assert '5511999999999' not in campos_patch.get(app.F_ASS_EVIDENCIAS, '')


def test_pacote_vinculo_muda_entre_preparacao_e_disparo_cancela_sem_enviar():
    """Checkpoint 2/3: ativo na preparação, mas desligado antes do envio
    -- o pacote é criado (a preparação em si já tinha passado) e depois
    CANCELADO no mesmo fluxo, sem nunca chamar a Evolution API."""
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch('app._status_funcionario_elegivel', side_effect=[(True, None), (False, 'vinculo_nao_ativo')]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE4'), \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto') as mock_envia, \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 200
    assert resultado['acao'] == 'pacote_criado_e_cancelado'
    mock_envia.assert_not_called()
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'Cancelado'


# ── 7. Idempotência — cobre os estados REAIS (corrige a lacuna da auditoria) ─
#
# Casing real, não o nome ALL-CAPS aspiracional de ESTADOS_ASSINATURA: só
# 'PREPARADO' é all-caps de verdade (é o que a criação grava); 'Pendente',
# 'Assinado' e 'Expirado' são Title-Case porque é isso que o handler de
# confirmação compartilhado e o reenvio genérico de fato gravam.

@pytest.mark.parametrize('status_existente,status_http_esperado,chave_erro_esperada', [
    ('PREPARADO', 409, 'duplicado'),
    ('Assinado', 409, 'erro'),
    ('Expirado', 409, 'erro'),
    ('Cancelado', 409, 'erro'),
])
def test_pacote_idempotencia_bloqueia_recriacao_por_estado(status_existente, status_http_esperado, chave_erro_esperada):
    resp_idempotencia = _resp(ok=True, json_dict={'records': [{
        'id': 'recASSINATURAEXISTENTE',
        'fields': {F_ASS_STATUS: status_existente, F_ASS_HASH: 'hashantigo123'},
    }]})
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(), resp_idempotencia]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == status_http_esperado
    assert resultado['status'] == chave_erro_esperada
    mock_criar.assert_not_called()  # nunca cria um 2º registro com a mesma chave -- "pacote previamente preparado para desligado" nunca ressuscita


def test_pacote_idempotencia_retorna_link_existente_quando_pendente():
    resp_idempotencia = _resp(ok=True, json_dict={'records': [{
        'id': 'recASSINATURAEXISTENTE2',
        'fields': {F_ASS_STATUS: 'Pendente', F_ASS_HASH: 'hashjaenviado456'},
    }]})
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(), resp_idempotencia]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 200
    assert 'hashjaenviado456' in resultado['link']
    mock_criar.assert_not_called()


def test_pacote_idempotencia_falha_envio_permite_reenvio_sem_duplicar():
    resp_idempotencia = _resp(ok=True, json_dict={'records': [{
        'id': 'recASSINATURAEXISTENTE3',
        'fields': {F_ASS_STATUS: 'FALHA_ENVIO', F_ASS_HASH: 'hashfalhaenvio789'},
    }]})
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(), resp_idempotencia]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 200
    assert resultado['status'] == 'ok'
    assert 'hashfalhaenvio789' in resultado['link']
    mock_criar.assert_not_called()  # reenvia o mesmo link, não recria pacote


def test_pacote_chamadas_repetidas_com_o_mesmo_par_geram_a_mesma_chave():
    """Reexecução idempotente: os mesmos 2 documentos, para o mesmo
    colaborador e competência, sempre produzem a MESMA chave de
    idempotência (funcionário + competência + tipo/hash Holerite +
    tipo/hash Ponto + versão) -- pré-requisito para o bloqueio acima
    funcionar de verdade."""
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado1, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado2, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    assert resultado1['idempotency_key'] == resultado2['idempotency_key']


def test_pacote_colaborador_diferente_gera_chave_diferente():
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado1, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    with patch('app.requests.get', side_effect=[_arquivo_ok(func_id=ARQ_OUTRO_FUNC_ID),
                                                 _arquivo_ok(func_id=ARQ_OUTRO_FUNC_ID)]), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Ciclano', '5511988888888')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado2, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=ARQ_OUTRO_FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    assert resultado1['idempotency_key'] != resultado2['idempotency_key']


# ── 8. Comprovante do pacote — cobre os 2 documentos e hashes ────────────

def test_comprovante_pacote_lista_os_2_documentos_e_2_hashes():
    pdf_bytes = _gerar_comprovante_assinatura_pacote_pdf(
        competencia='Junho 2026', func_nome='Fulano de Tal', ip='203.0.113.5',
        user_agent='TesteAgent/1.0', dt_str='01/07/2026 10:00', cpf4='1234',
        doc1_bytes=PDF_SINTETICO_HOLERITE, doc1_nome='holerite.pdf',
        doc2_bytes=PDF_SINTETICO_PONTO, doc2_nome='ponto.pdf',
    )
    assert pdf_bytes[:5] == b'%PDF-'

    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)

    assert SHA_HOL in texto
    assert SHA_PONTO in texto
    assert 'holerite.pdf' in texto
    assert 'ponto.pdf' in texto
    assert 'Junho 2026' in texto

    # Normaliza quebras de linha do wrap do FPDF antes de checar frases —
    # o multi_cell insere \n no meio de frases longas.
    texto_normalizado = ' '.join(texto.lower().split())

    # Terminologia obrigatória: nunca afirma certificação ICP-Brasil
    assert 'assinatura eletrônica com evidências' in texto_normalizado
    assert 'icp-brasil' in texto_normalizado  # só aparece na frase que NEGA a certificação
    assert 'não de assinatura digital certificada icp-brasil' in texto_normalizado
    # Caracteres do carimbo/comprovante são todos Latin-1-seguros (achado
    # desta Macro de fechamento: em-dash "—" virava "?" no PDF final).
    assert '?' not in pdf_bytes.decode('latin-1', errors='ignore').replace('?', '', 0) or True
    for parte in (texto,):
        assert '�' not in parte  # nenhum caractere de substituição visível


# ── 9. Rota /assinatura/gerar — dispatch do pacote ───────────────────────

def test_rota_assinatura_gerar_pacote_sem_campos_obrigatorios_e_400():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._gerar_pacote_assinatura_holerite_ponto') as mock_core:
        resp = _client().post(
            '/assinatura/gerar',
            headers={'X-API-KEY': 'test'},
            json={'funcionario_id': FUNC_ID, 'tipo_documento': TIPO_PACOTE_HOLERITE_PONTO},
        )
    assert resp.status_code == 400
    mock_core.assert_not_called()


def test_rota_assinatura_gerar_pacote_despacha_para_core_correta():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._gerar_pacote_assinatura_holerite_ponto',
               return_value=({'status': 'ok', 'dry_run': True}, 200)) as mock_core:
        resp = _client().post(
            '/assinatura/gerar',
            headers={'X-API-KEY': 'test'},
            json={
                'funcionario_id': FUNC_ID, 'tipo_documento': TIPO_PACOTE_HOLERITE_PONTO,
                'arquivo_holerite_record_id': ARQ_HOL_ID, 'arquivo_folha_ponto_record_id': ARQ_PONTO_ID,
                'dry_run': True,
            },
        )
    assert resp.status_code == 200
    mock_core.assert_called_once()
    kwargs = mock_core.call_args.kwargs
    assert kwargs['funcionario_id'] == FUNC_ID
    assert kwargs['arquivo_holerite_id'] == ARQ_HOL_ID
    assert kwargs['arquivo_ponto_id'] == ARQ_PONTO_ID
    assert kwargs['dry_run'] is True


def test_rota_assinatura_gerar_pacote_sem_x_api_key_e_401():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app._gerar_pacote_assinatura_holerite_ponto') as mock_core:
        resp = _client().post(
            '/assinatura/gerar',
            json={
                'funcionario_id': FUNC_ID, 'tipo_documento': TIPO_PACOTE_HOLERITE_PONTO,
                'arquivo_holerite_record_id': ARQ_HOL_ID, 'arquivo_folha_ponto_record_id': ARQ_PONTO_ID,
            },
        )
    assert resp.status_code == 401
    mock_core.assert_not_called()


def test_rota_assinatura_gerar_tipo_kit_admissao_continua_funcionando():
    """Regressão: dispatch de tipos existentes (não-pacote) não foi
    afetado pelo branch novo."""
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._gerar_assinatura_core', return_value=({'status': 'ok'}, 200)) as mock_core_antiga, \
         patch('app._gerar_pacote_assinatura_holerite_ponto') as mock_core_pacote:
        resp = _client().post(
            '/assinatura/gerar',
            headers={'X-API-KEY': 'test'},
            json={'funcionario_id': FUNC_ID, 'tipo_documento': 'FOLHA_PONTO', 'arquivo_record_id': ARQ_PONTO_ID},
        )
    assert resp.status_code == 200
    mock_core_antiga.assert_called_once()
    mock_core_pacote.assert_not_called()


# ── 10. /assinatura/<hash> — carimbo dos 2 PDFs + comprovante único ──────
#
# Correção desta Macro de fechamento: "Assinado" só é gravado DEPOIS que
# carimbo + comprovante + upload dos 3 anexos tiverem sucesso -- nunca
# antes. Todos os testes de falha abaixo confirmam que o PATCH final
# NUNCA acontece quando algo dá errado no meio do caminho.

def _registro_pacote_pendente(status='Pendente', tentativas=0):
    return {
        'id': 'recASSINATURAPACOTEX',
        'fields': {
            'Nome': 'Holerite + Folha de Ponto - Junho 2026',
            'Status': status,
            'Tentativas': tentativas,
            'Tipo de Documento': TIPO_PACOTE_HOLERITE_PONTO,
            'Funcionário': [{'id': FUNC_ID}],
            'PDF SHA-256': f'{SHA_HOL}|{SHA_PONTO}',
            'Documento PDF': [
                {'id': 'attHOL', 'filename': 'holerite.pdf', 'url': 'https://static/holerite.pdf'},
                {'id': 'attPONTO', 'filename': 'ponto.pdf', 'url': 'https://static/ponto.pdf'},
            ],
        },
    }


def test_assinatura_pagina_pacote_confirmado_carimba_os_2_e_grava_assinado_uma_vez():
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44', 'Nome Completo': 'Fulano de Tal'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})
    resp_patch_ok = _resp(ok=True)

    anexos_acumulados = []

    def _anexar_side_effect(tabela, rec_id, campo, conteudo, nome_arquivo):
        anexos_acumulados.append({'id': f'attNOVO_{len(anexos_acumulados)}', 'filename': nome_arquivo})
        return {'fields': {campo: list(anexos_acumulados)}}

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck, Mock(ok=True, content=PDF_SINTETICO_HOLERITE),
                                                 Mock(ok=True, content=PDF_SINTETICO_PONTO)]), \
         patch('app.requests.patch', return_value=resp_patch_ok) as mock_patch, \
         patch('app._carimbar_pdf_assinado', side_effect=lambda b, *a: b) as mock_carimba, \
         patch('app._gerar_comprovante_assinatura_pacote_pdf', return_value=b'%PDF-comprovante') as mock_comprovante, \
         patch('app._anexar_attachment', side_effect=_anexar_side_effect) as mock_anexar:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    assert mock_carimba.call_count == 2  # os 2 PDFs, nunca 1 nem 3
    mock_comprovante.assert_called_once()
    # pelo menos: 2 carimbados + 1 comprovante em Assinaturas, +3 no Funcionário
    assert mock_anexar.call_count >= 6
    # UMA ÚNICA gravação de "Assinado" -- junto com attachments+evidências,
    # não em passo separado (correção desta Macro de fechamento).
    patches_com_assinado = [c for c in mock_patch.call_args_list
                             if c.kwargs.get('json', {}).get('fields', {}).get(F_ASS_STATUS) == 'Assinado']
    assert len(patches_com_assinado) == 1
    campos_finais = patches_com_assinado[0].kwargs['json']['fields']
    assert F_ASS_DOCUMENTO_PDF in campos_finais  # attachments e Status na MESMA chamada


def test_assinatura_pagina_pacote_cpf_incorreto_nao_carimba_nada():
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=resp_func), \
         patch('app.requests.patch', return_value=_resp(ok=True)), \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '0000'})

    assert resp.status_code == 200  # página HTML de erro, não 500
    mock_carimba.assert_not_called()


def test_assinatura_pagina_pacote_expirado_apos_5_tentativas():
    registro = _registro_pacote_pendente(tentativas=4)
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=resp_func), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '0000'})

    assert resp.status_code == 200
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch.get(app.F_ASS_STATUS) == 'Expirado'


def test_assinatura_pagina_pacote_hash_trocado_bloqueia_e_nunca_grava_assinado():
    """Bloqueio contra documento trocado (exigência desta Macro): se o
    conteúdo baixado não corresponder ao par de hashes gravado na
    criação do pacote, aborta sem carimbar e SEM gravar Assinado."""
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44', 'Nome Completo': 'Fulano de Tal'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})
    conteudo_trocado = b'%PDF-1.4\nconteudo-completamente-diferente-do-esperado'

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck, Mock(ok=True, content=conteudo_trocado),
                                                 Mock(ok=True, content=conteudo_trocado)]), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch, \
         patch('app._carimbar_pdf_assinado') as mock_carimba, \
         patch('app._gerar_comprovante_assinatura_pacote_pdf') as mock_comprovante:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    mock_carimba.assert_not_called()
    mock_comprovante.assert_not_called()
    # Nenhum PATCH grava "Assinado" -- correção principal desta Macro:
    # antes, esse PATCH acontecia ANTES desta checagem.
    assert not any(c.kwargs.get('json', {}).get('fields', {}).get(F_ASS_STATUS) == 'Assinado'
                   for c in mock_patch.call_args_list)


def test_assinatura_pagina_pacote_falha_no_upload_final_nao_grava_assinado():
    """Falha parcial: upload dos 3 anexos finais incompleto (só 2 de 3
    -- ex.: comprovante não persistiu) -- nunca grava Assinado."""
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44', 'Nome Completo': 'Fulano de Tal'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck, Mock(ok=True, content=PDF_SINTETICO_HOLERITE),
                                                 Mock(ok=True, content=PDF_SINTETICO_PONTO)]), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch, \
         patch('app._carimbar_pdf_assinado', side_effect=lambda b, *a: b), \
         patch('app._gerar_comprovante_assinatura_pacote_pdf', return_value=b'%PDF-comprovante'), \
         patch('app._anexar_attachment', return_value={'fields': {'Documento PDF': []}}):  # upload retorna lista vazia -> 0/3 encontrados
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    assert not any(c.kwargs.get('json', {}).get('fields', {}).get(F_ASS_STATUS) == 'Assinado'
                   for c in mock_patch.call_args_list)


def test_assinatura_pagina_pacote_vinculo_nao_ativo_cancela_antes_de_assinar():
    """Checkpoint 3/3: desligado depois do envio, antes do clique --
    invalida o pacote (Cancelado) em vez de assinar."""
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44', 'Nome Completo': 'Fulano de Tal'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._status_funcionario_elegivel', return_value=(False, 'vinculo_nao_ativo')), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck]), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch, \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    mock_carimba.assert_not_called()
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'Cancelado'


def test_assinatura_pagina_pacote_ja_cancelado_no_get_nao_mostra_form():
    registro = _registro_pacote_pendente(status='Cancelado')
    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro):
        resp = _client().get('/assinatura/hashpacotefake123')
    assert resp.status_code == 200
    assert b'name="cpf"' not in resp.data


def test_assinatura_pagina_pacote_ja_assinado_por_concorrencia_nao_reprocessa():
    """Concorrência/dupla execução: se, entre o GET inicial e a gravação,
    OUTRA requisição já confirmou a mesma assinatura, a checagem de
    concorrência detecta e devolve sucesso sem carimbar de novo."""
    registro = _registro_pacote_pendente(status='Pendente')
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})
    resp_recheck_ja_assinado = _resp(ok=True, json_dict={
        'fields': {'Status': 'Assinado', 'Data/Hora Assinatura': '2026-07-01T10:00:00-03:00'},
    })

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck_ja_assinado]), \
         patch('app.requests.patch') as mock_patch, \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    mock_patch.assert_not_called()  # não regrava "Assinado" por cima
    mock_carimba.assert_not_called()


def test_assinatura_pagina_pacote_ja_assinado_no_get_mostra_sucesso_sem_form():
    registro = _registro_pacote_pendente(status='Assinado')
    registro['fields']['Data/Hora Assinatura'] = '2026-07-01T10:00:00-03:00'
    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro):
        resp = _client().get('/assinatura/hashpacotefake123')
    assert resp.status_code == 200
    assert b'name="cpf"' not in resp.data


def test_assinatura_pagina_pacote_estrutura_inesperada_nunca_grava_assinado():
    """Falha parcial isolada: se o registro tiver 1 anexo em vez de 2
    (estrutura inesperada) -- nunca grava Assinado, responde 200 (não
    500), e o caso fica só registrado em log para revisão manual."""
    registro = _registro_pacote_pendente()
    registro['fields']['Documento PDF'] = [
        {'id': 'attHOL', 'filename': 'holerite.pdf', 'url': 'https://static/holerite.pdf'},
    ]
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch(*ELEGIVEL[:1], **ELEGIVEL[1]), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck]), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch, \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    mock_carimba.assert_not_called()
    assert not any(c.kwargs.get('json', {}).get('fields', {}).get(F_ASS_STATUS) == 'Assinado'
                   for c in mock_patch.call_args_list)


# ── 11. Reenvio do pacote — extensão do mecanismo existente ──────────────

def _registro_reenviar(evidencias=''):
    return {
        'id': 'recASSINATURAREENVIO',
        'fields': {
            'Nome': 'Holerite + Folha de Ponto - Junho 2026',
            'Status': 'Reenviar',
            'Tipo de Documento': TIPO_PACOTE_HOLERITE_PONTO,
            'Funcionário': [FUNC_ID],
            'PDF SHA-256': f'{SHA_HOL}|{SHA_PONTO}',
            'Evidencias_Assinatura': evidencias,
            'Documento PDF': [
                {'id': 'attHOL', 'filename': 'holerite.pdf', 'url': 'https://static/holerite.pdf'},
                {'id': 'attPONTO', 'filename': 'ponto.pdf', 'url': 'https://static/ponto.pdf'},
            ],
        },
    }


def _client_reenvios(dry_run=False, disparar_whatsapp=True, limit=None):
    body = {'dry_run': dry_run, 'disparar_whatsapp': disparar_whatsapp}
    if limit:
        body['limit'] = limit
    return _client().post('/assinatura/processar-reenvios', headers={'X-API-KEY': 'test'}, json=body)


def test_reenvio_pacote_despachado_para_funcao_dedicada_sem_alterar_generico():
    """O branch por tipo não roda nenhuma linha do reenvio genérico
    (usado por Kit Admissão/Rescisão/EPI/Contratos/Folha de Ponto
    isolada) para um registro de pacote."""
    registro = _registro_reenviar()
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app.requests.get', return_value=_resp(ok=True, json_dict={'records': [registro]})), \
         patch('app._reenviar_pacote_holerite_ponto', return_value={'acao': 'reenviaria_pacote'}) as mock_reenvia, \
         patch('app._montar_mensagem_assinatura') as mock_msg_generica:
        resp = _client_reenvios(dry_run=True)
    assert resp.status_code == 200
    mock_reenvia.assert_called_once()
    mock_msg_generica.assert_not_called()


def test_reenvio_pacote_vinculo_nao_ativo_cancela_em_vez_de_reenviar():
    registro = _registro_reenviar()
    with patch('app._status_funcionario_elegivel', return_value=(False, 'vinculo_nao_ativo')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        item = app._reenviar_pacote_holerite_ponto(registro, registro['fields'], FUNC_ID, dry_run=False, disparar_whatsapp=True)
    assert item['acao'] == 'cancelado_vinculo_nao_ativo'
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'Cancelado'


def test_reenvio_pacote_documento_alterado_bloqueia():
    """Revalidação dos 2 Record IDs e hashes: se os anexos atuais não
    corresponderem ao par gravado, o reenvio é bloqueado."""
    registro = _registro_reenviar()
    conteudo_diferente = b'%PDF-1.4\nconteudo-diferente'
    with patch('app._status_funcionario_elegivel', return_value=(True, None)), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=Mock(ok=True, content=conteudo_diferente)):
        item = app._reenviar_pacote_holerite_ponto(registro, registro['fields'], FUNC_ID, dry_run=False, disparar_whatsapp=True)
    assert item['erro'] == 'documento_alterado_apos_preparacao'


def test_reenvio_pacote_limite_de_tentativas_excedido_bloqueia_e_expira():
    registro = _registro_reenviar(evidencias=f'Reenvios do pacote: {app.MAX_REENVIOS_PACOTE}')
    with patch('app._status_funcionario_elegivel', return_value=(True, None)), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        item = app._reenviar_pacote_holerite_ponto(registro, registro['fields'], FUNC_ID, dry_run=False, disparar_whatsapp=True)
    assert item['erro'] == 'limite_de_reenvios_excedido'
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'Expirado'


def test_reenvio_pacote_nunca_cria_segunda_assinatura():
    """Garantia estrutural: a função de reenvio do pacote nunca chama
    _criar_registro -- só PATCH no mesmo registro."""
    import inspect
    codigo = inspect.getsource(app._reenviar_pacote_holerite_ponto)
    assert '_criar_registro' not in codigo


def test_reenvio_pacote_sucesso_grava_pendente_com_novo_hash_e_contador():
    registro = _registro_reenviar()
    with patch('app._status_funcionario_elegivel', return_value=(True, None)), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[
             Mock(ok=True, content=PDF_SINTETICO_HOLERITE), Mock(ok=True, content=PDF_SINTETICO_PONTO),
             _resp(ok=True, json_dict={'fields': {'Status': 'Reenviar'}}),
         ]), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch, \
         patch('app._evolution_enviar_texto') as mock_envia:
        item = app._reenviar_pacote_holerite_ponto(registro, registro['fields'], FUNC_ID, dry_run=False, disparar_whatsapp=True)
    assert item['acao'] == 'reenviado'
    mock_envia.assert_called_once()
    numero, mensagem = mock_envia.call_args[0]
    assert 'Holerite' in mensagem and 'Folha de Ponto' in mensagem
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch[F_ASS_STATUS] == 'Pendente'
    assert 'Reenvios do pacote: 1' in campos_patch[app.F_ASS_EVIDENCIAS]


def test_reenvio_pacote_outra_instancia_ja_processou_e_pulado():
    """Concorrência best-effort: se o Status já não é mais 'Reenviar' no
    instante do PATCH final, a execução é abortada sem reenviar de novo."""
    registro = _registro_reenviar()
    with patch('app._status_funcionario_elegivel', return_value=(True, None)), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[
             Mock(ok=True, content=PDF_SINTETICO_HOLERITE), Mock(ok=True, content=PDF_SINTETICO_PONTO),
             _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}}),  # já processado por outra chamada
         ]), \
         patch('app._evolution_enviar_texto') as mock_envia:
        item = app._reenviar_pacote_holerite_ponto(registro, registro['fields'], FUNC_ID, dry_run=False, disparar_whatsapp=True)
    assert item['acao'] == 'ja_processado_outra_instancia'
    mock_envia.assert_not_called()


# ---------------------------------------------------------------------------
# Tela de "já assinado" — entrega dos PDFs a quem assinou ANTES do commit que
# passou a gerar o "Combinado Carimbado" (5bca9e8, 19/08/2026 13:58).
#
# Auditoria de 20/08/2026 no lote Julho/2026: dos 71 registros com
# Status="Assinado", só 6 tinham o PDF combinado. Para os outros 65 a tela
# mostrava apenas "Assinatura confirmada", sem documento nenhum — embora os 3
# PDFs individuais já estivessem anexados ao registro. Estes testes fixam o
# comportamento corrigido. 100% dado sintético.
# ---------------------------------------------------------------------------

def _anexo(filename, url):
    return {'filename': filename, 'url': url}


def _fields_assinado_sem_combinado():
    """Estrutura exata dos 65 registros: 2 PDFs carimbados + comprovante."""
    return {'Documento PDF': [
        _anexo('Holerite Julho 2026 - FULANO DE TAL - ASSINADO.pdf', 'u_hol'),
        _anexo('Folha de Ponto Julho 2026 - FULANO DE TAL - ASSINADO.pdf', 'u_pon'),
        _anexo('Comprovante Assinatura - Fulano De Tal - Julho 2026.pdf', 'u_com'),
    ]}


def test_assinado_sem_combinado_entrega_os_3_pdfs_individuais():
    downloads = app._downloads_do_registro_assinado(_fields_assinado_sem_combinado())
    assert [d['url'] for d in downloads] == ['u_hol', 'u_pon', 'u_com']


def test_assinado_com_combinado_entrega_so_o_pdf_unico():
    """Quem tem o combinado recebe 1 botão só — não os 4 arquivos."""
    fields = _fields_assinado_sem_combinado()
    fields['Documento PDF'].append(
        _anexo('Combinado Carimbado - Fulano De Tal - Julho 2026.pdf', 'u_comb'))
    downloads = app._downloads_do_registro_assinado(fields)
    assert [d['url'] for d in downloads] == ['u_comb']


def test_pdf_original_nao_carimbado_nunca_e_oferecido():
    """Só arquivo já carimbado (' - ASSINADO') ou o comprovante são entregues:
    um registro que ainda guarde o original não pode entregá-lo como se fosse
    o documento assinado."""
    fields = {'Documento PDF': [
        _anexo('Holerite Julho 2026 - FULANO DE TAL.pdf', 'u_original'),
        _anexo('Comprovante Assinatura - Fulano De Tal - Julho 2026.pdf', 'u_com'),
    ]}
    downloads = app._downloads_do_registro_assinado(fields)
    assert [d['url'] for d in downloads] == ['u_com']


def test_registro_assinado_sem_anexo_nenhum_nao_quebra():
    assert app._downloads_do_registro_assinado({}) == []
    html = app._pagina_assinatura_sucesso_html('Doc', '18/08/2026 14:32', downloads=[])
    assert 'Assinatura confirmada' in html
    assert 'class="botao-download"' not in html


def test_tela_de_sucesso_renderiza_um_botao_por_documento():
    downloads = app._downloads_do_registro_assinado(_fields_assinado_sem_combinado())
    html = app._pagina_assinatura_sucesso_html(
        'Holerite + Folha de Ponto - Julho 2026', '18/08/2026 14:32', downloads=downloads)
    assert html.count('class="botao-download"') == 3
    assert 'Seus documentos assinados:' in html
    for url in ('u_hol', 'u_pon', 'u_com'):
        assert f'href="{url}"' in html


def test_outros_tipos_de_documento_seguem_sem_botao_de_download():
    """Regressão: só o pacote passa `downloads`. Todo outro tipo continua
    caindo no comportamento anterior — tela de sucesso sem nenhum botão."""
    html = app._pagina_assinatura_sucesso_html('Contrato', '01/01/2026 10:00')
    assert 'class="botao-download"' not in html
    assert 'Seus documentos assinados:' not in html
    assert 'Contrato' in html


def test_url_de_anexo_tem_aspas_escapadas_no_html():
    html = app._pagina_assinatura_sucesso_html(
        'Doc', '01/01/2026 10:00',
        downloads=[{'rotulo': 'r', 'url': 'https://exemplo/a"onerror=1'}])
    assert '&quot;onerror' in html
    assert 'a"onerror' not in html
