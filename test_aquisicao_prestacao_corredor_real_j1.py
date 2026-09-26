"""Gate J1 -- aquisição da Prestação com o CORREDOR REAL (sem `patch`).

Até o J1, todo teste que chegava a PENDING pela Prestação substituía
`executar_documento_readonly`/`extrair_texto_seguro` por fakes -- e a
aquisição real tinha 3 defeitos de wiring invisíveis a esses testes (ver
docs/decisoes/auditoria-gate-j-composicao-prestacao-v1.md):

  1. `candidatos_colaborador` recebia `tipos_obrigatorios_por_colaborador`
     (tipos documentais, `str`) -> `AttributeError` no corredor;
  2. `fonte_vinculos`/`fonte_unidade_posto`/`fonte_cliente_direto`
     fixos em `None`, sem campo para injetá-los;
  3. `politica_competencia=None` repassado ao corredor junto com
     `cliente_do_ciclo` -> `AttributeError`.

Aqui NADA é substituído: PDF sintético real (fpdf2), extração real
(`extrair_texto_seguro`), corredor real, readiness real, wiring real,
Contato Canônico real (repositório em memória), núcleo genérico real até
PENDING. Só as FONTES são em memória e sintéticas -- nunca dado pessoal
real (CPF/nome fictícios, mesmo padrão de
test_magnata_os_classificacao_orquestrador_corredor_readonly.py). Zero
Airtable, zero rede, zero transporte.
"""
import ast
import hashlib
import inspect
import logging
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo_composicao
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    EVENTO_CORREDOR_FALHOU,
    EVENTO_DOCUMENTO_NIVEL_CLIENTE_FORA_ORDEM_COLABORADOR,
    ContextoComposicaoPrestacao,
    ResultadoAquisicaoPorNecessidade,
    _particionar_por_colaborador,
    adquirir_por_necessidades,
    resultados_aquisicao_prontos_por_cliente,
    resultados_aquisicao_prontos_por_colaborador,
)
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RegistroContatoColaborador,
    RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.executar_prestacao_contato_ate_pending_shadow_v1 import (
    executar_prestacao_contato_ate_pending_shadow_v1,
)
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
_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-j1')
_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'colab-j1')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_POSTO = ReferenciaCanonica('UNIDADE_POSTO', 'posto-j1')
_CANDIDATO = CandidatoFuncionario(func_id='colab-j1', cpf='11122233344', nome_normalizado='FULANO SINTETICO')
_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-j1-teste'

_TEXTO_HOLERITE = (
    'Recibo de Pagamento -- Total de Vencimentos\n'
    'Competência: 07/2026\n'
    'CPF: 111.222.333-44'
)
_TEXTO_EXTRATO = 'Extrato Mensal\nCNPJ: 11.222.333/0001-44\nCompetência: 07/2026'


# ---------------------------------------------------------------------
# PDF sintético real -- mesmo padrão de test_importacao_lote.py.
# ---------------------------------------------------------------------

def _pdf(texto: str) -> bytes:
    """Bytes DETERMINÍSTICOS: o fpdf2 grava a data de criação no PDF --
    sem fixá-la, 2 gerações em segundos diferentes teriam hash (e,
    portanto, `event_id`) diferentes, e testes de identidade entre 2
    ambientes passariam ou falhariam conforme o relógio."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_creation_date(AGORA)
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.multi_cell(0, 10, text=texto)
    return bytes(pdf.output())


def _documento(documento_id: str, conteudo: bytes) -> Documento:
    return Documento(
        documento_id=documento_id, arquivo_original=f'{documento_id}.pdf',
        nome_original=f'{documento_id}.pdf', mime_type='application/pdf', tamanho=len(conteudo),
        hash_sha256=hashlib.sha256(conteudo).hexdigest(), origem='teste', recebido_em=AGORA, lote_id=None,
        status='RECEBIDO', correlation_id=f'corr-{documento_id}', criado_em=AGORA, atualizado_em=AGORA,
    )


# ---------------------------------------------------------------------
# Fontes em memória (sintéticas) -- as ÚNICAS peças não reais.
# ---------------------------------------------------------------------

class _RepositorioExecucoesPrestacaoMemoria:
    def __init__(self):
        self._execucoes = {}

    def criar(self, execucao):
        self._execucoes[execucao.execucao_prestacao_id] = execucao

    def buscar_por_id(self, execucao_prestacao_id):
        return self._execucoes.get(execucao_prestacao_id)

    def atualizar_estado(self, *, execucao_prestacao_id, novo_estado, concluido_em=None):
        import dataclasses
        self._execucoes[execucao_prestacao_id] = dataclasses.replace(
            self._execucoes[execucao_prestacao_id], estado=novo_estado,
        )


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteClientes:
    def listar_ativos(self, contexto=None):
        return (_CLIENTE,)


class _FonteColaboradoresEsperados:
    def __init__(self, colaboradores=(_COLABORADOR,)):
        self._colaboradores = tuple(colaboradores)

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._colaboradores if cliente == _CLIENTE else ()


class _FonteCandidatosPorNecessidade:
    def __init__(self, documentos):
        self._documentos = tuple(documentos)

    def candidatos_para(self, necessidade):
        if necessidade.cliente == _CLIENTE and necessidade.competencia == _COMPETENCIA:
            return self._documentos
        return ()


class _FonteVinculos:
    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(_CLIENTE,),
        )


class _FonteUnidadePosto:
    def resolver_unidade_posto(self, colaborador, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(_POSTO,),
        )


class _FonteClienteDireto:
    def resolver_cliente_direto(self, texto_documento):
        return _CLIENTE if '11.222.333/0001-44' in texto_documento else None


# ---------------------------------------------------------------------
# Núcleo do Orquestrador -- mesmo duplo de conexão de
# test_executar_prestacao_contato_ate_pending_shadow_v1.py.
# ---------------------------------------------------------------------

class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao
        self._ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if 'INSERT INTO magnata_orquestrador.acoes_execucao_plano' in sql and 'RETURNING acao_execucao_id' in sql:
            colunas_valores = params[:-4]
            acao_execucao_id = colunas_valores[0]
            if acao_execucao_id in self.conexao.linhas:
                self._ultimo = None
            else:
                self.conexao.linhas[acao_execucao_id] = colunas_valores
                self._ultimo = (acao_execucao_id,)
        elif sql.strip().startswith('SELECT') and 'acoes_execucao_plano' in sql:
            self._ultimo = self.conexao.linhas.get(params[0])
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo


class _Conexao:
    def __init__(self):
        self.linhas = {}

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass


class _Ambiente:
    """Repositórios reais em memória compartilhados entre rodadas --
    permite provar replay sobre o MESMO estado."""

    def __init__(self, documentos_com_conteudo, *, colaboradores=(_COLABORADOR,), contatos=None,
                 requisitos_base=(TIPO_HOLERITE,)):
        self.conexao = _Conexao()
        self.repositorio_documentos = RepositorioDocumentosEmMemoria()
        self.armazenamento = ArmazenamentoArquivosEmMemoria()
        self.repositorio_execucoes = RepositorioExecucoesEmMemoria()
        self.repositorio_autorizacoes = RepositorioAutorizacoesGateEmMemoria()
        self.repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(self.conexao)
        self.repositorio_contato = RepositorioContatoColaboradorEmMemoria()
        self.colaboradores = tuple(colaboradores)
        self.requisitos_base = tuple(RequisitoDocumentalPrestacao(tipo) for tipo in requisitos_base)
        for colaborador_id, numero in (contatos or {_COLABORADOR.entidade_id: '5511999998888'}).items():
            self.repositorio_contato.criar_ou_confirmar(RegistroContatoColaborador(
                colaborador_id=colaborador_id, canal=CANAL_WHATSAPP,
                valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, numero),
                hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, numero),
                versao_chave='v1', origem='teste', criado_em=AGORA, atualizado_em=AGORA,
            ))
        self.documentos = []
        for documento_id, conteudo in documentos_com_conteudo:
            documento = _documento(documento_id, conteudo)
            self.repositorio_documentos.salvar(documento)
            self.armazenamento.armazenar(
                documento.hash_sha256, conteudo, 'application/pdf', documento.nome_original, len(conteudo),
            )
            self.documentos.append(documento)

    def contexto(self, **fontes):
        return ContextoComposicaoPrestacao(
            competencia_base='2026-07',
            fonte_clientes=_FonteClientes(),
            fonte_requisitos=_FonteRequisitosVazia(),
            repositorio_execucoes=_RepositorioExecucoesPrestacaoMemoria(),
            requisitos_base=self.requisitos_base,
            competencias_por_cliente={_CLIENTE: _COMPETENCIA},
            fonte_colaboradores_esperados=_FonteColaboradoresEsperados(self.colaboradores),
            fonte_candidatos_por_necessidade=_FonteCandidatosPorNecessidade(self.documentos),
            tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
            repositorio_documentos=self.repositorio_documentos,
            armazenamento_arquivos=self.armazenamento,
            **fontes,
        )

    def executar_ate_pending(self, contexto):
        return executar_prestacao_contato_ate_pending_shadow_v1(
            contexto=contexto, repositorio_contato=self.repositorio_contato, chave_fernet=_CHAVE_FERNET,
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
            montar_mensagem_texto=lambda cliente, competencia: f'Documento {competencia.entidade_id}',
            repositorio_documentos=self.repositorio_documentos, armazenamento=self.armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_execucoes=self.repositorio_execucoes,
            repositorio_autorizacoes=self.repositorio_autorizacoes,
            repositorio_acoes=self.repositorio_acoes,
            ator_referencia='ator:teste:j1', proveniencia='teste_j1_corredor_real', instante=AGORA,
        )

    def executar_ate_pending_com_trios(self, contexto, trios_prontos):
        """Mesmo caminho, sobre um snapshot JÁ calculado (J3)."""
        return executar_prestacao_contato_ate_pending_shadow_v1(
            contexto=contexto, repositorio_contato=self.repositorio_contato, chave_fernet=_CHAVE_FERNET,
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
            montar_mensagem_texto=lambda cliente, competencia: f'Documento {competencia.entidade_id}',
            repositorio_documentos=self.repositorio_documentos, armazenamento=self.armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_execucoes=self.repositorio_execucoes,
            repositorio_autorizacoes=self.repositorio_autorizacoes,
            repositorio_acoes=self.repositorio_acoes,
            ator_referencia='ator:teste:j1', proveniencia='teste_j1_corredor_real', instante=AGORA,
            trios_prontos=trios_prontos,
        )


def _todas_as_fontes():
    return dict(
        candidatos_colaborador=(_CANDIDATO,),
        fonte_vinculos=_FonteVinculos(),
        fonte_unidade_posto=_FonteUnidadePosto(),
    )


def _necessidade_holerite():
    return NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=TIPO_HOLERITE,
        motivo_exigencia='teste-j1', colaborador=_COLABORADOR,
    )


def _adquirir(ambiente, necessidade, **fontes):
    _inventario, resultados = adquirir_por_necessidades(
        ambiente.contexto(**fontes), (necessidade,), ContextoCicloPrestacao((2026, 7)),
    )
    return resultados


def _estados_dimensoes(resultado_aquisicao):
    (execucao,) = resultado_aquisicao.resultados_corredor
    resolucao = execucao.resultado_corredor.resolucao_semantica
    return execucao.resultado_corredor.estado, {r.dimensao: r.estado for r in resolucao.resolucoes}


def _eventos_corredor_falhou(caplog):
    return [r for r in caplog.records if getattr(r, 'evento', None) == EVENTO_CORREDOR_FALHOU]


# ---------------------------------------------------------------------
# Regressão do contrato de `candidatos_colaborador`.
# ---------------------------------------------------------------------

def test_default_de_candidatos_colaborador_e_vazio_nunca_tipos_documentais():
    contexto = _Ambiente(()).contexto()
    assert contexto.candidatos_colaborador == ()
    assert contexto.tipos_obrigatorios_por_colaborador == (TIPO_HOLERITE,)


def test_contexto_rejeita_tipo_documental_como_candidato_colaborador():
    with pytest.raises(TypeError, match='CandidatoFuncionario'):
        _Ambiente(()).contexto(candidatos_colaborador=(TIPO_HOLERITE,))


def test_repr_do_contexto_nunca_expoe_cpf_dos_candidatos():
    contexto = _Ambiente(()).contexto(candidatos_colaborador=(_CANDIDATO,))
    assert _CANDIDATO.cpf not in repr(contexto)


def test_corredor_recebe_candidatos_do_contexto_nunca_tipos_obrigatorios():
    """Espia o contexto que chega ao corredor REAL (delegando a ele) nas
    DUAS aquisições -- nunca mais `tipos_obrigatorios_por_colaborador`."""
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    contexto = ambiente.contexto(**_todas_as_fontes())
    capturados = []
    original = modulo_composicao.executar_documento_readonly

    def _espiao(contexto_corredor, sink):
        capturados.append(contexto_corredor)
        return original(contexto_corredor, sink)

    modulo_composicao.executar_documento_readonly = _espiao
    try:
        adquirir_por_necessidades(contexto, (_necessidade_holerite(),), ContextoCicloPrestacao((2026, 7)))
        modulo_composicao._adquirir_inventario_via_corredor(contexto, ContextoCicloPrestacao((2026, 7)))
    finally:
        modulo_composicao.executar_documento_readonly = original

    assert len(capturados) == 2
    for contexto_corredor in capturados:
        assert tuple(contexto_corredor.candidatos_colaborador) == (_CANDIDATO,)
        assert not any(isinstance(c, str) for c in contexto_corredor.candidatos_colaborador)
        assert contexto_corredor.fonte_vinculos is contexto.fonte_vinculos
        assert contexto_corredor.fonte_unidade_posto is contexto.fonte_unidade_posto
        assert contexto_corredor.politica_competencia is not None


# ---------------------------------------------------------------------
# Caso 1 -- sem fontes semânticas: fail-closed, sem exceção engolida.
# ---------------------------------------------------------------------

def test_sem_fontes_semanticas_nao_avanca_e_nao_quebra_o_corredor(caplog):
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    with caplog.at_level(logging.ERROR, logger=modulo_composicao.__name__):
        (resultado,) = _adquirir(ambiente, _necessidade_holerite())
        prontos = resultados_aquisicao_prontos_por_cliente(ambiente.contexto())
        acoes = ambiente.executar_ate_pending(ambiente.contexto())

    estado, dimensoes = _estados_dimensoes(resultado)
    assert _eventos_corredor_falhou(caplog) == []  # antes do J1: AttributeError aqui
    assert estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    assert dimensoes[DimensaoResolucao.COLABORADOR] != EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.CLIENTE] != EstadoResolucaoDimensao.RESOLVIDA
    assert prontos == ()
    assert acoes == ()
    assert ambiente.conexao.linhas == {}


# ---------------------------------------------------------------------
# Caso 2 -- candidato correto, vínculo/unidade ausentes: nada fabricado.
# ---------------------------------------------------------------------

def test_candidato_correto_sem_vinculo_nem_unidade_nao_fabrica_cliente():
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    fontes = dict(candidatos_colaborador=(_CANDIDATO,))
    (resultado,) = _adquirir(ambiente, _necessidade_holerite(), **fontes)

    estado, dimensoes = _estados_dimensoes(resultado)
    assert estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    assert dimensoes[DimensaoResolucao.COLABORADOR] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.CLIENTE] == EstadoResolucaoDimensao.NAO_AVALIADA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_AVALIADA
    assert resultados_aquisicao_prontos_por_cliente(ambiente.contexto(**fontes)) == ()
    assert ambiente.executar_ate_pending(ambiente.contexto(**fontes)) == ()


def test_com_vinculo_mas_sem_unidade_posto_continua_em_revisao():
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    fontes = dict(candidatos_colaborador=(_CANDIDATO,), fonte_vinculos=_FonteVinculos())
    (resultado,) = _adquirir(ambiente, _necessidade_holerite(), **fontes)

    estado, dimensoes = _estados_dimensoes(resultado)
    assert estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    assert dimensoes[DimensaoResolucao.CLIENTE] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_AVALIADA
    assert ambiente.executar_ate_pending(ambiente.contexto(**fontes)) == ()


# ---------------------------------------------------------------------
# Caso 3 -- todas as fontes: corredor real resolve e o fluxo chega a
# PENDING, com replay idempotente.
# ---------------------------------------------------------------------

def test_todas_as_fontes_corredor_real_resolve_todas_as_dimensoes(caplog):
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    with caplog.at_level(logging.ERROR, logger=modulo_composicao.__name__):
        (resultado,) = _adquirir(ambiente, _necessidade_holerite(), **_todas_as_fontes())

    estado, dimensoes = _estados_dimensoes(resultado)
    assert _eventos_corredor_falhou(caplog) == []
    assert estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    for dimensao in (
        DimensaoResolucao.TIPO_DOCUMENTAL, DimensaoResolucao.COMPETENCIA, DimensaoResolucao.COLABORADOR,
        DimensaoResolucao.CLIENTE, DimensaoResolucao.UNIDADE_POSTO,
    ):
        assert dimensoes[dimensao] == EstadoResolucaoDimensao.RESOLVIDA, dimensao


def test_todas_as_fontes_fluxo_real_ate_pending_sem_nenhum_patch():
    """Necessidade -> candidato em memória -> PDF real -> extração real ->
    corredor real -> âncora real -> readiness PRONTO -> Ordem -> Contato
    Canônico -> Orquestrador -> PENDING. `politica_competencia` NÃO é
    informada de propósito (defeito 3 do J1)."""
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    contexto = ambiente.contexto(**_todas_as_fontes())
    assert contexto.politica_competencia is None

    (resultado,) = ambiente.executar_ate_pending(contexto)

    assert resultado.funcionario_id == _COLABORADOR.entidade_id
    assert resultado.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING
    assert resultado.event_id
    assert resultado.envelope_sha256
    assert len(ambiente.conexao.linhas) == 2  # texto + documento


def test_replay_do_fluxo_real_nao_duplica_acao():
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))

    (primeiro,) = ambiente.executar_ate_pending(ambiente.contexto(**_todas_as_fontes()))
    (segundo,) = ambiente.executar_ate_pending(ambiente.contexto(**_todas_as_fontes()))

    assert primeiro.event_id == segundo.event_id
    assert primeiro.acao_persistida.acao_execucao_id == segundo.acao_persistida.acao_execucao_id
    assert len(ambiente.conexao.linhas) == 2  # texto + documento


# ---------------------------------------------------------------------
# Elegibilidade para distribuição (achado da revisão adversarial do J1):
# com o corredor real funcionando, candidatos em revisão ou resolvidos
# para OUTRA pessoa passaram a chegar em `resultados_aquisicao`.
# ---------------------------------------------------------------------

_CANDIDATO_OUTRO = CandidatoFuncionario(func_id='colab-outro', cpf='99988877766', nome_normalizado='CICRANO SINTETICO')
_TEXTO_HOLERITE_OUTRO = (
    'Recibo de Pagamento -- Total de Vencimentos\n'
    'Competência: 07/2026\n'
    'CPF: 999.888.777-66'
)


def _documentos_distribuiveis(contexto):
    return {
        ra.documento_id
        for _cliente, _competencia, resultados in resultados_aquisicao_prontos_por_cliente(contexto)
        for ra in resultados
    }


def test_candidato_em_revisao_nunca_entra_na_distribuicao(caplog):
    """`doc-ruim` tem CPF fora do universo de candidatos -> REVISAO; o
    cliente fica PRONTO pelo `doc-hol` válido, mas `doc-ruim` nunca é
    distribuído -- e a omissão é registrada, nunca silenciosa."""
    ambiente = _Ambiente((
        ('doc-hol', _pdf(_TEXTO_HOLERITE)), ('doc-ruim', _pdf(_TEXTO_HOLERITE_OUTRO)),
    ))
    with caplog.at_level(logging.WARNING, logger=modulo_composicao.__name__):
        distribuiveis = _documentos_distribuiveis(ambiente.contexto(**_todas_as_fontes()))

    assert distribuiveis == {'doc-hol'}
    assert [
        r.documento_id for r in caplog.records
        if getattr(r, 'evento', None) == modulo_composicao.EVENTO_DOCUMENTO_INELEGIVEL_DISTRIBUICAO
    ] == ['doc-ruim']


def test_documento_de_outro_colaborador_nunca_vai_para_a_ordem_da_necessidade():
    """A fonte de candidatos devolve, para a necessidade do colaborador
    A, também o holerite do colaborador B (resolvido de verdade para B).
    Nunca pode entrar na Ordem de A -- A recebe exatamente o próprio
    documento (preset UNITÁRIO chega a PENDING, o que só é possível com
    1 documento)."""
    ambiente = _Ambiente((
        ('doc-hol', _pdf(_TEXTO_HOLERITE)), ('doc-outro', _pdf(_TEXTO_HOLERITE_OUTRO)),
    ))
    fontes = dict(_todas_as_fontes(), candidatos_colaborador=(_CANDIDATO, _CANDIDATO_OUTRO))

    assert _documentos_distribuiveis(ambiente.contexto(**fontes)) == {'doc-hol'}
    (resultado,) = ambiente.executar_ate_pending(ambiente.contexto(**fontes))
    assert resultado.funcionario_id == _COLABORADOR.entidade_id
    assert resultado.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING


# ---------------------------------------------------------------------
# Granularidade cliente -- `fonte_cliente_direto` só resolve com
# evidência do próprio texto.
# ---------------------------------------------------------------------

def _necessidade_extrato():
    return NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste-j1',
    )


def test_extrato_com_fonte_cliente_direto_resolve_cliente_pelo_texto():
    ambiente = _Ambiente((('doc-ext', _pdf(_TEXTO_EXTRATO)),))
    (resultado,) = _adquirir(ambiente, _necessidade_extrato(), fonte_cliente_direto=_FonteClienteDireto())

    estado, dimensoes = _estados_dimensoes(resultado)
    assert estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert dimensoes[DimensaoResolucao.CLIENTE] == EstadoResolucaoDimensao.RESOLVIDA


def test_extrato_sem_fonte_cliente_direto_nunca_fabrica_cliente():
    ambiente = _Ambiente((('doc-ext', _pdf(_TEXTO_EXTRATO)),))
    (resultado,) = _adquirir(ambiente, _necessidade_extrato())

    estado, dimensoes = _estados_dimensoes(resultado)
    assert estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert dimensoes[DimensaoResolucao.CLIENTE] != EstadoResolucaoDimensao.RESOLVIDA


# ---------------------------------------------------------------------
# Nenhuma dependência nova de Airtable/legado/transporte no módulo.
# ---------------------------------------------------------------------

def test_modulo_de_composicao_nao_importa_airtable_app_nem_transporte():
    arvore = ast.parse(inspect.getsource(modulo_composicao))
    modulos = {n.module for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names
    }
    proibidos = [
        m for m in modulos
        if 'airtable' in m.lower() or m == 'app' or m.startswith('app.')
        or 'evolution' in m.lower() or 'transporte' in m.lower() or 'ciclo_producao' in m
    ]
    assert proibidos == []


# =====================================================================
# Gate J1b -- distribuição POR COLABORADOR em clientes com N
# colaboradores prontos. Mesmo corredor real, sem nenhum `patch`.
# Unidade canônica: cliente + competência + colaborador (1 Ordem de
# destinatário único por colaborador). Documento de nível cliente nunca
# entra em Ordem de colaborador.
# =====================================================================

_COLABORADOR_B = ReferenciaCanonica('COLABORADOR', 'colab-b')
_COLABORADOR_C = ReferenciaCanonica('COLABORADOR', 'colab-c')
_CANDIDATO_B = CandidatoFuncionario(func_id='colab-b', cpf='22233344455', nome_normalizado='BELTRANO SINTETICO')
_CANDIDATO_C = CandidatoFuncionario(func_id='colab-c', cpf='33344455566', nome_normalizado='DEOCLECIO SINTETICO')
_CONTATOS_ABC = {
    _COLABORADOR.entidade_id: '5511999998888',
    _COLABORADOR_B.entidade_id: '5511988887777',
    _COLABORADOR_C.entidade_id: '5511977776666',
}
_DOCUMENTO_DE = {'colab-j1': 'doc-a', 'colab-b': 'doc-b', 'colab-c': 'doc-c'}
_CPF_FORMATADO_DE = {'colab-j1': '111.222.333-44', 'colab-b': '222.333.444-55', 'colab-c': '333.444.555-66'}


def _texto_holerite_cpf(cpf_formatado):
    return f'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: {cpf_formatado}'


def _pdfs_abc(*colaboradores):
    return tuple(
        (_DOCUMENTO_DE[c.entidade_id], _pdf(_texto_holerite_cpf(_CPF_FORMATADO_DE[c.entidade_id])))
        for c in colaboradores
    )


def _fontes_abc():
    return dict(_todas_as_fontes(), candidatos_colaborador=(_CANDIDATO, _CANDIDATO_B, _CANDIDATO_C))


def _documentos_por_funcionario(resultados):
    return {r.funcionario_id: set(r.documento_ids) for r in resultados}


def test_j1b_um_colaborador_preserva_a_identidade_do_caminho_anterior():
    """Caso 1: com 1 colaborador, o trio por colaborador é exatamente o
    trio por cliente de antes, e o `event_id` é o mesmo que a Ordem do
    caminho anterior produziria."""
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    contexto = ambiente.contexto(**_todas_as_fontes())
    ((cliente, competencia, por_cliente),) = resultados_aquisicao_prontos_por_cliente(contexto)
    assert resultados_aquisicao_prontos_por_colaborador(contexto) == ((cliente, competencia, por_cliente),)

    ordem_anterior = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=por_cliente, destinatario='5511999998888',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        mensagem_texto='Documento 2026-07',
    )
    (resultado,) = ambiente.executar_ate_pending(contexto)
    assert resultado.event_id == derivar_identidade_ordem_distribuicao(ordem_anterior)


def test_j1b_dois_colaboradores_do_mesmo_cliente_geram_duas_ordens_ate_pending():
    """Casos 2 e 9: PDF real -> corredor real -> readiness -> 1 Ordem
    por colaborador -> Contato Canônico -> Orquestrador -> PENDING."""
    ambiente = _Ambiente(
        _pdfs_abc(_COLABORADOR, _COLABORADOR_B),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
    )
    resultados = ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))

    assert _documentos_por_funcionario(resultados) == {'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}}
    assert all(r.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING for r in resultados)
    assert len({r.event_id for r in resultados}) == 2
    assert len(ambiente.conexao.linhas) == 4  # 2 Ordens x (texto + documento)


def test_j1b_tres_colaboradores_sem_logica_especial_para_dois():
    """Caso 3."""
    todos = (_COLABORADOR, _COLABORADOR_B, _COLABORADOR_C)
    ambiente = _Ambiente(_pdfs_abc(*todos), colaboradores=todos, contatos=_CONTATOS_ABC)
    resultados = ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))

    assert _documentos_por_funcionario(resultados) == {
        'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}, 'colab-c': {'doc-c'},
    }
    assert len({r.event_id for r in resultados}) == 3
    assert len(ambiente.conexao.linhas) == 6  # 3 Ordens x (texto + documento)


def test_j1b_documento_de_a_nunca_chega_a_ordem_nem_ao_contato_de_b():
    """Caso 4: a fonte de candidatos devolve TODOS os holerites para TODA
    necessidade do cliente (pior caso). Cada Ordem leva só o documento
    do próprio colaborador, e o destinatário resolvido para cada grupo é
    o contato daquele colaborador -- nunca o de outro."""
    todos = (_COLABORADOR, _COLABORADOR_B, _COLABORADOR_C)
    ambiente = _Ambiente(_pdfs_abc(*todos), colaboradores=todos, contatos=_CONTATOS_ABC)
    resolvedor_real = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=ambiente.repositorio_contato, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=lambda cliente, competencia: f'Documento {competencia.entidade_id}',
    )
    grupos = []

    def _resolvedor_espiao(cliente, competencia, resultados_aquisicao):
        parametros = resolvedor_real(cliente, competencia, resultados_aquisicao)
        grupos.append((
            {ra.necessidade.colaborador.entidade_id for ra in resultados_aquisicao},
            {ra.documento_id for ra in resultados_aquisicao},
            parametros.destinatario,
        ))
        return parametros

    resultados = executar_prestacao_ate_distribuicao_documental_shadow(
        contexto=ambiente.contexto(**_fontes_abc()), resolver_parametros_ordem=_resolvedor_espiao,
        repositorio_documentos=ambiente.repositorio_documentos, armazenamento=ambiente.armazenamento,
        materializador=None, porta_assinatura=None,
        repositorio_execucoes=ambiente.repositorio_execucoes,
        repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
        repositorio_acoes=ambiente.repositorio_acoes,
        ator_referencia='ator:teste:j1b', proveniencia='teste_j1b', instante=AGORA,
    )

    assert sorted(grupos, key=lambda g: sorted(g[0])) == [
        ({'colab-b'}, {'doc-b'}, _CONTATOS_ABC['colab-b']),
        ({'colab-c'}, {'doc-c'}, _CONTATOS_ABC['colab-c']),
        ({'colab-j1'}, {'doc-a'}, _CONTATOS_ABC['colab-j1']),
    ]
    for resultado in resultados:
        assert set(resultado.documento_ids) == {_DOCUMENTO_DE[resultado.funcionario_id]}


def test_j1b_documento_em_revisao_continua_fora_e_os_demais_seguem():
    """Caso 5: um documento extra em REVISAO (CPF fora do universo) não
    entra em Ordem nenhuma; os 2 colaboradores válidos recebem as suas."""
    ambiente = _Ambiente(
        _pdfs_abc(_COLABORADOR, _COLABORADOR_B) + (('doc-ruim', _pdf(_TEXTO_HOLERITE_OUTRO)),),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
    )
    resultados = ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))

    assert _documentos_por_funcionario(resultados) == {'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}}


def test_j1b_readiness_continua_por_cliente():
    """Readiness do cliente nunca é confundida com elegibilidade
    individual: sem holerite válido de B, o pacote do cliente não fica
    PRONTO e NINGUÉM recebe Ordem (comportamento de readiness
    pré-existente, preservado)."""
    ambiente = _Ambiente(
        (('doc-a', _pdf(_TEXTO_HOLERITE)), ('doc-b-ruim', _pdf(_TEXTO_HOLERITE_OUTRO))),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
    )
    assert ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc())) == ()


def test_j1b_documento_de_nivel_cliente_nunca_entra_em_ordem_de_colaborador(caplog):
    """Caso 6: o Extrato (necessidade sem colaborador) participa da
    readiness e do pacote do cliente, mas não entra em Ordem de
    colaborador nenhuma -- nem duplicado entre todos, nem anexado a um.
    A omissão é registrada."""
    ambiente = _Ambiente(
        _pdfs_abc(_COLABORADOR, _COLABORADOR_B) + (('doc-ext', _pdf(_TEXTO_EXTRATO)),),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
        requisitos_base=(TIPO_HOLERITE, 'Extrato da Folha de Pagamento'),
    )
    contexto = ambiente.contexto(**_fontes_abc(), fonte_cliente_direto=_FonteClienteDireto())
    assert 'doc-ext' in _documentos_distribuiveis(contexto)  # elegível, parte do pacote do cliente

    with caplog.at_level(logging.INFO, logger=modulo_composicao.__name__):
        resultados = ambiente.executar_ate_pending(contexto)

    assert _documentos_por_funcionario(resultados) == {'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}}
    assert 'doc-ext' in {
        r.documento_id for r in caplog.records
        if getattr(r, 'evento', None) == EVENTO_DOCUMENTO_NIVEL_CLIENTE_FORA_ORDEM_COLABORADOR
    }


def test_j1b_replay_nao_duplica_ordens_eventos_nem_acoes():
    """Caso 7."""
    ambiente = _Ambiente(
        _pdfs_abc(_COLABORADOR, _COLABORADOR_B),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
    )
    primeira = ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))
    segunda = ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))

    assert [(r.funcionario_id, r.event_id, r.acao_persistida.acao_execucao_id) for r in primeira] == [
        (r.funcionario_id, r.event_id, r.acao_persistida.acao_execucao_id) for r in segunda
    ]
    assert len(ambiente.conexao.linhas) == 4  # 2 Ordens x (texto + documento)


def test_j1b_troca_de_contato_de_b_muda_so_a_identidade_de_b():
    """Caso 8: alteração legítima do destinatário de B gera outra
    identidade para B, sem tocar a de A e sem colisão."""
    def _eventos(contatos):
        ambiente = _Ambiente(
            _pdfs_abc(_COLABORADOR, _COLABORADOR_B),
            colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=contatos,
        )
        return {
            r.funcionario_id: r.event_id
            for r in ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))
        }

    antes = _eventos(_CONTATOS_ABC)
    depois = _eventos(dict(_CONTATOS_ABC, **{'colab-b': '5511966665555'}))

    assert antes['colab-j1'] == depois['colab-j1']
    assert antes['colab-b'] != depois['colab-b']
    assert len(set(antes.values()) | set(depois.values())) == 3


def test_j1b_ordem_de_listagem_dos_colaboradores_nao_altera_o_resultado():
    def _eventos(colaboradores):
        ambiente = _Ambiente(_pdfs_abc(*colaboradores), colaboradores=colaboradores, contatos=_CONTATOS_ABC)
        return [
            (r.funcionario_id, r.event_id)
            for r in ambiente.executar_ate_pending(ambiente.contexto(**_fontes_abc()))
        ]

    assert _eventos((_COLABORADOR, _COLABORADOR_B, _COLABORADOR_C)) == _eventos(
        (_COLABORADOR_C, _COLABORADOR_B, _COLABORADOR),
    )


def _resultado_manual(documento_id, colaborador, tipo=TIPO_HOLERITE):
    return ResultadoAquisicaoPorNecessidade(
        necessidade=NecessidadeDocumentoPrestacao(
            cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=tipo,
            motivo_exigencia='teste-j1b', colaborador=colaborador,
        ),
        documento_id=documento_id, hash_sha256='a' * 64,
    )


def test_j1b_particao_deduplica_documento_do_mesmo_colaborador_e_ordena_por_colaborador():
    """O mesmo documento que satisfaz 2 necessidades do MESMO
    colaborador aparece 1 vez no grupo; grupos saem em ordem
    determinística por colaborador; nível cliente fica fora."""
    resultados = (
        _resultado_manual('doc-b', _COLABORADOR_B),
        _resultado_manual('doc-a', _COLABORADOR),
        _resultado_manual('doc-a', _COLABORADOR, tipo='Folha de Ponto'),
        _resultado_manual('doc-ext', None, tipo='Extrato da Folha de Pagamento'),
    )
    grupos = _particionar_por_colaborador(_CLIENTE, _COMPETENCIA, resultados)

    assert [
        (tuple(ra.necessidade.colaborador.entidade_id for ra in g), tuple(ra.documento_id for ra in g))
        for _cliente, _competencia, g in grupos
    ] == [(('colab-b',), ('doc-b',)), (('colab-j1',), ('doc-a',))]


# =====================================================================
# Gate J1b hardening -- GENERICIDADE. Tipos arbitrários (DOCUMENTO_A..D
# nunca existiram na empresa): a partição por destinatário, a Ordem e o
# núcleo não dependem de nenhum nome de tipo documental. O tipo só entra
# na ELEGIBILIDADE da Prestação (pessoa certa + documento certo).
# =====================================================================

def _resolucao_sintetica(documento_id, *, tipo, colaborador):
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao, Cardinalidade, ConfiancaResolucao, EstadoResultadoSemantico, NivelConfianca,
        PerfilAplicabilidadeResolucao, RegraAplicabilidadeDimensao, ResultadoResolucaoSemantico,
    )
    dimensoes = (
        (DimensaoResolucao.TIPO_DOCUMENTAL, ReferenciaCanonica('TIPO_DOCUMENTAL', tipo)),
        (DimensaoResolucao.CLIENTE, _CLIENTE),
        (DimensaoResolucao.COMPETENCIA, _COMPETENCIA),
        (DimensaoResolucao.COLABORADOR, colaborador),
    )
    # Documento de nível cliente: sem dimensão COLABORADOR (nunca um valor fabricado).
    dimensoes = tuple((d, v) for d, v in dimensoes if v is not None)
    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id='resolver-generico-teste', resolver_version='1',
        politica_id='generica', politica_version='1',
        perfil=PerfilAplicabilidadeResolucao(
            perfil_id='generico-teste', version='1', escopo_documental='qualquer',
            regras=tuple(
                RegraAplicabilidadeDimensao(
                    dimensao=d, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA, cardinalidade=Cardinalidade(1, 1),
                ) for d, _ in dimensoes
            ),
        ),
        resolucoes=tuple(
            ResolucaoDimensao(
                dimensao=d, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(v,),
                confianca=ConfiancaResolucao(NivelConfianca.FORTE),
            ) for d, v in dimensoes
        ),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA, necessita_revisao_humana=False,
    )


def _resultado_arbitrario(ambiente, documento_id, *, tipo_necessidade, tipo_resolvido, colaborador):
    """1 `ResultadoAquisicaoPorNecessidade` com resolução RESOLVIDA
    sintética de tipo ARBITRÁRIO, apontando para um Documento real do
    ambiente."""
    from magnata_os.classificacao.orquestrador_corredor_readonly import ResultadoExecucaoCorredorPrestacao
    from magnata_os.classificacao.resolucao_documento_prestacao import ResultadoProcessamentoDocumentoPrestacao
    documento = next(d for d in ambiente.documentos if d.documento_id == documento_id)
    return ResultadoAquisicaoPorNecessidade(
        necessidade=NecessidadeDocumentoPrestacao(
            cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=tipo_necessidade,
            motivo_exigencia='teste-generico', colaborador=colaborador,
        ),
        documento_id=documento_id, hash_sha256=documento.hash_sha256,
        resultados_corredor=(ResultadoExecucaoCorredorPrestacao(
            resultado_corredor=ResultadoProcessamentoDocumentoPrestacao(
                documento_id=documento_id, estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
                tipo_documental=tipo_resolvido,
                resolucao_semantica=_resolucao_sintetica(documento_id, tipo=tipo_resolvido, colaborador=colaborador),
            ),
        ),),
    )


def _distribuir_grupos(ambiente, resultados):
    """Elegibilidade -> partição por destinatário -> 1 Ordem por grupo
    (preset genérico por cardinalidade) -> núcleo -> PENDING."""
    from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
        materializar_prestacao_distribuicao_documental_shadow,
    )
    elegiveis = tuple(r for r in resultados if modulo_composicao._elegivel_para_distribuicao(r))
    saida = []
    for _cliente, _competencia, grupo in _particionar_por_colaborador(_CLIENTE, _COMPETENCIA, elegiveis):
        colaborador_id = grupo[0].necessidade.colaborador.entidade_id
        saida.append(materializar_prestacao_distribuicao_documental_shadow(
            resultados_aquisicao=grupo, destinatario=_CONTATOS_ABC[colaborador_id],
            preset_id='DOCUMENTOS_SEM_ASSINATURA', tipo_documento='DOCUMENTOS_DIVERSOS',
            mensagem_texto='Seus documentos', repositorio_documentos=ambiente.repositorio_documentos,
            armazenamento=ambiente.armazenamento, materializador=None, porta_assinatura=None,
            repositorio_execucoes=ambiente.repositorio_execucoes,
            repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
            repositorio_acoes=ambiente.repositorio_acoes,
            ator_referencia='ator:teste:generico', proveniencia='teste_generico', instante=AGORA,
        ))
    return saida


def _ambiente_arbitrario():
    return _Ambiente(
        tuple((f'doc-{letra}', f'CONTEUDO-{letra}'.encode()) for letra in 'abcd'),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
    )


def _resultados_a_b_c_d(ambiente):
    def r(documento_id, tipo, colaborador):
        return _resultado_arbitrario(
            ambiente, documento_id, tipo_necessidade=tipo, tipo_resolvido=tipo, colaborador=colaborador,
        )
    return (
        r('doc-a', 'DOCUMENTO_A', _COLABORADOR), r('doc-b', 'DOCUMENTO_B', _COLABORADOR),
        r('doc-c', 'DOCUMENTO_C', _COLABORADOR_B), r('doc-d', 'DOCUMENTO_D', _COLABORADOR_B),
    )


def test_generico_um_destinatario_um_documento_arbitrario():
    """Teste A."""
    ambiente = _ambiente_arbitrario()
    (resultado,) = _distribuir_grupos(ambiente, _resultados_a_b_c_d(ambiente)[:1])
    assert resultado.documento_ids == ('doc-a',)
    assert [a.tipo for a in resultado.acoes_persistidas] == ['texto', 'documento']


def test_generico_um_destinatario_varios_documentos_arbitrarios_numa_so_distribuicao():
    """Teste B: DOCUMENTO_A + DOCUMENTO_B (+ o mesmo mecanismo para N)
    do mesmo destinatário formam UMA Ordem, com 1 ação por documento."""
    ambiente = _ambiente_arbitrario()
    (resultado,) = _distribuir_grupos(ambiente, _resultados_a_b_c_d(ambiente)[:2])
    assert resultado.documento_ids == ('doc-a', 'doc-b')
    assert [a.tipo for a in resultado.acoes_persistidas] == ['texto', 'documento', 'documento']
    assert resultado.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING


def test_generico_dois_destinatarios_sem_vazamento():
    """Teste C: A recebe A/B, B recebe C/D -- nada cruza."""
    ambiente = _ambiente_arbitrario()
    resultados = _distribuir_grupos(ambiente, _resultados_a_b_c_d(ambiente))
    assert {r.funcionario_id: r.documento_ids for r in resultados} == {
        'colab-b': ('doc-c', 'doc-d'), 'colab-j1': ('doc-a', 'doc-b'),
    }
    conteudos_por_funcionario = {
        r.funcionario_id: {a.conteudo_sha256 for a in r.acoes_persistidas if a.conteudo_sha256} for r in resultados
    }
    hashes = {d.documento_id: d.hash_sha256 for d in ambiente.documentos}
    assert conteudos_por_funcionario == {
        'colab-j1': {hashes['doc-a'], hashes['doc-b']}, 'colab-b': {hashes['doc-c'], hashes['doc-d']},
    }


def test_generico_pessoa_certa_documento_errado_e_fail_closed():
    """Teste D (tipos arbitrários): o documento de A resolvido como
    DOCUMENTO_B nunca atende a necessidade DOCUMENTO_A de A."""
    ambiente = _ambiente_arbitrario()
    errado = _resultado_arbitrario(
        ambiente, 'doc-a', tipo_necessidade='DOCUMENTO_A', tipo_resolvido='DOCUMENTO_B', colaborador=_COLABORADOR,
    )
    certo = _resultado_arbitrario(
        ambiente, 'doc-a', tipo_necessidade='DOCUMENTO_A', tipo_resolvido='DOCUMENTO_A', colaborador=_COLABORADOR,
    )
    assert modulo_composicao._elegivel_para_distribuicao(errado) is False
    assert modulo_composicao._elegivel_para_distribuicao(certo) is True
    assert _distribuir_grupos(ambiente, (errado,)) == []


def test_pessoa_certa_documento_errado_com_o_corredor_real():
    """Teste D com o corredor REAL: o holerite real de A oferecido para
    uma necessidade de OUTRO tipo de A é inelegível; para a necessidade
    do próprio tipo, é elegível."""
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))

    def _necessidade(tipo):
        return NecessidadeDocumentoPrestacao(
            cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=tipo,
            motivo_exigencia='teste-j1b', colaborador=_COLABORADOR,
        )

    (para_outro_tipo,) = _adquirir(ambiente, _necessidade('Folha de Ponto'), **_todas_as_fontes())
    (para_o_proprio_tipo,) = _adquirir(ambiente, _necessidade(TIPO_HOLERITE), **_todas_as_fontes())
    # Tudo o mais é idêntico e válido -- o ÚNICO motivo da recusa é o tipo.
    estado, dimensoes = _estados_dimensoes(para_outro_tipo)
    assert estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert all(
        dimensoes[d] == EstadoResolucaoDimensao.RESOLVIDA
        for d in (DimensaoResolucao.CLIENTE, DimensaoResolucao.COMPETENCIA, DimensaoResolucao.COLABORADOR)
    )
    assert modulo_composicao._elegivel_para_distribuicao(para_outro_tipo) is False
    assert modulo_composicao._elegivel_para_distribuicao(para_o_proprio_tipo) is True


def test_generico_ordem_de_entrada_dos_documentos_nao_altera_a_identidade():
    """Teste H: a mesma entrada em ordens diferentes produz as mesmas
    Ordens (mesmo event_id) -- a posição do documento faz parte da
    identidade, então a partição a torna determinística."""
    def _eventos(inverter):
        ambiente = _ambiente_arbitrario()
        resultados = _resultados_a_b_c_d(ambiente)
        if inverter:
            resultados = tuple(reversed(resultados))
        return sorted((r.funcionario_id, r.event_id, r.documento_ids) for r in _distribuir_grupos(ambiente, resultados))

    assert _eventos(False) == _eventos(True)


def test_generico_replay_nao_duplica():
    """Teste I (tipos arbitrários, N documentos)."""
    ambiente = _ambiente_arbitrario()
    primeira = _distribuir_grupos(ambiente, _resultados_a_b_c_d(ambiente))
    segunda = _distribuir_grupos(ambiente, _resultados_a_b_c_d(ambiente))
    ids = lambda rs: sorted(a.acao_execucao_id for r in rs for a in r.acoes_persistidas)
    assert ids(primeira) == ids(segunda)
    assert len(ambiente.conexao.linhas) == 6  # 2 Ordens x (texto + 2 documentos)


def test_particao_e_elegibilidade_nao_decidem_por_nome_de_documento():
    """Prova de não acoplamento na camada da Prestação: a partição por
    destinatário e a checagem de tipo da elegibilidade não contêm nenhum
    nome documental concreto."""
    nomes_reais = ('holerite', 'folha', 'ponto', 'contrato', 'advert', 'extrato', 'fgts', 'rescis')
    for funcao in (
        modulo_composicao._particionar_por_colaborador,
        modulo_composicao._tipo_resolvido_atende_necessidade,
        modulo_composicao.resultados_aquisicao_prontos_por_colaborador,
    ):
        arvore = ast.parse(inspect.getsource(funcao).lstrip())
        corpo = arvore.body[0].body
        docstring = corpo[0].value if corpo and isinstance(corpo[0], ast.Expr) else None
        literais = [
            no.value for no in ast.walk(arvore)
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and no is not docstring
        ]
        assert [l for l in literais if any(n in l.lower() for n in nomes_reais)] == [], funcao.__name__


# =====================================================================
# Prestação upstream real V1 -- PACOTE / INTENÇÃO DE NÍVEL CLIENTE.
# Documento sem colaborador ganha destino no domínio (intenção de
# cliente, sem funcionario_id, sem endereço, sem canal) e continua fora
# de toda Ordem de colaborador.
# =====================================================================

import dataclasses as _dataclasses  # noqa: E402

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (  # noqa: E402
    EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO,
    EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE,
    _separar_nivel_cliente,
    intencoes_distribuicao_cliente_prontas,
    resultados_aquisicao_prontos_nivel_cliente,
)
from magnata_os.classificacao.pacote_prestacao import PapelDestinatarioOrganizacional  # noqa: E402


def _ambiente_com_extrato(*, colaboradores=(_COLABORADOR, _COLABORADOR_B)):
    return _Ambiente(
        _pdfs_abc(*colaboradores) + (('doc-ext', _pdf(_TEXTO_EXTRATO)),),
        colaboradores=colaboradores, contatos=_CONTATOS_ABC,
        requisitos_base=(TIPO_HOLERITE, 'Extrato da Folha de Pagamento'),
    )


def _contexto_com_extrato(ambiente):
    return ambiente.contexto(**_fontes_abc(), fonte_cliente_direto=_FonteClienteDireto())


def _trocar_cliente(resultado, cliente):
    return _dataclasses.replace(
        resultado, necessidade=_dataclasses.replace(resultado.necessidade, cliente=cliente),
    )


def test_nivel_cliente_corredor_real_gera_uma_intencao_de_cliente_e_zero_ordem_de_colaborador():
    """PDF real -> corredor real -> readiness PRONTO -> Extrato vira
    intenção do CLIENTE; os holerites viram as Ordens dos colaboradores;
    nenhum documento cruza de uma granularidade para a outra."""
    ambiente = _ambiente_com_extrato()
    contexto = _contexto_com_extrato(ambiente)

    (intencao,) = intencoes_distribuicao_cliente_prontas(contexto)
    assert (intencao.cliente, intencao.competencia) == (_CLIENTE, _COMPETENCIA)
    assert intencao.documento_ids == ('doc-ext',)
    assert intencao.documentos[0].tipos_documentais == ('Extrato da Folha de Pagamento',)
    assert intencao.papel_destinatario == PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL

    ordens = ambiente.executar_ate_pending(contexto)
    assert _documentos_por_funcionario(ordens) == {'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}}
    assert not {'doc-a', 'doc-b'} & set(intencao.documento_ids)


def test_nivel_cliente_replay_mantem_a_mesma_intencao():
    ambiente = _ambiente_com_extrato()
    primeira = intencoes_distribuicao_cliente_prontas(_contexto_com_extrato(ambiente))
    segunda = intencoes_distribuicao_cliente_prontas(_contexto_com_extrato(ambiente))
    assert len(primeira) == 1
    assert [i.intencao_id for i in primeira] == [i.intencao_id for i in segunda]


def test_nivel_cliente_readiness_nao_pronto_nao_gera_intencao():
    """Holerite de B inválido: o pacote do cliente não fica PRONTO --
    nem Ordem de colaborador, nem intenção de cliente (mesmo gate)."""
    ambiente = _Ambiente(
        (('doc-a', _pdf(_TEXTO_HOLERITE)), ('doc-b-ruim', _pdf(_TEXTO_HOLERITE_OUTRO)),
         ('doc-ext', _pdf(_TEXTO_EXTRATO))),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
        requisitos_base=(TIPO_HOLERITE, 'Extrato da Folha de Pagamento'),
    )
    assert intencoes_distribuicao_cliente_prontas(_contexto_com_extrato(ambiente)) == ()


def test_nivel_cliente_documento_sem_cliente_comprovado_nao_entra_na_intencao():
    """Sem `fonte_cliente_direto` o Extrato não resolve CLIENTE: fica
    inelegível, o cliente não fica PRONTO e nada é fabricado."""
    ambiente = _ambiente_com_extrato()
    assert intencoes_distribuicao_cliente_prontas(ambiente.contexto(**_fontes_abc())) == ()


def test_nivel_cliente_documento_que_identifica_colaborador_fica_fora_da_intencao(caplog):
    """Necessidade de nível cliente, mas a resolução do documento
    confirmou um colaborador: é documento de pessoa -- nunca vai ao
    pacote do cliente. Genérico (tipos arbitrários)."""
    ambiente = _ambiente_arbitrario()
    de_pessoa = _resultado_arbitrario(
        ambiente, 'doc-a', tipo_necessidade='DOCUMENTO_A', tipo_resolvido='DOCUMENTO_A', colaborador=_COLABORADOR,
    )
    de_pessoa = _dataclasses.replace(
        de_pessoa, necessidade=_dataclasses.replace(de_pessoa.necessidade, colaborador=None),
    )
    do_cliente = _resultado_arbitrario(
        ambiente, 'doc-b', tipo_necessidade='DOCUMENTO_B', tipo_resolvido='DOCUMENTO_B', colaborador=None,
    )
    with caplog.at_level(logging.WARNING, logger=modulo_composicao.__name__):
        separados = _separar_nivel_cliente(_CLIENTE, _COMPETENCIA, (de_pessoa, do_cliente))

    assert [r.documento_id for r in separados] == ['doc-b']
    assert [
        r.documento_id for r in caplog.records
        if getattr(r, 'evento', None) == EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE
    ] == ['doc-a']


def test_nivel_cliente_separacao_ignora_colaborador_e_e_deterministica():
    ambiente = _ambiente_arbitrario()

    def r(documento_id, tipo, colaborador=None):
        return _resultado_arbitrario(
            ambiente, documento_id, tipo_necessidade=tipo, tipo_resolvido=tipo, colaborador=colaborador,
        )

    resultados = (r('doc-d', 'DOCUMENTO_D'), r('doc-a', 'DOCUMENTO_A', _COLABORADOR), r('doc-c', 'DOCUMENTO_C'))
    esperado = ['doc-c', 'doc-d']
    assert [x.documento_id for x in _separar_nivel_cliente(_CLIENTE, _COMPETENCIA, resultados)] == esperado
    assert [x.documento_id for x in _separar_nivel_cliente(_CLIENTE, _COMPETENCIA, resultados[::-1])] == esperado


def test_nivel_cliente_erro_de_dominio_de_um_cliente_nao_para_os_demais(monkeypatch, caplog):
    """Isolamento por cliente: o trio do cliente X é inválido (resultado
    de outro cliente misturado) -> registrado; o cliente Y segue."""
    ambiente = _ambiente_arbitrario()
    cliente_y = ReferenciaCanonica('CLIENTE', 'cliente-y')
    bom = _resultado_arbitrario(
        ambiente, 'doc-b', tipo_necessidade='DOCUMENTO_B', tipo_resolvido='DOCUMENTO_B', colaborador=None,
    )
    bom_y = _trocar_cliente(bom, cliente_y)
    monkeypatch.setattr(modulo_composicao, 'resultados_aquisicao_prontos_nivel_cliente', lambda contexto: (
        (_CLIENTE, _COMPETENCIA, (bom, bom_y)),  # resultado de cliente-y misturado no trio de _CLIENTE
        (cliente_y, _COMPETENCIA, (bom_y,)),
    ))
    with caplog.at_level(logging.ERROR, logger=modulo_composicao.__name__):
        intencoes = intencoes_distribuicao_cliente_prontas(object())

    assert [i.cliente for i in intencoes] == [cliente_y]
    assert [
        r.cliente for r in caplog.records
        if getattr(r, 'evento', None) == EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO
    ] == [_CLIENTE.entidade_id]


def test_nivel_cliente_erro_sistemico_propaga(monkeypatch):
    def _quebra(contexto):
        raise ConnectionError('fonte indisponivel')

    monkeypatch.setattr(modulo_composicao, 'resultados_aquisicao_prontos_nivel_cliente', _quebra)
    with pytest.raises(ConnectionError):
        intencoes_distribuicao_cliente_prontas(object())


def test_nivel_cliente_resultados_prontos_so_trazem_necessidades_sem_colaborador():
    ambiente = _ambiente_com_extrato()
    trios = resultados_aquisicao_prontos_nivel_cliente(_contexto_com_extrato(ambiente))
    assert [(c, k, tuple(r.documento_id for r in rs)) for c, k, rs in trios] == [
        (_CLIENTE, _COMPETENCIA, ('doc-ext',)),
    ]
    assert all(r.necessidade.colaborador is None for _c, _k, rs in trios for r in rs)


def test_nivel_cliente_separacao_e_intencao_nao_decidem_por_nome_de_documento():
    nomes_reais = (
        'holerite', 'folha', 'ponto', 'contrato', 'advert', 'extrato', 'fgts', 'rescis', 'dctf', 'certid',
    )
    for funcao in (
        modulo_composicao._separar_nivel_cliente,
        modulo_composicao._documento_identifica_colaborador,
        modulo_composicao.resultados_aquisicao_prontos_nivel_cliente,
        modulo_composicao.intencoes_distribuicao_cliente_prontas,
        modulo_composicao.particionar_nivel_cliente,
        modulo_composicao.intencoes_distribuicao_cliente_de_trios,
    ):
        arvore = ast.parse(inspect.getsource(funcao).lstrip())
        corpo = arvore.body[0].body
        docstring = corpo[0].value if corpo and isinstance(corpo[0], ast.Expr) else None
        literais = [
            no.value for no in ast.walk(arvore)
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and no is not docstring
        ]
        assert [l for l in literais if any(n in l.lower() for n in nomes_reais)] == [], funcao.__name__


@pytest.mark.parametrize('estado', [
    EstadoResolucaoDimensao.NAO_ENCONTRADA,
    EstadoResolucaoDimensao.AMBIGUA,
    EstadoResolucaoDimensao.NAO_AVALIADA,
])
def test_nivel_cliente_colaborador_nao_confirmado_tambem_fica_fora_da_intencao(estado):
    """Fail-closed por si só: a dimensão COLABORADOR existir (mesmo sem
    valor confirmado) já prova granularidade de pessoa -- não depende de
    a elegibilidade ter barrado antes."""
    ambiente = _ambiente_arbitrario()
    base = _resultado_arbitrario(
        ambiente, 'doc-a', tipo_necessidade='DOCUMENTO_A', tipo_resolvido='DOCUMENTO_A', colaborador=_COLABORADOR,
    )
    (execucao,) = base.resultados_corredor
    resolucao = execucao.resultado_corredor.resolucao_semantica
    resolucao = _dataclasses.replace(resolucao, resolucoes=tuple(
        ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=estado)
        if r.dimensao == DimensaoResolucao.COLABORADOR else r
        for r in resolucao.resolucoes
    ))
    resultado = _dataclasses.replace(
        base,
        necessidade=_dataclasses.replace(base.necessidade, colaborador=None),
        resultados_corredor=(_dataclasses.replace(
            execucao, resultado_corredor=_dataclasses.replace(
                execucao.resultado_corredor, resolucao_semantica=resolucao,
            ),
        ),),
    )
    assert _separar_nivel_cliente(_CLIENTE, _COMPETENCIA, (resultado,)) == ()


def test_nivel_cliente_mesmo_snapshot_para_ordens_e_intencoes():
    """Composition root futuro: 1 cálculo de readiness -> Ordens de
    colaborador E intenções de cliente, sem recomputar o ciclo."""
    from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
        intencoes_distribuicao_cliente_de_trios,
        particionar_nivel_cliente,
    )
    ambiente = _ambiente_com_extrato()
    trios = resultados_aquisicao_prontos_por_cliente(_contexto_com_extrato(ambiente))

    por_colaborador = [
        g for c, k, rs in trios for g in _particionar_por_colaborador(c, k, rs)
    ]
    (intencao,) = intencoes_distribuicao_cliente_de_trios(particionar_nivel_cliente(trios))

    documentos_ordens = {r.documento_id for _c, _k, grupo in por_colaborador for r in grupo}
    assert documentos_ordens == {'doc-a', 'doc-b'}
    assert intencao.documento_ids == ('doc-ext',)
    assert intencao.intencao_id == intencoes_distribuicao_cliente_prontas(
        _contexto_com_extrato(ambiente))[0].intencao_id


# =====================================================================
# J3 -- ÍNDICE INTERNO Documento <-> escopo alimentando o ciclo real.
# Produtor = resultado do corredor real na ingestão (mesmo que alimenta o
# sink); consumidor = candidatos por necessidade sobre o índice. Nenhuma
# fonte de candidatos "em memória por cliente" -- só o índice.
# =====================================================================

from magnata_os.classificacao.competencia_esperada_prestacao import (  # noqa: E402
    POLITICA_COMPETENCIA_PRESTACAO_V1,
)
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (  # noqa: E402
    diagnosticar_prestacao_upstream,
)
from magnata_os.classificacao.correlacao_documento_prestacao import (  # noqa: E402
    RepositorioCorrelacaoDocumentoPrestacaoEmMemoria,
    registrar_correlacoes_do_corredor,
)
from magnata_os.classificacao.fonte_candidatos_documento_inventario_interna import (  # noqa: E402
    FonteCandidatosDocumentoInventarioInterna,
)
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria  # noqa: E402
from magnata_os.classificacao.orquestrador_corredor_readonly import (  # noqa: E402
    ContextoExecucaoCorredorPrestacao,
    executar_documento_readonly,
)


def _ingerir_no_indice(ambiente, indice, *, fonte_cliente_direto=None, candidatos=None):
    """Ingestão: cada Documento interno passa pelo corredor real SEM
    nenhuma necessidade (ciclo da competência, cliente não informado) e o
    produtor grava as relações sustentadas no índice."""
    candidatos = candidatos if candidatos is not None else (_CANDIDATO, _CANDIDATO_B, _CANDIDATO_C)
    for documento in ambiente.documentos:
        with ambiente.armazenamento.abrir_leitura(documento.hash_sha256) as arquivo:
            conteudo = arquivo.read()
        from magnata_os.documental.extracao_texto import extrair_texto_pdf
        contexto = ContextoExecucaoCorredorPrestacao(
            documento_id=documento.documento_id, hash_sha256=documento.hash_sha256,
            paginas=(extrair_texto_pdf(conteudo),), ciclo=ContextoCicloPrestacao((2026, 7)),
            cliente_do_ciclo=None, politica_competencia=POLITICA_COMPETENCIA_PRESTACAO_V1,
            candidatos_colaborador=candidatos, fonte_vinculos=_FonteVinculos(),
            fonte_cliente_direto=fonte_cliente_direto, fonte_unidade_posto=_FonteUnidadePosto(),
            fonte_candidatos_relacao=None, clientes_broadcast=(), identificar_pagina=None,
            personalizar_contexto_do_grupo=None, registrar_dados_correlacao=False,
            fonte_inventario_pacote=None, politica_requisitos=None,
        )
        resultados = executar_documento_readonly(contexto, InventarioPrestacaoEmMemoria())
        registrar_correlacoes_do_corredor(
            indice, documento_id=documento.documento_id, resultados_corredor=resultados, registrado_em=AGORA,
        )


def _indice_do_ambiente(ambiente):
    return RepositorioCorrelacaoDocumentoPrestacaoEmMemoria(
        documento_existe=lambda d: ambiente.repositorio_documentos.buscar_por_id(d) is not None,
    )


def _contexto_pelo_indice(ambiente, indice, **fontes):
    import dataclasses
    return dataclasses.replace(
        ambiente.contexto(**fontes),
        fonte_candidatos_por_necessidade=FonteCandidatosDocumentoInventarioInterna(
            fonte_inventario=indice, repositorio_documentos=ambiente.repositorio_documentos,
        ),
    )


def test_j3_indice_interno_alimenta_o_ciclo_ate_pronto_ordens_e_intencao_do_cliente():
    ambiente = _ambiente_com_extrato()
    indice = _indice_do_ambiente(ambiente)
    _ingerir_no_indice(ambiente, indice, fonte_cliente_direto=_FonteClienteDireto())

    contexto = _contexto_pelo_indice(ambiente, indice, **_fontes_abc(), fonte_cliente_direto=_FonteClienteDireto())
    diagnostico = diagnosticar_prestacao_upstream(contexto)

    (cliente,) = diagnostico.clientes
    assert cliente.estado_pacote == 'PRONTO'
    assert set(cliente.documentos_elegiveis) == {'doc-a', 'doc-b', 'doc-ext'}
    grupos = {g[0].necessidade.colaborador.entidade_id: {r.documento_id for r in g}
              for _c, _k, g in diagnostico.grupos_por_colaborador()}
    assert grupos == {'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}}
    (intencao,) = diagnostico.intencoes_cliente()
    assert intencao.documento_ids == ('doc-ext',)

    # As Ordens saem do MESMO snapshot, até PENDING (sem transporte).
    ordens = ambiente.executar_ate_pending_com_trios(contexto, diagnostico.trios_prontos)
    assert _documentos_por_funcionario(ordens) == {'colab-j1': {'doc-a'}, 'colab-b': {'doc-b'}}


def test_j3_documento_fora_do_indice_deixa_o_cliente_em_revisao_sem_fabricar():
    ambiente = _ambiente_com_extrato()
    indice = _indice_do_ambiente(ambiente)  # nada ingerido -> nenhum candidato
    diagnostico = diagnosticar_prestacao_upstream(
        _contexto_pelo_indice(ambiente, indice, **_fontes_abc(), fonte_cliente_direto=_FonteClienteDireto()),
    )
    (cliente,) = diagnostico.clientes
    assert cliente.estado_pacote == 'EM_REVISAO'
    assert 'sem_evidencia_documental_real' in cliente.motivos
    assert diagnostico.trios_prontos == () and diagnostico.intencoes_cliente() == ()


def test_j3_documento_de_a_indexado_nunca_e_candidato_da_necessidade_de_b():
    ambiente = _Ambiente(
        _pdfs_abc(_COLABORADOR, _COLABORADOR_B),
        colaboradores=(_COLABORADOR, _COLABORADOR_B), contatos=_CONTATOS_ABC,
    )
    indice = _indice_do_ambiente(ambiente)
    _ingerir_no_indice(ambiente, indice)
    fonte = FonteCandidatosDocumentoInventarioInterna(
        fonte_inventario=indice, repositorio_documentos=ambiente.repositorio_documentos,
    )

    def _candidatos(colaborador):
        return [d.documento_id for d in fonte.candidatos_para(NecessidadeDocumentoPrestacao(
            cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=TIPO_HOLERITE,
            motivo_exigencia='teste-j3', colaborador=colaborador,
        ))]

    assert _candidatos(_COLABORADOR) == ['doc-a']
    assert _candidatos(_COLABORADOR_B) == ['doc-b']


def test_j3_documento_em_revisao_na_ingestao_nao_vira_candidato():
    ambiente = _Ambiente((('doc-ruim', _pdf(_TEXTO_HOLERITE_OUTRO)),))  # CPF fora do universo
    indice = _indice_do_ambiente(ambiente)
    _ingerir_no_indice(ambiente, indice)
    assert indice.historico_do_documento('doc-ruim') == ()
