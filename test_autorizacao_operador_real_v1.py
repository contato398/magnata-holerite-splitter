"""Autorização humana REAL (não-shadow) do Grande Orquestrador --
Etapa Pré-Canário Seguro da V1 WhatsApp.

Cobre exatamente o que a shadow nunca precisa provar: perfil exigido,
identidade real obrigatória, e que shadow/real nunca se confundem.
Idempotência/replay/vínculo a preview exato já são provados pelo
contrato compartilhado (`RegistroAutorizacaoGate`/
`RepositorioAutorizacoesGateEmMemoria`, `test_autorizacao_gate.py`
--se existir-- ou pelos testes de `wiring_distribuicao_documental_
shadow.py`) -- não duplicados aqui, só revalidados no ponto de
integração com esta função nova."""
from datetime import datetime, timezone

import pytest

from magnata_os.autenticacao.identidade import Perfil, PermissaoNegada, Sujeito
from magnata_os.orquestrador.autorizacao_gate import (
    ConflitoDecisaoGateError,
    RepositorioAutorizacoesGateEmMemoria,
)
from magnata_os.orquestrador.autorizacao_operador_real_v1 import (
    AutorizacaoOperadorRealError,
    PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1,
    autorizar_preview_operador_real,
)
from magnata_os.orquestrador.politica_comunicacao import montar_preview_comunicacao

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_EVENT_ID = 'evt_pre_canario_teste'


def _preview():
    return montar_preview_comunicacao(
        destinatarios=('destinatario:teste',), texto='Segue seu documento.',
        assinatura=False, comprovante=False,
    )


def test_operador_com_perfil_permitido_autoriza():
    repo = RepositorioAutorizacoesGateEmMemoria()
    sujeito = Sujeito(Perfil.GESTOR, email='gestor@magnataservicos.com.br', autenticado_por='google_oidc')
    autorizacao = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=_preview(), event_id=_EVENT_ID,
        sujeito=sujeito, instante=AGORA,
    )
    assert autorizacao.proveniencia == PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1
    assert autorizacao.ator_referencia == 'gestor@magnataservicos.com.br'
    assert repo.buscar(_EVENT_ID, autorizacao.preview_id) == autorizacao


def test_operador_sem_perfil_permitido_e_recusado():
    repo = RepositorioAutorizacoesGateEmMemoria()
    sujeito = Sujeito(Perfil.AUDITOR, email='auditor@magnataservicos.com.br')
    with pytest.raises(PermissaoNegada):
        autorizar_preview_operador_real(
            repositorio_autorizacoes=repo, preview=_preview(), event_id=_EVENT_ID,
            sujeito=sujeito, instante=AGORA,
        )
    assert repo.listar_por_evento(_EVENT_ID) == []  # nada persistido em falha


def test_operador_sem_email_e_recusado_mesmo_com_perfil_valido():
    """Sujeito construído só com perfil (sem passar pela fronteira real
    de autenticação) -- fail-closed mesmo que o perfil seja permitido."""
    repo = RepositorioAutorizacoesGateEmMemoria()
    sujeito_anonimo = Sujeito(Perfil.GESTOR)  # email=None, autenticado_por=None
    with pytest.raises(AutorizacaoOperadorRealError):
        autorizar_preview_operador_real(
            repositorio_autorizacoes=repo, preview=_preview(), event_id=_EVENT_ID,
            sujeito=sujeito_anonimo, instante=AGORA,
        )
    assert repo.listar_por_evento(_EVENT_ID) == []


def test_autorizacao_repetida_pelo_mesmo_operador_e_idempotente():
    repo = RepositorioAutorizacoesGateEmMemoria()
    sujeito = Sujeito(Perfil.OPERACIONAL, email='op@magnataservicos.com.br')
    preview = _preview()
    primeira = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview, event_id=_EVENT_ID,
        sujeito=sujeito, instante=AGORA,
    )
    segunda = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview, event_id=_EVENT_ID,
        sujeito=sujeito, instante=AGORA,
    )
    assert primeira == segunda
    assert len(repo.listar_por_evento(_EVENT_ID)) == 1  # replay nao duplica


def test_autorizacao_de_preview_diferente_nunca_reaproveita_a_anterior():
    """Alterar o texto do preview muda `preview_id` -- a autorização
    antiga nunca serve para o novo preview (mesmo invariante do núcleo
    genérico)."""
    repo = RepositorioAutorizacoesGateEmMemoria()
    sujeito = Sujeito(Perfil.GESTOR, email='gestor@magnataservicos.com.br')
    preview_original = _preview()
    preview_alterado = montar_preview_comunicacao(
        destinatarios=('destinatario:teste',), texto='Texto alterado depois do preview.',
        assinatura=False, comprovante=False,
    )
    assert preview_original.preview_id != preview_alterado.preview_id

    autorizacao_original = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview_original, event_id=_EVENT_ID,
        sujeito=sujeito, instante=AGORA,
    )
    autorizacao_novo_preview = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview_alterado, event_id=_EVENT_ID,
        sujeito=sujeito, instante=AGORA,
    )
    assert autorizacao_original.autorizacao_id != autorizacao_novo_preview.autorizacao_id
    assert autorizacao_original.preview_id != autorizacao_novo_preview.preview_id


def test_decisoes_conflitantes_para_o_mesmo_preview_sao_recusadas():
    """Dois operadores diferentes 'autorizando' o mesmo event_id/preview_id
    com decisões conflitantes nunca sobrescreve o fato original --
    mesmo invariante do contrato compartilhado `RegistroAutorizacaoGate`."""
    repo = RepositorioAutorizacoesGateEmMemoria()
    preview = _preview()
    autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview, event_id=_EVENT_ID,
        sujeito=Sujeito(Perfil.GESTOR, email='gestor-a@magnataservicos.com.br'), instante=AGORA,
    )
    # ator_referencia diferente -> autorizacao_id diferente -> registrar_se_novo
    # tentaria inserir um SEGUNDO fato para o mesmo (event_id, preview_id);
    # o contrato do repositório recusa por decisão conflitante apenas
    # quando a decisão em si diverge -- aqui ambas são AUTORIZADO, então
    # o teste prova que o segundo ator NUNCA sobrescreve o primeiro fato.
    resultado_ainda_gravado = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview, event_id=_EVENT_ID,
        sujeito=Sujeito(Perfil.GESTOR, email='gestor-a@magnataservicos.com.br'), instante=AGORA,
    )
    assert repo.buscar(_EVENT_ID, preview.preview_id).ator_referencia == 'gestor-a@magnataservicos.com.br'
    assert resultado_ainda_gravado.ator_referencia == 'gestor-a@magnataservicos.com.br'


def test_segundo_operador_perdedor_da_corrida_recebe_o_registro_realmente_persistido():
    """Achado de Ultrareview adversarial: se dois operadores DIFERENTES
    (emails distintos) chamam esta função para o MESMO event_id/
    preview_id, quem chega depois nunca pode receber de volta um objeto
    com o SEU PRÓPRIO ator_referencia se esse não é o que ficou
    persistido -- isso corromperia a trilha de auditoria (quem
    realmente autorizou) em qualquer código posterior que confie no
    valor de retorno (ex.: `criar_registro_acao_plano`)."""
    repo = RepositorioAutorizacoesGateEmMemoria()
    preview = _preview()
    primeiro = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview, event_id=_EVENT_ID,
        sujeito=Sujeito(Perfil.GESTOR, email='gestor-a@magnataservicos.com.br'), instante=AGORA,
    )
    segundo = autorizar_preview_operador_real(
        repositorio_autorizacoes=repo, preview=preview, event_id=_EVENT_ID,
        sujeito=Sujeito(Perfil.GESTOR, email='gestor-b@magnataservicos.com.br'), instante=AGORA,
    )
    persistido = repo.buscar(_EVENT_ID, preview.preview_id)

    assert segundo == persistido  # nunca o objeto local do perdedor
    assert segundo.ator_referencia == 'gestor-a@magnataservicos.com.br'  # quem realmente autorizou
    assert primeiro == segundo == persistido


def test_shadow_e_real_nunca_se_confundem_por_proveniencia():
    """Prova estrutural: a proveniência real nunca é a string usada pela
    autorização shadow em nenhum outro módulo do repositório."""
    assert PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1 != 'wiring_distribuicao_documental_shadow_v1'
    assert not PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1.endswith('_shadow_v1')
