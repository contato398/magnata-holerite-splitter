import pytest

from magnata_os.orquestrador.plano_comunicacao import (
    ConteudoItem,
    PlanoComunicacaoError,
    montar_plano_disparo,
)
from magnata_os.orquestrador.politica_comunicacao import (
    AutorizacaoObrigatoriaError,
    ItemComunicacao,
    hash_conteudo_comunicacao,
    montar_preview_comunicacao,
)

_VIDEO_1 = b"video-sintetico-1"
_VIDEO_2 = b"video-sintetico-2"


def _midia(tipo, nome, conteudo):
    return ItemComunicacao(tipo, nome, hash_conteudo_comunicacao(conteudo))


def _preview(preferencia="otimizar"):
    return montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Benefícios Magnata",
        itens=[
            _midia("video", "v1.mp4", _VIDEO_1),
            _midia("video", "v2.mp4", _VIDEO_2),
        ],
        assinatura=False,
        comprovante=False,
        preferencia=preferencia,
    )


def _conteudos():
    return [
        ConteudoItem("video", "v1.mp4", _VIDEO_1),
        ConteudoItem("video", "v2.mp4", _VIDEO_2),
    ]


def test_plano_otimizado_materializa_legenda_no_primeiro_video():
    preview = _preview()
    plano = montar_plano_disparo(
        preview=preview,
        texto="Benefícios Magnata",
        conteudos=_conteudos(),
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )

    assert plano.total_notificacoes == 2
    assert [a.tipo for a in plano.acoes] == ["video", "video"]
    assert plano.acoes[0].legenda == "Benefícios Magnata"
    assert plano.acoes[1].legenda == ""
    assert plano.acoes[0].conteudo == _VIDEO_1


def test_plano_separado_preserva_texto_mais_dois_videos():
    preview = _preview(preferencia="separado")
    plano = montar_plano_disparo(
        preview=preview,
        texto="Benefícios Magnata",
        conteudos=_conteudos(),
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
            conteudos=_conteudos(),
            preview_id_autorizado="outra-previa",
            autorizacao_explicita=True,
        )


def test_plano_recusa_conteudo_ausente():
    preview = _preview()
    with pytest.raises(PlanoComunicacaoError, match="conteúdo ausente"):
        montar_plano_disparo(
            preview=preview,
            texto="Benefícios Magnata",
            conteudos=[ConteudoItem("video", "v1.mp4", _VIDEO_1)],
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
                *_conteudos(),
                ConteudoItem("video", "v3.mp4", b"video-sintetico-3"),
            ],
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_plano_recusa_texto_ausente_quando_previa_tinha_texto():
    preview = _preview()
    with pytest.raises(PlanoComunicacaoError, match="texto não corresponde"):
        montar_plano_disparo(
            preview=preview,
            texto="",
            conteudos=_conteudos(),
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_plano_recusa_troca_de_texto_apos_previa():
    preview = _preview()
    with pytest.raises(PlanoComunicacaoError, match="texto não corresponde"):
        montar_plano_disparo(
            preview=preview,
            texto="Outro texto também não vazio",
            conteudos=_conteudos(),
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_plano_deduplicado_na_previa_nao_duplica_acoes():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999", "5515999999999"],
        texto="Oi",
        itens=[_midia("video", "v.mp4", b"video-unico")],
        assinatura=False,
        comprovante=False,
    )
    plano = montar_plano_disparo(
        preview=preview,
        texto="Oi",
        conteudos=[ConteudoItem("video", "v.mp4", b"video-unico")],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )
    assert len(plano.destinatarios) == 1
    assert len(plano.acoes) == 1


def test_mesmo_tipo_nome_e_bytes_diferentes_sao_rejeitados():
    preview = _preview()
    adulterados = [
        ConteudoItem("video", "v1.mp4", b"bytes-adulterados"),
        ConteudoItem("video", "v2.mp4", _VIDEO_2),
    ]

    with pytest.raises(PlanoComunicacaoError, match="diverge da prévia"):
        montar_plano_disparo(
            preview=preview,
            texto="Benefícios Magnata",
            conteudos=adulterados,
            preview_id_autorizado=preview.preview_id,
            autorizacao_explicita=True,
        )


def test_conteudo_por_referencia_sem_bytes_falha_explicitamente():
    with pytest.raises(PlanoComunicacaoError, match="deve ser binário"):
        ConteudoItem("video", "v1.mp4", "storage://referencia-sem-bytes")
