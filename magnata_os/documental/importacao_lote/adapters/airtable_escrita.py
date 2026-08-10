"""Adapter de ESCRITA (create/upload/releitura/delete condicional) ao
Airtable — Fase 4, isolado de `airtable_leitura.py` (só GET) de propósito
(ver CLAUDE.md do módulo: "se uma necessidade de escrita aparecer, é um
adapter novo, revisado à parte, não uma extensão deste").

Nunca importa `app.py` (legado protegido). IDs de tabela/campo duplicados
aqui deliberadamente, mesmo custo já aceito em `airtable_leitura.py`.
`MESES_PT` duplicado da mesma forma (ver app.py:587) — só para compor o
texto `folha_mensal` no mesmo formato já usado em produção ("Julho 2026"),
nunca para decidir competência sozinho (isso vem de `ConfiguracaoExecucao`).

NENHUMA chamada real é feita por este módulo nesta fase — toda chamada
usa `requests`, mas nenhum teste deste módulo aciona rede de verdade
(sempre via `unittest.mock`/monkeypatch em `requests.post/get/delete`).
"""

from __future__ import annotations

import base64
from typing import Optional

import requests

from ..contratos import TipoDocumental

BASE_ID = 'appaCpIVj7Q97VhFy'
TABLE_HOL = 'tblVaUgZeFfa5zRcH'
TABLE_EXTRATO = 'tblJCUcFBVTH5W2kP'

F_HOL_NOME = 'fldS42HdVbLhDRVOY'
F_HOL_STATUS = 'fld0hQpNpQTVmDSeZ'
F_HOL_FUNC = 'fldTXMjeHfgyDas9f'
F_HOL_DATA = 'fld8hTVUDyDf5jfPE'
F_HOL_FOLHA = 'fldqQZwNnMf8BGfyP'
F_HOL_PDF = 'fldGXsgmuADtZIgtx'
F_HOL_MES_CONT = 'fldUYB4uxkmBf7vDe'

F_EXT_STATUS = 'fldozFq8FJAOZMqns'
F_EXT_FOLHA = 'fldDqvqtFqN0U5UBD'
F_EXT_CLIENTE = 'fldKtdZpZ4fd7XpAX'
F_EXT_PDF = 'fldznv1E24rfbZt34'
F_EXT_DATA = 'fldZ3q923bEAqUekZ'

MESES_PT = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


def formatar_folha_mensal(ano: int, mes: int) -> str:
    """"Julho 2026" — mesmo formato usado em `criar_registro_holerite`/
    `criar_registro_extrato` de app.py (produção), reimplementado aqui
    para não importar o legado."""
    return f'{MESES_PT[mes - 1]} {ano}'


class ErroEscritaAirtable(Exception):
    """Erro de escrita/leitura no Airtable que preserva o motivo exato
    (status HTTP + corpo sanitizado), e classifica se é seguro tentar de
    novo (`retryable`). Nunca inclui a API key na mensagem — só o corpo
    de resposta do Airtable, que não contém o header Authorization."""

    def __init__(self, status_code: int, body_text: str, context: str = ''):
        self.status_code = status_code
        self.body_text = (body_text or '')[:500]
        self.context = context
        self.retryable = status_code == 429 or status_code >= 500
        super().__init__(
            f'[{context}] Airtable HTTP {status_code} '
            f'(retryable={self.retryable}): {self.body_text}'
        )


def _levantar_se_erro(r, context: str) -> None:
    if not r.ok:
        raise ErroEscritaAirtable(r.status_code, r.text, context)


class EscritorAirtable:
    """Superfície mínima de escrita necessária ao escritor.py (item 8 do
    macrocomando). Timeouts explícitos em toda chamada; nenhum retry
    automático aqui dentro — decidir re-tentar é responsabilidade de
    quem orquestra (escritor.py), que tem acesso ao estado persistido do
    item (tentativas, situação) para decidir com segurança."""

    def __init__(self, api_key: str, timeout_escrita: int = 30, timeout_upload: int = 60):
        self._api_key = api_key
        self._timeout_escrita = timeout_escrita
        self._timeout_upload = timeout_upload

    def _headers_json(self) -> dict:
        return {'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json'}

    def _headers_get(self) -> dict:
        return {'Authorization': f'Bearer {self._api_key}'}

    # ── Create ───────────────────────────────────────────────────────────

    def criar_registro_holerite(
        self, nome_referencia: str, func_id: str, folha_mensal: str,
        data_str: str, mes_cont_id: Optional[str],
    ) -> str:
        campos = {
            # Mesmo formato de app.py (produção): "Nome - Folha Mensal".
            F_HOL_NOME: f'{nome_referencia} - {folha_mensal}',
            F_HOL_STATUS: 'Concluído',
            F_HOL_FUNC: [func_id],
            F_HOL_DATA: data_str,
            F_HOL_FOLHA: folha_mensal,
        }
        if mes_cont_id:
            campos[F_HOL_MES_CONT] = [mes_cont_id]
        r = requests.post(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
            headers=self._headers_json(),
            json={'fields': campos, 'typecast': True},
            timeout=self._timeout_escrita,
        )
        _levantar_se_erro(r, f'criar holerite ({func_id})')
        return r.json()['id']

    def criar_registro_extrato(
        self, cliente_id: str, folha_mensal: str, data_str: str,
    ) -> str:
        campos = {
            F_EXT_STATUS: 'Concluido',
            F_EXT_FOLHA: folha_mensal,
            F_EXT_CLIENTE: [cliente_id],
            F_EXT_DATA: data_str,
        }
        r = requests.post(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_EXTRATO}',
            headers=self._headers_json(),
            json={'fields': campos, 'typecast': True},
            timeout=self._timeout_escrita,
        )
        _levantar_se_erro(r, f'criar extrato ({cliente_id})')
        return r.json()['id']

    def criar_registro(
        self, tipo: TipoDocumental, entidade_id: str, folha_mensal: str,
        data_str: str, mes_cont_id: Optional[str], nome_referencia: str = '',
    ) -> str:
        """Despacho por tipo — único ponto que `escritor.py` precisa
        chamar, sem decidir tabela/campo sozinho."""
        if tipo == TipoDocumental.HOLERITE:
            return self.criar_registro_holerite(nome_referencia, entidade_id, folha_mensal, data_str, mes_cont_id)
        return self.criar_registro_extrato(entidade_id, folha_mensal, data_str)

    # ── Upload ───────────────────────────────────────────────────────────

    def _campo_pdf(self, tipo: TipoDocumental) -> str:
        return F_HOL_PDF if tipo == TipoDocumental.HOLERITE else F_EXT_PDF

    def _tabela(self, tipo: TipoDocumental) -> str:
        return TABLE_HOL if tipo == TipoDocumental.HOLERITE else TABLE_EXTRATO

    def anexar_pdf(
        self, tipo: TipoDocumental, record_id: str, pdf_bytes: bytes, filename: str,
    ) -> dict:
        field_id = self._campo_pdf(tipo)
        url = f'https://content.airtable.com/v0/{BASE_ID}/{record_id}/{field_id}/uploadAttachment'
        r = requests.post(
            url,
            headers=self._headers_json(),
            json={
                'contentType': 'application/pdf',
                'filename': filename,
                'file': base64.b64encode(pdf_bytes).decode('utf-8'),
            },
            timeout=self._timeout_upload,
        )
        _levantar_se_erro(r, f'anexar PDF {tipo.value} {record_id}')
        return r.json()

    # ── Releitura / confirmação ─────────────────────────────────────────

    def confirmar_attachment(self, tipo: TipoDocumental, record_id: str) -> bool:
        """Releitura do registro — True só se o campo de anexo realmente
        tem ao menos um arquivo. Nunca confia na resposta 2xx do upload
        sozinha (item 8 do macrocomando: "confirmar attachment por
        releitura")."""
        field_id = self._campo_pdf(tipo)
        tabela = self._tabela(tipo)
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{tabela}/{record_id}',
            headers=self._headers_get(),
            params={'returnFieldsByFieldId': 'true', 'fields[]': [field_id]},
            timeout=self._timeout_escrita,
        )
        _levantar_se_erro(r, f'releitura confirmação {tipo.value} {record_id}')
        anexos = (r.json().get('fields', {}) or {}).get(field_id) or []
        return len(anexos) > 0

    # ── Compensação ──────────────────────────────────────────────────────

    def deletar_registro_condicional(self, tipo: TipoDocumental, record_id: str) -> bool:
        """Executa o DELETE. Não decide sozinho SE é seguro deletar —
        isso é responsabilidade de `escritor.py`, que só chama este
        método depois de confirmar (via `confirmar_attachment` == False +
        `external_criado_por_esta_execucao` == True) que o registro foi
        criado por esta execução e ainda não foi concluído por nenhuma
        tentativa. Retorna True se o delete teve sucesso; False em
        qualquer falha (nunca lança para não interromper a decisão de
        `failed_orphaned` vs `failed_compensated` de quem chamou)."""
        tabela = self._tabela(tipo)
        try:
            r = requests.delete(
                f'https://api.airtable.com/v0/{BASE_ID}/{tabela}/{record_id}',
                headers=self._headers_get(),
                timeout=self._timeout_escrita,
            )
            return r.ok
        except requests.RequestException:
            return False
