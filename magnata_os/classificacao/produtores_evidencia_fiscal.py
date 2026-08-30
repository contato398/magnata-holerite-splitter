"""Produtor FISCAL de evidência (missão "FECHAMENTO AMPLO DA COBERTURA
DOCUMENTAL", Fase 2E.3, Fase C).

Reconhece sinais fiscais genéricos — código de receita, linha
digitável/autenticação bancária de guia, identificador de obrigação —
e produz hipóteses para o tipo documental GENÉRICO já existente em
`classificador_documental.py` ('Guia', fallback para GPS/DARF sem
DCTFWeb) — nunca um tipo fiscal paralelo. Reforça (nunca substitui) a
evidência textual: quando a frase característica de um tipo específico
(GPS, DARF) está ausente ou com redação variável, o sinal estrutural
fiscal ainda entra na MESMA disputa por 'Guia' no resolvedor geral —
nunca decide sozinho quando é só 1 sinal fraco.

Nenhum destes sinais é uma palavra isolada: cada regex exige um rótulo
de campo característico (ex.: "Código de Receita" + número), nunca só
um número ou uma sigla solta."""
from __future__ import annotations

import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental

TIPO_GUIA_GENERICA = 'Guia'

_PADRAO_CODIGO_RECEITA = re.compile(r'C[óo]digo\s+de\s+Receita\s*[:\-]?\s*\d{3,4}', re.IGNORECASE)
_PADRAO_LINHA_DIGITAVEL_GUIA = re.compile(
    r'Linha\s+Digit[áa]vel|Autentica[çc][ãa]o\s+Banc[áa]ria', re.IGNORECASE,
)
_PADRAO_IDENTIFICADOR_OBRIGACAO = re.compile(
    r'N[úu]mero\s+do\s+Documento|Identificador\s+da\s+Guia|N[úu]mero\s+de\s+Refer[êe]ncia',
    re.IGNORECASE,
)


def hipoteses_fiscais_de_texto(texto: str) -> Tuple[HipoteseTipoDocumental, ...]:
    """Produtor real -- cada sinal exige um rótulo de campo
    característico (nunca um número/sigla isolados). Isolado, cada
    sinal é MODERADA (`Código de Receita`) ou FRACA (linha digitável de
    guia, identificador de obrigação) -- as regras já existentes de
    `resolver_tipo_documental` decidem se combinam para RESOLVIDA."""
    if not texto:
        return ()
    evidencias = []
    if _PADRAO_CODIGO_RECEITA.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='FISCAL_CODIGO_RECEITA', fonte='produtor_evidencia_fiscal',
            referencia_fonte='codigo_de_receita', metodo='regex_codigo_receita',
            forca=NivelConfianca.MODERADA,
        ))
    if _PADRAO_LINHA_DIGITAVEL_GUIA.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='FISCAL_LINHA_DIGITAVEL_GUIA', fonte='produtor_evidencia_fiscal',
            referencia_fonte='linha_digitavel_ou_autenticacao', metodo='regex_linha_digitavel_guia',
            forca=NivelConfianca.FRACA,
        ))
    if _PADRAO_IDENTIFICADOR_OBRIGACAO.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='FISCAL_IDENTIFICADOR_OBRIGACAO', fonte='produtor_evidencia_fiscal',
            referencia_fonte='identificador_de_obrigacao', metodo='regex_identificador_obrigacao',
            forca=NivelConfianca.FRACA,
        ))
    if not evidencias:
        return ()
    return (HipoteseTipoDocumental(tipo_documental=TIPO_GUIA_GENERICA, evidencias=tuple(evidencias)),)
