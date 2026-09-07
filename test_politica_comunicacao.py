import pytest

from magnata_os.orquestrador.politica_comunicacao import (
    AutorizacaoObrigatoriaError,
    ItemComunicacao,
    PoliticaComunicacaoError,
    PreviewObrigatorioError,
    hash_conteudo_comunicacao,
    montar_preview_comunicacao,
    validar_autorizacao_disparo,
)


def _midia(tipo, nome, conteudo=None):
    bytes_efetivos = conteudo if conteudo is not None else f"bytes:{nome}".encode()
    return ItemComunicacao(tipo, nome, hash_conteudo_comunicacao(bytes_efetivos))


def test_texto_video_otimizado_vira_uma_notificacao_por_pessoa():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999", "5515888888888"],
        texto="Olá! Veja o vídeo.",
        itens=[_midia("video", "beneficios.mp4")],
        assinatura=False,
        comprovante=False,
        preferencia="otimizar",
    )

    assert preview.mensagens_por_pessoa == 1
    assert preview.total_notificacoes == 2
    assert preview.composicao_solicitada[0].usa_texto_como_legenda is True
    assert preview.alerta_fragmentacao is False


def test_texto_dois_videos_otimiza_de_tres_para_duas_notificacoes():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"] * 2,
        texto="Benefícios Magnata",
        itens=[_midia("video", "v1.mp4"), _midia("video", "v2.mp4")],
        assinatura=False,
        comprovante=False,
        preferencia="otimizar",
    )

    # destinatário duplicado não aumenta o disparo
    assert len(preview.destinatarios) == 1
    assert preview.mensagens_por_pessoa == 2
    assert preview.total_notificacoes == 2
    assert preview.composicao_solicitada[0].usa_texto_como_legenda is True


def test_operador_pode_exigir_separado_mas_recebe_alerta_e_alternativa():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Mensagem",
        itens=[_midia("video", "v1.mp4"), _midia("video", "v2.mp4")],
        assinatura=False,
        comprovante=False,
        preferencia="separado",
    )

    assert preview.mensagens_por_pessoa == 3
    assert preview.mensagens_otimizadas_por_pessoa == 2
    assert preview.alternativa_mais_compacta is True
    assert preview.alerta_fragmentacao is True


def test_assinatura_e_comprovante_nunca_sao_presumidos():
    with pytest.raises(PoliticaComunicacaoError, match="assinatura"):
        montar_preview_comunicacao(
            destinatarios=["5515999999999"], texto="Oi", assinatura=None, comprovante=False
        )

    with pytest.raises(PoliticaComunicacaoError, match="comprovante"):
        montar_preview_comunicacao(
            destinatarios=["5515999999999"], texto="Oi", assinatura=False, comprovante=None
        )


def test_assinatura_e_comprovante_fazem_parte_da_previa():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Assine o documento",
        itens=[_midia("documento", "folha.pdf")],
        assinatura=True,
        comprovante=True,
        preferencia="otimizar",
    )
    assert preview.assinatura is True
    assert preview.comprovante is True
    assert preview.mensagens_por_pessoa == 1


def test_disparo_sem_preview_e_bloqueado():
    with pytest.raises(PreviewObrigatorioError):
        validar_autorizacao_disparo(
            preview=None, preview_id_autorizado=None, autorizacao_explicita=True
        )


def test_disparo_sem_autorizacao_pos_preview_e_bloqueado():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Oi",
        assinatura=False,
        comprovante=False,
    )
    with pytest.raises(AutorizacaoObrigatoriaError):
        validar_autorizacao_disparo(
            preview=preview,
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=False,
        )


def test_autorizacao_de_outra_previa_nao_libera_disparo():
    preview_a = montar_preview_comunicacao(
        destinatarios=["5515999999999"], texto="A", assinatura=False, comprovante=False
    )
    preview_b = montar_preview_comunicacao(
        destinatarios=["5515999999999"], texto="B", assinatura=False, comprovante=False
    )
    assert preview_a.preview_id != preview_b.preview_id

    with pytest.raises(AutorizacaoObrigatoriaError, match="não corresponde"):
        validar_autorizacao_disparo(
            preview=preview_b,
            preview_id_autorizado=preview_a.preview_id,
            autorizacao_explicita=True,
        )


def test_autorizacao_da_previa_atual_libera_gate():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Oi",
        itens=[_midia("video", "v.mp4")],
        assinatura=False,
        comprovante=False,
    )
    validar_autorizacao_disparo(
        preview=preview,
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )


def test_midia_sem_digest_e_rejeitada_no_preview():
    with pytest.raises(PoliticaComunicacaoError, match="SHA-256"):
        ItemComunicacao("video", "sem-integridade.mp4")


def test_mesmos_bytes_geram_digest_e_preview_deterministicos():
    conteudo = b"midia-sintetica-estavel"
    item_a = _midia("video", "video.mp4", conteudo)
    item_b = _midia("video", "video.mp4", bytes(conteudo))
    kwargs = dict(
        destinatarios=["destinatario-sintetico"], texto="Mensagem sintética",
        assinatura=False, comprovante=False,
    )

    assert item_a.conteudo_sha256 == item_b.conteudo_sha256
    assert montar_preview_comunicacao(itens=[item_a], **kwargs).preview_id == (
        montar_preview_comunicacao(itens=[item_b], **kwargs).preview_id
    )


def test_bytes_diferentes_mudam_preview_mesmo_com_tipo_e_nome_iguais():
    kwargs = dict(
        destinatarios=["destinatario-sintetico"], texto="Mensagem sintética",
        assinatura=False, comprovante=False,
    )
    preview_a = montar_preview_comunicacao(
        itens=[_midia("video", "video.mp4", b"conteudo-a")], **kwargs,
    )
    preview_b = montar_preview_comunicacao(
        itens=[_midia("video", "video.mp4", b"conteudo-b")], **kwargs,
    )

    assert preview_a.preview_id != preview_b.preview_id
