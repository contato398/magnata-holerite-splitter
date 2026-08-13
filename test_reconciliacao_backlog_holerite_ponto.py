"""
Testes com fixtures sintéticas para
scripts/reconciliacao_backlog_holerite_ponto.py — a rotina reutilizável de
reconciliação do backlog real de Holerite + Folha de Ponto por competência
(Macro de fechamento do pacote HOLERITE_FOLHA_PONTO, item 5).

100% dado sintético -- nenhum CPF/nome/telefone/Record ID real. Nenhum
teste aqui faz chamada de rede real (requests é sempre mockado).
"""
from unittest.mock import Mock, patch

from scripts.reconciliacao_backlog_holerite_ponto import (
    CATEGORIAS,
    reconciliar_colaborador,
    reconciliar_todos,
)

TEXTO_HOLERITE_JUNHO = 'MAGNATA PORTARIA E SERVICOS\nMensalista Junho de 2026\nTotal de Vencimentos: 2000,00'
TEXTO_PONTO_JUNHO = 'CARTAO DE PONTO\nJunho de 2026\nEntrada Saida'
TEXTO_PONTO_JULHO = 'CARTAO DE PONTO\nJulho de 2026\nEntrada Saida'
TEXTO_SEM_COMPETENCIA = 'documento sem nenhuma competencia impressa'


def _sessao_mock(conteudo_holerite: bytes, conteudo_ponto: bytes):
    sessao = Mock()
    sessao.get.side_effect = [
        Mock(content=conteudo_holerite, raise_for_status=Mock()),
        Mock(content=conteudo_ponto, raise_for_status=Mock()),
    ]
    return sessao


def _dados(**overrides):
    base = {
        'funcionario_id': 'recFAKE0000000001',
        'status': 'Ativo',
        'whatsapp': '5511999999999',
        'cpf': '111.222.333-44',
        'holerite_url': 'https://static/holerite.pdf',
        'folha_ponto_url': 'https://static/ponto.pdf',
        'envios_por_competencia': set(),
        'assinaturas_por_competencia': set(),
    }
    base.update(overrides)
    return base


def test_todas_as_categorias_sao_strings_unicas():
    assert len(CATEGORIAS) == len(set(CATEGORIAS))


def test_inativo_e_bloqueado_sem_baixar_nada():
    dados = _dados(status='Inativo')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._baixar') as mock_baixar:
        resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'bloqueado'
    mock_baixar.assert_not_called()


def test_status_ausente_e_bloqueado():
    dados = _dados(status=None)
    resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'bloqueado'


def test_status_desconhecido_e_bloqueado():
    dados = _dados(status='ValorNuncaVistoNoAirtable')
    resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'bloqueado'


def test_sem_cpf_e_identidade_insuficiente():
    dados = _dados(cpf=None)
    resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'identidade_insuficiente'


def test_sem_whatsapp_e_telefone_ausente():
    dados = _dados(whatsapp=None)
    resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'telefone_ausente_ou_invalido'


def test_sem_holerite_e_documento_ausente():
    dados = _dados(holerite_url=None)
    resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'documento_ausente'


def test_sem_folha_ponto_e_documento_ausente():
    dados = _dados(folha_ponto_url=None)
    resultado = reconciliar_colaborador(dados)
    assert resultado.categoria == 'documento_ausente'


def test_competencia_indeterminavel_em_qualquer_pdf():
    dados = _dados()
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_SEM_COMPETENCIA, TEXTO_PONTO_JUNHO]):
        resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'indeterminavel'


def test_competencia_divergente_entre_holerite_e_ponto():
    dados = _dados()
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JULHO]):
        resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'competencia_divergente'
    assert resultado.competencia_holerite == 'Junho 2026'
    assert resultado.competencia_ponto == 'Julho 2026'


def test_pronto_para_lote_quando_competencia_bate_e_nunca_enviado_nem_assinado():
    dados = _dados()
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'pronto_para_lote'
    assert resultado.competencia_holerite == 'Junho 2026'


def test_ja_recebeu_esta_competencia_nao_conta_como_pronto():
    """'Já recebeu alguma vez' não é suficiente -- mas 'já recebeu ESTA
    competência específica' sim é motivo para não recolocar no lote."""
    dados = _dados(envios_por_competencia={'Junho 2026'})
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'ja_recebeu_esta_competencia'


def test_ja_assinou_este_pacote_tem_prioridade_sobre_ja_recebeu():
    dados = _dados(
        envios_por_competencia={'Junho 2026'},
        assinaturas_por_competencia={'Junho 2026'},
    )
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'ja_assinou_este_pacote'


def test_envio_de_competencia_diferente_nao_impede_pronto_para_lote():
    """Já recebeu Maio, mas a competência atual dos PDFs é Junho -- isto
    NÃO é 'já recebeu esta competência' (a exigência do pedido: não
    presumir atendimento por competência errada)."""
    dados = _dados(envios_por_competencia={'Maio 2026'})
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'pronto_para_lote'


def test_falha_ao_baixar_pdf_e_indeterminavel_nao_bloqueado():
    dados = _dados()
    sessao = Mock()
    sessao.get.side_effect = RuntimeError('timeout')
    resultado = reconciliar_colaborador(dados, sessao)
    assert resultado.categoria == 'indeterminavel'


def test_reconciliar_todos_processa_lista_e_nao_gera_dupla_contagem():
    lista = [
        _dados(funcionario_id='recA'),
        _dados(funcionario_id='recB', status='Inativo'),
        _dados(funcionario_id='recC', cpf=None),
    ]
    sessao = _sessao_mock(b'%PDF-holerite', b'%PDF-ponto')
    with patch('scripts.reconciliacao_backlog_holerite_ponto._extrair_texto_pdf_bytes',
               side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        relatorio = reconciliar_todos(lista, sessao)
    assert relatorio.total() == 3
    contagem = relatorio.contagem_por_categoria()
    assert sum(contagem.values()) == 3  # cada colaborador cai em exatamente 1 categoria


def test_resultado_nunca_contem_campos_de_pii():
    """Blindagem estrutural: o dataclass de resultado não tem nenhum campo
    de nome/telefone/CPF -- só IDs e categorias."""
    from scripts.reconciliacao_backlog_holerite_ponto import ResultadoColaborador
    campos_esperados = {
        'funcionario_id', 'categoria', 'competencia_holerite', 'competencia_ponto', 'detalhe',
    }
    campos_reais = set(ResultadoColaborador.__dataclass_fields__.keys())
    assert campos_reais == campos_esperados
    for termo_pii in ('nome', 'telefone', 'whatsapp', 'cpf'):
        assert termo_pii not in campos_reais
