"""Fonte real do `diretorio_nomes` esperado por
`magnata_os.orquestrador.interpretar_ordem_operador_v1` (parâmetro
`Mapping[colaborador_id, nome]`, hoje opcional/vazio -- ver lacuna de
contrato registrada no cabeçalho daquele módulo e em
`docs/decisoes/cadastro-colaborador-persistente-v1.md` §4).

Este módulo NÃO altera `interpretar_ordem_operador_v1.py` -- só provê o
dicionário no MESMO formato que ele já espera, lido do Cadastro de
Colaborador PRÓPRIO (`RepositorioColaboradores`) em vez de ficar vazio.
`nome` aqui É dado pessoal (LGPD, `/CLAUDE.md` §6) -- este módulo não
imprime nem loga nenhum valor do dicionário que produz, só o devolve
para o chamador decidir o que fazer com ele."""
from __future__ import annotations

from typing import Dict

from magnata_os.rh_admissao.repositorio_colaboradores import RepositorioColaboradores


def montar_diretorio_nomes(repositorio_colaboradores: RepositorioColaboradores) -> Dict[str, str]:
    """`{colaborador_id: nome}` para todo colaborador já cadastrado --
    independente de `situacao_cadastro` (mesmo colaborador pendente de
    local de trabalho já tem nome conhecido e pode ser citado por nome
    numa ordem do operador)."""
    return {
        colaborador.colaborador_id: colaborador.nome
        for colaborador in repositorio_colaboradores.listar()
    }
