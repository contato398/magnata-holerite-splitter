"""
Missão B (investigação de automação DCTFWeb, 24/08/2026) — prioridade
técnica principal: o Recibo de Entrega da DCTFWeb de Junho/2026 existe no
Gmail (e-mail de 16/07/2026, thread "guia DCTFWEB", remetente
dpessoal.contabilidade1@hotmail.com, junto com a Declaração completa e a
Guia de pagamento) mas nunca chegou ao Airtable.

Achado principal, com evidência direta (não hipótese): a causa NÃO está em
app.py. É confirmada em duas camadas:

1. `git show 564ecb0` (04/08/2026) mostra que `REMETENTES_CONFIAVEIS` em
   apps_script_email_intake.gs tinha um TYPO até essa data:
   'dp.contabilidade1@hotmail.com' em vez do endereço real
   'dpessoal.contabilidade1@hotmail.com'. A própria mensagem do commit
   registra: "causa provável da não-captura de e-mails de Departamento
   Pessoal desde 09/06/2026" — intervalo que cobre o e-mail de 16-17/07
   inteiro. Sem o remetente na lista, a query do Gmail
   `(label:Documentos-Magnata OR from:<confiáveis>) -label:Processado-Render`
   nunca reconheceu esse e-mail como elegível, e ele nunca teve o label
   manual aplicado — então NUNCA foi sequer enviado para /email/webhook.

2. Confirmado por leitura direta do Gmail (thread "guia DCTFWEB",
   16-17/07/2026): a mensagem com os 3 PDFs (Declaração, Guia, Recibo)
   segue hoje (24/08/2026) SEM nenhum label do pipeline (só
   IMPORTANT/INBOX) — nem Documentos-Magnata, nem Processado-Render.
   Confirmado por leitura direta do Airtable: os hashes SHA-256 reais do
   Recibo e da Declaração (calculados a partir dos PDFs originais) não
   existem em nenhum registro de "Arquivos" (tblRsvhz8oOcUqhkv) — ou seja,
   nem o caminho fiscal, nem o caminho genérico de fallback (Processar
   Arquivos/Pendência) foram tentados. Isso descarta a hipótese de bug de
   classificação/competência para este caso: o e-mail nunca chegou perto
   de rodar `classificar_documento`/`_detectar_competencia_fiscal`.

Este arquivo prova, com teste de integração real via Flask test client
(payload igual ao que o Apps Script monta), que o app.py ATUAL (nesta
branch, com o fix de "Período apuração" sem preposição já aplicado) já
processaria corretamente os 3 anexos SE o payload chegasse até ele — ou
seja, o código deste repositório já não reproduz o problema; o bloqueio
está inteiramente na camada de captura (Apps Script/Gmail), não em
app.py. A pendência residual (não resolvida por este código) é: mesmo
após o typo ter sido corrigido no repositório (04/08/2026, 20 dias antes
desta investigação), esse e-mail específico continua sem label e sem
registro no Airtable — o que exige confirmar, fora do escopo de código,
se o script realmente implantado em script.google.com está sincronizado
com apps_script_email_intake.gs e se o gatilho horário está ativo (ver
relatório final, "Pendências que exigem decisão humana").

100% dado sintético -- nenhum CPF/nome/CNPJ real em nenhum lugar deste
arquivo (os PDFs abaixo reproduzem a ESTRUTURA/rótulos reais dos 3
documentos, com CNPJ/nome de empresa fictícios)."""
import base64
import hashlib
from unittest.mock import Mock, patch

import pytest

from app import app, TABLE_GUIAS, F_GUIA_TIPO, F_GUIA_COMPETENCIA, TIPOS_FISCAIS


def _gerar_pdf_com_linhas(*linhas: str) -> bytes:
    """Mesmo padrão já usado em test_importacao_lote.py: PDF de verdade,
    parseável por pdfplumber, com texto sintético embutido."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.multi_cell(0, 10, text='\n'.join(linhas))
    return bytes(pdf.output())


# Reconstrução sintética da estrutura real dos 3 anexos do e-mail de
# 16/07/2026 (CNPJ/nome fictícios, mesmos rótulos de campo do documento
# real, mesma competência 06/2026 usada nos testes de _detectar_competencia_fiscal).
PDF_RECIBO = _gerar_pdf_com_linhas(
    'MINISTÉRIO DA FAZENDA',
    'SECRETARIA ESPECIAL DA RECEITA FEDERAL DO BRASIL',
    'Recibo de Entrega da Declaração de Débitos e Créditos Tributários Federais - DCTFWeb',
    'CNPJ/CPF 11.111.111/0001-11',
    'Nome EMPRESA SINTETICA LTDA',
    'Período de apuração 06/2026',
    'Declaração Retificadora Não',
)
PDF_DECLARACAO = _gerar_pdf_com_linhas(
    'MINISTÉRIO DA FAZENDA',
    'SECRETARIA ESPECIAL DA RECEITA FEDERAL DO BRASIL',
    'RELATÓRIO DA DECLARAÇÃO COMPLETA - DCTFWeb',
    'Nome do Contribuinte CNPJ 11.111.111/0001-11 EMPRESA SINTETICA LTDA',
    'Período apuração 06/2026 Número do Recibo 50000000000000',
)
PDF_GUIA_DARF = _gerar_pdf_com_linhas(
    'MINISTÉRIO DA FAZENDA',
    'DOCUMENTO DE ARRECADAÇÃO DE RECEITAS FEDERAIS - DARF',
    'CNPJ 11.111.111/0001-11 EMPRESA SINTETICA LTDA',
    'Período de Apuração 06/2026',
    'Valor Total R$ 1.000,00',
)


def _payload_email_3_anexos():
    """Payload no MESMO formato que _processarMensagem (Apps Script) monta
    e envia a /email/webhook — mesmos nomes de arquivo do e-mail real (só
    o conteúdo é sintético)."""
    anexos = [
        ('Recibo_11111111000111_062026_40_0000050000000000000.pdf', PDF_RECIBO),
        ('DeclaracaoCompleta_11111111000111_062026_40_.pdf', PDF_DECLARACAO),
        ('GuiaPagamento_11111111000111_160720261619252876.pdf', PDF_GUIA_DARF),
    ]
    return {
        'message_id': 'msg-sintetico-thread-dctfweb-junho',
        'assunto': 'RE: guia DCTFWEB',
        'remetente': 'dpessoal.contabilidade1@hotmail.com',
        'corpo': 'Segue declaração completa, recibo e guia DCTFWEB 06/2026',
        'anexos': [
            {'nome_arquivo': nome, 'conteudo_base64': base64.b64encode(conteudo).decode()}
            for nome, conteudo in anexos
        ],
    }, anexos


def _resposta_criar_registro(record_id):
    r = Mock()
    r.ok = True
    r.json.return_value = {'id': record_id}
    return r


def test_email_com_3_anexos_dctfweb_recibo_declaracao_guia_processa_todos():
    """Teste de integração completo do fluxo do Missão B: simula o e-mail
    real de 16/07/2026 com os 3 anexos juntos, batendo em /email/webhook de
    ponta a ponta (base64 -> hash -> extração pdfplumber -> classificação
    -> competência -> roteamento fiscal -> _criar_registro). Mede
    exatamente o que a Missão B pediu: quantos anexos chegaram, quantos
    foram extraídos, como cada um foi classificado, qual competência cada
    um teve, e quantos seriam persistidos — provando que o CÓDIGO ATUAL
    não perde nenhum dos três."""
    payload, anexos_originais = _payload_email_3_anexos()

    ids_criados = iter([
        'recEMAIL_THREAD',  # Emails Savian, criado antes do loop de anexos
        'recGUIA_RECIBO', 'recGUIA_DECLARACAO', 'recARQ_GUIA_DARF', 'recPROC_GUIA_DARF',
    ])
    mock_post = Mock(side_effect=lambda *a, **k: _resposta_criar_registro(next(ids_criados)))

    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._at_throttle'), \
         patch('app.requests.post', mock_post), \
         patch('app._buscar_por_campo', return_value=None), \
         patch('app._anexar_attachment') as mock_anexar:
        app.testing = True
        resp = app.test_client().post(
            '/email/webhook', json=payload, headers={'X-API-KEY': 'test'},
        )

    assert resp.status_code == 200
    body = resp.get_json()

    # 1. Recebidos/extraídos: os 3 anexos do e-mail aparecem na resposta —
    #    nenhum foi descartado silenciosamente pelo loop.
    processados = body['anexos_processados']
    assert len(processados) == 3 == len(anexos_originais)

    por_nome = {item['nome_arquivo']: item for item in processados}

    # 2. Classificação — cada anexo cai no tipo correto (a ordem das regras
    #    de TIPO_DOC_REGRAS distingue Recibo de Declaração corretamente).
    recibo = por_nome['Recibo_11111111000111_062026_40_0000050000000000000.pdf']
    declaracao = por_nome['DeclaracaoCompleta_11111111000111_062026_40_.pdf']
    guia = por_nome['GuiaPagamento_11111111000111_160720261619252876.pdf']

    assert recibo['tipo_documento'] == 'DCTFWeb - Recibo de Entrega'
    assert declaracao['tipo_documento'] == 'DCTFWeb - Declaração'
    assert guia['tipo_documento'] == 'Guia'  # tipo genérico (DARF) -- ver nota abaixo

    # 3. Competência — comprovada para os 3 (Recibo já funcionava antes do
    #    fix; Declaração só funciona com o fix de "Período apuração" sem
    #    "de"; Guia/DARF usa "Período de Apuração" com "de", que já
    #    funcionava mesmo antes do fix desta branch).
    assert recibo['acao'] == 'arquivado_guia_comprovante'
    assert recibo['folha_mensal'] == 'Junho 2026'
    assert declaracao['acao'] == 'arquivado_guia_comprovante'
    assert declaracao['folha_mensal'] == 'Junho 2026'

    # 4. Persistência — Recibo e Declaração são roteados para a tabela
    #    fiscal correta (Guias e Comprovantes), com o campo Competência
    #    (Missão A) preenchido em ambos.
    assert recibo['guia_record_id'] == 'recGUIA_RECIBO'
    assert declaracao['guia_record_id'] == 'recGUIA_DECLARACAO'
    chamadas_guias = [
        c for c in mock_post.call_args_list
        if c.args and c.args[0].endswith(f'/{TABLE_GUIAS}')
    ]
    assert len(chamadas_guias) == 2
    for c in chamadas_guias:
        assert c.kwargs['json']['fields'][F_GUIA_COMPETENCIA] == '2026-06-01'

    # 5. Achado direto (Missão B, "outro defeito diretamente relacionado ao
    #    mesmo fluxo"): a Guia/DARF do DCTFWeb, embora venha no MESMO
    #    e-mail que o Recibo e a Declaração, cai no tipo genérico 'Guia' —
    #    que NÃO está em TIPOS_FISCAIS e não é um dos dois tipos que
    #    _processar_anexo_fiscal roteia para Guias e Comprovantes. Como o
    #    remetente também não é o REMETENTE_FISCAL dedicado (é o
    #    Departamento Pessoal, não o Fiscal), ela cai no caminho GENÉRICO
    #    (Arquivos + Processar Arquivos), não na tabela fiscal — mesmo após
    #    o typo do remetente ser corrigido, essa Guia nunca seria
    #    classificada automaticamente como documento fiscal DCTFWeb.
    #    Documentado aqui como pendência (Missão E/estrutural), não
    #    corrigido nesta rodada — mudar TIPO_DOC_REGRAS/TIPOS_FISCAIS para
    #    tratar 'Guia' + contexto DCTFWeb é uma mudança de classificação
    #    que afeta outros fluxos (Guia de Recolhimento/GPS/DARF genéricos
    #    não-DCTFWeb) e não é pequena/isolada o suficiente para corrigir
    #    sem decisão humana.
    assert 'Guia' not in TIPOS_FISCAIS
    assert guia['tipo_documento'] not in TIPOS_FISCAIS
    assert 'arquivo_record_id' in guia  # foi para o caminho genérico, não para Guias e Comprovantes
    assert 'guia_record_id' not in guia
