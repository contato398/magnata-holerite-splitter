"""Testes de `ponte_conteudo_motor_semantico.py` (missão "INTEGRAÇÃO REAL
DO CONTEÚDO DOCUMENTAL AO MOTOR SEMÂNTICO", Fase 2/4 -- prova que a ponte
agrega DE VERDADE os produtores de evidência já existentes para o MESMO
`resolver_tipo_documental`, nunca decide sozinha, nunca cria um segundo
motor).

Ambiente: `extrair_texto_pdf` (pdfplumber/cryptography) não funciona
neste sandbox (`pyo3_runtime.PanicException` na importação nativa, não
capturável nem por `except Exception`) -- por isso nenhum teste aqui
chama de verdade a extração de PDF com bytes não-vazios; o caminho
`resolver_tipo_documental_de_pdf` é provado por (a) bytes vazios, que
`extrair_texto_seguro` já trata sem tocar `extrair_texto_pdf`, e (b) um
monkeypatch do próprio `extrair_texto_seguro` reaproveitado, provando só
a DELEGAÇÃO, nunca uma segunda extração."""
from magnata_os.classificacao import ponte_conteudo_motor_semantico as ponte
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao
from magnata_os.classificacao.finalidade_comprovante_pagamento import FINALIDADE_FGTS
from magnata_os.classificacao.produtores_evidencia_extrato import TIPO_EXTRATO
from magnata_os.classificacao.produtores_evidencia_fiscal import TIPO_GUIA_GENERICA
from magnata_os.classificacao.produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO


def test_texto_none_nunca_gera_hipotese_nem_inventa_tipo():
    assert ponte.hipoteses_multi_evidencia_de_texto(None) == ()
    resolucao = ponte.resolver_tipo_documental_de_texto(None)
    assert resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_texto_vazio_nunca_gera_hipotese():
    assert ponte.hipoteses_multi_evidencia_de_texto('') == ()


def test_texto_totalmente_generico_fica_nao_encontrada():
    resolucao = ponte.resolver_tipo_documental_de_texto('texto qualquer sem nenhum sinal reconhecido')
    assert resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_apenas_evidencia_fiscal_resolve_guia_generica():
    """Só o produtor fiscal (Código de Receita) alimentando a ponte já
    basta para RESOLVER -- prova que o produtor fiscal está agregado,
    não é decorativo."""
    resolucao = ponte.resolver_tipo_documental_de_texto('Código de Receita: 1234')
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_GUIA_GENERICA


def test_apenas_evidencia_estrutural_de_ponto_resolve_folha_de_ponto():
    """Duas linhas de marcação repetidas, sem a frase "Folha de Ponto"
    em lugar nenhum -- prova que o produtor de ponto está agregado."""
    texto = (
        '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00'
    )
    resolucao = ponte.resolver_tipo_documental_de_texto(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_FOLHA_DE_PONTO


def test_apenas_rotulo_alternativo_de_extrato_resolve_extrato():
    """"Resumo da Folha" sozinho, sem nenhuma das 17 regras legadas
    reconhecer -- prova que o produtor de rótulo alternativo está
    agregado."""
    resolucao = ponte.resolver_tipo_documental_de_texto('Resumo da Folha de Pagamento -- Julho/2026')
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == TIPO_EXTRATO


def test_apenas_finalidade_de_pagamento_resolve_fgts():
    """Só a descrição de finalidade ("recolhimento do FGTS") -- prova
    que o produtor de finalidade de pagamento está agregado."""
    resolucao = ponte.resolver_tipo_documental_de_texto('Comprovante de recolhimento do FGTS -- competência 07/2026')
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.valores_confirmados[0].entidade_id == FINALIDADE_FGTS


def test_reforco_fiscal_estrutural_alimenta_a_mesma_disputa_do_resolvedor():
    """A descrição de FGTS (MODERADA) + o reforço fiscal estrutural
    (FRACA, mesma finalidade JÁ identificada pela descrição) -- prova
    que `reconciliar_evidencia_fiscal_com_finalidade` também está
    agregado à ponte, não só `sinais_textuais_de_finalidade_pagamento`
    isolado. O MESMO sinal fiscal (Código de Receita) também alimenta
    'Guia' (genérico) com força igual (MODERADA) -- o resolvedor único
    já trata esse empate como AMBIGUA (nunca decide por acaso entre um
    tipo genérico e uma finalidade específica igualmente sustentada);
    este teste prova a agregação real, não força um vencedor que a
    própria política de combinação de força não garante."""
    texto = 'Comprovante de recolhimento do FGTS -- Código de Receita: 0561'
    hipoteses = ponte.hipoteses_multi_evidencia_de_texto(texto)
    tipos_com_evidencia_de_finalidade_fiscal = {
        h.tipo_documental for h in hipoteses
        for e in h.evidencias if e.fonte == 'finalidade_comprovante_pagamento'
    }
    assert FINALIDADE_FGTS in tipos_com_evidencia_de_finalidade_fiscal
    resolucao = ponte.resolver_tipo_documental_de_texto(texto)
    assert resolucao.estado == EstadoResolucaoDimensao.AMBIGUA
    tipos_candidatos = {c.entidade_id for c in resolucao.candidatos}
    assert tipos_candidatos == {FINALIDADE_FGTS, TIPO_GUIA_GENERICA}


def test_resolver_de_pdf_com_bytes_vazios_nunca_toca_extracao_e_fica_nao_encontrada():
    """`b''` é falsy -- `extrair_texto_seguro` retorna `None` sem
    sequer chamar `extrair_texto_pdf` (nunca invoca pdfplumber)."""
    resolucao = ponte.resolver_tipo_documental_de_pdf(b'')
    assert resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_resolver_de_pdf_delega_para_resolver_de_texto_sem_segunda_extracao(monkeypatch):
    """Prova a DELEGAÇÃO (Fase 2: "nunca uma segunda extração de
    texto") -- reaproveita `extrair_texto_seguro` já existente via
    monkeypatch (nunca chama pdfplumber de verdade, indisponível neste
    sandbox) e confirma que o resultado é idêntico ao caminho por
    texto direto para o MESMO texto."""
    texto_canned = 'Resumo da Folha de Pagamento -- Julho/2026'
    monkeypatch.setattr(ponte, 'extrair_texto_seguro', lambda conteudo_pdf: texto_canned)
    resolucao_via_pdf = ponte.resolver_tipo_documental_de_pdf(b'bytes-fake-de-pdf')
    resolucao_via_texto = ponte.resolver_tipo_documental_de_texto(texto_canned)
    assert resolucao_via_pdf == resolucao_via_texto


def test_resolver_de_pdf_com_texto_none_extraido_nunca_inventa_classificacao():
    """PDF sem texto extraível (Fase 3: extração != classificação) --
    `resolver_tipo_documental_de_pdf` nunca inventa um tipo, vira
    `NAO_ENCONTRADA`, jamais uma exceção."""
    resolucao = ponte.resolver_tipo_documental_de_texto(None)
    assert resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resolucao.valores_confirmados == ()
