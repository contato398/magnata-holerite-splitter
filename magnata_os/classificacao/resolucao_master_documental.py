"""Detector GERAL de granularidade documental — "este documento parece
ser 1 entidade (unitário) ou várias (potencialmente master)?" (missão
"CAPACIDADES TRANSVERSAIS DO MOTOR DOCUMENTAL", Fase 2E.2, Fase D).

DECISÃO ARQUITETURAL REGISTRADA (não silenciosa — ver `docs/decisoes/
capacidades-transversais-motor-documental-v1.md`): esta decisão NÃO usa
`DimensaoResolucao`/`ResolucaoDimensao` (contrato canônico de
`contratos.py`). Motivo: `DimensaoResolucao` hoje tem 6 membros fixos
(TIPO_DOCUMENTAL/COMPETENCIA/CLIENTE/UNIDADE_POSTO/COLABORADOR/VINCULO)
e `ResultadoResolucaoSemantico.__post_init__` EXIGE que o conjunto de
dimensões resolvidas seja EXATAMENTE igual ao declarado pelo `Perfil
AplicabilidadeResolucao` — adicionar um 7º membro (`GRANULARIDADE`,
`MASTER`, etc.) é uma mudança de contrato compartilhado, com efeito em
todo perfil de aplicabilidade já validado, para um sinal que ainda não
tem nenhum consumidor formal de perfil. A missão pede explicitamente
"evitar contrato/enum novo a menos que comprovadamente necessário" —
aqui NÃO é: granularidade é uma decisão ORTOGONAL ao tipo/competência/
cliente, calculada ANTES da separação, nunca parte do mesmo perfil.
Por isso vive numa dataclass própria e pequena, reaproveitando só as
PEÇAS genéricas já existentes (`EvidenciaSanitizada`, `NivelConfianca`,
`ConfiancaResolucao`) — nunca duplicando o vocabulário de força/
evidência, só não usando o "envelope" `ResolucaoDimensao`.

"Master ≠ tipo documental" (Fase D da missão): esta função NUNCA sabe
o tipo documental do documento — só recebe evidência estrutural
(`EvidenciaEstruturalDocumento`), nunca `if tipo == EXTRATO`.
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Tuple

from .contratos import ConfiancaResolucao, EvidenciaSanitizada, NivelConfianca
from .evidencia_estrutural_documental import (
    EvidenciaEstruturalDocumento,
    evidencias_sanitizadas_de_estrutura,
)


class EstadoGranularidadeDocumento(str, enum.Enum):
    UNITARIO = 'UNITARIO'
    POTENCIALMENTE_MASTER = 'POTENCIALMENTE_MASTER'
    INCONCLUSIVO = 'INCONCLUSIVO'


@dataclasses.dataclass(frozen=True)
class DecisaoGranularidadeDocumento:
    estado: EstadoGranularidadeDocumento
    evidencias: Tuple[EvidenciaSanitizada, ...]
    confianca: ConfiancaResolucao
    motivos: Tuple[str, ...] = ()


def detectar_granularidade_documento(
    evidencia: EvidenciaEstruturalDocumento,
) -> DecisaoGranularidadeDocumento:
    """Decide UNITARIO / POTENCIALMENTE_MASTER / INCONCLUSIVO a partir
    de evidência estrutural JÁ CALCULADA (nunca extrai nada aqui — só
    interpreta `EvidenciaEstruturalDocumento`, produzida por
    `evidencia_estrutural_documental.analisar_estrutura_documento`).

    Regra (documentada, revisável — não um número mágico escondido):
      - >= 2 CNPJs distintos OU >= 2 CPFs distintos no documento inteiro
        -> POTENCIALMENTE_MASTER (generaliza o sinal já comprovado pelo
        legado — `construir_mapa_cliente`/CPF avulso mestre suspeito —
        para qualquer granularidade, nunca especializado a cliente ou
        colaborador);
      - exatamente 1 entidade distinta encontrada (CNPJ ou CPF) e
        nenhum sinal de múltiplas -> UNITARIO;
      - nenhuma entidade encontrada (0 CNPJs e 0 CPFs) -> INCONCLUSIVO
        (sem evidência estrutural suficiente para decidir nem um jeito
        nem outro — nunca força UNITARIO "por padrão otimista", que
        seria mascarar a ausência de evidência como confiança)."""
    evidencias = evidencias_sanitizadas_de_estrutura(evidencia)

    if evidencia.quantidade_cnpjs_distintos >= 2 or evidencia.quantidade_cpfs_distintos >= 2:
        return DecisaoGranularidadeDocumento(
            estado=EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER,
            evidencias=evidencias,
            confianca=ConfiancaResolucao(NivelConfianca.MODERADA),
            motivos=('multiplas_entidades_distintas_no_documento',),
        )

    if evidencia.quantidade_cnpjs_distintos == 1 or evidencia.quantidade_cpfs_distintos == 1:
        return DecisaoGranularidadeDocumento(
            estado=EstadoGranularidadeDocumento.UNITARIO,
            evidencias=evidencias,
            confianca=ConfiancaResolucao(NivelConfianca.MODERADA),
            motivos=('entidade_unica_distinta_no_documento',),
        )

    return DecisaoGranularidadeDocumento(
        estado=EstadoGranularidadeDocumento.INCONCLUSIVO,
        evidencias=evidencias,
        confianca=ConfiancaResolucao(NivelConfianca.INDETERMINADA),
        motivos=('nenhuma_entidade_estrutural_encontrada',),
    )
