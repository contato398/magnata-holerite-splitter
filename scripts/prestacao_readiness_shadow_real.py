"""Executa o Prestacao Readiness Shadow com leitura real e somente GET."""

from __future__ import annotations

import argparse
import json
import os
import sys

from requests import RequestException


RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)
from magnata_os.classificacao.politica_requisitos_prestacao import (
    PoliticaRequisitosPrestacao,
)
from magnata_os.classificacao.prestacao_shadow import avaliar_prestacao_shadow
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
    F_EXT_CLIENTE,
    TABLE_EXTRATO,
    FonteInventarioPrestacaoAirtableShadow,
    _folha_mensal,
    _ids_vinculados,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (
    LeitorAirtableSomenteLeitura,
)


CREDENCIAL_ENV = "AIRTABLE_API_KEY"
POLITICA_VERSION = "1"


def _selecionar_cliente_id(
    leitor: LeitorAirtableSomenteLeitura,
    competencia_id: str,
) -> str:
    folha = _folha_mensal(competencia_id)
    registros = leitor.listar_registros(
        table_id=TABLE_EXTRATO,
        fields=[F_EXT_CLIENTE],
        filter_by_formula=f'{{Folha Mensal}}="{folha}"',
    )
    clientes = {
        cliente_id
        for registro in registros
        for cliente_id in _ids_vinculados(
            registro.get("fields", {}).get(F_EXT_CLIENTE)
        )
    }
    if not clientes:
        raise RuntimeError("SEM_CLIENTE_NOS_EXTRATOS")
    return min(clientes)


def _resolucao(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
) -> ResultadoResolucaoSemantico:
    regras = tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao,
            aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )
        for dimensao in (
            DimensaoResolucao.CLIENTE,
            DimensaoResolucao.COMPETENCIA,
        )
    )
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id="prestacao-readiness-shadow-real",
        version="1",
        escopo_documental="prestacao-contas",
        regras=regras,
    )
    resolucoes = tuple(
        ResolucaoDimensao(
            dimensao=dimensao,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(referencia,),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
        for dimensao, referencia in (
            (DimensaoResolucao.CLIENTE, cliente),
            (DimensaoResolucao.COMPETENCIA, competencia),
        )
    )
    return ResultadoResolucaoSemantico(
        documento_id=f"prestacao-shadow:{cliente.entidade_id}:{competencia.entidade_id}",
        resolver_id="prestacao-readiness-shadow-real",
        resolver_version="1",
        politica_id="politica-requisitos-prestacao",
        politica_version=POLITICA_VERSION,
        perfil=perfil,
        resolucoes=resolucoes,
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA,
        necessita_revisao_humana=False,
    )


def executar(competencia_id: str, api_key: str) -> dict:
    _folha_mensal(competencia_id)
    leitor = LeitorAirtableSomenteLeitura(api_key)
    cliente = ReferenciaCanonica(
        "CLIENTE", _selecionar_cliente_id(leitor, competencia_id)
    )
    competencia = ReferenciaCanonica("COMPETENCIA", competencia_id)
    resultado = avaliar_prestacao_shadow(
        cliente=cliente,
        competencia=competencia,
        resolucao=_resolucao(cliente, competencia),
        fonte_inventario=FonteInventarioPrestacaoAirtableShadow(leitor),
        politica=PoliticaRequisitosPrestacao(version=POLITICA_VERSION),
    )
    return {
        "cliente_id": cliente.entidade_id,
        "competencia": competencia.entidade_id,
        "estado": resultado.estado.value,
        "tipos_encontrados": [tipo for tipo, _ in resultado.contagens_observadas],
        "tipos_faltantes": list(resultado.tipos_faltantes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--competencia", required=True)
    args = parser.parse_args()
    api_key = os.environ.get(CREDENCIAL_ENV)
    if not api_key:
        print(CREDENCIAL_ENV)
        return 2
    try:
        saida = executar(args.competencia, api_key)
    except RequestException:
        print("ERRO_LEITURA_EXTERNA")
        return 2
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        return 2
    print(json.dumps(saida, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
