"""
Teste de regressao para o bug de deduplicacao encontrado em 2026-07-21 no
Envio da Unimed Itapetininga: _aplicar_outros_documentos_no_envio() usava
(filename, url) como chave de dedup, mas a URL de anexo do Airtable e
assinada e muda a cada leitura — o dedup falhava silenciosamente e
duplicava os recibos de Joao Batista e Teodolino que ja estavam la.

A correcao troca a chave para filename normalizado + comparacao de
tamanho (bytes), que sao estaveis entre leituras.
"""
from app import _normalizar_filename, _classificar_novos_vs_existentes


# Tamanhos reais dos PDFs fatiados nesta rodada (MANIFESTO_FINAL.json)
TAM_JOAO = 55429
TAM_TEODOLINO = 55420
TAM_ALCIONE = 55413
TAM_EMILEIDE = 55427


def _attachment_existente(filename, size, url):
    return {'id': f'att_{filename}', 'filename': filename, 'size': size, 'url': url}


def _candidato(filename, size, url):
    return {'filename': filename, 'size': size, 'url': url, 'documento': filename}


def test_normalizar_filename_ignora_espacos_e_caixa():
    assert _normalizar_filename('  Recibo.pdf  ') == 'recibo.pdf'
    assert _normalizar_filename('RECIBO.PDF') == 'recibo.pdf'
    assert _normalizar_filename(None) == ''


def test_caso_real_unimed_nao_duplica_joao_e_teodolino():
    """Reproduz exatamente o cenario do Envio da Unimed Itapetininga em
    2026-07-21: Joao Batista e Teodolino ja estavam anexados (de uma
    aplicacao anterior, com uma URL assinada X); a nova leitura de "Outros
    documentos" traz os 4 candidatos (Joao, Teodolino, Alcione, Emileide)
    com uma URL assinada DIFERENTE (Y) para os mesmos arquivos de Joao e
    Teodolino — simulando a rotacao real de URL do Airtable.
    Resultado esperado: so Alcione e Emileide devem ser adicionados.
    """
    arquivos_existentes = [
        {'id': 'att1', 'filename': 'Folha de Ponto Junho 2026 - JOAO BATISTA SALES JUNIOR - ASSINADO.pdf',
         'size': 188000, 'url': 'https://airtable-attachments/urlX/folha_joao.pdf'},
        {'id': 'att2', 'filename': 'Comprovante Assinatura - Joao Batista Sales Junior.pdf',
         'size': 2300, 'url': 'https://airtable-attachments/urlX/comp_joao.pdf'},
        _attachment_existente(
            'Assiduidade Junho 2026 - TEODOLINO MUNIS FERNANDES JUNIOR.pdf',
            TAM_TEODOLINO, 'https://airtable-attachments/urlX/teodolino.pdf'),
        _attachment_existente(
            'Assiduidade Junho 2026 - JOAO BATISTA SALES JUNIOR.pdf',
            TAM_JOAO, 'https://airtable-attachments/urlX/joao.pdf'),
    ]

    candidatos = [
        _candidato('Assiduidade Junho 2026 - ALCIONE GISELE DE OLIVEIRA LEME.pdf',
                   TAM_ALCIONE, 'https://airtable-attachments/urlY/alcione.pdf'),
        _candidato('Assiduidade Junho 2026 - TEODOLINO MUNIS FERNANDES JUNIOR.pdf',
                   TAM_TEODOLINO, 'https://airtable-attachments/urlY/teodolino.pdf'),  # URL Y, diferente da urlX
        _candidato('Assiduidade Junho 2026 - EMILEIDE SIMOES CORREA LEITE.pdf',
                   TAM_EMILEIDE, 'https://airtable-attachments/urlY/emileide.pdf'),
        _candidato('Assiduidade Junho 2026 - JOAO BATISTA SALES JUNIOR.pdf',
                   TAM_JOAO, 'https://airtable-attachments/urlY/joao.pdf'),  # URL Y, diferente da urlX
    ]

    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes(
        arquivos_existentes, candidatos)

    nomes_a_adicionar = sorted(n['filename'] for n in a_adicionar)
    assert nomes_a_adicionar == sorted([
        'Assiduidade Junho 2026 - ALCIONE GISELE DE OLIVEIRA LEME.pdf',
        'Assiduidade Junho 2026 - EMILEIDE SIMOES CORREA LEITE.pdf',
    ]), f'Esperado somente Alcione e Emileide, obtido: {nomes_a_adicionar}'

    nomes_ja_existentes = sorted(n['filename'] for n in ja_existentes)
    assert nomes_ja_existentes == sorted([
        'Assiduidade Junho 2026 - TEODOLINO MUNIS FERNANDES JUNIOR.pdf',
        'Assiduidade Junho 2026 - JOAO BATISTA SALES JUNIOR.pdf',
    ]), f'Joao e Teodolino deveriam ser reconhecidos como ja existentes, obtido: {nomes_ja_existentes}'

    assert conflitos == []


def test_mesmo_nome_tamanho_diferente_gera_conflito_e_nao_adiciona():
    """Nome igual mas conteudo (tamanho) diferente = conflito real. Nao
    deve ser adicionado nem tratado como duplicata silenciosa."""
    arquivos_existentes = [
        _attachment_existente('Assiduidade Junho 2026 - FULANO.pdf', 50000, 'https://x/a.pdf'),
    ]
    candidatos = [
        _candidato('Assiduidade Junho 2026 - FULANO.pdf', 99999, 'https://y/a.pdf'),
    ]
    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes(
        arquivos_existentes, candidatos)
    assert a_adicionar == []
    assert ja_existentes == []
    assert len(conflitos) == 1
    assert conflitos[0]['motivo'] == 'mesmo_nome_tamanho_diferente'


def test_arquivo_novo_sem_conflito_e_adicionado():
    arquivos_existentes = []
    candidatos = [_candidato('Assiduidade Junho 2026 - NOVO.pdf', 1234, 'https://y/n.pdf')]
    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes(
        arquivos_existentes, candidatos)
    assert [n['filename'] for n in a_adicionar] == ['Assiduidade Junho 2026 - NOVO.pdf']
    assert ja_existentes == []
    assert conflitos == []


def test_mesmo_nome_duplicado_dentro_dos_proprios_candidatos():
    """Se a propria leitura de 'Outros documentos' trouxer 2 registros com
    o mesmo filename (ex.: reprocessamento acidental), o segundo deve ser
    sinalizado como conflito, nao silenciosamente ignorado ou duplicado."""
    candidatos = [
        _candidato('Assiduidade Junho 2026 - X.pdf', 100, 'https://y/1.pdf'),
        _candidato('Assiduidade Junho 2026 - X.pdf', 100, 'https://y/2.pdf'),
    ]
    a_adicionar, ja_existentes, conflitos = _classificar_novos_vs_existentes([], candidatos)
    assert len(a_adicionar) == 1
    assert len(conflitos) == 1
    assert conflitos[0]['motivo'] == 'duplicado_dentro_dos_proprios_candidatos'
