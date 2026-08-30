"""Produtor de evidência ESTRUTURAL do motor geral de compreensão
documental (missão "CAPACIDADES TRANSVERSAIS DO MOTOR DOCUMENTAL",
Fase 2E.2, Fase C).

Diferença central em relação aos produtores de `produtores_evidencia_
documental.py` (Fase 2E anterior): aqueles operam sobre o texto de UMA
página/documento já concatenado; este opera sobre a SEQUÊNCIA de textos
por página (`Tuple[str, ...]`), porque sinal estrutural de verdade —
quantidade real de entidades distintas no documento INTEIRO, múltiplas
seções — só existe quando a fronteira de página é preservada. Um texto
já concatenado perde essa fronteira.

Nunca decide fluxo sozinho ("evidência estrutural é produtor, nunca
decide fluxo diretamente fora do motor geral"): produz só
`EvidenciaEstruturalDocumento` (contagens sanitizadas — NUNCA a lista de
CPFs/CNPJs em si, só `len()`, seguindo a mesma regra já documentada em
`importacao_lote/dominio.py::extrair_cpfs_distintos_de_texto`: "o único
uso legítimo [de CPF] é contar quantos distintos existem... nunca
retornado em DTO, evento ou log") e, quando útil, `EvidenciaSanitizada`
genéricas para quem compuser outra decisão (ex.: `resolucao_master_
documental.py`).

Reaproveita só extratores puros já existentes e comprovados
(`extrair_cnpjs_de_texto`, `extrair_cpfs_distintos_de_texto`) — nunca
reimplementa extração de identificador.
"""
from __future__ import annotations

import dataclasses
from typing import Sequence, Tuple

from ..documental.importacao_lote.dominio import (
    extrair_cnpjs_de_texto,
    extrair_cpfs_distintos_de_texto,
)
from .contratos import EvidenciaSanitizada, NivelConfianca

TIPO_EVIDENCIA_MULTIPLOS_CNPJS = 'estrutura.multiplos_cnpjs_distintos'
TIPO_EVIDENCIA_MULTIPLOS_CPFS = 'estrutura.multiplos_cpfs_distintos'
TIPO_EVIDENCIA_MULTIPLAS_PAGINAS = 'estrutura.multiplas_paginas'


@dataclasses.dataclass(frozen=True)
class EvidenciaEstruturalDocumento:
    """Sinais estruturais SANITIZADOS de um documento completo — só
    contagens, nunca o identificador em si (CPF nunca sai daqui; CNPJ
    também não, por princípio de menor exposição mesmo não sendo dado
    pessoal)."""

    total_paginas: int
    quantidade_cnpjs_distintos: int
    quantidade_cpfs_distintos: int

    def __post_init__(self) -> None:
        for campo in ('total_paginas', 'quantidade_cnpjs_distintos', 'quantidade_cpfs_distintos'):
            valor = getattr(self, campo)
            if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
                raise ValueError(f'{campo} deve ser inteiro nao negativo')


def analisar_estrutura_documento(paginas: Sequence[str]) -> EvidenciaEstruturalDocumento:
    """Analisa a estrutura de um documento a partir do texto de cada
    página. Pura, determinística, sem I/O — reaproveita extratores já
    existentes; os conjuntos de CPF/CNPJ ficam só em memória local desta
    função (nunca retornados) e viram apenas contagem."""
    cnpjs_vistos: set = set()
    cpfs_vistos: set = set()
    for texto_pagina in paginas:
        cnpjs_vistos.update(extrair_cnpjs_de_texto(texto_pagina))
        cpfs_vistos.update(extrair_cpfs_distintos_de_texto(texto_pagina))
    return EvidenciaEstruturalDocumento(
        total_paginas=len(paginas),
        quantidade_cnpjs_distintos=len(cnpjs_vistos),
        quantidade_cpfs_distintos=len(cpfs_vistos),
    )


def evidencias_sanitizadas_de_estrutura(
    evidencia: EvidenciaEstruturalDocumento,
) -> Tuple[EvidenciaSanitizada, ...]:
    """Traduz a análise estrutural em `EvidenciaSanitizada` genérica —
    sem nenhum identificador real, só contagens — para quem quiser
    compor com outras evidências (ex.: `resolucao_master_documental.py`,
    ou o motor de tipo documental quando uma futura política decidir
    usar estrutura como reforço de tipo)."""
    evidencias = []
    if evidencia.quantidade_cnpjs_distintos > 1:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia=TIPO_EVIDENCIA_MULTIPLOS_CNPJS,
            fonte='evidencia_estrutural_documental',
            referencia_fonte=str(evidencia.quantidade_cnpjs_distintos),
            metodo='contagem_cnpjs_distintos_no_documento',
            forca=NivelConfianca.MODERADA,
        ))
    if evidencia.quantidade_cpfs_distintos > 1:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia=TIPO_EVIDENCIA_MULTIPLOS_CPFS,
            fonte='evidencia_estrutural_documental',
            referencia_fonte=str(evidencia.quantidade_cpfs_distintos),
            metodo='contagem_cpfs_distintos_no_documento',
            forca=NivelConfianca.MODERADA,
        ))
    if evidencia.total_paginas > 1:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia=TIPO_EVIDENCIA_MULTIPLAS_PAGINAS,
            fonte='evidencia_estrutural_documental',
            referencia_fonte=str(evidencia.total_paginas),
            metodo='contagem_paginas',
            forca=NivelConfianca.FRACA,
        ))
    return tuple(evidencias)
