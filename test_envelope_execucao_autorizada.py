"""Contrato puro do Envelope Executável Persistente V1, sem I/O externo."""
import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
)
from magnata_os.orquestrador.autorizacao_gate import (
    DecisaoGate,
    RegistroAutorizacaoGate,
)
from magnata_os.orquestrador.envelope_execucao_autorizada import (
    EnvelopeExecucaoError,
    armazenar_acao_e_envelope_v1,
    criar_envelope_v1,
    desserializar_envelope_v1,
    recuperar_acao_verificada_v1,
    serializar_envelope_v1,
)
from magnata_os.orquestrador.plano_comunicacao import AcaoEnvio, PlanoDisparo
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    criar_registro_acao_plano,
)

AGORA = datetime(2099, 4, 1, tzinfo=timezone.utc)


def _autorizacao(decisao=DecisaoGate.AUTORIZADO):
    return RegistroAutorizacaoGate(
        autorizacao_id='auth-envelope-v1', event_id='evento-envelope-v1',
        preview_id='preview-envelope-v1', decisao=decisao,
        ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='teste:sintetico',
    )


def _acao(tipo='documento'):
    if tipo == 'texto':
        return AcaoEnvio(
            destinatario='destinatario:sintetico', ordem=1, tipo='texto',
            texto='texto sintetico autorizado',
        )
    return AcaoEnvio(
        destinatario='destinatario:sintetico', ordem=1, tipo=tipo,
        nome='arquivo-sintetico.bin', conteudo=b'conteudo-sintetico-v1',
        legenda='legenda sintetica',
    )


def _registro(acao=None):
    acao = acao or _acao()
    plano = PlanoDisparo(
        preview_id='preview-envelope-v1',
        destinatarios=(acao.destinatario,), acoes=(acao,),
        mensagens_por_pessoa=1, total_notificacoes=1,
    )
    return criar_registro_acao_plano(
        event_id='evento-envelope-v1', plano=plano,
        autorizacao=_autorizacao(), acao=acao, criado_em=AGORA,
    )


def _armazenar(acao=None):
    acao = acao or _acao()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    registro = _registro(acao)
    envelope_sha = armazenar_acao_e_envelope_v1(
        armazenamento=armazenamento, registro=registro, acao=acao,
    )
    return armazenamento, dataclasses.replace(
        registro, envelope_sha256=envelope_sha,
    )


def test_envelope_json_e_sha_sao_deterministicos_e_versionados():
    acao = _acao()
    registro = _registro(acao)
    envelope = criar_envelope_v1(registro=registro, acao=acao)
    primeiro = serializar_envelope_v1(envelope)
    segundo = serializar_envelope_v1(envelope)
    assert primeiro == segundo
    assert hashlib.sha256(primeiro).hexdigest() == hashlib.sha256(segundo).hexdigest()
    assert desserializar_envelope_v1(primeiro) == envelope
    assert b'"schema_version":1' in primeiro
    alterado = serializar_envelope_v1(dataclasses.replace(
        envelope, legenda='outra legenda sintetica',
    ))
    assert hashlib.sha256(alterado).hexdigest() != hashlib.sha256(primeiro).hexdigest()


def test_texto_e_midia_sobrevivem_restart_logico_com_mesma_acao():
    for acao in (_acao('texto'), _acao('documento')):
        armazenamento, registro = _armazenar(acao)
        recuperada = recuperar_acao_verificada_v1(
            armazenamento=armazenamento, registro=registro,
            autorizacao=_autorizacao(),
        )
        assert recuperada == acao


@pytest.mark.parametrize(
    'campo,valor',
    (
        ('event_id', 'evento-adulterado'),
        ('preview_id', 'preview-adulterado'),
        ('autorizacao_id', 'auth-adulterada'),
        ('nome_arquivo', 'outro-nome.bin'),
        ('destinatario', 'destinatario:adulterado'),
        ('legenda', 'legenda adulterada'),
    ),
)
def test_adulteracao_de_campo_relevante_bloqueia_antes_do_claim(campo, valor):
    armazenamento, registro = _armazenar()
    bruto = armazenamento._objetos[registro.envelope_sha256]
    dados = json.loads(bruto)
    dados[campo] = valor
    adulterado = json.dumps(
        dados, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
    ).encode()
    novo_hash = hashlib.sha256(adulterado).hexdigest()
    armazenamento._objetos[novo_hash] = adulterado
    registro = dataclasses.replace(registro, envelope_sha256=novo_hash)
    with pytest.raises(EnvelopeExecucaoError):
        recuperar_acao_verificada_v1(
            armazenamento=armazenamento, registro=registro,
            autorizacao=_autorizacao(),
        )


def test_envelope_e_midia_ausentes_ou_adulterados_falham_fechado():
    armazenamento, registro = _armazenar()
    armazenamento._objetos[registro.envelope_sha256] = b'json-adulterado'
    with pytest.raises(EnvelopeExecucaoError):
        recuperar_acao_verificada_v1(
            armazenamento=armazenamento, registro=registro,
            autorizacao=_autorizacao(),
        )

    armazenamento, registro = _armazenar()
    armazenamento.remover(registro.conteudo_sha256)
    with pytest.raises(EnvelopeExecucaoError, match='nao encontrado'):
        recuperar_acao_verificada_v1(
            armazenamento=armazenamento, registro=registro,
            autorizacao=_autorizacao(),
        )

    armazenamento, registro = _armazenar()
    armazenamento._objetos[registro.conteudo_sha256] = b'midia-adulterada'
    with pytest.raises(EnvelopeExecucaoError, match='conteudo recuperado'):
        recuperar_acao_verificada_v1(
            armazenamento=armazenamento, registro=registro,
            autorizacao=_autorizacao(),
        )


def test_schema_desconhecido_e_envelope_legado_sao_inelegiveis():
    armazenamento, registro = _armazenar()
    bruto = json.loads(armazenamento._objetos[registro.envelope_sha256])
    bruto['schema_version'] = 2
    adulterado = json.dumps(
        bruto, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
    ).encode()
    novo_hash = hashlib.sha256(adulterado).hexdigest()
    armazenamento._objetos[novo_hash] = adulterado
    with pytest.raises(EnvelopeExecucaoError, match='schema_version'):
        recuperar_acao_verificada_v1(
            armazenamento=armazenamento,
            registro=dataclasses.replace(registro, envelope_sha256=novo_hash),
            autorizacao=_autorizacao(),
        )
    with pytest.raises(EnvelopeExecucaoError, match='legada'):
        recuperar_acao_verificada_v1(
            armazenamento=armazenamento,
            registro=dataclasses.replace(registro, envelope_sha256=None),
            autorizacao=_autorizacao(),
        )


def test_autorizacao_recusada_ou_divergente_bloqueia():
    armazenamento, registro = _armazenar()
    for autorizacao in (
        _autorizacao(DecisaoGate.RECUSADO),
        dataclasses.replace(_autorizacao(), autorizacao_id='auth-outra'),
    ):
        with pytest.raises(EnvelopeExecucaoError, match='autorizacao'):
            recuperar_acao_verificada_v1(
                armazenamento=armazenamento, registro=registro,
                autorizacao=autorizacao,
            )


def test_metadata_de_blob_e_fixa_e_nao_contem_pii():
    armazenamento, registro = _armazenar()
    assert armazenamento._metadados[registro.envelope_sha256] == {
        'mime_type': 'application/json',
        'nome_original': 'envelope-execucao-v1.json',
        'tamanho': len(armazenamento._objetos[registro.envelope_sha256]),
    }
    metadados = repr(armazenamento._metadados)
    assert 'destinatario:sintetico' not in metadados
    assert 'arquivo-sintetico.bin' not in metadados


def test_migration_0004_e_minima_inerte_nullable_e_sem_indice():
    sql = Path(
        'magnata_os/orquestrador/migrations/'
        '0004_envelope_execucao_autorizada.sql'
    ).read_text(encoding='utf-8')
    assert 'INERTE' in sql
    assert sql.count('ADD COLUMN envelope_sha256 TEXT') == 1
    assert "'^[0-9a-f]{64}$'" in sql
    assert 'CREATE TABLE' not in sql
    assert 'CREATE INDEX' not in sql
    assert 'UPDATE ' not in sql
    assert 'NOT NULL' not in sql
