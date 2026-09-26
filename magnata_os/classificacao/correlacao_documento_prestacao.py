"""J3 -- índice de correlação Documento interno ↔ escopo da Prestação.

Responde, de forma persistida, a pergunta que faltava ao ciclo da
Prestação: "quais Documentos internos são candidatos reais a esta
necessidade (cliente, competência, tipo, colaborador opcional)?".

REUTILIZA o contrato de relação que já existia: `ItemInventarioPrestacao`
(`prestacao_readiness.py`) -- documento_id + tipo + cliente + competência
+ colaborador opcional, com 1 item por cliente legítimo (broadcast,
vínculo múltiplo, transferência de posto no período). O índice é a versão
PERSISTIDA e HISTÓRICA desse inventário, com duas garantias a mais:

  - `documento_id` é sempre um Documento interno (FK no banco; no twin
    em memória, `documento_existe`), nunca um record-id do Airtable;
  - append-only: cada mudança de estado de uma relação vira uma nova
    observação (VIGENTE/SUPERADA), nunca UPDATE/DELETE.

Produtores (fluxo documental existente, nenhum pipeline paralelo):
  - `registrar_correlacoes_do_corredor`: resultado do corredor da
    Prestação (`executar_documento_readonly`), o mesmo que já alimenta o
    sink de inventário -- só itens de documento `RESOLVIDO_E_AVANCOU`
    (regra de `avancar_para_inventario`, nunca refeita aqui);
  - `registrar_correlacoes_de_ponto`: resolução temporal da Folha/Cartão
    de Ponto (`resolucao_temporal_ponto`, 0010 + alocação temporal) --
    1 relação por cliente cuja alocação intersecta o período.

Evidência independente: a relação nasce da resolução do CONTEÚDO do
documento contra as fontes de referência (vínculo, cliente direto,
alocação) no momento da ingestão -- nunca da necessidade que depois vai
consultá-la. A aquisição da Prestação continua revalidando cada candidato
(corredor + `_elegivel_para_distribuicao`): o índice recorta o universo,
nunca substitui as proteções J1/J1b.

Puro: sem driver, sem Airtable, sem rede. O adapter Postgres fica em
`adapters/postgres_correlacao_documento_prestacao.py` e reusa
`planejar_observacoes` -- nenhuma decisão duplicada entre os dois.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Protocol, Tuple

from .contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao
from .prestacao_readiness import ItemInventarioPrestacao

_logger = logging.getLogger(__name__)

ORIGEM_CORREDOR_PRESTACAO = 'corredor_prestacao_v1'
ORIGEM_RESOLUCAO_TEMPORAL_PONTO = 'resolucao_temporal_ponto_v1'

EVENTO_RELACAO_DOCUMENTO_DERIVADO_IGNORADA = 'correlacao_documento_derivado_ignorada'

_COMPETENCIA_RE = re.compile(r'^[0-9]{4}-(0[1-9]|1[0-2])$')


class EstadoCorrelacao(str, enum.Enum):
    VIGENTE = 'VIGENTE'
    SUPERADA = 'SUPERADA'


class CorrelacaoDocumentoPrestacaoError(ValueError):
    """Relação inválida para o índice (fail-closed, nunca gravada)."""


class DocumentoInexistenteNaCorrelacao(CorrelacaoDocumentoPrestacaoError):
    """`documento_id` não é um Documento interno existente."""


def _validar_item(item: ItemInventarioPrestacao) -> None:
    if item.cliente.tipo_entidade != 'CLIENTE':
        raise CorrelacaoDocumentoPrestacaoError('cliente deve ser referência canônica de CLIENTE')
    if item.competencia.tipo_entidade != 'COMPETENCIA' or not _COMPETENCIA_RE.match(item.competencia.entidade_id):
        raise CorrelacaoDocumentoPrestacaoError('competencia deve ser COMPETENCIA no formato AAAA-MM')


def chave_relacao(item: ItemInventarioPrestacao) -> str:
    """Identidade lógica COMPLETA da relação (sha256 canônico). Inclui
    competência e tipo, além da `identidade_logica` do item: o mesmo
    documento com outra competência/tipo resolvidos é outra relação."""
    payload = [
        item.documento_id,
        item.cliente.entidade_id,
        item.competencia.entidade_id,
        item.tipo_documental,
        item.colaborador.entidade_id if item.colaborador is not None else '',
    ]
    serializado = json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(serializado.encode('utf-8')).hexdigest()


@dataclasses.dataclass(frozen=True)
class ObservacaoCorrelacao:
    """1 linha do índice (append-only)."""

    relacao_id: str
    sequencia: int
    item: ItemInventarioPrestacao
    estado: EstadoCorrelacao
    origem: str
    evidencia_sha256: Optional[str]
    registrado_em: datetime


@dataclasses.dataclass(frozen=True)
class ResultadoRegistroCorrelacao:
    novas: int = 0
    reativadas: int = 0
    superadas: int = 0
    inalteradas: int = 0

    @property
    def gravadas(self) -> int:
        return self.novas + self.reativadas + self.superadas


def planejar_observacoes(
    *,
    documento_id: str,
    origem: str,
    itens: Iterable[ItemInventarioPrestacao],
    estado_atual: Mapping[str, Tuple[EstadoCorrelacao, int, ItemInventarioPrestacao]],
    evidencia_sha256: Optional[str],
    registrado_em: datetime,
    competencias_superaveis: Optional[FrozenSet[str]] = None,
) -> Tuple[Tuple[ObservacaoCorrelacao, ...], ResultadoRegistroCorrelacao]:
    """Decisão ÚNICA (memória e Postgres usam esta função): dado o estado
    corrente das relações de (documento, origem) e o conjunto de relações
    sustentado pela nova resolução, devolve as observações a gravar.

      - relação nova                      -> VIGENTE, sequencia 1;
      - relação SUPERADA sustentada de novo -> VIGENTE, sequencia+1;
      - relação VIGENTE sustentada de novo -> nada (idempotente);
      - relação VIGENTE não sustentada     -> SUPERADA, sequencia+1 --
        SÓ se a sua competência está em `competencias_superaveis` (as
        competências que ESTA execução do produtor conseguia validar;
        `None` = todas). Documento reprocessado sob outro ciclo não
        sustenta a relação de outra competência por CONFLITO com o
        ciclo, não por nova evidência -- nunca a supera.

    Ordem determinística por `relacao_id`."""
    if not str(documento_id or '').strip():
        raise CorrelacaoDocumentoPrestacaoError('documento_id é obrigatório')
    if not str(origem or '').strip():
        raise CorrelacaoDocumentoPrestacaoError('origem é obrigatória')

    sustentadas: Dict[str, ItemInventarioPrestacao] = {}
    for item in itens:
        if item.documento_id != documento_id:
            raise CorrelacaoDocumentoPrestacaoError(
                'item de outro documento na reconciliação de um documento'
            )
        _validar_item(item)
        sustentadas.setdefault(chave_relacao(item), item)

    observacoes: List[ObservacaoCorrelacao] = []
    novas = reativadas = superadas = inalteradas = 0
    for relacao_id in sorted(set(sustentadas) | set(estado_atual)):
        atual = estado_atual.get(relacao_id)
        if relacao_id in sustentadas:
            if atual is None:
                estado, sequencia, novas = EstadoCorrelacao.VIGENTE, 1, novas + 1
            elif atual[0] == EstadoCorrelacao.SUPERADA:
                estado, sequencia, reativadas = EstadoCorrelacao.VIGENTE, atual[1] + 1, reativadas + 1
            else:
                inalteradas += 1
                continue
            item = sustentadas[relacao_id]
        else:
            if atual[0] != EstadoCorrelacao.VIGENTE:
                continue
            if (
                competencias_superaveis is not None
                and atual[2].competencia.entidade_id not in competencias_superaveis
            ):
                continue
            estado, sequencia, item, superadas = EstadoCorrelacao.SUPERADA, atual[1] + 1, atual[2], superadas + 1
        observacoes.append(ObservacaoCorrelacao(
            relacao_id=relacao_id, sequencia=sequencia, item=item, estado=estado,
            origem=origem, evidencia_sha256=evidencia_sha256, registrado_em=registrado_em,
        ))
    return tuple(observacoes), ResultadoRegistroCorrelacao(novas, reativadas, superadas, inalteradas)


class RepositorioCorrelacaoDocumentoPrestacao(Protocol):
    """Índice J3. `listar` implementa `FonteInventarioPrestacao`: só
    relações VIGENTES, com `documento_id` interno."""

    def registrar_relacoes_do_documento(
        self, *, documento_id: str, origem: str, itens: Tuple[ItemInventarioPrestacao, ...],
        evidencia_sha256: Optional[str], registrado_em: datetime,
        competencias_superaveis: Optional[FrozenSet[str]] = None,
    ) -> ResultadoRegistroCorrelacao: ...

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]: ...

    def historico_do_documento(self, documento_id: str) -> Tuple[ObservacaoCorrelacao, ...]: ...


def _itens_vigentes_deduplicados(itens: Iterable[ItemInventarioPrestacao]) -> Tuple[ItemInventarioPrestacao, ...]:
    """Mesma relação observada por 2 origens aparece 1 vez; ordem
    determinística."""
    unicos: Dict[str, ItemInventarioPrestacao] = {}
    for item in itens:
        unicos.setdefault(chave_relacao(item), item)
    return tuple(unicos[chave] for chave in sorted(unicos))


class RepositorioCorrelacaoDocumentoPrestacaoEmMemoria:
    """Twin em memória (testes/piloto local). `documento_existe` emula a
    FK do banco: sem Documento interno, nada é gravado."""

    def __init__(self, documento_existe: Callable[[str], bool]) -> None:
        self._documento_existe = documento_existe
        self._observacoes: List[ObservacaoCorrelacao] = []

    def _estado_atual(self, documento_id: str, origem: str) -> Dict[str, Tuple[EstadoCorrelacao, int, ItemInventarioPrestacao]]:
        atual: Dict[str, Tuple[EstadoCorrelacao, int, ItemInventarioPrestacao]] = {}
        for obs in self._observacoes:
            if obs.item.documento_id == documento_id and obs.origem == origem:
                anterior = atual.get(obs.relacao_id)
                if anterior is None or obs.sequencia > anterior[1]:
                    atual[obs.relacao_id] = (obs.estado, obs.sequencia, obs.item)
        return atual

    def registrar_relacoes_do_documento(
        self, *, documento_id: str, origem: str, itens: Tuple[ItemInventarioPrestacao, ...],
        evidencia_sha256: Optional[str], registrado_em: datetime,
        competencias_superaveis: Optional[FrozenSet[str]] = None,
    ) -> ResultadoRegistroCorrelacao:
        if not self._documento_existe(documento_id):
            raise DocumentoInexistenteNaCorrelacao(f'documento_id não é Documento interno: {documento_id!r}')
        observacoes, resultado = planejar_observacoes(
            documento_id=documento_id, origem=origem, itens=itens,
            estado_atual=self._estado_atual(documento_id, origem),
            evidencia_sha256=evidencia_sha256, registrado_em=registrado_em,
            competencias_superaveis=competencias_superaveis,
        )
        versoes = {(o.relacao_id, o.origem, o.sequencia) for o in self._observacoes}
        if any((o.relacao_id, o.origem, o.sequencia) in versoes for o in observacoes):
            raise CorrelacaoDocumentoPrestacaoError('versão duplicada (espelho da UNIQUE do banco)')
        self._observacoes.extend(observacoes)
        return resultado

    def listar(self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica) -> Tuple[ItemInventarioPrestacao, ...]:
        ultima: Dict[Tuple[str, str], ObservacaoCorrelacao] = {}
        for obs in self._observacoes:
            chave = (obs.relacao_id, obs.origem)
            if chave not in ultima or obs.sequencia > ultima[chave].sequencia:
                ultima[chave] = obs
        return _itens_vigentes_deduplicados(
            obs.item for obs in ultima.values()
            if obs.estado == EstadoCorrelacao.VIGENTE
            and obs.item.cliente == cliente and obs.item.competencia == competencia
        )

    def historico_do_documento(self, documento_id: str) -> Tuple[ObservacaoCorrelacao, ...]:
        return tuple(sorted(
            (obs for obs in self._observacoes if obs.item.documento_id == documento_id),
            key=lambda o: (o.origem, o.relacao_id, o.sequencia),
        ))


# ---------------------------------------------------------------------------
# Produtores
# ---------------------------------------------------------------------------

def _sha256_de_ids(ids: Iterable[str]) -> Optional[str]:
    unicos = sorted({i for i in ids if i})
    if not unicos:
        return None
    return hashlib.sha256('\n'.join(unicos).encode('utf-8')).hexdigest()


def itens_e_evidencia_do_corredor(
    documento_id: str, resultados_corredor: Iterable,
) -> Tuple[Tuple[ItemInventarioPrestacao, ...], Optional[str]]:
    """Relações sustentadas pelo corredor para o Documento INTERNO
    `documento_id`: os `itens_inventario` já produzidos pelo corredor
    (só existem para `RESOLVIDO_E_AVANCOU` -- regra de
    `avancar_para_inventario`, reaproveitada, nunca refeita). Resultados
    de documento DERIVADO (separação: `documento_id` do filho não é um
    Documento interno) são ignorados e registrados -- nunca promovidos a
    Documento. Evidência = hash dos `semantic_result_id` que sustentam os
    itens (sanitizado, sem conteúdo)."""
    itens: List[ItemInventarioPrestacao] = []
    ids_resolucao: List[str] = []
    for resultado in resultados_corredor:
        corredor = resultado.resultado_corredor
        if corredor.documento_id != documento_id:
            _logger.warning(
                '%s documento_id=%s', EVENTO_RELACAO_DOCUMENTO_DERIVADO_IGNORADA, documento_id,
                extra={'evento': EVENTO_RELACAO_DOCUMENTO_DERIVADO_IGNORADA, 'documento_id': documento_id},
            )
            continue
        for item in resultado.itens_inventario:
            if item.documento_id == documento_id:
                itens.append(item)
        if resultado.itens_inventario and corredor.resolucao_semantica is not None:
            ids_resolucao.append(corredor.resolucao_semantica.semantic_result_id)
    return tuple(itens), _sha256_de_ids(ids_resolucao)


def registrar_correlacoes_do_corredor(
    repositorio: RepositorioCorrelacaoDocumentoPrestacao,
    *,
    documento_id: str,
    resultados_corredor: Tuple,
    registrado_em: datetime,
    origem: str = ORIGEM_CORREDOR_PRESTACAO,
    competencias_superaveis: Optional[FrozenSet[str]] = None,
) -> ResultadoRegistroCorrelacao:
    """Produtor do índice sobre o resultado do corredor. Chamado sempre
    que o corredor processou o documento (inclusive quando ele foi para
    revisão: aí o conjunto sustentado é vazio e as relações antes
    VIGENTES viram SUPERADA -- o índice reflete a revisão, nunca mantém
    candidato elegível sem evidência). `competencias_superaveis`: as
    competências que o ciclo desta execução valida -- relação de outra
    competência nunca é superada por esta execução."""
    itens, evidencia = itens_e_evidencia_do_corredor(documento_id, resultados_corredor)
    return repositorio.registrar_relacoes_do_documento(
        documento_id=documento_id, origem=origem, itens=itens,
        evidencia_sha256=evidencia, registrado_em=registrado_em,
        competencias_superaveis=competencias_superaveis,
    )


def itens_de_resolucao_temporal_ponto(
    resolucao_documental, resolucao_cliente: ResolucaoDimensao,
) -> Tuple[ItemInventarioPrestacao, ...]:
    """Folha/Cartão de Ponto: 1 relação por cliente cuja alocação
    intersecta o período do documento (`resolver_clientes_por_periodo`,
    0010 + alocação temporal -- nunca uma escolha única denormalizada).
    Sem competência RESOLVIDA com 1 valor, sem colaborador, ou cliente não
    RESOLVIDA -> nenhuma relação (nunca fabrica)."""
    competencia = resolucao_documental.resolucao_competencia
    if (
        competencia.estado != EstadoResolucaoDimensao.RESOLVIDA
        or len(competencia.valores_confirmados) != 1
        or not resolucao_documental.colaborador_id
        or resolucao_cliente.dimensao != DimensaoResolucao.CLIENTE
        or resolucao_cliente.estado != EstadoResolucaoDimensao.RESOLVIDA
    ):
        return ()
    colaborador = ReferenciaCanonica('COLABORADOR', resolucao_documental.colaborador_id)
    return tuple(
        ItemInventarioPrestacao(
            documento_id=resolucao_documental.documento_id,
            tipo_documental=resolucao_documental.tipo_documental,
            cliente=cliente, competencia=competencia.valores_confirmados[0], colaborador=colaborador,
        )
        for cliente in resolucao_cliente.valores_confirmados
    )


def registrar_correlacoes_de_ponto(
    repositorio: RepositorioCorrelacaoDocumentoPrestacao,
    *,
    resolucao_documental,
    resolucao_cliente: ResolucaoDimensao,
    registrado_em: datetime,
) -> ResultadoRegistroCorrelacao:
    """Produtor do índice sobre a resolução temporal de ponto (mesmo
    resultado que `resolver_documento_ponto` já devolve)."""
    return repositorio.registrar_relacoes_do_documento(
        documento_id=resolucao_documental.documento_id,
        origem=ORIGEM_RESOLUCAO_TEMPORAL_PONTO,
        itens=itens_de_resolucao_temporal_ponto(resolucao_documental, resolucao_cliente),
        evidencia_sha256=None,
        registrado_em=registrado_em,
    )
