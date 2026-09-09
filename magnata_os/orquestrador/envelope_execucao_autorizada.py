"""Envelope recuperavel e verificavel de uma ``AcaoEnvio`` autorizada.

O envelope e JSON UTF-8 canonico, imutavel e enderecado pelo SHA-256 de seus
bytes. Destinatario, texto e nome existem somente no blob protegido; a tabela
operacional conserva hashes e a referencia do envelope. Midia fica em blob
separado, enderecado por ``conteudo_sha256``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Optional

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos
from magnata_os.documental.modulo01.armazenamento import ArquivoNaoEncontrado

from .autorizacao_gate import DecisaoGate, RegistroAutorizacaoGate
from .plano_comunicacao import AcaoEnvio
from .politica_comunicacao import hash_conteudo_comunicacao, hash_texto_comunicacao


class EnvelopeExecucaoError(ValueError):
    """Envelope ausente, adulterado ou incompatível com a ação autorizada."""


@dataclasses.dataclass(frozen=True)
class IdentidadesAcao:
    destinatario_sha256: str
    nome_sha256: Optional[str]
    conteudo_sha256: Optional[str]
    texto_sha256: Optional[str]


def _sha256_texto_exato(valor: str) -> str:
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def calcular_identidades_acao(acao: AcaoEnvio) -> IdentidadesAcao:
    """Fonte única dos hashes usados pelo envelope e pelo repositório."""
    destinatario = str(acao.destinatario or '').strip()
    if not destinatario:
        raise EnvelopeExecucaoError('destinatario canonico e obrigatorio')
    nome_sha256 = _sha256_texto_exato(acao.nome) if acao.nome else None
    if acao.tipo == 'texto':
        return IdentidadesAcao(
            destinatario_sha256=_sha256_texto_exato(destinatario),
            nome_sha256=nome_sha256,
            conteudo_sha256=None,
            texto_sha256=hash_texto_comunicacao(acao.texto),
        )
    try:
        conteudo_sha256 = hash_conteudo_comunicacao(acao.conteudo)
    except (TypeError, ValueError) as exc:
        raise EnvelopeExecucaoError('acao de midia exige conteudo binario integro') from exc
    return IdentidadesAcao(
        destinatario_sha256=_sha256_texto_exato(destinatario),
        nome_sha256=nome_sha256,
        conteudo_sha256=conteudo_sha256,
        texto_sha256=(hash_texto_comunicacao(acao.legenda) if acao.legenda else None),
    )


@dataclasses.dataclass(frozen=True)
class EnvelopeExecucaoAutorizadaV1:
    schema_version: int
    acao_execucao_id: str
    event_id: str
    preview_id: str
    autorizacao_id: str
    ordem: int
    tipo: str
    destinatario: str
    texto: str
    legenda: str
    nome_arquivo: str
    destinatario_sha256: str
    texto_sha256: Optional[str]
    nome_sha256: Optional[str]
    conteudo_sha256: Optional[str]


_CAMPOS = tuple(campo.name for campo in dataclasses.fields(EnvelopeExecucaoAutorizadaV1))


def criar_envelope_v1(*, registro, acao: AcaoEnvio) -> EnvelopeExecucaoAutorizadaV1:
    ids = calcular_identidades_acao(acao)
    observadas = (
        ids.destinatario_sha256, ids.nome_sha256,
        ids.conteudo_sha256, ids.texto_sha256,
    )
    persistidas = (
        registro.destinatario_sha256, registro.nome_sha256,
        registro.conteudo_sha256, registro.texto_sha256,
    )
    if observadas != persistidas:
        raise EnvelopeExecucaoError('acao diverge das identidades persistidas')
    return EnvelopeExecucaoAutorizadaV1(
        schema_version=1,
        acao_execucao_id=registro.acao_execucao_id,
        event_id=registro.event_id,
        preview_id=registro.preview_id,
        autorizacao_id=registro.autorizacao_id,
        ordem=registro.ordem,
        tipo=registro.tipo,
        destinatario=str(acao.destinatario or '').strip(),
        texto=acao.texto if acao.tipo == 'texto' else '',
        legenda=acao.legenda if acao.tipo != 'texto' else '',
        nome_arquivo=acao.nome,
        destinatario_sha256=ids.destinatario_sha256,
        texto_sha256=ids.texto_sha256,
        nome_sha256=ids.nome_sha256,
        conteudo_sha256=ids.conteudo_sha256,
    )


def serializar_envelope_v1(envelope: EnvelopeExecucaoAutorizadaV1) -> bytes:
    return json.dumps(
        dataclasses.asdict(envelope), sort_keys=True, separators=(',', ':'),
        ensure_ascii=True,
    ).encode('utf-8')


def desserializar_envelope_v1(conteudo: bytes) -> EnvelopeExecucaoAutorizadaV1:
    try:
        bruto = json.loads(bytes(conteudo).decode('utf-8'))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EnvelopeExecucaoError('envelope nao e JSON UTF-8 valido') from exc
    if not isinstance(bruto, dict) or set(bruto) != set(_CAMPOS):
        raise EnvelopeExecucaoError('campos do envelope V1 sao invalidos')
    if bruto.get('schema_version') != 1:
        raise EnvelopeExecucaoError('schema_version do envelope nao suportada')
    try:
        return EnvelopeExecucaoAutorizadaV1(**bruto)
    except TypeError as exc:
        raise EnvelopeExecucaoError('estrutura do envelope V1 invalida') from exc


def armazenar_acao_e_envelope_v1(
    *, armazenamento: ArmazenamentoArquivos, registro, acao: AcaoEnvio,
) -> str:
    """Armazena mídia e envelope antes de qualquer escrita no banco."""
    envelope = criar_envelope_v1(registro=registro, acao=acao)
    if envelope.conteudo_sha256 is not None:
        conteudo = bytes(acao.conteudo)
        armazenamento.armazenar(
            envelope.conteudo_sha256, conteudo, 'application/octet-stream',
            'conteudo-acao-v1.bin', len(conteudo),
        )
    bytes_envelope = serializar_envelope_v1(envelope)
    envelope_sha256 = hashlib.sha256(bytes_envelope).hexdigest()
    armazenamento.armazenar(
        envelope_sha256, bytes_envelope, 'application/json',
        'envelope-execucao-v1.json', len(bytes_envelope),
    )
    return envelope_sha256


def _ler_bytes(armazenamento: ArmazenamentoArquivos, hash_sha256: str) -> bytes:
    try:
        with armazenamento.abrir_leitura(hash_sha256) as arquivo:
            return arquivo.read()
    except ArquivoNaoEncontrado as exc:
        raise EnvelopeExecucaoError('blob recuperavel nao encontrado') from exc


def recuperar_acao_verificada_v1(
    *, armazenamento: ArmazenamentoArquivos, registro,
    autorizacao: RegistroAutorizacaoGate,
) -> AcaoEnvio:
    """Recupera e valida integralmente antes de qualquer claim."""
    if not registro.envelope_sha256:
        raise EnvelopeExecucaoError('acao legada sem envelope recuperavel')
    if (
        autorizacao.decisao != DecisaoGate.AUTORIZADO
        or autorizacao.autorizacao_id != registro.autorizacao_id
        or autorizacao.event_id != registro.event_id
        or autorizacao.preview_id != registro.preview_id
    ):
        raise EnvelopeExecucaoError('autorizacao AUTORIZADO exata nao encontrada')

    bytes_envelope = _ler_bytes(armazenamento, registro.envelope_sha256)
    if hashlib.sha256(bytes_envelope).hexdigest() != registro.envelope_sha256:
        raise EnvelopeExecucaoError('hash do envelope recuperado diverge')
    envelope = desserializar_envelope_v1(bytes_envelope)
    vinculos = (
        envelope.acao_execucao_id, envelope.event_id, envelope.preview_id,
        envelope.autorizacao_id, envelope.ordem, envelope.tipo,
    )
    esperados = (
        registro.acao_execucao_id, registro.event_id, registro.preview_id,
        registro.autorizacao_id, registro.ordem, registro.tipo,
    )
    if vinculos != esperados:
        raise EnvelopeExecucaoError('vinculos do envelope divergem da acao persistida')

    conteudo = None
    if registro.tipo != 'texto':
        if not envelope.conteudo_sha256:
            raise EnvelopeExecucaoError('envelope de midia sem conteudo_sha256')
        conteudo = _ler_bytes(armazenamento, envelope.conteudo_sha256)
        if hash_conteudo_comunicacao(conteudo) != envelope.conteudo_sha256:
            raise EnvelopeExecucaoError('conteudo recuperado diverge do hash autorizado')
    acao = AcaoEnvio(
        destinatario=envelope.destinatario,
        ordem=envelope.ordem,
        tipo=envelope.tipo,
        nome=envelope.nome_arquivo,
        conteudo=conteudo,
        texto=envelope.texto,
        legenda=envelope.legenda,
    )
    ids = calcular_identidades_acao(acao)
    identidade_envelope = (
        envelope.destinatario_sha256, envelope.nome_sha256,
        envelope.conteudo_sha256, envelope.texto_sha256,
    )
    identidade_registro = (
        registro.destinatario_sha256, registro.nome_sha256,
        registro.conteudo_sha256, registro.texto_sha256,
    )
    identidade_calculada = (
        ids.destinatario_sha256, ids.nome_sha256,
        ids.conteudo_sha256, ids.texto_sha256,
    )
    if identidade_envelope != identidade_registro or identidade_calculada != identidade_registro:
        raise EnvelopeExecucaoError('hashes do envelope divergem da acao autorizada')
    return acao
