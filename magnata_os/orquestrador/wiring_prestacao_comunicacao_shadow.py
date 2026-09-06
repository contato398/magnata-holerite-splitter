"""Wiring canônico Prestação de Contas -> Comunicação, V1 shadow.

Este módulo faz SOMENTE a ponte entre um ``PacotePrestacaoCliente`` já
avaliado e a infraestrutura genérica de comunicação/orquestração já existente.

Regras duras do V1:
- somente pacote PRONTO pode gerar intenção;
- monta a prévia pela política canônica já existente;
- persiste a intenção pelo ``MotorOrquestrador``;
- ``COMUNICACAO_SOLICITADA`` é HUMAN_REQUIRED, portanto termina em
  ``WAITING_GATE``;
- não importa transporte, Evolution, Flask, Airtable nem requests;
- não envia nada e não materializa ``PlanoDisparo``.

A identidade da intenção é determinística e baseada somente em referências
canônicas/sanitizadas + ``preview_id``. Texto e destinatários nunca entram no
envelope persistido do evento; o ``preview_id`` já vincula exatamente a prévia
que o operador viu.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable, Sequence

from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
)

from .eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from .motor import MotorOrquestrador
from .politica_comunicacao import (
    ItemComunicacao,
    PreferenciaComposicao,
    PreviewComunicacao,
    montar_preview_comunicacao,
)
from .repositorio_execucoes import RegistroExecucao, RepositorioExecucoes


class WiringPrestacaoComunicacaoError(ValueError):
    """Entrada incompatível com o wiring shadow da Prestação."""


@dataclasses.dataclass(frozen=True)
class IntencaoComunicacaoPrestacao:
    """Referência canônica da proposta de comunicação originada na Prestação.

    Não é uma fila WhatsApp. ``canal_preferencial`` expressa a preferência
    operacional atual e pode evoluir sem alterar o contrato da Prestação.
    """

    intencao_id: str
    pacote_id: str
    origem: str
    canal_preferencial: str
    preview: PreviewComunicacao


@dataclasses.dataclass(frozen=True)
class ResultadoWiringPrestacaoComunicacaoShadow:
    intencao: IntencaoComunicacaoPrestacao
    execucao: RegistroExecucao


def _ref_payload(ref) -> list[str]:
    return [ref.tipo_entidade, ref.entidade_id]


def _pacote_payload(pacote: PacotePrestacaoCliente) -> dict:
    itens = []
    for item in pacote.itens_incluidos:
        colaborador = _ref_payload(item.colaborador) if item.colaborador is not None else None
        itens.append({
            'documento_id': item.documento_id,
            'tipo_documental': item.tipo_documental,
            'colaborador': colaborador,
        })
    itens.sort(key=lambda item: (
        item['documento_id'],
        item['tipo_documental'],
        item['colaborador'] or ['', ''],
    ))
    return {
        'cliente': _ref_payload(pacote.cliente),
        'competencia': _ref_payload(pacote.competencia),
        'estado': pacote.estado.value,
        'itens': itens,
        'tipos_obrigatorios': sorted(pacote.tipos_obrigatorios),
        'tipos_faltantes': sorted(pacote.tipos_faltantes),
    }


def _sha256_canonico(payload: dict) -> str:
    serializado = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
    )
    return hashlib.sha256(serializado.encode('utf-8')).hexdigest()


def identidade_pacote_prestacao(pacote: PacotePrestacaoCliente) -> str:
    """Fingerprint estável do pacote lógico, sem filename nem conteúdo binário."""
    return _sha256_canonico(_pacote_payload(pacote))


def identidade_intencao_comunicacao(
    *,
    pacote_id: str,
    preview_id: str,
    origem: str,
    canal_preferencial: str,
) -> str:
    """Identidade da intenção: pacote + prévia exata + contexto operacional."""
    return _sha256_canonico({
        'pacote_id': pacote_id,
        'preview_id': preview_id,
        'origem': origem,
        'canal_preferencial': canal_preferencial,
    })


def registrar_intencao_comunicacao_shadow(
    *,
    pacote: PacotePrestacaoCliente,
    repositorio: RepositorioExecucoes,
    destinatarios: Iterable[str],
    texto: str = '',
    itens: Sequence[ItemComunicacao] = (),
    assinatura: bool,
    comprovante: bool,
    preferencia: PreferenciaComposicao = 'otimizar',
    canal_preferencial: str = 'WHATSAPP',
    instante: datetime | None = None,
) -> ResultadoWiringPrestacaoComunicacaoShadow:
    """Registra em shadow uma intenção e SEMPRE para no gate humano.

    O pacote não envia nada. O preview é montado pela política existente e o
    ``MotorOrquestrador`` registra a intenção com uma chave idempotente.
    Como ``COMUNICACAO_SOLICITADA`` é explicitamente HUMAN_REQUIRED, nenhuma
    ação é registrada e nenhuma camada de transporte participa desta função.
    """
    if pacote.estado != EstadoPacotePrestacao.PRONTO:
        raise WiringPrestacaoComunicacaoError(
            f'somente pacote PRONTO pode propor comunicacao; recebido {pacote.estado.value}'
        )

    canal = str(canal_preferencial or '').strip().upper()
    if not canal:
        raise WiringPrestacaoComunicacaoError('canal_preferencial deve ser texto nao vazio')

    preview = montar_preview_comunicacao(
        destinatarios=destinatarios,
        texto=texto,
        itens=itens,
        assinatura=assinatura,
        comprovante=comprovante,
        preferencia=preferencia,
    )
    pacote_id = identidade_pacote_prestacao(pacote)
    intencao_id = identidade_intencao_comunicacao(
        pacote_id=pacote_id,
        preview_id=preview.preview_id,
        origem='PRESTACAO_CONTAS',
        canal_preferencial=canal,
    )

    agora = instante or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        raise WiringPrestacaoComunicacaoError('instante deve possuir timezone')

    evento = Evento(
        event_id=f'comunicacao:{intencao_id}',
        event_type=TipoEvento.COMUNICACAO_SOLICITADA,
        source='prestacao_contas',
        occurred_at=agora,
        received_at=agora,
        correlation_id=f'pacote:{pacote_id}',
        entity_type='PACOTE_PRESTACAO',
        entity_id=pacote_id,
        payload_referencia=f'intencao:{intencao_id}:preview:{preview.preview_id}',
        sensibilidade=Sensibilidade.INTERNO,
        proveniencia='wiring_prestacao_comunicacao_shadow_v1',
    )

    execucao = MotorOrquestrador(repositorio=repositorio, acoes={}).processar(evento)
    if execucao.estado != EstadoExecucao.WAITING_GATE:
        raise RuntimeError(
            'invariante violada: comunicacao shadow deve terminar em WAITING_GATE'
        )

    return ResultadoWiringPrestacaoComunicacaoShadow(
        intencao=IntencaoComunicacaoPrestacao(
            intencao_id=intencao_id,
            pacote_id=pacote_id,
            origem='PRESTACAO_CONTAS',
            canal_preferencial=canal,
            preview=preview,
        ),
        execucao=execucao,
    )
