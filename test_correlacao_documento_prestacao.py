"""J3 -- índice de correlação Documento interno ↔ escopo da Prestação.

Unitários (sem banco): decisão de observações, twin em memória (mesma
decisão do adapter Postgres), produtores (corredor e ponto temporal),
consumidor (candidatos por necessidade), destinatário organizacional
(bridge Airtable read-only), backfill e composition root. Dados
sintéticos; nenhum dado pessoal; nenhuma rede.
"""
import dataclasses
import datetime as dt
import io
import logging
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.correlacao_documento_prestacao import (
    EVENTO_RELACAO_DOCUMENTO_DERIVADO_IGNORADA,
    ORIGEM_CORREDOR_PRESTACAO,
    ORIGEM_RESOLUCAO_TEMPORAL_PONTO,
    CorrelacaoDocumentoPrestacaoError,
    DocumentoInexistenteNaCorrelacao,
    EstadoCorrelacao,
    RepositorioCorrelacaoDocumentoPrestacaoEmMemoria,
    chave_relacao,
    itens_de_resolucao_temporal_ponto,
    planejar_observacoes,
    registrar_correlacoes_de_ponto,
    registrar_correlacoes_do_corredor,
)
from magnata_os.classificacao.fonte_candidatos_documento_inventario_interna import (
    FonteCandidatosDocumentoInventarioInterna,
)
from magnata_os.classificacao.pacote_prestacao import PapelDestinatarioOrganizacional
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.resolucao_temporal_ponto import (
    AlocacaoHistorica,
    resolver_documento_ponto,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
CLI_A = ReferenciaCanonica('CLIENTE', 'cli-a')
CLI_B = ReferenciaCanonica('CLIENTE', 'cli-b')
COMP = ReferenciaCanonica('COMPETENCIA', '2026-07')
COMP_OUTRA = ReferenciaCanonica('COMPETENCIA', '2026-08')
COL_X = ReferenciaCanonica('COLABORADOR', 'col-x')
COL_Y = ReferenciaCanonica('COLABORADOR', 'col-y')


def _item(documento_id='doc-1', tipo='DOCUMENTO_A', cliente=CLI_A, competencia=COMP, colaborador=COL_X):
    return ItemInventarioPrestacao(
        documento_id=documento_id, tipo_documental=tipo, cliente=cliente,
        competencia=competencia, colaborador=colaborador,
    )


def _conteudo(documento_id):
    return f'%PDF-sintetico-{documento_id}'.encode()


def _documento(documento_id):
    import hashlib
    return Documento(
        documento_id=documento_id, arquivo_original=f'{documento_id}.pdf', nome_original=f'{documento_id}.pdf',
        mime_type='application/pdf', tamanho=1, hash_sha256=hashlib.sha256(_conteudo(documento_id)).hexdigest(),
        origem='teste', recebido_em=AGORA, lote_id=None, status='RECEBIDO',
        correlation_id=f'corr-{documento_id}', criado_em=AGORA, atualizado_em=AGORA,
    )


class _Ambiente:
    def __init__(self, *documento_ids):
        self.documentos = RepositorioDocumentosEmMemoria()
        for documento_id in documento_ids:
            self.documentos.salvar(_documento(documento_id))
        self.indice = RepositorioCorrelacaoDocumentoPrestacaoEmMemoria(
            documento_existe=lambda d: self.documentos.buscar_por_id(d) is not None,
        )
        self.candidatos = FonteCandidatosDocumentoInventarioInterna(
            fonte_inventario=self.indice, repositorio_documentos=self.documentos,
        )

    def registrar(self, documento_id, itens, origem=ORIGEM_CORREDOR_PRESTACAO, instante=AGORA):
        return self.indice.registrar_relacoes_do_documento(
            documento_id=documento_id, origem=origem, itens=tuple(itens),
            evidencia_sha256=None, registrado_em=instante,
        )


def _necessidade(tipo='DOCUMENTO_A', cliente=CLI_A, competencia=COMP, colaborador=COL_X):
    return NecessidadeDocumentoPrestacao(
        cliente=cliente, competencia=competencia, tipo_documental=tipo,
        motivo_exigencia='teste-j3', colaborador=colaborador,
    )


def _ids(documentos):
    return [d.documento_id for d in documentos]


# ---- identidade e decisão --------------------------------------------------

def test_chave_relacao_inclui_as_cinco_dimensoes():
    base = chave_relacao(_item())
    assert len(base) == 64
    variantes = [
        _item(documento_id='doc-2'), _item(cliente=CLI_B), _item(competencia=COMP_OUTRA),
        _item(tipo='DOCUMENTO_B'), _item(colaborador=COL_Y), _item(colaborador=None),
    ]
    assert len({base} | {chave_relacao(v) for v in variantes}) == 7


def test_planejar_nova_inalterada_superada_reativada():
    item = _item()
    obs, res = planejar_observacoes(documento_id='doc-1', origem='o', itens=(item,), estado_atual={},
                                    evidencia_sha256=None, registrado_em=AGORA)
    assert [(o.estado, o.sequencia) for o in obs] == [(EstadoCorrelacao.VIGENTE, 1)]
    atual = {chave_relacao(item): (EstadoCorrelacao.VIGENTE, 1, item)}
    obs, res = planejar_observacoes(documento_id='doc-1', origem='o', itens=(item,), estado_atual=atual,
                                    evidencia_sha256=None, registrado_em=AGORA)
    assert obs == () and res.inalteradas == 1
    obs, res = planejar_observacoes(documento_id='doc-1', origem='o', itens=(), estado_atual=atual,
                                    evidencia_sha256=None, registrado_em=AGORA)
    assert [(o.estado, o.sequencia) for o in obs] == [(EstadoCorrelacao.SUPERADA, 2)] and res.superadas == 1
    atual = {chave_relacao(item): (EstadoCorrelacao.SUPERADA, 2, item)}
    obs, res = planejar_observacoes(documento_id='doc-1', origem='o', itens=(item,), estado_atual=atual,
                                    evidencia_sha256=None, registrado_em=AGORA)
    assert [(o.estado, o.sequencia) for o in obs] == [(EstadoCorrelacao.VIGENTE, 3)] and res.reativadas == 1


@pytest.mark.parametrize('item', [
    _item(documento_id='doc-outro'),
    _item(cliente=ReferenciaCanonica('COLABORADOR', 'x')),
    _item(competencia=ReferenciaCanonica('COMPETENCIA', '07/2026')),
    _item(competencia=ReferenciaCanonica('CLIENTE', '2026-07')),
])
def test_planejar_rejeita_relacao_invalida(item):
    with pytest.raises(CorrelacaoDocumentoPrestacaoError):
        planejar_observacoes(documento_id='doc-1', origem='o', itens=(item,), estado_atual={},
                             evidencia_sha256=None, registrado_em=AGORA)


# ---- índice em memória: FK, replay, 1:N, histórico ---------------------------

def test_documento_inexistente_nunca_entra_no_indice():
    ambiente = _Ambiente('doc-1')
    with pytest.raises(DocumentoInexistenteNaCorrelacao):
        ambiente.registrar('recAIRTABLE123', [_item(documento_id='recAIRTABLE123')])
    assert ambiente.indice.historico_do_documento('recAIRTABLE123') == ()


def test_replay_nao_duplica_e_relacoes_legitimas_coexistem():
    ambiente = _Ambiente('doc-1')
    itens = [_item(cliente=CLI_A), _item(cliente=CLI_B)]  # 1 documento, 2 clientes legítimos
    primeiro = ambiente.registrar('doc-1', itens)
    segundo = ambiente.registrar('doc-1', list(reversed(itens)))
    assert (primeiro.novas, segundo.gravadas, segundo.inalteradas) == (2, 0, 2)
    assert len(ambiente.indice.historico_do_documento('doc-1')) == 2
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade(cliente=CLI_A))) == ['doc-1']
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade(cliente=CLI_B))) == ['doc-1']


def test_revisao_supera_e_nova_evidencia_reativa_sem_apagar_historico():
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item()])
    ambiente.registrar('doc-1', [])                       # reprocessado -> revisão
    assert ambiente.candidatos.candidatos_para(_necessidade()) == ()
    ambiente.registrar('doc-1', [_item()])                # revisão -> resolvido
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade())) == ['doc-1']
    historico = ambiente.indice.historico_do_documento('doc-1')
    assert [(o.estado.value, o.sequencia) for o in historico] == [
        ('VIGENTE', 1), ('SUPERADA', 2), ('VIGENTE', 3),
    ]


def test_nova_evidencia_troca_o_escopo_e_preserva_a_relacao_anterior_no_historico():
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item(cliente=CLI_A)])
    resultado = ambiente.registrar('doc-1', [_item(cliente=CLI_B)])
    assert (resultado.novas, resultado.superadas) == (1, 1)
    assert ambiente.candidatos.candidatos_para(_necessidade(cliente=CLI_A)) == ()
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade(cliente=CLI_B))) == ['doc-1']
    assert len(ambiente.indice.historico_do_documento('doc-1')) == 3


def test_origens_distintas_nao_se_superam():
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item()], origem=ORIGEM_CORREDOR_PRESTACAO)
    ambiente.registrar('doc-1', [], origem=ORIGEM_RESOLUCAO_TEMPORAL_PONTO)
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade())) == ['doc-1']


# ---- consumidor: necessidade exata e todas as divergências -----------------

@pytest.mark.parametrize('necessidade', [
    _necessidade(cliente=CLI_B),                 # cliente errado
    _necessidade(competencia=COMP_OUTRA),        # competência errada
    _necessidade(tipo='DOCUMENTO_B'),            # tipo errado
    _necessidade(colaborador=COL_Y),             # colaborador errado
    _necessidade(colaborador=None),              # nível cliente não recebe documento de pessoa
])
def test_consumidor_nunca_devolve_documento_para_necessidade_divergente(necessidade):
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item()])
    assert ambiente.candidatos.candidatos_para(necessidade) == ()


def test_consumidor_nivel_cliente_colaborador_nulo():
    ambiente = _Ambiente('doc-cli', 'doc-pessoa')
    ambiente.registrar('doc-cli', [_item(documento_id='doc-cli', tipo='DOCUMENTO_C', colaborador=None)])
    ambiente.registrar('doc-pessoa', [_item(documento_id='doc-pessoa', tipo='DOCUMENTO_C')])
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade(tipo='DOCUMENTO_C', colaborador=None))) == ['doc-cli']
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade(tipo='DOCUMENTO_C'))) == ['doc-pessoa']


def test_consumidor_devolve_documento_interno_real_nunca_id_de_inventario_externo():
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item()])
    (documento,) = ambiente.candidatos.candidatos_para(_necessidade())
    assert isinstance(documento, Documento) and documento.documento_id == 'doc-1'


def test_consumidor_usa_a_mesma_traducao_de_vocabulario_da_elegibilidade():
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item(tipo='Extrato da Folha de Pagamento', colaborador=None)])
    assert _ids(ambiente.candidatos.candidatos_para(
        _necessidade(tipo='extrato_cliente', colaborador=None))) == ['doc-1']


# ---- produtor: corredor --------------------------------------------------

@dataclasses.dataclass(frozen=True)
class _Resolucao:
    semantic_result_id: str


@dataclasses.dataclass(frozen=True)
class _Corredor:
    documento_id: str
    resolucao_semantica: object


@dataclasses.dataclass(frozen=True)
class _ResultadoExecucao:
    resultado_corredor: _Corredor
    itens_inventario: tuple = ()


def test_produtor_do_corredor_registra_itens_do_documento_interno_e_ignora_derivado(caplog):
    ambiente = _Ambiente('doc-1')
    resultados = (
        _ResultadoExecucao(_Corredor('doc-1', _Resolucao('r' * 64)), (_item(cliente=CLI_A), _item(cliente=CLI_B))),
        _ResultadoExecucao(_Corredor('doc-1:grupo-2', _Resolucao('s' * 64)), (_item(documento_id='doc-1:grupo-2'),)),
    )
    with caplog.at_level(logging.WARNING):
        resultado = registrar_correlacoes_do_corredor(
            ambiente.indice, documento_id='doc-1', resultados_corredor=resultados, registrado_em=AGORA,
        )
    assert resultado.novas == 2
    historico = ambiente.indice.historico_do_documento('doc-1')
    assert {o.item.cliente for o in historico} == {CLI_A, CLI_B}
    assert all(o.evidencia_sha256 and len(o.evidencia_sha256) == 64 for o in historico)
    assert EVENTO_RELACAO_DOCUMENTO_DERIVADO_IGNORADA in [getattr(r, 'evento', None) for r in caplog.records]


def test_produtor_do_corredor_documento_em_revisao_nao_gera_relacao_elegivel():
    ambiente = _Ambiente('doc-1')
    registrar_correlacoes_do_corredor(
        ambiente.indice, documento_id='doc-1', registrado_em=AGORA,
        resultados_corredor=(_ResultadoExecucao(_Corredor('doc-1', _Resolucao('r' * 64)), (_item(),)),),
    )
    em_revisao = (_ResultadoExecucao(_Corredor('doc-1', _Resolucao('t' * 64)), ()),)
    resultado = registrar_correlacoes_do_corredor(
        ambiente.indice, documento_id='doc-1', resultados_corredor=em_revisao, registrado_em=AGORA,
    )
    assert resultado.superadas == 1
    assert ambiente.candidatos.candidatos_para(_necessidade()) == ()


# ---- produtor: documento temporal (0010 + alocação) -------------------------

_TEXTO_PONTO = 'Cartão de Ponto\nPeríodo: 29/05/2026 até 28/06/2026'


class _Alocacoes:
    def __init__(self, *alocacoes):
        self._alocacoes = alocacoes

    def listar_para_colaborador(self, colaborador_id):
        return tuple(a for a in self._alocacoes if a.colaborador_id == colaborador_id)


def _ponto(*alocacoes, texto=_TEXTO_PONTO):
    return resolver_documento_ponto('doc-ponto', texto, 'col-x', _Alocacoes(*alocacoes))


def test_ponto_temporal_com_um_cliente():
    resolucao, clientes = _ponto(AlocacaoHistorica('col-x', 'cli-a', dt.date(2026, 1, 1), None))
    itens = itens_de_resolucao_temporal_ponto(resolucao, clientes)
    assert [(i.cliente, i.competencia.entidade_id, i.colaborador) for i in itens] == [
        (CLI_A, '2026-06', COL_X),
    ]


def test_ponto_temporal_legitimamente_ligado_a_dois_clientes_sem_duplicar_documento():
    ambiente = _Ambiente('doc-ponto')
    resolucao, clientes = _ponto(
        AlocacaoHistorica('col-x', 'cli-a', dt.date(2026, 1, 1), dt.date(2026, 6, 10)),
        AlocacaoHistorica('col-x', 'cli-b', dt.date(2026, 6, 11), None),
    )
    resultado = registrar_correlacoes_de_ponto(
        ambiente.indice, resolucao_documental=resolucao, resolucao_cliente=clientes, registrado_em=AGORA,
    )
    assert resultado.novas == 2
    assert {o.item.documento_id for o in ambiente.indice.historico_do_documento('doc-ponto')} == {'doc-ponto'}
    comp = ReferenciaCanonica('COMPETENCIA', '2026-06')
    for cliente in (CLI_A, CLI_B):
        assert _ids(ambiente.candidatos.candidatos_para(_necessidade(
            tipo='Folha de Ponto', cliente=cliente, competencia=comp))) == ['doc-ponto']


@pytest.mark.parametrize('alocacoes,texto', [
    ((), _TEXTO_PONTO),                                                            # sem alocação no período
    ((AlocacaoHistorica('col-x', 'cli-a', dt.date(2026, 1, 1), None),), 'sem periodo declarado'),
])
def test_ponto_sem_evidencia_suficiente_nao_gera_relacao(alocacoes, texto):
    resolucao, clientes = _ponto(*alocacoes, texto=texto)
    assert itens_de_resolucao_temporal_ponto(resolucao, clientes) == ()


# ---- destinatário organizacional (bridge Airtable read-only) --------------

class _LeitorClientes:
    def __init__(self, registros):
        self._registros = registros
        self.chamadas = 0

    def listar_campos_destinatario_clientes(self):
        self.chamadas += 1
        return self._registros


def test_destinatario_um_campo_por_papel_sem_fallback_nem_invencao():
    from magnata_os.documental.importacao_lote.adapters.airtable_destinatario_cliente import (
        FonteDestinatarioOrganizacionalClienteAirtableShadow,
    )
    leitor = _LeitorClientes([
        {'cliente_id': 'cli-a', 'email': ' financeiro@cliente-a.exemplo ', 'emails_contador': ['c@escritorio.exemplo']},
        {'cliente_id': 'cli-b', 'email': None, 'emails_contador': ['c@escritorio.exemplo', 'c@escritorio.exemplo']},
        {'cliente_id': 'cli-c', 'email': 'sem-arroba', 'emails_contador': None},
    ])
    fonte = FonteDestinatarioOrganizacionalClienteAirtableShadow(leitor)
    inst, cont = PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL, PapelDestinatarioOrganizacional.CONTADOR_DO_CLIENTE
    assert fonte.enderecos_para(CLI_A, inst) == ('financeiro@cliente-a.exemplo',)
    assert fonte.enderecos_para(CLI_B, inst) == ()                  # nunca cai para o contador sozinho
    assert fonte.enderecos_para(CLI_B, cont) == ('c@escritorio.exemplo',)
    assert fonte.enderecos_para(ReferenciaCanonica('CLIENTE', 'cli-c'), inst) == ()
    assert fonte.enderecos_para(ReferenciaCanonica('CLIENTE', 'inexistente'), inst) == ()
    assert leitor.chamadas == 1


def test_destinatario_adapter_nao_escreve_e_dominio_nao_importa_airtable():
    import ast
    import inspect
    import magnata_os.classificacao.pacote_prestacao as dominio
    import magnata_os.documental.importacao_lote.adapters.airtable_destinatario_cliente as adapter
    nomes = {n.module for n in ast.walk(ast.parse(inspect.getsource(dominio))) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any('airtable' in n.lower() for n in nomes)
    fonte = inspect.getsource(adapter)
    assert 'requests.' not in fonte and '.post(' not in fonte and '.patch(' not in fonte


# ---- backfill (projetado; nunca executado em dado real) --------------------

class _ExecucaoFalsa:
    """Duck type de `ExecucaoCorredorReadonly` para o backfill: grava no
    índice como o produtor real faria."""

    def __init__(self, ambiente, relacoes_por_documento, falhar_em=()):
        self._ambiente = ambiente
        self._relacoes = relacoes_por_documento
        self._falhar_em = set(falhar_em)
        self.ultimo_registro_correlacao = None
        self.processados = []
        self.produz_indice_correlacao = True

    def processar_documento(self, documento_id, hash_sha256, pdf_bytes=None, candidatos_colaborador=()):
        if documento_id in self._falhar_em:
            raise RuntimeError('falha sintetica')
        self.processados.append(documento_id)
        self.ultimo_registro_correlacao = self._ambiente.registrar(documento_id, self._relacoes.get(documento_id, ()))
        return ()


def _backfill_ambiente():
    ambiente = _Ambiente('doc-1', 'doc-2', 'doc-3', 'doc-4')
    armazenamento = ArmazenamentoArquivosEmMemoria()
    documentos = [ambiente.documentos.buscar_por_id(d) for d in ('doc-3', 'doc-1', 'doc-2', 'doc-4')]
    for documento in documentos:
        if documento.documento_id != 'doc-2':  # doc-2 sem blob
            conteudo = _conteudo(documento.documento_id)
            armazenamento.armazenar(documento.hash_sha256, conteudo, 'application/pdf',
                                    documento.nome_original, len(conteudo))
    return ambiente, armazenamento, documentos


def test_backfill_reusa_produtor_e_e_idempotente_reiniciavel_e_auditavel():
    from magnata_os.documental.importacao_lote import composicao_prestacao_upstream as borda
    ambiente, armazenamento, documentos = _backfill_ambiente()
    relacoes = {'doc-1': (_item(documento_id='doc-1'),), 'doc-3': ()}
    execucao = _ExecucaoFalsa(ambiente, relacoes, falhar_em={'doc-4'})

    primeiro = borda.executar_backfill_correlacao(
        documentos=documentos, armazenamento=armazenamento, execucao_corredor=execucao,
    )
    assert execucao.processados == ['doc-1', 'doc-3']       # ordem determinística
    assert (primeiro.processados, primeiro.com_relacao_vigente, primeiro.sem_relacao, primeiro.sem_blob) == (2, 1, 1, 1)
    assert primeiro.erros == (('doc-4', 'RuntimeError'),)
    assert (primeiro.relacoes_novas, primeiro.ultimo_documento_id) == (1, 'doc-4')

    segundo = borda.executar_backfill_correlacao(
        documentos=documentos, armazenamento=armazenamento, execucao_corredor=_ExecucaoFalsa(ambiente, relacoes),
    )
    assert segundo.relacoes_novas == 0                       # replay não grava nada novo
    assert len(ambiente.indice.historico_do_documento('doc-1')) == 1

    retomado = borda.executar_backfill_correlacao(
        documentos=documentos, armazenamento=armazenamento,
        execucao_corredor=_ExecucaoFalsa(ambiente, relacoes), retomar_apos='doc-2',
    )
    assert retomado.processados == 2 and retomado.ultimo_documento_id == 'doc-4'


def test_backfill_conta_conflito_quando_reprocessamento_muda_o_escopo():
    from magnata_os.documental.importacao_lote import composicao_prestacao_upstream as borda
    ambiente, armazenamento, documentos = _backfill_ambiente()
    ambiente.registrar('doc-1', [_item(documento_id='doc-1', cliente=CLI_A)])
    relatorio = borda.executar_backfill_correlacao(
        documentos=[d for d in documentos if d.documento_id == 'doc-1'], armazenamento=armazenamento,
        execucao_corredor=_ExecucaoFalsa(ambiente, {'doc-1': (_item(documento_id='doc-1', cliente=CLI_B),)}),
    )
    assert (relatorio.relacoes_novas, relatorio.relacoes_superadas) == (1, 1)


# ---- composition root e relatório do piloto (fontes falsas) ----------------

class _LeitorFalso:
    def listar_funcionarios(self):
        return ()


class _ExecucaoCorredorFalsa:
    fonte_colaboradores_esperados = object()
    fonte_vinculos = object()
    fonte_unidade_posto = object()
    fonte_cliente_direto = object()


def test_composition_root_usa_indice_interno_requisitos_canonicos_e_mesmas_fontes(monkeypatch):
    from magnata_os.documental.importacao_lote import composicao_prestacao_upstream as borda

    class _Clientes:
        def __init__(self, leitor):
            pass

        def listar_ativos(self, contexto):
            return (CLI_A, CLI_B)

    monkeypatch.setattr(borda, 'FonteClientesPrestacaoAirtable', _Clientes)
    execucao = _ExecucaoCorredorFalsa()
    fonte_candidatos = object()
    contexto = borda.compor_contexto_prestacao_upstream(
        leitor=_LeitorFalso(), execucao_corredor=execucao, competencia_base='2026-07',
        fonte_candidatos_por_necessidade=fonte_candidatos, repositorio_documentos=object(),
        armazenamento=object(), repositorio_execucoes_prestacao=object(), clientes=(CLI_B,),
    )
    assert contexto.fonte_clientes.listar_ativos(None) == (CLI_B,)
    assert contexto.competencias_por_cliente == {CLI_B: COMP}
    assert contexto.fonte_candidatos_por_necessidade is fonte_candidatos
    assert contexto.tipos_obrigatorios_por_colaborador == ('Holerite',)
    assert (contexto.fonte_vinculos, contexto.fonte_unidade_posto, contexto.fonte_cliente_direto,
            contexto.fonte_colaboradores_esperados) == (
        execucao.fonte_vinculos, execucao.fonte_unidade_posto, execucao.fonte_cliente_direto,
        execucao.fonte_colaboradores_esperados)
    assert {r.tipo_documental for r in contexto.requisitos_base} >= {'FGTS', 'Extrato da Folha de Pagamento'}


def test_compositor_de_ambiente_sem_credencial_falha_explicitamente():
    from magnata_os.documental.importacao_lote import composicao_prestacao_upstream as borda
    with pytest.raises(RuntimeError, match='AIRTABLE_API_KEY'):
        borda.compor_contexto_prestacao_upstream_a_partir_do_ambiente(
            competencia_base='2026-07', armazenamento=object(), ambiente={},
        )


# ---- adapter Postgres com cursor fake (roda sem banco) ---------------------

class _CursorFake:
    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        if self.conexao.falhar_em and self.conexao.falhar_em in sql:
            raise RuntimeError('falha sintetica no banco')
        self.conexao.executados.append((' '.join(sql.split()), params))

    def fetchall(self):
        return self.conexao.linhas


class _ConexaoFake:
    def __init__(self, linhas=(), falhar_em=None):
        self.linhas = list(linhas)
        self.falhar_em = falhar_em
        self.executados = []
        self.commits = self.rollbacks = 0

    def cursor(self):
        return _CursorFake(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _linha(item, sequencia, estado, origem=ORIGEM_CORREDOR_PRESTACAO):
    return (chave_relacao(item), sequencia, item.documento_id, item.cliente.entidade_id,
            item.competencia.entidade_id, item.tipo_documental,
            item.colaborador.entidade_id if item.colaborador else None, estado, origem, None, AGORA)


def test_adapter_postgres_trava_le_estado_e_grava_o_plano_do_dominio_numa_transacao():
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        RepositorioCorrelacaoDocumentoPrestacaoPostgres,
    )
    anterior = _item(cliente=CLI_A)
    conexao = _ConexaoFake(linhas=[_linha(anterior, 1, 'VIGENTE')])
    resultado = RepositorioCorrelacaoDocumentoPrestacaoPostgres(conexao).registrar_relacoes_do_documento(
        documento_id='doc-1', origem=ORIGEM_CORREDOR_PRESTACAO, itens=(_item(cliente=CLI_B),),
        evidencia_sha256=None, registrado_em=AGORA,
    )
    sqls = [sql for sql, _ in conexao.executados]
    assert sqls[0].startswith('SELECT pg_advisory_xact_lock(%s, hashtext(%s))')
    assert conexao.executados[0][1] == (6007, f'doc-1|{ORIGEM_CORREDOR_PRESTACAO}')
    assert 'DISTINCT ON (relacao_id)' in sqls[1]
    inserts = [params for sql, params in conexao.executados if sql.startswith('INSERT')]
    assert sorted((p[3], p[1], p[7]) for p in inserts) == [('cli-a', 2, 'SUPERADA'), ('cli-b', 1, 'VIGENTE')]
    assert (resultado.novas, resultado.superadas) == (1, 1)
    assert (conexao.commits, conexao.rollbacks) == (1, 0)


def test_adapter_postgres_falha_desfaz_tudo():
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        RepositorioCorrelacaoDocumentoPrestacaoPostgres,
    )
    conexao = _ConexaoFake(falhar_em='INSERT')
    with pytest.raises(RuntimeError):
        RepositorioCorrelacaoDocumentoPrestacaoPostgres(conexao).registrar_relacoes_do_documento(
            documento_id='doc-1', origem='o', itens=(_item(),), evidencia_sha256=None, registrado_em=AGORA,
        )
    assert (conexao.commits, conexao.rollbacks) == (0, 1)


def test_adapter_postgres_listar_so_estado_corrente_vigente_sem_escrever():
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        RepositorioCorrelacaoDocumentoPrestacaoPostgres,
    )
    item = _item()
    conexao = _ConexaoFake(linhas=[_linha(item, 3, 'VIGENTE'), _linha(item, 1, 'VIGENTE', origem='outra')])
    itens = RepositorioCorrelacaoDocumentoPrestacaoPostgres(conexao).listar(CLI_A, COMP)
    assert itens == (item,)                                   # mesma relação de 2 origens -> 1 item
    sql, params = conexao.executados[0]
    assert 'DISTINCT ON (relacao_id, origem)' in sql and 'WHERE estado = %s' in sql
    assert params == ('cli-a', '2026-07', 'VIGENTE')
    assert conexao.commits == 0
    assert RepositorioCorrelacaoDocumentoPrestacaoPostgres(_ConexaoFake()).listar(COL_X, COMP) == ()


# ---- revisão independente: 2 origens e 2 ciclos -------------------------

def test_mesma_relacao_de_duas_origens_nao_colide_e_uma_nao_supera_a_outra():
    ambiente = _Ambiente('doc-1')
    item = _item(tipo='Folha de Ponto')
    assert ambiente.registrar('doc-1', [item], origem=ORIGEM_CORREDOR_PRESTACAO).novas == 1
    assert ambiente.registrar('doc-1', [item], origem=ORIGEM_RESOLUCAO_TEMPORAL_PONTO).novas == 1
    ambiente.registrar('doc-1', [], origem=ORIGEM_CORREDOR_PRESTACAO)
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade(tipo='Folha de Ponto'))) == ['doc-1']
    assert ambiente.registrar('doc-1', [item], origem=ORIGEM_CORREDOR_PRESTACAO).reativadas == 1


def test_reprocessar_sob_outro_ciclo_nao_supera_relacao_de_outra_competencia():
    ambiente = _Ambiente('doc-1')
    ambiente.registrar('doc-1', [_item(competencia=COMP)])
    resultado = ambiente.indice.registrar_relacoes_do_documento(
        documento_id='doc-1', origem=ORIGEM_CORREDOR_PRESTACAO, itens=(), evidencia_sha256=None,
        registrado_em=AGORA, competencias_superaveis=frozenset({'2026-08'}),
    )
    assert resultado.gravadas == 0
    assert _ids(ambiente.candidatos.candidatos_para(_necessidade())) == ['doc-1']
    # Na MESMA competência, a revisão continua superando.
    resultado = ambiente.indice.registrar_relacoes_do_documento(
        documento_id='doc-1', origem=ORIGEM_CORREDOR_PRESTACAO, itens=(), evidencia_sha256=None,
        registrado_em=AGORA, competencias_superaveis=frozenset({'2026-07'}),
    )
    assert resultado.superadas == 1


def test_produtor_do_corredor_escopo_de_superacao_vem_do_ciclo_da_execucao():
    from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
    from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly

    execucao = ExecucaoCorredorReadonly.__new__(ExecucaoCorredorReadonly)
    execucao._ciclo = ContextoCicloPrestacao(competencia_base=(2026, 8))
    execucao._cliente_do_ciclo = None
    resultados = (_ResultadoExecucao(_Corredor('doc-1', _Resolucao('r' * 64)), (_item(competencia=COMP),)),)
    assert execucao._competencias_validaveis(resultados) == frozenset({'2026-08', '2026-07'})
    assert execucao._competencias_validaveis(()) == frozenset({'2026-08'})


def test_produtor_com_cliente_do_ciclo_deslocado_nunca_supera_a_base_nao_validada():
    from magnata_os.classificacao.competencia_esperada_prestacao import (
        POLITICA_COMPETENCIA_PRESTACAO_V1,
        ContextoCicloPrestacao,
    )
    from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly

    deslocamento = POLITICA_COMPETENCIA_PRESTACAO_V1.deslocamentos[0]
    cliente_deslocado = deslocamento.cliente
    ciclo = ContextoCicloPrestacao(competencia_base=(2026, 7))
    esperada = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(ciclo, cliente_deslocado, '')
    assert esperada != (2026, 7)  # a política realmente desloca este cliente

    execucao = ExecucaoCorredorReadonly.__new__(ExecucaoCorredorReadonly)
    execucao._ciclo = ciclo
    execucao._cliente_do_ciclo = cliente_deslocado
    assert execucao._competencias_validaveis(()) == frozenset({f'{esperada[0]:04d}-{esperada[1]:02d}'})


def test_backfill_sem_produtor_do_indice_falha_explicitamente():
    from magnata_os.documental.importacao_lote import composicao_prestacao_upstream as borda
    ambiente, armazenamento, documentos = _backfill_ambiente()
    execucao = _ExecucaoFalsa(ambiente, {})
    execucao.produz_indice_correlacao = False
    with pytest.raises(RuntimeError, match='produtor'):
        borda.executar_backfill_correlacao(
            documentos=documentos, armazenamento=armazenamento, execucao_corredor=execucao,
        )
    assert execucao.processados == []
