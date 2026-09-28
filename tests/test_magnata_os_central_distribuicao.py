from magnata_os.central import (
    CanalDistribuicao,
    EstadoDistribuicao,
    OrdemDistribuicao,
    transicionar,
)


def ordem() -> OrdemDistribuicao:
    return OrdemDistribuicao(
        intent_id="intent-test-001",
        document_id="doc-test-001",
        document_version="sha256:test",
        recipient_id="recipient-test-001",
        channel=CanalDistribuicao.WHATSAPP,
    )


def test_fluxo_automatico_ate_conclusao():
    atual = ordem()
    atual = transicionar(atual, EstadoDistribuicao.PREPARANDO)
    atual = transicionar(atual, EstadoDistribuicao.PRONTO)
    atual = transicionar(atual, EstadoDistribuicao.ENVIANDO, incrementar_tentativa=True)
    atual = transicionar(atual, EstadoDistribuicao.ENTREGUE, evidence_id="evidence-001")
    atual = transicionar(atual, EstadoDistribuicao.CONCLUIDO)

    assert atual.state is EstadoDistribuicao.CONCLUIDO
    assert atual.attempt_count == 1
    assert atual.evidence_id == "evidence-001"


def test_falha_transitoria_permite_retry_sem_perder_ordem():
    atual = transicionar(ordem(), EstadoDistribuicao.PREPARANDO)
    atual = transicionar(atual, EstadoDistribuicao.PRONTO)
    atual = transicionar(atual, EstadoDistribuicao.ENVIANDO, incrementar_tentativa=True)
    atual = transicionar(atual, EstadoDistribuicao.ERRO_RETRY, erro="canal indisponível")
    atual = transicionar(atual, EstadoDistribuicao.ENVIANDO, incrementar_tentativa=True)

    assert atual.state is EstadoDistribuicao.ENVIANDO
    assert atual.attempt_count == 2
    assert atual.last_error is None


def test_fallback_manual_eh_caminho_explicito():
    atual = transicionar(ordem(), EstadoDistribuicao.PREPARANDO)
    atual = transicionar(atual, EstadoDistribuicao.PRONTO)
    atual = transicionar(atual, EstadoDistribuicao.FALLBACK_MANUAL, fallback_required=True)
    atual = transicionar(atual, EstadoDistribuicao.ENTREGUE, evidence_id="manual-evidence-001")
    atual = transicionar(atual, EstadoDistribuicao.CONCLUIDO)

    assert atual.state is EstadoDistribuicao.CONCLUIDO
    assert atual.fallback_required is True
    assert atual.evidence_id == "manual-evidence-001"


def test_transicao_invalida_e_rejeitada():
    try:
        transicionar(ordem(), EstadoDistribuicao.CONCLUIDO)
    except ValueError as exc:
        assert "transição não permitida" in str(exc)
    else:
        raise AssertionError("transição inválida deveria ser rejeitada")


def test_ordem_exige_identidade_minima():
    try:
        OrdemDistribuicao(
            intent_id="",
            document_id="doc-test-001",
            document_version="sha256:test",
            recipient_id="recipient-test-001",
            channel=CanalDistribuicao.EMAIL,
        )
    except ValueError as exc:
        assert "obrigatórios" in str(exc)
    else:
        raise AssertionError("ordem sem intent_id deveria ser rejeitada")
