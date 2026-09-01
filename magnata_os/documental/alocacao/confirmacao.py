"""Confirmação HUMANA de Alocação (missão "CONFIRMAÇÃO DE ALOCAÇÃO
SHADOW V1"). Fecha a lacuna já registrada nas 2 missões anteriores
desta série: não existe nenhuma fonte AUTOMÁTICA de data efetiva para
posto (`docs/decisoes/alocacao-vigencia-historica-v1.md`,
`VIGENCIA_FONTE_REAL_ENCONTRADA=FALSE`) -- a confirmação humana é o
"menor mecanismo seguro" já proposto para preencher essa memória
(`docs/decisoes/captura-automatica-vinculo-alocacao-v1.md`, Fase 6) e é
o que este módulo implementa.

**Regra pétrea desta missão:** Magnata OS é a autoridade histórica de
alocação; Airtable é fotografia operacional temporária. Nenhuma
verdade histórica nova nasce exclusivamente no Airtable, e este módulo
nunca depende do schema Airtable diretamente -- só de um `resolver`
INJETADO (duck-typed), substituível por qualquer fonte futura sem
mudar 1 linha aqui. `SolicitacaoConfirmacaoAlocacao` só conhece
`colaborador_id`/`posto_id` já resolvidos (identificadores canônicos
opacos, mesma convenção de `eventos.py`/`captura.py`/`resolucao.py`) --
nunca um CPF ou nome cru: resolver CPF -> `colaborador_id` é uma
responsabilidade de BORDA, de quem monta a solicitação (ver
`ResolverIdentidadeAlocacaoAirtableShadow.resolver_colaborador_id` em
`airtable_resolver_identidade_alocacao.py`), nunca deste módulo.
`aplicar_confirmacao_alocacao` só RE-CONFIRMA que os ids já
selecionados ainda existem no snapshot atual (`resolver.
confirmar_colaborador_existe`/`confirmar_posto_existe`) -- nunca busca
por nome/CPF sozinho.

**Regra central:** `data_efetiva` só chega a este módulo por uma
pessoa confirmando explicitamente -- nunca inferida, nunca "hoje" por
padrão. `SolicitacaoConfirmacaoAlocacao.__post_init__` recusa qualquer
valor que não seja uma `datetime.date` real (mesma disciplina de
`eventos.py::_exigir_data`); não existe nenhum caminho neste módulo que
construa uma data sozinho.

**Ação, não evento novo.** 5 ações (`ACAO_INICIAR`, `ACAO_ENCERRAR`,
`ACAO_TRANSFERIR`, `ACAO_ADICIONAR_RATEIO`, `ACAO_REMOVER_RATEIO`)
capturam a INTENÇÃO humana com precisão para auditoria, mas todas se
traduzem nos MESMOS 4 eventos canônicos já existentes
(`AlocacaoIniciada`/`AlocacaoEncerrada`, aplicados via `captura.py`
já existente, nunca reimplementado) -- nenhum domínio paralelo, nenhuma
tabela/coluna nova: "iniciar" e "adicionar rateio" são, na persistência,
a MESMA primitiva (`aplicar_alocacao_iniciada`, já idempotente e já
correta tanto para a primeira alocação quanto para uma adicional sem
fechar as demais); "encerrar" e "remover rateio" são igualmente a
mesma primitiva (`aplicar_alocacao_encerrada`, fecha só aquele posto).
A distinção de ação existe para quem CHAMA este módulo (ex.: rótulo
mostrado/auditado numa UI futura), nunca para o schema.

Aplicação sempre via `captura.py` já existente contra um repositório
SHADOW (SQLite/Postgres efêmero) -- nunca um Postgres de produção
assumido por padrão; quem chama este módulo decide qual `repo`
injetar."""
from __future__ import annotations

import dataclasses
from datetime import date
from typing import Optional

from .captura import aplicar_alocacao_encerrada, aplicar_alocacao_iniciada, aplicar_transferencia
from .eventos import AlocacaoEncerrada, AlocacaoIniciada

ACAO_INICIAR = 'iniciar'
ACAO_ENCERRAR = 'encerrar'
ACAO_TRANSFERIR = 'transferir'
ACAO_ADICIONAR_RATEIO = 'adicionar_rateio'
ACAO_REMOVER_RATEIO = 'remover_rateio'

_ACOES_VALIDAS = (ACAO_INICIAR, ACAO_ENCERRAR, ACAO_TRANSFERIR, ACAO_ADICIONAR_RATEIO, ACAO_REMOVER_RATEIO)
_ACOES_DE_ABERTURA = (ACAO_INICIAR, ACAO_ADICIONAR_RATEIO)
_ACOES_DE_FECHAMENTO = (ACAO_ENCERRAR, ACAO_REMOVER_RATEIO)


class ColaboradorNaoIdentificadoError(ValueError):
    """`colaborador_id` informado não corresponde a nenhum colaborador
    real e atual no snapshot do `resolver` -- confirmação recusada,
    nunca aplicada com identidade incerta."""


class PostoNaoIdentificadoError(ValueError):
    """`posto_id` informado não corresponde a nenhum posto real e atual
    no snapshot do `resolver` -- confirmação recusada, nunca aplicada
    com posto inexistente/desatualizado."""


@dataclasses.dataclass(frozen=True)
class SolicitacaoConfirmacaoAlocacao:
    """Entrada de UMA confirmação humana -- nunca gerada
    automaticamente, nunca deduzida de um documento. `colaborador_id`/
    `posto_id` já chegam RESOLVIDOS (ver docstring do módulo);
    `data_efetiva` é sempre obrigatória e validada na própria
    construção: um chamador sem uma data confirmada por uma pessoa
    simplesmente não consegue construir este objeto."""

    colaborador_id: str
    posto_id: str
    data_efetiva: date
    acao: str
    origem_confirmacao: str
    posto_destino_id: Optional[str] = None  # obrigatório só para ACAO_TRANSFERIR

    def __post_init__(self) -> None:
        if self.acao not in _ACOES_VALIDAS:
            raise ValueError(f'acao deve ser uma de {_ACOES_VALIDAS}, recebida {self.acao!r}')
        if not isinstance(self.data_efetiva, date):
            raise ValueError(
                'data_efetiva deve ser uma data efetiva real (datetime.date), '
                'confirmada por uma pessoa -- nunca None, nunca string, nunca "hoje" inferido')
        if not self.colaborador_id or not self.colaborador_id.strip():
            raise ValueError('colaborador_id deve ser texto nao vazio')
        if not self.posto_id or not self.posto_id.strip():
            raise ValueError('posto_id deve ser texto nao vazio')
        if not self.origem_confirmacao or not self.origem_confirmacao.strip():
            raise ValueError('origem_confirmacao deve ser texto nao vazio')
        if self.acao == ACAO_TRANSFERIR and not (self.posto_destino_id and self.posto_destino_id.strip()):
            raise ValueError('posto_destino_id e obrigatorio quando acao=transferir')
        if self.acao != ACAO_TRANSFERIR and self.posto_destino_id:
            raise ValueError('posto_destino_id so e valido quando acao=transferir')


def aplicar_confirmacao_alocacao(repo, resolver, solicitacao: SolicitacaoConfirmacaoAlocacao) -> str:
    """RE-CONFIRMA (nunca resolve por nome/CPF) que `colaborador_id`/
    `posto_id` ainda existem no snapshot atual do `resolver`, e só
    então delega a `captura.py` (idempotência/conflito/atomicidade já
    garantidas lá, nunca reimplementadas aqui). Devolve o `id` da
    alocação afetada.

    `resolver` precisa expor (duck-typed, sem Protocol formal novo --
    mesma disciplina de `captura.py` para `repo`):
      - `confirmar_colaborador_existe(colaborador_id: str) -> bool`
      - `confirmar_posto_existe(posto_id: str) -> bool`
    `repo`: `RepositorioAlocacaoPostgres`/`RepositorioAlocacaoSQLite` --
    shadow sempre, nunca Postgres de produção assumido aqui."""
    if not resolver.confirmar_colaborador_existe(solicitacao.colaborador_id):
        raise ColaboradorNaoIdentificadoError(
            f'colaborador_id {solicitacao.colaborador_id!r} nao corresponde a nenhum '
            f'colaborador real e atual no snapshot do Airtable')

    if not resolver.confirmar_posto_existe(solicitacao.posto_id):
        raise PostoNaoIdentificadoError(
            f'posto_id {solicitacao.posto_id!r} nao corresponde a nenhum posto real '
            f'e atual no snapshot do Airtable')

    if solicitacao.acao in _ACOES_DE_ABERTURA:
        return aplicar_alocacao_iniciada(
            repo,
            AlocacaoIniciada(
                solicitacao.colaborador_id, solicitacao.posto_id,
                solicitacao.data_efetiva, solicitacao.origem_confirmacao),
        )

    if solicitacao.acao in _ACOES_DE_FECHAMENTO:
        return aplicar_alocacao_encerrada(
            repo,
            AlocacaoEncerrada(
                solicitacao.colaborador_id, solicitacao.posto_id,
                solicitacao.data_efetiva, solicitacao.origem_confirmacao),
        )

    # ACAO_TRANSFERIR
    if not resolver.confirmar_posto_existe(solicitacao.posto_destino_id):
        raise PostoNaoIdentificadoError(
            f'posto_destino_id {solicitacao.posto_destino_id!r} nao corresponde '
            f'a nenhum posto real e atual no snapshot do Airtable')
    return aplicar_transferencia(
        repo, solicitacao.colaborador_id, solicitacao.posto_id, solicitacao.posto_destino_id,
        solicitacao.data_efetiva, solicitacao.origem_confirmacao,
    )
