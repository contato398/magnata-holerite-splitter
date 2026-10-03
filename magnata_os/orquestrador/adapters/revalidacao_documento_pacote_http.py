"""Adapter concreto de `PortaRevalidacaoDocumentoPacote`
(`magnata_os/classificacao/politica_reenvio_pacote_holerite_ponto_v1.py`)
via download HTTP direto dos anexos.

Mesma técnica já usada em `_reenviar_pacote_holerite_ponto` (`app.py`):
baixar cada anexo pela URL já conhecida (não precisa de credencial do
Airtable -- a URL do anexo já é a forma pronta de acesso) e calcular
SHA-256 do conteúdo. Nenhuma dependência de Flask/Airtable/driver de
banco; só `requests` e `hashlib`, isolados aqui dentro do adapter
(`magnata_os/CLAUDE.md`, "todo serviço externo entra por adapter").
"""
from __future__ import annotations

import dataclasses
import hashlib
from typing import FrozenSet, Tuple

import requests


class RevalidacaoDocumentoPacoteError(RuntimeError):
    """Falha ao baixar ou ler algum dos anexos originais do pacote."""


@dataclasses.dataclass(frozen=True)
class AdapterRevalidacaoDocumentoPacoteHttp:
    """Implementa `PortaRevalidacaoDocumentoPacote` via download HTTP
    simples. `timeout_segundos` replica o mesmo valor já usado em
    `app.py` para este download (60s)."""

    timeout_segundos: int = 60

    def hashes_atuais(self, urls_anexos_originais: Tuple[str, ...]) -> FrozenSet[str]:
        """Baixa cada URL e devolve o conjunto de hashes SHA-256 do
        conteúdo -- nunca assume sucesso: qualquer download que falhe
        (rede, HTTP não-2xx) levanta `RevalidacaoDocumentoPacoteError`
        em vez de devolver um conjunto parcial, que poderia ser
        confundido com "documento alterado" pela política pura."""
        hashes = set()
        for url in urls_anexos_originais:
            try:
                resposta = requests.get(url, timeout=self.timeout_segundos)
            except requests.RequestException as exc:
                raise RevalidacaoDocumentoPacoteError(
                    f'falha de rede ao baixar anexo original: {exc}'
                ) from exc
            if not resposta.ok:
                raise RevalidacaoDocumentoPacoteError(
                    f'download do anexo original falhou: HTTP {resposta.status_code}'
                )
            hashes.add(hashlib.sha256(resposta.content).hexdigest())
        return frozenset(hashes)
