"""Liga a decisão de granularidade (`resolucao_master_documental.py`,
`magnata_os/classificacao/`) à etapa operacional da esteira (Fase 2E.2,
Fase K).

Decisão de não forçar (registrada, não escondida): `TRANSICOES_ETAPA_
PERMITIDAS` (`dominio_esteira.py`) já permite CLASSIFICACAO -> SEPARACAO
e CLASSIFICACAO -> IDENTIFICACAO SEM NENHUMA ALTERAÇÃO — a tabela de
transições, um componente estável e validado por invariante própria
(ver `dominio_esteira.py`, o `assert` logo após a tabela), não precisou
mudar. Por isso esta função vive num arquivo NOVO, pequeno e aditivo,
em vez de editar `dominio_esteira.py` (mesmo sendo uma mudança mínima,
a missão pede para nunca forçar mudança num componente estável só para
"já ligar tudo" — aqui não foi necessário, então nada nele foi tocado).

Direção do import (`modulo01` -> `classificacao`) segue o precedente já
estabelecido por `ponte_prestacao_holerite.py` (mesma direção) — nunca o
inverso, o que evitaria abrir uma dependência circular entre os dois
pacotes.

Esta função só SUGERE a próxima etapa — nunca chama `avancar_etapa`
nem `validar_transicao_etapa` sozinha; quem orquestra a esteira decide
se aplica a sugestão (mantém "automação por confiança, ação humana para
exceção": INCONCLUSIVO nunca sugere uma etapa sozinho -- fica para
decisão humana explícita, nunca uma adivinhação silenciosa)."""
from __future__ import annotations

from typing import Optional

from ...classificacao.resolucao_master_documental import (
    DecisaoGranularidadeDocumento,
    EstadoGranularidadeDocumento,
)
from .dominio_esteira import EtapaEsteira

_ETAPA_SUGERIDA_POR_GRANULARIDADE = {
    EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER: EtapaEsteira.SEPARACAO,
    EstadoGranularidadeDocumento.UNITARIO: EtapaEsteira.IDENTIFICACAO,
}


def proxima_etapa_sugerida_apos_classificacao(
    decisao: DecisaoGranularidadeDocumento,
) -> Optional[EtapaEsteira]:
    """POTENCIALMENTE_MASTER -> SEPARACAO; UNITARIO -> IDENTIFICACAO
    (pula SEPARACAO, já previsto e permitido por `TRANSICOES_ETAPA_
    PERMITIDAS`); INCONCLUSIVO -> None (evidência insuficiente para
    decidir automaticamente -- nunca escolhe um caminho "por padrão",
    fica para revisão humana, nunca uma tentativa de adivinhação
    silenciosa, ver `/CLAUDE.md` §4)."""
    return _ETAPA_SUGERIDA_POR_GRANULARIDADE.get(decisao.estado)
