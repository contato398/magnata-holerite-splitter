"""Política pura de reenvio do pacote Holerite + Folha de Ponto.

Extrai, como funções testáveis isoladas, os gates de decisão hoje
implementados inline em `_reenviar_pacote_holerite_ponto` (`app.py`,
legado protegido, CLAUDE.md raiz §7) -- vínculo ativo, WhatsApp
presente, limite de reenvios, estrutura de anexos/hashes, integridade
do documento e concorrência best-effort. `app.py` não foi tocado; este
é código novo, sem integração ainda (ver
`/mnt/project-files/magnata-os/orquestrador.md` §9).

Diferença deliberada em relação a
`politica_situacao_distribuicao_colaborador_v1.py` (PR #230): a decisão
de reenvio real depende de dois fatos que só existem depois de I/O
(hash dos anexos originais já baixados; status relido do registro
imediatamente antes de gravar, para concorrência). Este módulo nunca
faz esse I/O -- define só o contrato (`Porta...`) que o adapter real
(fora deste módulo, ainda não escrito) terá que implementar, e as
funções puras que decidem a partir do resultado já resolvido. Nenhuma
função aqui importa Flask, Airtable, `requests` ou qualquer driver,
conforme `magnata_os/CLAUDE.md`.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import FrozenSet, Optional, Protocol, Tuple

__all__ = [
    'AcaoReenvioPacote',
    'AvaliacaoPreCondicoesReenvio',
    'avaliar_pre_condicoes_reenvio',
    'avaliar_integridade_documento',
    'avaliar_concorrencia_reenvio',
    'PortaRevalidacaoDocumentoPacote',
    'PortaConsultaStatusAssinaturaPacote',
]


class AcaoReenvioPacote(str, Enum):
    """Vocabulário alinhado ao `item['erro']` (mais específico, nunca
    ambíguo) já produzido por `_reenviar_pacote_holerite_ponto` em
    `app.py`, não ao `item['acao']` -- em `app.py`, LIMITE_REENVIOS
    e ESTRUTURA_INESPERADA compartilham o mesmo `acao='bloqueado_
    para_revisao'` e só se distinguem pelo `erro`; usar esse valor
    aqui evitaria que os dois nomes colidissem no mesmo membro do
    Enum (aliasing), o que faria um dos dois nomes desaparecer."""

    CANCELADO_VINCULO_NAO_ATIVO = 'cancelado_vinculo_nao_ativo'
    WHATSAPP_AUSENTE = 'whatsapp_ausente'
    LIMITE_REENVIOS_EXCEDIDO = 'limite_de_reenvios_excedido'
    ESTRUTURA_INESPERADA = 'estrutura_inesperada'
    DOCUMENTO_ALTERADO_APOS_PREPARACAO = 'documento_alterado_apos_preparacao'
    JA_PROCESSADO_OUTRA_INSTANCIA = 'ja_processado_outra_instancia'
    LIBERADO_PARA_ENVIO = 'liberado_para_envio'


@dataclasses.dataclass(frozen=True)
class AvaliacaoPreCondicoesReenvio:
    """Resultado dos 4 primeiros gates -- todos calculáveis a partir do
    registro já lido, sem nenhum I/O adicional (nem download de
    anexo, nem releitura de status)."""

    acao: AcaoReenvioPacote
    bloqueado: bool


def avaliar_pre_condicoes_reenvio(
    *,
    elegivel: bool,
    whatsapp_presente: bool,
    reenvios_ate_agora: int,
    max_reenvios: int,
    quantidade_anexos_originais: int,
    quantidade_hashes_gravados: int,
) -> AvaliacaoPreCondicoesReenvio:
    """Replica, nesta ordem exata, os 4 gates de
    `_reenviar_pacote_holerite_ponto` que não dependem de nenhum I/O
    além do registro já lido: vínculo ativo -> WhatsApp presente ->
    limite de reenvios -> estrutura de anexos/hashes. A ordem importa
    para reproduzir fielmente o comportamento hoje em produção -- um
    vínculo inativo bloqueia antes mesmo de checar WhatsApp, por
    exemplo, e o limite de reenvios é checado antes de qualquer
    revalidação de documento (CLAUDE.md §4, "automação por confiança").
    """
    if not elegivel:
        return AvaliacaoPreCondicoesReenvio(AcaoReenvioPacote.CANCELADO_VINCULO_NAO_ATIVO, True)
    if not whatsapp_presente:
        return AvaliacaoPreCondicoesReenvio(AcaoReenvioPacote.WHATSAPP_AUSENTE, True)
    if reenvios_ate_agora >= max_reenvios:
        return AvaliacaoPreCondicoesReenvio(AcaoReenvioPacote.LIMITE_REENVIOS_EXCEDIDO, True)
    if quantidade_anexos_originais != 2 or quantidade_hashes_gravados != 2:
        return AvaliacaoPreCondicoesReenvio(AcaoReenvioPacote.ESTRUTURA_INESPERADA, True)
    return AvaliacaoPreCondicoesReenvio(AcaoReenvioPacote.LIBERADO_PARA_ENVIO, False)


def avaliar_integridade_documento(
    hashes_atuais: FrozenSet[str], hashes_gravados: FrozenSet[str],
) -> bool:
    """`True` só quando os anexos originais ainda têm exatamente o
    conjunto de hashes gravado na preparação do pacote -- nunca aceita
    um documento trocado por fora depois da preparação (CLAUDE.md §4,
    "arquivo original é imutável"). `hashes_atuais` é o resultado já
    calculado por `PortaRevalidacaoDocumentoPacote`; esta função nunca
    baixa nada."""
    return hashes_atuais == hashes_gravados


def avaliar_concorrencia_reenvio(status_atual: Optional[str]) -> bool:
    """`True` quando ainda é seguro prosseguir com o reenvio -- ou
    seja, nenhuma outra execução concorrente processou este mesmo
    registro primeiro. Reproduz a checagem best-effort de `app.py`:
    só segue se o status relido imediatamente antes de gravar ainda for
    `'Reenviar'`. `status_atual` é o resultado já lido por
    `PortaConsultaStatusAssinaturaPacote`; mesma limitação já
    documentada no legado -- reduz, não elimina, a janela de corrida."""
    return status_atual == 'Reenviar'


class PortaRevalidacaoDocumentoPacote(Protocol):
    """Porta read-only: calcula o hash de integridade dos anexos
    originais de um pacote, a partir das URLs já conhecidas no
    registro. Único lugar autorizado a saber como baixar o conteúdo
    (hoje, anexo do Airtable) -- as funções puras deste módulo nunca
    importam `requests`/Flask/Airtable."""

    def hashes_atuais(self, urls_anexos_originais: Tuple[str, ...]) -> FrozenSet[str]:
        ...


class PortaConsultaStatusAssinaturaPacote(Protocol):
    """Porta read-only: relê o status atual do registro de assinatura
    do pacote, para a checagem de concorrência best-effort imediatamente
    antes de gravar o reenvio."""

    def status_atual(self, registro_id: str) -> Optional[str]:
        ...
