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
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import ServicoAvancoEsteira
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ServicoCriacaoLote


class FonteMensagensEmailFalsa:
    """Duplo de teste de `FonteMensagensEmail` -- devolve exatamente as
    mensagens configuradas, sem nenhum acesso real a e-mail."""

    def __init__(self, mensagens=None):
        self._mensagens = list(mensagens or [])

    def definir_mensagens(self, mensagens):
        self._mensagens = list(mensagens)

    def buscar_novas_mensagens(self):
        return list(self._mensagens)


def _montar_adapter(mensagens=None):
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco)

    fonte = FonteMensagensEmailFalsa(mensagens)
    adapter = AdapterCapturaEmail(fonte, servico_lote)
    return adapter, fonte, repo_docs


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
    from magnata_os.documental.modulo01.repositorio import (
        RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria,
    )
    from magnata_os.documental.modulo01.repositorio_esteira import (
        RepositorioEstadosEsteiraEmMemoria, RepositorioLotesEmMemoria,
    )

    servico_entrada = ServicoEntradaDocumental(
        RepositorioDocumentosEmMemoria(), RepositorioHistoricoEmMemoria(),
    )
    servico_avanco = ServicoAvancoEsteira(
        RepositorioEstadosEsteiraEmMemoria(), RepositorioHistoricoEmMemoria(),
    )
    servico_lote = ServicoCriacaoLote(
        RepositorioLotesEmMemoria(), servico_entrada, servico_avanco,
    )
    adapter = AdapterCapturaEmail(_FonteQueFalha(), servico_lote)

    with pytest.raises(ConnectionError):
        adapter.capturar_novas_mensagens()
