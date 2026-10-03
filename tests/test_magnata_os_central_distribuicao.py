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
        document_ids=("doc-test-001", "doc-test-002"),
        document_versions=("sha256:test-1", "sha256:test-2"),
        recipient_ids=("recipient-test-001", "recipient-test-002"),
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


def test_ordem_exige_documento_e_destinatario():
    try:
        OrdemDistribuicao(
            intent_id="intent-test-001",
            document_ids=(),
            document_versions=(),
            recipient_ids=("recipient-test-001",),
            channel="EMAIL",
        )
    except ValueError as exc:
        assert "ao menos 1 documento" in str(exc)
    else:
        raise AssertionError("ordem sem documento deveria ser rejeitada")


def test_documentos_e_destinatarios_sao_realmente_1_a_n():
    ordem_futura = OrdemDistribuicao(
        intent_id="intent-test-002",
        document_ids=("doc-a", "doc-b", "doc-c"),
        document_versions=("sha-a", "sha-b", "sha-c"),
        recipient_ids=("dest-a", "dest-b", "dest-c"),
        channel="CANAL_FUTURO",
        signature_required=True,
        receipt_required=True,
    )

    assert len(ordem_futura.document_ids) == 3
    assert len(ordem_futura.recipient_ids) == 3
    assert ordem_futura.signature_required is True
