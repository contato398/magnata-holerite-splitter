import pytest

from magnata_os.orquestrador.plano_comunicacao import (
    ConteudoItem,
    montar_plano_disparo,
)
from magnata_os.orquestrador.politica_comunicacao import (
    ItemComunicacao,
    montar_preview_comunicacao,
)
from magnata_os.orquestrador.transporte_comunicacao import (
    FalhaDisparo,
    TransporteComunicacaoError,
    executar_plano_disparo,
)


class TransporteFake:
    def __init__(self, falhar_em=None):
        self.chamadas = []
        self.falhar_em = falhar_em

    def _registrar(self, tipo, **kwargs):
        self.chamadas.append((tipo, kwargs))
        if self.falhar_em == len(self.chamadas):
            raise RuntimeError("falha simulada")
        return {"ok": True, "tipo": tipo}

    def enviar_texto(self, **kwargs):
        return self._registrar("texto", **kwargs)

    def enviar_video(self, **kwargs):
        return self._registrar("video", **kwargs)

    def enviar_documento(self, **kwargs):
        return self._registrar("documento", **kwargs)


def _plano_dois_videos():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Benefícios Magnata",
        itens=[
            ItemComunicacao("video", "v1.mp4"),
            ItemComunicacao("video", "v2.mp4"),
        ],
        assinatura=False,
        comprovante=False,
        preferencia="otimizar",
    )
    return montar_plano_disparo(
        preview=preview,
        texto="Benefícios Magnata",
        conteudos=[
            ConteudoItem("video", "v1.mp4", "B64-1"),
            ConteudoItem("video", "v2.mp4", "B64-2"),
        ],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )


def test_executor_respeita_ordem_e_legenda_do_plano_otimizado():
    transporte = TransporteFake()
    plano = _plano_dois_videos()

    resultado = executar_plano_disparo(plano=plano, transporte=transporte)

    assert len(resultado.resultados) == 2
    assert [tipo for tipo, _ in transporte.chamadas] == ["video", "video"]
    assert transporte.chamadas[0][1] == {
        "numero": "5515999999999",
        "conteudo": "B64-1",
        "nome_arquivo": "v1.mp4",
        "legenda": "Benefícios Magnata",
    }
    assert transporte.chamadas[1][1]["legenda"] == ""


def test_executor_separado_chama_texto_antes_das_midias():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="Mensagem",
        itens=[ItemComunicacao("documento", "arquivo.pdf")],
        assinatura=False,
        comprovante=False,
        preferencia="separado",
    )
    plano = montar_plano_disparo(
        preview=preview,
        texto="Mensagem",
        conteudos=[ConteudoItem("documento", "arquivo.pdf", "PDF")],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )
    transporte = TransporteFake()

    executar_plano_disparo(plano=plano, transporte=transporte)

    assert [tipo for tipo, _ in transporte.chamadas] == ["texto", "documento"]


def test_executor_fail_fast_preserva_evidencia_do_que_concluiu():
    transporte = TransporteFake(falhar_em=2)
    plano = _plano_dois_videos()

    with pytest.raises(FalhaDisparo) as erro:
        executar_plano_disparo(plano=plano, transporte=transporte)

    assert len(erro.value.concluidas) == 1
    assert erro.value.acao.ordem == 2
    assert len(transporte.chamadas) == 2


def test_preflight_bloqueia_tipo_sem_adapter_antes_de_qualquer_io():
    preview = montar_preview_comunicacao(
        destinatarios=["5515999999999"],
        texto="",
        itens=[ItemComunicacao("audio", "audio.ogg")],
        assinatura=False,
        comprovante=False,
    )
    plano = montar_plano_disparo(
        preview=preview,
        texto="",
        conteudos=[ConteudoItem("audio", "audio.ogg", "AUDIO")],
        preview_id_autorizado=preview.preview_id,
        autorizacao_explicita=True,
    )
    transporte = TransporteFake()

    with pytest.raises(TransporteComunicacaoError, match="audio"):
        executar_plano_disparo(plano=plano, transporte=transporte)

    assert transporte.chamadas == []
