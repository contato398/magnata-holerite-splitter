"""Testes de caracterização: classificador_documental.py — migração de app.py.

Cobre:
- 17 tipos documentais (1+ caso positivo cada)
- Casos de produção real que motivaram precedência
- Colisão histórica conhecida → RESOLVIDA (por precedência comprovada)
- Colisão nova/artificial sem precedência → AMBIGUA + revisão humana
- Fallback "Outro"
- Comparação com o formato de retorno de app.py (tupla tipo/hits),
  reproduzida aqui só para teste — não existe wrapper de compatibilidade
  no core (ver nota da revisão).
"""

import pytest
from magnata_os.classificacao.classificador_documental import (
    classificar_documento,
    EstadoClassificacao,
    ResultadoClassificacaoDocumental,
)


def _tupla_legado(texto: str) -> tuple[str, int]:
    """Reproduz o formato (tipo, hits) de app.py classificar_documento()
    a partir do novo resultado — só para comparação em teste. Não existe
    função equivalente exposta pelo core (ver revisão: sem consumidor
    real de produção para essa API)."""
    resultado = classificar_documento(texto)
    return resultado.tipo_documental, resultado.quantidade_hits


# ── Caracterização de Tipos (1+ caso positivo cada) ────────────────────────────

class TestTipo01Rescisao:
    """Tipo 1: Rescisão — precisa vir ANTES de Holerite."""

    def test_resolvida_com_trct(self):
        resultado = classificar_documento("TRCT - Termo de Rescisão do Contrato de Trabalho")
        assert resultado.tipo_documental == "Rescisão"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA
        assert resultado.quantidade_hits > 0

    def test_resolvida_com_aviso_rescisao(self):
        resultado = classificar_documento("Aviso de Rescisão de Contrato")
        assert resultado.tipo_documental == "Rescisão"
        assert resultado.quantidade_hits > 0

    def test_resolvida_com_data_demissao(self):
        resultado = classificar_documento("Motivo demissão: x\nData de demissão: 15/07/2026")
        assert resultado.tipo_documental == "Rescisão"
        assert resultado.quantidade_hits > 0


class TestTipo02ExtratoFolhaPagamento:
    """Tipo 2: Extrato da Folha de Pagamento — precisa vir ANTES de Holerite."""

    def test_resolvida_com_extrato_folha_pagamento(self):
        resultado = classificar_documento("Extrato da Folha de Pagamento - Julho/2026")
        assert resultado.tipo_documental == "Extrato da Folha de Pagamento"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_extrato_mensal(self):
        resultado = classificar_documento("Extrato Mensal - Julho/2026")
        assert resultado.tipo_documental == "Extrato da Folha de Pagamento"
        assert resultado.quantidade_hits > 0


class TestTipo03DCTFWebRecibo:
    """Tipo 3: DCTFWeb - Recibo de Entrega — precisa vir ANTES de Declaração."""

    def test_resolvida_com_recibo_dctfweb(self):
        resultado = classificar_documento("Recibo de Entrega da DCTFWeb")
        assert resultado.tipo_documental == "DCTFWeb - Recibo de Entrega"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestTipo04GuiaDCTFWebDARF:
    """Tipo 4: Guia DCTFWeb/DARF."""

    def test_resolvida_com_guia_dctfweb(self):
        resultado = classificar_documento("Guia de Recolhimento da DCTFWeb")
        assert resultado.tipo_documental == "Guia DCTFWeb/DARF"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_darf_dctfweb(self):
        resultado = classificar_documento("DARF - DCTFWeb")
        assert resultado.tipo_documental == "Guia DCTFWeb/DARF"
        assert resultado.quantidade_hits > 0


class TestTipo05DCTFWebDeclaracao:
    """Tipo 5: DCTFWeb - Declaração (genérico catch-all)."""

    def test_resolvida_com_dctfweb_generico(self):
        resultado = classificar_documento("Declaração DCTFWeb")
        assert resultado.tipo_documental == "DCTFWeb - Declaração"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestTipo06FGTS:
    """Tipo 6: FGTS — precisa vir ANTES de Contrato de Trabalho, EPI, etc."""

    def test_resolvida_com_fgts_digital(self):
        resultado = classificar_documento("FGTS Digital - Guia Emitida")
        assert resultado.tipo_documental == "FGTS"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_guia_fgts(self):
        resultado = classificar_documento("Guia do FGTS - Julho/2026")
        assert resultado.tipo_documental == "FGTS"
        assert resultado.quantidade_hits > 0

    def test_resolvida_com_detalhe_guia_emitida(self):
        resultado = classificar_documento("Detalhe da Guia Emitida - FGTS")
        assert resultado.tipo_documental == "FGTS"
        assert resultado.quantidade_hits > 0


class TestTipo07Holerite:
    """Tipo 7: Holerite."""

    def test_resolvida_com_recibo_pagamento(self):
        resultado = classificar_documento("Recibo de Pagamento - Julho/2026")
        assert resultado.tipo_documental == "Holerite"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_valor_liquido(self):
        resultado = classificar_documento("Folha de Pagamento\nValor Líquido: R$ 5.000,00")
        assert resultado.tipo_documental == "Holerite"
        assert resultado.quantidade_hits > 0


class TestTipo08FolhaPonto:
    """Tipo 8: Folha de Ponto."""

    def test_resolvida_com_folha_ponto(self):
        resultado = classificar_documento("Folha de Ponto - Julho/2026")
        assert resultado.tipo_documental == "Folha de Ponto"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_secullum(self):
        resultado = classificar_documento("Ponto - Secullum")
        assert resultado.tipo_documental == "Folha de Ponto"
        assert resultado.quantidade_hits > 0

    def test_resolvida_com_ponto_web(self):
        resultado = classificar_documento("Ponto Web - Registro de Presença")
        assert resultado.tipo_documental == "Folha de Ponto"
        assert resultado.quantidade_hits > 0


class TestTipo09EPI:
    """Tipo 9: EPI."""

    def test_resolvida_com_ficha_epi(self):
        resultado = classificar_documento("Ficha de EPI - Proteção Individual")
        assert resultado.tipo_documental == "EPI"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_equipamento_protecao(self):
        resultado = classificar_documento("Equipamento de Proteção Individual")
        assert resultado.tipo_documental == "EPI"
        assert resultado.quantidade_hits > 0


class TestTipo10ProrrogacaoContratoExperiencia:
    """Tipo 10: Termo de Prorrogação de Contrato de Experiência."""

    def test_resolvida_com_prorrogacao(self):
        resultado = classificar_documento("Prorrogação do Contrato de Experiência")
        assert resultado.tipo_documental == "Termo de Prorrogação de Contrato de Experiência"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestTipo11FichaRegistroEmpregado:
    """Tipo 11: Ficha de Registro de Empregado."""

    def test_resolvida_com_ficha_registro(self):
        resultado = classificar_documento("Ficha de Registro de Empregado")
        assert resultado.tipo_documental == "Ficha de Registro de Empregado"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_matricula_esocial(self):
        resultado = classificar_documento("Matrícula eSocial - Registro de Empregado")
        assert resultado.tipo_documental == "Ficha de Registro de Empregado"
        assert resultado.quantidade_hits > 0


class TestTipo12ContratoExperiencia:
    """Tipo 12: Contrato de Experiência."""

    def test_resolvida_com_contrato_experiencia(self):
        resultado = classificar_documento("Contrato de Experiência - 90 dias")
        assert resultado.tipo_documental == "Contrato de Experiência"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestTipo13ContratoTrabalho:
    """Tipo 13: Contrato de Trabalho."""

    def test_resolvida_com_contrato_trabalho(self):
        resultado = classificar_documento("Contrato de Trabalho - Admissão")
        assert resultado.tipo_documental == "Contrato de Trabalho"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_ctps(self):
        resultado = classificar_documento("CTPS: 12345678900")
        assert resultado.tipo_documental == "Contrato de Trabalho"
        assert resultado.quantidade_hits > 0


class TestTipo14Ferias:
    """Tipo 14: Férias."""

    def test_resolvida_com_aviso_ferias(self):
        resultado = classificar_documento("Aviso de Férias - Julho/2026")
        assert resultado.tipo_documental == "Férias"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_recibo_ferias(self):
        resultado = classificar_documento("Recibo de Férias")
        assert resultado.tipo_documental == "Férias"
        assert resultado.quantidade_hits > 0


class TestTipo15GuiaGenerica:
    """Tipo 15: Guia (fallback genérico para GPS, DARF sem DCTFWeb)."""

    def test_resolvida_com_gps(self):
        resultado = classificar_documento("GPS - Guia de Previdência Social")
        assert resultado.tipo_documental == "Guia"
        assert resultado.quantidade_hits > 0

    def test_resolvida_com_darf_generico(self):
        resultado = classificar_documento("DARF - Documento de Arrecadação Federal")
        assert resultado.tipo_documental == "Guia"
        assert resultado.quantidade_hits > 0


class TestTipo16Boleto:
    """Tipo 16: Boleto."""

    def test_resolvida_com_codigo_barras(self):
        resultado = classificar_documento("12345.67890 12345.678901 12345.678901 1 12345678901234")
        assert resultado.tipo_documental == "Boleto"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestTipo17NotaFiscal:
    """Tipo 17: Nota Fiscal."""

    def test_resolvida_com_nfse(self):
        resultado = classificar_documento("NFS-e - Nota Fiscal de Serviço")
        assert resultado.tipo_documental == "Nota Fiscal"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA

    def test_resolvida_com_danfe(self):
        resultado = classificar_documento("DANFE - Documento de Arrecadação")
        assert resultado.tipo_documental == "Nota Fiscal"
        assert resultado.quantidade_hits > 0


class TestFallbackOutro:
    """Fallback: Outro (nenhum padrão casou)."""

    def test_nao_reconhecida_com_texto_aleatorio(self):
        resultado = classificar_documento("Lorem ipsum dolor sit amet")
        assert resultado.tipo_documental == "Outro"
        assert resultado.estado == EstadoClassificacao.NAO_RECONHECIDA
        assert resultado.quantidade_hits == 0


# ── Casos Reais de Produção — Colisão Histórica Conhecida → RESOLVIDA ─────────

class TestCasoRealProducao_TRCTxHolerite:
    """CASO REAL 05/07/2026: TRCT com 'Valor Líquido' não deve cair como Holerite."""

    def test_trct_com_valor_liquido_nao_e_holerite(self):
        texto_trct = """
        TERMO DE RESCISÃO DO CONTRATO DE TRABALHO
        ...
        Discriminação das Verbas Rescisórias:
        Valor Líquido: R$ 8.500,00
        """
        resultado = classificar_documento(texto_trct)
        assert resultado.tipo_documental == "Rescisão"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA
        assert "Holerite" in resultado.tipos_concorrentes


class TestCasoRealProducao_HoleritesComRubricasRescisao:
    """CASO REAL 05/07/2026: Rubricas internas em holerite não devem classificar como Rescisão."""

    def test_holerite_com_rubrica_liquido_rescisao_nao_e_rescisao(self):
        texto_holerite = """
        RECIBO DE PAGAMENTO
        Colaborador: João da Silva
        Período: Julho/2026
        Rubrica 1: Base de Cálculo - R$ 5.000,00
        Rubrica 2: 1/3 FERIAS RESCISAO - R$ 500,00
        Rubrica 3: LIQUIDO RESCISAO - R$ 2.000,00
        Total de Vencimentos: R$ 7.500,00
        Valor Líquido: R$ 5.200,00
        """
        resultado = classificar_documento(texto_holerite)
        assert resultado.tipo_documental == "Holerite"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestCasoRealProducao_FGTSxContratoTrabalho:
    """CASO REAL 10/07/2026: Guia FGTS Digital com glossário não deve cair como Contrato."""

    def test_fgts_com_glossario_contrato_trabalho_nao_e_contrato(self):
        texto_fgts = """
        DETALHE DA GUIA EMITIDA
        FGTS Mensal na Guia - Julho/2026
        Qtd. Trabalhadores FGTS: 98
        Total FGTS: R$ 45.000,00

        GLOSSÁRIO:
        Contrato de trabalho Verde e Amarelo
        Contrato de trabalho Intermitente
        Contrato de trabalho Terceirizado
        """
        resultado = classificar_documento(texto_fgts)
        assert resultado.tipo_documental == "FGTS"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA
        assert "Contrato de Trabalho" in resultado.tipos_concorrentes


class TestCasoRealProducao_ExtratoFolhaXHolerite:
    """Extrato mensal x Holerite — precedência preservada."""

    def test_extrato_mensal_sem_nome_completo_nao_e_holerite(self):
        resultado = classificar_documento("Extrato Mensal - Julho/2026\nTotal de Vencimentos: R$ 50.000,00")
        assert resultado.tipo_documental == "Extrato da Folha de Pagamento"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA


class TestCasoRealProducao_DCTFWebReciboXDeclaracao:
    """DCTFWeb: Recibo > Declaração genérica (precedência)."""

    def test_recibo_nao_e_declaracao_generica(self):
        resultado = classificar_documento("Recibo de Entrega da DCTFWeb")
        assert resultado.tipo_documental == "DCTFWeb - Recibo de Entrega"


class TestCasoRealProducao_FichaRegistroXContratoTrabalho:
    """Ficha de Registro (cita CTPS) x Contrato de Trabalho (padrão \\bCTPS\\b)."""

    def test_ficha_registro_com_ctps_nao_e_contrato_trabalho(self):
        texto = "Ficha de Registro de Empregado\nCTPS: 12345678900"
        resultado = classificar_documento(texto)
        assert resultado.tipo_documental == "Ficha de Registro de Empregado"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA
        assert "Contrato de Trabalho" in resultado.tipos_concorrentes


class TestCasoRealProducao_ProrrogacaoXContratoExperiencia:
    """Termo de Prorrogação (cita 'contrato de experiência') x Contrato de Experiência."""

    def test_prorrogacao_com_mencao_contrato_experiencia_nao_e_contrato_experiencia(self):
        texto = "Termo de Prorrogação do Contrato de Experiência - 30 dias adicionais"
        resultado = classificar_documento(texto)
        assert resultado.tipo_documental == "Termo de Prorrogação de Contrato de Experiência"
        assert resultado.estado == EstadoClassificacao.RESOLVIDA
        assert "Contrato de Experiência" in resultado.tipos_concorrentes


# ── Colisão NOVA / Artificial — Sem Precedência Comprovada → AMBIGUA ──────────

class TestColisaoNovaSemPrecedencia:
    """Requisito bloqueante da revisão: colisão sem precedência histórica
    explícita NUNCA vira RESOLVIDA só porque um tipo aparece antes na
    lista — deve virar AMBIGUA + necessita_revisao_humana=True."""

    def test_folha_ponto_x_epi_sem_precedencia_e_ambigua(self):
        """Folha de Ponto (pos 8) e EPI (pos 9) não têm precedência
        histórica declarada entre si. Se um texto casar em ambos, isso é
        uma colisão NOVA — nunca decidida silenciosamente."""
        texto = "Folha de Ponto - Secullum\nEquipamento de Proteção Individual entregue"
        resultado = classificar_documento(texto)
        assert resultado.estado == EstadoClassificacao.AMBIGUA
        assert resultado.tipo_documental == "Outro"
        assert resultado.necessita_revisao_humana is True
        assert resultado.prioridade_revisao == "ALTA"
        assert "Folha de Ponto" in resultado.tipos_concorrentes
        assert "EPI" in resultado.tipos_concorrentes

    def test_ferias_x_guia_sem_precedencia_e_ambigua(self):
        """Férias (pos 14) e Guia (pos 15) não têm precedência histórica
        declarada entre si."""
        texto = "Aviso de Férias\nGuia de Recolhimento GPS anexa"
        resultado = classificar_documento(texto)
        assert resultado.estado == EstadoClassificacao.AMBIGUA
        assert resultado.necessita_revisao_humana is True
        assert set(resultado.tipos_concorrentes) == {"Férias", "Guia"}

    def test_boleto_x_nota_fiscal_sem_precedencia_e_ambigua(self):
        """Boleto (pos 16) e Nota Fiscal (pos 17) não têm precedência
        histórica declarada entre si."""
        texto = "12345.67890 12345.678901 12345.678901 1 12345678901234\nDANFE anexo"
        resultado = classificar_documento(texto)
        assert resultado.estado == EstadoClassificacao.AMBIGUA
        assert resultado.necessita_revisao_humana is True
        assert set(resultado.tipos_concorrentes) == {"Boleto", "Nota Fiscal"}

    def test_ambigua_registra_todas_as_regras_matching(self):
        """regras_matching em caso AMBIGUA deve conter as evidências de
        TODOS os tipos concorrentes, não só do candidato."""
        texto = "Folha de Ponto - Secullum\nEquipamento de Proteção Individual entregue"
        resultado = classificar_documento(texto)
        assert resultado.estado == EstadoClassificacao.AMBIGUA
        assert "folha_ponto" in resultado.regras_matching
        assert "secullum" in resultado.regras_matching
        assert "equipamento_protecao_individual" in resultado.regras_matching


# ── Evidências Sanitizadas ─────────────────────────────────────────────────────

class TestEvidenciasSanitizadas:
    """Resultado nunca deve conter texto bruto, PII ou payload externo."""

    def test_resultado_nao_contem_pii(self):
        texto_com_pii = """
        Recibo de Pagamento
        Funcionário: João Silva Pereira
        CPF: 123.456.789-01
        CNPJ Empresa: 12.345.678/0001-90
        Valor Líquido: R$ 5.000,00
        """
        resultado = classificar_documento(texto_com_pii)
        assert resultado.tipo_documental == "Holerite"

        # Nenhum campo do resultado deve conter fragmento do texto original
        campos_texto = (
            resultado.tipo_documental,
            resultado.estado.value,
            str(resultado.quantidade_hits),
            " ".join(resultado.regras_matching),
            " ".join(resultado.tipos_concorrentes),
        )
        texto_concatenado = " ".join(campos_texto).lower()
        assert "joão" not in texto_concatenado
        assert "silva" not in texto_concatenado
        assert "123.456.789" not in texto_concatenado
        assert "12.345.678" not in texto_concatenado

    def test_regras_matching_sao_apenas_identificadores(self):
        resultado = classificar_documento("Recibo de Pagamento\nValor Líquido: R$ 1,00")
        for regra in resultado.regras_matching:
            # identificadores são snake_case simples, nunca frases com espaço
            assert " " not in regra
            assert regra.islower() or "_" in regra


# ── Formato Legado (tupla tipo/hits) — Comparação em Teste ────────────────────

class TestFormatoLegadoReproduzidoEmTeste:
    """Reproduz os 7 casos de test_classificacao_guia_dctfweb_darf.py usando
    `_tupla_legado()` (definida neste arquivo de teste, não no core — ver
    revisão: compatibilidade_app_py() foi removida do módulo de produção
    por não ter consumidor real)."""

    @pytest.mark.parametrize("texto,esperado", [
        ("Guia de Recolhimento DCTFWeb", ("Guia DCTFWeb/DARF", 1)),
        ("DARF - DCTFWeb", ("Guia DCTFWeb/DARF", 1)),
        ("Declaração DCTFWeb", ("DCTFWeb - Declaração", 1)),
        ("Recibo de Entrega da DCTFWeb referente à Guia DCTFWeb", ("DCTFWeb - Recibo de Entrega", 1)),
        ("Guia DCTFWeb", ("Guia DCTFWeb/DARF", 1)),
        ("DARF - Documento de Arrecadação", ("Guia", 1)),
        ("Comprovante de pagamento bancário", ("Outro", 0)),
    ])
    def test_caso_legado_reproduzido(self, texto, esperado):
        assert _tupla_legado(texto) == esperado


# ── Validações de Contrato ────────────────────────────────────────────────────

class TestValidacaoContrato:
    """ResultadoClassificacaoDocumental — validações estruturais."""

    def test_resolvida_exige_hits_positivos(self):
        with pytest.raises(ValueError, match="RESOLVIDA exige quantidade_hits > 0"):
            ResultadoClassificacaoDocumental(
                tipo_documental="Holerite",
                estado=EstadoClassificacao.RESOLVIDA,
                quantidade_hits=0,
            )

    def test_nao_reconhecida_exige_outro_e_zero_hits(self):
        with pytest.raises(ValueError, match="NAO_RECONHECIDA exige"):
            ResultadoClassificacaoDocumental(
                tipo_documental="Holerite",
                estado=EstadoClassificacao.NAO_RECONHECIDA,
                quantidade_hits=0,
            )

    def test_necessita_revisao_exige_prioridade(self):
        with pytest.raises(ValueError, match="necessita_revisao_humana exige prioridade"):
            ResultadoClassificacaoDocumental(
                tipo_documental="Holerite",
                estado=EstadoClassificacao.RESOLVIDA,
                quantidade_hits=2,
                necessita_revisao_humana=True,
            )

    def test_ambigua_exige_necessita_revisao_humana(self):
        with pytest.raises(ValueError, match="AMBIGUA exige necessita_revisao_humana"):
            ResultadoClassificacaoDocumental(
                tipo_documental="Outro",
                estado=EstadoClassificacao.AMBIGUA,
                quantidade_hits=2,
                tipos_concorrentes=("Férias", "Guia"),
            )

    def test_ambigua_exige_ao_menos_dois_tipos_concorrentes(self):
        with pytest.raises(ValueError, match="AMBIGUA exige ao menos 2 tipos concorrentes"):
            ResultadoClassificacaoDocumental(
                tipo_documental="Outro",
                estado=EstadoClassificacao.AMBIGUA,
                quantidade_hits=2,
                tipos_concorrentes=("Férias",),
                necessita_revisao_humana=True,
                prioridade_revisao="ALTA",
            )
