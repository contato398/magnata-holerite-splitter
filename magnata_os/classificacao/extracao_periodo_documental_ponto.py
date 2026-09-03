"""Extração PURA do período declarado no PDF real de Folha/Cartão de
Ponto (missão "IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO
V1").

Porta FIEL de `app.py::_PERIODO_CARTAO_PONTO_RE`/`extrair_cartao_ponto`
(legado protegido — CLAUDE.md §7, nunca importado): a MESMA regex,
validada contra PDF real, portada por valor para dentro do Magnata OS.
Este módulo só extrai `(periodo_inicio, periodo_fim)`; a extração
completa de dias/horários de `extrair_cartao_ponto` está fora de
escopo aqui (não é necessária para a identidade temporal do
documento — cláusula pétrea #9 do corredor: nunca reimplementar o que
não foi pedido).

Puro: sem I/O, sem Airtable, sem rede, sem import de `app.py`. O
período SÓ vem do texto do documento — nunca de nome de arquivo, data
de upload ou cadastro atual (regra pétrea já estabelecida em
`docs/decisoes/identidade-temporal-ponto-auditoria-v1.md`)."""
from __future__ import annotations

import datetime
import re
from typing import Optional, Tuple

# Porta EXATA de app.py:762-764 (`_PERIODO_CARTAO_PONTO_RE`) — mesma
# regex, nunca reescrita.
_PERIODO_CARTAO_PONTO_RE = re.compile(
    r'Per[íi]odo:\s*(\d{2}/\d{2}/\d{4})\s*at[ée]\s*(\d{2}/\d{2}/\d{4})'
)


def _parse_data_br(data_str: str) -> Optional[datetime.date]:
    """Converte 'dd/mm/aaaa' em `datetime.date`. `None` se malformada —
    nunca levanta exceção (o chamador trata ausência/erro do mesmo
    jeito: sem período confiável)."""
    try:
        dia, mes, ano = data_str.split('/')
        return datetime.date(int(ano), int(mes), int(dia))
    except (ValueError, AttributeError):
        return None


def extrair_periodo_cartao_ponto(texto: str) -> Optional[Tuple[datetime.date, datetime.date]]:
    """Extrai `(periodo_inicio, periodo_fim)` do texto REAL do PDF —
    `None` quando o período não está declarado explicitamente, é
    malformado, ou está invertido (fim antes do início). Nunca infere
    de outro lugar — ausência aqui é sempre um `None` honesto, nunca um
    valor inventado."""
    if not texto:
        return None
    m = _PERIODO_CARTAO_PONTO_RE.search(texto)
    if not m:
        return None
    inicio = _parse_data_br(m.group(1))
    fim = _parse_data_br(m.group(2))
    if inicio is None or fim is None:
        return None
    if fim < inicio:
        return None
    return inicio, fim
