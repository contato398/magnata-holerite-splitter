"""Produtor de evidência ADICIONAL para variantes de rótulo do Extrato
da Folha de Pagamento (missão "AUTOMAÇÃO DOCUMENTAL REAL V1", §9:
"Reconhecer variantes: Extrato Mensal, Extrato da Folha, Resumo da
Folha e outros rótulos equivalentes. Não depender de nome exato").

NUNCA altera `classificador_documental.py` (17 regras fixas, espelho
comprovado 1:1 do legado `app.py::TIPO_DOC_REGRAS` — cláusula do
próprio módulo: "as 17 regras... continuam INTOCADAS"). Este produtor
soma uma hipótese A MAIS para o MESMO `resolver_tipo_documental`, mesmo
padrão já usado por `produtores_evidencia_ponto.py` para Folha de
Ponto: nunca um classificador paralelo, nunca decide sozinho."""
from __future__ import annotations

import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental

TIPO_EXTRATO = 'Extrato da Folha de Pagamento'

# "Resumo da Folha[ de Pagamento]" -- rótulo alternativo real, nunca
# coberto pelas 17 regras legadas (que só reconhecem "Extrato Mensal"/
# "Extrato da Folha de Pagamento"). MODERADA, nunca FORTE sozinha --
# mesma cautela do produtor de Ponto: uma única evidência textual
# alternativa nunca basta para um tipo que já tem regra estrutural
# fiscal mais forte disputando (ex.: FGTS, DCTFWeb).
_PADRAO_RESUMO_DA_FOLHA = re.compile(
    r'Resumo\s+da\s+Folha(?:\s+de\s+Pagamento)?\b', re.IGNORECASE,
)


def hipoteses_de_rotulo_alternativo_de_extrato(texto: str) -> Tuple[HipoteseTipoDocumental, ...]:
    """Devolve hipótese para `TIPO_EXTRATO` quando o texto usa um
    rótulo alternativo já confirmado (ex.: "Resumo da Folha") -- nunca
    exige a frase exata das 17 regras legadas."""
    if not texto:
        return ()
    if not _PADRAO_RESUMO_DA_FOLHA.search(texto):
        return ()
    return (HipoteseTipoDocumental(
        tipo_documental=TIPO_EXTRATO,
        evidencias=(EvidenciaSanitizada(
            tipo_evidencia='EXTRATO_ROTULO_ALTERNATIVO', fonte='produtor_evidencia_extrato',
            referencia_fonte='resumo_da_folha', metodo='regex_rotulo_alternativo',
            forca=NivelConfianca.MODERADA,
        ),),
    ),)
