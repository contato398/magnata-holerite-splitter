from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from magnata_os.central.localizacao import (
    DecisaoLocalizacao,
    FonteNomeada,
    StatusConsultaFonte,
    data_recebimento_email,
    localizar_documento,
)
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_documento_inventario_interna import (
    FonteCandidatosDocumentoInventarioInterna,
)
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.dominio_esteira import LoteDocumental, SituacaoEsteira
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.documental.modulo01.repositorio_esteira import RepositorioLotesEmMemoria


NECESSIDADE = "necessidade-sintetica"


def documento(documento_id: str, hash_sha256: str) -> Documento:
    agora = datetime.now(timezone.utc)
    return Documento(
        documento_id=documento_id,
        arquivo_original=f"s3://bucket/{hash_sha256}",
        nome_original=f"{documento_id}.pdf",
        mime_type="application/pdf",
        tamanho=1,
        hash_sha256=hash_sha256,
        origem="teste",
        recebido_em=agora,
        lote_id=None,
        status="REGISTRADO",
        correlation_id="teste",
        criado_em=agora,
        atualizado_em=agora,
    )


class Fixa:
    def __init__(self, *documentos):
        self.documentos = documentos
        self.chamadas = 0

    def candidatos_para(self, necessidade):
        self.chamadas += 1
        return self.documentos


class Quebrada:
    def candidatos_para(self, necessidade):
        raise ConnectionError("detalhe com possível dado pessoal")


def test_localiza_na_primeira_fonte_e_nao_consulta_as_seguintes():
    seguinte = Fixa(documento("d2", "b" * 64))
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("interna", Fixa(documento("d1", "a" * 64))), FonteNomeada("legado", seguinte)],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert resultado.documento_selecionado.documento_id == "d1"
    assert resultado.fonte_selecionada == "interna"
    assert not resultado.requer_acao_humana
    assert seguinte.chamadas == 0
    assert [(c.fonte, c.status) for c in resultado.consultas] == [
        ("interna", StatusConsultaFonte.CONSULTADA),
        ("legado", StatusConsultaFonte.NAO_CONSULTADA),
    ]


def test_fonte_vazia_segue_para_a_proxima_prioridade():
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("interna", Fixa()), FonteNomeada("legado", Fixa(documento("d2", "b" * 64)))],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert resultado.fonte_selecionada == "legado"
    assert resultado.consultas[0].documento_ids == ()


def test_nenhum_candidato_sem_falha_eh_nao_localizado_nas_fontes_consultadas():
    resultado = localizar_documento(NECESSIDADE, [FonteNomeada("a", Fixa()), FonteNomeada("b", Fixa())])

    assert resultado.decisao is DecisaoLocalizacao.NAO_LOCALIZADO
    assert resultado.documento_selecionado is None
    assert all(c.status is StatusConsultaFonte.CONSULTADA for c in resultado.consultas)


def test_mesmo_conteudo_repetido_eh_deduplicado_por_hash():
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("a", Fixa(documento("d2", "a" * 64), documento("d1", "a" * 64), documento("d1", "a" * 64)))],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert [d.documento_id for d in resultado.candidatos] == ["d1"]


def test_conteudos_distintos_sao_ambiguos_e_exigem_acao_humana():
    resultado = localizar_documento(
        NECESSIDADE, [FonteNomeada("a", Fixa(documento("d1", "a" * 64), documento("d2", "b" * 64)))]
    )

    assert resultado.decisao is DecisaoLocalizacao.AMBIGUO
    assert resultado.documento_selecionado is None
    assert resultado.requer_acao_humana
    assert len(resultado.candidatos) == 2


def test_mesmo_documento_id_com_hashes_diferentes_eh_ambiguo():
    resultado = localizar_documento(
        NECESSIDADE, [FonteNomeada("a", Fixa(documento("d1", "a" * 64), documento("d1", "b" * 64)))]
    )

    assert resultado.decisao is DecisaoLocalizacao.AMBIGUO


def test_falha_de_fonte_prioritaria_nunca_permite_selecionar_candidato_inferior():
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("interna", Quebrada()), FonteNomeada("legado", Fixa(documento("d2", "b" * 64)))],
    )

    assert resultado.decisao is DecisaoLocalizacao.INDETERMINADO
    assert resultado.documento_selecionado is None
    assert resultado.requer_acao_humana
    assert [d.documento_id for d in resultado.candidatos] == ["d2"]
    assert resultado.consultas[0].status is StatusConsultaFonte.FALHOU
    assert resultado.consultas[0].erro_tipo == "ConnectionError"


def test_sem_candidato_com_falha_eh_indeterminado_nunca_nao_localizado():
    resultado = localizar_documento(NECESSIDADE, [FonteNomeada("a", Fixa()), FonteNomeada("b", Quebrada())])

    assert resultado.decisao is DecisaoLocalizacao.INDETERMINADO
    assert "b" in resultado.motivo


def test_falha_em_fonte_posterior_nao_consultada_nao_afeta_localizacao():
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("a", Fixa(documento("d1", "a" * 64))), FonteNomeada("b", Quebrada())],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert resultado.consultas[1].status is StatusConsultaFonte.NAO_CONSULTADA


def test_evidencia_registra_rastro_sem_mensagem_de_erro_nem_nome_de_arquivo():
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("a", Quebrada()), FonteNomeada("b", Fixa(documento("d1", "a" * 64)))],
    )

    evidencia = resultado.como_evidencia()

    assert evidencia["decisao"] == "INDETERMINADO"
    assert [c["fonte"] for c in evidencia["consultas"]] == ["a", "b"]
    assert evidencia["candidatos"] == [{"documento_id": "d1", "hash_sha256": "a" * 64}]
    texto = repr(evidencia)
    assert "dado pessoal" not in texto
    assert "d1.pdf" not in texto


def test_contrato_de_entrada_rejeita_fontes_vazias_ou_nomes_duplicados():
    with pytest.raises(ValueError):
        localizar_documento(NECESSIDADE, [])
    with pytest.raises(ValueError):
        localizar_documento(NECESSIDADE, [FonteNomeada("a", Fixa()), FonteNomeada("a", Fixa())])
    with pytest.raises(ValueError):
        FonteNomeada(" ", Fixa())


def test_fonte_interna_de_inventario_existente_serve_como_fonte():
    cliente = ReferenciaCanonica("CLIENTE", "cli-sintetico")
    competencia = ReferenciaCanonica("COMPETENCIA", "2026-09")
    repositorio = RepositorioDocumentosEmMemoria()
    repositorio.salvar(documento("doc-001", "c" * 64))
    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(
        ItemInventarioPrestacao(
            documento_id="doc-001",
            tipo_documental="Extrato da Folha de Pagamento",
            cliente=cliente,
            competencia=competencia,
        )
    )
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental="Extrato da Folha de Pagamento",
        motivo_exigencia="teste",
    )

    resultado = localizar_documento(
        necessidade,
        [FonteNomeada("inventario_interno", FonteCandidatosDocumentoInventarioInterna(inventario, repositorio))],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert resultado.documento_selecionado.documento_id == "doc-001"


T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def por_data(datas):
    return lambda documento: datas.get(documento.documento_id)


def test_fonte_com_criterio_de_versao_seleciona_o_mais_recente_e_mantem_o_substituido():
    antigo, novo = documento("d1", "a" * 64), documento("d2", "b" * 64)
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("email", Fixa(antigo, novo), data_versao=por_data({"d1": T0, "d2": T0 + timedelta(days=1)}))],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert resultado.documento_selecionado.documento_id == "d2"
    assert {d.documento_id for d in resultado.candidatos} == {"d1", "d2"}
    assert "mais recente" in resultado.motivo


def test_criterio_de_versao_sem_data_em_algum_candidato_continua_ambiguo():
    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("email", Fixa(documento("d1", "a" * 64), documento("d2", "b" * 64)), data_versao=por_data({"d2": T0}))],
    )

    assert resultado.decisao is DecisaoLocalizacao.AMBIGUO
    assert "sem data em d1" in resultado.motivo


def test_criterio_de_versao_com_empate_na_data_mais_recente_continua_ambiguo():
    resultado = localizar_documento(
        NECESSIDADE,
        [
            FonteNomeada(
                "email",
                Fixa(documento("d1", "a" * 64), documento("d2", "b" * 64), documento("d3", "c" * 64)),
                data_versao=por_data({"d1": T0 - timedelta(days=1), "d2": T0, "d3": T0}),
            )
        ],
    )

    assert resultado.decisao is DecisaoLocalizacao.AMBIGUO


def test_criterio_de_versao_nunca_supera_falha_de_fonte_prioritaria():
    resultado = localizar_documento(
        NECESSIDADE,
        [
            FonteNomeada("interna", Quebrada()),
            FonteNomeada("email", Fixa(documento("d1", "a" * 64), documento("d2", "b" * 64)), data_versao=por_data({"d1": T0, "d2": T0 + timedelta(days=1)})),
        ],
    )

    assert resultado.decisao is DecisaoLocalizacao.INDETERMINADO


def lote(lote_id, origem, metadados):
    return LoteDocumental(
        lote_id=lote_id,
        origem=origem,
        recebido_em=T0,
        quantidade_arquivos=1,
        situacao=SituacaoEsteira.CONCLUIDO,
        correlation_id="teste",
        criado_em=T0,
        atualizado_em=T0,
        metadados=metadados,
    )


def test_data_do_email_vem_do_lote_e_nao_do_horario_de_registro_no_sistema():
    lotes = RepositorioLotesEmMemoria()
    lotes.salvar(lote("l-antigo", "email", {"recebido_em_origem": T0.isoformat()}))
    lotes.salvar(lote("l-novo", "email", {"recebido_em_origem": (T0 + timedelta(days=2)).isoformat()}))
    # captura de backlog: o e-mail NOVO foi registrado no sistema ANTES do antigo
    novo = replace(documento("d-novo", "b" * 64), lote_id="l-novo", recebido_em=T0)
    antigo = replace(documento("d-antigo", "a" * 64), lote_id="l-antigo", recebido_em=T0 + timedelta(days=5))

    resultado = localizar_documento(
        NECESSIDADE,
        [FonteNomeada("email", Fixa(antigo, novo), data_versao=data_recebimento_email(lotes))],
    )

    assert resultado.decisao is DecisaoLocalizacao.LOCALIZADO
    assert resultado.documento_selecionado.documento_id == "d-novo"


@pytest.mark.parametrize(
    "lote_id, lote_salvo",
    [
        (None, None),
        ("l-inexistente", None),
        ("l-upload", lote("l-upload", "upload", {"recebido_em_origem": T0.isoformat()})),
        ("l-sem-data", lote("l-sem-data", "email", {})),
        ("l-data-invalida", lote("l-data-invalida", "email", {"recebido_em_origem": "ontem"})),
        ("l-sem-fuso", lote("l-sem-fuso", "email", {"recebido_em_origem": "2026-09-01T12:00:00"})),
    ],
)
def test_data_do_email_desconhecida_devolve_none(lote_id, lote_salvo):
    lotes = RepositorioLotesEmMemoria()
    if lote_salvo is not None:
        lotes.salvar(lote_salvo)

    data = data_recebimento_email(lotes)(replace(documento("d1", "a" * 64), lote_id=lote_id))

    assert data is None
