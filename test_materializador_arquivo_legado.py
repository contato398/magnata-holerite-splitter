"""
Materializador Documental Generico Owner-Aware V1.

Cobre `MaterializadorArquivoLegadoAirtable.materializar` (Documento
canonico + destinatario -> registro utilizavel em TABLE_ARQUIVOS legado).
`requests` sempre mockado -- nenhuma chamada real ao Airtable.

100% dado sintetico -- nenhum CPF/nome/telefone real em nenhum lugar
deste arquivo. IDs (recXXXX) sao inventados.
"""
import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
from magnata_os.documental.modulo01.armazenamento import HashInconsistente
from magnata_os.documental.modulo01.adapters.materializador_arquivo_legado import (
    F_ARQ_ATTACH,
    F_ARQ_FUNCIONARIO_OWNER,
    F_ARQ_HASH,
    TABLE_ARQUIVOS,
    ErroMaterializacaoAirtable,
    MaterializadorArquivoLegadoAirtable,
)
from magnata_os.documental.modulo01.materializador_arquivo import (
    AmbiguidadeMaterializacao,
    OwnerAusenteMaterializacao,
    OwnerMalformadoMaterializacao,
    TamanhoInconsistente,
)


CONTEUDO = b'%PDF-1.4\nconteudo-sintetico-de-teste-do-materializador' * 3
HASH_REAL = hashlib.sha256(CONTEUDO).hexdigest()
FUNC_A = 'recFUNCIONARIOA0001'
FUNC_B = 'recFUNCIONARIOB0002'
ARQ_EXISTENTE = 'recARQUIVOEXISTENTE1'


def _documento(hash_sha256=HASH_REAL, tamanho=len(CONTEUDO), documento_id='docSINTETICO0001'):
    agora = datetime.now(timezone.utc)
    return Documento(
        documento_id=documento_id,
        arquivo_original=f'memoria://{hash_sha256}',
        nome_original='documento-sintetico.pdf',
        mime_type='application/pdf',
        tamanho=tamanho,
        hash_sha256=hash_sha256,
        origem='teste',
        recebido_em=agora,
        lote_id=None,
        status=StatusDocumento.REGISTRADO,
        correlation_id='corr-teste',
        criado_em=agora,
        atualizado_em=agora,
    )


def _resp(ok=True, status_code=200, json_dict=None):
    r = Mock()
    r.ok = ok
    r.status_code = status_code
    r.json.return_value = json_dict or {}
    return r


def _registro(record_id, owner=None, com_attachment=True, hash_sha256=HASH_REAL):
    fields = {F_ARQ_HASH: hash_sha256}
    if owner is not None:
        fields[F_ARQ_FUNCIONARIO_OWNER] = owner
    if com_attachment:
        fields[F_ARQ_ATTACH] = [{'url': 'https://dl.airtable.com/fake.pdf', 'filename': 'x.pdf'}]
    return {'id': record_id, 'fields': fields}


def _materializador():
    return MaterializadorArquivoLegadoAirtable(api_key_provider=lambda: 'chave-fake-de-teste')


# ── Validação antes de qualquer rede ────────────────────────────────────

def test_documento_id_vazio_bloqueia_antes_de_rede():
    doc = _documento(documento_id='')
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        with pytest.raises(ValueError):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_get.assert_not_called()
    mock_post.assert_not_called()


def test_hash_invalido_bloqueia_antes_de_rede():
    doc = _documento(hash_sha256='nao-e-um-hash-valido')
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        with pytest.raises(ValueError):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_get.assert_not_called()
    mock_post.assert_not_called()


def test_funcionario_id_invalido_bloqueia_antes_de_rede():
    doc = _documento()
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        with pytest.raises(ValueError):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id='nao-e-record-id')
    mock_get.assert_not_called()
    mock_post.assert_not_called()


def test_conteudo_vazio_bloqueia_antes_de_rede():
    doc = _documento()
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        with pytest.raises(ValueError):
            _materializador().materializar(documento=doc, conteudo_bytes=b'', funcionario_id=FUNC_A)
    mock_get.assert_not_called()
    mock_post.assert_not_called()


def test_tamanho_divergente_levanta_tamanho_inconsistente_antes_de_rede():
    doc = _documento(tamanho=len(CONTEUDO) + 1)
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        with pytest.raises(TamanhoInconsistente):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_get.assert_not_called()
    mock_post.assert_not_called()


def test_hash_divergente_levanta_hashinconsistente_importada_antes_de_rede():
    hash_errado = hashlib.sha256(b'outro conteudo qualquer').hexdigest()
    doc = _documento(hash_sha256=hash_errado)
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        with pytest.raises(HashInconsistente):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_get.assert_not_called()
    mock_post.assert_not_called()


# ── Reuso / recuperação / criação ────────────────────────────────────────

def test_documento_valido_cria_registro_com_exatamente_1_owner():
    doc = _documento()
    with patch('requests.get', return_value=_resp(json_dict={'records': []})), \
         patch('requests.post') as mock_post:
        mock_post.side_effect = [
            _resp(json_dict={'id': 'recArquivoNovo0001'}),  # criar registro
            _resp(json_dict={}),  # upload attachment
        ]
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=True,
        ):
            resultado = _materializador().materializar(
                documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A,
            )
    assert resultado.reutilizado is False
    assert resultado.arquivo_record_id == 'recArquivoNovo0001'
    campos_criacao = mock_post.call_args_list[0].kwargs['json']['fields']
    assert campos_criacao[F_ARQ_FUNCIONARIO_OWNER] == [FUNC_A]


def test_mesmo_hash_mesmo_owner_attachment_presente_reutiliza():
    doc = _documento()
    candidatos = [_registro(ARQ_EXISTENTE, owner=[FUNC_A], com_attachment=True)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        resultado = _materializador().materializar(
            documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A,
        )
    assert resultado.reutilizado is True
    assert resultado.arquivo_record_id == ARQ_EXISTENTE
    mock_post.assert_not_called()  # nenhuma escrita nova


def test_mesmo_hash_mesmo_owner_attachment_ausente_completa_upload_no_mesmo_record():
    doc = _documento()
    candidatos = [_registro(ARQ_EXISTENTE, owner=[FUNC_A], com_attachment=False)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        mock_post.return_value = _resp(json_dict={})
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=True,
        ):
            resultado = _materializador().materializar(
                documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A,
            )
    assert resultado.reutilizado is True
    assert resultado.arquivo_record_id == ARQ_EXISTENTE
    assert mock_post.call_count == 1  # só o upload, nenhum POST de criação
    url_chamada = mock_post.call_args_list[0].args[0]
    assert ARQ_EXISTENTE in url_chamada
    assert 'uploadAttachment' in url_chamada


def test_retry_apos_falha_de_upload_nao_cria_segundo_record():
    """Simula: 1ª chamada cria metadados mas a falha ocorre entre
    criação e upload (registro fica órfão, sem attachment). 2ª chamada
    (retry) com o MESMO Documento/owner deve completar o mesmo record,
    nunca criar outro."""
    doc = _documento()
    candidatos_orfao = [_registro(ARQ_EXISTENTE, owner=[FUNC_A], com_attachment=False)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos_orfao})), \
         patch('requests.post') as mock_post:
        mock_post.return_value = _resp(json_dict={})
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=True,
        ):
            resultado = _materializador().materializar(
                documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A,
            )
    assert resultado.arquivo_record_id == ARQ_EXISTENTE
    assert resultado.reutilizado is True
    # Nenhuma chamada de criação de registro novo (só 1 POST: o upload).
    assert mock_post.call_count == 1


def test_mesmo_hash_outro_owner_valido_pode_criar_novo_record_para_destinatario_atual():
    doc = _documento()
    candidatos = [_registro('recARQUIVODEOUTROFUNC', owner=[FUNC_B], com_attachment=True)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        mock_post.side_effect = [
            _resp(json_dict={'id': 'recArquivoNovoParaA01'}),
            _resp(json_dict={}),
        ]
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=True,
        ):
            resultado = _materializador().materializar(
                documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A,
            )
    assert resultado.reutilizado is False
    assert resultado.arquivo_record_id == 'recArquivoNovoParaA01'


# ── Fail-closed de ownership ─────────────────────────────────────────────

def test_owner_ausente_em_candidato_e_fail_closed():
    doc = _documento()
    candidatos = [_registro(ARQ_EXISTENTE, owner=None, com_attachment=True)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        with pytest.raises(OwnerAusenteMaterializacao):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_post.assert_not_called()


def test_owner_multiplo_em_candidato_e_fail_closed():
    doc = _documento()
    candidatos = [_registro(ARQ_EXISTENTE, owner=[FUNC_A, FUNC_B], com_attachment=True)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        with pytest.raises(OwnerMalformadoMaterializacao):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_post.assert_not_called()


def test_owner_malformado_em_candidato_e_fail_closed():
    doc = _documento()
    candidatos = [_registro(ARQ_EXISTENTE, owner=['nao-e-record-id'], com_attachment=True)]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        with pytest.raises(OwnerMalformadoMaterializacao):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_post.assert_not_called()


def test_dois_candidatos_exatos_levanta_ambiguidade():
    doc = _documento()
    candidatos = [
        _registro('recARQ0001', owner=[FUNC_A], com_attachment=True),
        _registro('recARQ0002', owner=[FUNC_A], com_attachment=True),
    ]
    with patch('requests.get', return_value=_resp(json_dict={'records': candidatos})), \
         patch('requests.post') as mock_post:
        with pytest.raises(AmbiguidadeMaterializacao):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_post.assert_not_called()


# ── Falhas de rede nunca produzem sucesso falso ─────────────────────────

def test_falha_de_get_na_busca_nao_cria_nada():
    doc = _documento()
    with patch('requests.get', return_value=_resp(ok=False, status_code=503)), \
         patch('requests.post') as mock_post:
        with pytest.raises(ErroMaterializacaoAirtable):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    mock_post.assert_not_called()


def test_falha_na_criacao_nao_produz_falsa_resposta_de_sucesso():
    doc = _documento()
    with patch('requests.get', return_value=_resp(json_dict={'records': []})), \
         patch('requests.post', return_value=_resp(ok=False, status_code=500)):
        with pytest.raises(ErroMaterializacaoAirtable):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)


def test_falha_no_upload_nao_produz_falsa_resposta_de_sucesso():
    doc = _documento()
    with patch('requests.get', return_value=_resp(json_dict={'records': []})), \
         patch('requests.post') as mock_post:
        mock_post.side_effect = [
            _resp(json_dict={'id': 'recArquivoNovo0002'}),  # criar registro ok
            _resp(ok=False, status_code=500),  # upload falha
        ]
        with pytest.raises(ErroMaterializacaoAirtable):
            _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)


def test_falha_na_confirmacao_do_attachment_nao_produz_falsa_resposta_de_sucesso():
    doc = _documento()
    with patch('requests.get', return_value=_resp(json_dict={'records': []})), \
         patch('requests.post') as mock_post:
        mock_post.side_effect = [
            _resp(json_dict={'id': 'recArquivoNovo0003'}),
            _resp(json_dict={}),
        ]
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=False,
        ):
            with pytest.raises(ErroMaterializacaoAirtable):
                _materializador().materializar(documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)


# ── ResultadoMaterializacao — campos corretos ────────────────────────────

def test_resultado_ecoa_documento_id_funcionario_id_hash():
    doc = _documento(documento_id='docECOTESTE0001')
    with patch('requests.get', return_value=_resp(json_dict={'records': []})), \
         patch('requests.post') as mock_post:
        mock_post.side_effect = [
            _resp(json_dict={'id': 'recArquivoEco0001'}),
            _resp(json_dict={}),
        ]
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=True,
        ):
            resultado = _materializador().materializar(
                documento=doc, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A,
            )
    assert resultado.documento_id == 'docECOTESTE0001'
    assert resultado.funcionario_id == FUNC_A
    assert resultado.hash_sha256 == HASH_REAL


# ── Nenhuma decisão de reuso por filename/competência/nome/tamanho ──────

def test_busca_de_candidatos_usa_apenas_hash_nunca_nome_do_documento():
    """Dois Documentos com hash IGUAL mas nome_original DIFERENTE devem
    ser tratados como o mesmo conteúdo para fins de busca — a formula
    de busca depende só do hash, nunca do nome."""
    doc1 = _documento(documento_id='docA')
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        mock_get.return_value = _resp(json_dict={'records': []})
        mock_post.side_effect = [_resp(json_dict={'id': 'recX'}), _resp(json_dict={})]
        with patch.object(
            MaterializadorArquivoLegadoAirtable, '_confirmar_attachment', return_value=True,
        ):
            _materializador().materializar(documento=doc1, conteudo_bytes=CONTEUDO, funcionario_id=FUNC_A)
    formula_usada = mock_get.call_args.kwargs['params']['filterByFormula']
    assert HASH_REAL in formula_usada
    assert doc1.nome_original not in formula_usada
