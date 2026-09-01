"""Pré-visualização, somente leitura, de uma confirmação de alocação
antes dela ser aplicada (missão "ENTRADA OPERACIONAL + POSTGRES
PRÓPRIO V1", FASE 3). Nunca escreve nada -- monta um retrato do que a
confirmação FARIA, para exibição humana antes do clique de confirmação
final (FASE 3 exige exatamente os campos abaixo).

**TOCTOU entre preview e confirmação (Revisão 1 desta missão):** o
preview é só informativo, nunca uma fonte de verdade para a escrita
real. `confirmacao.aplicar_confirmacao_alocacao` sempre RE-LÊ o estado
atual (shadow + Airtable) no momento da aplicação -- nunca recebe nem
confia em nenhum dado deste preview. Se o snapshot Airtable mudar entre
a pré-visualização e a confirmação, o pior efeito é um preview
mostrado ficar cosmeticamente desatualizado; a aplicação real detecta
e recusa (`ColaboradorNaoIdentificadoError`/`PostoNaoIdentificadoError`/
`ConflitoTemporalEventoError`/`EventoForaDeOrdemError`) exatamente como
sempre fez, nunca aplica algo que o preview não mostrou."""
from __future__ import annotations

import dataclasses
from datetime import date
from typing import FrozenSet, Optional

from .comparacao_airtable import EstadoComparacaoAirtable, comparar_colaborador_shadow_com_airtable
from .confirmacao import (
    ACAO_ADICIONAR_RATEIO,
    ACAO_ENCERRAR,
    ACAO_INICIAR,
    ACAO_REMOVER_RATEIO,
    ACAO_TRANSFERIR,
    SolicitacaoConfirmacaoAlocacao,
)


@dataclasses.dataclass(frozen=True)
class PreviewConfirmacaoAlocacao:
    """Exatamente os campos exigidos pela FASE 3: Colaborador, Ação,
    De, Para, Data efetiva, Estado atual Magnata OS, Snapshot atual
    Airtable, Consequência temporal."""

    colaborador_id: str
    acao: str
    posto_origem_id: str
    posto_destino_id: Optional[str]
    data_efetiva: date
    postos_atuais_magnata_os: FrozenSet[str]
    postos_atuais_airtable: Optional[FrozenSet[str]]
    estado_comparacao: EstadoComparacaoAirtable
    consequencia_temporal: str


def montar_preview(
    repo, snapshot_airtable, solicitacao: SolicitacaoConfirmacaoAlocacao, *, hoje: Optional[date] = None,
) -> PreviewConfirmacaoAlocacao:
    """`repo`/`snapshot_airtable`: mesmo duck-type já usado por
    `confirmacao.py`/`comparacao_airtable.py` -- nenhum contrato novo.
    Nunca chama nenhum método de escrita de `repo` nem de
    `snapshot_airtable`.

    `hoje`: data de referência para "estado ATUAL" (injetável para
    teste, `date.today()` por padrão) -- **deliberadamente distinta**
    de `solicitacao.data_efetiva`. "Estado atual Magnata OS"/"Snapshot
    atual Airtable" (FASE 3) significam agora, nunca a data futura ou
    passada da mudança pendente -- ler o estado corrente é uma consulta
    read-only, não a `data_efetiva` confirmada por humano (que continua
    100% intocada, nunca inferida de `hoje`)."""
    referencia = hoje if hoje is not None else date.today()
    vinculo = repo.vinculo_mais_recente_de(solicitacao.colaborador_id)
    postos_shadow = (
        frozenset(repo.postos_vigentes_em(vinculo.id, referencia, referencia))
        if vinculo is not None
        else frozenset()
    )
    try:
        postos_airtable: Optional[FrozenSet[str]] = frozenset(
            snapshot_airtable.postos_atuais_do_colaborador(solicitacao.colaborador_id))
    except Exception:
        postos_airtable = None

    estado = comparar_colaborador_shadow_com_airtable(
        repo, snapshot_airtable, solicitacao.colaborador_id, referencia)

    return PreviewConfirmacaoAlocacao(
        colaborador_id=solicitacao.colaborador_id,
        acao=solicitacao.acao,
        posto_origem_id=solicitacao.posto_id,
        posto_destino_id=solicitacao.posto_destino_id,
        data_efetiva=solicitacao.data_efetiva,
        postos_atuais_magnata_os=postos_shadow,
        postos_atuais_airtable=postos_airtable,
        estado_comparacao=estado,
        consequencia_temporal=_descrever_consequencia(solicitacao, postos_shadow),
    )


def _descrever_consequencia(solicitacao: SolicitacaoConfirmacaoAlocacao, postos_shadow: FrozenSet[str]) -> str:
    """Texto sanitizado -- só ids já opacos (`posto_id`), nunca nome de
    colaborador/local/PII (mesma disciplina de `MotivoSanitizado` em
    todo o pacote `importacao_lote`)."""
    permanecem_abertos = sorted(postos_shadow - {solicitacao.posto_id})

    if solicitacao.acao in (ACAO_INICIAR, ACAO_ADICIONAR_RATEIO):
        base = f'Abre o posto {solicitacao.posto_id!r} em {solicitacao.data_efetiva.isoformat()}.'
    elif solicitacao.acao in (ACAO_ENCERRAR, ACAO_REMOVER_RATEIO):
        base = f'Fecha o posto {solicitacao.posto_id!r} em {solicitacao.data_efetiva.isoformat()}.'
    elif solicitacao.acao == ACAO_TRANSFERIR:
        base = (
            f'Fecha o posto {solicitacao.posto_id!r} e abre o posto '
            f'{solicitacao.posto_destino_id!r} em {solicitacao.data_efetiva.isoformat()}.'
        )
    else:  # pragma: no cover -- SolicitacaoConfirmacaoAlocacao ja valida acao na construcao
        base = 'Acao desconhecida.'

    if permanecem_abertos:
        base += f' Postos que permanecem abertos, sem alteração: {permanecem_abertos}.'
    return base
