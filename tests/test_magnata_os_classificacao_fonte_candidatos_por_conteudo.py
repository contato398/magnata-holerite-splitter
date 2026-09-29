import hashlib
from datetime import datetime, timezone

import pytest

from _pdf_sintetico import cpf_sintetico, pdf_com_paginas
from magnata_os.central.localizacao import DecisaoLocalizacao, FonteNomeada, localizar_documento
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_por_conteudo import (
    BuscaPorConteudoIncompleta,
    FonteCandidatosPorConteudo,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.modulo01.adaptador_entrada_duravel import AdaptadorEntradaDuravel
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria


T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
CANDIDATOS = (
    CandidatoFuncionario("colab-a", cpf_sintetico(90000000001), "a"),
    CandidatoFuncionario("colab-b", cpf_sintetico(90000000002), "b"),
)


def necessidade(colaborador="colab-a"):
    return NecessidadeDocumentoPrestacao(
        cliente=ReferenciaCanonica("CLIENTE", "cli"), competencia=ReferenciaCanonica("COMPETENCIA", "2026-09"),
        tipo_documental="Holerite", motivo_exigencia="teste",
        colaborador=ReferenciaCanonica("COLABORADOR", colaborador) if colaborador else None,
    )


def ambiente():
    documentos, armazenamento = RepositorioDocumentosEmMemoria(), ArmazenamentoArquivosEmMemoria()
    entrada = AdaptadorEntradaDuravel(documentos, RepositorioHistoricoEmMemoria(), armazenamento)
    return documentos, armazenamento, entrada


def registrar(entrada, paginas, nome="arquivo.pdf"):
    return entrada.registrar_entrada(pdf_com_paginas(paginas), nome, "application/pdf", "email")


def test_encontra_pelo_conteudo_mesmo_com_nome_de_arquivo_inutil():
    documentos, armazenamento, entrada = ambiente()
    alvo = registrar(entrada, ["relatorio", f"CPF {cpf_sintetico(90000000001)}"], "scan_000123.pdf")
    registrar(entrada, [f"CPF {cpf_sintetico(90000000002)}"], "holerite_colab_a.pdf")  # nome enganoso

    fonte = FonteCandidatosPorConteudo(documentos, armazenamento, CANDIDATOS)

    assert fonte.candidatos_para(necessidade()) == (alvo,)
    assert fonte.resumo_ultima_consulta() == {
        "documentos_analisados": 2, "documentos_sem_texto": 0, "documentos_ilegiveis": 0, "documentos_encontrados": 1,
    }


def test_pdf_sem_texto_conta_como_nao_pesquisavel_e_nao_como_falha():
    documentos, armazenamento, entrada = ambiente()
    registrar(entrada, ["", ""])

    fonte = FonteCandidatosPorConteudo(documentos, armazenamento, CANDIDATOS)

    assert fonte.candidatos_para(necessidade()) == ()
    assert fonte.resumo_ultima_consulta()["documentos_sem_texto"] == 1


def test_arquivo_ilegivel_sem_nenhum_achado_impede_afirmar_ausencia():
    documentos, armazenamento, _ = ambiente()
    documentos.salvar(Documento(
        documento_id="d-sem-blob", arquivo_original="x", nome_original="x.pdf", mime_type="application/pdf",
        tamanho=1, hash_sha256=hashlib.sha256(b"x").hexdigest(), origem="email", recebido_em=T0, lote_id=None,
        status="REGISTRADO", correlation_id="c", criado_em=T0, atualizado_em=T0,
    ))
    fonte = FonteCandidatosPorConteudo(documentos, armazenamento, CANDIDATOS)

    with pytest.raises(BuscaPorConteudoIncompleta):
        fonte.candidatos_para(necessidade())

    resultado = localizar_documento(necessidade(), [FonteNomeada("conteudo", fonte)])
    assert resultado.decisao is DecisaoLocalizacao.INDETERMINADO
    assert resultado.consultas[0].detalhes["documentos_ilegiveis"] == 1


def test_necessidade_sem_colaborador_ou_colaborador_sem_cpf_conhecido_nao_e_atendida():
    documentos, armazenamento, entrada = ambiente()
    registrar(entrada, [f"CPF {cpf_sintetico(90000000001)}"])
    fonte = FonteCandidatosPorConteudo(documentos, armazenamento, CANDIDATOS)

    assert fonte.candidatos_para(necessidade(None)) == ()
    assert fonte.candidatos_para(necessidade("colab-desconhecido")) == ()


def test_isolamento_entre_colaboradores():
    documentos, armazenamento, entrada = ambiente()
    doc_a = registrar(entrada, [f"CPF {cpf_sintetico(90000000001)}"])
    doc_b = registrar(entrada, [f"CPF {cpf_sintetico(90000000002)}"])
    fonte = FonteCandidatosPorConteudo(documentos, armazenamento, CANDIDATOS)

    assert fonte.candidatos_para(necessidade("colab-a")) == (doc_a,)
    assert fonte.candidatos_para(necessidade("colab-b")) == (doc_b,)


def test_evidencia_da_localizacao_nao_carrega_cpf():
    documentos, armazenamento, entrada = ambiente()
    registrar(entrada, [f"CPF {cpf_sintetico(90000000001)}"])
    fonte = FonteCandidatosPorConteudo(documentos, armazenamento, CANDIDATOS)

    evidencia = localizar_documento(necessidade(), [FonteNomeada("conteudo", fonte)]).como_evidencia()

    assert "90000000001" not in repr(evidencia)
    assert cpf_sintetico(90000000001) not in repr(evidencia)
