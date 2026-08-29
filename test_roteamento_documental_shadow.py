"""Testes de comportamento: roteamento_documental.py — ponte shadow.

NÃO replica os 58 testes de classificação (já cobertos em
test_classificador_documental_migracao.py) — testa só a TRADUÇÃO de
ResultadoClassificacaoDocumental para DecisaoRoteamentoDocumental, e o
fluxo completo bytes->decisão via um PDF fabricado em memória.
"""

import pytest

# `pdfplumber` (via pdfminer/cryptography) quebra neste ambiente com
# pyo3_runtime.PanicException (módulo nativo `_cffi_backend` ausente) —
# falha de AMBIENTE pré-existente, já documentada na auditoria da ponte
# Documento->ResultadoItem e em test_classificacao_guia_dctfweb_darf.py.
# Não é uma exceção Python normal (não é subclasse de Exception), então
# não pode ser capturada dentro do código de produção sem mascarar um
# crash real — os testes que exercitam extração de PDF de verdade são
# pulados aqui quando o ambiente está quebrado, nunca escondidos como
# "passou".
try:
    import pdfplumber  # noqa: F401
    _PDFPLUMBER_FUNCIONAL = True
except BaseException:
    _PDFPLUMBER_FUNCIONAL = False

_MOTIVO_SKIP_PDFPLUMBER = (
    "pdfplumber quebrado neste ambiente (pyo3_runtime.PanicException / "
    "_cffi_backend ausente) — falha de ambiente pré-existente, não do código novo"
)

from magnata_os.classificacao.classificador_documental import (
    EstadoClassificacao,
    ResultadoClassificacaoDocumental,
)
from magnata_os.classificacao.roteamento_documental import (
    AcaoRoteamento,
    DecisaoRoteamentoDocumental,
    EscopoDocumental,
    MotivoRoteamento,
    _ESCOPO_POR_TIPO,
    _TIPOS_COM_PROCESSADOR_AVULSO_COMPATIVEL,
    _traduzir_para_decisao,
    decidir_roteamento,
)


def _resolvida(tipo: str, hits: tuple[str, ...] = ("hit",), concorrentes: tuple[str, ...] = ()) -> ResultadoClassificacaoDocumental:
    return ResultadoClassificacaoDocumental(
        tipo_documental=tipo,
        estado=EstadoClassificacao.RESOLVIDA,
        quantidade_hits=len(hits),
        regras_matching=hits,
        tipos_concorrentes=concorrentes,
    )


# ── Contagem de escopos — critério de sucesso da revisão ──────────────────────

class TestContagemDeEscopos:
    def test_total_de_tipos_mapeados_e_17(self):
        assert len(_ESCOPO_POR_TIPO) == 17

    def test_contagem_por_escopo(self):
        contagem: dict[EscopoDocumental, int] = {}
        for escopo in _ESCOPO_POR_TIPO.values():
            contagem[escopo] = contagem.get(escopo, 0) + 1
        assert contagem[EscopoDocumental.COLABORADOR] == 9
        assert contagem[EscopoDocumental.CLIENTE] == 2
        assert contagem[EscopoDocumental.COMPETENCIA_GLOBAL] == 3
        assert contagem[EscopoDocumental.GENERICO] == 3


# ── Tradução: tipos individuais / colaborador ─────────────────────────────────

class TestTraducaoColaborador:
    def test_holerite_reconhecido(self):
        decisao = _traduzir_para_decisao(_resolvida("Holerite"))
        assert decisao.tipo_documental == "Holerite"
        assert decisao.estado_classificacao == EstadoClassificacao.RESOLVIDA
        assert decisao.escopo_documental == EscopoDocumental.COLABORADOR
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.motivo == MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL
        assert decisao.processador_disponivel is False

    def test_folha_de_ponto_reconhecida(self):
        decisao = _traduzir_para_decisao(_resolvida("Folha de Ponto"))
        assert decisao.escopo_documental == EscopoDocumental.COLABORADOR
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_rescisao_reconhecida(self):
        decisao = _traduzir_para_decisao(_resolvida("Rescisão"))
        assert decisao.escopo_documental == EscopoDocumental.COLABORADOR
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_epi_reconhecido(self):
        decisao = _traduzir_para_decisao(_resolvida("EPI"))
        assert decisao.escopo_documental == EscopoDocumental.COLABORADOR
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO


# ── Tradução: tipos por cliente ────────────────────────────────────────────────

class TestTraducaoCliente:
    def test_extrato_reconhecido(self):
        decisao = _traduzir_para_decisao(_resolvida("Extrato da Folha de Pagamento"))
        assert decisao.escopo_documental == EscopoDocumental.CLIENTE
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.processador_disponivel is False

    def test_fgts_reconhecido(self):
        decisao = _traduzir_para_decisao(_resolvida("FGTS"))
        assert decisao.escopo_documental == EscopoDocumental.CLIENTE
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO


# ── Tradução: tipos globais / broadcast por competência ────────────────────────

class TestTraducaoCompetenciaGlobal:
    def test_dctfweb_recibo_reconhecido(self):
        decisao = _traduzir_para_decisao(_resolvida("DCTFWeb - Recibo de Entrega"))
        assert decisao.escopo_documental == EscopoDocumental.COMPETENCIA_GLOBAL
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_dctfweb_declaracao_reconhecida(self):
        decisao = _traduzir_para_decisao(_resolvida("DCTFWeb - Declaração"))
        assert decisao.escopo_documental == EscopoDocumental.COMPETENCIA_GLOBAL
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_guia_dctfweb_darf_e_competencia_global(self):
        """Guia DCTFWeb/DARF permanece COMPETENCIA_GLOBAL (mesmo grupo
        documental do DCTFWeb) — diferente da Guia genérica (ver abaixo)."""
        decisao = _traduzir_para_decisao(_resolvida("Guia DCTFWeb/DARF"))
        assert decisao.escopo_documental == EscopoDocumental.COMPETENCIA_GLOBAL
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO


# ── Tradução: tipos genéricos, sem rota comprovada ─────────────────────────────

class TestTraducaoGenerico:
    def test_guia_generica_e_generico_nunca_competencia_global(self):
        """CORREÇÃO desta revisão: 'Guia' genérica NÃO é COMPETENCIA_GLOBAL
        — evidência legada direta: PROCESSADORES_DOCUMENTO['Guia'] =
        _processar_documento_sem_automacao (app.py), o mesmo handler
        usado para Boleto/Nota Fiscal, nunca uma rota broadcast."""
        decisao = _traduzir_para_decisao(_resolvida("Guia"))
        assert decisao.escopo_documental == EscopoDocumental.GENERICO
        assert decisao.escopo_documental != EscopoDocumental.COMPETENCIA_GLOBAL
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_boleto_reconhecido_e_generico(self):
        decisao = _traduzir_para_decisao(_resolvida("Boleto"))
        assert decisao.escopo_documental == EscopoDocumental.GENERICO
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_nota_fiscal_reconhecida_e_generica(self):
        decisao = _traduzir_para_decisao(_resolvida("Nota Fiscal"))
        assert decisao.escopo_documental == EscopoDocumental.GENERICO
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO


# ── Tipo reconhecido sem processador -> sempre REVISAR_HUMANO ─────────────────

class TestTipoResolvidoSemProcessadorViraRevisaoHumana:
    """Requisito da revisão: um tipo RESOLVIDO sem processador avulso
    comprovado nunca fica em 'limbo' — vira REVISAR_HUMANO explícito,
    preservando tipo/escopo corretos (mesmo comportamento do legado:
    _processar_documento_sem_automacao sempre cria Pendência + 'Revisão
    Manual')."""

    @pytest.mark.parametrize("tipo", [
        "Holerite", "Rescisão", "Extrato da Folha de Pagamento", "FGTS",
        "DCTFWeb - Recibo de Entrega", "DCTFWeb - Declaração",
        "Guia DCTFWeb/DARF", "Folha de Ponto", "EPI",
        "Termo de Prorrogação de Contrato de Experiência",
        "Ficha de Registro de Empregado", "Contrato de Experiência",
        "Contrato de Trabalho", "Férias", "Guia", "Boleto", "Nota Fiscal",
    ])
    def test_nenhum_tipo_recebe_acao_automatica_hoje(self, tipo):
        assert tipo not in _TIPOS_COM_PROCESSADOR_AVULSO_COMPATIVEL
        decisao = _traduzir_para_decisao(_resolvida(tipo))
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.acao_recomendada != AcaoRoteamento.PROCESSAR_AUTOMATICAMENTE
        assert decisao.processador_disponivel is False
        assert decisao.motivo == MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL
        # Classificação continua RESOLVIDA -- isto NÃO é ambiguidade.
        assert decisao.estado_classificacao == EstadoClassificacao.RESOLVIDA
        assert decisao.tipo_documental == tipo
        assert decisao.escopo_documental != EscopoDocumental.DESCONHECIDO

    def test_processador_disponivel_e_acao_automatica_ficam_reservados_para_o_futuro(self):
        """Hoje o conjunto de tipos com processador avulso está vazio —
        quando um adapter futuro for construído e comprovado, um tipo
        entra neste conjunto e passa a receber PROCESSAR_AUTOMATICAMENTE
        (não testado aqui por não existir ainda, só a garantia de que a
        mecânica está pronta para isso)."""
        assert _TIPOS_COM_PROCESSADOR_AVULSO_COMPATIVEL == frozenset()


# ── Distinção explícita: resolvido-sem-processador vs AMBIGUA vs NAO_RECONHECIDA vs INVALIDA

class TestDistincaoEntreMotivos:
    """Os 4 caminhos que levam (ou não) a REVISAR_HUMANO precisam ficar
    diferenciados pelo campo `motivo`, nunca só por inferência cruzando
    estado+ação."""

    def test_resolvido_sem_processador_tem_motivo_proprio(self):
        decisao = _traduzir_para_decisao(_resolvida("Holerite"))
        assert decisao.motivo == MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL
        assert decisao.estado_classificacao == EstadoClassificacao.RESOLVIDA

    def test_ambigua_tem_motivo_proprio_diferente(self):
        resultado = ResultadoClassificacaoDocumental(
            tipo_documental="Outro",
            estado=EstadoClassificacao.AMBIGUA,
            quantidade_hits=2,
            regras_matching=("folha_ponto", "epi_generico"),
            tipos_concorrentes=("Folha de Ponto", "EPI"),
            necessita_revisao_humana=True,
            prioridade_revisao="ALTA",
        )
        decisao = _traduzir_para_decisao(resultado)
        assert decisao.motivo == MotivoRoteamento.CLASSIFICACAO_AMBIGUA
        assert decisao.motivo != MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.escopo_documental == EscopoDocumental.DESCONHECIDO
        assert decisao.prioridade_revisao == "ALTA"
        assert set(decisao.tipos_concorrentes) == {"Folha de Ponto", "EPI"}

    def test_nao_reconhecida_tem_motivo_proprio_diferente(self):
        resultado = ResultadoClassificacaoDocumental(
            tipo_documental="Outro",
            estado=EstadoClassificacao.NAO_RECONHECIDA,
            quantidade_hits=0,
        )
        decisao = _traduzir_para_decisao(resultado)
        assert decisao.motivo == MotivoRoteamento.TIPO_NAO_RECONHECIDO
        assert decisao.motivo not in (
            MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
            MotivoRoteamento.CLASSIFICACAO_AMBIGUA,
        )
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.tipo_documental == "Outro"
        assert decisao.escopo_documental == EscopoDocumental.DESCONHECIDO

    @pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
    def test_pdf_invalido_tem_motivo_proprio_diferente(self):
        decisao = decidir_roteamento(b"isto-nao-e-um-pdf-valido")
        assert decisao.motivo == MotivoRoteamento.PDF_INVALIDO
        assert decisao.estado_classificacao == EstadoClassificacao.INVALIDA
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_bytes_vazios_tem_motivo_pdf_invalido(self):
        decisao = decidir_roteamento(b"")
        assert decisao.motivo == MotivoRoteamento.PDF_INVALIDO
        assert decisao.estado_classificacao == EstadoClassificacao.INVALIDA
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO

    def test_os_quatro_motivos_sao_distintos_entre_si(self):
        motivos_vistos = set()

        motivos_vistos.add(_traduzir_para_decisao(_resolvida("Holerite")).motivo)
        motivos_vistos.add(_traduzir_para_decisao(ResultadoClassificacaoDocumental(
            tipo_documental="Outro", estado=EstadoClassificacao.AMBIGUA,
            quantidade_hits=1, regras_matching=("x",),
            tipos_concorrentes=("A", "B"), necessita_revisao_humana=True,
            prioridade_revisao="ALTA",
        )).motivo)
        motivos_vistos.add(_traduzir_para_decisao(ResultadoClassificacaoDocumental(
            tipo_documental="Outro", estado=EstadoClassificacao.NAO_RECONHECIDA,
            quantidade_hits=0,
        )).motivo)
        motivos_vistos.add(decidir_roteamento(b"").motivo)

        assert motivos_vistos == {
            MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
            MotivoRoteamento.CLASSIFICACAO_AMBIGUA,
            MotivoRoteamento.TIPO_NAO_RECONHECIDO,
            MotivoRoteamento.PDF_INVALIDO,
        }


# ── Fluxo completo bytes -> decisão, com PDF real fabricado em memória ────────

def _pdf_minimo_com_texto(texto: str) -> bytes:
    """Fabrica um PDF válido mínimo contendo `texto` como conteúdo de
    página, usando reportlab se disponível."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import io
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.drawString(72, 720, texto)
        c.save()
        return buffer.getvalue()
    except ImportError:
        pytest.skip("reportlab não disponível neste ambiente — pulando teste de PDF real")


@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
class TestFluxoCompletoComPdfReal:
    """Fluxo bytes -> extrair_texto_pdf -> classificar_documento ->
    decisão, de ponta a ponta, com um PDF de verdade fabricado em
    memória (não um mock de texto). Confirma também que a promoção da
    extração para o módulo neutro não quebrou o fluxo."""

    def test_holerite_via_pdf_real(self):
        pdf_bytes = _pdf_minimo_com_texto("Recibo de Pagamento - Valor Liquido")
        decisao = decidir_roteamento(pdf_bytes)
        assert decisao.tipo_documental == "Holerite"
        assert decisao.estado_classificacao == EstadoClassificacao.RESOLVIDA
        assert decisao.escopo_documental == EscopoDocumental.COLABORADOR
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.motivo == MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL

    def test_texto_desconhecido_via_pdf_real(self):
        pdf_bytes = _pdf_minimo_com_texto("Lorem ipsum dolor sit amet")
        decisao = decidir_roteamento(pdf_bytes)
        assert decisao.tipo_documental == "Outro"
        assert decisao.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO
        assert decisao.motivo == MotivoRoteamento.TIPO_NAO_RECONHECIDO


# ── Evidências sanitizadas — nenhuma PII/texto bruto no resultado ─────────────

class TestEvidenciasSanitizadas:
    def test_decisao_nao_contem_pii(self):
        resultado = ResultadoClassificacaoDocumental(
            tipo_documental="Holerite",
            estado=EstadoClassificacao.RESOLVIDA,
            quantidade_hits=1,
            regras_matching=("valor_liquido",),
        )
        decisao = _traduzir_para_decisao(resultado)
        campos_texto = " ".join([
            decisao.tipo_documental,
            decisao.estado_classificacao.value,
            decisao.escopo_documental.value,
            decisao.acao_recomendada.value,
            decisao.motivo.value,
            " ".join(decisao.evidencias_sanitizadas),
            " ".join(decisao.tipos_concorrentes),
        ]).lower()
        assert "cpf" not in campos_texto
        assert "cnpj" not in campos_texto
        assert "123.456" not in campos_texto

    def test_evidencias_sao_apenas_identificadores(self):
        decisao = _traduzir_para_decisao(_resolvida("Holerite", hits=("recibo_pagamento", "valor_liquido")))
        for evidencia in decisao.evidencias_sanitizadas:
            assert " " not in evidencia


# ── Validações de contrato ─────────────────────────────────────────────────────

class TestValidacaoContrato:
    def test_processar_automaticamente_exige_processador_disponivel(self):
        with pytest.raises(ValueError, match="PROCESSAR_AUTOMATICAMENTE exige processador_disponivel"):
            DecisaoRoteamentoDocumental(
                tipo_documental="Holerite",
                estado_classificacao=EstadoClassificacao.RESOLVIDA,
                escopo_documental=EscopoDocumental.COLABORADOR,
                acao_recomendada=AcaoRoteamento.PROCESSAR_AUTOMATICAMENTE,
                motivo=MotivoRoteamento.TIPO_RESOLVIDO_COM_PROCESSADOR,
                processador_disponivel=False,
                necessita_revisao_humana=False,
            )

    def test_revisar_humano_exige_necessita_revisao(self):
        with pytest.raises(ValueError, match="REVISAR_HUMANO exige necessita_revisao_humana"):
            DecisaoRoteamentoDocumental(
                tipo_documental="Outro",
                estado_classificacao=EstadoClassificacao.NAO_RECONHECIDA,
                escopo_documental=EscopoDocumental.DESCONHECIDO,
                acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
                motivo=MotivoRoteamento.TIPO_NAO_RECONHECIDO,
                processador_disponivel=False,
                necessita_revisao_humana=False,
            )

    def test_revisar_humano_incompativel_com_processador_disponivel(self):
        with pytest.raises(ValueError, match="REVISAR_HUMANO é incompatível com processador_disponivel"):
            DecisaoRoteamentoDocumental(
                tipo_documental="Holerite",
                estado_classificacao=EstadoClassificacao.RESOLVIDA,
                escopo_documental=EscopoDocumental.COLABORADOR,
                acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
                motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
                processador_disponivel=True,
                necessita_revisao_humana=True,
                prioridade_revisao="BAIXA",
            )

    def test_motivo_ambigua_exige_estado_ambigua(self):
        with pytest.raises(ValueError, match="motivo=CLASSIFICACAO_AMBIGUA exige estado_classificacao=AMBIGUA"):
            DecisaoRoteamentoDocumental(
                tipo_documental="Outro",
                estado_classificacao=EstadoClassificacao.NAO_RECONHECIDA,
                escopo_documental=EscopoDocumental.DESCONHECIDO,
                acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
                motivo=MotivoRoteamento.CLASSIFICACAO_AMBIGUA,
                processador_disponivel=False,
                necessita_revisao_humana=True,
                prioridade_revisao="ALTA",
            )

    def test_motivo_processador_ausente_exige_estado_resolvida(self):
        with pytest.raises(ValueError, match="motivo=PROCESSADOR_AINDA_NAO_DISPONIVEL exige estado_classificacao=RESOLVIDA"):
            DecisaoRoteamentoDocumental(
                tipo_documental="Outro",
                estado_classificacao=EstadoClassificacao.NAO_RECONHECIDA,
                escopo_documental=EscopoDocumental.DESCONHECIDO,
                acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
                motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
                processador_disponivel=False,
                necessita_revisao_humana=True,
                prioridade_revisao="BAIXA",
            )
