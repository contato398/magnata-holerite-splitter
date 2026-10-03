"""Adapter concreto de `PortaConsultaStatusAssinaturaPacote`
(`magnata_os/classificacao/politica_reenvio_pacote_holerite_ponto_v1.py`)
sobre o motor legado de assinatura, via a mesma rota HTTP read-only já
usada por `AdapterObrigacaoAssinaturaLegadoHttp`
(`obrigacao_assinatura_legado_http.py`): `GET /assinatura/consulta`.

Único lugar deste adapter autorizado a saber que o backend fala HTTP.
Nunca importa `app.py`, Airtable, Flask nem credenciais -- a URL base e
a chave de API são injetadas pelo chamador, como no adapter irmão.
Reaproveitar `/assinatura/consulta` em vez de ler `TABLE_ASSINATURAS`
direto evita abrir uma segunda leitura concorrente da mesma tabela fora
de `app.py` (ver `orquestrador.md` §3 e §10).
"""
from __future__ import annotations

import dataclasses
from typing import Optional

import requests


class ConsultaStatusAssinaturaPacoteLegadoError(RuntimeError):
    """Falha de rede ou HTTP na consulta read-only de status."""


@dataclasses.dataclass(frozen=True)
class AdapterConsultaStatusAssinaturaPacoteLegadoHttp:
    """Implementa `PortaConsultaStatusAssinaturaPacote` via
    `GET /assinatura/consulta?token_reservado=...`."""

    base_url: str
    api_key: str  # injetada pelo chamador; nunca hardcoded neste arquivo
    timeout_segundos: int = 30

    def _headers(self) -> dict:
        return {'X-API-KEY': self.api_key}

    def status_atual(self, token_reservado: str) -> Optional[str]:
        """Consulta estritamente somente leitura. Devolve `None` quando
        a obrigação não existe (`existe: False` na resposta) -- a
        política pura (`avaliar_concorrencia_reenvio`) já trata `None`
        como "não seguro para prosseguir", mesmo tratamento dado a
        qualquer status diferente de `'Reenviar'`.

        Levanta `ConsultaStatusAssinaturaPacoteLegadoError` em falha de
        rede ou HTTP não-2xx -- nunca devolve `None` nesses casos, para
        que o chamador nunca confunda "falha ao consultar" com
        "obrigação inexistente" (CLAUDE.md §4, "falha nunca é
        silenciosa")."""
        try:
            resposta = requests.get(
                f'{self.base_url}/assinatura/consulta',
                params={'token_reservado': token_reservado},
                headers=self._headers(), timeout=self.timeout_segundos,
            )
        except requests.RequestException as exc:
            raise ConsultaStatusAssinaturaPacoteLegadoError(
                f'falha de rede na consulta read-only de status: {exc}'
            ) from exc
        if not (200 <= resposta.status_code < 300):
            raise ConsultaStatusAssinaturaPacoteLegadoError(
                f'consulta read-only de status falhou: HTTP {resposta.status_code}'
            )
        corpo = resposta.json()
        if not corpo.get('existe'):
            return None
        return corpo.get('status')
