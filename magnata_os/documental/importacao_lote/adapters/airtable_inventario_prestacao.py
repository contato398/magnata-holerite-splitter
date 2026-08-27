"""Inventario shadow de extratos lido do Airtable, sem efeitos externos."""

from __future__ import annotations

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao

from ..contratos import TipoDocumental
from .airtable_leitura import (
    F_EXT_CLIENTE,
    TABLE_EXTRATO,
    LeitorAirtableSomenteLeitura,
)


_MESES_PT = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)

TABLE_FGTS = "tbl8ehgLa00cE1U3s"
F_FGTS_CLIENTE = "fldGFwcySH5TXBjDB"


def _folha_mensal(competencia_id: str) -> str:
    try:
        ano_texto, mes_texto = competencia_id.split("-", maxsplit=1)
        ano = int(ano_texto)
        mes = int(mes_texto)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("competencia deve usar o formato AAAA-MM") from exc
    if len(ano_texto) != 4 or len(mes_texto) != 2 or not 1 <= mes <= 12:
        raise ValueError("competencia deve usar o formato AAAA-MM")
    return f"{_MESES_PT[mes - 1]} {ano}"


def _ids_vinculados(valor: object) -> set[str]:
    if not isinstance(valor, list):
        return set()
    return {
        item.get("id") if isinstance(item, dict) else item
        for item in valor
        if isinstance(item, str)
        or (isinstance(item, dict) and isinstance(item.get("id"), str))
    }


class FonteInventarioPrestacaoAirtableShadow:
    """Adapter read-only para extratos e FGTS por cliente."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def listar(
        self,
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> tuple[ItemInventarioPrestacao, ...]:
        if cliente.tipo_entidade != "CLIENTE":
            raise ValueError("cliente deve ser referencia canonica de CLIENTE")
        if competencia.tipo_entidade != "COMPETENCIA":
            raise ValueError(
                "competencia deve ser referencia canonica de COMPETENCIA"
            )

        folha = _folha_mensal(competencia.entidade_id)
        itens = []
        for table_id, campo_cliente, tipo_documental in (
            (TABLE_EXTRATO, F_EXT_CLIENTE, TipoDocumental.EXTRATO_CLIENTE.value),
            (TABLE_FGTS, F_FGTS_CLIENTE, "FGTS"),
        ):
            registros = self._leitor.listar_registros(
                table_id=table_id,
                fields=[campo_cliente],
                filter_by_formula=f'{{Folha Mensal}}="{folha}"',
            )
            itens.extend(
                ItemInventarioPrestacao(
                    documento_id=registro["id"],
                    tipo_documental=tipo_documental,
                    cliente=cliente,
                    competencia=competencia,
                )
                for registro in registros
                if cliente.entidade_id
                in _ids_vinculados(
                    registro.get("fields", {}).get(campo_cliente)
                )
            )
        return tuple(sorted(itens, key=lambda item: item.documento_id))
