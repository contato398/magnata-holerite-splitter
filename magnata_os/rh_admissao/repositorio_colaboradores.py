"""Porta (contrato) do repositório de Cadastro de Colaborador.

Protocol mínimo -- domínio e wiring dependem só desta interface, nunca
de um driver concreto (`/CLAUDE.md` §3, "adapters para todo serviço
externo"). A implementação Postgres real vive em
`magnata_os/rh_admissao/adapters/repositorio_colaboradores_postgres.py`;
um dublê em memória para teste vive junto dos testes de domínio/wiring
(nunca aqui -- este módulo é só o contrato).

Idempotência: `salvar` é um upsert por `colaborador_id` -- a MESMA
chave de idempotência que `gatilho_admissao.RegistroGatilhoAdmissaoEmMemoria`
já usa. Reprocessar o mesmo kit nunca duplica linha; `salvar` nunca
decide sozinho se uma mudança de `local_trabalho` já definido é
legítima -- essa regra é do domínio
(`dominio_cadastro_colaborador.aplicar_determinacao_local_trabalho`),
aplicada pelo chamador ANTES de invocar `salvar`.

`cpf` neste contrato é sempre o valor em claro (`Colaborador.cpf`,
`str`) -- o domínio e esta porta nunca sabem que existe cifra em
repouso; cifrar/decifrar é responsabilidade exclusiva do adapter
Postgres (`/CLAUDE.md` §3, "domínio sem dependência de... qualquer
fornecedor").

Histórico append-only de correção de `local_trabalho`
(`EventoCorrecaoLocalTrabalho`, `dominio_cadastro_colaborador.py`):
`registrar_evento_correcao_local_trabalho` é a ÚNICA forma de escrita
(nunca um `atualizar`/`editar` -- um evento já registrado nunca é
alterado nem apagado, `/CLAUDE.md` §4) e `listar_historico_correcao_
local_trabalho` é só leitura, por `colaborador_id`, na ordem em que os
eventos foram registrados.
"""
from __future__ import annotations

from typing import Optional, Protocol, Tuple

from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    Colaborador,
    EventoCorrecaoLocalTrabalho,
)


class RepositorioColaboradores(Protocol):
    def salvar(self, colaborador: Colaborador) -> Colaborador:
        """Upsert por `colaborador_id`. Devolve o registro persistido
        (pode divergir do argumento em `criado_em`, quando a linha já
        existia)."""
        ...

    def buscar_por_id(self, colaborador_id: str) -> Optional[Colaborador]:
        ...

    def listar(self) -> Tuple[Colaborador, ...]:
        ...

    def registrar_evento_correcao_local_trabalho(
        self, evento: EventoCorrecaoLocalTrabalho,
    ) -> EventoCorrecaoLocalTrabalho:
        """Grava `evento` no histórico append-only -- nunca sobrescreve
        nem remove um evento já registrado. Devolve o próprio `evento`
        (não há upsert/merge aqui: cada chamada é um evento novo)."""
        ...

    def listar_historico_correcao_local_trabalho(
        self, colaborador_id: str,
    ) -> Tuple[EventoCorrecaoLocalTrabalho, ...]:
        """Todos os eventos de correção de `local_trabalho` já
        registrados para `colaborador_id`, na ordem em que foram
        gravados (nunca por `determinado_em`, que é entrada do
        chamador -- ver adapter)."""
        ...
