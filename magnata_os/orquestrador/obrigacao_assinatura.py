"""Porta de obrigação de assinatura eletrônica, V1.

Mesmo padrão de `autorizacao_gate.RepositorioAutorizacoesGate`: um Protocol
puro no domínio, sem conhecer o backend concreto. O motor legado (Airtable)
é implementado por um adapter fora deste módulo -- ver
`adapters/obrigacao_assinatura_legado_http.py`. Este arquivo nunca importa
Flask, requests, Airtable, credenciais ou `app.py`.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Protocol


@dataclasses.dataclass(frozen=True)
class ObrigacaoAssinatura:
    """Retorno opaco da consulta/criação de uma obrigação de assinatura.

    Nunca carrega CPF, nome de campo do backend concreto, credencial ou
    URL de anexo bruta -- só o que o domínio precisa para decidir e para
    compor a mensagem exata autorizada no preview.
    """

    assinatura_id: str
    link: str
    status: str
    tem_comprovante: bool
    evidencia_opaca: Optional[str] = None


class PortaObrigacaoAssinatura(Protocol):
    """Contrato mínimo entre o Orquestrador e o motor de assinatura.

    `criar_ou_recuperar` é o único método com efeito colateral possível
    (cria a obrigação se não existir; se existir com a mesma identidade,
    token e correlação, recupera sem duplicar). `consultar_por_correlacao`
    é estritamente somente leitura -- nunca pode criar nada, mesmo se a
    obrigação não existir.
    """

    def criar_ou_recuperar(
        self,
        *,
        token_reservado: str,
        acao_execucao_id: str,
        funcionario_id: str,
        tipo_documento: str,
        arquivo_record_id: str,
    ) -> ObrigacaoAssinatura:
        ...

    def consultar_por_correlacao(
        self, *, acao_execucao_id: str,
    ) -> Optional[ObrigacaoAssinatura]:
        ...
