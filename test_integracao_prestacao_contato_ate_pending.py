"""Integração ponta a ponta: CLIENTE+COMPETÊNCIA -> pacote PRONTO ->
destinatário interno (Contato Canônico de Colaborador V1) -> Ordem ->
Evento canônico -> Preview -> Autorização -> AÇÃO PERSISTIDA (PENDING),
SEM TRANSPORTE.

Fecha o item de teste que faltava nas sessões anteriores desta mesma
missão: até aqui, `resolver_parametros_ordem_prestacao_contato_v1` só
tinha cobertura isolada (`test_resolver_parametros_ordem_prestacao_
contato_v1.py`) e o composition root real
(`executar_prestacao_ate_distribuicao_documental_shadow`) só tinha
cobertura com resolvedores FAKE/hardcoded
(`test_wiring_prestacao_ate_distribuicao_documental_shadow.py`). Este
arquivo é o primeiro a rodar os dois juntos.

Fixtures duplicadas (não importadas) de `test_wiring_prestacao_ate_
distribuicao_documental_shadow.py` -- mesmo padrão de fixture já
estabelecido nesse arquivo, replicado aqui de propósito para não criar
dependência de import entre módulos de teste (nem tocar naquele arquivo
já mesclado)."""
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

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
from magnata_os.orquestrador.resolver_parametros_ordem_prestacao_contato_v1 import (
    construir_resolvedor_parametros_ordem_prestacao_contato_v1,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    derivar_identidade_ordem_distribuicao,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    executar_prestacao_ate_distribuicao_documental_shadow,
    montar_ordem_distribuicao_documental_de_prestacao,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-09')
_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-integracao-teste'


# ---------------------------------------------------------------------
# Fakes de Prestação -- mesmo padrão de
# test_wiring_prestacao_ate_distribuicao_documental_shadow.py.
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
        perfil_id='prestacao-contato-integracao', version='1', escopo_documental='prestacao-contas',
        regras=(
            _regra(DimensaoResolucao.CLIENTE), _regra(DimensaoResolucao.COMPETENCIA),
            _regra(DimensaoResolucao.COLABORADOR),
        ),
    )
    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id='resolver-integracao-teste', resolver_version='1',
        politica_id='prestacao-contato', politica_version='1', perfil=perfil,
        resolucoes=(
            _dim(DimensaoResolucao.CLIENTE, cliente), _dim(DimensaoResolucao.COMPETENCIA, competencia),
            _dim(DimensaoResolucao.COLABORADOR, colaborador),
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


def _registrar_contato(repo, colaborador_id, numero):
    repo.criar_ou_confirmar(RegistroContatoColaborador(
        colaborador_id=colaborador_id, canal=CANAL_WHATSAPP,
        valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, numero),
        hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, numero),
        versao_chave='v1', origem='teste', criado_em=AGORA, atualizado_em=AGORA,
    ))


# ---------------------------------------------------------------------
# Integração completa.
# ---------------------------------------------------------------------

def test_cliente_competencia_pacote_pronto_destinatario_interno_ate_pending_sem_transporte():
    """CLIENTE+COMPETÊNCIA -> requisitos -> necessidades -> aquisição ->
    readiness -> pacote PRONTO -> destinatário resolvido pela fonte
    interna (Contato Canônico de Colaborador V1, nunca Airtable) ->
    Ordem -> Evento canônico -> Preview -> Autorização -> AÇÃO
    PERSISTIDA (PENDING). Zero transporte real em qualquer ponto."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-integracao')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-integracao')
    conteudo = b'holerite-integracao-contato'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-integracao', hash_sha256)

    repositorio_contato = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato, 'colab-integracao', '11999998888')

    deps, conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    resolver_parametros_ordem_prestacao_v1 = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repositorio_contato, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )

    fake_executor = _executor_readonly_resolve_holerite(cliente, _COMPETENCIA, colaborador)
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento)
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_parametros_ordem_prestacao_v1,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_integracao_contato_v1', instante=AGORA,
            **deps,
        )

    # Chegou a exatamente 1 Ordem, com o destinatário vindo da fonte
    # interna (nunca do Airtable -- nenhum objeto Airtable existe em
    # nenhum ponto desta cadeia).
    assert len(resultados) == 1
    resultado = resultados[0]
    assert resultado.funcionario_id == 'colab-integracao'

    # Chegou a PENDING de verdade -- ação persistida no repositório de
    # ações, sem transporte (nenhum `reivindicar_proxima`/execução foi
    # chamado neste teste).
    assert resultado.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING
    assert resultado.acao_persistida.acao_execucao_id in conexao.linhas

    # Evento canônico + Preview + Autorização de fato aconteceram --
    # event_id não vazio, autorizacao_id não vazio, envelope gravado.
    assert resultado.event_id
    assert resultado.autorizacao_id
    assert resultado.envelope_sha256


def test_replay_da_mesma_integracao_nao_duplica_acao():
    """Rodar a MESMA composição duas vezes (mesmo cliente, competência,
    documento, contato) produz o MESMO event_id/acao_execucao_id -- a
    segunda chamada não cria uma segunda linha em acoes_execucao_plano
    (ON CONFLICT DO NOTHING, já garantido pelo núcleo; aqui provamos que
    a composição INTEIRA, com o resolvedor real, preserva essa
    garantia)."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-replay')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-replay')
    conteudo = b'holerite-replay-contato'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-replay', hash_sha256)

    repositorio_contato = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato, 'colab-replay', '11999998888')

    resolver_parametros_ordem_prestacao_v1 = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repositorio_contato, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )

    def _rodar_uma_vez(deps):
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
            return executar_prestacao_ate_distribuicao_documental_shadow(
                contexto=contexto, resolver_parametros_ordem=resolver_parametros_ordem_prestacao_v1,
                materializador=None, porta_assinatura=None,
                ator_referencia='ator:teste', proveniencia='teste_replay_contato_v1', instante=AGORA,
                **deps,
            )

    # Mesma conexao/repositorios de ações reaproveitados entre as duas
    # rodadas -- só assim é possível provar não-duplicação real na
    # camada de persistência (cada rodada monta seu próprio
    # repositorio_documentos/armazenamento/contexto, mas a tabela de
    # ações é a MESMA).
    deps, conexao = _deps_nucleo()
    deps2 = dict(deps)
    deps2['repositorio_documentos'] = RepositorioDocumentosEmMemoria()
    deps2['armazenamento'] = ArmazenamentoArquivosEmMemoria()
    deps2['repositorio_execucoes'] = deps['repositorio_execucoes']
    deps2['repositorio_autorizacoes'] = deps['repositorio_autorizacoes']
    deps2['repositorio_acoes'] = deps['repositorio_acoes']

    resultados1 = _rodar_uma_vez(deps)
    resultados2 = _rodar_uma_vez(deps2)

    assert len(resultados1) == 1 and len(resultados2) == 1
    assert resultados1[0].event_id == resultados2[0].event_id
    assert resultados1[0].acao_persistida.acao_execucao_id == resultados2[0].acao_persistida.acao_execucao_id
    # Só 1 linha real na tabela de ações, apesar de 2 execuções.
    assert len(conexao.linhas) == 1


def test_mudanca_de_telefone_entre_execucoes_gera_ordem_e_event_id_diferentes():
    """Telefone do MESMO colaborador muda entre duas competências
    distintas (cenário real: reconciliação de contato entre ciclos) --
    a Ordem resultante é diferente, com `event_id` diferente, nunca
    tratada como replay da anterior."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-telefone-mudou')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-telefone-mudou')

    repositorio_contato_v1 = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato_v1, 'colab-telefone-mudou', '11999998888')
    repositorio_contato_v2 = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repositorio_contato_v2, 'colab-telefone-mudou', '11988887777')

    resolver_v1 = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repositorio_contato_v1, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    resolver_v2 = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repositorio_contato_v2, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )

    from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
        ResultadoAquisicaoPorNecessidade,
    )
    from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente, competencia=_COMPETENCIA, tipo_documental='HOLERITE',
        motivo_exigencia='teste', colaborador=colaborador,
    )
    resultado_aquisicao = (ResultadoAquisicaoPorNecessidade(
        necessidade=necessidade, documento_id='doc-x', hash_sha256='hash-x',
    ),)

    params_v1 = resolver_v1(cliente, _COMPETENCIA, resultado_aquisicao)
    params_v2 = resolver_v2(cliente, _COMPETENCIA, resultado_aquisicao)
    assert params_v1.destinatario != params_v2.destinatario

    ordem_v1 = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultado_aquisicao, destinatario=params_v1.destinatario,
        preset_id=params_v1.preset_id, tipo_documento=params_v1.tipo_documento,
        mensagem_texto=params_v1.mensagem_texto,
    )
    ordem_v2 = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultado_aquisicao, destinatario=params_v2.destinatario,
        preset_id=params_v2.preset_id, tipo_documento=params_v2.tipo_documento,
        mensagem_texto=params_v2.mensagem_texto,
    )
    assert derivar_identidade_ordem_distribuicao(ordem_v1) != derivar_identidade_ordem_distribuicao(ordem_v2)
