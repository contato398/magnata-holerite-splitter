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
TABLE_GUIAS = "tbl6FT1YzK1yqI77l"
F_GUIA_TIPO = "fldZc4A6stiQPI8qt"
TIPOS_DCTFWEB_DETERMINISTICOS = (
    "DCTFWeb - Declaração",
    "DCTFWeb - Recibo de Entrega",
    "Guia DCTFWeb/DARF",
)


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


class FonteEscopoClientesPorInventarioAirtableShadow:
    """Implementa `FonteEscopoClientesPrestacao.escopo_para_competencia`
    (missão "MERGE PR #108 + FECHAR BLOQUEIOS REAIS DO CORREDOR LIVE
    V2") -- fecha honestamente a lacuna registrada em `docs/decisoes/
    adapters-reais-unidade-posto-candidatos-relacao-v1.md` §9/§13:
    "nenhuma fonte real enumera clientes presentes no inventário de uma
    competência, independente de atividade atual".

    Evidência REAL: os MESMOS 2 vínculos de cliente já lidos em
    produção por `FonteInventarioPrestacaoAirtableShadow.listar`
    (Extrato/`F_EXT_CLIENTE`, FGTS/`F_FGTS_CLIENTE`) -- nenhuma tabela
    nova, nenhum campo novo, nenhuma suposição de schema não
    confirmada. A diferença: `listar()` busca TODOS os registros da
    folha e filtra por 1 cliente DEPOIS, em Python -- aqui a mesma
    busca (idêntica, por folha) é usada para AGREGAR o conjunto de
    clientes que aparecem em QUALQUER registro daquela folha, nunca
    "ativos hoje" (`FonteClientesPrestacaoAirtable.listar_ativos`, que
    lê `Status`, um snapshot sem relação com competência nenhuma).

    Guias/DCTFWeb ficam DE FORA -- essa tabela nunca carrega vínculo de
    cliente no Airtable (broadcast por desenho, `perfil_aplicabilidade_
    documental.py`); incluir um cliente aqui só por causa de um
    documento broadcast seria inventar evidência que a tabela não tem.

    Histórico REAL, nunca "hoje disfarçado de histórico": a mesma
    competência pedida SEMPRE é a que decide a folha consultada -- não
    há noção de "ciclo corrente" aqui, nenhum `ContextoCicloPrestacao`
    envolvido. Um cliente com item em Junho/2026 aparece no escopo de
    Junho mesmo que hoje esteja com `Status=Inativo`."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def escopo_para_competencia(self, competencia: ReferenciaCanonica) -> tuple[ReferenciaCanonica, ...]:
        if competencia.tipo_entidade != "COMPETENCIA":
            raise ValueError("competencia deve ser referencia canonica de COMPETENCIA")

        folha = _folha_mensal(competencia.entidade_id)
        clientes_ids: set[str] = set()
        for table_id, campo_cliente in (
            (TABLE_EXTRATO, F_EXT_CLIENTE),
            (TABLE_FGTS, F_FGTS_CLIENTE),
        ):
            registros = self._leitor.listar_registros(
                table_id=table_id,
                fields=[campo_cliente],
                filter_by_formula=f'{{Folha Mensal}}="{folha}"',
            )
            for registro in registros:
                clientes_ids |= _ids_vinculados(registro.get("fields", {}).get(campo_cliente))

        return tuple(
            ReferenciaCanonica("CLIENTE", cliente_id) for cliente_id in sorted(clientes_ids)
        )


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

        filtro_tipos_dctfweb = ",".join(
            f'{{Tipo}}="{tipo}"' for tipo in TIPOS_DCTFWEB_DETERMINISTICOS
        )
        registros_dctfweb = self._leitor.listar_registros(
            table_id=TABLE_GUIAS,
            fields=[F_GUIA_TIPO],
            filter_by_formula=(
                f'AND({{Mês Contabilidade}}="{folha}",'
                f'OR({filtro_tipos_dctfweb}))'
            ),
        )
        itens.extend(
            ItemInventarioPrestacao(
                documento_id=registro["id"],
                tipo_documental=tipo_documental,
                cliente=cliente,
                competencia=competencia,
            )
            for registro in registros_dctfweb
            if (tipo_documental := registro.get("fields", {}).get(F_GUIA_TIPO))
            in TIPOS_DCTFWEB_DETERMINISTICOS
        )
        return tuple(sorted(itens, key=lambda item: item.documento_id))
