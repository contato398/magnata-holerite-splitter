"""Pacote LÓGICO da Prestação de Contas por cliente (missão "CORREDOR
OPERACIONAL DA PRESTAÇÃO DE CONTAS", Fase 10).

NUNCA gera ZIP/PDF/arquivo físico — representação PURA, construída a
partir do `ResultadoPrestacaoReadiness` já existente
(`prestacao_readiness.py`, reaproveitado sem alteração) + o inventário
já consultado — nunca do filename ou de uma pasta. Reutiliza o
vocabulário de estado do readiness (PRONTO/FALTANDO/REVISAR/
DIVERGENTE) via um mapeamento 1:1 — nunca reimplementa a lógica de
decisão, só empresta um rótulo mais operacional para o conceito de
"pacote" (PRONTO/INCOMPLETO/EM_REVISAO/BLOQUEADO), que ainda não
existia como contrato.

O pacote é sempre formado a partir de INVENTÁRIO + POLÍTICA/READINESS —
nunca inventa item, nunca decide sozinho em caso de ambiguidade (herda
a mesma cautela do readiness: REVISAR vira EM_REVISAO, nunca PRONTO)."""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from typing import Iterable, Optional, Tuple

from .cardinalidade_colaborador_por_tipo import ResultadoObrigatoriedadeDocumental
from .contratos import ReferenciaCanonica, ResultadoResolucaoSemantico
from .holerite_obrigatorio_prestacao import TIPO_HOLERITE, ResultadoObrigatoriedadeHolerite
from .inventario_prestacao import FonteInventarioPrestacao
from .politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from .prestacao_readiness import (
    EntradaPrestacaoReadiness,
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    ResultadoPrestacaoReadiness,
    avaliar_prestacao_readiness,
)


class EstadoPacotePrestacao(str, enum.Enum):
    PRONTO = 'PRONTO'
    INCOMPLETO = 'INCOMPLETO'
    EM_REVISAO = 'EM_REVISAO'
    BLOQUEADO = 'BLOQUEADO'


# Mapeamento 1:1, nunca uma decisão nova -- DIVERGENTE (competência
# incompatível) é tratado como BLOQUEADO (mais grave que "faltando":
# o que está presente nem corresponde ao ciclo pedido).
_ESTADO_PACOTE_POR_READINESS = {
    EstadoPrestacaoReadiness.PRONTO: EstadoPacotePrestacao.PRONTO,
    EstadoPrestacaoReadiness.FALTANDO: EstadoPacotePrestacao.INCOMPLETO,
    EstadoPrestacaoReadiness.REVISAR: EstadoPacotePrestacao.EM_REVISAO,
    EstadoPrestacaoReadiness.DIVERGENTE: EstadoPacotePrestacao.BLOQUEADO,
}


@dataclasses.dataclass(frozen=True)
class PacotePrestacaoCliente:
    """Representação LÓGICA (nunca física) do que existe/falta para UM
    cliente numa competência. `itens_incluidos` é sempre o inventário
    JÁ FILTRADO por cliente/competência (nunca reavaliado aqui)."""

    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    estado: EstadoPacotePrestacao
    itens_incluidos: Tuple[ItemInventarioPrestacao, ...]
    tipos_obrigatorios: Tuple[str, ...]
    tipos_faltantes: Tuple[str, ...] = ()
    motivos: Tuple[str, ...] = ()
    holerite: Optional[ResultadoObrigatoriedadeHolerite] = None
    """Adendo de Regra de Negócio (Holerite): detalhe da obrigatoriedade
    por cardinalidade colaborador, quando avaliada (ver `combinar_
    pacote_com_holerite`) -- `None` quando a avaliação não foi pedida
    (nunca confundir "não avaliado" com "completo")."""

    def __post_init__(self) -> None:
        if any(item.cliente != self.cliente for item in self.itens_incluidos):
            raise ValueError('itens_incluidos so pode conter itens do MESMO cliente do pacote')
        if any(item.competencia != self.competencia for item in self.itens_incluidos):
            raise ValueError('itens_incluidos so pode conter itens da MESMA competencia do pacote')


def montar_pacote_logico(
    readiness: ResultadoPrestacaoReadiness,
    requisitos: Tuple,
    inventario: Tuple[ItemInventarioPrestacao, ...],
) -> PacotePrestacaoCliente:
    """Traduz um `ResultadoPrestacaoReadiness` (já calculado, nunca
    reavaliado aqui) num `PacotePrestacaoCliente`. `requisitos` e
    `inventario` são os MESMOS já usados para calcular `readiness` --
    este módulo nunca torna a consultar política/fonte de inventário."""
    return PacotePrestacaoCliente(
        cliente=readiness.cliente,
        competencia=readiness.competencia,
        estado=_ESTADO_PACOTE_POR_READINESS[readiness.estado],
        itens_incluidos=inventario,
        tipos_obrigatorios=tuple(sorted(r.tipo_documental for r in requisitos)),
        tipos_faltantes=readiness.tipos_faltantes,
        motivos=readiness.motivos,
    )


def avaliar_e_montar_pacote(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    resolucao: Optional[ResultadoResolucaoSemantico],
    fonte_inventario: FonteInventarioPrestacao,
    politica: PoliticaRequisitosPrestacao,
) -> PacotePrestacaoCliente:
    """Orquestração ponta-a-ponta: política + inventário + resolução →
    readiness (`avaliar_prestacao_readiness`, sem alteração) → pacote
    lógico. Mesma composição de `prestacao_shadow.avaliar_prestacao_
    shadow`, só que devolvendo o pacote em vez do readiness cru --
    NUNCA duplica a lógica daquela função, monta a MESMA entrada uma
    única vez.

    `resolucao=None` (evolução do contrato do ciclo de Prestação V1):
    repassado como está para `EntradaPrestacaoReadiness` -- vira
    EM_REVISAO (`sem_evidencia_documental_real`) via
    `avaliar_prestacao_readiness`, nunca uma resolução fabricada aqui
    como substituto."""
    requisitos = politica.requisitos_para(cliente, competencia)
    inventario = fonte_inventario.listar(cliente, competencia)
    readiness = avaliar_prestacao_readiness(
        EntradaPrestacaoReadiness(
            cliente=cliente, competencia=competencia, requisitos=requisitos,
            inventario=inventario, resolucao=resolucao,
        )
    )
    return montar_pacote_logico(readiness, requisitos, inventario)


def combinar_pacote_com_obrigatoriedade_documental(
    pacote: PacotePrestacaoCliente,
    resultado_obrigatoriedade: ResultadoObrigatoriedadeDocumental,
) -> PacotePrestacaoCliente:
    """GENÉRICO: combina um pacote JÁ MONTADO com obrigatoriedade de
    qualquer tipo_documental por cardinalidade colaborador (Holerite,
    Folha de Ponto, etc.).

    Regras (idênticas às do Holerite, agora generalizadas):
    - Se completo (zero faltantes) → retorna pacote inalterado + registro
    - Se incompleto → rebaixa PRONTO→INCOMPLETO, adiciona tipo aos faltantes
    - Nunca upgrada BLOQUEADO/EM_REVISAO (herança de cautela)
    - Nunca promove um pacote já incompleto por outro motivo

    Retorna pacote com estado potencialmente rebaixado, tipos_faltantes
    potencialmente aumentado."""
    if resultado_obrigatoriedade.completo:
        return pacote  # Sem alteração se completo
    novo_estado = pacote.estado
    if novo_estado == EstadoPacotePrestacao.PRONTO:
        novo_estado = EstadoPacotePrestacao.INCOMPLETO
    tipos_faltantes = pacote.tipos_faltantes
    if resultado_obrigatoriedade.tipo_documental not in tipos_faltantes:
        tipos_faltantes = tuple(
            sorted(tipos_faltantes + (resultado_obrigatoriedade.tipo_documental,))
        )
    return dataclasses.replace(
        pacote, estado=novo_estado, tipos_faltantes=tipos_faltantes,
    )


def combinar_pacote_com_holerite(
    pacote: PacotePrestacaoCliente,
    resultado_holerite: ResultadoObrigatoriedadeHolerite,
) -> PacotePrestacaoCliente:
    """COMPATIBILIDADE V1: wrapper que applica lógica Holerite diretamente.

    Não delega à função genérica (pois `ResultadoObrigatoriedadeHolerite`
    não tem `tipo_documental` como field). Mantém assinatura original
    por compatibilidade com consumidores existentes. Campo `holerite`
    no pacote continua sendo preenchido (usado em consumidores que
    precisam inspecionar detalhes de Holerite)."""
    if resultado_holerite.completo:
        return dataclasses.replace(pacote, holerite=resultado_holerite)
    novo_estado = pacote.estado
    if novo_estado == EstadoPacotePrestacao.PRONTO:
        novo_estado = EstadoPacotePrestacao.INCOMPLETO
    tipos_faltantes = pacote.tipos_faltantes
    if TIPO_HOLERITE not in tipos_faltantes:
        tipos_faltantes = tuple(sorted(tipos_faltantes + (TIPO_HOLERITE,)))
    return dataclasses.replace(
        pacote, estado=novo_estado, tipos_faltantes=tipos_faltantes, holerite=resultado_holerite,
    )


# =====================================================================
# PACOTE / INTENÇÃO DE DISTRIBUIÇÃO DE NÍVEL CLIENTE (Prestação upstream
# real V1). Fecha no DOMÍNIO a lacuna do Gate J1b: documentos cuja
# necessidade não tem colaborador (granularidade cliente) nunca entram em
# Ordem de colaborador, mas até aqui também não viravam nada -- só um
# WARNING. Esta intenção é o destino deles: `cliente + competência +
# documentos de nível cliente`, sem `funcionario_id`.
#
# Deliberadamente PARA NA INTENÇÃO: nenhum endereço de destinatário
# (quem recebe é um PAPEL organizacional; o endereço depende de fonte
# canônica de destinatários do cliente, que hoje só existe no legado),
# nenhum canal (e-mail é só o precedente do legado, nunca arquitetura do
# domínio), nenhuma lista de tipos documentais (a granularidade vem da
# NECESSIDADE e da resolução do documento). Puro: sem I/O. Recebe os
# resultados de aquisição por duck typing (`necessidade`,
# `documento_id`, `hash_sha256`) para não criar ciclo de import com a
# composição.
# =====================================================================

VERSAO_INTENCAO_DISTRIBUICAO_CLIENTE = 'intencao-distribuicao-cliente-v1'


class PapelDestinatarioOrganizacional(str, enum.Enum):
    """Quem recebe, como PAPEL -- nunca um endereço. V1 conhece só o
    destinatário institucional do próprio cliente (entidade Cliente como
    "destinatário institucional de documentos coletivos",
    MAGNATA_OS_ENTIDADES.md). Papéis mais finos (financeiro,
    administrativo, contador) dependem de fonte canônica que ainda não
    existe -- não são adivinhados aqui."""

    CLIENTE_INSTITUCIONAL = 'CLIENTE_INSTITUCIONAL'


class IntencaoDistribuicaoClienteError(ValueError):
    """Erro de DOMÍNIO, isolável por cliente: os resultados recebidos não
    formam uma intenção de nível cliente válida."""


class ResultadoComColaboradorNaIntencaoCliente(IntencaoDistribuicaoClienteError):
    """Uma necessidade com colaborador tentou entrar na intenção de
    cliente -- granularidades diferentes nunca se misturam."""


class ResultadoDeOutroClienteOuCompetencia(IntencaoDistribuicaoClienteError):
    """Resultado cuja necessidade é de outro cliente ou competência."""


@dataclasses.dataclass(frozen=True)
class DocumentoIntencaoCliente:
    """1 documento físico da intenção. `tipos_documentais` são os tipos
    das NECESSIDADES que ele satisfaz (vocabulário da necessidade, nunca
    reinterpretado) -- o mesmo documento que atende 2 necessidades do
    cliente aparece 1 vez, com os 2 tipos."""

    documento_id: str
    hash_sha256: str
    tipos_documentais: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not str(self.documento_id or '').strip():
            raise IntencaoDistribuicaoClienteError('documento_id deve ser texto não vazio')
        if not str(self.hash_sha256 or '').strip():
            raise IntencaoDistribuicaoClienteError('hash_sha256 deve ser texto não vazio')
        tipos = tuple(self.tipos_documentais)
        if not tipos or any(not str(t or '').strip() for t in tipos):
            raise IntencaoDistribuicaoClienteError('tipos_documentais exige ao menos 1 tipo não vazio')
        if tipos != tuple(sorted(set(tipos))):
            raise IntencaoDistribuicaoClienteError('tipos_documentais deve ser ordenado e sem repetição')


@dataclasses.dataclass(frozen=True)
class IntencaoDistribuicaoCliente:
    """Intenção de entregar documentos de nível cliente ao destinatário
    ORGANIZACIONAL do cliente numa competência. Nunca carrega
    `funcionario_id`, endereço nem canal."""

    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    papel_destinatario: PapelDestinatarioOrganizacional
    documentos: Tuple[DocumentoIntencaoCliente, ...]

    def __post_init__(self) -> None:
        if self.cliente.tipo_entidade != 'CLIENTE':
            raise IntencaoDistribuicaoClienteError('cliente deve ser referência canônica de CLIENTE')
        if self.competencia.tipo_entidade != 'COMPETENCIA':
            raise IntencaoDistribuicaoClienteError('competencia deve ser referência canônica de COMPETENCIA')
        if not isinstance(self.papel_destinatario, PapelDestinatarioOrganizacional):
            raise IntencaoDistribuicaoClienteError('papel_destinatario deve ser PapelDestinatarioOrganizacional')
        documentos = tuple(self.documentos)
        if not documentos:
            raise IntencaoDistribuicaoClienteError('intenção de cliente exige ao menos 1 documento')
        chaves = [(d.documento_id, d.hash_sha256) for d in documentos]
        if chaves != sorted(set(chaves)):
            raise IntencaoDistribuicaoClienteError(
                'documentos devem estar ordenados por (documento_id, hash_sha256) e sem repetição'
            )
        object.__setattr__(self, 'documentos', documentos)

    @property
    def documento_ids(self) -> Tuple[str, ...]:
        return tuple(d.documento_id for d in self.documentos)

    @property
    def intencao_id(self) -> str:
        """Identidade DETERMINÍSTICA: mesmo cliente/competência/papel/
        documentos -> mesmo id (replay nunca gera intenção "nova"); a
        ordem de chegada dos resultados nunca entra (documentos já são
        canônicos pela invariante acima)."""
        payload = {
            'versao': VERSAO_INTENCAO_DISTRIBUICAO_CLIENTE,
            'cliente': [self.cliente.tipo_entidade, self.cliente.entidade_id],
            'competencia': [self.competencia.tipo_entidade, self.competencia.entidade_id],
            'papel_destinatario': self.papel_destinatario.value,
            'documentos': [
                [d.documento_id, d.hash_sha256, list(d.tipos_documentais)] for d in self.documentos
            ],
        }
        serializado = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serializado.encode('utf-8')).hexdigest()


def montar_intencao_distribuicao_cliente(
    *,
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    resultados_aquisicao: Iterable,
    papel_destinatario: PapelDestinatarioOrganizacional = PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL,
) -> IntencaoDistribuicaoCliente:
    """Monta a intenção a partir de resultados de aquisição JÁ
    ELEGÍVEIS de nível cliente (a elegibilidade continua sendo da
    composição da Prestação, nunca refeita aqui). Fail-closed: qualquer
    resultado com colaborador, ou de outro cliente/competência, derruba a
    intenção inteira desse cliente com erro de domínio -- nunca é
    "filtrado em silêncio" para dentro de uma intenção menor."""
    tipos_por_documento: dict = {}
    for resultado in resultados_aquisicao:
        necessidade = resultado.necessidade
        if necessidade.colaborador is not None:
            raise ResultadoComColaboradorNaIntencaoCliente(
                f'necessidade com colaborador não pertence à intenção de cliente '
                f'(documento_id={resultado.documento_id!r})'
            )
        if necessidade.cliente != cliente or necessidade.competencia != competencia:
            raise ResultadoDeOutroClienteOuCompetencia(
                f'resultado de outro cliente/competência (documento_id={resultado.documento_id!r})'
            )
        chave = (resultado.documento_id, resultado.hash_sha256)
        tipos_por_documento.setdefault(chave, set()).add(necessidade.tipo_documental)

    return IntencaoDistribuicaoCliente(
        cliente=cliente,
        competencia=competencia,
        papel_destinatario=papel_destinatario,
        documentos=tuple(
            DocumentoIntencaoCliente(
                documento_id=documento_id, hash_sha256=hash_sha256,
                tipos_documentais=tuple(sorted(tipos_por_documento[(documento_id, hash_sha256)])),
            )
            for documento_id, hash_sha256 in sorted(tipos_por_documento)
        ),
    )
