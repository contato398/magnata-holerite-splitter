"""Adapter READ-ONLY de clientes da Prestação (missão "POLÍTICA
OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fase 6).

Reaproveita `LeitorAirtableSomenteLeitura` (já existente,
`airtable_leitura.py` — nenhum cliente HTTP novo criado aqui, cláusula
pétrea/Fase 6: "não criar cliente HTTP Airtable novo se já existe").
Nenhum método de escrita, nenhuma mutação nesta missão.

CORREÇÃO REGISTRADA (validação live read-only, missão "MERGE PR #100 +
VALIDAÇÃO LIVE READ-ONLY", 2026-08-30 — corrige a decisão anterior
abaixo, nunca a apaga): a auditoria original (Fases 1/2 da missão
"POLÍTICA OPERACIONAL...") concluiu que NENHUM campo "Ativo"/"Status"
existia na tabela Clientes — essa conclusão foi obtida SEM leitura live
(só por inspeção de `app.py`, que nunca usa esse campo). A validação
live (leitura GET real, somente esquema + confirmação de 2 opções,
nunca payload de registro) confirmou que a tabela Clientes TEM um
campo `Status` real (`fld8bkTUma9T5BT6r`, singleSelect, opções
"Ativo"/"Inativo" — mesmo padrão já usado em Funcionários/`F_FUNC_
STATUS`). `listar_ativos` agora filtra por esse campo — nunca mais
devolve todos os clientes indiscriminadamente. Divergência técnica
simples (campo existente não mapeado antes), corrigida sem necessidade
de nova decisão de negócio (Fase 5 da missão: "nome de campo
diferente/status real -- autorizado corrigir o adapter")."""
from __future__ import annotations

from typing import Tuple

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica

from .airtable_leitura import TABLE_CLIENTES, LeitorAirtableSomenteLeitura

# Confirmado por leitura live do schema (GET, sem payload de registro)
# em 2026-08-30 -- mesma disciplina de duplicação de ID já usada pelos
# demais adapters deste pacote (nunca importado de app.py).
F_CLI_STATUS = 'fld8bkTUma9T5BT6r'
STATUS_CLIENTE_ATIVO = 'Ativo'


class FonteClientesPrestacaoAirtable:
    """Implementa `FonteClientesPrestacao` (Protocol,
    `classificacao/fonte_clientes_prestacao.py`) sobre o leitor
    read-only já existente. `listar_ativos` ignora `contexto` (nenhum
    campo de VIGÊNCIA POR CICLO comprovado -- Status é um snapshot
    atual, não histórico por competência); aceito como parâmetro para
    manter a assinatura do Protocol estável quando/se um campo de
    vigência por ciclo existir."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def listar_ativos(
        self, contexto: ContextoCicloPrestacao,
    ) -> Tuple[ReferenciaCanonica, ...]:
        registros = self._leitor.listar_registros(table_id=TABLE_CLIENTES, fields=[F_CLI_STATUS])
        return tuple(
            ReferenciaCanonica('CLIENTE', registro['id'])
            for registro in registros
            if registro.get('fields', {}).get(F_CLI_STATUS) == STATUS_CLIENTE_ATIVO
        )
