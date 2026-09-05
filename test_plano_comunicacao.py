import pytest

from magnata_os.orquestrador.plano_comunicacao import (
    ConteudoItem,
    PlanoComunicacaoError,
    montar_plano_disparo,
)
from magnata_os.orquestrador.politica_comunicacao import (
    AutorizacaoObrigatoriaError,
    ItemComunicacao,
    montar_preview_comunicacao,
)


def _preview(preferencia="otimizar"):
    return montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Benefícios Magnata",
        itens=[
            ItemComunicacao("video", "v1.mp4"),
            ItemComunicacao("video", "v2.mp4"),
        ],
        assinatura=False,
        comprovante=False,
        preferencia=preferencia,
    )


def test_plano_otimizado_materializa_legenda_no_primeiro_video():
    preview = _preview()
    plano = montar_plano_disparo(
        preview=preview,
        texto="Benefícios Magnata",
        conteudos=[
            ConteudoItem("video", "v1.mp4", "BASE64-1"),
            ConteudoItem("video", "v2.mp4", "BASE64-2"),
        ],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )

    assert plano.total_notificacoes == 2
    assert [a.tipo for a in plano.acoes] == ["video", "video"]
    assert plano.acoes[0].legenda == "Benefícios Magnata"
    assert plano.acoes[1].legenda == ""
    assert plano.acoes[0].conteudo == "BASE64-1"


def test_plano_separado_preserva_texto_mais_dois_videos():
    preview = _preview(preferencia="separado")
    plano = montar_plano_disparo(
        preview=preview,
        texto="Benefícios Magnata",
        conteudos=[
            ConteudoItem("video", "v1.mp4", "BASE64-1"),
            ConteudoItem("video", "v2.mp4", "BASE64-2"),
        ],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )

    assert plano.total_notificacoes == 3
    assert [a.tipo for a in plano.acoes] == ["texto", "video", "video"]
    assert plano.acoes[0].texto == "Benefícios Magnata"
    assert all(a.legenda == "" for a in plano.acoes)


def test_plano_revalida_gate_de_autorizacao():
    preview = _preview()
    with pytest.raises(AutorizacaoObrigatoriaError):
        montar_plano_disparo(
            preview=preview,
            texto="Benefícios Magnata",
            conteudos=[
                ConteudoItem("video", "v1.mp4", "1"),
                ConteudoItem("video", "v2.mp4", "2"),
            ],
            preview_id_autorizado="outra-previa",
            autorizacao_explicita=True,
        )


def test_plano_recusa_conteudo_ausente():
    preview = _preview()
    with pytest.raises(PlanoComunicacaoError, match="conteúdo ausente"):
        montar_plano_disparo(
            preview=preview,
            texto="Benefícios Magnata",
            conteudos=[ConteudoItem("video", "v1.mp4", "1")],
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_plano_recusa_conteudo_extra():
    preview = _preview()
    with pytest.raises(PlanoComunicacaoError, match="não previsto"):
        montar_plano_disparo(
            preview=preview,
            texto="Benefícios Magnata",
            conteudos=[
                ConteudoItem("video", "v1.mp4", "1"),
                ConteudoItem("video", "v2.mp4", "2"),
                ConteudoItem("video", "v3.mp4", "3"),
            ],
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_plano_recusa_texto_diferente_da_previa_na_presenca():
    preview = _preview()
    with pytest.raises(PlanoComunicacaoError, match="texto não corresponde"):
        montar_plano_disparo(
            preview=preview,
            texto="",
            conteudos=[
                ConteudoItem("video", "v1.mp4", "1"),
                ConteudoItem("video", "v2.mp4", "2"),
            ],
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_plano_deduplicado_na_previa_nao_duplica_acoes():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999", "5515999999999"],
        texto="Oi",
        itens=[ItemComunicacao("video", "v.mp4")],
        assinatura=False,
        comprovante=False,
    )
    plano = montar_plano_disparo(
        preview=preview,
        texto="Oi",
        conteudos=[ConteudoItem("video", "v.mp4", "X")],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )
    assert len(plano.destinatarios) == 1
    assert len(plano.acoes) == 1
