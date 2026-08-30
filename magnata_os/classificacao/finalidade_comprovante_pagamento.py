"""Finalidade de comprovantes de pagamento (missão "CAPACIDADES
TRANSVERSAIS DO MOTOR DOCUMENTAL", Fase 2E.2, Fase G).

Regra fundamental do adendo constitucional da missão anterior:
"Comprovante de Pagamento" isolado NUNCA é uma finalidade semântica
suficiente — salário, FGTS, DCTF/DARF, VR/VA, assiduidade e diárias são
finalidades DIFERENTES que só um comprovante genérico não distingue.

Este módulo NÃO cria um motor paralelo: as finalidades concorrem pelas
MESMAS regras de força/conflito já provadas em `resolucao_tipo_
documental.py` (motor único). O que muda é só a origem da evidência —
um novo produtor (`sinais_textuais_de_finalidade_pagamento`) que exige
uma FRASE característica da finalidade (nunca uma palavra isolada tipo
"pagamento") e classifica estrutura bancária isolada (TED/PIX/
"comprovante de transferência") como sinal FRACO que nunca resolve
sozinho — só reforça uma finalidade já sustentada por uma descrição
específica.

Política resultante (herdada do resolvedor geral, sem regra nova):
  - 1 evidência FRACA isolada (só estrutura bancária, sem descrição) ->
    NAO_ENCONTRADA (inconclusivo — nunca resolve "a qualquer custo");
  - 1 descrição específica (MODERADA) já resolve sozinha — é uma frase
    característica, não uma palavra isolada;
  - 2+ evidências coerentes para a MESMA finalidade (descrição +
    estrutura bancária, por exemplo) reforçam para FORTE;
  - 2 finalidades incompatíveis com evidência igualmente forte (ex.:
    documento cita salário E FGTS com a mesma força) -> CONFLITO.
"""
from __future__ import annotations

import dataclasses
import enum
import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental

FINALIDADE_SALARIO = 'Comprovante de Pagamento - Salário'
FINALIDADE_FGTS = 'Comprovante de Pagamento - FGTS'
FINALIDADE_DCTF_DARF = 'Comprovante de Pagamento - DCTF/DARF'
FINALIDADE_VR_VA = 'Comprovante de Pagamento - VR/VA'
FINALIDADE_ASSIDUIDADE = 'Comprovante de Pagamento - Assiduidade'
FINALIDADE_DIARIAS = 'Comprovante de Pagamento - Diárias'
FINALIDADE_HORAS_EXTRAS = 'Comprovante de Pagamento - Horas Extras'


class SinalFinalidadePagamento(str, enum.Enum):
    ESTRUTURA_BANCARIA = 'ESTRUTURA_BANCARIA'
    DESCRICAO_SALARIO = 'DESCRICAO_SALARIO'
    DESCRICAO_FGTS = 'DESCRICAO_FGTS'
    DESCRICAO_DCTF_DARF = 'DESCRICAO_DCTF_DARF'
    DESCRICAO_VR_VA = 'DESCRICAO_VR_VA'
    DESCRICAO_ASSIDUIDADE = 'DESCRICAO_ASSIDUIDADE'
    DESCRICAO_DIARIAS = 'DESCRICAO_DIARIAS'
    DESCRICAO_HORAS_EXTRAS = 'DESCRICAO_HORAS_EXTRAS'
    # Fase 2E.3 (Fase F): abreviação isolada ("VR"/"VA" fora de uma
    # frase característica) -- SEMPRE FRACA, estruturalmente, nunca
    # decide sozinha ("'VR' na descrição sozinho -> FRACA"). Reforça
    # (nunca substitui) uma finalidade já sustentada por descrição
    # específica -- mesmo papel que ESTRUTURA_BANCARIA já tem.
    ABREVIACAO_VR_VA = 'ABREVIACAO_VR_VA'


_FORCA_POR_SINAL = {
    SinalFinalidadePagamento.ESTRUTURA_BANCARIA: NivelConfianca.FRACA,
    SinalFinalidadePagamento.DESCRICAO_SALARIO: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.DESCRICAO_FGTS: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.DESCRICAO_DCTF_DARF: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.DESCRICAO_VR_VA: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.DESCRICAO_ASSIDUIDADE: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.DESCRICAO_DIARIAS: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.DESCRICAO_HORAS_EXTRAS: NivelConfianca.MODERADA,
    SinalFinalidadePagamento.ABREVIACAO_VR_VA: NivelConfianca.FRACA,
}


@dataclasses.dataclass(frozen=True)
class OcorrenciaSinalFinalidade:
    sinal: SinalFinalidadePagamento
    finalidade_sugerida: str
    referencia: str

    def __post_init__(self) -> None:
        if not self.finalidade_sugerida.strip():
            raise ValueError('finalidade_sugerida deve ser texto nao vazio')
        if not self.referencia.strip():
            raise ValueError('referencia deve ser texto nao vazio')


def hipoteses_de_finalidade_pagamento(
    ocorrencias: Tuple[OcorrenciaSinalFinalidade, ...],
) -> Tuple[HipoteseTipoDocumental, ...]:
    """Traduz sinais JÁ IDENTIFICADOS em hipóteses para o MESMO
    `resolver_tipo_documental` — nenhuma regra de combinação nova aqui,
    o resolvedor geral já implementa exatamente a política descrita na
    docstring do módulo."""
    return tuple(
        HipoteseTipoDocumental(
            tipo_documental=ocorrencia.finalidade_sugerida,
            evidencias=(
                EvidenciaSanitizada(
                    tipo_evidencia=ocorrencia.sinal.value,
                    fonte='finalidade_comprovante_pagamento',
                    referencia_fonte=ocorrencia.referencia,
                    metodo='sinal_finalidade_pagamento',
                    forca=_FORCA_POR_SINAL[ocorrencia.sinal],
                ),
            ),
        )
        for ocorrencia in ocorrencias
    )


# Frases características (nunca palavra isolada) por finalidade -- cada
# padrão exige contexto suficiente para não disparar em qualquer menção
# solta da palavra ("pagamento", "salário" avulsos nunca bastam).
_PADROES_DESCRICAO: Tuple[Tuple[str, SinalFinalidadePagamento, re.Pattern], ...] = (
    (FINALIDADE_SALARIO, SinalFinalidadePagamento.DESCRICAO_SALARIO,
     re.compile(r'pagamento\s+de\s+sal[aá]rio|cr[eé]dito\s+em\s+conta\s*[-–]?\s*sal[aá]rio', re.IGNORECASE)),
    (FINALIDADE_FGTS, SinalFinalidadePagamento.DESCRICAO_FGTS,
     re.compile(r'recolhimento\s+(?:do\s+)?fgts|guia\s+do\s+fgts', re.IGNORECASE)),
    (FINALIDADE_DCTF_DARF, SinalFinalidadePagamento.DESCRICAO_DCTF_DARF,
     re.compile(r'\bdarf\b|documento\s+de\s+arrecada[cç][aã]o', re.IGNORECASE)),
    (FINALIDADE_VR_VA, SinalFinalidadePagamento.DESCRICAO_VR_VA,
     re.compile(r'vale[-\s]?refei[cç][aã]o|vale[-\s]?alimenta[cç][aã]o', re.IGNORECASE)),
    (FINALIDADE_ASSIDUIDADE, SinalFinalidadePagamento.DESCRICAO_ASSIDUIDADE,
     re.compile(r'pr[eê]mio\s+de\s+assiduidade', re.IGNORECASE)),
    (FINALIDADE_DIARIAS, SinalFinalidadePagamento.DESCRICAO_DIARIAS,
     re.compile(r'pagamento\s+de\s+di[aá]rias', re.IGNORECASE)),
    (FINALIDADE_HORAS_EXTRAS, SinalFinalidadePagamento.DESCRICAO_HORAS_EXTRAS,
     re.compile(r'pagamento\s+de\s+horas\s+extras|recibo\s+de\s+horas\s+extras', re.IGNORECASE)),
)

_PADRAO_ESTRUTURA_BANCARIA = re.compile(
    r'comprovante\s+de\s+(?:transfer[eê]ncia|pagamento)|\bted\b|\bpix\b', re.IGNORECASE,
)

# Abreviação isolada -- nunca decide sozinha (ver SinalFinalidadePagamento.
# ABREVIACAO_VR_VA, sempre FRACA). Emitida independentemente da frase
# completa (_PADROES_DESCRICAO acima): sozinha, o resolvedor geral já
# garante que 1 FRACA isolada -> NAO_ENCONTRADA; só quando reforçada por
# OUTRO sinal (estrutura bancária, ou a própria frase completa) a força
# combinada sobe (2+ FRACA -> MODERADA, regra já existente e não
# duplicada aqui -- Fase F: "VR isolado -> fraca; + estrutura bancária
# + referência -> pode aumentar confiança").
_PADRAO_ABREVIACAO_VR_VA = re.compile(r'\bVR\b|\bVA\b')


def sinais_textuais_de_finalidade_pagamento(texto: str) -> Tuple[OcorrenciaSinalFinalidade, ...]:
    """Produtor textual real. Procura frases características de
    finalidade (nunca uma palavra isolada); estrutura bancária isolada
    (TED/PIX/"comprovante de transferência") NUNCA gera hipótese sem
    já haver uma descrição específica -- sozinha, ela nunca decide
    (Fase G: "nunca uma palavra isolada")."""
    if not texto:
        return ()
    ocorrencias = []
    finalidades_encontradas = set()
    for finalidade, sinal, padrao in _PADROES_DESCRICAO:
        if padrao.search(texto):
            ocorrencias.append(OcorrenciaSinalFinalidade(
                sinal=sinal, finalidade_sugerida=finalidade, referencia=padrao.pattern,
            ))
            finalidades_encontradas.add(finalidade)

    if _PADRAO_ABREVIACAO_VR_VA.search(texto):
        # Sempre FRACA, sempre emitida (mesmo sem a frase completa) --
        # nunca decide sozinha; combinada com outro sinal fraco (ex.:
        # estrutura bancária) reforça para MODERADA (Fase F: "VR
        # isolado -> fraca; + estrutura bancária + referência -> pode
        # aumentar confiança" -- regra de combinação já existente em
        # resolver_tipo_documental, não duplicada aqui).
        ocorrencias.append(OcorrenciaSinalFinalidade(
            sinal=SinalFinalidadePagamento.ABREVIACAO_VR_VA,
            finalidade_sugerida=FINALIDADE_VR_VA,
            referencia='abreviacao_vr_va_isolada',
        ))
        finalidades_encontradas.add(FINALIDADE_VR_VA)

    if _PADRAO_ESTRUTURA_BANCARIA.search(texto):
        for finalidade in finalidades_encontradas:
            ocorrencias.append(OcorrenciaSinalFinalidade(
                sinal=SinalFinalidadePagamento.ESTRUTURA_BANCARIA,
                finalidade_sugerida=finalidade,
                referencia='estrutura_bancaria_comprovante',
            ))

    return tuple(ocorrencias)
