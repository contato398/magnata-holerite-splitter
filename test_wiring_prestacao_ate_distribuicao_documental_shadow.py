"""Delta Final A-F (Ultraplan "Cliente+Competência -> PENDING"): testa
o composition root `executar_prestacao_ate_distribuicao_documental_
shadow` -- fecha o trecho upstream (requisitos -> necessidades ->
aquisição -> readiness -> pacote) até o elo G-P já staged
(`wiring_prestacao_distribuicao_documental_shadow.materializar_
prestacao_distribuicao_documental_shadow`), sem duplicar nenhuma
invariante interna já provada por `test_wiring_distribuicao_
documental_shadow.py`/`test_wiring_prestacao_distribuicao_documental_
shadow.py`.
"""
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo_composicao
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.execucao_prestacao import RepositorioExecucoesPrestacao
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
from magnata_os.classificacao.orquestrador_corredor_readonly import (
    ResultadoExecucaoCorredorPrestacao,
)
from magnata_os.classificacao.prestacao_readiness import (
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
from magnata_os.classificacao.resolucao_documento_prestacao import (
    EstadoCorredorDocumentoPrestacao,
    ResultadoProcessamentoDocumentoPrestacao,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.politica_preset_distribuicao_documental import (
    PresetDistribuicaoDocumentalDesconhecido,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    ParametrosOrdemPrestacao,
    PrestacaoDistribuicaoDocumentalError,
    executar_prestacao_ate_distribuicao_documental_shadow,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_COMPETENCIA_AF = ReferenciaCanonica('COMPETENCIA', '2026-09')


# ---------------------------------------------------------------------
# Fakes de Prestação -- mesmo padrão já usado por
# test_composicao_ciclo_persistente_prestacao.py (fontes substituíveis,
# nunca hardcode de nome de cliente no motor).
# ---------------------------------------------------------------------

class _RepositorioExecucoesPrestacaoMemoria:
    def __init__(self):
        self._execucoes = {}

    def criar(self, execucao):
        self._execucoes[execucao.execucao_prestacao_id] = execucao
        return execucao

    def buscar_por_id(self, execucao_prestacao_id):
        return self._execucoes.get(execucao_prestacao_id)

    def atualizar_estado(self, *, execucao_prestacao_id, novo_estado, concluido_em=None, **kwargs):
        import dataclasses
        execucao = self._execucoes[execucao_prestacao_id]
        execucao = dataclasses.replace(execucao, estado=novo_estado)
        self._execucoes[execucao_prestacao_id] = execucao
        return execucao


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteClientes:
    def __init__(self, *clientes):
        self._clientes = clientes

    def listar_ativos(self, contexto=None):
        return self._clientes


class _FonteColaboradoresEsperados:
    def __init__(self, mapa: dict):
        self._mapa = mapa  # {cliente: (colaborador, ...)}

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._mapa.get(cliente, ())


class _FonteCandidatosPorNecessidade:
    def __init__(self, mapa: dict):
        self._mapa = mapa  # {(cliente, competencia): (Documento, ...)}

    def candidatos_para(self, necessidade):
        return self._mapa.get((necessidade.cliente, necessidade.competencia), ())


def _documento_bruto(documento_id, hash_sha256):
    return Documento(
        documento_id=documento_id, arquivo_original=f'{documento_id}.pdf',
        nome_original=f'{documento_id}.pdf', mime_type='application/pdf', tamanho=10,
        hash_sha256=hash_sha256, origem='teste', recebido_em=AGORA, lote_id=None,
        status='RECEBIDO', correlation_id=f'corr-{documento_id}', criado_em=AGORA, atualizado_em=AGORA,
    )


def _resolucao_ancora_holerite(documento_id, *, cliente, competencia, colaborador):
    """Resolução semântica mínima e válida o bastante para
    `avaliar_candidatos_ancora` aceitar como âncora real -- reaproveita
    o mesmo shape de `ResultadoResolucaoSemantico` usado pelos testes
    existentes de `test_composicao_ciclo_persistente_prestacao.py`."""
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao,
        Cardinalidade,
        ConfiancaResolucao,
        DimensaoResolucao,
        EstadoResolucaoDimensao,
        EstadoResultadoSemantico,
        NivelConfianca,
        PerfilAplicabilidadeResolucao,
        RegraAplicabilidadeDimensao,
        ResolucaoDimensao,
        ResultadoResolucaoSemantico,
    )

    def _regra(dimensao):
        return RegraAplicabilidadeDimensao(
            dimensao=dimensao, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )

    def _dim(dimensao, valor):
        return ResolucaoDimensao(
            dimensao=dimensao, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(valor,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )

    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='prestacao-af-teste', version='1', escopo_documental='prestacao-contas',
        regras=(_regra(DimensaoResolucao.CLIENTE), _regra(DimensaoResolucao.COMPETENCIA)),
    )
    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id='resolver-af-teste', resolver_version='1',
        politica_id='prestacao-af', politica_version='1', perfil=perfil,
        resolucoes=(_dim(DimensaoResolucao.CLIENTE, cliente), _dim(DimensaoResolucao.COMPETENCIA, competencia)),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA, necessita_revisao_humana=False,
    )


def _contexto(
    *, clientes, colaboradores_por_cliente, candidatos_por_necessidade, competencias_por_cliente,
    repositorio_documentos, armazenamento_arquivos,
):
    return ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=_FonteClientes(*clientes),
        fonte_requisitos=_FonteRequisitosVazia(),
        repositorio_execucoes=_RepositorioExecucoesPrestacaoMemoria(),
        requisitos_base=(RequisitoDocumentalPrestacao(TIPO_HOLERITE),),
        competencias_por_cliente=competencias_por_cliente,
        fonte_colaboradores_esperados=_FonteColaboradoresEsperados(colaboradores_por_cliente),
        fonte_candidatos_por_necessidade=_FonteCandidatosPorNecessidade(candidatos_por_necessidade),
        tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
        repositorio_documentos=repositorio_documentos,
        armazenamento_arquivos=armazenamento_arquivos,
    )


def _executor_readonly_resolve_holerite(cliente, competencia, colaborador):
    """Fabrica um fake de `executar_documento_readonly` que resolve o
    documento como Holerite daquele colaborador (adiciona ao inventário
    E devolve a resolução semântica que serve de âncora) -- mesmo
    padrão de `test_obrigatorio_sem_fonte_candidatos_por_necessidade_
    cliente_fica_em_revisao_explicita`."""
    def _fake(contexto_corredor, sink):
        sink.adicionar(ItemInventarioPrestacao(
            documento_id=contexto_corredor.documento_id, tipo_documental=TIPO_HOLERITE,
            cliente=cliente, competencia=competencia, colaborador=colaborador,
        ))
        resultado_processamento = ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto_corredor.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
            tipo_documental=TIPO_HOLERITE,
            resolucao_semantica=_resolucao_ancora_holerite(
                contexto_corredor.documento_id, cliente=cliente, competencia=competencia, colaborador=colaborador,
            ),
        )
        return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=resultado_processamento),)
    return _fake


def _executor_readonly_resolve_por_documento(mapa_por_documento_id: dict):
    """Variante genérica, keyed por `documento_id` -> (cliente,
    competencia, colaborador) -- permite simular, dentro do MESMO
    `patch.object`, múltiplos clientes/documentos resolvendo de forma
    independente, inclusive um MESMO cliente com 2 documentos
    resolvendo para colaboradores DIFERENTES (cenário de divergência
    real, usado para provar o isolamento por exceção de domínio)."""
    def _fake(contexto_corredor, sink):
        cliente, competencia, colaborador = mapa_por_documento_id[contexto_corredor.documento_id]
        sink.adicionar(ItemInventarioPrestacao(
            documento_id=contexto_corredor.documento_id, tipo_documental=TIPO_HOLERITE,
            cliente=cliente, competencia=competencia, colaborador=colaborador,
        ))
        resultado_processamento = ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto_corredor.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
            tipo_documental=TIPO_HOLERITE,
            resolucao_semantica=_resolucao_ancora_holerite(
                contexto_corredor.documento_id, cliente=cliente, competencia=competencia, colaborador=colaborador,
            ),
        )
        return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=resultado_processamento),)
    return _fake


def _deps_nucleo():
    conexao = _Conexao()
    return {
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_autorizacoes': RepositorioAutorizacoesGateEmMemoria(),
        'repositorio_acoes': RepositorioAcoesExecucaoPlanoPostgres(conexao),
    }, conexao


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao
        self._ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((sql, params))
        if 'INSERT INTO magnata_orquestrador.acoes_execucao_plano' in sql and 'RETURNING acao_execucao_id' in sql:
            colunas_valores = params[:-4]
            acao_execucao_id = colunas_valores[0]
            if acao_execucao_id in self.conexao.linhas:
                self._ultimo = None
            else:
                self.conexao.linhas[acao_execucao_id] = colunas_valores
                self._ultimo = (acao_execucao_id,)
        elif sql.strip().startswith('SELECT') and 'acoes_execucao_plano' in sql:
            acao_execucao_id = params[0]
            self._ultimo = self.conexao.linhas.get(acao_execucao_id)
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo


class _Conexao:
    def __init__(self):
        self.executados = []
        self.linhas = {}
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1


def test_cliente_readiness_apto_produz_ordem_valida_ate_pending():
    """A. Cliente/competência completo -> chega ao wiring downstream. G.
    Correlação necessidade/documento/colaborador preservada (funcionario_id
    == colaborador.entidade_id na Ordem/resultado)."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-af-pronto')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-af-pronto')
    conteudo = b'holerite-af-pronto'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-af-pronto', hash_sha256)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA_AF): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    chamadas_resolver = []

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        chamadas_resolver.append((cliente_, competencia_, resultados_aquisicao))
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='HOLERITE', mensagem_texto='Segue seu holerite:',
        )

    fake_executor = _executor_readonly_resolve_holerite(cliente, _COMPETENCIA_AF, colaborador)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        # `armazenar`/blob precisa existir para `_ler_e_extrair_texto` ler.
        deps['repositorio_documentos'].salvar(documento)
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_parametros,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
            **deps,
        )

    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-af-pronto'
    assert len(chamadas_resolver) == 1
    cliente_recebido, competencia_recebida, resultados_aquisicao_recebidos = chamadas_resolver[0]
    assert cliente_recebido == cliente
    assert competencia_recebida == _COMPETENCIA_AF
    assert resultados_aquisicao_recebidos[0].necessidade.colaborador == colaborador


def test_cliente_readiness_insuficiente_zero_ordem():
    """B/C. Readiness insuficiente (nenhum documento adquirido) -> zero
    Ordem, `resolver_parametros_ordem` nunca chamado para este cliente."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-af-incompleto')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-af-incompleto')

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={},  # nenhum candidato -- nunca resolve
        competencias_por_cliente={cliente: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    chamado = []

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        chamado.append(1)
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='HOLERITE', mensagem_texto='Segue:',
        )

    resultados = executar_prestacao_ate_distribuicao_documental_shadow(
        contexto=contexto, resolver_parametros_ordem=resolver_parametros,
        materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
        **deps,
    )

    assert resultados == ()
    assert chamado == []


def test_destinatario_ausente_fail_closed_zero_ordem():
    """H. Destinatário/preset não resolvido (resolver_parametros_ordem
    devolve None) -> fail-closed, zero Ordem para aquele cliente, mesmo
    com readiness apto."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-af-sem-destinatario')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-af-sem-destinatario')
    conteudo = b'holerite-af-sem-destinatario'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-af-sem-destinatario', hash_sha256)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA_AF): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    fake_executor = _executor_readonly_resolve_holerite(cliente, _COMPETENCIA_AF, colaborador)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=lambda *a: None,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
            **deps,
        )

    assert resultados == ()


def test_multi_cliente_isolamento_um_apto_outro_nao():
    """H. Múltiplos clientes com isolamento correto: cliente A pronto
    gera Ordem; cliente B incompleto não gera nenhuma, e A não é
    afetado pela ausência de B."""
    cliente_a = ReferenciaCanonica('CLIENTE', 'cliente-af-a')
    cliente_b = ReferenciaCanonica('CLIENTE', 'cliente-af-b')
    colaborador_a = ReferenciaCanonica('COLABORADOR', 'colab-af-a')
    colaborador_b = ReferenciaCanonica('COLABORADOR', 'colab-af-b')
    conteudo_a = b'holerite-af-a'
    hash_a = hashlib.sha256(conteudo_a).hexdigest()
    documento_a = _documento_bruto('doc-af-a', hash_a)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente_a, cliente_b),
        colaboradores_por_cliente={cliente_a: (colaborador_a,), cliente_b: (colaborador_b,)},
        candidatos_por_necessidade={(cliente_a, _COMPETENCIA_AF): (documento_a,)},  # B nunca resolve
        competencias_por_cliente={cliente_a: _COMPETENCIA_AF, cliente_b: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='HOLERITE', mensagem_texto='Segue:',
        )

    fake_executor = _executor_readonly_resolve_holerite(cliente_a, _COMPETENCIA_AF, colaborador_a)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento_a)
        deps['armazenamento'].armazenar(hash_a, conteudo_a, 'application/pdf', 'doc.pdf', len(conteudo_a))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_parametros,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
            **deps,
        )

    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-af-a'


def test_replay_nao_duplica_acao():
    """I. Replay -> nenhuma duplicação (mesmo event_id/acao_execucao_id,
    mesma linha persistida)."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-af-replay')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-af-replay')
    conteudo = b'holerite-af-replay'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-af-replay', hash_sha256)

    deps, conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA_AF): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='HOLERITE', mensagem_texto='Segue:',
        )

    fake_executor = _executor_readonly_resolve_holerite(cliente, _COMPETENCIA_AF, colaborador)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento)
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        kwargs = dict(
            contexto=contexto, resolver_parametros_ordem=resolver_parametros,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
            **deps,
        )
        primeiro = executar_prestacao_ate_distribuicao_documental_shadow(**kwargs)
        segundo = executar_prestacao_ate_distribuicao_documental_shadow(**kwargs)

    assert primeiro[0].event_id == segundo[0].event_id
    assert primeiro[0].acao_execucao_id == segundo[0].acao_execucao_id
    assert len(conexao.linhas) == 1


def test_preset_invalido_propaga_fail_closed_do_elo_downstream():
    """J. Preset inválido -> fail-closed, erro do elo G-P propagado sem
    mascarar (não duplicando os testes já existentes desse elo -- só
    confirmando que o composition root novo não engole a exceção)."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-af-preset-invalido')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-af-preset-invalido')
    conteudo = b'holerite-af-preset-invalido'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-af-preset-invalido', hash_sha256)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA_AF): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='PRESET_INEXISTENTE',
            tipo_documento='HOLERITE', mensagem_texto='Segue:',
        )

    fake_executor = _executor_readonly_resolve_holerite(cliente, _COMPETENCIA_AF, colaborador)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        with pytest.raises(PresetDistribuicaoDocumentalDesconhecido):
            executar_prestacao_ate_distribuicao_documental_shadow(
                contexto=contexto, resolver_parametros_ordem=resolver_parametros,
                materializador=None, porta_assinatura=None,
                ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
                **deps,
            )


def test_parametros_ordem_prestacao_campo_vazio_falha_fechado():
    with pytest.raises(PrestacaoDistribuicaoDocumentalError):
        ParametrosOrdemPrestacao(destinatario='', preset_id='x', tipo_documento='y', mensagem_texto='z')


def test_zero_transporte_zero_execucao_prestacao_criada():
    """K/N. Zero transporte (checagem estrutural leve) e zero
    ExecucaoPrestacao criada por este composition root (não cria
    segundo `execucao_id` -- simplesmente não cria nenhum)."""
    import ast
    import magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow as modulo
    with open(modulo.__file__, encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=modulo.__file__)
    proibidos = {'requests', 'boto3', 'psycopg', 'ExecutorEvolutionLegado', 'compor_porta_execucao'}
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(alias.name.split('.')[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            nomes.update(alias.name for alias in no.names)
        elif isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
    assert proibidos.isdisjoint(nomes)
    assert 'criar_e_persistir_execucao' not in nomes
    assert 'criar_execucao_prestacao' not in nomes


def test_erro_de_dominio_de_um_cliente_nao_impede_os_demais():
    """Correção pós-Ultrareview (achado MEDIUM): um cliente cujos
    `ResultadoAquisicaoPorNecessidade` divergem de colaborador
    (`ColaboradorDivergenteEntreDocumentos`, erro de DADO daquele
    cliente específico) não pode impedir que outro cliente, íntegro e
    processado na mesma chamada, chegue a PENDING -- nem antes nem
    depois dele na iteração."""
    cliente_com_erro = ReferenciaCanonica('CLIENTE', 'cliente-af-erro-dominio')
    colaborador_1 = ReferenciaCanonica('COLABORADOR', 'colab-af-erro-1')
    colaborador_2 = ReferenciaCanonica('COLABORADOR', 'colab-af-erro-2')
    cliente_integro = ReferenciaCanonica('CLIENTE', 'cliente-af-integro')
    colaborador_integro = ReferenciaCanonica('COLABORADOR', 'colab-af-integro')

    conteudo_1 = b'holerite-erro-colab-1'
    conteudo_2 = b'holerite-erro-colab-2'
    conteudo_integro = b'holerite-integro'
    hash_1 = hashlib.sha256(conteudo_1).hexdigest()
    hash_2 = hashlib.sha256(conteudo_2).hexdigest()
    hash_integro = hashlib.sha256(conteudo_integro).hexdigest()
    doc_1 = _documento_bruto('doc-af-erro-1', hash_1)
    doc_2 = _documento_bruto('doc-af-erro-2', hash_2)
    doc_integro = _documento_bruto('doc-af-integro', hash_integro)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente_com_erro, cliente_integro),
        colaboradores_por_cliente={
            cliente_com_erro: (colaborador_1, colaborador_2),
            cliente_integro: (colaborador_integro,),
        },
        candidatos_por_necessidade={
            # cliente_com_erro tem 2 documentos, 1 por colaborador --
            # ambos resolvem, mas para colaboradores DIFERENTES, o que
            # o elo G-P rejeita como uma única Ordem (ColaboradorDivergenteEntreDocumentos).
            (cliente_com_erro, _COMPETENCIA_AF): (doc_1, doc_2),
            (cliente_integro, _COMPETENCIA_AF): (doc_integro,),
        },
        competencias_por_cliente={cliente_com_erro: _COMPETENCIA_AF, cliente_integro: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='HOLERITE', mensagem_texto='Segue:',
        )

    fake_executor = _executor_readonly_resolve_por_documento({
        'doc-af-erro-1': (cliente_com_erro, _COMPETENCIA_AF, colaborador_1),
        'doc-af-erro-2': (cliente_com_erro, _COMPETENCIA_AF, colaborador_2),
        'doc-af-integro': (cliente_integro, _COMPETENCIA_AF, colaborador_integro),
    })
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(doc_1)
        deps['repositorio_documentos'].salvar(doc_2)
        deps['repositorio_documentos'].salvar(doc_integro)
        deps['armazenamento'].armazenar(hash_1, conteudo_1, 'application/pdf', 'doc.pdf', len(conteudo_1))
        deps['armazenamento'].armazenar(hash_2, conteudo_2, 'application/pdf', 'doc.pdf', len(conteudo_2))
        deps['armazenamento'].armazenar(hash_integro, conteudo_integro, 'application/pdf', 'doc.pdf', len(conteudo_integro))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_parametros,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
            **deps,
        )

    # Nenhuma exceção propagou; cliente com erro de dado foi pulado
    # (registrado via _logger, nunca silenciado), cliente íntegro
    # chegou a PENDING normalmente.
    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-af-integro'


def test_multi_cliente_isolamento_ambos_com_candidatos_apenas_apto_recebe_ordem():
    """Reforço do teste de isolamento (achado LOW da Ultrareview): desta
    vez AMBOS os clientes têm candidato de aquisição -- só o cliente B
    nunca converge para uma âncora real (resolve para um cliente
    diferente do esperado, divergência explícita), provando isolamento
    de verdade, não apenas "quem não tem candidato não aparece"."""
    cliente_a = ReferenciaCanonica('CLIENTE', 'cliente-af-reforco-a')
    cliente_b = ReferenciaCanonica('CLIENTE', 'cliente-af-reforco-b')
    cliente_errado = ReferenciaCanonica('CLIENTE', 'cliente-af-reforco-nao-esperado')
    colaborador_a = ReferenciaCanonica('COLABORADOR', 'colab-af-reforco-a')
    colaborador_b = ReferenciaCanonica('COLABORADOR', 'colab-af-reforco-b')

    conteudo_a = b'holerite-af-reforco-a'
    conteudo_b = b'holerite-af-reforco-b'
    hash_a = hashlib.sha256(conteudo_a).hexdigest()
    hash_b = hashlib.sha256(conteudo_b).hexdigest()
    documento_a = _documento_bruto('doc-af-reforco-a', hash_a)
    documento_b = _documento_bruto('doc-af-reforco-b', hash_b)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente_a, cliente_b),
        colaboradores_por_cliente={cliente_a: (colaborador_a,), cliente_b: (colaborador_b,)},
        candidatos_por_necessidade={
            (cliente_a, _COMPETENCIA_AF): (documento_a,),
            (cliente_b, _COMPETENCIA_AF): (documento_b,),  # cliente_b TEM candidato
        },
        competencias_por_cliente={cliente_a: _COMPETENCIA_AF, cliente_b: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    def resolver_parametros(cliente_, competencia_, resultados_aquisicao):
        return ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='HOLERITE', mensagem_texto='Segue:',
        )

    def _fake_executor(contexto_corredor, sink):
        if contexto_corredor.documento_id == 'doc-af-reforco-a':
            sink.adicionar(ItemInventarioPrestacao(
                documento_id=contexto_corredor.documento_id, tipo_documental=TIPO_HOLERITE,
                cliente=cliente_a, competencia=_COMPETENCIA_AF, colaborador=colaborador_a,
            ))
            resolucao = _resolucao_ancora_holerite(
                contexto_corredor.documento_id, cliente=cliente_a, competencia=_COMPETENCIA_AF, colaborador=colaborador_a,
            )
        else:
            # cliente_b: o documento candidato resolve para um cliente
            # DIFERENTE do esperado -- divergência real, nunca âncora
            # fabricada; `avaliar_candidatos_ancora` rejeita.
            resolucao = _resolucao_ancora_holerite(
                contexto_corredor.documento_id, cliente=cliente_errado, competencia=_COMPETENCIA_AF, colaborador=colaborador_b,
            )
        resultado_processamento = ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto_corredor.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
            tipo_documental=TIPO_HOLERITE, resolucao_semantica=resolucao,
        )
        return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=resultado_processamento),)

    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', _fake_executor):
        deps['repositorio_documentos'].salvar(documento_a)
        deps['armazenamento'].armazenar(hash_a, conteudo_a, 'application/pdf', 'doc.pdf', len(conteudo_a))
        deps['armazenamento'].armazenar(hash_b, conteudo_b, 'application/pdf', 'doc.pdf', len(conteudo_b))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_parametros,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_af_v1', instante=AGORA,
            **deps,
        )

    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-af-reforco-a'
