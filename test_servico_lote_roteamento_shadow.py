"""Teste de integração: ServicoCriacaoLote -> roteamento documental shadow.

Cobre o ponto exato de integração confirmado pela auditoria: dentro de
`ServicoCriacaoLote._processar_um_arquivo`, depois que o Documento já
existe (novo ou duplicado), o roteamento shadow roda sobre os MESMOS
bytes já em escopo (`arquivo.conteudo`) e o resultado (`RoteamentoShadowDTO`)
fica só no retorno em memória (`ItemResumoLote.roteamento_shadow`) --
nada é persistido, nenhuma etapa da esteira avança para CLASSIFICACAO.

Onde a classificação real (via pdfplumber) não é necessária para o que
o teste verifica (isolamento de erro, proveniência sem metadados,
duplicado), o teste monkeypatch a função `decidir_roteamento` importada
em `servico_lote.py`, tornando esses testes independentes do ambiente
de extração de PDF. Os 2 testes que precisam de classificação REAL
(Holerite resolvido, tipo desconhecido) usam PDFs fabricados via
reportlab e são pulados explicitamente (nunca escondidos como "passou")
quando `pdfplumber` está quebrado neste sandbox -- mesmo padrão já
usado em test_roteamento_documental_shadow.py.
"""
import collections
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01 import servico_lote as servico_lote_mod
from magnata_os.documental.modulo01.dtos_esteira import MOTIVO_ERRO_TECNICO_SHADOW
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
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote
from magnata_os.classificacao.classificador_documental import EstadoClassificacao
from magnata_os.classificacao.roteamento_documental import (
    AcaoRoteamento,
    DecisaoRoteamentoDocumental,
    EscopoDocumental,
    MotivoRoteamento,
)

try:
    import pdfplumber  # noqa: F401
    _PDFPLUMBER_FUNCIONAL = True
except BaseException:
    _PDFPLUMBER_FUNCIONAL = False

_MOTIVO_SKIP_PDFPLUMBER = (
    "pdfplumber quebrado neste ambiente (pyo3_runtime.PanicException / "
    "_cffi_backend ausente) — falha de ambiente pré-existente, não do código novo"
)


_Contexto = collections.namedtuple(
    '_Contexto', 'repo_docs repo_hist repo_lotes repo_estados servico_lote'
)


def _montar_servicos() -> _Contexto:
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco)

    return _Contexto(repo_docs, repo_hist, repo_lotes, repo_estados, servico_lote)


def _pdf_minimo_com_texto(texto: str) -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(72, 720, texto)
    c.save()
    return buffer.getvalue()


def _decisao_fake(tipo: str, estado: EstadoClassificacao, escopo: EscopoDocumental) -> DecisaoRoteamentoDocumental:
    """Decisão fabricada, para testes que não precisam de classificação
    real (isolamento de erro, proveniência, duplicado)."""
    return DecisaoRoteamentoDocumental(
        tipo_documental=tipo,
        estado_classificacao=estado,
        escopo_documental=escopo,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='BAIXA',
        evidencias_sanitizadas=('hit',),
        tipos_concorrentes=(),
    )


# ── Fluxo completo com 2 PDFs reais (classificação de verdade) ────────────────

@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
class TestLoteComDoisPdfsReais:
    """1 lote, 2 PDFs (A=Holerite reconhecível, B=texto desconhecido) --
    fluxo de ponta a ponta com classificação REAL."""

    def test_dois_documentos_criados_e_shadow_correlacionado(self):
        ctx = _montar_servicos()
        pdf_holerite = _pdf_minimo_com_texto("Recibo de Pagamento - Valor Liquido")
        pdf_desconhecido = _pdf_minimo_com_texto("Lorem ipsum dolor sit amet")

        arquivos = [
            ArquivoEntradaLote(pdf_holerite, 'holerite.pdf', 'application/pdf'),
            ArquivoEntradaLote(pdf_desconhecido, 'desconhecido.pdf', 'application/pdf'),
        ]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        # 1. 2 Documentos criados normalmente.
        assert resumo.quantidade_arquivos == 2
        assert resumo.quantidade_sucesso == 2
        assert resumo.quantidade_erro == 0

        # 2. 2 ItemResumoLote com sucesso de ingestão.
        item_holerite, item_desconhecido = resumo.itens
        assert item_holerite.sucesso is True
        assert item_desconhecido.sucesso is True

        # 3. Cada item tem RoteamentoShadowDTO.
        assert item_holerite.roteamento_shadow is not None
        assert item_desconhecido.roteamento_shadow is not None

        # 4 + 5. documento_id e hash_sha256 do shadow correspondem ao
        # Documento correto (nunca recalculados, vêm do próprio Documento).
        doc_holerite = ctx.repo_docs.buscar_por_hash(
            __import__('hashlib').sha256(pdf_holerite).hexdigest()
        )
        assert item_holerite.roteamento_shadow.documento_id == doc_holerite.documento_id
        assert item_holerite.roteamento_shadow.hash_sha256 == doc_holerite.hash_sha256
        assert item_holerite.roteamento_shadow.documento_id == item_holerite.documento_id

        # 6. Holerite: RESOLVIDA, tipo Holerite, sem processador avulso,
        # REVISAR_HUMANO (conforme PR #84).
        shadow_holerite = item_holerite.roteamento_shadow
        assert shadow_holerite.executado is True
        assert shadow_holerite.sucesso is True
        assert shadow_holerite.tipo_documental == 'Holerite'
        assert shadow_holerite.estado_classificacao == EstadoClassificacao.RESOLVIDA.value
        assert shadow_holerite.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO.value
        assert shadow_holerite.motivo == MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL.value

        # 7. Desconhecido: NAO_RECONHECIDA, REVISAR_HUMANO.
        shadow_desconhecido = item_desconhecido.roteamento_shadow
        assert shadow_desconhecido.tipo_documental == 'Outro'
        assert shadow_desconhecido.estado_classificacao == EstadoClassificacao.NAO_RECONHECIDA.value
        assert shadow_desconhecido.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO.value
        assert shadow_desconhecido.motivo == MotivoRoteamento.TIPO_NAO_RECONHECIDO.value

        # 8. Nenhuma PII/texto bruto no DTO.
        for shadow in (shadow_holerite, shadow_desconhecido):
            campos_texto = " ".join(str(v) for v in [
                shadow.tipo_documental, shadow.estado_classificacao,
                shadow.escopo_documental, shadow.acao_recomendada, shadow.motivo,
            ] if v is not None).lower()
            assert "lorem" not in campos_texto
            assert "recibo de pagamento" not in campos_texto


# ── Isolamento de erro técnico do roteamento shadow ────────────────────────────

class TestIsolamentoDeErroTecnico:
    """Uma exceção inesperada dentro de decidir_roteamento NUNCA desfaz o
    Documento nem aborta o lote -- vira ERRO_TECNICO_SHADOW no DTO."""

    def test_excecao_no_roteamento_nao_afeta_ingestao(self, monkeypatch):
        ctx = _montar_servicos()

        def _decidir_roteamento_quebrado(conteudo_pdf: bytes):
            raise RuntimeError("falha técnica simulada — nunca deve vazar")

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_quebrado)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item = resumo.itens[0]
        # Documento é criado; ItemResumoLote.sucesso reflete a INGESTÃO.
        assert item.sucesso is True
        assert item.documento_id is not None
        assert resumo.quantidade_erro == 0
        assert resumo.situacao.value == 'CONCLUIDO'

        # Shadow reflete o erro técnico, isolado.
        shadow = item.roteamento_shadow
        assert shadow is not None
        assert shadow.executado is True
        assert shadow.sucesso is False
        assert shadow.motivo == MOTIVO_ERRO_TECNICO_SHADOW
        assert shadow.tipo_documental is None
        assert shadow.estado_classificacao is None

        # A mensagem da exceção NUNCA vaza para o DTO.
        campos = [shadow.motivo, str(shadow.tipo_documental), str(shadow.estado_classificacao)]
        assert not any('falha técnica simulada' in c for c in campos)

    def test_panic_exception_real_e_isolada(self, monkeypatch):
        """pyo3_runtime.PanicException REAL (levantada de verdade pela
        dependência nativa quebrada neste sandbox) precisa ser isolada.
        Só roda quando o ambiente reproduz o panic de verdade -- não
        simulado."""
        if _PDFPLUMBER_FUNCIONAL:
            pytest.skip("pdfplumber funcional neste ambiente — panic real não ocorre para testar aqui")

        ctx = _montar_servicos()
        # Não substitui decidir_roteamento -- deixa o roteamento REAL
        # tentar extrair texto via pdfplumber, que produz o panic de
        # verdade neste sandbox (confirmado empiricamente antes desta
        # implementação: module='pyo3_runtime', name='PanicException').
        arquivos = [ArquivoEntradaLote(b'%PDF-1.4 conteudo qualquer', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item = resumo.itens[0]
        assert item.sucesso is True
        assert item.documento_id is not None
        assert item.roteamento_shadow is not None
        assert item.roteamento_shadow.executado is True
        assert item.roteamento_shadow.sucesso is False
        assert item.roteamento_shadow.motivo == MOTIVO_ERRO_TECNICO_SHADOW

    def test_panic_exception_equivalente_fiel_e_isolada(self, monkeypatch):
        """Equivalente FIEL ao achado real: uma classe construída com o
        MESMO módulo ('pyo3_runtime') e MESMO nome ('PanicException')
        confirmados empiricamente — sem depender do ambiente reproduzir
        o panic de verdade, e sem importar `pyo3_runtime` como
        dependência de produção."""
        ctx = _montar_servicos()

        PanicExceptionFiel = type('PanicException', (BaseException,), {'__module__': 'pyo3_runtime'})
        assert PanicExceptionFiel.__module__ == 'pyo3_runtime'
        assert PanicExceptionFiel.__name__ == 'PanicException'

        def _decidir_roteamento_panic(conteudo_pdf: bytes):
            raise PanicExceptionFiel("Python API call failed")

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_panic)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item = resumo.itens[0]
        assert item.sucesso is True
        assert item.documento_id is not None
        assert item.roteamento_shadow.executado is True
        assert item.roteamento_shadow.sucesso is False
        assert item.roteamento_shadow.motivo == MOTIVO_ERRO_TECNICO_SHADOW

    def test_outro_baseexception_com_nome_parecido_nao_e_isolado(self, monkeypatch):
        """Isolamento é CIRÚRGICO: uma classe chamada 'PanicException' mas
        em OUTRO módulo (não 'pyo3_runtime') não é absorvida — nunca
        confundir por nome sozinho."""
        ctx = _montar_servicos()

        class PanicException(BaseException):
            pass
        assert PanicException.__module__ != 'pyo3_runtime'

        def _decidir_roteamento_outro_panic(conteudo_pdf: bytes):
            raise PanicException("nao e o pyo3_runtime de verdade")

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_outro_panic)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        with pytest.raises(PanicException):
            ctx.servico_lote.criar_lote('upload_manual', arquivos)

    def test_keyboard_interrupt_nao_e_engolido(self, monkeypatch):
        ctx = _montar_servicos()

        def _decidir_roteamento_interrompe(conteudo_pdf: bytes):
            raise KeyboardInterrupt()

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_interrompe)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        with pytest.raises(KeyboardInterrupt):
            ctx.servico_lote.criar_lote('upload_manual', arquivos)

    def test_system_exit_nao_e_engolido(self, monkeypatch):
        ctx = _montar_servicos()

        def _decidir_roteamento_sai(conteudo_pdf: bytes):
            raise SystemExit(1)

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_sai)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        with pytest.raises(SystemExit):
            ctx.servico_lote.criar_lote('upload_manual', arquivos)

    def test_generator_exit_nao_e_engolido(self, monkeypatch):
        ctx = _montar_servicos()

        def _decidir_roteamento_generator_exit(conteudo_pdf: bytes):
            raise GeneratorExit()

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_generator_exit)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        with pytest.raises(GeneratorExit):
            ctx.servico_lote.criar_lote('upload_manual', arquivos)

    def test_cancelled_error_nao_e_engolido(self, monkeypatch):
        """asyncio.CancelledError é BaseException (não Exception) desde
        Python 3.8 — levantada aqui de forma síncrona, sem nenhuma
        infraestrutura async nova, só para confirmar que também
        propaga."""
        import asyncio
        ctx = _montar_servicos()

        def _decidir_roteamento_cancelado(conteudo_pdf: bytes):
            raise asyncio.CancelledError()

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_cancelado)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        with pytest.raises(asyncio.CancelledError):
            ctx.servico_lote.criar_lote('upload_manual', arquivos)


# ── Proveniência: origem sem metadados (não-Gmail) ────────────────────────────

class TestProvenienciaOrigemNaoGmail:
    def test_sem_metadados_origem_message_id_e_none(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento',
            lambda conteudo: _decisao_fake('Holerite', EstadoClassificacao.RESOLVIDA, EscopoDocumental.COLABORADOR),
        )

        arquivos = [ArquivoEntradaLote(b'conteudo sem metadados', 'x.pdf', 'application/pdf', metadados=None)]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item = resumo.itens[0]
        assert item.sucesso is True
        assert item.roteamento_shadow is not None
        assert item.roteamento_shadow.origem_message_id is None

    def test_metadados_sem_a_chave_origem_message_id_e_none(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento',
            lambda conteudo: _decisao_fake('Holerite', EstadoClassificacao.RESOLVIDA, EscopoDocumental.COLABORADOR),
        )

        arquivos = [ArquivoEntradaLote(
            b'conteudo com outros metadados', 'x.pdf', 'application/pdf',
            metadados={'outra_chave': 'valor'},
        )]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        assert resumo.itens[0].roteamento_shadow.origem_message_id is None

    def test_metadados_com_origem_message_id_e_repassado(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento',
            lambda conteudo: _decisao_fake('Holerite', EstadoClassificacao.RESOLVIDA, EscopoDocumental.COLABORADOR),
        )

        arquivos = [ArquivoEntradaLote(
            b'conteudo de email', 'x.pdf', 'application/pdf',
            metadados={'origem_message_id': '<abc123@mail.gmail.com>', 'origem_remetente': 'x@y.com'},
        )]
        resumo = ctx.servico_lote.criar_lote('email', arquivos)

        assert resumo.itens[0].roteamento_shadow.origem_message_id == '<abc123@mail.gmail.com>'


# ── Duplicado: shadow roda, semântica de duplicidade preservada ──────────────

class TestDuplicado:
    """Auditado: quando o conteúdo já foi registrado antes (mesmo hash),
    `criado_agora=False` e o item vem com `duplicado=True` -- isso NÃO
    muda com a integração shadow. O shadow roda igual (função pura,
    mesmo Documento existente, mesmos bytes), mantendo diagnóstico
    uniforme, sem criar novo Documento nem alterar a flag `duplicado`."""

    def test_duplicado_no_mesmo_lote_preserva_semantica_e_roda_shadow(self, monkeypatch):
        ctx = _montar_servicos()
        chamadas = []

        def _decidir_roteamento_espiao(conteudo: bytes):
            chamadas.append(conteudo)
            return _decisao_fake('Holerite', EstadoClassificacao.RESOLVIDA, EscopoDocumental.COLABORADOR)

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _decidir_roteamento_espiao)

        conteudo = b'mesmo conteudo duas vezes'
        arquivos = [
            ArquivoEntradaLote(conteudo, 'a.pdf', 'application/pdf'),
            ArquivoEntradaLote(conteudo, 'b.pdf', 'application/pdf'),
        ]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item_original, item_duplicado = resumo.itens

        # Semântica de duplicidade preservada -- não alterada por esta integração.
        assert item_original.duplicado is False
        assert item_duplicado.duplicado is True
        # Mesmo documento_id para ambos (idempotência por hash preservada).
        assert item_original.documento_id == item_duplicado.documento_id

        # Shadow roda para os dois (diagnóstico uniforme) -- nenhum novo
        # Documento criado (repo_docs continua com só 1 documento).
        assert item_original.roteamento_shadow is not None
        assert item_duplicado.roteamento_shadow is not None
        assert len(chamadas) == 2  # decidir_roteamento chamado 2x, mesmos bytes
        assert chamadas[0] == conteudo
        assert chamadas[1] == conteudo
        # Nenhum novo Documento criado para o duplicado -- só 1 documento
        # existe de fato no repositório para este hash.
        import hashlib
        doc = ctx.repo_docs.buscar_por_hash(hashlib.sha256(conteudo).hexdigest())
        assert doc is not None
        assert doc.documento_id == item_original.documento_id

    def test_bytes_passados_para_roteamento_sao_exatamente_os_mesmos_do_arquivo(self, monkeypatch):
        """`arquivo.conteudo` — nunca releitura, nunca recálculo de
        hash, nunca cópia — é o que chega em decidir_roteamento."""
        ctx = _montar_servicos()
        recebido = {}

        def _espiao(conteudo: bytes):
            recebido['bytes'] = conteudo
            return _decisao_fake('Holerite', EstadoClassificacao.RESOLVIDA, EscopoDocumental.COLABORADOR)

        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento', _espiao)

        conteudo_original = b'bytes identicos e rastreaveis'
        arquivos = [ArquivoEntradaLote(conteudo_original, 'x.pdf', 'application/pdf')]
        ctx.servico_lote.criar_lote('upload_manual', arquivos)

        assert recebido['bytes'] is conteudo_original  # mesma identidade de objeto, não só igualdade
