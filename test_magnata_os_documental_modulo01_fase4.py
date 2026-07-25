"""
Testes do Modulo 01 (Documental), Fase 4 -- API de consulta da esteira.

Nenhum destes testes acessa Postgres, S3, Airtable ou qualquer servidor
HTTP real -- os handlers sao chamados diretamente como funcoes Python,
contra repositorios em memoria (Fase 1 e Fase 3).
"""
import collections
import json
from datetime import datetime, timedelta, timezone

import pytest

from magnata_os.documental.modulo01.api.autorizacao import Perfil, Sujeito
from magnata_os.documental.modulo01.api.erros import (
    MENSAGEM_ERRO_INTERNO_PADRAO,
    DocumentoNaoEncontrado,
    ErroInternoNaoExposto,
    FiltroInvalido,
    LoteNaoEncontrado,
    OrdenacaoInvalida,
    PaginacaoInvalida,
    PermissaoNegada,
    tratar_erro_para_resposta,
)
from magnata_os.documental.modulo01.api.filtros import FiltroDocumentos, FiltroLotes, Ordenacao, Paginacao
from magnata_os.documental.modulo01.api.handlers import (
    ContextoApi,
    listar_acoes_humanas,
    listar_bloqueios,
    listar_documentos,
    listar_documentos_parados,
    listar_lotes,
    obter_documento,
    obter_historico_documento,
    obter_lote,
    obter_resumo_esteira,
)
from magnata_os.documental.modulo01.api.serializacao import para_json
from magnata_os.documental.modulo01.dominio_esteira import EtapaEsteira, MotivoBloqueio, SituacaoEsteira
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import ServicoAvancoEsteira
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote

SUJEITO_OPERACIONAL = Sujeito(Perfil.OPERACIONAL)
SUJEITO_GESTOR = Sujeito(Perfil.GESTOR)
SUJEITO_AUDITOR = Sujeito(Perfil.AUDITOR)


# ============================================================================
# helpers
# ============================================================================

_Fixture = collections.namedtuple(
    '_Fixture',
    'repo_docs repo_hist repo_lotes repo_estados servico_entrada servico_avanco servico_lote ctx_api',
)


class _RelogioControlavel:
    def __init__(self, inicio: datetime):
        self._agora = inicio

    def __call__(self) -> datetime:
        return self._agora

    def avancar(self, seconds: float) -> None:
        self._agora = self._agora + timedelta(seconds=seconds)


def _montar_ctx(relogio=None) -> _Fixture:
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    kwargs = {'relogio': relogio} if relogio is not None else {}
    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist, **kwargs)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist, **kwargs)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco, **kwargs)
    ctx_api = ContextoApi(repo_docs, repo_hist, repo_lotes, repo_estados, **kwargs)

    return _Fixture(repo_docs, repo_hist, repo_lotes, repo_estados, servico_entrada, servico_avanco, servico_lote, ctx_api)


class _RepositorioDocumentosQueFalhaComSegredo:
    """Duplo de teste: simula uma falha de infraestrutura cuja mensagem
    original contem um segredo -- usado para provar que esse segredo
    NUNCA escapa para a resposta da API."""

    _MENSAGEM_COM_SEGREDO = 'postgres user=admin password=SUPER_SECRETO_NUNCA_VAZAR host=10.0.0.5'

    def listar_todos(self):
        raise ConnectionError(self._MENSAGEM_COM_SEGREDO)

    def buscar_por_id(self, documento_id):
        raise ConnectionError(self._MENSAGEM_COM_SEGREDO)

    def buscar_por_hash(self, hash_sha256):
        raise ConnectionError(self._MENSAGEM_COM_SEGREDO)

    def salvar(self, documento):
        raise ConnectionError(self._MENSAGEM_COM_SEGREDO)

    def salvar_se_ausente_por_hash(self, hash_sha256, fabricar_documento):
        raise ConnectionError(self._MENSAGEM_COM_SEGREDO)

    def remover(self, documento_id):
        raise ConnectionError(self._MENSAGEM_COM_SEGREDO)


# ============================================================================
# 1. resumo
# ============================================================================

def test_resumo_esteira_agrega_indicadores_corretamente():
    fx = _montar_ctx()
    fx.servico_lote.criar_lote('upload_manual', [
        ArquivoEntradaLote(b'resumo doc 1', 'a.pdf', 'application/pdf'),
        ArquivoEntradaLote(b'resumo doc 2', 'b.pdf', 'application/pdf'),
    ])

    resposta = obter_resumo_esteira(fx.ctx_api, SUJEITO_GESTOR)

    assert resposta.total_documentos == 2
    assert resposta.total_por_etapa.get('REGISTRO') == 2
    assert resposta.total_por_situacao.get('CONCLUIDO') == 2
    assert resposta.total_bloqueados == 0
    assert resposta.total_com_acao_humana == 0
    assert resposta.total_em_erro == 0
    assert resposta.lotes_recebidos_hoje == 1
    assert resposta.tempo_medio_na_etapa_segundos is not None
    assert resposta.documento_mais_antigo_pendente is not None


def test_resumo_esteira_limite_parado_negativo_e_filtro_invalido():
    fx = _montar_ctx()
    with pytest.raises(FiltroInvalido):
        obter_resumo_esteira(fx.ctx_api, SUJEITO_GESTOR, limite_parado_segundos=-1)


# ============================================================================
# 2. filtros combinados
# ============================================================================

def test_listar_documentos_filtros_combinados():
    fx = _montar_ctx()
    resumo_a = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'filtro combinado origem a', 'a.pdf', 'application/pdf')],
    )
    fx.servico_lote.criar_lote(
        'outra_origem', [ArquivoEntradaLote(b'filtro combinado origem b', 'b.pdf', 'application/pdf')],
    )

    filtro = FiltroDocumentos(
        origem='upload_manual', etapa=EtapaEsteira.REGISTRO, situacao=SituacaoEsteira.CONCLUIDO,
        bloqueado=False, acao_humana=False,
    )
    resposta = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro)

    assert resposta.total_itens == 1
    assert resposta.itens[0].documento_id == resumo_a.itens[0].documento_id


def test_listar_documentos_filtro_lote_e_tempo_minimo_parado():
    relogio = _RelogioControlavel(datetime(2026, 1, 1, tzinfo=timezone.utc))
    fx = _montar_ctx(relogio=relogio)
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'filtro por lote e tempo parado', 'a.pdf', 'application/pdf')],
    )
    relogio.avancar(3600)

    filtro = FiltroDocumentos(lote_id=resumo.lote_id, tempo_minimo_parado_segundos=1800)
    resposta = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro)
    assert resposta.total_itens == 1

    filtro_alto_demais = FiltroDocumentos(lote_id=resumo.lote_id, tempo_minimo_parado_segundos=7200)
    resposta_vazia = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro_alto_demais)
    assert resposta_vazia.total_itens == 0


def test_listar_documentos_filtro_recebido_de_ate():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'filtro por intervalo de recebimento', 'a.pdf', 'application/pdf')],
    )
    documento = fx.repo_docs.buscar_por_id(resumo.itens[0].documento_id)

    filtro_dentro = FiltroDocumentos(
        recebido_de=documento.recebido_em - timedelta(hours=1),
        recebido_ate=documento.recebido_em + timedelta(hours=1),
    )
    assert listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro_dentro).total_itens == 1

    filtro_fora = FiltroDocumentos(
        recebido_de=documento.recebido_em + timedelta(days=1),
        recebido_ate=documento.recebido_em + timedelta(days=2),
    )
    assert listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro_fora).total_itens == 0


# ============================================================================
# 3. paginacao
# ============================================================================

def test_listar_documentos_paginacao():
    fx = _montar_ctx()
    arquivos = [ArquivoEntradaLote(f'paginacao doc {i}'.encode(), f'{i}.pdf', 'application/pdf') for i in range(5)]
    fx.servico_lote.criar_lote('upload_manual', arquivos)

    pagina1 = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, paginacao=Paginacao(pagina=1, tamanho_pagina=2))
    assert pagina1.total_itens == 5
    assert pagina1.total_paginas == 3
    assert len(pagina1.itens) == 2

    pagina3 = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, paginacao=Paginacao(pagina=3, tamanho_pagina=2))
    assert len(pagina3.itens) == 1  # 5 itens, 2 por pagina -> ultima pagina com 1

    pagina_alem_do_fim = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, paginacao=Paginacao(pagina=4, tamanho_pagina=2))
    assert pagina_alem_do_fim.itens == ()
    assert pagina_alem_do_fim.total_itens == 5  # total nao muda so por pedir uma pagina alem do fim


# ============================================================================
# 4. ordenacao
# ============================================================================

def test_listar_documentos_ordenacao_segura():
    fx = _montar_ctx()
    arquivos = [ArquivoEntradaLote(f'ordenacao doc {i}'.encode(), f'{i}.pdf', 'application/pdf') for i in range(3)]
    fx.servico_lote.criar_lote('upload_manual', arquivos)

    asc = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, ordenacao=Ordenacao(campo='documento_id', direcao='asc'))
    desc = listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, ordenacao=Ordenacao(campo='documento_id', direcao='desc'))

    ids_asc = [item.documento_id for item in asc.itens]
    ids_desc = [item.documento_id for item in desc.itens]
    assert ids_asc == sorted(ids_asc)
    assert ids_desc == list(reversed(ids_asc))


def test_listar_documentos_ordenacao_campo_fora_da_allowlist_e_invalida():
    fx = _montar_ctx()
    with pytest.raises(OrdenacaoInvalida):
        listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, ordenacao=Ordenacao(campo='nome_original', direcao='asc'))


def test_listar_documentos_ordenacao_direcao_invalida():
    fx = _montar_ctx()
    with pytest.raises(OrdenacaoInvalida):
        listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, ordenacao=Ordenacao(campo='documento_id', direcao='lateral'))


def test_listar_lotes_ordenacao_e_paginacao():
    fx = _montar_ctx()
    fx.servico_lote.criar_lote('upload_manual', [ArquivoEntradaLote(b'lote 1', 'a.pdf', 'application/pdf')])
    fx.servico_lote.criar_lote('upload_manual', [ArquivoEntradaLote(b'lote 2', 'b.pdf', 'application/pdf')])

    resposta = listar_lotes(fx.ctx_api, SUJEITO_OPERACIONAL, ordenacao=Ordenacao(campo='criado_em', direcao='desc'))
    assert resposta.total_itens == 2
    assert len(resposta.itens) == 2


# ============================================================================
# 5. documento individual
# ============================================================================

def test_obter_documento_individual():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'documento individual', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id

    resposta = obter_documento(fx.ctx_api, SUJEITO_OPERACIONAL, documento_id)

    assert resposta.documento_id == documento_id
    assert resposta.nome_original == 'a.pdf'
    assert resposta.lote_id == resumo.lote_id
    assert resposta.origem == 'upload_manual'
    assert resposta.etapa_atual == 'REGISTRO'
    assert resposta.situacao == 'CONCLUIDO'
    assert resposta.rastreado_pela_esteira is True
    assert resposta.ultimo_evento is not None
    assert resposta.recebido_em is not None
    assert resposta.atualizado_em is not None


def test_obter_documento_legado_sem_esteira():
    fx = _montar_ctx()
    documento = fx.servico_entrada.registrar_entrada(
        b'documento legado sem esteira', 'legado.pdf', 'application/pdf', 'upload_manual',
    )

    resposta = obter_documento(fx.ctx_api, SUJEITO_OPERACIONAL, documento.documento_id)

    assert resposta.rastreado_pela_esteira is False
    assert resposta.etapa_atual is None
    assert resposta.situacao is None
    assert resposta.motivo_bloqueio is None
    assert resposta.proxima_acao is None
    assert resposta.atualizado_em is None


# ============================================================================
# 6. lote individual
# ============================================================================

def test_obter_lote_individual():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'lote individual', 'a.pdf', 'application/pdf')],
    )

    resposta = obter_lote(fx.ctx_api, SUJEITO_GESTOR, resumo.lote_id)

    assert resposta.lote_id == resumo.lote_id
    assert resposta.situacao == 'CONCLUIDO'
    assert resposta.quantidade_arquivos == 1
    assert resposta.origem == 'upload_manual'


# ============================================================================
# 7. historico
# ============================================================================

def test_obter_historico_documento():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'historico doc', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id

    resposta = obter_historico_documento(fx.ctx_api, SUJEITO_AUDITOR, documento_id)

    assert resposta.documento_id == documento_id
    assert resposta.total_eventos == len(resposta.eventos)
    assert resposta.total_eventos >= 2
    nomes_eventos = [e.evento for e in resposta.eventos]
    assert 'DOCUMENTO_RECEBIDO' in nomes_eventos
    assert 'DOCUMENTO_REGISTRADO' in nomes_eventos

    timestamps = [e.timestamp for e in resposta.eventos]
    assert timestamps == sorted(timestamps)  # ordenado cronologicamente


# ============================================================================
# 8. bloqueios
# ============================================================================

def test_listar_bloqueios():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'bloqueio doc', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id
    motivo = MotivoBloqueio(codigo='CPF_ILEGIVEL', descricao='CPF ilegivel no documento', detalhe_tecnico=None, resolvivel_automaticamente=False)
    fx.servico_avanco.registrar_bloqueio(documento_id, motivo, 'corr-1')

    resposta = listar_bloqueios(fx.ctx_api, SUJEITO_OPERACIONAL)

    assert resposta.total_itens == 1
    item = resposta.itens[0]
    assert item.documento_id == documento_id
    assert item.motivo_bloqueio.codigo == 'CPF_ILEGIVEL'
    assert item.tempo_bloqueado_segundos >= 0


def test_listar_bloqueios_vazio_quando_nada_bloqueado():
    fx = _montar_ctx()
    fx.servico_lote.criar_lote('upload_manual', [ArquivoEntradaLote(b'sem bloqueio', 'a.pdf', 'application/pdf')])

    resposta = listar_bloqueios(fx.ctx_api, SUJEITO_OPERACIONAL)
    assert resposta.total_itens == 0
    assert resposta.itens == ()


# ============================================================================
# 9. acoes humanas
# ============================================================================

def test_listar_acoes_humanas():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'acao humana doc', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id
    fx.servico_avanco.avancar_etapa(documento_id, EtapaEsteira.CLASSIFICACAO, 'corr-1')  # proxima acao HUMANA

    resposta = listar_acoes_humanas(fx.ctx_api, SUJEITO_GESTOR)

    ids_com_acao_humana = [item.documento_id for item in resposta.itens]
    assert documento_id in ids_com_acao_humana
    assert all(item.proxima_acao.tipo == 'HUMANA' for item in resposta.itens)


# ============================================================================
# 10. documentos parados
# ============================================================================

def test_listar_documentos_parados():
    relogio = _RelogioControlavel(datetime(2026, 1, 1, tzinfo=timezone.utc))
    fx = _montar_ctx(relogio=relogio)
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'documento parado', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id

    relogio.avancar(3600)

    resposta = listar_documentos_parados(fx.ctx_api, SUJEITO_OPERACIONAL, tempo_minimo_segundos=1800)
    assert documento_id in [item.documento_id for item in resposta.itens]

    resposta_vazia = listar_documentos_parados(fx.ctx_api, SUJEITO_OPERACIONAL, tempo_minimo_segundos=7200)
    assert resposta_vazia.total_itens == 0


def test_listar_documentos_parados_tempo_negativo_e_filtro_invalido():
    fx = _montar_ctx()
    with pytest.raises(FiltroInvalido):
        listar_documentos_parados(fx.ctx_api, SUJEITO_OPERACIONAL, tempo_minimo_segundos=-1)


# ============================================================================
# 11. autorizacao
# ============================================================================

def test_autorizacao_historico_exige_gestor_ou_auditor():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'autorizacao historico', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id

    with pytest.raises(PermissaoNegada):
        obter_historico_documento(fx.ctx_api, SUJEITO_OPERACIONAL, documento_id)

    obter_historico_documento(fx.ctx_api, SUJEITO_GESTOR, documento_id)
    obter_historico_documento(fx.ctx_api, SUJEITO_AUDITOR, documento_id)


def test_autorizacao_filas_operacionais_excluem_auditor():
    fx = _montar_ctx()
    with pytest.raises(PermissaoNegada):
        listar_bloqueios(fx.ctx_api, SUJEITO_AUDITOR)
    with pytest.raises(PermissaoNegada):
        listar_acoes_humanas(fx.ctx_api, SUJEITO_AUDITOR)

    listar_bloqueios(fx.ctx_api, SUJEITO_OPERACIONAL)
    listar_bloqueios(fx.ctx_api, SUJEITO_GESTOR)
    listar_acoes_humanas(fx.ctx_api, SUJEITO_OPERACIONAL)
    listar_acoes_humanas(fx.ctx_api, SUJEITO_GESTOR)


def test_autorizacao_leitura_geral_permite_todos_os_perfis():
    fx = _montar_ctx()
    for sujeito in (SUJEITO_OPERACIONAL, SUJEITO_GESTOR, SUJEITO_AUDITOR):
        obter_resumo_esteira(fx.ctx_api, sujeito)
        listar_documentos(fx.ctx_api, sujeito)
        listar_lotes(fx.ctx_api, sujeito)


def test_autorizacao_negada_carrega_perfis_permitidos_na_mensagem():
    fx = _montar_ctx()
    with pytest.raises(PermissaoNegada) as excinfo:
        listar_bloqueios(fx.ctx_api, SUJEITO_AUDITOR)
    assert 'AUDITOR' in str(excinfo.value)


# ============================================================================
# 12. erros
# ============================================================================

def test_erro_documento_nao_encontrado():
    fx = _montar_ctx()
    with pytest.raises(DocumentoNaoEncontrado):
        obter_documento(fx.ctx_api, SUJEITO_OPERACIONAL, 'documento-inexistente')


def test_erro_lote_nao_encontrado():
    fx = _montar_ctx()
    with pytest.raises(LoteNaoEncontrado):
        obter_lote(fx.ctx_api, SUJEITO_OPERACIONAL, 'lote-inexistente')


def test_erro_historico_documento_inexistente():
    fx = _montar_ctx()
    with pytest.raises(DocumentoNaoEncontrado):
        obter_historico_documento(fx.ctx_api, SUJEITO_GESTOR, 'documento-inexistente')


def test_erro_paginacao_invalida():
    fx = _montar_ctx()
    with pytest.raises(PaginacaoInvalida):
        listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, paginacao=Paginacao(pagina=0))
    with pytest.raises(PaginacaoInvalida):
        listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, paginacao=Paginacao(tamanho_pagina=0))
    with pytest.raises(PaginacaoInvalida):
        listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, paginacao=Paginacao(tamanho_pagina=99999))


def test_erro_filtro_invalido_intervalo_de_datas():
    fx = _montar_ctx()
    filtro = FiltroDocumentos(
        recebido_de=datetime(2026, 6, 1, tzinfo=timezone.utc),
        recebido_ate=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(FiltroInvalido):
        listar_documentos(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro)

    filtro_lotes = FiltroLotes(
        recebido_de=datetime(2026, 6, 1, tzinfo=timezone.utc),
        recebido_ate=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(FiltroInvalido):
        listar_lotes(fx.ctx_api, SUJEITO_OPERACIONAL, filtro=filtro_lotes)


def test_tratar_erro_para_resposta_mapeia_codigo_e_mensagem():
    resposta = tratar_erro_para_resposta(DocumentoNaoEncontrado('Documento nao encontrado: xyz'))
    assert resposta.codigo == 'DOCUMENTO_NAO_ENCONTRADO'
    assert resposta.mensagem == 'Documento nao encontrado: xyz'


# ============================================================================
# 13. serializacao JSON
# ============================================================================

def test_serializacao_json_de_todos_os_contratos():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'serializacao doc', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id
    motivo = MotivoBloqueio(codigo='X', descricao='motivo qualquer', detalhe_tecnico='detalhe', resolvivel_automaticamente=True)
    fx.servico_avanco.registrar_bloqueio(documento_id, motivo, 'corr-1')

    respostas = [
        obter_resumo_esteira(fx.ctx_api, SUJEITO_GESTOR),
        listar_lotes(fx.ctx_api, SUJEITO_GESTOR),
        obter_lote(fx.ctx_api, SUJEITO_GESTOR, resumo.lote_id),
        listar_documentos(fx.ctx_api, SUJEITO_GESTOR),
        obter_documento(fx.ctx_api, SUJEITO_GESTOR, documento_id),
        obter_historico_documento(fx.ctx_api, SUJEITO_GESTOR, documento_id),
        listar_bloqueios(fx.ctx_api, SUJEITO_GESTOR),
        listar_acoes_humanas(fx.ctx_api, SUJEITO_GESTOR),
        listar_documentos_parados(fx.ctx_api, SUJEITO_GESTOR, tempo_minimo_segundos=0),
        tratar_erro_para_resposta(DocumentoNaoEncontrado('teste')),
    ]
    for resposta in respostas:
        bruto = para_json(resposta)
        texto = json.dumps(bruto)  # nunca levanta TypeError
        recarregado = json.loads(texto)
        assert isinstance(recarregado, (dict, list))


def test_serializacao_json_preserva_valores_aninhados():
    fx = _montar_ctx()
    resumo = fx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(b'serializacao aninhada', 'a.pdf', 'application/pdf')],
    )
    documento_id = resumo.itens[0].documento_id
    motivo = MotivoBloqueio(codigo='Y', descricao='bloqueio aninhado', detalhe_tecnico=None, resolvivel_automaticamente=False)
    fx.servico_avanco.registrar_bloqueio(documento_id, motivo, 'corr-1')

    resposta = obter_documento(fx.ctx_api, SUJEITO_GESTOR, documento_id)
    bruto = para_json(resposta)

    assert bruto['documento_id'] == documento_id
    assert bruto['motivo_bloqueio']['codigo'] == 'Y'
    assert isinstance(bruto['motivo_bloqueio'], dict)


# ============================================================================
# 14. ausencia de vazamento de detalhes internos
# ============================================================================

def test_erro_interno_nao_vaza_detalhes_tecnicos():
    ctx_quebrado = ContextoApi(
        repositorio_documentos=_RepositorioDocumentosQueFalhaComSegredo(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados=RepositorioEstadosEsteiraEmMemoria(),
    )

    with pytest.raises(ErroInternoNaoExposto) as excinfo:
        obter_resumo_esteira(ctx_quebrado, SUJEITO_GESTOR)

    assert 'SUPER_SECRETO' not in str(excinfo.value)
    assert 'SUPER_SECRETO' not in excinfo.value.mensagem
    assert excinfo.value.mensagem == MENSAGEM_ERRO_INTERNO_PADRAO
    assert isinstance(excinfo.value.__cause__, ConnectionError)  # causa original encadeada, so para log

    resposta_erro = tratar_erro_para_resposta(excinfo.value)
    assert resposta_erro.codigo == 'ERRO_INTERNO'
    assert 'SUPER_SECRETO' not in resposta_erro.mensagem
    assert resposta_erro.detalhes is None

    bruto = para_json(resposta_erro)
    assert 'SUPER_SECRETO' not in json.dumps(bruto)


def test_erro_interno_nao_vaza_detalhes_em_listar_documentos():
    ctx_quebrado = ContextoApi(
        repositorio_documentos=_RepositorioDocumentosQueFalhaComSegredo(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados=RepositorioEstadosEsteiraEmMemoria(),
    )
    with pytest.raises(ErroInternoNaoExposto) as excinfo:
        listar_documentos(ctx_quebrado, SUJEITO_OPERACIONAL)
    assert 'SUPER_SECRETO' not in excinfo.value.mensagem
