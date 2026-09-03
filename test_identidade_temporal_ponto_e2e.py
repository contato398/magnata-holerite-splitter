"""Prova de composição SINTÉTICA, sem produção (missão "IDENTIDADE
TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1"):

    PDF/texto sintético
    -> Documento (Modulo 01, já existente)
    -> hash (já existente, salvar_se_ausente_por_hash)
    -> extração do período (extracao_periodo_documental_ponto.py, novo)
    -> competência (resolucao_temporal_ponto.py, novo)
    -> resolução do colaborador -> cliente(s) via alocação histórica
       sintética (resolucao_temporal_ponto.py, novo)
    -> resolução temporal (ResolucaoDocumentalTemporalPonto, novo)
    -> persistência em repositório de teste (RepositorioResolucaoTemporalEmMemoria,
       novo) + evento de auditoria (EventoHistorico, já existente)
    -> leitura de volta
    -> transformação para ItemInventarioPrestacao (já existente, motor
       de completude reaproveitado sem alteração)

Nenhuma escrita real (Airtable/Postgres/produção). Nenhum nome real/CPF
real."""
import ast
import datetime
import inspect

import pytest

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO
from magnata_os.classificacao.resolucao_temporal_ponto import (
    AlocacaoHistorica,
    TransicaoResolucaoTemporal,
    resolver_documento_ponto,
)
from magnata_os.documental.modulo01 import dominio as modulo_dominio
from magnata_os.documental.modulo01.dominio import (
    EventoHistorico,
    StatusDocumento,
    gerar_correlation_id,
    gerar_documento_id,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_resolucao_temporal import (
    FalhaAuditoriaResolucaoTemporal,
    RepositorioResolucaoTemporalEmMemoria,
)


class _FonteAlocacaoEmMemoria:
    def __init__(self, alocacoes):
        self._alocacoes = tuple(alocacoes)

    def listar_para_colaborador(self, colaborador_id: str):
        return tuple(a for a in self._alocacoes if a.colaborador_id == colaborador_id)


def _texto_cartao_ponto(periodo_inicio_txt: str, periodo_fim_txt: str) -> str:
    return (
        f'CARTAO DE PONTO\nFuncionario: Sintetico\n'
        f'Período: {periodo_inicio_txt} até {periodo_fim_txt}\n'
        f'29/05/26 - Sex - C1 08:00 12:00 13:00 17:00'
    )


def _registrar_documento(repo_docs, conteudo: bytes, origem: str = 'teste-sintetico'):
    agora = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)

    def _fabricar():
        import hashlib
        return modulo_dominio.Documento(
            documento_id=gerar_documento_id(),
            arquivo_original=f'pendente-armazenamento://{hashlib.sha256(conteudo).hexdigest()}',
            nome_original='cartao_ponto_sintetico.pdf',
            mime_type='application/pdf',
            tamanho=len(conteudo),
            hash_sha256=hashlib.sha256(conteudo).hexdigest(),
            origem=origem,
            recebido_em=agora,
            lote_id=None,
            status=StatusDocumento.RECEBIDO,
            correlation_id=gerar_correlation_id(),
            criado_em=agora,
            atualizado_em=agora,
        )

    import hashlib
    documento, criado = repo_docs.salvar_se_ausente_por_hash(hashlib.sha256(conteudo).hexdigest(), _fabricar)
    return documento, criado


_NOMES_EVENTO_POR_TRANSICAO = {
    'NOVA': 'RESOLUCAO_TEMPORAL_PONTO_REGISTRADA',
    'ATUALIZACAO': 'RESOLUCAO_TEMPORAL_PONTO_ATUALIZADA',
    'CONFLITO': 'RESOLUCAO_TEMPORAL_PONTO_DIVERGENTE',
}


def _fabricar_evento(transicao, anterior, novo) -> EventoHistorico:
    """Fábrica de evento usada pelos testes -- reflete a transição
    classificada pelo repositório, preservando anterior/novo nos
    detalhes (nunca um evento genérico que esconda o que mudou)."""
    agora = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)
    detalhes = {
        'competencia_anterior': (
            anterior.resolucao_competencia.valores_confirmados[0].entidade_id
            if anterior and anterior.resolucao_competencia.valores_confirmados else None
        ),
        'competencia_nova': (
            novo.resolucao_competencia.valores_confirmados[0].entidade_id
            if novo.resolucao_competencia.valores_confirmados else None
        ),
    }
    return EventoHistorico(
        documento_id=novo.documento_id, evento=_NOMES_EVENTO_POR_TRANSICAO[transicao.value],
        status_anterior=None, status_novo=None, timestamp=agora,
        correlation_id=gerar_correlation_id(), detalhes=detalhes,
    )


# ---------------------------------------------------------------------------
# Casos 1-2: períodos válidos -> competência correta
# ---------------------------------------------------------------------------

def test_caso1_periodo_29_05_a_28_06_resolve_competencia_junho():
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao, _cliente = resolver_documento_ponto('doc-1', texto, 'func-1', _FonteAlocacaoEmMemoria(()))
    assert resolucao.resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao.resolucao_competencia.valores_confirmados == (
        ReferenciaCanonica('COMPETENCIA', '2026-06'),
    )
    assert resolucao.periodo_inicio == datetime.date(2026, 5, 29)
    assert resolucao.periodo_fim == datetime.date(2026, 6, 28)


def test_caso2_periodo_29_06_a_28_07_resolve_competencia_julho():
    texto = _texto_cartao_ponto('29/06/2026', '28/07/2026')
    resolucao, _cliente = resolver_documento_ponto('doc-2', texto, 'func-1', _FonteAlocacaoEmMemoria(()))
    assert resolucao.resolucao_competencia.valores_confirmados == (
        ReferenciaCanonica('COMPETENCIA', '2026-07'),
    )


# ---------------------------------------------------------------------------
# Caso 3: PDF sem período
# ---------------------------------------------------------------------------

def test_caso3_pdf_sem_periodo_fica_nao_encontrada():
    texto = 'CARTAO DE PONTO sem periodo declarado nenhum'
    resolucao, resolucao_cliente = resolver_documento_ponto('doc-3', texto, 'func-1', _FonteAlocacaoEmMemoria(()))
    assert resolucao.resolucao_competencia.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resolucao.periodo_inicio is None and resolucao.periodo_fim is None
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.NAO_AVALIADA


# ---------------------------------------------------------------------------
# Caso 4: período inválido (invertido)
# ---------------------------------------------------------------------------

def test_caso4_periodo_invertido_fica_nao_encontrada():
    texto = _texto_cartao_ponto('28/06/2026', '29/05/2026')  # invertido
    resolucao, _cliente = resolver_documento_ponto('doc-4', texto, 'func-1', _FonteAlocacaoEmMemoria(()))
    assert resolucao.resolucao_competencia.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


# ---------------------------------------------------------------------------
# Caso 5: mesmo documento/hash reapresentado -> idempotência
# ---------------------------------------------------------------------------

def test_caso5_mesmo_hash_reapresentado_nunca_duplica_documento_nem_resolucao():
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)
    conteudo = b'%PDF-1.7 cartao ponto sintetico caso5'

    documento_1, criado_1 = _registrar_documento(repo_docs, conteudo)
    documento_2, criado_2 = _registrar_documento(repo_docs, conteudo)  # reapresentado
    assert criado_1 is True
    assert criado_2 is False
    assert documento_1.documento_id == documento_2.documento_id

    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao, _cliente = resolver_documento_ponto(documento_1.documento_id, texto, 'func-1', _FonteAlocacaoEmMemoria(()))
    transicao_1 = repo_resolucao.salvar_com_evento(resolucao, _fabricar_evento)
    # Reprocessar o MESMO documento_id com a MESMA resolução -- EQUIVALENTE
    # (idempotência real: nenhuma escrita nova, nenhum evento novo).
    transicao_2 = repo_resolucao.salvar_com_evento(resolucao, _fabricar_evento)

    assert transicao_1 == TransicaoResolucaoTemporal.NOVA
    assert transicao_2 == TransicaoResolucaoTemporal.EQUIVALENTE
    assert len(repo_resolucao.listar_todos()) == 1
    assert len(repo_docs.listar_todos()) == 1
    assert len(repo_historico.listar_por_documento(documento_1.documento_id)) == 1  # so 1 evento, nunca 2


# ---------------------------------------------------------------------------
# Reprocessamento: equivalente / atualização legítima / conflito real
# (revisão independente pós-PR #127 -- gate de reprocessamento)
# ---------------------------------------------------------------------------

def test_reprocessamento_equivalente_e_idempotente_sem_evento_novo():
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao, _c = resolver_documento_ponto('doc-reproc-1', texto, 'func-r1', _FonteAlocacaoEmMemoria(()))

    t1 = repo_resolucao.salvar_com_evento(resolucao, _fabricar_evento)
    t2 = repo_resolucao.salvar_com_evento(resolucao, _fabricar_evento)  # mesmo resultado, reprocessado

    assert t1 == TransicaoResolucaoTemporal.NOVA
    assert t2 == TransicaoResolucaoTemporal.EQUIVALENTE
    assert len(repo_historico.listar_por_documento('doc-reproc-1')) == 1
    assert repo_resolucao.buscar_por_documento_id('doc-reproc-1') == resolucao


def test_reprocessamento_correcao_legitima_nao_encontrada_para_resolvida_e_atualizacao():
    """Primeira extração falhou (sem período); reprocessamento com um
    extrator corrigido agora encontra o período -- isso é uma CORREÇÃO
    legítima, nunca uma disputa (não há 2 valores RESOLVIDA
    conflitantes) -- ATUALIZACAO, nunca CONFLITO."""
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)

    resolucao_sem_periodo, _c = resolver_documento_ponto(
        'doc-reproc-2', 'texto sem periodo declarado', 'func-r2', _FonteAlocacaoEmMemoria(()),
    )
    t1 = repo_resolucao.salvar_com_evento(resolucao_sem_periodo, _fabricar_evento)
    assert t1 == TransicaoResolucaoTemporal.NOVA
    assert resolucao_sem_periodo.resolucao_competencia.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA

    texto_corrigido = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao_corrigida, _c2 = resolver_documento_ponto(
        'doc-reproc-2', texto_corrigido, 'func-r2', _FonteAlocacaoEmMemoria(()),
    )
    t2 = repo_resolucao.salvar_com_evento(resolucao_corrigida, _fabricar_evento)

    assert t2 == TransicaoResolucaoTemporal.ATUALIZACAO
    persistida = repo_resolucao.buscar_por_documento_id('doc-reproc-2')
    assert persistida.resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert persistida.resolucao_competencia.valores_confirmados == (
        ReferenciaCanonica('COMPETENCIA', '2026-06'),
    )
    eventos = repo_historico.listar_por_documento('doc-reproc-2')
    assert len(eventos) == 2  # NOVA + ATUALIZACAO -- historico completo preservado
    assert eventos[1].detalhes['competencia_anterior'] is None
    assert eventos[1].detalhes['competencia_nova'] == '2026-06'


def test_reprocessamento_divergente_vira_conflito_nunca_escolhe_um_valor_sozinho():
    """2 extrações CONFIANTES (RESOLVIDA) mas com competências
    DIFERENTES -- disputa real. O sistema NUNCA decide sozinho qual
    prevalece: rebaixa a competência persistida para CONFLITO e limpa o
    período -- mas preserva OS DOIS valores no evento de auditoria."""
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)

    texto_junho = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao_junho, _c = resolver_documento_ponto('doc-reproc-3', texto_junho, 'func-r3', _FonteAlocacaoEmMemoria(()))
    repo_resolucao.salvar_com_evento(resolucao_junho, _fabricar_evento)

    texto_julho = _texto_cartao_ponto('29/06/2026', '28/07/2026')
    resolucao_julho, _c2 = resolver_documento_ponto('doc-reproc-3', texto_julho, 'func-r3', _FonteAlocacaoEmMemoria(()))
    transicao = repo_resolucao.salvar_com_evento(resolucao_julho, _fabricar_evento)

    assert transicao == TransicaoResolucaoTemporal.CONFLITO
    persistida = repo_resolucao.buscar_por_documento_id('doc-reproc-3')
    assert persistida.resolucao_competencia.estado == EstadoResolucaoDimensao.CONFLITO
    assert persistida.resolucao_competencia.valores_confirmados == ()  # nunca escolhe um dos dois
    assert persistida.periodo_inicio is None and persistida.periodo_fim is None  # nao confiavel em disputa

    eventos = repo_historico.listar_por_documento('doc-reproc-3')
    assert len(eventos) == 2
    assert eventos[1].evento == 'RESOLUCAO_TEMPORAL_PONTO_DIVERGENTE'
    assert eventos[1].detalhes['competencia_anterior'] == '2026-06'  # preservado, nunca perdido
    assert eventos[1].detalhes['competencia_nova'] == '2026-07'  # preservado, nunca perdido


def test_reprocessamento_e_deterministico():
    repo_historico_1 = RepositorioHistoricoEmMemoria()
    repo_resolucao_1 = RepositorioResolucaoTemporalEmMemoria(repo_historico_1)
    repo_historico_2 = RepositorioHistoricoEmMemoria()
    repo_resolucao_2 = RepositorioResolucaoTemporalEmMemoria(repo_historico_2)

    texto_junho = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    texto_julho = _texto_cartao_ponto('29/06/2026', '28/07/2026')
    resolucao_junho, _c = resolver_documento_ponto('doc-det', texto_junho, 'func-det', _FonteAlocacaoEmMemoria(()))
    resolucao_julho, _c2 = resolver_documento_ponto('doc-det', texto_julho, 'func-det', _FonteAlocacaoEmMemoria(()))

    for repo in (repo_resolucao_1, repo_resolucao_2):
        repo.salvar_com_evento(resolucao_junho, _fabricar_evento)
        transicao = repo.salvar_com_evento(resolucao_julho, _fabricar_evento)
        assert transicao == TransicaoResolucaoTemporal.CONFLITO

    assert repo_resolucao_1.buscar_por_documento_id('doc-det') == repo_resolucao_2.buscar_por_documento_id('doc-det')


# ---------------------------------------------------------------------------
# Casos 6-9: resolução de cliente por alocação histórica
# ---------------------------------------------------------------------------

def test_caso6_colaborador_sem_alocacao_fica_nao_encontrada():
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    _resolucao, resolucao_cliente = resolver_documento_ponto(
        'doc-6', texto, 'func-sem-alocacao', _FonteAlocacaoEmMemoria(()),
    )
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resolucao_cliente.valores_confirmados == ()


def test_caso7_uma_alocacao_resolve_1_cliente():
    alocacoes = (AlocacaoHistorica('func-7', 'cliente-A', datetime.date(2026, 1, 1), None),)
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    _resolucao, resolucao_cliente = resolver_documento_ponto(
        'doc-7', texto, 'func-7', _FonteAlocacaoEmMemoria(alocacoes),
    )
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_cliente.valores_confirmados == (ReferenciaCanonica('CLIENTE', 'cliente-A'),)


def test_caso8_transferencia_entre_dois_clientes_dentro_do_periodo():
    alocacoes = (
        AlocacaoHistorica('func-8', 'cliente-A', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10)),
        AlocacaoHistorica('func-8', 'cliente-B', datetime.date(2026, 6, 11), None),
    )
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    _resolucao, resolucao_cliente = resolver_documento_ponto(
        'doc-8', texto, 'func-8', _FonteAlocacaoEmMemoria(alocacoes),
    )
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert set(resolucao_cliente.valores_confirmados) == {
        ReferenciaCanonica('CLIENTE', 'cliente-A'), ReferenciaCanonica('CLIENTE', 'cliente-B'),
    }
    assert len(resolucao_cliente.valores_confirmados) == 2


def test_caso9_ordem_deterministica_dos_multiplos_vinculos():
    alocacoes_ordem_1 = (
        AlocacaoHistorica('func-9', 'cliente-Z', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10)),
        AlocacaoHistorica('func-9', 'cliente-A', datetime.date(2026, 6, 11), None),
    )
    alocacoes_ordem_2 = (  # mesmas alocações, ordem de entrada invertida
        AlocacaoHistorica('func-9', 'cliente-A', datetime.date(2026, 6, 11), None),
        AlocacaoHistorica('func-9', 'cliente-Z', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10)),
    )
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    _r1, cliente_1 = resolver_documento_ponto('doc-9a', texto, 'func-9', _FonteAlocacaoEmMemoria(alocacoes_ordem_1))
    _r2, cliente_2 = resolver_documento_ponto('doc-9b', texto, 'func-9', _FonteAlocacaoEmMemoria(alocacoes_ordem_2))
    assert cliente_1.valores_confirmados == cliente_2.valores_confirmados  # mesma ordem, independente da entrada


# ---------------------------------------------------------------------------
# Caso 10: falha de auditoria força rollback de TODA a mutação
# ---------------------------------------------------------------------------

def test_caso10_falha_de_auditoria_reverte_a_resolucao_documento_novo():
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)
    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao, _cliente = resolver_documento_ponto('doc-10', texto, 'func-10', _FonteAlocacaoEmMemoria(()))

    def _fabricar_evento_com_falha(transicao, anterior, novo):
        raise RuntimeError('falha simulada de auditoria')

    with pytest.raises(FalhaAuditoriaResolucaoTemporal):
        repo_resolucao.salvar_com_evento(resolucao, _fabricar_evento_com_falha)

    assert repo_resolucao.buscar_por_documento_id('doc-10') is None  # nunca ficou salvo sozinho
    assert repo_historico.listar_por_documento('doc-10') == []


def test_caso10b_falha_de_auditoria_reverte_para_o_estado_anterior_documento_ja_existente():
    """Documento JÁ tinha uma resolução anterior; uma nova tentativa que
    falha na auditoria deve restaurar a resolução ANTERIOR -- nunca
    deixar o estado novo (não-auditado) visível."""
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)
    texto_original = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    resolucao_original, _c = resolver_documento_ponto('doc-10b', texto_original, 'func-10b', _FonteAlocacaoEmMemoria(()))
    repo_resolucao.salvar_com_evento(resolucao_original, _fabricar_evento)

    texto_novo = _texto_cartao_ponto('29/06/2026', '28/07/2026')
    resolucao_nova, _c2 = resolver_documento_ponto('doc-10b', texto_novo, 'func-10b', _FonteAlocacaoEmMemoria(()))

    def _fabricar_evento_com_falha(transicao, anterior, novo):
        raise RuntimeError('falha simulada de auditoria na atualizacao')

    with pytest.raises(FalhaAuditoriaResolucaoTemporal):
        repo_resolucao.salvar_com_evento(resolucao_nova, _fabricar_evento_com_falha)

    restaurada = repo_resolucao.buscar_por_documento_id('doc-10b')
    assert restaurada == resolucao_original  # nunca ficou com a resolucao nova nao-auditada


# ---------------------------------------------------------------------------
# Pipeline ponta-a-ponta completo + transformação para o corredor existente
# ---------------------------------------------------------------------------

def test_pipeline_completo_documento_ate_item_inventario_prestacao():
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_resolucao = RepositorioResolucaoTemporalEmMemoria(repo_historico)

    conteudo = b'%PDF-1.7 cartao ponto sintetico pipeline completo'
    documento, criado = _registrar_documento(repo_docs, conteudo)
    assert criado is True

    texto = _texto_cartao_ponto('29/05/2026', '28/06/2026')
    alocacoes = (AlocacaoHistorica('func-pipeline', 'cliente-pipeline', datetime.date(2026, 1, 1), None),)
    resolucao, resolucao_cliente = resolver_documento_ponto(
        documento.documento_id, texto, 'func-pipeline', _FonteAlocacaoEmMemoria(alocacoes),
    )
    repo_resolucao.salvar_com_evento(resolucao, _fabricar_evento)

    # Leitura de volta
    lida = repo_resolucao.buscar_por_documento_id(documento.documento_id)
    assert lida == resolucao
    eventos = repo_historico.listar_por_documento(documento.documento_id)
    assert len(eventos) == 1 and eventos[0].evento == 'RESOLUCAO_TEMPORAL_PONTO_REGISTRADA'

    # Transformação para o corredor documental JÁ EXISTENTE (motor de
    # completude reaproveitado sem alteração) -- só possível quando
    # cliente resolveu com exatamente 1 valor (múltiplos exigiria 1 item
    # por cliente, mesma semântica de itens_para_multiplos_clientes_do_
    # vinculo, já existente -- fora do escopo mínimo desta prova).
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert len(resolucao_cliente.valores_confirmados) == 1
    item = ItemInventarioPrestacao(
        documento_id=lida.documento_id,
        tipo_documental=lida.tipo_documental,
        cliente=resolucao_cliente.valores_confirmados[0],
        competencia=resolucao.resolucao_competencia.valores_confirmados[0],
        colaborador=ReferenciaCanonica('COLABORADOR', lida.colaborador_id),
    )
    assert item.tipo_documental == TIPO_FOLHA_DE_PONTO
    assert item.cliente == ReferenciaCanonica('CLIENTE', 'cliente-pipeline')
    assert item.competencia == ReferenciaCanonica('COMPETENCIA', '2026-06')


# ---------------------------------------------------------------------------
# Casos 11-12: isolamento (AST)
# ---------------------------------------------------------------------------

_MODULOS_NUCLEO_NOVO = (
    'magnata_os.classificacao.extracao_periodo_documental_ponto',
    'magnata_os.classificacao.resolucao_temporal_ponto',
    'magnata_os.documental.modulo01.repositorio_resolucao_temporal',
)


def test_caso11_e_12_nucleo_novo_nunca_importa_airtable_requests_ou_app_py():
    import importlib
    for nome_modulo in _MODULOS_NUCLEO_NOVO:
        modulo = importlib.import_module(nome_modulo)
        codigo_fonte = inspect.getsource(modulo)
        arvore = ast.parse(codigo_fonte)
        for no in ast.walk(arvore):
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                nomes = [no.module] if isinstance(no, ast.ImportFrom) else [a.name for a in no.names]
                for nome in nomes:
                    if not nome:
                        continue
                    proibido = (
                        nome.lower() == 'requests'
                        or 'airtable' in nome.lower()
                        or nome == 'app'
                        or nome.startswith('app.')
                    )
                    assert not proibido, f'{nome_modulo}: import proibido {nome!r}'
