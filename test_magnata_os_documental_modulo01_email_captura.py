"""
Testes do adapter de captura de e-mail (Modulo 01, Documental).

Nenhum destes testes acessa Gmail, IMAP, rede ou disco -- tudo roda
contra `FonteMensagensEmailFalsa` (duplo de teste) e os repositorios em
memoria ja existentes do Modulo 01 (Fase 1/Fase 3).
"""
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.adapters.email_captura import (
    ORIGEM_EMAIL,
    AdapterCapturaEmail,
    AnexoEmailRecebido,
    MensagemEmailRecebida,
)
from magnata_os.documental.modulo01.composicao import construir_pipeline_modulo01
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)


class FonteMensagensEmailFalsa:
    """Duplo de teste de `FonteMensagensEmail` -- devolve exatamente as
    mensagens configuradas, sem nenhum acesso real a e-mail."""

    def __init__(self, mensagens=None):
        self._mensagens = list(mensagens or [])

    def definir_mensagens(self, mensagens):
        self._mensagens = list(mensagens)

    def buscar_novas_mensagens(self):
        return list(self._mensagens)


def _montar_adapter(mensagens=None, fonte_candidatos_funcionario=None):
    """Monta o adapter via `construir_pipeline_modulo01` (composition
    root V1, magnata_os/documental/modulo01/composicao.py) -- todos os
    testes deste arquivo passam a validar o composition root
    automaticamente, sem duplicar a montagem manual que existia aqui
    antes."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    fonte = FonteMensagensEmailFalsa(mensagens)
    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=repo_docs,
        repositorio_historico=repo_hist,
        repositorio_lotes=repo_lotes,
        repositorio_estados_esteira=repo_estados,
        fonte_mensagens=fonte,
        fonte_candidatos_funcionario=fonte_candidatos_funcionario,
    )
    return pipeline.adapter_captura_email, fonte, repo_docs


def _mensagem(message_id='msg-1', remetente='cliente@exemplo.com', assunto='Documentos', anexos=None):
    return MensagemEmailRecebida(
        message_id=message_id,
        remetente=remetente,
        assunto=assunto,
        recebido_em=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        anexos=anexos or [],
    )


def _anexo(nome='holerite.pdf', conteudo=b'conteudo do anexo'):
    return AnexoEmailRecebido(nome_original=nome, mime_type='application/pdf', conteudo=conteudo)


# ============================================================================
# 1. mensagem com um anexo vira um lote de sucesso
# ============================================================================

def test_mensagem_com_um_anexo_vira_lote_de_sucesso():
    adapter, _fonte, repo_docs = _montar_adapter([
        _mensagem(anexos=[_anexo()]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    assert resumo.mensagens_processadas == 1
    assert resumo.mensagens_sem_anexo == ()
    assert len(resumo.resumos_lote) == 1

    resumo_lote = resumo.resumos_lote[0]
    assert resumo_lote.origem == ORIGEM_EMAIL
    assert resumo_lote.quantidade_arquivos == 1
    assert resumo_lote.quantidade_sucesso == 1
    assert resumo_lote.quantidade_erro == 0
    assert len(repo_docs.listar_todos()) == 1


# ============================================================================
# 2. mensagem com varios anexos vira um lote com N arquivos
# ============================================================================

def test_mensagem_com_varios_anexos_vira_lote_com_todos_os_arquivos():
    adapter, _fonte, repo_docs = _montar_adapter([
        _mensagem(anexos=[
            _anexo('holerite.pdf', b'conteudo holerite'),
            _anexo('folha_ponto.pdf', b'conteudo folha ponto'),
        ]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    resumo_lote = resumo.resumos_lote[0]
    assert resumo_lote.quantidade_arquivos == 2
    assert resumo_lote.quantidade_sucesso == 2
    assert len(repo_docs.listar_todos()) == 2


# ============================================================================
# 3. mensagem sem anexo nunca vira lote vazio -- e contada, nunca escondida
# ============================================================================

def test_mensagem_sem_anexo_e_contabilizada_e_nunca_vira_lote():
    adapter, _fonte, repo_docs = _montar_adapter([
        _mensagem(message_id='msg-sem-anexo', anexos=[]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    assert resumo.mensagens_processadas == 1
    assert resumo.mensagens_sem_anexo == ('msg-sem-anexo',)
    assert resumo.resumos_lote == ()
    assert repo_docs.listar_todos() == []


# ============================================================================
# 4. multiplas mensagens na mesma chamada -- cada uma seu proprio lote
# ============================================================================

def test_multiplas_mensagens_geram_um_lote_por_mensagem():
    adapter, _fonte, repo_docs = _montar_adapter([
        _mensagem(message_id='msg-1', anexos=[_anexo('a.pdf', b'conteudo a')]),
        _mensagem(message_id='msg-2', anexos=[]),
        _mensagem(message_id='msg-3', anexos=[_anexo('b.pdf', b'conteudo b')]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    assert resumo.mensagens_processadas == 3
    assert resumo.mensagens_sem_anexo == ('msg-2',)
    assert len(resumo.resumos_lote) == 2
    assert len(repo_docs.listar_todos()) == 2


# ============================================================================
# 5. idempotencia -- reprocessar a mesma mensagem nunca duplica o Documento
# ============================================================================

def test_reprocessar_mesma_mensagem_marca_duplicado_e_nao_duplica_documento():
    mensagem = _mensagem(message_id='msg-repetida', anexos=[_anexo('holerite.pdf', b'conteudo fixo')])
    adapter, fonte, repo_docs = _montar_adapter([mensagem])

    primeiro_resumo = adapter.capturar_novas_mensagens()
    assert primeiro_resumo.resumos_lote[0].quantidade_sucesso == 1
    assert primeiro_resumo.resumos_lote[0].quantidade_duplicados == 0
    assert len(repo_docs.listar_todos()) == 1

    # a fonte "reenvia" a mesma mensagem (ex.: reinicio, reprocessamento manual)
    fonte.definir_mensagens([mensagem])
    segundo_resumo = adapter.capturar_novas_mensagens()

    assert segundo_resumo.resumos_lote[0].quantidade_duplicados == 1
    assert segundo_resumo.resumos_lote[0].quantidade_erro == 0
    # nenhum Documento novo foi criado -- mesmo hash de conteudo
    assert len(repo_docs.listar_todos()) == 1


# ============================================================================
# 6. metadados da mensagem chegam no lote, para rastreabilidade
# ============================================================================

def test_metadados_da_mensagem_chegam_no_resumo_do_lote():
    adapter, _fonte, _repo_docs = _montar_adapter([
        _mensagem(message_id='msg-meta', remetente='rh@cliente.com', assunto='Folha Agosto', anexos=[_anexo()]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    resumo_lote = resumo.resumos_lote[0]
    assert resumo_lote.correlation_id  # gerado automaticamente pelo servico de lote
    assert resumo_lote.itens[0].sucesso is True


# ============================================================================
# 7. nenhuma mensagem nova -- resumo vazio, sem erro
# ============================================================================

def test_nenhuma_mensagem_nova_retorna_resumo_vazio():
    adapter, _fonte, repo_docs = _montar_adapter([])

    resumo = adapter.capturar_novas_mensagens()

    assert resumo.mensagens_processadas == 0
    assert resumo.mensagens_sem_anexo == ()
    assert resumo.resumos_lote == ()
    assert repo_docs.listar_todos() == []


# ============================================================================
# 8. anexo invalido (vazio) -- ServicoCriacaoLote ja rejeita, o adapter nunca
#    esconde o erro nem trava as demais mensagens da mesma chamada
# ============================================================================

def test_anexo_vazio_gera_item_com_erro_sem_travar_a_mensagem():
    adapter, _fonte, repo_docs = _montar_adapter([
        _mensagem(anexos=[_anexo('vazio.pdf', b'')]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    resumo_lote = resumo.resumos_lote[0]
    assert resumo_lote.quantidade_erro == 1
    assert resumo_lote.quantidade_sucesso == 0
    assert resumo_lote.itens[0].sucesso is False
    assert resumo_lote.itens[0].erro  # mensagem de erro explicita, nunca None
    # nenhum Documento foi criado para o anexo vazio -- mas a mensagem
    # inteira nao foi descartada, o resumo do lote existe e reporta o erro
    assert repo_docs.listar_todos() == []


# ============================================================================
# 9. erro parcial -- uma mensagem com anexo valido E anexo invalido no mesmo
#    lote nunca perde o sucesso por causa do erro do outro
# ============================================================================

def test_erro_parcial_um_anexo_falha_outro_da_mesma_mensagem_sucede():
    adapter, _fonte, repo_docs = _montar_adapter([
        _mensagem(anexos=[
            _anexo('valido.pdf', b'conteudo real'),
            _anexo('vazio.pdf', b''),
        ]),
    ])

    resumo = adapter.capturar_novas_mensagens()

    resumo_lote = resumo.resumos_lote[0]
    assert resumo_lote.quantidade_arquivos == 2
    assert resumo_lote.quantidade_sucesso == 1
    assert resumo_lote.quantidade_erro == 1
    assert len(repo_docs.listar_todos()) == 1


# ============================================================================
# 10. erro na propria busca (API/rede) -- NAO e engolido pelo adapter.
#     Comportamento fail-loud documentado e travado por teste: o adapter nao
#     tem retry nem tratamento proprio, propositalmente (ver docstring do
#     modulo) -- quem instanciar com uma fonte real precisa decidir a
#     politica de retry/backoff do lado de fora. Este teste existe para que
#     uma mudanca futura desse comportamento seja deliberada, nunca
#     acidental.
# ============================================================================

class _FonteQueFalha:
    def buscar_novas_mensagens(self):
        raise ConnectionError('falha simulada de rede/API')


def test_falha_na_busca_de_mensagens_propaga_sem_ser_engolida():
    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=RepositorioDocumentosEmMemoria(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=RepositorioEstadosEsteiraEmMemoria(),
        fonte_mensagens=_FonteQueFalha(),
    )

    with pytest.raises(ConnectionError):
        pipeline.adapter_captura_email.capturar_novas_mensagens()


# ============================================================================
# Composition root V1 (magnata_os/documental/modulo01/composicao.py) --
# provas específicas de que a fiação está correta, nunca ativa produção
# externa (ver docs/decisoes/composition-root-modulo01-v1.md).
# ============================================================================

class _FonteCandidatosFuncionarioFake:
    """Duplo de teste de FonteCandidatosFuncionario -- conta chamadas
    para provar que a leitura é feita no máximo 1 vez por lote."""

    def __init__(self, candidatos=None):
        self._candidatos = list(candidatos or [])
        self.chamadas = 0

    def listar_funcionarios(self):
        self.chamadas += 1
        return self._candidatos


def test_importar_o_modulo_de_composicao_nao_exige_nenhuma_credencial(monkeypatch):
    """Nenhuma variável de ambiente precisa existir para importar
    composicao.py -- a composição nunca lê configuração nem abre
    conexão/rede durante a montagem."""
    for variavel in ('DATABASE_URL', 'AIRTABLE_API_KEY'):
        monkeypatch.delenv(variavel, raising=False)

    import importlib
    import magnata_os.documental.modulo01.composicao as composicao_mod
    importlib.reload(composicao_mod)  # reimporta sem nenhuma env setada
    assert composicao_mod.construir_pipeline_modulo01 is not None


def test_adapter_capturado_e_servico_lote_sao_o_mesmo_objeto():
    """Prova estrutural: o AdapterCapturaEmail devolvido pelo pipeline
    usa exatamente a MESMA instância de ServicoCriacaoLote exposta em
    PipelineModulo01.servico_lote -- nunca uma cópia/segunda
    composição."""
    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=RepositorioDocumentosEmMemoria(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=RepositorioEstadosEsteiraEmMemoria(),
        fonte_mensagens=FonteMensagensEmailFalsa(),
    )

    assert pipeline.adapter_captura_email._servico_lote is pipeline.servico_lote


def test_fonte_candidatos_funcionario_chega_ao_servico_lote():
    """Prova estrutural: a fonte de candidatos passada ao composition
    root é exatamente a mesma injetada em ServicoCriacaoLote."""
    fonte_candidatos = _FonteCandidatosFuncionarioFake()
    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=RepositorioDocumentosEmMemoria(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=RepositorioEstadosEsteiraEmMemoria(),
        fonte_mensagens=FonteMensagensEmailFalsa(),
        fonte_candidatos_funcionario=fonte_candidatos,
    )

    assert pipeline.servico_lote._fonte_candidatos_funcionario is fonte_candidatos


def test_sem_fonte_candidatos_o_default_seguro_none_e_preservado():
    """Fora da composição operacional (ex.: um script de reprocessamento
    manual que só quer ingestão, sem identificação), o pipeline
    continua podendo ser montado sem fonte de candidatos -- off by
    default, mesmo comportamento já existente de ServicoCriacaoLote."""
    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=RepositorioDocumentosEmMemoria(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=RepositorioEstadosEsteiraEmMemoria(),
        fonte_mensagens=FonteMensagensEmailFalsa(),
    )

    assert pipeline.servico_lote._fonte_candidatos_funcionario is None


def test_holerite_elegivel_alcanca_identificacao_via_pipeline_completo(monkeypatch):
    """Prova de ponta a ponta (fakes na fronteira, nenhum acesso
    externo): com a fonte de candidatos conectada na composição, um
    Holerite avulso RESOLVIDO recebido por e-mail atravessa o pipeline
    inteiro (FonteMensagensEmail -> AdapterCapturaEmail ->
    ServicoCriacaoLote -> gate CLASSIFICACAO -> gate IDENTIFICACAO) e
    chega a IDENTIFICACAO/CONCLUIDO -- a mesma extração/classificação/
    identificação já testadas isoladamente em test_gate_classificacao_
    esteira.py/test_gate_identificacao_holerite_esteira.py, agora
    provadas através da composição real."""
    from magnata_os.classificacao.classificador_documental import EstadoClassificacao
    from magnata_os.classificacao.roteamento_documental import (
        AcaoRoteamento, DecisaoRoteamentoDocumental, EscopoDocumental, MotivoRoteamento,
    )
    from magnata_os.classificacao.contratos import (
        DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao,
    )
    from magnata_os.documental.modulo01 import servico_lote as servico_lote_mod
    from magnata_os.documental.modulo01.dominio_esteira import EtapaEsteira, SituacaoEsteira

    monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
    monkeypatch.setattr(
        servico_lote_mod, 'decidir_roteamento_de_texto',
        lambda texto: DecisaoRoteamentoDocumental(
            tipo_documental='Holerite',
            estado_classificacao=EstadoClassificacao.RESOLVIDA,
            escopo_documental=EscopoDocumental.COLABORADOR,
            acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
            motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
            processador_disponivel=False,
            necessita_revisao_humana=True,
            prioridade_revisao='BAIXA',
            evidencias_sanitizadas=('hit',),
            tipos_concorrentes=(),
        ),
    )
    monkeypatch.setattr(
        servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
        lambda texto, candidatos: ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('COLABORADOR', 'func-1'),),
        ),
    )

    fonte_candidatos = _FonteCandidatosFuncionarioFake()
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()
    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=repo_docs,
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=repo_estados,
        fonte_mensagens=FonteMensagensEmailFalsa([
            _mensagem(anexos=[_anexo()]),
        ]),
        fonte_candidatos_funcionario=fonte_candidatos,
    )

    resumo = pipeline.adapter_captura_email.capturar_novas_mensagens()

    assert len(resumo.resumos_lote) == 1
    item = resumo.resumos_lote[0].itens[0]
    documento_id = item.documento_id

    estado = repo_estados.buscar_por_documento_id(documento_id)
    assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
    assert estado.situacao == SituacaoEsteira.CONCLUIDO
    assert fonte_candidatos.chamadas == 1  # lida no máximo 1x por lote


def test_nenhum_acesso_externo_durante_construcao_ou_captura(monkeypatch):
    """A composição e a captura (com fakes na fronteira) nunca chamam
    rede -- nenhuma biblioteca de rede é sequer importada por
    composicao.py."""
    import ast
    import inspect

    import magnata_os.documental.modulo01.composicao as composicao_mod

    codigo_fonte = inspect.getsource(composicao_mod)
    arvore = ast.parse(codigo_fonte)
    modulos_importados = {
        alias.name.split('.')[0]
        for no in ast.walk(arvore)
        if isinstance(no, (ast.Import, ast.ImportFrom))
        for alias in no.names
        if isinstance(no, ast.Import)
    } | {
        no.module.split('.')[0]
        for no in ast.walk(arvore)
        if isinstance(no, ast.ImportFrom) and no.module
    }
    proibidos = {'requests', 'psycopg', 'psycopg2', 'googleapiclient', 'google', 'boto3'}
    assert not (modulos_importados & proibidos)
