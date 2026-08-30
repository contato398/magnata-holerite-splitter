"""Adapter READ-ONLY de clientes da Prestação (missão "POLÍTICA
OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fase 6).

Reaproveita `LeitorAirtableSomenteLeitura.listar_clientes()` (já
existente, `airtable_leitura.py` — nenhum cliente HTTP novo criado
aqui, cláusula pétrea/Fase 6: "não criar cliente HTTP Airtable novo se
já existe"). Nenhum método de escrita, nenhuma mutação, nenhum acesso
live nesta missão (testado só com fake/stub).

DECISÃO REGISTRADA (Fase 1/2 desta missão — auditoria confirmou):
NENHUM campo "Ativo"/"Status" foi encontrado na tabela Clientes do
Airtable (`app.py` só expõe `F_CLI_NOME` e campos de ANEXO de
benefício — `F_CLI_HORAS_EXTRAS`/`F_CLI_ASSIDUIDADE`/`F_CLI_VRVA`/
`F_CLI_ALMOCO_JANTA`/`F_CLI_DIARIAS` — que armazenam o PDF já
processado daquele benefício, não uma flag de obrigatoriedade). Sem
evidência de um campo real de "cliente ativo", `listar_ativos` aqui
devolve TODOS os clientes cadastrados — nunca um subconjunto inventado.
Se um campo de status real existir e ainda não foi mapeado, é uma
NECESSITA REVISÃO explícita (cláusula pétrea #15), não algo a resolver
por suposição nesta missão."""
from __future__ import annotations

from typing import Tuple

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica

from .airtable_leitura import LeitorAirtableSomenteLeitura


class FonteClientesPrestacaoAirtable:
    """Implementa `FonteClientesPrestacao` (Protocol,
    `classificacao/fonte_clientes_prestacao.py`) sobre o leitor
    read-only já existente. `listar_ativos` ignora `contexto`
    (nenhum campo de vigência por ciclo comprovado no cadastro hoje —
    ver decisão registrada acima); aceito como parâmetro para manter a
    assinatura do Protocol estável quando/se esse campo existir."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def listar_ativos(
        self, contexto: ContextoCicloPrestacao,
    ) -> Tuple[ReferenciaCanonica, ...]:
        candidatos = self._leitor.listar_clientes()
        return tuple(
            ReferenciaCanonica('CLIENTE', candidato.cliente_id)
            for candidato in candidatos
        )
