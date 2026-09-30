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
"""
from __future__ import annotations

from typing import Optional, Protocol, Tuple

from magnata_os.rh_admissao.dominio_cadastro_colaborador import Colaborador


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
