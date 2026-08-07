"""Adapter de leitura (SOMENTE GET) ao Airtable.

Nunca importa `app.py` (legado protegido — CLAUDE.md §7) nem faz
POST/PATCH/DELETE. IDs de tabela/campo duplicados aqui deliberadamente
(mesmos valores já usados em app.py) — módulo novo, sem acoplamento ao
legado, custo aceito de duplicação documentado (ver CLAUDE.md do módulo).

Este adapter é a forma reutilizável do componente para quando ele rodar
como serviço (fora desta sessão interativa). Na execução de HOJE, os
dados foram obtidos por leitura direta via o conector Airtable
disponível nesta sessão e injetados como listas já prontas — ver
`docs/decisoes/` e o relatório final desta rodada.
"""

from __future__ import annotations

import requests

from ..contratos import CandidatoCliente, CandidatoFuncionario

BASE_ID = 'appaCpIVj7Q97VhFy'
TABLE_FUNC = 'tblNd8G66kjwos3eP'
TABLE_CLIENTES = 'tbl0znyuCEzoCHtCV'
TABLE_HOL = 'tblVaUgZeFfa5zRcH'
TABLE_EXTRATO = 'tblJCUcFBVTH5W2kP'

F_HOL_FUNC = 'fldTXMjeHfgyDas9f'
F_EXT_CLIENTE = 'fldKtdZpZ4fd7XpAX'


class LeitorAirtableSomenteLeitura:
    """Só métodos GET. Nenhum método de escrita existe nesta classe —
    isso não é uma convenção a lembrar, é a superfície inteira dela."""

    def __init__(self, api_key: str, timeout: int = 30):
        self._headers = {'Authorization': f'Bearer {api_key}'}
        self._timeout = timeout

    def _listar_todos(self, table_id: str, fields: list[str]) -> list[dict]:
        registros: list[dict] = []
        offset = None
        while True:
            params = {'fields[]': fields, 'pageSize': 100}
            if offset:
                params['offset'] = offset
            r = requests.get(
                f'https://api.airtable.com/v0/{BASE_ID}/{table_id}',
                headers=self._headers, params=params, timeout=self._timeout,
            )
            r.raise_for_status()
            data = r.json()
            registros.extend(data.get('records', []))
            offset = data.get('offset')
            if not offset:
                break
        return registros

    def listar_funcionarios(self) -> list[CandidatoFuncionario]:
        from ..dominio import normalizar_nome
        registros = self._listar_todos(TABLE_FUNC, ['Nome Completo', 'CPF'])
        return [
            CandidatoFuncionario(
                func_id=r['id'],
                cpf=r.get('fields', {}).get('CPF'),
                nome_normalizado=normalizar_nome(r.get('fields', {}).get('Nome Completo', '')),
            )
            for r in registros
        ]

    def listar_clientes(self) -> list[CandidatoCliente]:
        from ..dominio import normalizar_nome
        registros = self._listar_todos(TABLE_CLIENTES, ['Nome', 'CNPJ'])
        return [
            CandidatoCliente(
                cliente_id=r['id'],
                cnpj=r.get('fields', {}).get('CNPJ'),
                nome_normalizado=normalizar_nome(r.get('fields', {}).get('Nome', '')),
            )
            for r in registros
        ]

    def holerites_existentes_na_folha(self, folha_mensal: str) -> set[str]:
        """Retorna o conjunto de func_id que já têm holerite criado nesta
        folha — mesma checagem de `_buscar_holerite_existente` do app.py,
        reimplementada aqui só-leitura, sem importar o legado."""
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
            headers=self._headers,
            params={
                'filterByFormula': f'{{Folha Mensal}}="{folha_mensal}"',
                'returnFieldsByFieldId': 'true',
                'fields[]': [F_HOL_FUNC],
            },
            timeout=self._timeout,
        )
        r.raise_for_status()
        func_ids = set()
        for rec in r.json().get('records', []):
            for link in (rec.get('fields', {}).get(F_HOL_FUNC) or []):
                func_ids.add(link['id'] if isinstance(link, dict) else link)
        return func_ids

    def extratos_existentes_na_folha(self, folha_mensal: str) -> set[str]:
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_EXTRATO}',
            headers=self._headers,
            params={
                'filterByFormula': f'{{Folha Mensal}}="{folha_mensal}"',
                'returnFieldsByFieldId': 'true',
                'fields[]': [F_EXT_CLIENTE],
            },
            timeout=self._timeout,
        )
        r.raise_for_status()
        cliente_ids = set()
        for rec in r.json().get('records', []):
            for link in (rec.get('fields', {}).get(F_EXT_CLIENTE) or []):
                cliente_ids.add(link['id'] if isinstance(link, dict) else link)
        return cliente_ids
