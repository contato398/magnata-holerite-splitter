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
from unittest.mock import Mock, patch

from magnata_os.documental.importacao_lote import dominio
from magnata_os.documental.importacao_lote.contratos import (
    CandidatoCliente,
    CandidatoFuncionario,
    ClassificacaoCorrespondencia,
    CompetenciaExtraida,
    ConfiguracaoExecucao,
    ItemManifestoExtrato,
    ItemManifestoHolerite,
    MotivoSanitizado,
    ResultadoCompetencia,
    StatusExtracaoCompetencia,
    TipoDocumental,
)
from magnata_os.documental.importacao_lote.adapters import pacote
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import LeitorAirtableSomenteLeitura
from magnata_os.documental.importacao_lote.orquestrador import (
    processar_extrato,
    processar_holerite,
)

PDF_SINTETICO_VALIDO = b'%PDF-1.4\n' + b'x' * 200


def test_leitura_existentes_percorre_paginacao_airtable():
    primeira = Mock()
    primeira.raise_for_status.return_value = None
    primeira.json.return_value = {
        'records': [{'fields': {'fldTXMjeHfgyDas9f': [{'id': 'recFUNC1'}]}}],
        'offset': 'pagina-2',
    }
    segunda = Mock()
    segunda.raise_for_status.return_value = None
    segunda.json.return_value = {
        'records': [{'fields': {'fldTXMjeHfgyDas9f': [{'id': 'recFUNC2'}]}}],
    }
    with patch('magnata_os.documental.importacao_lote.adapters.airtable_leitura.requests.get',
               side_effect=[primeira, segunda]) as get:
        ids = LeitorAirtableSomenteLeitura('token-sintetico').holerites_existentes_na_folha('Julho 2026')
    assert ids == {'recFUNC1', 'recFUNC2'}
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs['params']['offset'] == 'pagina-2'


def test_listar_registros_publico_preserva_get_paginacao_campos_e_filtro():
    primeira = Mock()
    primeira.raise_for_status.return_value = None
    primeira.json.return_value = {
        'records': [{'id': 'recDOC1'}],
        'offset': 'pagina-2',
    }
    segunda = Mock()
    segunda.raise_for_status.return_value = None
    segunda.json.return_value = {'records': [{'id': 'recDOC2'}]}
    modulo = 'magnata_os.documental.importacao_lote.adapters.airtable_leitura.requests'

    with (
        patch(f'{modulo}.get', side_effect=[primeira, segunda]) as get,
        patch(f'{modulo}.post') as post,
        patch(f'{modulo}.patch') as patch_request,
        patch(f'{modulo}.put') as put,
        patch(f'{modulo}.delete') as delete,
    ):
        registros = LeitorAirtableSomenteLeitura(
            'token-sintetico'
        ).listar_registros(
            table_id='tblDOCUMENTOS',
            fields=['Tipo', 'Cliente'],
            filter_by_formula='{Folha Mensal}="Julho 2026"',
        )

    assert registros == [{'id': 'recDOC1'}, {'id': 'recDOC2'}]
    assert get.call_count == 2
    for chamada in get.call_args_list:
        assert chamada.args[0].endswith('/tblDOCUMENTOS')
        assert chamada.kwargs['params']['fields[]'] == ['Tipo', 'Cliente']
        assert chamada.kwargs['params']['filterByFormula'] == (
            '{Folha Mensal}="Julho 2026"'
        )
        assert chamada.kwargs['params']['returnFieldsByFieldId'] == 'true'
    assert get.call_args_list[1].kwargs['params']['offset'] == 'pagina-2'
    post.assert_not_called()
    patch_request.assert_not_called()
    put.assert_not_called()
    delete.assert_not_called()


def _gerar_pdf_real_sintetico(texto: str = 'documento sintetico de teste') -> bytes:
    """PDF de verdade (estrutura válida, parseável por pdfplumber), com
    texto sintético embutido — usado nos testes que passam pela
    orquestração (que extrai texto do PDF). Nunca contém dado real.
    `multi_cell` (em vez de `cell`) preserva quebras de linha (`\\n`) no
    texto extraído por pdfplumber -- necessário para os testes de
    competência que dependem de campos em linhas separadas (mesmo padrão
    de layout de um holerite/extrato real)."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.multi_cell(0, 10, text=texto)
    return bytes(pdf.output())


def _gerar_pdf_com_linhas(*linhas: str) -> bytes:
    """Atalho para montar um PDF sintético com um campo por linha —
    mesma granularidade que `pdfplumber` produz de um documento real."""
    return _gerar_pdf_real_sintetico('\n'.join(linhas))


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
    pdf_bytes = _gerar_pdf_real_sintetico(
        'CPF 444.444.444-44 dado sintetico de teste - Competencia: 07/2026')

    r1 = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    r2 = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    assert r1.classificacao == r2.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r1.identidade_documental == r2.identidade_documental
    assert r1.pronto_para_gravacao == r2.pronto_para_gravacao is True
    assert r1.resultado_competencia == r2.resultado_competencia == ResultadoCompetencia.CONFIRMADA


# ── Competência documental (Macro 5) ─────────────────────────────────────
#
# Revisão adversarial: uma data só conta como candidata a competência
# quando aparece na MESMA LINHA de um marcador semântico explícito
# ('competência'/'mês de referência'). Data de pagamento, admissão,
# período de férias, impressão etc. nunca têm essas palavras — ficam de
# fora por construção, mesmo em formato MM/AAAA. Texto extraído de PDF
# já vem quebrado em linhas por `pdfplumber` — mesma granularidade usada
# aqui (`_gerar_pdf_com_linhas`).

def test_competencia_extraida_formato_numerico():
    r = dominio.extrair_competencia_de_texto('Holerite sintetico - Competencia: 07/2026')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)
    assert r.estrategia == 'mm_aaaa_numerico'


def test_competencia_extraida_nome_do_mes_por_extenso():
    r = dominio.extrair_competencia_de_texto('Competencia: Julho/2026 - documento sintetico')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)
    assert r.estrategia == 'nome_mes_pt'


def test_competencia_extraida_do_cabecalho_mensalista_do_holerite():
    r = dominio.extrair_competencia_de_texto(
        'Mensalista Julho de 2026\nData de pagamento: 05/08/2026')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)
    assert r.estrategia == 'cabecalho_vinculo_mes_pt'


def test_competencia_extraida_do_cabecalho_horista_do_holerite():
    r = dominio.extrair_competencia_de_texto(
        'Horista Julho de 2026\nData de pagamento: 05/08/2026')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)
    assert r.estrategia == 'cabecalho_vinculo_mes_pt'


def test_cabecalho_vinculo_nunca_confunde_admissao_com_competencia():
    rejeitados = [
        'Mensalista desde 03/2015',
        'Horista admitido em 07/2026',
        'Mensalista - Admitido em 03/2015 - Julho de 2026',
        'Mensalista 03/2015',
        'Mensalista desde Julho de 2026',
    ]
    for texto in rejeitados:
        r = dominio.extrair_competencia_de_texto(texto)
        assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA, texto


def test_cabecalho_vinculo_aceita_apenas_mes_por_extenso_adjacente():
    aceitos = [
        'Mensalista Julho de 2026',
        'Mensalista: Julho/2026',
        'Horista - Julho de 2026',
    ]
    for texto in aceitos:
        r = dominio.extrair_competencia_de_texto(texto)
        assert r.status == StatusExtracaoCompetencia.ENCONTRADA, texto
        assert r.ano_mes == (2026, 7)
        assert r.estrategia == 'cabecalho_vinculo_mes_pt'


def test_competencia_extraida_nome_do_mes_com_acento_e_separador_de():
    r = dominio.extrair_competencia_de_texto('Competencia de Março de 2026')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 3)


def test_competencia_nao_encontrada_quando_texto_nao_tem_padrao():
    r = dominio.extrair_competencia_de_texto('documento sintetico sem nenhuma data reconhecivel')
    assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA
    assert r.ano_mes is None


def test_competencia_texto_vazio_e_nao_encontrada():
    r = dominio.extrair_competencia_de_texto('')
    assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA


def test_competencia_ambigua_quando_duas_linhas_marcadas_divergem():
    texto = 'Competencia: 07/2026\nCompetencia: 08/2026'
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.AMBIGUA
    assert r.ano_mes is None


def test_competencia_mesmo_valor_repetido_na_mesma_linha_nao_e_ambigua():
    r = dominio.extrair_competencia_de_texto('Competencia 07/2026, Julho/2026 conforme contrato')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)


def test_competencia_data_de_pagamento_dd_mm_aaaa_nunca_conta_sozinha():
    """Data de pagamento não tem marcador — nunca é tratada como
    competência por coincidência de formato, mesmo sendo a única data do
    texto."""
    r = dominio.extrair_competencia_de_texto('Data de pagamento: 05/07/2026, sem outra referencia')
    assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA


def test_competencia_e_data_de_pagamento_diferentes_extrai_so_a_marcada():
    texto = 'Competencia: 07/2026\nData de pagamento: 05/08/2026'
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)


def test_competencia_e_data_de_admissao_extrai_so_a_marcada():
    texto = 'Competencia: 07/2026\nData de admissao: 15/03/2019'
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)


def test_competencia_e_periodo_de_ferias_extrai_so_a_marcada():
    texto = 'Periodo de ferias: 01/2026 a 02/2026\nCompetencia: 07/2026'
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)


def test_competencia_varios_mm_aaaa_alheios_mas_somente_uma_marcada():
    texto = (
        'Periodo de ferias: 01/2026 a 02/2026\n'
        'Data de pagamento: 05/08/2026\n'
        'Data de admissao: 03/2015\n'
        'Competencia: 07/2026'
    )
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)
    assert r.estrategia == 'mm_aaaa_numerico'


def test_competencia_mes_por_extenso_em_texto_que_nao_indica_competencia():
    """'Julho de 2026' aparece no texto, mas sem nenhum marcador
    semântico na mesma linha (é uma data de impressão, não competência)
    — nunca vira uma confirmação por coincidência."""
    texto = 'Este contracheque foi impresso em Julho de 2026 apenas para conferencia interna.'
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA


def test_competencia_duas_competencias_explicitamente_marcadas_e_divergentes():
    texto = 'Competencia: Julho/2026\nCompetencia: Agosto/2026'
    r = dominio.extrair_competencia_de_texto(texto)
    assert r.status == StatusExtracaoCompetencia.AMBIGUA


def test_competencia_ano_fora_do_intervalo_valido_nunca_e_aceito():
    r = dominio.extrair_competencia_de_texto('Competencia: 07/1899')
    assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA


def test_competencia_mes_invalido_nunca_e_aceito():
    r = dominio.extrair_competencia_de_texto('Competencia: 13/2026')
    assert r.status == StatusExtracaoCompetencia.NAO_ENCONTRADA


def test_competencia_variacoes_de_caixa_acento_e_espacos():
    variantes = [
        'COMPETÊNCIA: 07/2026',
        'competência:07/2026',
        'CoMpEtEnCiA :  07 / 2026',
        '  competencia   07/2026  ',
    ]
    for texto in variantes:
        r = dominio.extrair_competencia_de_texto(texto)
        assert r.status == StatusExtracaoCompetencia.ENCONTRADA, f'falhou para: {texto!r}'
        assert r.ano_mes == (2026, 7), f'falhou para: {texto!r}'


def test_competencia_marcador_mes_de_referencia_tambem_e_reconhecido():
    r = dominio.extrair_competencia_de_texto('Mes de referencia: Julho/2026')
    assert r.status == StatusExtracaoCompetencia.ENCONTRADA
    assert r.ano_mes == (2026, 7)


def test_validar_competencia_confirmada():
    extraida = CompetenciaExtraida(StatusExtracaoCompetencia.ENCONTRADA, (2026, 7), 'mm_aaaa_numerico')
    assert dominio.validar_competencia(extraida, 2026, 7) == ResultadoCompetencia.CONFIRMADA


def test_validar_competencia_divergente():
    extraida = CompetenciaExtraida(StatusExtracaoCompetencia.ENCONTRADA, (2026, 6), 'mm_aaaa_numerico')
    assert dominio.validar_competencia(extraida, 2026, 7) == ResultadoCompetencia.DIVERGENTE


def test_validar_competencia_ambigua_repassada():
    extraida = CompetenciaExtraida(StatusExtracaoCompetencia.AMBIGUA, None, None)
    assert dominio.validar_competencia(extraida, 2026, 7) == ResultadoCompetencia.AMBIGUA


def test_validar_competencia_nao_extraivel_repassada():
    extraida = CompetenciaExtraida(StatusExtracaoCompetencia.NAO_ENCONTRADA, None, None)
    assert dominio.validar_competencia(extraida, 2026, 7) == ResultadoCompetencia.NAO_EXTRAIVEL


# ── competencia_apta_para_gravacao (defesa em profundidade, revisão
# adversarial) — nunca confia só no enum, reconfirma por valor ─────────

def test_apta_quando_tudo_consistente_e_confirmado():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 7), 'mm_aaaa_numerico', 2026, 7) is True


def test_nao_apta_quando_resultado_competencia_ausente():
    assert dominio.competencia_apta_para_gravacao(
        None, (2026, 7), 'mm_aaaa_numerico', 2026, 7) is False


def test_nao_apta_quando_resultado_competencia_divergente():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.DIVERGENTE, (2026, 6), 'mm_aaaa_numerico', 2026, 7) is False


def test_nao_apta_quando_ano_mes_extraido_ausente_mesmo_com_confirmada():
    """Defesa em profundidade: mesmo que um chamador tenha (incorretamente)
    marcado CONFIRMADA sem preencher o valor extraído, a função nunca
    confia só no enum."""
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, None, 'mm_aaaa_numerico', 2026, 7) is False


def test_nao_apta_quando_estrategia_ausente_mesmo_com_confirmada():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 7), None, 2026, 7) is False


def test_nao_apta_quando_estrategia_invalida_mesmo_com_confirmada():
    """Código de estratégia arbitrário (fora da lista branca do que este
    módulo sabe produzir) nunca é aceito, mesmo com todo o resto
    consistente."""
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 7), 'estrategia_inventada', 2026, 7) is False


def test_nao_apta_quando_confirmada_mas_valor_extraido_diverge_do_esperado():
    """O caso mais adversarial: status CONFIRMADA, mas o valor extraído
    de fato não bate com o esperado (ex.: enum calculado com dados
    trocados por outro caminho) — a reconfirmação direta por valor pega
    essa inconsistência mesmo com o enum dizendo o contrário."""
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 8), 'mm_aaaa_numerico', 2026, 7) is False


def test_nao_apta_quando_mes_esperado_fora_de_faixa():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 7), 'mm_aaaa_numerico', 2026, 13) is False


def test_nao_apta_quando_mes_esperado_zero():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 7), 'mm_aaaa_numerico', 2026, 0) is False


def test_nao_apta_quando_ano_esperado_implausivel():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (1899, 7), 'mm_aaaa_numerico', 1899, 7) is False


def test_nao_apta_quando_mes_extraido_fora_de_faixa():
    assert dominio.competencia_apta_para_gravacao(
        ResultadoCompetencia.CONFIRMADA, (2026, 0), 'mm_aaaa_numerico', 2026, 0) is False


def test_holerite_bloqueado_por_competencia_divergente_mas_entidade_continua_exact():
    """Requisito obrigatório: identificação da entidade e validação da
    competência são dimensões independentes — a entidade foi resolvida
    corretamente (classificacao continua EXACT), só pronto_para_gravacao
    cai por causa da competência divergente."""
    candidatos = [CandidatoFuncionario('recFUNC900', '900.900.900-90', 'COMPETENCIA DIVERGENTE SINTETICO')]
    item = ItemManifestoHolerite('holerite:900', '1', 'Competencia Divergente Sintetico', '***.***.900-90', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico('CPF 900.900.900-90 - Competencia: 06/2026')
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is False
    assert r.resultado_competencia == ResultadoCompetencia.DIVERGENTE
    assert r.motivo == MotivoSanitizado.COMPETENCIA_DIVERGENTE
    assert r.competencia_ano_mes_extraido == (2026, 6)


def test_holerite_bloqueado_por_competencia_nao_extraivel():
    candidatos = [CandidatoFuncionario('recFUNC901', '901.901.901-91', 'SEM COMPETENCIA SINTETICO')]
    item = ItemManifestoHolerite('holerite:901', '1', 'Sem Competencia Sintetico', '***.***.901-91', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico('CPF 901.901.901-91 sem nenhuma data reconhecivel')
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is False
    assert r.resultado_competencia == ResultadoCompetencia.NAO_EXTRAIVEL
    assert r.motivo == MotivoSanitizado.COMPETENCIA_NAO_EXTRAIVEL


def test_holerite_bloqueado_por_competencia_ambigua():
    candidatos = [CandidatoFuncionario('recFUNC902', '902.902.902-92', 'COMPETENCIA AMBIGUA SINTETICO')]
    item = ItemManifestoHolerite('holerite:902', '1', 'Competencia Ambigua Sintetico', '***.***.902-92', 'x.pdf', 1)
    pdf_bytes = _gerar_pdf_real_sintetico(
        'CPF 902.902.902-92 - Competencia 07/2026 ... reimpresso em 08/2026')
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is False
    assert r.resultado_competencia == ResultadoCompetencia.AMBIGUA
    assert r.motivo == MotivoSanitizado.COMPETENCIA_AMBIGUA
    assert r.competencia_ano_mes_extraido is None


def test_extrato_bloqueado_por_competencia_divergente():
    candidatos = [CandidatoCliente('recCLI901', '90.111.000/0001-09', 'CLIENTE COMPETENCIA DIVERGENTE')]
    item = ItemManifestoExtrato(
        'extrato:901', '901', 'CLIENTE COMPETENCIA DIVERGENTE',
        'Serviço: 901 - CLIENTE COMPETENCIA DIVERGENTE - CNPJ: 90.111.000/0001-09', 'x.pdf', (1,))
    pdf_bytes = _gerar_pdf_real_sintetico('Extrato sintetico - Competencia: 12/2025')
    r = processar_extrato(item, pdf_bytes, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is False
    assert r.resultado_competencia == ResultadoCompetencia.DIVERGENTE


def test_competencia_nunca_carrega_texto_bruto_do_pdf():
    """Requisito obrigatório: nunca texto integral nem trecho do PDF —
    só (ano, mes) e um código de estratégia sanitizado."""
    candidatos = [CandidatoFuncionario('recFUNC903', '903.903.903-93', 'PESSOA SINTETICA COMPETENCIA')]
    item = ItemManifestoHolerite('holerite:903', '1', 'Pessoa Sintetica Competencia', '***.***.903-93', 'x.pdf', 1)
    texto_embutido = 'CPF 903.903.903-93 dado sintetico de teste - Competencia: 07/2026'
    pdf_bytes = _gerar_pdf_real_sintetico(texto_embutido)
    r = processar_holerite(item, pdf_bytes, CONFIG, candidatos, set())
    campos = {f: getattr(r, f) for f in r.__dataclass_fields__}
    for valor in campos.values():
        assert texto_embutido not in str(valor)
        assert '903.903.903-93' not in str(valor)


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
    # PDF real (parseável) — necessário desde o Macro 5: processar_extrato
    # agora lê o conteúdo para extrair competência, não só `linha_bruta`.
    pdf_bytes = _gerar_pdf_real_sintetico('Extrato sintetico de teste - Competencia: 07/2026')
    r = processar_extrato(item, pdf_bytes, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.EXACT
    assert r.pronto_para_gravacao is True
    assert r.resultado_competencia == ResultadoCompetencia.CONFIRMADA


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


def test_manifesto_generaliza_para_outra_competencia_sem_hardcode(tmp_path):
    """Achado do Ultrareview, corrigido: a pasta raiz e o nome do
    manifesto de holerites eram hard-coded para 'julho_2026'. Este teste
    usa uma competência DIFERENTE, com pasta e nome de arquivo diferentes,
    para provar que nenhuma alteração de código seria necessária."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('documentos_agosto_2026_organizados/indice_holerites_agosto_2026.json',
                    '[{"page": 1, "code": "1", "name": "FAKE AGOSTO", '
                    '"client": "9 - CLIENTE FAKE AGOSTO", "filename": "h1.pdf", '
                    '"cpf_mascarado": "***.***.001-00"}]')
        z.writestr('documentos_agosto_2026_organizados/indice_extratos_por_cliente.json', '[]')
        z.writestr('documentos_agosto_2026_organizados/holerites_por_cliente/9_FAKE/h1.pdf',
                   PDF_SINTETICO_VALIDO)
    caminho = tmp_path / 'pacote_agosto.zip'
    caminho.write_bytes(buf.getvalue())

    itens = pacote.ler_manifesto_holerites(str(caminho))
    assert len(itens) == 1
    assert itens[0].nome_manifesto == 'FAKE AGOSTO'
    pdf = pacote.ler_pdf_holerite_bytes(str(caminho), 'h1.pdf')
    assert pdf == PDF_SINTETICO_VALIDO


def test_manifesto_ambiguo_dois_candidatos_nunca_escolhe_sozinho(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('pasta_a/indice_holerites_julho_2026.json', '[]')
        z.writestr('pasta_b/indice_holerites_agosto_2026.json', '[]')
    caminho = tmp_path / 'pacote_ambiguo.zip'
    caminho.write_bytes(buf.getvalue())
    with pytest.raises(ValueError):
        pacote.ler_manifesto_holerites(str(caminho))


def test_entrada_zip_acima_do_limite_nao_e_lida(tmp_path):
    """Defesa contra zip bomb: `file_size` declarado acima do teto nunca
    é lido, mesmo que a leitura em si fosse pequena de verdade. Unitário
    direto sobre `_ler_entrada_com_limite`, que é o ponto exato da defesa
    — mutar `ZipInfo.file_size` depois de escrito no zip não persiste no
    arquivo em disco, então testar via reescrita de zip seria enganoso."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('pequeno.pdf', PDF_SINTETICO_VALIDO)
    caminho = tmp_path / 'pacote.zip'
    caminho.write_bytes(buf.getvalue())

    with zipfile.ZipFile(caminho) as z:
        info = z.getinfo('pequeno.pdf')
        info.file_size = 100 * 1024 * 1024  # declarado 100 MB, > teto de 50 MB
        resultado = pacote._ler_entrada_com_limite(z, info)
    assert resultado is None


def test_pdf_corrompido_estrutura_invalida_nao_derruba_lote():
    """Achado do Ultrareview, corrigido: assinatura/tamanho válidos mas
    estrutura interna do PDF corrompida fazia pdfplumber lançar exceção
    sem tratamento, derrubando o lote inteiro. Agora vira `invalid` só
    deste item."""
    pdf_corrompido = b'%PDF-1.4\n' + b'\x00' * 500  # assinatura ok, conteudo lixo
    candidatos = [CandidatoFuncionario('recFUNC700', '888.888.888-88', 'CORROMPIDO SINTETICO')]
    item = ItemManifestoHolerite('holerite:700', '1', 'Corrompido Sintetico', '***.***.888-88', 'x.pdf', 1)
    r = processar_holerite(item, pdf_corrompido, CONFIG, candidatos, set())
    assert r.classificacao == ClassificacaoCorrespondencia.INVALID
    assert r.motivo == MotivoSanitizado.PDF_ILEGIVEL
    assert r.pronto_para_gravacao is False


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
        # raiz do pacote é derivada do manifesto de holerites — precisa
        # existir mesmo neste teste focado só no relatório geral.
        z.writestr('documentos_julho_2026_organizados/indice_holerites_julho_2026.json', '[]')
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
