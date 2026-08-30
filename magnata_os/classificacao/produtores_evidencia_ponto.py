"""Produtor de PONTO (missão "FECHAMENTO AMPLO DA COBERTURA
DOCUMENTAL", Fase 2E.3, Fase E).

Prova que o produtor estrutural geral reconhece "Folha de Ponto" mesmo
quando a frase literal está ausente/variável — combinando:
  - estrutura: linhas de marcação repetidas, no MESMO formato já
    validado contra PDF real pelo legado (`app.py::
    extrair_cartao_ponto`, "ainda não usado em produção" mas o PADRÃO
    já é comprovado — ex.: "29/04/26 - Qua - C1 18:56 01:00 01:53
    09:05"), portado aqui só como REGEX de detecção (nunca a extração
    completa de dias/horários, fora do escopo desta missão);
  - textual: período declarado ("Período: dd/mm/aaaa até dd/mm/aaaa"),
    também já validado pelo legado.

Produz hipótese para o MESMO tipo 'Folha de Ponto' já usado por
`classificador_documental.py` — nunca um tipo paralelo. Uma única linha
de marcação isolada nunca basta (poderia ser coincidência de formato);
exige repetição (>= 2 linhas) para virar evidência estrutural."""
from __future__ import annotations

import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental

TIPO_FOLHA_DE_PONTO = 'Folha de Ponto'

# Linha de dia do "Cartão Ponto" (mesmo padrão de
# `app.py::_LINHA_CARTAO_PONTO_RE`), ex.:
#   "29/04/26 - Qua - C1 18:56 01:00 01:53 09:05"
_LINHA_MARCACAO_PONTO_RE = re.compile(
    r'^\d{2}/\d{2}/\d{2}\s*-\s*[A-Za-zÀ-ú]{3}\s*-\s*C\d\s+.+$', re.MULTILINE,
)
_PADRAO_PERIODO_PONTO = re.compile(
    r'Per[íi]odo:\s*\d{2}/\d{2}/\d{4}\s*at[ée]\s*\d{2}/\d{2}/\d{4}', re.IGNORECASE,
)


def contar_linhas_de_marcacao_ponto(texto: str) -> int:
    """Conta quantas linhas seguem o formato de marcação de ponto
    (dia + ciclo + horários) -- puramente estrutural, nunca depende da
    frase "Folha de Ponto"/"Secullum"."""
    if not texto:
        return 0
    return len(_LINHA_MARCACAO_PONTO_RE.findall(texto))


def hipoteses_estruturais_de_ponto(texto: str) -> Tuple[HipoteseTipoDocumental, ...]:
    """>= 2 linhas de marcação repetidas -> evidência MODERADA
    (estrutura real, nunca 1 linha isolada); período declarado reforça
    com FRACA. Nenhum dos dois exige a palavra "Folha de Ponto"."""
    if not texto:
        return ()
    evidencias = []
    quantidade_linhas = contar_linhas_de_marcacao_ponto(texto)
    if quantidade_linhas >= 2:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='PONTO_ESTRUTURA_LINHAS_MARCACAO_REPETIDAS',
            fonte='produtor_evidencia_ponto', referencia_fonte=str(quantidade_linhas),
            metodo='regex_linha_marcacao_repetida', forca=NivelConfianca.MODERADA,
        ))
    if _PADRAO_PERIODO_PONTO.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='PONTO_PERIODO_DECLARADO', fonte='produtor_evidencia_ponto',
            referencia_fonte='periodo_cartao_ponto', metodo='regex_periodo_ponto',
            forca=NivelConfianca.FRACA,
        ))
    if not evidencias:
        return ()
    return (HipoteseTipoDocumental(tipo_documental=TIPO_FOLHA_DE_PONTO, evidencias=tuple(evidencias)),)
