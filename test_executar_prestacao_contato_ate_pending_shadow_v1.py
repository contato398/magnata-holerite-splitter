"""Testes de `executar_prestacao_contato_ate_pending_shadow_v1.py` -- a peça
nova que fecha o gap de integração (ver "AUDITORIA CANÔNICA DO ELO"):
liga `executar_prestacao_ate_distribuicao_documental_shadow` (Prestação,
intocado) ao resolvedor real do Contato Canônico do Colaborador
(`construir_resolvedor_parametros_ordem_prestacao_contato_v1`,
intocado) fora de um arquivo de teste, pela primeira vez.

Mesmas fixtures de `test_integracao_prestacao_contato_ate_pending.py`,
duplicadas de propósito (mesmo padrão já estabelecido neste repositório
de nunca importar helpers privados entre arquivos de teste)."""
import ast
import hashlib
import inspect
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo_composicao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
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
from magnata_os.documental.alocacao.configuracao_contato_colaborador import (
    SegredoContatoColaboradorAusente,
)
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RegistroContatoColaborador,
    RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    derivar_identidade_ordem_distribuicao,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    montar_ordem_distribuicao_documental_de_prestacao,
)
import magnata_os.orquestrador.executar_prestacao_contato_ate_pending_shadow_v1 as modulo_composicao_v1
from magnata_os.orquestrador.executar_prestacao_contato_ate_pending_shadow_v1 import (
    compor_chave_fernet_contato_a_partir_do_ambiente,
    compor_repositorio_contato_a_partir_do_ambiente,
    executar_prestacao_contato_ate_pending_shadow_v1,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-09')
_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-composicao-v1-teste'


# ---------------------------------------------------------------------
# Fakes de Prestação -- mesmo padrão de
# test_integracao_prestacao_contato_ate_pending.py.
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
        self._mapa = mapa

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._mapa.get(cliente, ())


class _FonteCandidatosPorNecessidade:
    def __init__(self, mapa: dict):
        self._mapa = mapa

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
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao, Cardinalidade, ConfiancaResolucao, DimensaoResolucao,
        EstadoResolucaoDimensao, EstadoResultadoSemantico, NivelConfianca,
        PerfilAplicabilidadeResolucao, RegraAplicabilidadeDimensao, ResolucaoDimensao,
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
        perfil_id='prestacao-composicao-v1-teste', version='1', escopo_documental='prestacao-contas',
        regras=(
            _regra(DimensaoResolucao.CLIENTE), _regra(DimensaoResolucao.COMPETENCIA),
            _regra(DimensaoResolucao.COLABORADOR), _regra(DimensaoResolucao.TIPO_DOCUMENTAL),
        ),
    )
    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id='resolver-composicao-v1-teste', resolver_version='1',
        politica_id='prestacao-composicao-v1', politica_version='1', perfil=perfil,
        resolucoes=(
            _dim(DimensaoResolucao.CLIENTE, cliente), _dim(DimensaoResolucao.COMPETENCIA, competencia),
            _dim(DimensaoResolucao.COLABORADOR, colaborador),
            _dim(DimensaoResolucao.TIPO_DOCUMENTAL, ReferenciaCanonica('TIPO_DOCUMENTAL', TIPO_HOLERITE)),
        ),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA, necessita_revisao_humana=False,
    )


def _contexto(*, clientes, colaboradores_por_cliente, candidatos_por_necessidade,
              competencias_por_cliente, repositorio_documentos, armazenamento_arquivos):
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


def _deps_nucleo():
    conexao = _Conexao()
    return {
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_execucoes': RepositorioExecucoesEmMemoria(),
        'repositorio_autorizacoes': RepositorioAutorizacoesGateEmMemoria(),
        'repositorio_acoes': RepositorioAcoesExecucaoPlanoPostgres(conexao),
    }, conexao


def _mensagem_texto(cliente, competencia):
    return f'Segue seu documento -- {cliente.entidade_id}/{competencia.entidade_id}'


def _registrar_contato(repo, colaborador_id, numero, canal=CANAL_WHATSAPP):
    repo.criar_ou_confirmar(RegistroContatoColaborador(
        colaborador_id=colaborador_id, canal=canal,
        valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, numero),
        hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, numero),
        versao_chave='v1', origem='teste', criado_em=AGORA, atualizado_em=AGORA,
    ))


def _rodar(cliente, colaborador, repositorio_contato, chave_fernet, documento_id='doc-1', conteudo=b'holerite-composicao-v1'):
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto(documento_id, hash_sha256)
    deps, conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )
    fake_executor = _executor_readonly_resolve_holerite(cliente, _COMPETENCIA, colaborador)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento)
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        resultados = executar_prestacao_contato_ate_pending_shadow_v1(
            contexto=contexto, repositorio_contato=repositorio_contato, chave_fernet=chave_fernet,
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
            montar_mensagem_texto=_mensagem_texto,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_composicao_v1', instante=AGORA,
            **deps,
        )
    return resultados, conexao


# ---------------------------------------------------------------------
# Fluxo completo.
# ---------------------------------------------------------------------

def test_fluxo_completo_ate_pending_via_composicao_v1():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-composicao-v1')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-composicao-v1')
    repositorio_contato = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato, 'colab-composicao-v1', '5511999998888')

    resultados, _conexao = _rodar(cliente, colaborador, repositorio_contato, _CHAVE_FERNET)

    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-composicao-v1'
    assert resultados[0].acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING
    assert resultados[0].event_id
    assert resultados[0].envelope_sha256


def test_contato_ausente_produz_zero_ordem_fail_closed():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-sem-contato')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-sem-contato')
    repositorio_contato = RepositorioContatoColaboradorEmMemoria()  # vazio

    resultados, _conexao = _rodar(cliente, colaborador, repositorio_contato, _CHAVE_FERNET)

    assert resultados == ()


def test_chave_fernet_incorreta_produz_zero_ordem_fail_closed():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-chave-errada')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-chave-errada')
    repositorio_contato = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato, 'colab-chave-errada', '5511999998888')
    chave_errada = Fernet.generate_key()

    resultados, _conexao = _rodar(cliente, colaborador, repositorio_contato, chave_errada)

    assert resultados == ()


def test_replay_nao_duplica_acao():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-replay-v1')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-replay-v1')
    repositorio_contato = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato, 'colab-replay-v1', '5511999998888')

    resultados1, conexao = _rodar(cliente, colaborador, repositorio_contato, _CHAVE_FERNET, documento_id='doc-replay')
    # Segunda rodada reaproveitando a MESMA tabela de ações (conexao != a
    # nova, mas o event_id/acao_execucao_id determinístico é o que importa
    # aqui -- replay real de ponta a ponta já é provado por
    # test_replay_da_mesma_integracao_nao_duplica_acao, este teste foca em
    # confirmar que a composição v1 preserva esse determinismo).
    resultados2, _conexao2 = _rodar(cliente, colaborador, repositorio_contato, _CHAVE_FERNET, documento_id='doc-replay')

    assert resultados1[0].event_id == resultados2[0].event_id
    assert resultados1[0].acao_persistida.acao_execucao_id == resultados2[0].acao_persistida.acao_execucao_id


def test_telefone_alterado_gera_novo_event_id():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-telefone-v1')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-telefone-v1')
    repo_v1 = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo_v1, 'colab-telefone-v1', '5511999998888')
    repo_v2 = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo_v2, 'colab-telefone-v1', '5511988887777')

    resultados1, _c1 = _rodar(cliente, colaborador, repo_v1, _CHAVE_FERNET, documento_id='doc-tel')
    resultados2, _c2 = _rodar(cliente, colaborador, repo_v2, _CHAVE_FERNET, documento_id='doc-tel')

    assert resultados1[0].event_id != resultados2[0].event_id


# ---------------------------------------------------------------------
# Zero Airtable / zero transporte (AST).
# ---------------------------------------------------------------------

def test_modulo_nunca_importa_airtable_nem_app():
    arvore = ast.parse(inspect.getsource(modulo_composicao_v1))
    modulos_importados = {
        node.module for node in ast.walk(arvore) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name for node in ast.walk(arvore) if isinstance(node, ast.Import) for alias in node.names
    }
    proibidos = [m for m in modulos_importados if m and ('airtable' in m.lower() or m == 'app' or m.startswith('app.'))]
    assert proibidos == []


def test_modulo_nunca_importa_transporte_real_nem_evolution():
    nomes_importados = {
        alias.asname or alias.name
        for node in ast.walk(ast.parse(inspect.getsource(modulo_composicao_v1)))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    proibidos = {
        'ExecutorEvolutionLegado', 'TransporteEvolutionLegado',
        'transporte_real_habilitado', 'compor_porta_execucao', 'ciclo_producao_v1',
    }
    assert not (nomes_importados & proibidos)


# ---------------------------------------------------------------------
# Compositores de ambiente.
# ---------------------------------------------------------------------

def test_compor_repositorio_contato_usa_conexao_real_composta():
    from magnata_os.documental.alocacao.adapters.postgres_contato_colaborador import (
        RepositorioContatoColaboradorPostgres,
    )

    conexao_fake = object()
    with patch(
        'magnata_os.documental.modulo01.adapters.conexao.abrir_conexao',
        return_value=conexao_fake,
    ):
        repo = compor_repositorio_contato_a_partir_do_ambiente()

    assert isinstance(repo, RepositorioContatoColaboradorPostgres)
    assert repo._conexao is conexao_fake


def test_compor_chave_fernet_ausente_levanta_erro_fail_closed(monkeypatch):
    monkeypatch.delenv('MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL', raising=False)
    with pytest.raises(SegredoContatoColaboradorAusente):
        compor_chave_fernet_contato_a_partir_do_ambiente()


def test_compor_chave_fernet_presente_devolve_chave_valida(monkeypatch):
    monkeypatch.setenv('MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL', 'v1')
    monkeypatch.setenv('MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V1', 'segredo-teste-composicao-v1')
    chave = compor_chave_fernet_contato_a_partir_do_ambiente()
    Fernet(chave)  # nao levanta -- formato valido
