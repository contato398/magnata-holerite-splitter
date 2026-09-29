"""Localização central ligada à aquisição por necessidade da Prestação.

Isola `adquirir_por_necessidades` do corredor real (extração e corredor
substituídos por fakes) para provar só o que a localização muda: quais
documentos seguem para o corredor e o que acontece quando uma fonte falha.
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest

import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
from magnata_os.central.localizacao import FonteNomeada
from magnata_os.classificacao.ciclo_prestacao import ContextoCicloPrestacao, NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.modulo01.dominio import Documento


T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-09")
CLIENTE_A = ReferenciaCanonica("CLIENTE", "cli-a")
CLIENTE_B = ReferenciaCanonica("CLIENTE", "cli-b")
CICLO = ContextoCicloPrestacao(competencia_base=(2026, 9))


def documento(documento_id, hash_sha256):
    return Documento(
        documento_id=documento_id,
        arquivo_original=f"{documento_id}.pdf",
        nome_original=f"{documento_id}.pdf",
        mime_type="application/pdf",
        tamanho=1,
        hash_sha256=hash_sha256,
        origem="teste",
        recebido_em=T0,
        lote_id=None,
        status="REGISTRADO",
        correlation_id="teste",
        criado_em=T0,
        atualizado_em=T0,
    )


def necessidade(cliente):
    return NecessidadeDocumentoPrestacao(
        cliente=cliente, competencia=COMPETENCIA, tipo_documental="Extrato da Folha de Pagamento",
        motivo_exigencia="teste",
    )


class PorCliente:
    """Fonte fake: candidatos por cliente; cliente em `quebra` levanta."""

    def __init__(self, candidatos, quebra=()):
        self.candidatos = candidatos
        self.quebra = quebra

    def candidatos_para(self, necessidade):
        if necessidade.cliente in self.quebra:
            raise TimeoutError("fonte fora do ar")
        return self.candidatos.get(necessidade.cliente, ())


def contexto(**kwargs):
    return modulo.ContextoComposicaoPrestacao(
        competencia_base="2026-09",
        fonte_clientes=None,
        fonte_requisitos=None,
        repositorio_execucoes=None,
        repositorio_documentos=object(),
        armazenamento_arquivos=object(),
        **kwargs,
    )


@pytest.fixture
def corredor_fake(monkeypatch):
    processados = []
    monkeypatch.setattr(modulo, "_ler_e_extrair_texto", lambda contexto, documento: "texto")
    monkeypatch.setattr(
        modulo, "_contexto_corredor", lambda contexto, documento, texto, ciclo, cliente_do_ciclo: documento
    )

    def _executar(documento, sink):
        processados.append(documento.documento_id)
        return (object(),)

    monkeypatch.setattr(modulo, "executar_documento_readonly", _executar)
    return processados


def test_falha_de_fonte_em_uma_necessidade_nao_derruba_as_demais(corredor_fake, caplog):
    fonte = PorCliente({CLIENTE_B: (documento("doc-b", "b" * 64),)}, quebra=(CLIENTE_A,))

    with caplog.at_level(logging.WARNING, logger=modulo.__name__):
        _, resultados = modulo.adquirir_por_necessidades(
            contexto(fontes_localizacao=(FonteNomeada("interna", fonte),)),
            (necessidade(CLIENTE_A), necessidade(CLIENTE_B)),
            CICLO,
        )

    assert [r.documento_id for r in resultados] == ["doc-b"]
    assert corredor_fake == ["doc-b"]
    eventos = [r for r in caplog.records if getattr(r, "evento", None) == modulo.EVENTO_LOCALIZACAO_SEM_DOCUMENTO]
    assert len(eventos) == 1
    assert eventos[0].decisao == "INDETERMINADO"
    assert eventos[0].cliente == "cli-a"
    assert eventos[0].consultas[0]["erro_tipo"] == "TimeoutError"
    assert "fora do ar" not in caplog.text


def test_fonte_legada_unica_passa_pela_localizacao_e_falha_nao_derruba_o_ciclo(corredor_fake):
    fonte = PorCliente({CLIENTE_B: (documento("doc-b", "b" * 64),)}, quebra=(CLIENTE_A,))

    _, resultados = modulo.adquirir_por_necessidades(
        contexto(fonte_candidatos_por_necessidade=fonte),
        (necessidade(CLIENTE_A), necessidade(CLIENTE_B)),
        CICLO,
    )

    assert [r.documento_id for r in resultados] == ["doc-b"]


def test_email_com_duas_versoes_so_processa_a_mais_recente(corredor_fake):
    antigo, novo = documento("doc-1o-email", "a" * 64), documento("doc-2o-email", "b" * 64)
    datas = {"doc-1o-email": T0, "doc-2o-email": T0 + timedelta(days=1)}
    fonte = FonteNomeada(
        "email", PorCliente({CLIENTE_A: (antigo, novo)}), data_versao=lambda d: datas.get(d.documento_id)
    )

    _, resultados = modulo.adquirir_por_necessidades(
        contexto(fontes_localizacao=(fonte,)), (necessidade(CLIENTE_A),), CICLO,
    )

    assert [r.documento_id for r in resultados] == ["doc-2o-email"]
    assert corredor_fake == ["doc-2o-email"]


def test_ambiguo_sem_criterio_de_versao_envia_todos_ao_corredor_para_conferencia(corredor_fake):
    fonte = PorCliente({CLIENTE_A: (documento("d1", "a" * 64), documento("d2", "b" * 64))})

    _, resultados = modulo.adquirir_por_necessidades(
        contexto(fontes_localizacao=(FonteNomeada("interna", fonte),)), (necessidade(CLIENTE_A),), CICLO,
    )

    assert sorted(r.documento_id for r in resultados) == ["d1", "d2"]


def test_nao_localizado_registra_evento_e_segue(corredor_fake, caplog):
    with caplog.at_level(logging.WARNING, logger=modulo.__name__):
        _, resultados = modulo.adquirir_por_necessidades(
            contexto(fontes_localizacao=(FonteNomeada("interna", PorCliente({})),)),
            (necessidade(CLIENTE_A),),
            CICLO,
        )

    assert resultados == ()
    decisoes = [r.decisao for r in caplog.records if getattr(r, "evento", None) == modulo.EVENTO_LOCALIZACAO_SEM_DOCUMENTO]
    assert decisoes == ["NAO_LOCALIZADO"]


def test_prioridade_entre_fontes_respeitada_no_ciclo(corredor_fake):
    interna = FonteNomeada("interna", PorCliente({CLIENTE_A: (documento("doc-interno", "a" * 64),)}))
    legado = FonteNomeada("legado", PorCliente({CLIENTE_A: (documento("doc-legado", "b" * 64),)}))

    _, resultados = modulo.adquirir_por_necessidades(
        contexto(fontes_localizacao=(interna, legado)), (necessidade(CLIENTE_A),), CICLO,
    )

    assert [r.documento_id for r in resultados] == ["doc-interno"]


def test_as_duas_formas_de_fonte_juntas_sao_rejeitadas(corredor_fake):
    fonte = PorCliente({})
    with pytest.raises(ValueError):
        modulo.adquirir_por_necessidades(
            contexto(fontes_localizacao=(FonteNomeada("interna", fonte),), fonte_candidatos_por_necessidade=fonte),
            (necessidade(CLIENTE_A),),
            CICLO,
        )
