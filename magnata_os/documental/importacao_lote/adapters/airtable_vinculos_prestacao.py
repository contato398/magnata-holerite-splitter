"""Adapter temporario read-only de vinculos canonicos da prestacao."""

from __future__ import annotations

from typing import FrozenSet

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
from .airtable_link_utils import filtro_ids as _filtro_ids, ids_vinculados as _ids_vinculados

# _ids_vinculados/_filtro_ids: PROMOVIDAS para airtable_link_utils.py
# (missão "...ADAPTERS REAIS...") quando um segundo adapter
# (airtable_unidade_posto_prestacao.py) precisou da MESMA lógica --
# reimportadas com os MESMOS nomes locais, zero mudança de
# comportamento, zero duplicação.

TABLE_LOCAIS = "tblZy1WfzmGIeR8ZP"
F_FUNC_LOCAIS = "fldqpwuLJsZsavaEJ"
F_LOCAL_CLIENTE = "fldu9xd2vvoMQ2Iqb"


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

    def clientes_atuais_do_posto(self, posto_id: str) -> FrozenSet[str]:
        """Snapshot ATUAL (sem vigência histórica -- Airtable só expõe o
        link corrente) dos Clientes vinculados a um posto/local, via o
        MESMO link Local->Cliente já lido por `resolver_clientes`
        (`_resolver_por_locais`) -- nenhuma segunda leitura, nenhum campo
        novo criado para esta missão (missão "SHADOW CLIENTE X POSTO
        AIRTABLE V1", frente 7 de redução de dependência do Airtable).

        Devolve um `FrozenSet` (zero, um ou, em dado sujo, mais de um
        cliente -- a invariante de "1 cliente por posto" é garantida só
        no lado Postgres, `vigencia_cliente_por_posto`; o Airtable pode
        estar desatualizado ou ambíguo, e isso é precisamente o que a
        comparação shadow em `comparacao_airtable.py` existe para
        detectar, nunca corrigir). Usado só pela comparação diagnóstica
        -- nunca pelo corredor semântico, que continua usando
        `resolver_clientes` com a disciplina de vigência de competência
        comprovada."""
        resolucao = self._resolver_por_locais(
            ReferenciaCanonica("UNIDADE_POSTO", posto_id), (posto_id,)
        )
        return frozenset(
            referencia.entidade_id
            for referencia in resolucao.valores_confirmados + resolucao.candidatos
        )

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
