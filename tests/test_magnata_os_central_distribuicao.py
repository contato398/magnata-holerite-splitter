from magnata_os.central import (
    CanalDistribuicao,
    EstadoDistribuicao,
    OrdemDistribuicao,
    encaminhar_para_fallback_manual,
    transicionar,
)


def ordem() -> OrdemDistribuicao:
    return OrdemDistribuicao(
        intent_id="intent-test-001",
        document_id="doc-test-001",
        document_version="sha256:test",
        recipient_id="recipient-test-001",
        channel=CanalDistribuicao("WHATSAPP"),
    )


def test_fluxo_automatico_reutiliza_ciclo_do_orquestrador():
    atual = ordem()
    atual = transicionar(atual, EstadoDistribuicao.EXECUTING, incrementar_tentativa=True)
    atual = transicionar(atual, EstadoDistribuicao.SUCCEEDED, evidence_id="evidence-001")

    assert atual.state is EstadoDistribuicao.SUCCEEDED
    assert atual.attempt_count == 1
    assert atual.evidence_id == "evidence-001"


def test_falha_transitoria_permite_retry_sem_novo_estado():
    atual = transicionar(ordem(), EstadoDistribuicao.EXECUTING, incrementar_tentativa=True)
    atual = transicionar(
        atual,
        EstadoDistribuicao.FAILED_RETRYABLE,
        erro="canal indisponível",
    )
    atual = transicionar(
        atual,
        EstadoDistribuicao.EXECUTING,
        incrementar_tentativa=True,
    )

    assert atual.state is EstadoDistribuicao.EXECUTING
    assert atual.attempt_count == 2
    assert atual.last_error == "canal indisponível"


def test_fallback_manual_eh_marca_de_politica_sem_novo_estado():
    atual = encaminhar_para_fallback_manual(
        ordem(),
        motivo="canal automático indisponível",
    )

    assert atual.state is EstadoDistribuicao.PENDING
    assert atual.fallback_required is True
    assert atual.last_error == "canal automático indisponível"


def test_transicao_invalida_e_rejeitada():
    try:
        transicionar(ordem(), EstadoDistribuicao.SUCCEEDED)
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
            channel="EMAIL",
        )
    except ValueError as exc:
        assert "obrigatórios" in str(exc)
    else:
        raise AssertionError("ordem sem intent_id deveria ser rejeitada")


def test_canal_e_extensivel_sem_edicao_do_nucleo():
    ordem_futura = OrdemDistribuicao(
        intent_id="intent-test-002",
        document_id="doc-test-002",
        document_version="sha256:test-2",
        recipient_id="recipient-test-002",
        channel="CANAL_FUTURO",
    )

    assert ordem_futura.channel == "CANAL_FUTURO"
