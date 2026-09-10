"""Adapter concreto de `PortaObrigacaoAssinatura` sobre o motor legado de
assinatura (rotas HTTP `/assinatura/gerar` e `/assinatura/consulta` de
`app.py`).

Único lugar do pacote autorizado a saber que o backend atual fala HTTP.
Nunca importa `app.py`, Airtable, Flask nem credenciais -- fala com o
serviço já publicado via `requests`, com a URL base e a chave de API
injetadas. Trocar o backend de assinatura no futuro significa escrever um
novo adapter implementando o mesmo `PortaObrigacaoAssinatura`; o
Orquestrador nunca muda.
"""
from __future__ import annotations

import dataclasses

import requests

from ..obrigacao_assinatura import ObrigacaoAssinatura, PortaObrigacaoAssinatura


class ObrigacaoAssinaturaLegadoError(RuntimeError):
    """Falha ao criar/recuperar/consultar a obrigação no motor legado."""


@dataclasses.dataclass(frozen=True)
class AdapterObrigacaoAssinaturaLegadoHttp:
    """Implementa `PortaObrigacaoAssinatura` via HTTP contra `app.py`."""

    base_url: str
    api_key: str  # injetada pelo chamador; nunca hardcoded neste arquivo
    timeout_segundos: int = 30

    def _headers(self) -> dict:
        return {'X-API-KEY': self.api_key, 'Content-Type': 'application/json; charset=utf-8'}

    def criar_ou_recuperar(
        self,
        *,
        token_reservado: str,
        acao_execucao_id: str,
        funcionario_id: str,
        tipo_documento: str,
        arquivo_record_id: str,
    ) -> ObrigacaoAssinatura:
        """Chama `/assinatura/gerar` com `token_reservado` +
        `acao_execucao_id` e `disparar_whatsapp=false` (contrato do PR
        #150) -- único método deste adapter com efeito colateral possível
        (cria a obrigação se não existir; se já existir com a mesma
        identidade/token/correlação, o próprio motor legado devolve a
        existente sem duplicar)."""
        payload = {
            'funcionario_id': funcionario_id,
            'tipo_documento': tipo_documento,
            'arquivo_record_id': arquivo_record_id,
            'token_reservado': token_reservado,
            'acao_execucao_id': acao_execucao_id,
            'disparar_whatsapp': False,
        }
        try:
            resposta = requests.post(
                f'{self.base_url}/assinatura/gerar',
                json=payload, headers=self._headers(), timeout=self.timeout_segundos,
            )
        except requests.RequestException as exc:
            raise ObrigacaoAssinaturaLegadoError(
                f'falha de rede ao criar/recuperar obrigação: {exc}'
            ) from exc
        if not (200 <= resposta.status_code < 300):
            raise ObrigacaoAssinaturaLegadoError(
                f'motor de assinatura recusou a criação/recuperação: HTTP {resposta.status_code}'
            )
        corpo = resposta.json()
        return ObrigacaoAssinatura(
            assinatura_id=corpo.get('assinatura_id') or '',
            link=corpo.get('link') or '',
            status=corpo.get('status', 'ok'),
            tem_comprovante=False,
        )

    def consultar_por_correlacao(
        self, *, acao_execucao_id: str,
    ) -> ObrigacaoAssinatura | None:
        """Chama `GET /assinatura/consulta?acao_execucao_id=...` --
        estritamente somente leitura. Nunca chama `/assinatura/gerar` para
        "consultar": essa rota pode criar estado se a obrigação não
        existir, o que violaria a garantia read-only deste método."""
        try:
            resposta = requests.get(
                f'{self.base_url}/assinatura/consulta',
                params={'acao_execucao_id': acao_execucao_id},
                headers=self._headers(), timeout=self.timeout_segundos,
            )
        except requests.RequestException as exc:
            raise ObrigacaoAssinaturaLegadoError(
                f'falha de rede na consulta read-only: {exc}'
            ) from exc
        if not (200 <= resposta.status_code < 300):
            raise ObrigacaoAssinaturaLegadoError(
                f'consulta read-only falhou: HTTP {resposta.status_code}'
            )
        corpo = resposta.json()
        if not corpo.get('existe'):
            return None
        return ObrigacaoAssinatura(
            assinatura_id=corpo.get('assinatura_id') or '',
            link=corpo.get('link') or '',
            status=corpo.get('status') or '',
            tem_comprovante=bool(corpo.get('comprovante_existe')),
            evidencia_opaca=corpo.get('evidencia_hash'),
        )
