"""
Macro 6A — Auditoria e correção pontual da competência fiscal.

Achado comprovado (Task #2): `_detectar_competencia_fiscal` caía
silenciosamente em "mês anterior ao recebimento" sempre que o PDF não
trazia "Competência MM/AAAA" ou "Período de Apuração MM/AAAA" -- esse mês
adivinhado era então gravado em TODOS os registros de cliente fatiados a
partir do mesmo PDF (Extrato/FGTS, via _processar_doc_cliente_master) ou no
comprovante de Guia, sem nenhum sinal de revisão.

Correção: a função nunca adivinha -- na ausência de marcador semântico
explícito (numérico ou por extenso, sempre ancorado em "Competência" /
"Período de Apuração" / "Período de Referência"), devolve None, e quem
chama (_processar_anexo_fiscal) roteia para Pendência de revisão manual em
vez de processar automaticamente.

100% dado sintético -- nenhum CPF/nome real em nenhum lugar deste arquivo.

Macro 6A — fechamento autônomo (revisão adversarial, §5): testes adicionais
abaixo para múltiplas competências divergentes (ambiguidade), propagação
correta ao fatiamento, e auditabilidade sanitizada do log de rejeição.
"""
import inspect
import logging
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app import (
    _detectar_competencia_fiscal,
    _processar_anexo_fiscal,
)


# ── _detectar_competencia_fiscal — marcadores reconhecidos (regressão) ──

def test_competencia_numerica_com_marcador_competencia_e_reconhecida():
    texto = 'DCTFWeb - Declaração\nCompetência: 05/2026\nCNPJ: 11.111.111/0001-11'
    assert _detectar_competencia_fiscal(texto) == 'Maio 2026'


def test_competencia_numerica_com_marcador_periodo_de_apuracao_e_reconhecida():
    texto = 'Guia de Recolhimento\nPeríodo de Apuração 08/2026\nValor: R$ 100,00'
    assert _detectar_competencia_fiscal(texto) == 'Agosto 2026'


def test_competencia_por_extenso_com_marcador_e_reconhecida():
    texto = 'Extrato da Folha de Pagamento\nCompetência: Junho de 2026\n'
    assert _detectar_competencia_fiscal(texto) == 'Junho 2026'


def test_competencia_por_extenso_sem_preposicao_de_e_reconhecida():
    texto = 'Período de Referência Julho 2026\nFGTS Digital\n'
    assert _detectar_competencia_fiscal(texto) == 'Julho 2026'


def test_competencia_com_acentuacao_alternativa_e_reconhecida():
    # "Periodo de Apuracao" sem acento -- variação de OCR/exportação real.
    texto = 'Periodo de Apuracao: 03/2026\n'
    assert _detectar_competencia_fiscal(texto) == 'Marco 2026' or _detectar_competencia_fiscal(texto) == 'Março 2026'


def test_competencia_periodo_apuracao_sem_preposicao_de_e_reconhecida():
    """Achado real em produção (24/08/2026): o RELATÓRIO DA DECLARAÇÃO
    COMPLETA - DCTFWeb emitido pela Receita Federal rotula o campo como
    "Período apuração" (sem "de") -- diferente do Recibo de Entrega do
    mesmo DCTFWeb, que usa "Período de apuração" (com "de"). Antes desta
    correção, a Declaração completa nunca tinha competência comprovada e
    caía sempre em "Competência fiscal não detectada", mesmo com o valor
    certo (06/2026) presente no texto -- reproduzido aqui a partir do
    layout real (dado sintético, sem CNPJ/nome real)."""
    texto = (
        'RELATÓRIO DA DECLARAÇÃO COMPLETA - DCTFWeb\n'
        'Nome do Contribuinte EMPRESA SINTETICA LTDA\n'
        'Período apuração 06/2026 Número do Recibo 50000000000000\n'
    )
    assert _detectar_competencia_fiscal(texto) == 'Junho 2026'


# ── _detectar_competencia_fiscal — adversarial: nunca adivinha ──────────

def test_sem_nenhum_marcador_devolve_none_em_vez_de_adivinhar():
    """O achado central: texto fiscal plausível, mas SEM 'Competência' nem
    'Período de Apuração/Referência' -- antes caía num mês adivinhado."""
    texto = 'FGTS Digital\nCNPJ: 11.111.111/0001-11\nValor total: R$ 500,00\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_texto_vazio_devolve_none():
    assert _detectar_competencia_fiscal('') is None
    assert _detectar_competencia_fiscal(None) is None


def test_data_de_vencimento_isolada_nunca_e_usada_como_competencia():
    """Vencimento/pagamento/emissão/recebimento são datas diferentes de
    competência -- nunca podem substituí-la."""
    texto = 'Guia de Recolhimento\nVencimento: 10/06/2026\nData de Pagamento: 09/06/2026\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_data_de_emissao_isolada_nunca_e_usada_como_competencia():
    texto = 'DCTFWeb - Recibo de Entrega\nData de Emissão: 15/07/2026\nProtocolo: 123456\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_data_de_recebimento_isolada_nunca_e_usada_como_competencia():
    texto = 'Comprovante\nData de Recebimento: 20/08/2026\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_mes_solto_sem_marcador_semantico_nunca_e_usado_como_competencia():
    """Mês por extenso presente no texto, mas SEM estar perto de
    'Competência'/'Período de Apuração/Referência' -- não deve ser
    confundido com competência (ex.: mês citado em outro contexto)."""
    texto = 'Este documento foi gerado em Agosto de 2026 pelo sistema XPTO.\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_mes_corrente_do_sistema_nunca_e_usado_como_fallback():
    """Regressão do bug original: com `datetime.now()` mockado para uma
    data arbitrária, o resultado continua None -- a função NUNCA deriva a
    resposta do relógio do sistema quando não há marcador."""
    texto = 'Extrato da Folha de Pagamento\nCNPJ: 22.222.222/0001-22\n'
    with patch('app.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1)
        assert _detectar_competencia_fiscal(texto) is None


def test_nome_do_arquivo_nunca_e_usado_isoladamente():
    """A função só recebe `texto` -- nome de arquivo nunca é parâmetro,
    então não há como ele influenciar a resposta (documentado aqui como
    prova de contrato: a assinatura da função não aceita nome_arquivo)."""
    import inspect
    assinatura = inspect.signature(_detectar_competencia_fiscal)
    assert list(assinatura.parameters.keys()) == ['texto']


# ── _processar_anexo_fiscal — roteia para revisão quando não comprovada ─

def _resposta_criar_registro(record_id):
    r = Mock()
    r.ok = True
    r.json.return_value = {'id': record_id}
    return r


def test_processar_anexo_fiscal_sem_competencia_cria_pendencia_e_nao_fatiar():
    texto_sem_marcador = 'FGTS Digital\nCNPJ: 11.111.111/0001-11\nValor total: R$ 500,00\n'

    with patch('app._at_throttle'), \
         patch('app.requests.post', return_value=_resposta_criar_registro('recPEND1')), \
         patch('app._processar_doc_cliente_master') as mock_fatiador:
        resultado = _processar_anexo_fiscal(b'conteudo-fake', 'fgts.pdf', 'FGTS', texto_sem_marcador)

    assert resultado['acao'] == 'competencia_fiscal_nao_detectada'
    assert resultado['pendencia_record_id'] == 'recPEND1'
    # nunca chega a fatiar/gravar nos registros de cliente com competência adivinhada
    mock_fatiador.assert_not_called()


def test_processar_anexo_fiscal_sem_competencia_cria_pendencia_para_guia():
    texto_sem_marcador = 'DCTFWeb - Recibo de Entrega\nProtocolo: 999999\n'

    with patch('app._at_throttle'), \
         patch('app.requests.post', return_value=_resposta_criar_registro('recPEND2')), \
         patch('app._anexar_attachment') as mock_anexar:
        resultado = _processar_anexo_fiscal(
            b'conteudo-fake', 'dctfweb.pdf', 'DCTFWeb - Recibo de Entrega', texto_sem_marcador,
        )

    assert resultado['acao'] == 'competencia_fiscal_nao_detectada'
    # nunca chega a criar/anexar a Guia com competência adivinhada
    mock_anexar.assert_not_called()


def test_processar_anexo_fiscal_com_competencia_comprovada_segue_fluxo_normal():
    texto_com_marcador = 'FGTS Digital\nCompetência: 05/2026\nCNPJ: 11.111.111/0001-11\n'

    with patch('app._processar_doc_cliente_master',
               return_value={'status': 'concluido', 'registros_criados': 0}) as mock_fatiador:
        resultado = _processar_anexo_fiscal(b'conteudo-fake', 'fgts.pdf', 'FGTS', texto_com_marcador)

    assert resultado['acao'] == 'fatiado_por_cliente'
    assert resultado['folha_mensal'] == 'Maio 2026'
    mock_fatiador.assert_called_once()
    # a competência comprovada foi de fato repassada ao fatiador
    args, kwargs = mock_fatiador.call_args
    assert args[2] == 'Maio 2026'


# ── Revisão adversarial (Macro 6A — fechamento autônomo, §5) ────────────

def test_multiplas_competencias_divergentes_e_ambiguidade_nunca_escolhe_uma():
    """Achado da revisão adversarial: a versão anterior usava re.search
    (só o 1º achado) e escolheria silenciosamente um dos dois valores
    divergentes -- o mesmo risco de "adivinhar" que a correção original
    eliminou para ausência total de marcador. Documento com DOIS valores
    de competência DIFERENTES nunca deve resultar num valor escolhido."""
    texto = 'Guia consolidada\nCompetência: 05/2026\n(outras páginas)\nCompetência: 08/2026\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_competencia_repetida_com_mesmo_valor_nao_e_ambiguidade():
    """Cabeçalho + rodapé repetindo o MESMO valor não é ambíguo -- só
    valores DIVERGENTES bloqueiam."""
    texto = 'Guia\nCompetência: 05/2026\n(rodapé)\nCompetência: 05/2026\n'
    assert _detectar_competencia_fiscal(texto) == 'Maio 2026'


def test_formato_numerico_e_por_extenso_concordando_nao_e_ambiguidade():
    texto = 'Competência: 05/2026\nCompetência: Maio de 2026\n'
    assert _detectar_competencia_fiscal(texto) == 'Maio 2026'


def test_formato_numerico_e_por_extenso_divergindo_e_ambiguidade():
    texto = 'Competência: 05/2026\nCompetência: Junho de 2026\n'
    assert _detectar_competencia_fiscal(texto) is None


def test_ambiguidade_gera_aviso_sanitizado_e_auditavel(caplog):
    """O log de ambiguidade nunca reproduz trecho do PDF/PII -- só os
    valores (mês, ano) em conflito, que não são dado pessoal."""
    texto = 'Competência: 05/2026\nCompetência: 08/2026\nCPF: 111.111.111-11\nFULANO DE TAL SINTETICO\n'
    with caplog.at_level(logging.WARNING):
        resultado = _detectar_competencia_fiscal(texto)
    assert resultado is None
    mensagens = [r.getMessage() for r in caplog.records if 'ambígua' in r.getMessage()]
    assert len(mensagens) == 1
    assert '05/2026' in mensagens[0] and '08/2026' in mensagens[0]
    # nunca vaza CPF/nome no log de auditoria
    assert '111.111.111-11' not in mensagens[0]
    assert 'FULANO' not in mensagens[0].upper()


def test_recebimento_do_email_nunca_pode_influenciar_pois_nao_e_parametro():
    """'Recebimento do e-mail não seja competência' -- estruturalmente
    garantido: a função só aceita `texto`, nunca recebe data de e-mail,
    então não há como essa informação vazar para o resultado."""
    assinatura = inspect.signature(_detectar_competencia_fiscal)
    parametros = list(assinatura.parameters.keys())
    assert parametros == ['texto']
    assert 'data_email' not in parametros
    assert 'recebido_em' not in parametros


def test_processar_anexo_fiscal_com_competencias_ambiguas_vai_para_pendencia():
    """Ambiguidade propaga corretamente para o mesmo caminho de revisão
    manual usado para ausência total de marcador -- nenhum registro de
    cliente é criado com uma competência escolhida arbitrariamente."""
    texto_ambiguo = 'FGTS Digital\nCompetência: 05/2026\nCompetência: 08/2026\n'

    with patch('app._at_throttle'), \
         patch('app.requests.post', return_value=_resposta_criar_registro('recPENDAMBIGUA')), \
         patch('app._processar_doc_cliente_master') as mock_fatiador:
        resultado = _processar_anexo_fiscal(b'conteudo-fake', 'fgts.pdf', 'FGTS', texto_ambiguo)

    assert resultado['acao'] == 'competencia_fiscal_nao_detectada'
    mock_fatiador.assert_not_called()
