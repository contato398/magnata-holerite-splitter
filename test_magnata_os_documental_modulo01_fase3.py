"""
Testes do Modulo 01 (Documental), Fase 3 -- lotes e esteira operacional.

Nenhum destes testes acessa Postgres, S3 ou Airtable reais -- tudo roda
contra os repositorios em memoria (Fase 1 e Fase 3).
"""
import collections
import threading
from datetime import datetime, timedelta, timezone

import pytest

from magnata_os.documental.modulo01.consultas_esteira import (
    documentos_bloqueados,
    documentos_com_acao_humana_pendente,
    documentos_parados_a_partir_de,
    documentos_por_etapa,
    documentos_por_situacao,
    lote_por_id,
    lotes_recentes,
    montar_resumo_esteira,
    ultimo_evento_e_proxima_acao,
)
from magnata_os.documental.modulo01.dominio_esteira import (
    AvancoBloqueadoPorPendencia,
    EtapaEsteira,
    MotivoBloqueio,
    SituacaoEsteira,
    TipoProximaAcao,
    TransicaoEtapaInvalida,
)
from magnata_os.documental.modulo01.dtos_esteira import montar_item_esteira
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import (
    EstadoEsteiraInexistente,
    NenhumBloqueioAtivo,
    ServicoAvancoEsteira,
    calcular_proxima_acao,
)
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote


# ============================================================================
# helpers
# ============================================================================

_Contexto = collections.namedtuple(
    '_Contexto',
    'repo_docs repo_hist repo_lotes repo_estados servico_entrada servico_avanco servico_lote',
)


class _RelogioControlavel:
    """Relogio falso, controlavel manualmente -- usado para testar
    calculo de tempo-na-etapa sem depender de sleep() real."""

    def __init__(self, inicio: datetime):
        self._agora = inicio

    def __call__(self) -> datetime:
        return self._agora

    def avancar(self, seconds: float) -> None:
        self._agora = self._agora + timedelta(seconds=seconds)


def _montar_servicos(relogio=None) -> _Contexto:
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    kwargs = {'relogio': relogio} if relogio is not None else {}
    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist, **kwargs)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist, **kwargs)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco, **kwargs)

    return _Contexto(repo_docs, repo_hist, repo_lotes, repo_estados, servico_entrada, servico_avanco, servico_lote)


def _criar_documento_registrado(ctx: _Contexto, conteudo: bytes, nome_original: str = 'doc.pdf') -> str:
    documento = ctx.servico_entrada.registrar_entrada(conteudo, nome_original, 'application/pdf', 'upload_manual')
    return documento.documento_id


# ============================================================================
# 1. lote com varios arquivos
# ============================================================================

def test_criar_lote_com_varios_arquivos_todos_sucesso():
    ctx = _montar_servicos()
    arquivos = [
        ArquivoEntradaLote(b'conteudo 1 do lote', 'a.pdf', 'application/pdf'),
        ArquivoEntradaLote(b'conteudo 2 do lote', 'b.pdf', 'application/pdf'),
        ArquivoEntradaLote(b'conteudo 3 do lote', 'c.pdf', 'application/pdf'),
    ]

    resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

    assert resumo.quantidade_arquivos == 3
    assert resumo.quantidade_sucesso == 3
    assert resumo.quantidade_duplicados == 0
    assert resumo.quantidade_erro == 0
    assert resumo.situacao == SituacaoEsteira.CONCLUIDO
    assert len(resumo.itens) == 3
    assert all(item.sucesso and not item.duplicado and item.erro is None for item in resumo.itens)

    lote = ctx.repo_lotes.buscar_por_id(resumo.lote_id)
    assert lote is not None
    assert lote.situacao == SituacaoEsteira.CONCLUIDO
    assert lote.quantidade_arquivos == 3

    documento_ids = {item.documento_id for item in resumo.itens}
    assert len(documento_ids) == 3  # 3 documentos distintos
    for item in resumo.itens:
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.REGISTRO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO
        assert estado.lote_id == resumo.lote_id


# ============================================================================
# 2. duplicidade no mesmo lote
# ============================================================================

def test_criar_lote_duplicidade_no_mesmo_lote_nao_aborta():
    ctx = _montar_servicos()
    conteudo = b'conteudo repetido dentro do mesmo lote'
    arquivos = [
        ArquivoEntradaLote(conteudo, 'original.pdf', 'application/pdf'),
        ArquivoEntradaLote(conteudo, 'copia.pdf', 'application/pdf'),
    ]

    resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

    assert resumo.quantidade_arquivos == 2
    assert resumo.quantidade_sucesso == 1
    assert resumo.quantidade_duplicados == 1
    assert resumo.quantidade_erro == 0
    assert resumo.situacao == SituacaoEsteira.CONCLUIDO  # duplicidade nao e erro
    assert resumo.itens[0].duplicado is False
    assert resumo.itens[1].duplicado is True
    assert resumo.itens[0].documento_id == resumo.itens[1].documento_id
    assert len(ctx.repo_estados.listar_todos()) == 1  # um unico EstadoEsteiraDocumento


# ============================================================================
# 3. duplicidade em lote anterior
# ============================================================================

def test_criar_lote_duplicidade_em_lote_anterior_preserva_lote_original():
    ctx = _montar_servicos()
    conteudo = b'conteudo reenviado num lote diferente'

    resumo1 = ctx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(conteudo, 'a.pdf', 'application/pdf')],
    )
    resumo2 = ctx.servico_lote.criar_lote(
        'upload_manual', [ArquivoEntradaLote(conteudo, 'a_reenviado.pdf', 'application/pdf')],
    )

    assert resumo2.itens[0].duplicado is True
    assert resumo2.itens[0].documento_id == resumo1.itens[0].documento_id

    estado = ctx.repo_estados.buscar_por_documento_id(resumo1.itens[0].documento_id)
    assert estado.lote_id == resumo1.lote_id  # NAO foi reatribuido ao lote 2
    assert estado.lote_id != resumo2.lote_id


# ============================================================================
# 4. falha isolada
# ============================================================================

def test_criar_lote_falha_isolada_nao_aborta_os_demais():
    ctx = _montar_servicos()
    arquivos = [
        ArquivoEntradaLote(b'', 'vazio.pdf', 'application/pdf'),  # ArquivoAusente
        ArquivoEntradaLote(b'conteudo valido no meio de uma falha', 'ok.pdf', 'application/pdf'),
    ]

    resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

    assert resumo.quantidade_arquivos == 2
    assert resumo.quantidade_sucesso == 1
    assert resumo.quantidade_erro == 1
    assert resumo.situacao == SituacaoEsteira.EM_REVISAO  # sucesso parcial
    assert resumo.itens[0].sucesso is False
    assert resumo.itens[0].documento_id is None
    assert resumo.itens[0].erro is not None
    assert resumo.itens[1].sucesso is True
    assert resumo.itens[1].erro is None


def test_criar_lote_todos_os_arquivos_falham_situacao_erro():
    ctx = _montar_servicos()
    arquivos = [
        ArquivoEntradaLote(b'', 'vazio1.pdf', 'application/pdf'),
        ArquivoEntradaLote(b'', 'vazio2.pdf', 'application/pdf'),
    ]

    resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

    assert resumo.quantidade_erro == 2
    assert resumo.quantidade_sucesso == 0
    assert resumo.situacao == SituacaoEsteira.ERRO


# ============================================================================
# 5. transicao valida / 6. transicao invalida
# ============================================================================

def test_avancar_etapa_transicao_valida():
    ctx = _montar_servicos()
    documento_id = _criar_documento_registrado(ctx, b'conteudo transicao valida')
    ctx.servico_avanco.criar_estado_inicial(documento_id, None, 'corr-1')
    ctx.servico_avanco.avancar_etapa(
        documento_id, EtapaEsteira.REGISTRO, 'corr-1', situacao_nova_etapa=SituacaoEsteira.CONCLUIDO,
    )

    novo_estado = ctx.servico_avanco.avancar_etapa(documento_id, EtapaEsteira.CLASSIFICACAO, 'corr-1')

    assert novo_estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
    assert novo_estado.situacao == SituacaoEsteira.AGUARDANDO


def test_avancar_etapa_transicao_invalida_levanta_excecao():
    ctx = _montar_servicos()
    documento_id = _criar_documento_registrado(ctx, b'conteudo transicao invalida')
    ctx.servico_avanco.criar_estado_inicial(documento_id, None, 'corr-1')  # etapa ENTRADA

    with pytest.raises(TransicaoEtapaInvalida):
        # pula etapas -- ENTRADA so pode ir para REGISTRO, nunca direto para AUDITORIA
        ctx.servico_avanco.avancar_etapa(documento_id, EtapaEsteira.AUDITORIA, 'corr-1')


def test_avancar_etapa_documento_sem_estado_levanta_excecao():
    ctx = _montar_servicos()
    with pytest.raises(EstadoEsteiraInexistente):
        ctx.servico_avanco.avancar_etapa('documento-inexistente', EtapaEsteira.REGISTRO, 'corr-1')


# ============================================================================
# 7. bloqueio impedindo avanco / 8. resolucao de bloqueio
# ============================================================================

def test_bloqueio_impede_avanco_de_etapa():
    ctx = _montar_servicos()
    documento_id = _criar_documento_registrado(ctx, b'conteudo com bloqueio')
    ctx.servico_avanco.criar_estado_inicial(documento_id, None, 'corr-1')

    motivo = MotivoBloqueio(
        codigo='CPF_ILEGIVEL', descricao='CPF ilegivel no documento',
        detalhe_tecnico=None, resolvivel_automaticamente=False,
    )
    estado_bloqueado = ctx.servico_avanco.registrar_bloqueio(documento_id, motivo, 'corr-1')
    assert estado_bloqueado.situacao == SituacaoEsteira.BLOQUEADO
    assert estado_bloqueado.motivo_bloqueio == motivo

    with pytest.raises(AvancoBloqueadoPorPendencia):
        ctx.servico_avanco.avancar_etapa(documento_id, EtapaEsteira.REGISTRO, 'corr-1')


def test_resolucao_de_bloqueio_permite_avanco_depois():
    ctx = _montar_servicos()
    documento_id = _criar_documento_registrado(ctx, b'conteudo resolucao de bloqueio')
    ctx.servico_avanco.criar_estado_inicial(documento_id, None, 'corr-1')

    motivo = MotivoBloqueio(
        codigo='ARQUIVO_CORROMPIDO', descricao='Arquivo corrompido na leitura',
        detalhe_tecnico='zlib.error: incomplete or truncated stream', resolvivel_automaticamente=True,
    )
    ctx.servico_avanco.registrar_bloqueio(documento_id, motivo, 'corr-1')

    resolvido = ctx.servico_avanco.resolver_bloqueio(documento_id, 'corr-1')
    assert resolvido.situacao == SituacaoEsteira.AGUARDANDO
    assert resolvido.motivo_bloqueio is None

    avancado = ctx.servico_avanco.avancar_etapa(documento_id, EtapaEsteira.REGISTRO, 'corr-1')
    assert avancado.etapa_atual == EtapaEsteira.REGISTRO


def test_resolver_bloqueio_sem_bloqueio_ativo_levanta_excecao():
    ctx = _montar_servicos()
    documento_id = _criar_documento_registrado(ctx, b'conteudo sem bloqueio ativo')
    ctx.servico_avanco.criar_estado_inicial(documento_id, None, 'corr-1')  # situacao CONCLUIDO, nunca bloqueado

    with pytest.raises(NenhumBloqueioAtivo):
        ctx.servico_avanco.resolver_bloqueio(documento_id, 'corr-1')


# ============================================================================
# 9. calculo de documentos parados
# ============================================================================

def test_documentos_parados_a_partir_de_calcula_corretamente():
    relogio = _RelogioControlavel(datetime(2026, 1, 1, tzinfo=timezone.utc))
    ctx = _montar_servicos(relogio=relogio)

    documento_id = _criar_documento_registrado(ctx, b'conteudo documento parado')
    ctx.servico_avanco.criar_estado_inicial(documento_id, None, 'corr-1')

    relogio.avancar(seconds=3600)  # 1h depois, ainda na mesma etapa

    parados_1800s = documentos_parados_a_partir_de(ctx.repo_estados, limite_segundos=1800, relogio=relogio)
    assert len(parados_1800s) == 1
    assert parados_1800s[0].documento_id == documento_id

    parados_7200s = documentos_parados_a_partir_de(ctx.repo_estados, limite_segundos=7200, relogio=relogio)
    assert parados_7200s == []


# ============================================================================
# 10. proxima acao automatica / 11. proxima acao humana
# ============================================================================

def test_proxima_acao_automatica_para_entrada_e_registro():
    acao_entrada = calcular_proxima_acao(EtapaEsteira.ENTRADA, SituacaoEsteira.CONCLUIDO)
    acao_registro = calcular_proxima_acao(EtapaEsteira.REGISTRO, SituacaoEsteira.CONCLUIDO)

    assert acao_entrada.tipo == TipoProximaAcao.AUTOMATICA
    assert acao_registro.tipo == TipoProximaAcao.AUTOMATICA


def test_proxima_acao_humana_para_etapas_futuras_e_em_revisao():
    acao_classificacao = calcular_proxima_acao(EtapaEsteira.CLASSIFICACAO, SituacaoEsteira.AGUARDANDO)
    assert acao_classificacao.tipo == TipoProximaAcao.HUMANA

    acao_em_revisao = calcular_proxima_acao(EtapaEsteira.REGISTRO, SituacaoEsteira.EM_REVISAO)
    assert acao_em_revisao.tipo == TipoProximaAcao.HUMANA


def test_proxima_acao_bloqueio_resolvivel_automaticamente_e_automatica():
    motivo = MotivoBloqueio('X', 'desc', None, resolvivel_automaticamente=True)
    acao = calcular_proxima_acao(EtapaEsteira.CLASSIFICACAO, SituacaoEsteira.BLOQUEADO, motivo)
    assert acao.tipo == TipoProximaAcao.AUTOMATICA


def test_proxima_acao_auditoria_concluida_e_terminal():
    acao = calcular_proxima_acao(EtapaEsteira.AUDITORIA, SituacaoEsteira.CONCLUIDO)
    assert acao is None


# ============================================================================
# 12. compatibilidade com documento legado
# ============================================================================

def test_documento_legado_sem_estado_esteira_e_tratado_explicitamente():
    ctx = _montar_servicos()
    # Documento criado diretamente via ServicoEntradaDocumental (Fase 1),
    # sem passar por ServicoCriacaoLote -- simula um documento anterior
    # a Fase 3, sem lote_id e sem EstadoEsteiraDocumento.
    documento = ctx.servico_entrada.registrar_entrada(
        b'conteudo documento legado sem esteira', 'legado.pdf', 'application/pdf', 'upload_manual',
    )
    assert documento.lote_id is None

    estado = ctx.repo_estados.buscar_por_documento_id(documento.documento_id)
    assert estado is None

    item = montar_item_esteira(documento, estado, agora=datetime.now(timezone.utc))
    assert item.rastreado_pela_esteira is False
    assert item.documento_id == documento.documento_id
    assert item.lote_id is None
    assert item.etapa_atual is None
    assert item.situacao is None
    assert item.motivo_bloqueio is None
    assert item.proxima_acao is None
    assert item.tempo_na_etapa_segundos is None

    ids_em_entrada = {e.documento_id for e in documentos_por_etapa(ctx.repo_estados, EtapaEsteira.ENTRADA)}
    assert documento.documento_id not in ids_em_entrada


# ============================================================================
# 13. concorrencia na criacao de lotes
# ============================================================================

def test_concorrencia_na_criacao_de_lotes_mesmo_conteudo():
    ctx = _montar_servicos()
    conteudo = b'conteudo concorrente entre varios lotes simultaneos'
    n = 15
    barreira = threading.Barrier(n)
    resumos = []
    lock = threading.Lock()

    def _tentar():
        barreira.wait(timeout=5)
        resumo = ctx.servico_lote.criar_lote(
            'upload_manual', [ArquivoEntradaLote(conteudo, 'concorrente.pdf', 'application/pdf')],
        )
        with lock:
            resumos.append(resumo)

    threads = [threading.Thread(target=_tentar) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(resumos) == n
    documento_ids = {r.itens[0].documento_id for r in resumos}
    assert len(documento_ids) == 1  # todos os lotes apontam para o MESMO documento

    quantidade_nao_duplicados = sum(1 for r in resumos if not r.itens[0].duplicado)
    quantidade_duplicados = sum(1 for r in resumos if r.itens[0].duplicado)
    assert quantidade_nao_duplicados == 1
    assert quantidade_duplicados == n - 1

    (documento_id,) = documento_ids
    assert len(ctx.repo_estados.listar_todos()) == 1  # um unico EstadoEsteiraDocumento, sem duplicar


# ============================================================================
# consultas -- cobertura adicional
# ============================================================================

def test_documentos_bloqueados_retorna_apenas_bloqueados():
    ctx = _montar_servicos()
    doc_livre = _criar_documento_registrado(ctx, b'documento livre')
    doc_bloqueado = _criar_documento_registrado(ctx, b'documento bloqueado')
    ctx.servico_avanco.criar_estado_inicial(doc_livre, None, 'corr-1')
    ctx.servico_avanco.criar_estado_inicial(doc_bloqueado, None, 'corr-1')
    motivo = MotivoBloqueio('X', 'motivo qualquer', None, False)
    ctx.servico_avanco.registrar_bloqueio(doc_bloqueado, motivo, 'corr-1')

    bloqueados = documentos_bloqueados(ctx.repo_estados)
    assert {e.documento_id for e in bloqueados} == {doc_bloqueado}


def test_documentos_com_acao_humana_pendente():
    ctx = _montar_servicos()
    doc_id = _criar_documento_registrado(ctx, b'documento pendente de humano')
    ctx.servico_avanco.criar_estado_inicial(doc_id, None, 'corr-1')
    ctx.servico_avanco.avancar_etapa(doc_id, EtapaEsteira.REGISTRO, 'corr-1', situacao_nova_etapa=SituacaoEsteira.CONCLUIDO)
    ctx.servico_avanco.avancar_etapa(doc_id, EtapaEsteira.CLASSIFICACAO, 'corr-1')  # proxima acao HUMANA

    pendentes = documentos_com_acao_humana_pendente(ctx.repo_estados)
    assert doc_id in {e.documento_id for e in pendentes}


def test_ultimo_evento_e_proxima_acao():
    ctx = _montar_servicos()
    doc_id = _criar_documento_registrado(ctx, b'documento com historico')
    ctx.servico_avanco.criar_estado_inicial(doc_id, None, 'corr-1')

    ultimo_evento, proxima_acao_dto = ultimo_evento_e_proxima_acao(ctx.repo_hist, ctx.repo_estados, doc_id)

    assert ultimo_evento is not None
    assert proxima_acao_dto is not None
    assert proxima_acao_dto.tipo == TipoProximaAcao.AUTOMATICA  # etapa ENTRADA


def test_lotes_recentes_ordenado_mais_novo_primeiro():
    ctx = _montar_servicos()
    resumo1 = ctx.servico_lote.criar_lote('upload_manual', [ArquivoEntradaLote(b'lote 1', 'a.pdf', 'application/pdf')])
    resumo2 = ctx.servico_lote.criar_lote('upload_manual', [ArquivoEntradaLote(b'lote 2', 'b.pdf', 'application/pdf')])

    recentes = lotes_recentes(ctx.repo_lotes, limite=10)
    assert [l.lote_id for l in recentes][:2] == [resumo2.lote_id, resumo1.lote_id]


def test_lote_por_id():
    ctx = _montar_servicos()
    resumo = ctx.servico_lote.criar_lote('upload_manual', [ArquivoEntradaLote(b'lote unico', 'a.pdf', 'application/pdf')])

    lote = lote_por_id(ctx.repo_lotes, resumo.lote_id)
    assert lote is not None
    assert lote.lote_id == resumo.lote_id
    assert lote_por_id(ctx.repo_lotes, 'inexistente') is None


def test_documentos_por_situacao():
    ctx = _montar_servicos()
    doc_id = _criar_documento_registrado(ctx, b'documento por situacao')
    ctx.servico_avanco.criar_estado_inicial(doc_id, None, 'corr-1')

    concluidos = documentos_por_situacao(ctx.repo_estados, SituacaoEsteira.CONCLUIDO)
    aguardando = documentos_por_situacao(ctx.repo_estados, SituacaoEsteira.AGUARDANDO)
    assert doc_id in {e.documento_id for e in concluidos}
    assert doc_id not in {e.documento_id for e in aguardando}


def test_montar_resumo_esteira_agrega_corretamente():
    ctx = _montar_servicos()
    ctx.servico_lote.criar_lote('upload_manual', [
        ArquivoEntradaLote(b'agregado 1', 'a.pdf', 'application/pdf'),
        ArquivoEntradaLote(b'agregado 2', 'b.pdf', 'application/pdf'),
    ])

    resumo = montar_resumo_esteira(ctx.repo_estados)
    assert resumo.total_documentos_rastreados == 2
    assert resumo.por_etapa.get(EtapaEsteira.REGISTRO) == 2
    assert resumo.por_situacao.get(SituacaoEsteira.CONCLUIDO) == 2
    assert resumo.total_bloqueados == 0
