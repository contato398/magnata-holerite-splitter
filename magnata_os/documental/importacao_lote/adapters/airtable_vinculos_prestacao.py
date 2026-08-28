"""Adapter temporario read-only de vinculos canonicos da prestacao."""

from __future__ import annotations

from magnata_os.classificacao.contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EvidenciaSanitizada,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)

from .airtable_leitura import LeitorAirtableSomenteLeitura, TABLE_FUNC


TABLE_LOCAIS = "tblZy1WfzmGIeR8ZP"
F_FUNC_LOCAIS = "fldqpwuLJsZsavaEJ"
F_LOCAL_CLIENTE = "fldu9xd2vvoMQ2Iqb"


def _ids_vinculados(valor: object) -> tuple[str, ...]:
    if not isinstance(valor, list):
        return ()
    ids = {
        item if isinstance(item, str) else item.get("id")
        for item in valor
        if isinstance(item, str)
        or (isinstance(item, dict) and isinstance(item.get("id"), str))
    }
    return tuple(sorted(item for item in ids if item))


def _escapar_formula(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace('"', '\\"')


def _filtro_ids(ids: tuple[str, ...]) -> str:
    expressoes = tuple(
        f'RECORD_ID()="{_escapar_formula(record_id)}"' for record_id in ids
    )
    if len(expressoes) == 1:
        return expressoes[0]
    return f"OR({','.join(expressoes)})"


class FonteVinculosPrestacaoAirtableShadow:
    """Le os links Funcionario -> Local -> Cliente sem qualquer escrita."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def resolver_clientes(
        self,
        origem: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        if competencia.tipo_entidade != "COMPETENCIA":
            raise ValueError("competencia deve ser referencia canonica de COMPETENCIA")
        if origem.tipo_entidade in {"COLABORADOR", "FUNCIONARIO"}:
            locais = self._locais_do_funcionario(origem.entidade_id)
        elif origem.tipo_entidade == "UNIDADE_POSTO":
            locais = (origem.entidade_id,)
        else:
            raise ValueError(
                "origem deve ser COLABORADOR, FUNCIONARIO ou UNIDADE_POSTO"
            )
        return self._resolver_por_locais(origem, locais)

    def _locais_do_funcionario(self, funcionario_id: str) -> tuple[str, ...]:
        registros = self._leitor.listar_registros(
            table_id=TABLE_FUNC,
            fields=[F_FUNC_LOCAIS],
            filter_by_formula=_filtro_ids((funcionario_id,)),
        )
        return tuple(
            sorted(
                {
                    local_id
                    for registro in registros
                    for local_id in _ids_vinculados(
                        registro.get("fields", {}).get(F_FUNC_LOCAIS)
                    )
                }
            )
        )

    def _resolver_por_locais(
        self,
        origem: ReferenciaCanonica,
        locais: tuple[str, ...],
    ) -> ResolucaoDimensao:
        registros = (
            self._leitor.listar_registros(
                table_id=TABLE_LOCAIS,
                fields=[F_LOCAL_CLIENTE],
                filter_by_formula=_filtro_ids(locais),
            )
            if locais
            else []
        )
        pares = tuple(
            sorted(
                {
                    (registro["id"], cliente_id)
                    for registro in registros
                    for cliente_id in _ids_vinculados(
                        registro.get("fields", {}).get(F_LOCAL_CLIENTE)
                    )
                }
            )
        )
        clientes = tuple(
            ReferenciaCanonica("CLIENTE", cliente_id)
            for cliente_id in sorted({cliente_id for _, cliente_id in pares})
        )
        evidencias = tuple(
            EvidenciaSanitizada(
                tipo_evidencia="VINCULO_CANONICO",
                fonte="airtable_readonly",
                referencia_fonte=local_id,
                metodo="funcionario_local_cliente",
                forca=NivelConfianca.FORTE,
                entidade_candidata=ReferenciaCanonica("CLIENTE", cliente_id),
                motivo_sanitizado="vinculo_explicito",
            )
            for local_id, cliente_id in pares
        )
        if not clientes:
            estado = EstadoResolucaoDimensao.NAO_ENCONTRADA
            confirmados = ()
            candidatos = ()
        elif len(clientes) == 1:
            estado = EstadoResolucaoDimensao.RESOLVIDA
            confirmados = clientes
            candidatos = ()
        else:
            estado = EstadoResolucaoDimensao.AMBIGUA
            confirmados = ()
            candidatos = clientes
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE,
            estado=estado,
            valores_confirmados=confirmados,
            candidatos=candidatos,
            evidencias=evidencias,
            metodo="funcionario_local_cliente",
            confianca=ConfiancaResolucao(
                NivelConfianca.FORTE if clientes else NivelConfianca.INDETERMINADA
            ),
        )
