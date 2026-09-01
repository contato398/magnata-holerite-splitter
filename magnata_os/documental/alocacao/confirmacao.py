"""Confirmação HUMANA de Alocação (missão "CONFIRMAÇÃO DE ALOCAÇÃO
SHADOW V1"). Fecha a lacuna já registrada nas 2 missões anteriores
desta série: não existe nenhuma fonte AUTOMÁTICA de data efetiva para
posto (`docs/decisoes/alocacao-vigencia-historica-v1.md`,
`VIGENCIA_FONTE_REAL_ENCONTRADA=FALSE`) -- a confirmação humana é o
"menor mecanismo seguro" já proposto para preencher essa memória
(`docs/decisoes/captura-automatica-vinculo-alocacao-v1.md`, Fase 6) e é
o que este módulo implementa.

**Regra central:** `data_efetiva` só chega a este módulo por uma
pessoa confirmando explicitamente -- nunca inferida, nunca "hoje" por
padrão. `SolicitacaoConfirmacaoAlocacao.__post_init__` recusa qualquer
valor que não seja uma `datetime.date` real (mesma disciplina de
`eventos.py::_exigir_data`); não existe nenhum caminho neste módulo que
construa uma data sozinho.

Identidade nunca é resolvida aqui dentro -- `resolver` é sempre
INJETADO (mesma disciplina de `wiring.py::resolver_colaborador_id`):
implementação real e read-only em
`magnata_os/documental/importacao_lote/adapters/
airtable_resolver_identidade_alocacao.py`
(`ResolverIdentidadeAlocacaoAirtableShadow`); testes usam um resolvedor
sintético (dict), nunca Airtable real.

Aplicação do evento sempre via `captura.py` já existente (nunca
reimplementada) contra um repositório SHADOW (SQLite/Postgres efêmero,
`adapters/sqlite_alocacao.py`/`adapters/postgres_alocacao.py`) -- nunca
um Postgres de produção assumido por padrão; quem chama este módulo
decide qual `repo` injetar, exatamente como já acontece em
`captura.py`/`wiring.py`.

Posto é identificado por `posto_id` (Airtable record id) -- nunca por
nome livre digitado. Mesma convenção já usada em todo o subsistema de
alocação (`eventos.py`, `captura.py`, `resolucao.py`): um humano
confirmando numa tela futura SELECIONA um Local de uma lista, a
identidade carregada é sempre o record id (ver docstring de
`airtable_resolver_identidade_alocacao.py` para o motivo de não
resolver por nome)."""
from __future__ import annotations

import dataclasses
from datetime import date
from typing import Optional

from .captura import aplicar_alocacao_encerrada, aplicar_alocacao_iniciada, aplicar_transferencia
from .eventos import AlocacaoEncerrada, AlocacaoIniciada

TIPO_INICIAR = 'iniciar'
TIPO_ENCERRAR = 'encerrar'
TIPO_TRANSFERIR = 'transferir'
_TIPOS_VALIDOS = (TIPO_INICIAR, TIPO_ENCERRAR, TIPO_TRANSFERIR)


class ColaboradorNaoIdentificadoError(ValueError):
    """CPF informado não resolveu para nenhum colaborador conhecido no
    Airtable -- confirmação recusada, nunca aplicada com identidade
    incerta."""


class PostoNaoIdentificadoError(ValueError):
    """`posto_id` informado não corresponde a nenhum Local real e atual
    no Airtable -- confirmação recusada, nunca aplicada com posto
    inexistente/desatualizado."""


@dataclasses.dataclass(frozen=True)
class SolicitacaoConfirmacaoAlocacao:
    """Entrada de UMA confirmação humana -- nunca gerada
    automaticamente, nunca deduzida de um documento. `data_efetiva` é
    sempre obrigatória e validada na própria construção: um chamador
    sem uma data confirmada por uma pessoa simplesmente não consegue
    construir este objeto (mesmo princípio de `eventos.py`)."""

    colaborador_cpf: str
    posto_id: str
    data_efetiva: date
    tipo: str
    origem_evidencia: str
    posto_destino_id: Optional[str] = None  # obrigatório só para TIPO_TRANSFERIR

    def __post_init__(self) -> None:
        if self.tipo not in _TIPOS_VALIDOS:
            raise ValueError(f'tipo deve ser um de {_TIPOS_VALIDOS}, recebido {self.tipo!r}')
        if not isinstance(self.data_efetiva, date):
            raise ValueError(
                'data_efetiva deve ser uma data efetiva real (datetime.date), '
                'confirmada por uma pessoa -- nunca None, nunca string, nunca "hoje" inferido')
        if not self.colaborador_cpf or not self.colaborador_cpf.strip():
            raise ValueError('colaborador_cpf deve ser texto nao vazio')
        if not self.posto_id or not self.posto_id.strip():
            raise ValueError('posto_id deve ser texto nao vazio')
        if not self.origem_evidencia or not self.origem_evidencia.strip():
            raise ValueError('origem_evidencia deve ser texto nao vazio')
        if self.tipo == TIPO_TRANSFERIR and not (self.posto_destino_id and self.posto_destino_id.strip()):
            raise ValueError('posto_destino_id e obrigatorio quando tipo=transferir')
        if self.tipo != TIPO_TRANSFERIR and self.posto_destino_id:
            raise ValueError('posto_destino_id so e valido quando tipo=transferir')


def aplicar_confirmacao_alocacao(repo, resolver, solicitacao: SolicitacaoConfirmacaoAlocacao) -> str:
    """Resolve identidade (via `resolver`, injetado, read-only) e aplica
    o evento correspondente (via `captura.py`, já idempotente) contra
    `repo` (shadow). Devolve o `id` da alocação afetada.

    `resolver` precisa expor:
      - `resolver_colaborador_id(cpf: str) -> str | None`
      - `confirmar_posto_existe(posto_id: str) -> bool`
    (duck-typed, sem Protocol formal novo -- mesma disciplina de
    `captura.py` para `repo`)."""
    colaborador_id = resolver.resolver_colaborador_id(solicitacao.colaborador_cpf)
    if colaborador_id is None:
        raise ColaboradorNaoIdentificadoError(
            'CPF informado nao resolveu para nenhum colaborador conhecido no Airtable')

    if not resolver.confirmar_posto_existe(solicitacao.posto_id):
        raise PostoNaoIdentificadoError(
            f'posto_id {solicitacao.posto_id!r} nao corresponde a nenhum Local real e atual no Airtable')

    if solicitacao.tipo == TIPO_INICIAR:
        return aplicar_alocacao_iniciada(
            repo,
            AlocacaoIniciada(
                colaborador_id, solicitacao.posto_id, solicitacao.data_efetiva, solicitacao.origem_evidencia),
        )

    if solicitacao.tipo == TIPO_ENCERRAR:
        return aplicar_alocacao_encerrada(
            repo,
            AlocacaoEncerrada(
                colaborador_id, solicitacao.posto_id, solicitacao.data_efetiva, solicitacao.origem_evidencia),
        )

    # TIPO_TRANSFERIR
    if not resolver.confirmar_posto_existe(solicitacao.posto_destino_id):
        raise PostoNaoIdentificadoError(
            f'posto_destino_id {solicitacao.posto_destino_id!r} nao corresponde '
            f'a nenhum Local real e atual no Airtable')
    return aplicar_transferencia(
        repo, colaborador_id, solicitacao.posto_id, solicitacao.posto_destino_id,
        solicitacao.data_efetiva, solicitacao.origem_evidencia,
    )
