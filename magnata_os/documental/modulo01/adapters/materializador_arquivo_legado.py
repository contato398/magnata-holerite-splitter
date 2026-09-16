"""Adapter de ESCRITA ao Airtable legado (`TABLE_ARQUIVOS`) para o
Materializador Documental Generico Owner-Aware V1.

Nunca importa `app.py` (legado protegido, CLAUDE.md §7). IDs de
tabela/campo duplicados aqui deliberadamente -- mesmo custo ja aceito em
`magnata_os/documental/importacao_lote/adapters/airtable_escrita.py`
("IDs de tabela/campo duplicados aqui, nao importados de app.py"). Se o
schema do Airtable mudar, os dois lugares precisam ser atualizados
separadamente -- registrado, nao escondido.

Reaproveita os DOIS mecanismos HTTP ja usados em producao (app.py):
busca por `filterByFormula` (padrao de `_buscar_por_campo`) e upload de
attachment via `content.airtable.com/.../uploadAttachment` (padrao de
`_anexar_attachment`) -- reimplementados aqui, nunca importados, pela
mesma razao de nao-import de app.py.

Nenhuma chamada real e feita pelos testes deste modulo -- toda cobertura
usa `unittest.mock`/monkeypatch em `requests.get/post`, nunca rede real.
"""
from __future__ import annotations

import base64
import hashlib
import re
from typing import Callable, Optional

import requests

from ..dominio import Documento
from ..materializador_arquivo import (
    AmbiguidadeMaterializacao,
    HashInconsistente,
    OwnerAusenteMaterializacao,
    OwnerMalformadoMaterializacao,
    ResultadoMaterializacao,
    TamanhoInconsistente,
)

BASE_ID = 'appaCpIVj7Q97VhFy'
TABLE_ARQUIVOS = 'tblRsvhz8oOcUqhkv'
F_ARQ_NOME = 'fldjVGYri7DZDJuee'
F_ARQ_HASH = 'fldOB09YlKDEqKSFO'
F_ARQ_ATTACH = 'fldm6S1xnp8S6sKFE'
F_ARQ_FUNCIONARIO_OWNER = 'fldq2Ne6bLaQX9w8y'

# Mesmo padrao tolerante ja usado em app.py (_RE_RECORD_ID): Record IDs
# reais do Airtable sao sempre 'rec' + 14 alfanumericos, mas a suite de
# testes deste repositorio usa IDs sinteticos de tamanho variavel -- o
# que importa e rejeitar valor vazio, prefixo errado ou caractere nao
# alfanumerico, nunca replicar o comprimento exato de producao.
_RE_RECORD_ID = re.compile(r'^rec[A-Za-z0-9]{6,}$')
_RE_HASH_SHA256 = re.compile(r'^[0-9a-f]{64}$')


class ErroMaterializacaoAirtable(Exception):
    """Falha de rede/HTTP contra o Airtable durante a materializacao --
    nunca produz um ResultadoMaterializacao parcial; propaga sempre."""


def _validar_entrada(documento: Documento, conteudo_bytes: bytes, funcionario_id: str) -> None:
    """Validacao obrigatoria ANTES de qualquer chamada de rede -- nunca
    confia apenas no que o chamador afirma sem recalcular."""
    if not documento.documento_id:
        raise ValueError('documento.documento_id vazio')
    if not documento.hash_sha256 or not _RE_HASH_SHA256.match(documento.hash_sha256):
        raise ValueError(f'documento.hash_sha256 invalido: {documento.hash_sha256!r}')
    if not funcionario_id or not _RE_RECORD_ID.match(funcionario_id):
        raise ValueError(f'funcionario_id invalido: {funcionario_id!r}')
    if not conteudo_bytes:
        raise ValueError('conteudo_bytes vazio')
    if len(conteudo_bytes) != documento.tamanho:
        raise TamanhoInconsistente(
            f'len(conteudo_bytes)={len(conteudo_bytes)} != documento.tamanho={documento.tamanho}'
        )
    hash_real = hashlib.sha256(conteudo_bytes).hexdigest()
    if hash_real != documento.hash_sha256:
        raise HashInconsistente(
            f'sha256(conteudo_bytes)={hash_real} != documento.hash_sha256={documento.hash_sha256}'
        )


def _classificar_owner(campos: dict) -> Optional[str]:
    """Retorna o Record ID do owner se exatamente 1 owner valido estiver
    presente. Levanta OwnerAusenteMaterializacao/OwnerMalformadoMaterializacao
    para qualquer estado que nao seja "exatamente 1 owner valido" --
    nunca descarta esses candidatos em silencio (ver docstring do modulo
    de contrato: owner indeterminavel pode ser exatamente a mesma
    relacao documento-destinatario que estamos materializando)."""
    valor = campos.get(F_ARQ_FUNCIONARIO_OWNER, None)
    if valor is None or not isinstance(valor, list) or len(valor) == 0:
        raise OwnerAusenteMaterializacao(
            f'candidato com hash igual tem F_ARQ_FUNCIONARIO_OWNER ausente/vazio: {campos!r}'
        )
    if len(valor) > 1:
        raise OwnerMalformadoMaterializacao(
            f'candidato com hash igual tem owner multiplo: {valor!r}'
        )
    owner_id = valor[0]
    if not isinstance(owner_id, str) or not _RE_RECORD_ID.match(owner_id):
        raise OwnerMalformadoMaterializacao(
            f'candidato com hash igual tem owner malformado: {owner_id!r}'
        )
    return owner_id


class MaterializadorArquivoLegadoAirtable:
    """Implementacao real de `MaterializadorArquivoLegado` contra o
    Airtable legado (`TABLE_ARQUIVOS`)."""

    def __init__(self, api_key_provider: Callable[[], str], timeout: int = 30, timeout_upload: int = 60):
        self._api_key_provider = api_key_provider
        self._timeout = timeout
        self._timeout_upload = timeout_upload

    def _headers(self) -> dict:
        return {'Authorization': f'Bearer {self._api_key_provider()}'}

    def _headers_json(self) -> dict:
        return {'Authorization': f'Bearer {self._api_key_provider()}', 'Content-Type': 'application/json'}

    def _buscar_candidatos_por_hash(self, hash_sha256: str) -> list:
        formula = f'{{Hash do Anexo}}="{hash_sha256}"'
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ARQUIVOS}',
            headers=self._headers(),
            params={'filterByFormula': formula},
            timeout=self._timeout,
        )
        if not r.ok:
            raise ErroMaterializacaoAirtable(f'GET candidatos por hash falhou: HTTP {r.status_code}')
        return r.json().get('records', [])

    def _criar_registro(self, documento: Documento, funcionario_id: str) -> str:
        r = requests.post(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ARQUIVOS}',
            headers=self._headers_json(),
            json={
                'fields': {
                    F_ARQ_NOME: documento.nome_original,
                    F_ARQ_HASH: documento.hash_sha256,
                    F_ARQ_FUNCIONARIO_OWNER: [funcionario_id],
                }
            },
            timeout=self._timeout,
        )
        if not r.ok:
            raise ErroMaterializacaoAirtable(f'POST criar registro falhou: HTTP {r.status_code}')
        arquivo_record_id = r.json().get('id')
        if not arquivo_record_id:
            raise ErroMaterializacaoAirtable('POST criar registro nao devolveu id')
        return arquivo_record_id

    def _upload_attachment(self, arquivo_record_id: str, documento: Documento, conteudo_bytes: bytes) -> None:
        r = requests.post(
            f'https://content.airtable.com/v0/{BASE_ID}/{arquivo_record_id}/{F_ARQ_ATTACH}/uploadAttachment',
            headers=self._headers_json(),
            json={
                'contentType': documento.mime_type,
                'filename': documento.nome_original,
                'file': base64.b64encode(conteudo_bytes).decode('utf-8'),
            },
            timeout=self._timeout_upload,
        )
        if not r.ok:
            raise ErroMaterializacaoAirtable(f'POST uploadAttachment falhou: HTTP {r.status_code}')

    def _confirmar_attachment(self, arquivo_record_id: str) -> bool:
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ARQUIVOS}/{arquivo_record_id}',
            headers=self._headers(),
            timeout=self._timeout,
        )
        if not r.ok:
            raise ErroMaterializacaoAirtable(f'GET confirmar attachment falhou: HTTP {r.status_code}')
        anexos = r.json().get('fields', {}).get(F_ARQ_ATTACH) or []
        return bool(anexos)

    def materializar(
        self,
        *,
        documento: Documento,
        conteudo_bytes: bytes,
        funcionario_id: str,
    ) -> ResultadoMaterializacao:
        _validar_entrada(documento, conteudo_bytes, funcionario_id)

        candidatos = self._buscar_candidatos_por_hash(documento.hash_sha256)

        exatos = []
        for registro in candidatos:
            campos = registro.get('fields', {})
            owner_id = _classificar_owner(campos)  # levanta se ausente/multiplo/malformado
            if owner_id == funcionario_id:
                exatos.append(registro)
            # owner valido e diferente de funcionario_id: ignorado só
            # para este destinatario, nunca bloqueia a operacao inteira.

        if len(exatos) > 1:
            raise AmbiguidadeMaterializacao(
                f'{len(exatos)} candidatos com hash={documento.hash_sha256} '
                f'e owner={funcionario_id} — nunca escolhido silenciosamente'
            )

        if len(exatos) == 1:
            candidato = exatos[0]
            arquivo_record_id = candidato['id']
            anexos = candidato.get('fields', {}).get(F_ARQ_ATTACH) or []
            if anexos:
                return ResultadoMaterializacao(
                    arquivo_record_id=arquivo_record_id,
                    documento_id=documento.documento_id,
                    funcionario_id=funcionario_id,
                    hash_sha256=documento.hash_sha256,
                    reutilizado=True,
                )
            # Registro orfao de uma falha anterior entre criacao e
            # upload -- completa so o upload faltante, nunca cria outro.
            self._upload_attachment(arquivo_record_id, documento, conteudo_bytes)
            if not self._confirmar_attachment(arquivo_record_id):
                raise ErroMaterializacaoAirtable(
                    f'attachment nao confirmado apos upload em {arquivo_record_id}'
                )
            return ResultadoMaterializacao(
                arquivo_record_id=arquivo_record_id,
                documento_id=documento.documento_id,
                funcionario_id=funcionario_id,
                hash_sha256=documento.hash_sha256,
                reutilizado=True,
            )

        # Nenhum candidato exato e nenhum candidato bloqueante sobreviveu
        # (qualquer owner ausente/multiplo/malformado ja levantou acima).
        arquivo_record_id = self._criar_registro(documento, funcionario_id)
        self._upload_attachment(arquivo_record_id, documento, conteudo_bytes)
        if not self._confirmar_attachment(arquivo_record_id):
            raise ErroMaterializacaoAirtable(
                f'attachment nao confirmado apos criacao em {arquivo_record_id}'
            )
        return ResultadoMaterializacao(
            arquivo_record_id=arquivo_record_id,
            documento_id=documento.documento_id,
            funcionario_id=funcionario_id,
            hash_sha256=documento.hash_sha256,
            reutilizado=False,
        )
