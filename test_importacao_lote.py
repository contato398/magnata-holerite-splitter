"""Testes do núcleo de importação em lote (magnata_os/documental/importacao_lote).

Todos os dados são SINTÉTICOS — nenhum CPF, nome ou CNPJ real. Cobre o
vocabulário de classificação pedido (exact/duplicate/ambiguous/
not_found/conflict/invalid), as duas identidades, correspondência
determinística e ausência de PII no resultado.

Rodar: pytest test_importacao_lote.py -v  (ou python -m pytest ...)
"""

import hashlib
import io
import zipfile

import pytest

from magnata_os.documental.importacao_lote import dominio
from magnata_os.documental.importacao_lote.contratos import (
    CandidatoCliente,
    CandidatoFuncionario,
    ClassificacaoCorrespondencia,
    ConfiguracaoExecucao,
    ItemManifestoExtrato,
    ItemManifestoHolerite,
    MotivoSanitizado,
    TipoDocumental,
)
from magnata_os.documental.importacao_lote.adapters import pacote
from magnata_os.documental.importacao_lote.orquestrador import (
    processar_extrato,
    processar_holerite,
)

PDF_SINTETICO_VALIDO = b'%PDF-1.4\n' + b'x' * 200


def _gerar_pdf_real_sintetico(texto: str = 'documento sintetico de teste') -> bytes:
    """PDF de verdade (estrutura válida, parseável por pdfplumber), com
    texto sintético embutido — usado nos testes que passam pela
    orquestração (que extrai texto do PDF). Nunca contém dado real."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.cell(0, 10, text=texto)
    return bytes(pdf.output())


CONFIG = ConfiguracaoExecucao(
    mes_cont_id='recCANONICOFAKE01',
    ano=2026, mes=7,
    message_id_estavel='msgFakeTeste0001',
    package_sha256='0' * 64,
    mes_cont_id_duplicado_bloqueado=('recDUPLICADOFAKE1',),
)


# ── Validação de PDF ──────────────────────────────────────────────────────

def test_pdf_valido():
    r = dominio.validar_pdf_bytes(PDF_SINTETICO_VALIDO)
    assert r.valido is True
    assert r.motivo == MotivoSanitizado.OK
    assert r.hash_sha256 == hashlib.sha256(PDF_SINTETICO_VALIDO).hexdigest()


def test_pdf_vazio():
    r = dominio.validar_pdf_bytes(b'')
    assert r.valido is False
    assert r.motivo == MotivoSanitizado.PDF_VAZIO


def test_pdf_assinatura_invalida():
    r = dominio.validar_pdf_bytes(b'nao sou um pdf' + b'x' * 100)
    assert r.valido is False
    assert r.motivo == MotivoSanitizado.PDF_SEM_ASSINATURA


def test_pdf_corrompido_curto_demais():
    r = dominio.validar_pdf_bytes(b'%PDF')
    assert r.valido is False
    assert r.motivo == MotivoSanitizado.PDF_VAZIO


# ── Correspondência de colaborador ───────────────────────────────────────

def test_colaborador_exato_por_cpf():
    candidatos = [
        CandidatoFuncionario('recFUNC001', '111.111.111-11', 'FULANO DE TAL SINTETICO'),
        CandidatoFuncionario('recFUNC002', '222.222.222-22', 'OUTRO SINTETICO'),
    ]
    r = dominio.resolver_funcionario('11111111111', 'nome que nao importa', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.entidade_id == 'recFUNC001'
    assert r.criterio_usado == 'cpf_exato'


def test_colaborador_exato_por_nome_quando_sem_cpf():
    candidatos = [CandidatoFuncionario('recFUNC003', None, 'CICLANO SINTETICO DA SILVA')]
    r = dominio.resolver_funcionario(None, 'Ciclano Sintético da Silva', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.criterio_usado == 'nome_normalizado_exato'


def test_colaborador_ambiguo_mesmo_cpf_em_dois_candidatos():
    candidatos = [
        CandidatoFuncionario('recFUNC004', '333.333.333-33', 'A'),
        CandidatoFuncionario('recFUNC005', '333.333.333-33', 'B'),
    ]
    r = dominio.resolver_funcionario('33333333333', 'nome irrelevante aqui', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.AMBIGUOUS
    assert r.entidade_id is None


def test_colaborador_inexistente():
    r = dominio.resolver_funcionario('99999999999', 'NINGUEM SINTETICO', [])
    assert r.classificacao == ClassificacaoCorrespondencia.NOT_FOUND
    assert r.motivo == MotivoSanitizado.COLABORADOR_NAO_ENCONTRADO


# ── Correspondência de cliente (estrita, CNPJ antes de nome) ────────────

def test_cliente_exato_por_cnpj():
    candidatos = [CandidatoCliente('recCLI001', '11.222.333/0001-44', 'CLIENTE SINTETICO UM')]
    linha = 'Serviço: 1 - CLIENTE SINTETICO UM - CNPJ: 11.222.333/0001-44 - Rua Fake, 1'
    r = dominio.resolver_cliente(linha, 'CLIENTE SINTETICO UM', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.entidade_id == 'recCLI001'
    assert r.criterio_usado == 'cnpj_exato'


def test_cliente_nomes_truncados_identicos_resolvidos_por_cnpj_distinto():
    """Caso real desta rodada (num=20/21): nome truncado idêntico, CNPJ
    distinto — a correspondência NUNCA decide pelo nome truncado."""
    candidatos = [
        CandidatoCliente('recCLI020', '10.000.000/0001-01', 'CDTR - CENTRO DE DIALISE E TRANSPLANTE RENAL A'),
        CandidatoCliente('recCLI021', '20.000.000/0001-02', 'CDTR - CENTRO DE DIALISE E TRANSPLANTE RENAL B'),
    ]
    linha_20 = 'Serviço: 20 - CDTR - CENTRO DE DIALISE E TRAN - CNPJ: 10.000.000/0001-01 - Rua X'
    linha_21 = 'Serviço: 21 - CDTR - CENTRO DE DIALISE E TRAN - CNPJ: 20.000.000/0001-02 - Rua Y'
    r20 = dominio.resolver_cliente(linha_20, 'CDTR - CENTRO DE DIALISE E TRAN', candidatos)
    r21 = dominio.resolver_cliente(linha_21, 'CDTR - CENTRO DE DIALISE E TRAN', candidatos)
    assert r20.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r21.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r20.entidade_id != r21.entidade_id
    assert r20.criterio_usado == 'cnpj_exato'
    assert r21.criterio_usado == 'cnpj_exato'


def test_cliente_conflito_dois_cnpjs_batendo():
    candidatos = [
        CandidatoCliente('recCLI030', '30.000.000/0001-03', 'X'),
        CandidatoCliente('recCLI031', '31.000.000/0001-04', 'Y'),
    ]
    linha = 'CNPJ: 30.000.000/0001-03 também CNPJ: 31.000.000/0001-04 na mesma linha'
    r = dominio.resolver_cliente(linha, 'nome nao usado', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.CONFLICT
    assert r.motivo == MotivoSanitizado.CLIENTE_CONFLITO_CNPJ


def test_cliente_cnpj_extraido_mas_nao_cadastrado_nao_cai_para_nome():
    """Se a linha tem CNPJ mas ele não bate em nenhum candidato, o
    resultado é not_found — nunca tenta salvar por nome depois."""
    candidatos = [CandidatoCliente('recCLI040', '40.000.000/0001-05', 'NOME QUE BATERIA SE FOSSE POR NOME')]
    linha = 'CNPJ: 99.999.999/0001-99 - NOME QUE BATERIA SE FOSSE POR NOME'
    r = dominio.resolver_cliente(linha, 'NOME QUE BATERIA SE FOSSE POR NOME', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.NOT_FOUND
    assert r.criterio_usado == 'cnpj_exato'


def test_cliente_ambiguo_por_nome_sem_cnpj_na_linha():
    candidatos = [
        CandidatoCliente('recCLI050', None, 'CLIENTE SEM CNPJ NA LINHA'),
        CandidatoCliente('recCLI051', None, 'CLIENTE SEM CNPJ NA LINHA'),
    ]
    r = dominio.resolver_cliente('linha sem nenhum cnpj', 'Cliente sem CNPJ na linha', candidatos)
    assert r.classificacao == ClassificacaoCorrespondencia.AMBIGUOUS


def test_cliente_inexistente():
    r = dominio.resolver_cliente('linha qualquer sem cnpj', 'NINGUEM CADASTRADO', [])
    assert r.classificacao == ClassificacaoCorrespondencia.NOT_FOUND


# ── Identidades ───────────────────────────────────────────────────────────

def test_identidade_documental_nao_usa_cpf_nem_nome():
    id1 = dominio.calcular_identidade_documental(
        TipoDocumental.HOLERITE, 'recCOMP', 'recFUNC999', 'a' * 64)
    # mesma chamada, mesmos IDs -> mesmo hash (determinístico)
    id2 = dominio.calcular_identidade_documental(
        TipoDocumental.HOLERITE, 'recCOMP', 'recFUNC999', 'a' * 64)
    assert id1 == id2
    assert len(id1) == 64  # sha256 hex


def test_identidade_ingestao_usa_message_id_nao_data_texto():
    id_a = dominio.calcular_identidade_ingestao('msgEstavel1', 'pkgsha256fake', 'holerite:001')
    id_b = dominio.calcular_identidade_ingestao('msgEstavel2', 'pkgsha256fake', 'holerite:001')
    assert id_a != id_b  # origem diferente => ingestão diferente, mesmo item


def test_repeticao_do_dry_run_produz_mesmo_resultado():
    """Rodar duas vezes com os mesmos dados sintéticos produz exatamente
    a mesma classificação e as mesmas identidades — sem duplicar."""
    candidatos = [CandidatoFuncionario('recFUNC100', '444.444.444-44', 'REPETICAO SINTETICA')]
    item = ItemManifestoHolerite('holerite:100', '1', 'Repetição Sintética', '***.***.444-44', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico('CPF 444.444.444-44 dado sintetico de teste')

    r1 = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    r2 = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    assert r1.classificacao == r2.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r1.identidade_documental == r2.identidade_documental
    assert r1.pronto_para_gravacao == r2.pronto_para_gravacao is True


# ── Orquestração ponta a ponta (dados sintéticos) ────────────────────────

def test_item_sem_pdf_no_pacote():
    item = ItemManifestoHolerite('holerite:200', '1', 'X', '***.***.000-00', 'ausente.pdf', 1)
    r = processar_holerite(item, None, CONFIG, [], set())
    assert r.classificacao == ClassificacaoCorrespondencia.INVALID
    assert r.motivo == MotivoSanitizado.ARQUIVO_AUSENTE_NO_PACOTE


def test_holerite_duplicado_quando_ja_existe_na_folha():
    candidatos = [CandidatoFuncionario('recFUNC300', '555.555.555-55', 'JA EXISTENTE SINTETICO')]
    item = ItemManifestoHolerite('holerite:300', '1', 'Ja Existente Sintetico', '***.***.555-55', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico('CPF 555.555.555-55 dado sintetico')
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, {'recFUNC300'})
    assert r.classificacao == ClassificacaoCorrespondencia.DUPLICATE
    assert r.pronto_para_gravacao is False


def test_holerite_exact_sem_leitura_airtable_nunca_fica_pronto_para_gravacao():
    """Leitura indisponível (func_ids_ja_com_holerite=None) nunca é
    tratada como 'sem duplicidade' por omissão."""
    candidatos = [CandidatoFuncionario('recFUNC400', '666.666.666-66', 'SEM LEITURA SINTETICO')]
    item = ItemManifestoHolerite('holerite:400', '1', 'Sem Leitura Sintetico', '***.***.666-66', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico('CPF 666.666.666-66 dado sintetico')
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, None)
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is False
    assert r.motivo == MotivoSanitizado.LEITURA_AIRTABLE_INDISPONIVEL


def test_extrato_exact_e_pronto_quando_sem_duplicidade():
    candidatos = [CandidatoCliente('recCLI500', '50.000.000/0001-06', 'CLIENTE EXTRATO SINTETICO')]
    item = ItemManifestoExtrato(
        'extrato:500', '500', 'CLIENTE EXTRATO SINTETICO',
        'Serviço: 500 - CLIENTE EXTRATO SINTETICO - CNPJ: 50.000.000/0001-06', 'x.pdf', (1, 2))
    r = processar_extrato(item, PDF_SINTETICO_VALIDO, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is True


# ── Ausência de PII no resultado ─────────────────────────────────────────

def test_resultado_item_nunca_carrega_cpf_ou_nome():
    candidatos = [CandidatoFuncionario('recFUNCPII', '777.777.777-77', 'PESSOA SINTETICA PII')]
    item = ItemManifestoHolerite('holerite:600', '1', 'Pessoa Sintetica PII', '***.***.777-77', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico('CPF 777.777.777-77 dado sintetico')
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    campos = {f: getattr(r, f) for f in r.__dataclass_fields__}
    for valor in campos.values():
        texto = str(valor)
        assert 'PESSOA SINTETICA PII' not in texto
        assert '777.777.777-77' not in texto
        assert '77777777777' not in texto


# ── Leitor de manifesto real (estrutura, não conteúdo) ───────────────────

def _zip_sintetico_com_manifesto(holerites: list[dict], extratos: list[dict]) -> bytes:
    import json
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('documentos_julho_2026_organizados/indice_holerites_julho_2026.json',
                    json.dumps(holerites))
        z.writestr('documentos_julho_2026_organizados/indice_extratos_por_cliente.json',
                    json.dumps(extratos))
        for h in holerites:
            z.writestr(f'documentos_julho_2026_organizados/holerites_por_cliente/1_CLIENTE_FAKE/{h["filename"]}',
                       PDF_SINTETICO_VALIDO)
        for e in extratos:
            z.writestr(f'documentos_julho_2026_organizados/extratos_por_cliente/{e["filename"]}',
                       PDF_SINTETICO_VALIDO)
        z.writestr('documentos_julho_2026_organizados/relatorios_gerais/RelatoriodeLiquidos_Fake.pdf',
                   PDF_SINTETICO_VALIDO)
    return buf.getvalue()


def test_manifesto_valido_quantidade_variavel(tmp_path):
    """Quantidade não é fixa em 135 — o leitor aceita qualquer tamanho."""
    holerites = [
        {'page': 1, 'code': '1', 'name': 'FAKE UM', 'client': '1 - CLIENTE FAKE',
         'filename': 'h1.pdf', 'cpf_mascarado': '***.***.001-00'},
        {'page': 1, 'code': '2', 'name': 'FAKE DOIS', 'client': '1 - CLIENTE FAKE',
         'filename': 'h2.pdf', 'cpf_mascarado': '***.***.002-00'},
        {'page': 1, 'code': '3', 'name': 'FAKE TRES', 'client': '1 - CLIENTE FAKE',
         'filename': 'h3.pdf', 'cpf_mascarado': '***.***.003-00'},
    ]
    extratos = [
        {'num': 1, 'name': 'CLIENTE FAKE', 'line': 'CNPJ: 00.000.000/0001-00',
         'filename': 'e1.pdf', 'source_pages': [1]},
    ]
    zip_bytes = _zip_sintetico_com_manifesto(holerites, extratos)
    caminho = tmp_path / 'pacote_fake.zip'
    caminho.write_bytes(zip_bytes)

    itens_h = pacote.ler_manifesto_holerites(str(caminho))
    itens_e = pacote.ler_manifesto_extratos(str(caminho))
    assert len(itens_h) == 3
    assert len(itens_e) == 1
    assert itens_h[0].source_service_number == '1'
    relatorios = pacote.listar_relatorios_gerais(str(caminho))
    assert 'RelatoriodeLiquidos_Fake.pdf' in relatorios


def test_manifesto_invalido_json_malformado(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('documentos_julho_2026_organizados/indice_holerites_julho_2026.json', '{nao e json valido')
    caminho = tmp_path / 'pacote_invalido.zip'
    caminho.write_bytes(buf.getvalue())
    with pytest.raises(Exception):
        pacote.ler_manifesto_holerites(str(caminho))


def test_relatorios_gerais_corrige_mojibake_cp437(tmp_path):
    """Achado real do dry-run (Gate 1): 1 entrada do pacote real vem sem a
    flag UTF-8 do ZIP setada, produzindo mojibake ('ExtratoServiço' vira
    'ExtratoServi├ºo'). O nome correto precisa ser recuperado."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        # zipfile grava com flag UTF-8 automaticamente se detectar não-ASCII
        # no nome -- para reproduzir o caso real (flag_bits sem 0x800),
        # gravamos os bytes UTF-8 manualmente via ZipInfo sem a flag.
        info = zipfile.ZipInfo('documentos_julho_2026_organizados/relatorios_gerais/ExtratoServiço_Fake.pdf')
        info.flag_bits &= ~0x800  # garante que a flag UTF-8 NÃO está setada
        z.writestr(info, PDF_SINTETICO_VALIDO)
    caminho = tmp_path / 'pacote_mojibake.zip'
    caminho.write_bytes(buf.getvalue())

    nomes = pacote.listar_relatorios_gerais(str(caminho))
    assert any('ExtratoServiço' in n for n in nomes), f'nome não corrigido: {nomes}'


def test_hash_do_pacote_e_determinístico(tmp_path):
    caminho = tmp_path / 'x.zip'
    caminho.write_bytes(b'conteudo fake de teste')
    h1 = pacote.calcular_sha256_arquivo(str(caminho))
    h2 = pacote.calcular_sha256_arquivo(str(caminho))
    assert h1 == h2
    assert len(h1) == 64


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
