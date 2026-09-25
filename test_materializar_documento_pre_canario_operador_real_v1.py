"""E2E do Pré-Canário Seguro (V1 WhatsApp) com autorização humana REAL.

Prova a cadeia completa exigida pela missão de implementação:

    Prestação/corredor real (PR #183, reaproveitando `_Ambiente` de
    test_aquisicao_prestacao_corredor_real_j1.py, sem duplicar nenhum
    dos testes de elegibilidade já provados lá)
    -> Ordem (`montar_ordem_distribuicao_documental_de_prestacao`)
    -> Evento Canônico -> Grande Orquestrador -> WAITING_GATE
       (`registrar_evento_canonico_ordem_distribuicao_documental_shadow`)
    -> Preview -> autorização humana REAL
       (`materializar_documento_pre_canario_operador_real_v1`, NUNCA
       `materializar_prestacao_distribuicao_documental_shadow`/
       `autorizar_preview_assinatura_shadow`)
    -> Plano -> Envelope -> PENDING -> PARADA.

Mesmos repositórios em memória/fake DB-API do J1 (`_Ambiente`) --
nenhuma migration, nenhum Postgres real necessário para provar esta
etapa (a ação PENDING em si já é validada contra Postgres real pelos
testes `_real` existentes do núcleo genérico; aqui o que se prova é
exclusivamente que o operador REAL substitui a shadow sem quebrar
nada)."""
from datetime import datetime, timezone

import pytest

from magnata_os.autenticacao.identidade import Perfil, PermissaoNegada, Sujeito
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    adquirir_por_necessidades,
    resultados_aquisicao_prontos_por_cliente,
)
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.orquestrador.autorizacao_operador_real_v1 import (
    AutorizacaoOperadorRealError,
    PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1,
)
from magnata_os.orquestrador.eventos import EstadoExecucao, TipoEvento
from magnata_os.orquestrador.materializar_documento_pre_canario_operador_real_v1 import (
    DocumentoUnitarioObrigatorio,
    materializar_documento_pre_canario_operador_real_v1,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    OrdemDistribuicaoDocumental,
    registrar_evento_canonico_ordem_distribuicao_documental_shadow,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    montar_ordem_distribuicao_documental_de_prestacao,
)

from test_aquisicao_prestacao_corredor_real_j1 import (
    _Ambiente,
    _necessidade_holerite,
    _pdf,
    _todas_as_fontes,
    _TEXTO_HOLERITE,
    _COLABORADOR,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_SUJEITO_GESTOR = Sujeito(Perfil.GESTOR, email='gestor@magnataservicos.com.br', autenticado_por='google_oidc')


def _resultados_prontos(ambiente):
    contexto = ambiente.contexto(**_todas_as_fontes())
    adquirir_por_necessidades(contexto, (_necessidade_holerite(),), ContextoCicloPrestacao((2026, 7)))
    (par,) = resultados_aquisicao_prontos_por_cliente(contexto)
    _cliente, _competencia, resultados_aquisicao = par
    return resultados_aquisicao


def _montar_e_registrar_ordem(ambiente, resultados_aquisicao) -> OrdemDistribuicaoDocumental:
    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultados_aquisicao,
        destinatario='destinatario:pre-canario:teste',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
        tipo_documento='HOLERITE',
        mensagem_texto='Segue seu holerite de julho/2026.',
    )
    registrar_evento_canonico_ordem_distribuicao_documental_shadow(
        ordem=ordem, repositorio_execucoes=ambiente.repositorio_execucoes, instante=AGORA,
    )
    return ordem


def test_corredor_real_ate_pending_com_autorizacao_humana_real():
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    resultados_aquisicao = _resultados_prontos(ambiente)
    ordem = _montar_e_registrar_ordem(ambiente, resultados_aquisicao)

    resultado = materializar_documento_pre_canario_operador_real_v1(
        ordem=ordem,
        repositorio_documentos=ambiente.repositorio_documentos,
        armazenamento=ambiente.armazenamento,
        repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
        repositorio_acoes=ambiente.repositorio_acoes,
        sujeito=_SUJEITO_GESTOR,
        instante=AGORA,
    )

    assert resultado.funcionario_id == _COLABORADOR.entidade_id
    assert resultado.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING
    assert resultado.assinatura_link is None
    assert resultado.envelope_sha256

    # Achado do Ultrareview adversarial (herdado do padrão que #184 já
    # corrigiu no núcleo): a composição precisa persistir TODAS as
    # ações do plano, nunca só a primeira -- com mensagem de texto não
    # vazia e 1 documento, o plano produz ['texto', 'documento'], nessa
    # ordem (`_composicao_separada`). Pegar só `acoes[0]` persistiria
    # apenas o texto e o documento nunca chegaria a `PENDING`.
    assert [a.tipo for a in resultado.acoes_persistidas] == ['texto', 'documento']
    assert all(a.estado == EstadoAcaoExecucaoPlano.PENDING for a in resultado.acoes_persistidas)
    assert all(a.envelope_sha256 for a in resultado.acoes_persistidas)
    (acao_documento,) = [a for a in resultado.acoes_persistidas if a.tipo == 'documento']
    assert acao_documento.nome_sha256

    # Autorização REAL, nunca shadow.
    autorizacoes_do_evento = ambiente.repositorio_autorizacoes.listar_por_evento(resultado.event_id)
    assert len(autorizacoes_do_evento) == 1
    (autorizacao,) = autorizacoes_do_evento
    assert autorizacao.proveniencia == PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1
    assert autorizacao.ator_referencia == 'gestor@magnataservicos.com.br'

    # Evento canônico chegou a WAITING_GATE antes da autorização -- prova
    # que o Grande Orquestrador continua no comando (não foi bypassado).
    execucao = ambiente.repositorio_execucoes.buscar_por_event_id(resultado.event_id)
    assert execucao.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
    assert execucao.estado == EstadoExecucao.WAITING_GATE


def test_replay_nao_duplica_com_autorizacao_real():
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    resultados_aquisicao = _resultados_prontos(ambiente)
    ordem = _montar_e_registrar_ordem(ambiente, resultados_aquisicao)

    kwargs = dict(
        ordem=ordem, repositorio_documentos=ambiente.repositorio_documentos,
        armazenamento=ambiente.armazenamento, repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
        repositorio_acoes=ambiente.repositorio_acoes, sujeito=_SUJEITO_GESTOR, instante=AGORA,
    )
    primeiro = materializar_documento_pre_canario_operador_real_v1(**kwargs)
    segundo = materializar_documento_pre_canario_operador_real_v1(**kwargs)

    assert primeiro.event_id == segundo.event_id
    assert primeiro.acao_execucao_id == segundo.acao_execucao_id
    assert len(primeiro.acoes_persistidas) == len(segundo.acoes_persistidas) == 2
    assert [a.acao_execucao_id for a in primeiro.acoes_persistidas] == \
        [a.acao_execucao_id for a in segundo.acoes_persistidas]
    assert len(ambiente.conexao.linhas) == 2  # 2 ações (texto + documento), replay não duplica nenhuma


def test_operador_sem_perfil_permitido_bloqueia_antes_de_pending():
    ambiente = _Ambiente((('doc-hol', _pdf(_TEXTO_HOLERITE)),))
    resultados_aquisicao = _resultados_prontos(ambiente)
    ordem = _montar_e_registrar_ordem(ambiente, resultados_aquisicao)
    sujeito_auditor = Sujeito(Perfil.AUDITOR, email='auditor@magnataservicos.com.br')

    with pytest.raises(PermissaoNegada):
        materializar_documento_pre_canario_operador_real_v1(
            ordem=ordem, repositorio_documentos=ambiente.repositorio_documentos,
            armazenamento=ambiente.armazenamento, repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
            repositorio_acoes=ambiente.repositorio_acoes, sujeito=sujeito_auditor, instante=AGORA,
        )
    assert ambiente.conexao.linhas == {}  # nada persistido -- fail-closed antes de PENDING


def test_exigir_assinatura_true_esta_fora_de_escopo_desta_composicao():
    from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
        DistribuicaoDocumentalError,
        ItemDocumentoOrdem,
    )
    ordem_com_assinatura = OrdemDistribuicaoDocumental(
        documentos=(ItemDocumentoOrdem('doc-1', 'a' * 64),), funcionario_id='colab-x',
        destinatario='destinatario:x', canal='whatsapp', preset_id='X', tipo_documento='X',
        exigir_assinatura=True, exigir_comprovante=False, politica_agrupamento='UNITARIO',
        mensagem_texto='texto',
    )
    ambiente = _Ambiente(())
    with pytest.raises(DistribuicaoDocumentalError):
        materializar_documento_pre_canario_operador_real_v1(
            ordem=ordem_com_assinatura, repositorio_documentos=ambiente.repositorio_documentos,
            armazenamento=ambiente.armazenamento, repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
            repositorio_acoes=ambiente.repositorio_acoes, sujeito=_SUJEITO_GESTOR, instante=AGORA,
        )


def test_dois_documentos_sao_rejeitados_fail_closed():
    from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import ItemDocumentoOrdem
    ordem_dois_docs = OrdemDistribuicaoDocumental(
        documentos=(
            ItemDocumentoOrdem('doc-1', 'a' * 64),
            ItemDocumentoOrdem('doc-2', 'b' * 64),
        ),
        funcionario_id='colab-x', destinatario='destinatario:x', canal='whatsapp',
        preset_id='X', tipo_documento='X', exigir_assinatura=False, exigir_comprovante=False,
        politica_agrupamento='UNITARIO', mensagem_texto='texto',
    )
    ambiente = _Ambiente(())
    with pytest.raises(DocumentoUnitarioObrigatorio):
        materializar_documento_pre_canario_operador_real_v1(
            ordem=ordem_dois_docs, repositorio_documentos=ambiente.repositorio_documentos,
            armazenamento=ambiente.armazenamento, repositorio_autorizacoes=ambiente.repositorio_autorizacoes,
            repositorio_acoes=ambiente.repositorio_acoes, sujeito=_SUJEITO_GESTOR, instante=AGORA,
        )


def test_modulo_nunca_importa_transporte_real():
    import ast
    caminho = 'magnata_os/orquestrador/materializar_documento_pre_canario_operador_real_v1.py'
    with open(caminho, 'r', encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=caminho)
    proibidos = {
        'requests', 'boto3', 'porta_execucao', 'transporte_real_habilitado',
        'ExecutorEvolutionLegado', 'ciclo_producao_v1', 'compor_transporte_evolution_real',
    }
    encontrados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            encontrados.update(a.name.split('.')[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            encontrados.update(a.name for a in no.names)
        elif isinstance(no, ast.Name):
            encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            encontrados.add(no.attr)
    assert proibidos.isdisjoint(encontrados)
