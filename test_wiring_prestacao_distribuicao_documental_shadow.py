"""Wiring Prestação de Contas -> Distribuição Documental Genérica V1.

Testa APENAS montagem/repasse deste elo -- as invariantes internas do
núcleo genérico (ordem dos efeitos, idempotência de token, replay,
malformação de link, etc.) já são provadas por
`test_wiring_distribuicao_documental_shadow.py` e não são duplicadas
aqui.
"""
import ast
import hashlib
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ResultadoAquisicaoPorNecessidade,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
from magnata_os.documental.modulo01.materializador_arquivo import ResultadoMaterializacao
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.eventos import EstadoExecucao, Sensibilidade, TipoEvento
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.politica_preset_distribuicao_documental import (
    PresetDistribuicaoDocumentalDesconhecido,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    DistribuicaoDocumentalError,
    InconsistenciaOrdemDocumento,
    ItemDocumentoOrdem,
    derivar_identidade_ordem_distribuicao,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    ColaboradorAusenteNaNecessidade,
    ColaboradorDivergenteEntreDocumentos,
    EventoCanonicoNaoAguardaGate,
    PrestacaoDistribuicaoDocumentalError,
    materializar_prestacao_distribuicao_documental_shadow,
    montar_evento_canonico_ordem_distribuicao_documental,
    montar_ordem_distribuicao_documental_de_prestacao,
    registrar_evento_canonico_ordem_distribuicao_documental_shadow,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------
# Fakes -- mesmos padrões já usados por test_wiring_distribuicao_
# documental_shadow.py, duplicados aqui deliberadamente para isolamento
# de teste (mesma convenção já usada no repo, ex.: cada arquivo `_real`
# define seus próprios `_kwargs()`/fakes).
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
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _MaterializadorFake:
    def __init__(self):
        self._por_chave = {}

    def materializar(self, *, documento, conteudo_bytes, funcionario_id):
        chave = (documento.hash_sha256, funcionario_id)
        if chave not in self._por_chave:
            self._por_chave[chave] = ResultadoMaterializacao(
                arquivo_record_id=f'recARQ{len(self._por_chave) + 1}',
                documento_id=documento.documento_id, funcionario_id=funcionario_id,
                hash_sha256=documento.hash_sha256, reutilizado=False,
            )
        return self._por_chave[chave]


class _PortaAssinaturaFake:
    def __init__(self):
        self._por_correlacao: dict = {}
        self.ordem_chamadas: list = []

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id, funcionario_id, tipo_documento, arquivo_record_ids):
        self.ordem_chamadas.append('criar_ou_recuperar')
        existente = self._por_correlacao.get(acao_execucao_id)
        if existente is not None:
            return existente
        obrigacao = ObrigacaoAssinatura(
            assinatura_id=f'rec-obg-{len(self._por_correlacao) + 1}',
            link=f'https://exemplo.invalid/assinatura/{token_reservado}',
            status='Pendente', tem_comprovante=False,
        )
        self._por_correlacao[acao_execucao_id] = obrigacao
        return obrigacao

    def consultar_por_correlacao(self, *, acao_execucao_id):
        self.ordem_chamadas.append('consultar_por_correlacao')
        return self._por_correlacao.get(acao_execucao_id)


def _preparar_documento(repositorio_documentos, armazenamento, *, documento_id, conteudo: bytes, nome_original='arquivo.pdf'):
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = Documento(
        documento_id=documento_id, arquivo_original='origem.pdf', nome_original=nome_original,
        mime_type='application/pdf', tamanho=len(conteudo), hash_sha256=hash_sha256, origem='teste',
        recebido_em=AGORA, lote_id=None, status=StatusDocumento.REGISTRADO,
        correlation_id='corr-1', criado_em=AGORA, atualizado_em=AGORA,
    )
    repositorio_documentos.salvar(documento)
    armazenamento.armazenar(hash_sha256, conteudo, documento.mime_type, documento.nome_original, documento.tamanho)
    return documento


def _colaborador(entidade_id='colab-1') -> ReferenciaCanonica:
    return ReferenciaCanonica('COLABORADOR', entidade_id)


def _necessidade(*, tipo_documental='HOLERITE', colaborador=None, cliente_id='cliente-1', competencia_id='2099-01'):
    return NecessidadeDocumentoPrestacao(
        cliente=ReferenciaCanonica('CLIENTE', cliente_id),
        competencia=ReferenciaCanonica('COMPETENCIA', competencia_id),
        tipo_documental=tipo_documental,
        motivo_exigencia='teste',
        colaborador=colaborador,
    )


def _resultado_aquisicao(documento, *, tipo_documental='HOLERITE', colaborador=None):
    return ResultadoAquisicaoPorNecessidade(
        necessidade=_necessidade(tipo_documental=tipo_documental, colaborador=colaborador),
        documento_id=documento.documento_id, hash_sha256=documento.hash_sha256,
    )


def _montar_dependencias():
    conexao = _Conexao()
    return {
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_execucoes': RepositorioExecucoesEmMemoria(),
        'repositorio_autorizacoes': RepositorioAutorizacoesGateEmMemoria(),
        'repositorio_acoes': RepositorioAcoesExecucaoPlanoPostgres(conexao),
    }, conexao


# ---------------------------------------------------------------------
# Correlação colaborador/documento
# ---------------------------------------------------------------------

def test_correlacao_colaborador_preservada_ate_funcionario_id():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-holerite-1', conteudo=b'holerite-conteudo',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-42'))

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        mensagem_texto='Segue seu documento:',
    )

    assert ordem.funcionario_id == 'colab-42'
    assert ordem.documentos == (
        ItemDocumentoOrdem(documento_id='doc-holerite-1', hash_sha256=documento.hash_sha256),
    )


def test_colaborador_ausente_falha_fechado():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-sem-colaborador', conteudo=b'sem-colaborador',
    )
    resultado = _resultado_aquisicao(documento, colaborador=None)

    with pytest.raises(ColaboradorAusenteNaNecessidade):
        montar_ordem_distribuicao_documental_de_prestacao(
            resultados_aquisicao=(resultado,), destinatario='5511999999999',
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='FGTS',
            mensagem_texto='Segue seu documento:',
        )


def test_colaboradores_divergentes_falha_fechado():
    deps, _conexao = _montar_dependencias()
    doc_a = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-a', conteudo=b'conteudo-a',
    )
    doc_b = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-b', conteudo=b'conteudo-b',
    )
    resultado_a = _resultado_aquisicao(doc_a, tipo_documental='HOLERITE', colaborador=_colaborador('colab-1'))
    resultado_b = _resultado_aquisicao(doc_b, tipo_documental='FOLHA_PONTO', colaborador=_colaborador('colab-2'))

    with pytest.raises(ColaboradorDivergenteEntreDocumentos):
        montar_ordem_distribuicao_documental_de_prestacao(
            resultados_aquisicao=(resultado_a, resultado_b), destinatario='5511999999999',
            preset_id='PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA', tipo_documento='HOLERITE_FOLHA_PONTO',
            mensagem_texto='Seus documentos:',
        )


# ---------------------------------------------------------------------
# Presets -- preset_id -> política, tipo_documento sempre opaco
# ---------------------------------------------------------------------

def test_preset_documento_unitario_sem_assinatura_repassa_politica_correta():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-1',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador())

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
        mensagem_texto='Segue:',
    )
    assert ordem.canal == 'WHATSAPP'
    assert ordem.exigir_assinatura is False
    assert ordem.exigir_comprovante is False
    assert ordem.politica_agrupamento == 'UNITARIO'


def test_preset_documento_unitario_com_assinatura_repassa_politica_correta():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-1',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador())

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA', tipo_documento='CONTRATO',
        mensagem_texto='Assine:',
    )
    assert ordem.exigir_assinatura is True
    assert ordem.exigir_comprovante is True
    assert ordem.politica_agrupamento == 'UNITARIO'


def test_preset_pacote_2_documentos_1_link_repassa_politica_correta():
    deps, _conexao = _montar_dependencias()
    doc_holerite = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-holerite', conteudo=b'holerite',
    )
    doc_ponto = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-ponto', conteudo=b'ponto',
    )
    colaborador = _colaborador('colab-9')
    resultado_holerite = _resultado_aquisicao(doc_holerite, tipo_documental='HOLERITE', colaborador=colaborador)
    resultado_ponto = _resultado_aquisicao(doc_ponto, tipo_documental='FOLHA_PONTO', colaborador=colaborador)

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado_holerite, resultado_ponto), destinatario='5511999999999',
        preset_id='PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA', tipo_documento='HOLERITE_FOLHA_PONTO',
        mensagem_texto='Seus documentos do mês:',
    )
    assert len(ordem.documentos) == 2
    assert ordem.funcionario_id == 'colab-9'
    assert ordem.exigir_assinatura is True
    assert ordem.exigir_comprovante is True
    assert ordem.politica_agrupamento == 'AGRUPADO_1_LINK'
    assert ordem.tipo_documento == 'HOLERITE_FOLHA_PONTO'


def test_preset_desconhecido_falha_fechado():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-1',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador())

    with pytest.raises(PresetDistribuicaoDocumentalDesconhecido):
        montar_ordem_distribuicao_documental_de_prestacao(
            resultados_aquisicao=(resultado,), destinatario='5511999999999',
            preset_id='PRESET_QUE_NAO_EXISTE', tipo_documento='HOLERITE',
            mensagem_texto='Segue:',
        )


@pytest.mark.parametrize('tipo_documento', ['EPI', 'NR01'])
def test_tipos_documentais_arbitrarios_usam_mesmo_preset_sem_alteracao_de_codigo(tipo_documento):
    """Prova de genericidade: nenhum `if tipo_documento` neste módulo --
    qualquer tipo novo funciona com o preset compatível."""
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id=f'doc-{tipo_documento}', conteudo=f'conteudo-{tipo_documento}'.encode(),
    )
    resultado = _resultado_aquisicao(documento, tipo_documental=tipo_documento, colaborador=_colaborador())

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento=tipo_documento,
        mensagem_texto='Segue:',
    )
    assert ordem.tipo_documento == tipo_documento
    assert ordem.politica_agrupamento == 'UNITARIO'


def test_mesmo_tipo_documento_usa_presets_diferentes():
    """`CONTRATO` pode ir sem ou com assinatura -- a decisão vem do
    preset escolhido pelo chamador, nunca de um mapeamento fixo por
    tipo_documento."""
    deps, _conexao = _montar_dependencias()
    doc_sem = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-contrato-sem', conteudo=b'contrato-sem-assinatura',
    )
    doc_com = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-contrato-com', conteudo=b'contrato-com-assinatura',
    )
    colaborador = _colaborador()

    ordem_sem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(_resultado_aquisicao(doc_sem, tipo_documental='CONTRATO', colaborador=colaborador),),
        destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
        tipo_documento='CONTRATO', mensagem_texto='Segue:',
    )
    ordem_com = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(_resultado_aquisicao(doc_com, tipo_documental='CONTRATO', colaborador=colaborador),),
        destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA',
        tipo_documento='CONTRATO', mensagem_texto='Assine:',
    )

    assert ordem_sem.tipo_documento == ordem_com.tipo_documento == 'CONTRATO'
    assert ordem_sem.exigir_assinatura is False
    assert ordem_com.exigir_assinatura is True


# ---------------------------------------------------------------------
# Integração com o núcleo -- monta e repassa, nunca duplica
# ---------------------------------------------------------------------

def test_e2e_n1_sem_assinatura_chega_pending_reutilizando_nucleo():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-e2e-sem-assinatura',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-e2e'))

    resultado_distribuicao = materializar_prestacao_distribuicao_documental_shadow(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
        mensagem_texto='Segue:', materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    assert resultado_distribuicao.funcionario_id == 'colab-e2e'
    assert resultado_distribuicao.assinatura_link is None
    assert resultado_distribuicao.acao_persistida.acao_execucao_id == resultado_distribuicao.acao_execucao_id


def test_e2e_n1_com_assinatura_chega_pending_com_link_reutilizando_nucleo():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-e2e-com-assinatura',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-e2e'))
    porta_assinatura = _PortaAssinaturaFake()

    resultado_distribuicao = materializar_prestacao_distribuicao_documental_shadow(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA', tipo_documento='CONTRATO',
        mensagem_texto='Assine:', materializador=_MaterializadorFake(),
        porta_assinatura=porta_assinatura,
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    assert resultado_distribuicao.assinatura_link is not None
    # autorização SEMPRE antes da obrigação -- invariante do núcleo,
    # reconfirmada aqui na integração real deste wiring.
    assert porta_assinatura.ordem_chamadas[0] == 'consultar_por_correlacao'
    assert 'criar_ou_recuperar' in porta_assinatura.ordem_chamadas


def test_e2e_n2_pacote_holerite_folha_ponto_chega_pending_com_link_unico():
    deps, _conexao = _montar_dependencias()
    doc_holerite = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-holerite', conteudo=b'holerite-e2e',
    )
    doc_ponto = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-ponto', conteudo=b'ponto-e2e',
    )
    colaborador = _colaborador('colab-e2e-n2')
    resultados = (
        _resultado_aquisicao(doc_holerite, tipo_documental='HOLERITE', colaborador=colaborador),
        _resultado_aquisicao(doc_ponto, tipo_documental='FOLHA_PONTO', colaborador=colaborador),
    )

    resultado_distribuicao = materializar_prestacao_distribuicao_documental_shadow(
        resultados_aquisicao=resultados, destinatario='5511999999999',
        preset_id='PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA', tipo_documento='HOLERITE_FOLHA_PONTO',
        mensagem_texto='Seus documentos do mês:', materializador=_MaterializadorFake(),
        porta_assinatura=_PortaAssinaturaFake(),
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    assert len(resultado_distribuicao.arquivo_record_ids) == 2
    assert resultado_distribuicao.assinatura_link is not None
    assert resultado_distribuicao.funcionario_id == 'colab-e2e-n2'


def test_replay_idempotente_mesmo_event_id_sem_duplicar():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-replay',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-replay'))
    kwargs = dict(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
        mensagem_texto='Segue:', materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    primeiro = materializar_prestacao_distribuicao_documental_shadow(**kwargs)
    segundo = materializar_prestacao_distribuicao_documental_shadow(**kwargs)

    assert primeiro.event_id == segundo.event_id
    assert primeiro.acao_execucao_id == segundo.acao_execucao_id
    # Gate J1b: todas as ações do plano são persistidas (texto + documento).
    assert len(_conexao.linhas) == 2


def test_documento_hash_divergente_propaga_erro_do_nucleo_sem_mascarar():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-real',
    )
    resultado_com_hash_errado = ResultadoAquisicaoPorNecessidade(
        necessidade=_necessidade(colaborador=_colaborador()),
        documento_id=documento.documento_id, hash_sha256='0' * 64,
    )

    with pytest.raises(InconsistenciaOrdemDocumento):
        materializar_prestacao_distribuicao_documental_shadow(
            resultados_aquisicao=(resultado_com_hash_errado,), destinatario='5511999999999',
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
            mensagem_texto='Segue:', materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
            **deps,
        )


# ---------------------------------------------------------------------
# Ponte Ordem -> Evento canônico (COMUNICACAO_SOLICITADA)
# ---------------------------------------------------------------------

def _ordem_minima(*, destinatario='5511999999999', funcionario_id='colab-evento-1'):
    return montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(
            ResultadoAquisicaoPorNecessidade(
                necessidade=_necessidade(colaborador=_colaborador(funcionario_id)),
                documento_id='doc-evento-1', hash_sha256='a' * 64,
            ),
        ),
        destinatario=destinatario, preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
        tipo_documento='COMUNICADO', mensagem_texto='Segue:',
    )


def test_evento_canonico_tem_campos_exatos():
    ordem = _ordem_minima()
    evento = montar_evento_canonico_ordem_distribuicao_documental(ordem=ordem, instante=AGORA)
    event_id_esperado = derivar_identidade_ordem_distribuicao(ordem)

    assert evento.event_id == event_id_esperado
    assert evento.event_type == TipoEvento.COMUNICACAO_SOLICITADA
    assert evento.source == 'distribuicao_documental'
    assert evento.entity_type == 'ORDEM_DISTRIBUICAO_DOCUMENTAL'
    assert evento.entity_id == event_id_esperado
    assert evento.payload_referencia == f'ordem:{event_id_esperado}'
    assert evento.correlation_id == 'funcionario:colab-evento-1'
    assert evento.sensibilidade == Sensibilidade.INTERNO
    assert evento.proveniencia == 'wiring_distribuicao_documental_shadow_v1'
    assert evento.occurred_at == AGORA
    assert evento.received_at == AGORA
    # nunca telefone/texto no envelope persistido
    assert '5511999999999' not in evento.payload_referencia
    assert 'Segue' not in evento.payload_referencia


def test_evento_canonico_exige_instante_com_timezone():
    """`DistribuicaoDocumentalError` (nunca `PrestacaoDistribuicaoDocumentalError`)
    -- esta validação vive agora no núcleo genérico
    (`wiring_distribuicao_documental_shadow.py`), extraída de lá desde
    que deixou de ter qualquer dependência real de Prestação."""
    ordem = _ordem_minima()
    with pytest.raises(DistribuicaoDocumentalError):
        montar_evento_canonico_ordem_distribuicao_documental(ordem=ordem, instante=datetime(2099, 1, 1))


def test_mesma_ordem_produz_mesmo_event_id_evento_diferente_produz_id_diferente():
    ordem_a = _ordem_minima(funcionario_id='colab-x')
    ordem_a_de_novo = _ordem_minima(funcionario_id='colab-x')
    ordem_b = _ordem_minima(funcionario_id='colab-y')

    evento_a = montar_evento_canonico_ordem_distribuicao_documental(ordem=ordem_a, instante=AGORA)
    evento_a2 = montar_evento_canonico_ordem_distribuicao_documental(ordem=ordem_a_de_novo, instante=AGORA)
    evento_b = montar_evento_canonico_ordem_distribuicao_documental(ordem=ordem_b, instante=AGORA)

    assert evento_a.event_id == evento_a2.event_id
    assert evento_a.event_id != evento_b.event_id


def test_registrar_evento_canonico_cria_execucao_em_waiting_gate():
    repositorio_execucoes = RepositorioExecucoesEmMemoria()
    ordem = _ordem_minima()

    execucao = registrar_evento_canonico_ordem_distribuicao_documental_shadow(
        ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=AGORA,
    )

    assert execucao.estado == EstadoExecucao.WAITING_GATE
    assert execucao.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
    assert execucao.event_id == derivar_identidade_ordem_distribuicao(ordem)
    persistido = repositorio_execucoes.buscar_por_event_id(execucao.event_id)
    assert persistido is not None
    assert persistido.estado == EstadoExecucao.WAITING_GATE


def test_registrar_evento_canonico_replay_nao_duplica():
    repositorio_execucoes = RepositorioExecucoesEmMemoria()
    ordem = _ordem_minima()

    primeiro = registrar_evento_canonico_ordem_distribuicao_documental_shadow(
        ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=AGORA,
    )
    segundo = registrar_evento_canonico_ordem_distribuicao_documental_shadow(
        ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=AGORA,
    )

    assert primeiro.event_id == segundo.event_id
    assert len(repositorio_execucoes.listar_todos()) == 1


def test_registrar_evento_canonico_concorrencia_nao_duplica():
    """Corrida em `criar_se_novo` -- só um vencedor cria a linha;
    nenhuma dupla materialização em `execucoes` (mesma técnica de prova
    já usada pelo núcleo do motor: threading.Barrier forçando a
    corrida).

    Achado real, não introduzido por esta ponte: `criar_se_novo`/
    `reivindicar_retry` são atômicos (lock explícito em `Repositorio
    Execucoes EmMemoria`), mas as transições internas de `Motor
    Orquestrador.processar` (RECEIVED -> VALIDATED -> CLASSIFIED ->
    WAITING_GATE) NÃO são -- um chamador que perde a corrida de criação
    pode observar `RegistroExecucao` num estado intermediário do
    vencedor (nunca duplicado, mas transitoriamente não-terminal), e
    nesse caso esta ponte falha fechado (`EventoCanonicoNaoAguardaGate`)
    em vez de prosseguir sobre uma garantia ainda não estabelecida --
    correto por construção, mas registrado aqui como comportamento
    pré-existente de `motor.py`/`repositorio_execucoes.py` (fora do
    escopo desta missão alterar). A invariante real e forte, provada
    abaixo, é: nenhuma segunda linha é criada, e o estado final
    (após toda a corrida) converge para `WAITING_GATE`."""
    import threading

    repositorio_execucoes = RepositorioExecucoesEmMemoria()
    ordem = _ordem_minima()
    n_threads = 8
    barreira = threading.Barrier(n_threads)
    resultados = []
    falhas_fail_closed = []

    def _tentar():
        barreira.wait()
        try:
            resultados.append(
                registrar_evento_canonico_ordem_distribuicao_documental_shadow(
                    ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=AGORA,
                )
            )
        except EventoCanonicoNaoAguardaGate as exc:
            falhas_fail_closed.append(exc)

    threads = [threading.Thread(target=_tentar) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Nenhuma segunda linha materializada -- a invariante que importa.
    assert len(repositorio_execucoes.listar_todos()) == 1
    assert len(resultados) + len(falhas_fail_closed) == n_threads
    if resultados:
        assert len({r.event_id for r in resultados}) == 1
    # Estado final, após a corrida, converge para WAITING_GATE -- o
    # vencedor sempre termina a sequência de transições.
    final = repositorio_execucoes.buscar_por_event_id(derivar_identidade_ordem_distribuicao(ordem))
    assert final.estado == EstadoExecucao.WAITING_GATE


def test_evento_canonico_fail_closed_quando_motor_nao_atinge_waiting_gate():
    """Prova de fail-closed: se o registro já existir em estado
    terminal (nunca WAITING_GATE), a ponte nunca finge sucesso --
    levanta `EventoCanonicoNaoAguardaGate` em vez de prosseguir para
    autorização/distribuição sobre uma garantia falsa."""
    import dataclasses as _dc

    repositorio_execucoes = RepositorioExecucoesEmMemoria()
    ordem = _ordem_minima()
    event_id = derivar_identidade_ordem_distribuicao(ordem)
    evento = montar_evento_canonico_ordem_distribuicao_documental(ordem=ordem, instante=AGORA)
    from magnata_os.orquestrador.motor import _serializar_evento
    from magnata_os.orquestrador.repositorio_execucoes import RegistroExecucao

    repositorio_execucoes.criar_se_novo(RegistroExecucao(
        event_id=event_id, event_type=evento.event_type.value,
        estado=EstadoExecucao.SUCCEEDED, nivel_autonomia=0, acao='',
        resultado=None, evidencia=None, attempt=0, next_retry_at=None,
        last_error_classe=None, last_error_at=None, criado_em=AGORA, atualizado_em=AGORA,
        evento_json=_serializar_evento(evento),
    ))

    # Evento duplicado num estado terminal diferente de WAITING_GATE
    # nunca deveria acontecer em uso normal (nenhuma Acao é registrada
    # para COMUNICACAO_SOLICITADA); simulado aqui só para provar que a
    # ponte falha fechado em vez de prosseguir silenciosamente.
    with pytest.raises(EventoCanonicoNaoAguardaGate):
        registrar_evento_canonico_ordem_distribuicao_documental_shadow(
            ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=AGORA,
        )


def test_ausencia_de_execucao_bloqueia_autorizacao_fail_closed():
    """Sem passar pela ponte (sem `execucoes` semeado), a autorização
    explícita via `registrar_decisao_gate_shadow` -- caminho canônico
    de gate humano para `COMUNICACAO_SOLICITADA` -- recusa fail-closed,
    provando que a linha em `execucoes` é pré-requisito real, não
    cosmético."""
    from magnata_os.orquestrador.autorizacao_gate import (
        AutorizacaoGateError, DecisaoGate, registrar_decisao_gate_shadow,
    )

    repositorio_execucoes = RepositorioExecucoesEmMemoria()
    repositorio_autorizacoes = RepositorioAutorizacoesGateEmMemoria()
    ordem = _ordem_minima()
    event_id = derivar_identidade_ordem_distribuicao(ordem)

    with pytest.raises(AutorizacaoGateError):
        registrar_decisao_gate_shadow(
            repositorio_execucoes=repositorio_execucoes,
            repositorio_autorizacoes=repositorio_autorizacoes,
            event_id=event_id, preview_id='preview-qualquer',
            decisao=DecisaoGate.AUTORIZADO, ator_referencia='ator:teste',
            proveniencia='teste_v1', instante=AGORA,
        )


# ---------------------------------------------------------------------
# E2E Postgres real/efêmero -- ponte Ordem -> Evento canônico ate PENDING
# ---------------------------------------------------------------------

@pytest.mark.skipif(
    not __import__('os').environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)
def test_e2e_postgres_real_ponte_execucoes_ate_pending_sem_seed_manual():
    """Prova a cadeia completa contra Postgres real/efêmero, migrations
    0001-0004: `execucoes` (COMUNICACAO_SOLICITADA, WAITING_GATE) ->
    `autorizacoes_gate` -> `acoes_execucao_plano` (PENDING) -- SEM
    nenhum `INSERT` manual de seed em `execucoes` (ao contrário de
    `test_wiring_distribuicao_documental_shadow_real.py`, que testa o
    núcleo isolado e por isso precisa de `_semear_execucao_se_ausente`):
    aqui é a PRÓPRIA ponte (`materializar_prestacao_distribuicao_
    documental_shadow`, que agora chama `registrar_evento_canonico_
    ordem_distribuicao_documental_shadow` antes do núcleo) quem fecha a
    FK. Núcleo genérico (`wiring_distribuicao_documental_shadow.py`)
    continua intocado -- reutilizado como está."""
    from pathlib import Path

    psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')
    from magnata_os.orquestrador.repositorio_autorizacoes_gate_postgres import (
        RepositorioAutorizacoesGatePostgres,
    )
    from magnata_os.orquestrador.repositorio_execucoes_postgres import RepositorioExecucoesPostgres
    from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
        EstadoAcaoExecucaoPlano,
    )

    raiz_migrations = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
    migrations = tuple(
        (raiz_migrations / nome).read_text(encoding='utf-8')
        for nome in (
            '0001_repositorio_execucoes.sql', '0002_autorizacoes_gate.sql',
            '0003_acoes_execucao_plano.sql', '0004_envelope_execucao_autorizada.sql',
        )
    )
    instante = datetime(2099, 3, 1, 12, 0, tzinfo=timezone.utc)
    destinatario = 'destinatario:e2e:ponte:evento:sintetico'

    def _aplicar_migrations_se_ausentes(conn):
        with conn.cursor() as cursor:
            for nome_tabela, migration in zip(
                ('execucoes', 'autorizacoes_gate', 'acoes_execucao_plano'), migrations[:3],
            ):
                cursor.execute("SELECT to_regclass(%s)", (f'magnata_orquestrador.{nome_tabela}',))
                if cursor.fetchone()[0] is None:
                    cursor.execute(migration)
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='magnata_orquestrador' "
                "AND table_name='acoes_execucao_plano' AND column_name='envelope_sha256'"
            )
            if cursor.fetchone() is None:
                cursor.execute(migrations[3])
        conn.commit()

    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    repositorio_documentos = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    try:
        _aplicar_migrations_se_ausentes(conn)
        documento = _preparar_documento(
            repositorio_documentos, armazenamento,
            documento_id='documento-e2e-ponte-evento', conteudo=b'e2e-ponte-evento-canonico-v1',
        )
        colaborador = _colaborador('colab-e2e-ponte-evento')
        resultado = _resultado_aquisicao(documento, colaborador=colaborador)

        repositorio_execucoes = RepositorioExecucoesPostgres(conn)
        repositorio_autorizacoes = RepositorioAutorizacoesGatePostgres(conn)
        repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conn)

        kwargs = dict(
            resultados_aquisicao=(resultado,), destinatario=destinatario,
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
            mensagem_texto='E2E sintético da ponte Ordem->Evento canônico.',
            repositorio_documentos=repositorio_documentos, armazenamento=armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_execucoes=repositorio_execucoes,
            repositorio_autorizacoes=repositorio_autorizacoes, repositorio_acoes=repositorio_acoes,
            ator_referencia='ator:e2e:ponte:evento', proveniencia='e2e_ponte_evento_v1',
            instante=instante,
        )

        primeiro = materializar_prestacao_distribuicao_documental_shadow(**kwargs)
        segundo = materializar_prestacao_distribuicao_documental_shadow(**kwargs)

        assert primeiro.event_id == segundo.event_id
        assert primeiro.acao_execucao_id == segundo.acao_execucao_id
        assert primeiro.assinatura_link is None

        execucao = repositorio_execucoes.buscar_por_event_id(primeiro.event_id)
        assert execucao is not None
        assert execucao.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
        assert execucao.estado == EstadoExecucao.WAITING_GATE

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM magnata_orquestrador.execucoes WHERE event_id = %s',
                (primeiro.event_id,),
            )
            (quantidade_execucoes,) = cursor.fetchone()
        assert quantidade_execucoes == 1  # replay nao duplicou execucoes

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM magnata_orquestrador.autorizacoes_gate WHERE event_id = %s',
                (primeiro.event_id,),
            )
            (quantidade_autorizacoes,) = cursor.fetchone()
        assert quantidade_autorizacoes == 1  # replay nao duplicou autorizacao

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*), MAX(estado) FROM magnata_orquestrador.acoes_execucao_plano '
                'WHERE acao_execucao_id = %s',
                (primeiro.acao_execucao_id,),
            )
            quantidade_acoes, estado_acao = cursor.fetchone()
        assert quantidade_acoes == 1  # replay nao duplicou a acao PENDING
        assert estado_acao == EstadoAcaoExecucaoPlano.PENDING.value
    finally:
        conn.close()


def test_zero_import_de_transporte_ou_evolution_neste_wiring():
    """Checagem estrutural via AST (mesma técnica de
    `test_wiring_distribuicao_documental_shadow.py::
    test_modulo_nunca_importa_nem_chama_transporte_real`) -- imune a
    aliasing (`import requests as r`) ou uso indireto via atributo, ao
    contrário de uma busca textual simples."""
    import magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow as modulo
    caminho = modulo.__file__
    with open(caminho, 'r', encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=caminho)
    proibidos = {
        'requests', 'boto3', 'psycopg',
        'transporte_real_habilitado', 'compor_porta_execucao',
        'ExecutorEvolutionLegado', 'executar_plano_disparo',
        'gerar_token_reservado_csprng',
    }
    nomes_encontrados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes_encontrados.update(alias.name.split('.')[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            nomes_encontrados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.Name):
            nomes_encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes_encontrados.add(no.attr)
    assert proibidos.isdisjoint(nomes_encontrados)
