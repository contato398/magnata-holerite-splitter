import hashlib
from datetime import datetime, timezone

import pytest

from _pdf_sintetico import cpf_sintetico, pdf_com_paginas
from magnata_os.classificacao.roteamento_documental import extrair_paginas_seguro
from magnata_os.classificacao.separacao_documental import (
    estrategia_por_cpf_colaborador,
    indice_cpf_de_candidatos,
    separar_por_carry_forward,
)
from magnata_os.documental.derivacao_documental import (
    ORIGEM_DERIVADO_SEPARACAO,
    GrupoPaginas,
    derivar_documentos,
)
from magnata_os.documental.extracao_texto import extrair_texto_pdf, extrair_texto_pdf_por_pagina
from magnata_os.documental.fatiamento_pdf import fatiar_pdf
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.modulo01.adaptador_entrada_duravel import AdaptadorEntradaDuravel
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)


PAGINAS = [f"HOLERITE\nColaborador sintetico {i}\nCPF {cpf_sintetico(90000000000 + i)}" for i in range(1, 13)]


def entrada():
    documentos, historico, armazenamento = (
        RepositorioDocumentosEmMemoria(), RepositorioHistoricoEmMemoria(), ArmazenamentoArquivosEmMemoria(),
    )
    return AdaptadorEntradaDuravel(documentos, historico, armazenamento), documentos, historico, armazenamento


def test_extracao_por_pagina_preserva_fronteiras_e_equivale_a_extracao_inteira():
    conteudo = pdf_com_paginas(PAGINAS[:3])

    paginas = extrair_texto_pdf_por_pagina(conteudo)

    assert len(paginas) == 3
    assert cpf_sintetico(90000000002) in paginas[1]
    assert cpf_sintetico(90000000001) not in paginas[1]
    assert extrair_texto_pdf(conteudo) == "".join(p + "\n" for p in paginas)


def test_extracao_segura_por_pagina_devolve_none_para_pdf_invalido_ou_sem_texto():
    assert extrair_paginas_seguro(b"") is None
    assert extrair_paginas_seguro(b"nao e pdf") is None
    assert extrair_paginas_seguro(pdf_com_paginas(["", ""])) is None


def test_fatiar_pdf_e_deterministico_e_so_contem_as_paginas_pedidas():
    conteudo = pdf_com_paginas(PAGINAS[:4])

    parte_1 = fatiar_pdf(conteudo, [2])
    parte_2 = fatiar_pdf(conteudo, [2])

    assert parte_1 == parte_2
    assert extrair_texto_pdf_por_pagina(parte_1) == (extrair_texto_pdf_por_pagina(conteudo)[2],)
    with pytest.raises(ValueError):
        fatiar_pdf(conteudo, [])
    with pytest.raises(ValueError):
        fatiar_pdf(conteudo, [4])


def test_indice_cpf_descarta_cpf_ambiguo_e_nunca_carrega_nome():
    candidatos = [
        CandidatoFuncionario("colab-1", cpf_sintetico(90000000001), "nome sintetico"),
        CandidatoFuncionario("colab-2", cpf_sintetico(90000000002), "outro"),
        CandidatoFuncionario("colab-3", cpf_sintetico(90000000002), "duplicado"),
        CandidatoFuncionario("colab-4", None, "sem cpf"),
    ]

    indice = indice_cpf_de_candidatos(candidatos)

    assert indice == {"90000000001": ("colab-1", None)}


def pai_registrado(conteudo, entrada_documental):
    return entrada_documental.registrar_entrada(conteudo, "holerites_setembro.pdf", "application/pdf", "email", lote_id="lote-1")


def test_pdf_de_12_paginas_vira_12_documentos_derivados_com_proveniencia():
    conteudo = pdf_com_paginas(PAGINAS)
    entrada_documental, documentos, historico, _ = entrada()
    pai = pai_registrado(conteudo, entrada_documental)
    indice = {cpf_sintetico(90000000000 + i).replace(".", "").replace("-", ""): (f"colab-{i}", None) for i in range(1, 13)}
    separacao = separar_por_carry_forward(extrair_texto_pdf_por_pagina(conteudo), estrategia_por_cpf_colaborador(indice))

    derivados = derivar_documentos(
        pai, conteudo,
        [GrupoPaginas(g.entidade_id, g.indices_paginas) for g in separacao.grupos],
        "cpf_colaborador", entrada_documental,
    )

    assert len(derivados) == 12
    setimo = next(d for d in derivados if d.entidade_id == "colab-7")
    assert setimo.indices_paginas == (6,)
    assert setimo.documento.origem == ORIGEM_DERIVADO_SEPARACAO
    assert setimo.documento.lote_id == "lote-1"
    assert setimo.documento.nome_original == "holerites_setembro_pag7.pdf"
    assert len({d.documento.hash_sha256 for d in derivados}) == 12
    assert setimo.documento.hash_sha256 != pai.hash_sha256

    evento = historico.listar_por_documento(setimo.documento.documento_id)[0]
    assert evento.evento == "DOCUMENTO_RECEBIDO"
    proveniencia = evento.detalhes["metadados"]
    assert proveniencia["documento_pai_id"] == pai.documento_id
    assert proveniencia["hash_pai"] == pai.hash_sha256
    assert proveniencia["paginas"] == [7]
    assert proveniencia["entidade_id"] == "colab-7"
    assert "90000000007" not in repr(evento.detalhes)

    # original intacto
    assert documentos.buscar_por_id(pai.documento_id) == pai


def test_derivar_de_novo_nao_duplica_documentos():
    conteudo = pdf_com_paginas(PAGINAS[:3])
    entrada_documental, documentos, _, _ = entrada()
    pai = pai_registrado(conteudo, entrada_documental)
    grupos = [GrupoPaginas(f"colab-{i}", (i,)) for i in range(3)]

    primeira = derivar_documentos(pai, conteudo, grupos, "cpf_colaborador", entrada_documental)
    segunda = derivar_documentos(pai, conteudo, grupos, "cpf_colaborador", entrada_documental)

    assert [d.documento.documento_id for d in primeira] == [d.documento.documento_id for d in segunda]
    assert len(documentos.listar_todos()) == 1 + 3


def test_grupo_unico_cobrindo_o_documento_inteiro_nao_gera_derivado():
    conteudo = pdf_com_paginas(PAGINAS[:2])
    entrada_documental, documentos, _, _ = entrada()
    pai = pai_registrado(conteudo, entrada_documental)

    derivados = derivar_documentos(pai, conteudo, [GrupoPaginas("colab-1", (0, 1))], "cpf_colaborador", entrada_documental)

    assert derivados == ()
    assert len(documentos.listar_todos()) == 1


def test_bytes_do_derivado_batem_com_o_hash_registrado():
    conteudo = pdf_com_paginas(PAGINAS[:2])
    entrada_documental, _, _, armazenamento = entrada()
    pai = pai_registrado(conteudo, entrada_documental)

    derivado = derivar_documentos(pai, conteudo, [GrupoPaginas("colab-2", (1,))], "cpf_colaborador", entrada_documental)[0]

    with armazenamento.abrir_leitura(derivado.documento.hash_sha256) as arquivo:
        assert hashlib.sha256(arquivo.read()).hexdigest() == derivado.documento.hash_sha256
