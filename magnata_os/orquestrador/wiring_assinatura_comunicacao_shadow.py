"""Wiring canônico Assinatura -> Comunicação WhatsApp, V1 shadow.

Prova a composição ponta a ponta exigida pela missão:

    intenção → otimização → token reservado → preview exato →
    autorização persistida → obrigação de assinatura (adapter) →
    PlanoDisparo → Envelope Executável → persistência

sempre parando ANTES de qualquer transporte real (Evolution) ou serviço
real (Airtable/Render) -- mesmo sufixo `_shadow` e mesmo espírito de
`wiring_prestacao_orquestrador_postgres_shadow.py`, mas sem depender do
domínio de Prestação de Contas (evitaria misturar módulos -- CLAUDE.md
§7): a intenção de assinatura nasce diretamente de uma ordem do operador,
não de um `PacotePrestacaoCliente`.

Não conhece Flask, Evolution, Airtable, requests nem credenciais -- a
obrigação de assinatura é criada através de `PortaObrigacaoAssinatura`
injetada (fake em teste/shadow; `AdapterObrigacaoAssinaturaLegadoHttp` em
produção, fora desta função).
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import secrets
from datetime import datetime

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos

from .autorizacao_gate import (
    DecisaoGate,
    RegistroAutorizacaoGate,
    RepositorioAutorizacoesGate,
)
from .envelope_execucao_autorizada import armazenar_acao_e_envelope_v1
from .obrigacao_assinatura import ObrigacaoAssinatura, PortaObrigacaoAssinatura
from .plano_comunicacao import AcaoEnvio, PlanoDisparo, montar_plano_disparo
from .politica_comunicacao import PreviewComunicacao, montar_preview_comunicacao
from .repositorio_acoes_execucao_plano_postgres import (
    RegistroAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
    criar_registro_acao_plano,
)


class WiringAssinaturaComunicacaoError(ValueError):
    """Composição incompatível com o wiring shadow de assinatura."""


def gerar_token_reservado_csprng() -> str:
    """CSPRNG real, nunca dado humano. 32 bytes (256 bits), Base64
    URL-safe canônico -- exatamente o formato exigido por
    `_validar_reserva_assinatura` (PR #150). Nunca logado pelo chamador."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('ascii')


@dataclasses.dataclass(frozen=True)
class ResultadoWiringAssinaturaShadow:
    preview: PreviewComunicacao
    autorizacao: RegistroAutorizacaoGate
    obrigacao: ObrigacaoAssinatura
    plano: PlanoDisparo
    acao_persistida: RegistroAcaoExecucaoPlano
    envelope_sha256: str


def montar_intencao_assinatura_shadow(
    *, destinatario: str, texto_sem_link: str, token_reservado: str,
) -> tuple[str, PreviewComunicacao]:
    """Monta o texto exato (com o link já embutido, usando o token
    reservado ANTES do preview -- exatamente a ordem que resolve o
    conflito preview-vs-link documentado no ADR do fluxo WhatsApp) e a
    prévia determinística correspondente. Sem I/O."""
    if not token_reservado:
        raise WiringAssinaturaComunicacaoError('token_reservado é obrigatório antes do preview')
    link = f'/assinatura/{token_reservado}'
    texto_exato = f'{texto_sem_link.strip()} {link}'.strip()
    preview = montar_preview_comunicacao(
        destinatarios=(destinatario,), texto=texto_exato, itens=(),
        assinatura=True, comprovante=True, preferencia='separado',
    )
    return texto_exato, preview


def autorizar_preview_assinatura_shadow(
    *,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    preview: PreviewComunicacao,
    event_id: str,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
) -> RegistroAutorizacaoGate:
    """Registra o fato de autorização (append-only, idempotente) vinculado
    ao `preview_id` exato -- mudar texto/destinatário/composição depois
    disso invalida a autorização (hash diferente, `preview_id` diferente)."""
    autorizacao = RegistroAutorizacaoGate(
        autorizacao_id=hashlib.sha256(
            f'{event_id}|{preview.preview_id}|{ator_referencia}'.encode('utf-8')
        ).hexdigest(),
        event_id=event_id, preview_id=preview.preview_id,
        decisao=DecisaoGate.AUTORIZADO, ator_referencia=ator_referencia,
        registrado_em=instante, proveniencia=proveniencia,
    )
    repositorio_autorizacoes.registrar_se_novo(autorizacao)
    return autorizacao


def materializar_assinatura_shadow(
    *,
    porta_assinatura: PortaObrigacaoAssinatura,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    armazenamento: ArmazenamentoArquivos,
    preview: PreviewComunicacao,
    autorizacao: RegistroAutorizacaoGate,
    texto_exato: str,
    token_reservado: str,
    funcionario_id: str,
    tipo_documento: str,
    arquivo_record_id: str,
    event_id: str,
    instante: datetime,
) -> ResultadoWiringAssinaturaShadow:
    """Composição completa até a persistência da ação, sem transporte:

    preview autorizado → PlanoDisparo → identidade determinística da ação
    (mesma derivação de `criar_registro_acao_plano`, fonte única de
    verdade) → cria/recupera obrigação com o MESMO token e a MESMA
    correlação (`acao_execucao_id`) já derivada → envelope armazenado →
    ação persistida (PENDING, elegível ao executor real depois, fora
    desta função).

    Correlação nunca é um parâmetro solto do chamador: se fosse, nada
    impediria que a obrigação de assinatura e a ação de transporte
    tivessem identidades diferentes, quebrando o vínculo que o observador
    depende para reconciliar assinatura → conclusão."""
    plano = montar_plano_disparo(
        preview=preview, texto=texto_exato, conteudos=(),
        preview_id_autorizado=autorizacao.preview_id, autorizacao_explicita=True,
    )

    acao = plano.acoes[0]
    registro = criar_registro_acao_plano(
        event_id=event_id, plano=plano, autorizacao=autorizacao,
        acao=acao, criado_em=instante,
    )

    # A obrigação nasce com a MESMA correlação que a ação de transporte
    # vai ter -- derivada primeiro, nunca solta.
    obrigacao = porta_assinatura.criar_ou_recuperar(
        token_reservado=token_reservado, acao_execucao_id=registro.acao_execucao_id,
        funcionario_id=funcionario_id, tipo_documento=tipo_documento,
        arquivo_record_id=arquivo_record_id,
    )

    envelope_sha256 = armazenar_acao_e_envelope_v1(
        armazenamento=armazenamento, registro=registro, acao=acao,
    )
    registro_com_envelope = dataclasses.replace(registro, envelope_sha256=envelope_sha256)

    (acao_persistida,) = repositorio_acoes.materializar_registros(
        registros=(registro_com_envelope,), autorizacao=autorizacao,
    )

    return ResultadoWiringAssinaturaShadow(
        preview=preview, autorizacao=autorizacao, obrigacao=obrigacao,
        plano=plano, acao_persistida=acao_persistida, envelope_sha256=envelope_sha256,
    )
