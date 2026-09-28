from datetime import datetime, timezone

import pytest

from magnata_os.central.localizacao import (
    DecisaoLocalizacao,
    FonteNomeada,
    StatusConsultaFonte,
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
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria


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
