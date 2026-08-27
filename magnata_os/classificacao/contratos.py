"""Contratos puros do Document Resolution & Routing Shadow V1.

Este modulo pertence ao bounded context geral de Classificacao. Ele nao
importa o fluxo especializado ``documental.importacao_lote`` para evitar
dependencia invertida. O mapeamento futuro preserva o vocabulario existente:
``EXACT`` -> ``RESOLVIDA``, ``AMBIGUOUS`` -> ``AMBIGUA``, ``NOT_FOUND`` ->
``NAO_ENCONTRADA``, ``CONFLICT`` -> ``CONFLITO`` e ``INVALID`` -> ``INVALIDA``.

Os tipos abaixo sao somente value objects, enums e validacoes estruturais.
Nao ha matching, I/O, persistencia, mutacao de Documento, evento publicado ou
executor de routing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _exigir_texto(valor: str, campo: str) -> None:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{campo} deve ser texto nao vazio")


def _hash_canonico(payload: dict) -> str:
    serializado = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


class DimensaoResolucao(str, Enum):
    TIPO_DOCUMENTAL = "TIPO_DOCUMENTAL"
    COMPETENCIA = "COMPETENCIA"
    CLIENTE = "CLIENTE"
    UNIDADE_POSTO = "UNIDADE_POSTO"
    COLABORADOR = "COLABORADOR"
    VINCULO = "VINCULO"


class EstadoResolucaoDimensao(str, Enum):
    NAO_AVALIADA = "NAO_AVALIADA"
    NAO_APLICAVEL = "NAO_APLICAVEL"
    RESOLVIDA = "RESOLVIDA"
    AMBIGUA = "AMBIGUA"
    NAO_ENCONTRADA = "NAO_ENCONTRADA"
    CONFLITO = "CONFLITO"
    INVALIDA = "INVALIDA"
    ERRO_TECNICO = "ERRO_TECNICO"


class NivelConfianca(str, Enum):
    FORTE = "FORTE"
    MODERADA = "MODERADA"
    FRACA = "FRACA"
    INDETERMINADA = "INDETERMINADA"


class AplicabilidadeDimensao(str, Enum):
    OBRIGATORIA = "OBRIGATORIA"
    OPCIONAL = "OPCIONAL"
    NAO_APLICAVEL = "NAO_APLICAVEL"


class EstadoResultadoSemantico(str, Enum):
    RESOLVIDA = "RESOLVIDA"
    PARCIAL = "PARCIAL"
    INCONCLUSIVA = "INCONCLUSIVA"
    INVALIDA = "INVALIDA"
    ERRO_TECNICO = "ERRO_TECNICO"


class RotaLogica(str, Enum):
    VALIDACAO_DOCUMENTAL = "VALIDACAO_DOCUMENTAL"
    REVISAO_HUMANA = "REVISAO_HUMANA"
    SEM_ROTA_APLICAVEL = "SEM_ROTA_APLICAVEL"
    BLOQUEADA = "BLOQUEADA"
    SHADOW_OBSERVADA = "SHADOW_OBSERVADA"


class EstadoDecisaoRouting(str, Enum):
    PROPOSTA = "PROPOSTA"
    INCONCLUSIVA = "INCONCLUSIVA"
    BLOQUEADA = "BLOQUEADA"


@dataclasses.dataclass(frozen=True)
class ReferenciaCanonica:
    tipo_entidade: str
    entidade_id: str

    def __post_init__(self) -> None:
        _exigir_texto(self.tipo_entidade, "tipo_entidade")
        _exigir_texto(self.entidade_id, "entidade_id")

    def _canonico(self) -> tuple[str, str]:
        return self.tipo_entidade, self.entidade_id


@dataclasses.dataclass(frozen=True)
class ConfiancaResolucao:
    nivel: NivelConfianca
    score: Optional[float] = None
    escala_score: Optional[str] = None
    estrategia_origem: Optional[str] = None

    def __post_init__(self) -> None:
        if self.score is None:
            if self.escala_score is not None:
                raise ValueError("escala_score so pode existir quando score existe")
            return
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("score deve ser numerico")
        if not math.isfinite(float(self.score)):
            raise ValueError("score deve ser finito")
        _exigir_texto(self.escala_score or "", "escala_score")
        _exigir_texto(self.estrategia_origem or "", "estrategia_origem")

    def _canonico(self) -> dict:
        score = None
        if self.score is not None:
            score = format(float(self.score), ".17g")
        return {
            "escala_score": self.escala_score,
            "estrategia_origem": self.estrategia_origem,
            "nivel": self.nivel.value,
            "score": score,
        }


@dataclasses.dataclass(frozen=True)
class EvidenciaSanitizada:
    tipo_evidencia: str
    fonte: str
    referencia_fonte: str
    metodo: str
    forca: NivelConfianca
    entidade_candidata: Optional[ReferenciaCanonica] = None
    score: Optional[float] = None
    escala_score: Optional[str] = None
    estrategia_score: Optional[str] = None
    motivo_sanitizado: Optional[str] = None

    def __post_init__(self) -> None:
        for campo in ("tipo_evidencia", "fonte", "referencia_fonte", "metodo"):
            _exigir_texto(getattr(self, campo), campo)
        ConfiancaResolucao(
            nivel=self.forca,
            score=self.score,
            escala_score=self.escala_score,
            estrategia_origem=self.estrategia_score,
        )

    def _canonico(self) -> dict:
        return {
            "entidade_candidata": (
                self.entidade_candidata._canonico()
                if self.entidade_candidata is not None
                else None
            ),
            "escala_score": self.escala_score,
            "estrategia_score": self.estrategia_score,
            "fonte": self.fonte,
            "forca": self.forca.value,
            "metodo": self.metodo,
            "motivo_sanitizado": self.motivo_sanitizado,
            "referencia_fonte": self.referencia_fonte,
            "score": (
                format(float(self.score), ".17g")
                if self.score is not None
                else None
            ),
            "tipo_evidencia": self.tipo_evidencia,
        }


@dataclasses.dataclass(frozen=True)
class Cardinalidade:
    minima: int
    maxima: Optional[int]

    def __post_init__(self) -> None:
        if isinstance(self.minima, bool) or not isinstance(self.minima, int):
            raise ValueError("cardinalidade minima deve ser inteira")
        if self.minima < 0:
            raise ValueError("cardinalidade minima nao pode ser negativa")
        if self.maxima is not None:
            if isinstance(self.maxima, bool) or not isinstance(self.maxima, int):
                raise ValueError("cardinalidade maxima deve ser inteira ou None")
            if self.maxima < self.minima:
                raise ValueError("cardinalidade maxima nao pode ser menor que a minima")

    def contem(self, quantidade: int) -> bool:
        return quantidade >= self.minima and (
            self.maxima is None or quantidade <= self.maxima
        )

    def _canonico(self) -> dict:
        return {"maxima": self.maxima, "minima": self.minima}


@dataclasses.dataclass(frozen=True)
class RegraAplicabilidadeDimensao:
    dimensao: DimensaoResolucao
    aplicabilidade: AplicabilidadeDimensao
    cardinalidade: Cardinalidade
    bloqueia_confirmacao: bool = True
    bloqueia_routing: bool = True
    motivo_regra: Optional[str] = None

    def __post_init__(self) -> None:
        if self.aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL:
            if self.cardinalidade != Cardinalidade(0, 0):
                raise ValueError(
                    "dimensao nao aplicavel exige cardinalidade minima=0 e maxima=0"
                )

    def _canonico(self) -> dict:
        return {
            "aplicabilidade": self.aplicabilidade.value,
            "bloqueia_confirmacao": self.bloqueia_confirmacao,
            "bloqueia_routing": self.bloqueia_routing,
            "cardinalidade": self.cardinalidade._canonico(),
            "dimensao": self.dimensao.value,
            "motivo_regra": self.motivo_regra,
        }


@dataclasses.dataclass(frozen=True)
class PerfilAplicabilidadeResolucao:
    perfil_id: str
    version: str
    escopo_documental: str
    regras: Tuple[RegraAplicabilidadeDimensao, ...]

    def __post_init__(self) -> None:
        _exigir_texto(self.perfil_id, "perfil_id")
        _exigir_texto(self.version, "version")
        _exigir_texto(self.escopo_documental, "escopo_documental")
        dimensoes = [regra.dimensao for regra in self.regras]
        if len(dimensoes) != len(set(dimensoes)):
            raise ValueError("perfil nao pode repetir dimensao")

    def regra_para(self, dimensao: DimensaoResolucao) -> RegraAplicabilidadeDimensao:
        for regra in self.regras:
            if regra.dimensao == dimensao:
                return regra
        raise KeyError(dimensao)

    def _canonico(self) -> dict:
        return {
            "escopo_documental": self.escopo_documental,
            "perfil_id": self.perfil_id,
            "regras": sorted(
                (regra._canonico() for regra in self.regras),
                key=lambda item: item["dimensao"],
            ),
            "version": self.version,
        }


@dataclasses.dataclass(frozen=True)
class ResolucaoDimensao:
    dimensao: DimensaoResolucao
    estado: EstadoResolucaoDimensao
    valores_confirmados: Tuple[ReferenciaCanonica, ...] = ()
    candidatos: Tuple[ReferenciaCanonica, ...] = ()
    evidencias: Tuple[EvidenciaSanitizada, ...] = ()
    metodo: Optional[str] = None
    confianca: ConfiancaResolucao = dataclasses.field(
        default_factory=lambda: ConfiancaResolucao(NivelConfianca.INDETERMINADA)
    )
    motivos: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.estado in {
            EstadoResolucaoDimensao.AMBIGUA,
            EstadoResolucaoDimensao.CONFLITO,
        } and self.valores_confirmados:
            raise ValueError("dimensao ambigua ou em conflito nao possui valor confirmado")
        if self.estado == EstadoResolucaoDimensao.RESOLVIDA and not self.valores_confirmados:
            raise ValueError("dimensao resolvida exige ao menos um valor confirmado")
        if self.estado in {
            EstadoResolucaoDimensao.NAO_AVALIADA,
            EstadoResolucaoDimensao.NAO_APLICAVEL,
            EstadoResolucaoDimensao.NAO_ENCONTRADA,
            EstadoResolucaoDimensao.INVALIDA,
            EstadoResolucaoDimensao.ERRO_TECNICO,
        } and self.valores_confirmados:
            raise ValueError(f"estado {self.estado.value} nao aceita valor confirmado")
        if self.estado == EstadoResolucaoDimensao.NAO_APLICAVEL and (
            self.candidatos or self.evidencias
        ):
            raise ValueError("dimensao nao aplicavel nao aceita candidatos ou evidencias")

    def validar_contra(self, regra: RegraAplicabilidadeDimensao) -> None:
        if regra.dimensao != self.dimensao:
            raise ValueError("regra e resolucao pertencem a dimensoes diferentes")
        if regra.aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL:
            if self.estado != EstadoResolucaoDimensao.NAO_APLICAVEL:
                raise ValueError("regra nao aplicavel exige estado NAO_APLICAVEL")
            return
        if self.estado == EstadoResolucaoDimensao.NAO_APLICAVEL:
            raise ValueError("estado NAO_APLICAVEL exige regra nao aplicavel")
        if self.estado == EstadoResolucaoDimensao.RESOLVIDA and not regra.cardinalidade.contem(
            len(self.valores_confirmados)
        ):
            raise ValueError("quantidade resolvida viola a cardinalidade da dimensao")

    def _canonico(self) -> dict:
        return {
            "candidatos": sorted(ref._canonico() for ref in self.candidatos),
            "confianca": self.confianca._canonico(),
            "dimensao": self.dimensao.value,
            "estado": self.estado.value,
            "evidencias": sorted(
                (evidencia._canonico() for evidencia in self.evidencias),
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True),
            ),
            "metodo": self.metodo,
            "motivos": sorted(self.motivos),
            "valores_confirmados": sorted(
                ref._canonico() for ref in self.valores_confirmados
            ),
        }


@dataclasses.dataclass(frozen=True)
class EntradaResolucaoDocumento:
    documento_id: str
    hash_sha256: str
    resolver_id: str
    resolver_version: str
    politica_id: str
    politica_version: str
    contexto_fontes_fingerprint: str
    execution_idempotency_key: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        for campo in (
            "documento_id",
            "resolver_id",
            "resolver_version",
            "politica_id",
            "politica_version",
            "contexto_fontes_fingerprint",
        ):
            _exigir_texto(getattr(self, campo), campo)
        if not _SHA256_RE.fullmatch(self.hash_sha256):
            raise ValueError("hash_sha256 deve conter 64 caracteres hexadecimais minusculos")
        chave = _hash_canonico(
            {
                "contexto_fontes_fingerprint": self.contexto_fontes_fingerprint,
                "documento_id": self.documento_id,
                "hash_sha256": self.hash_sha256,
                "politica_id": self.politica_id,
                "politica_version": self.politica_version,
                "resolver_id": self.resolver_id,
                "resolver_version": self.resolver_version,
            }
        )
        object.__setattr__(self, "execution_idempotency_key", chave)


@dataclasses.dataclass(frozen=True)
class ResultadoResolucaoSemantico:
    documento_id: str
    resolver_id: str
    resolver_version: str
    politica_id: str
    politica_version: str
    perfil: PerfilAplicabilidadeResolucao
    resolucoes: Tuple[ResolucaoDimensao, ...]
    estado_consolidado: EstadoResultadoSemantico
    necessita_revisao_humana: bool
    motivos_consolidados: Tuple[str, ...] = ()
    pronto_para_routing_logico: bool = False
    semantic_result_id: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        for campo in (
            "documento_id",
            "resolver_id",
            "resolver_version",
            "politica_id",
            "politica_version",
        ):
            _exigir_texto(getattr(self, campo), campo)
        por_dimensao = {resolucao.dimensao: resolucao for resolucao in self.resolucoes}
        if len(por_dimensao) != len(self.resolucoes):
            raise ValueError("resultado nao pode repetir dimensao")
        dimensoes_perfil = {regra.dimensao for regra in self.perfil.regras}
        if set(por_dimensao) != dimensoes_perfil:
            raise ValueError("resultado deve conter exatamente as dimensoes do perfil")
        for regra in self.perfil.regras:
            por_dimensao[regra.dimensao].validar_contra(regra)
        object.__setattr__(self, "semantic_result_id", _hash_canonico(self._canonico()))

    def _canonico(self) -> dict:
        return {
            "documento_id": self.documento_id,
            "estado_consolidado": self.estado_consolidado.value,
            "motivos_consolidados": sorted(self.motivos_consolidados),
            "necessita_revisao_humana": self.necessita_revisao_humana,
            "perfil": self.perfil._canonico(),
            "politica_id": self.politica_id,
            "politica_version": self.politica_version,
            "pronto_para_routing_logico": self.pronto_para_routing_logico,
            "resolver_id": self.resolver_id,
            "resolver_version": self.resolver_version,
            "resolucoes": sorted(
                (resolucao._canonico() for resolucao in self.resolucoes),
                key=lambda item: item["dimensao"],
            ),
        }


@dataclasses.dataclass(frozen=True)
class MetadadosExecucaoResolucao:
    execution_idempotency_key: str
    correlation_id: str
    attempt_id: str
    observado_em: datetime
    resultado_reutilizado: bool = False

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.execution_idempotency_key):
            raise ValueError("execution_idempotency_key deve ser SHA-256 hexadecimal")
        _exigir_texto(self.correlation_id, "correlation_id")
        _exigir_texto(self.attempt_id, "attempt_id")
        if not isinstance(self.observado_em, datetime):
            raise ValueError("observado_em deve ser datetime")


@dataclasses.dataclass(frozen=True)
class DecisaoRoutingDocumental:
    semantic_result_id: str
    politica_routing_id: str
    politica_routing_version: str
    rota_logica: RotaLogica
    estado: EstadoDecisaoRouting
    precondicoes_atendidas: Tuple[str, ...] = ()
    precondicoes_pendentes: Tuple[str, ...] = ()
    motivos: Tuple[str, ...] = ()
    necessita_revisao_humana: bool = False

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.semantic_result_id):
            raise ValueError("semantic_result_id deve ser SHA-256 hexadecimal")
        _exigir_texto(self.politica_routing_id, "politica_routing_id")
        _exigir_texto(self.politica_routing_version, "politica_routing_version")
