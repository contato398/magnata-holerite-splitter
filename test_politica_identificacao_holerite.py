"""Testes da política pura de transição CLASSIFICACAO -> IDENTIFICACAO
para Holerite avulso (magnata_os/documental/modulo01/
politica_identificacao_holerite.py) e das duas funções puras de domínio
que a alimentam (magnata_os/documental/importacao_lote/dominio.py:
extrair_nome_funcionario_de_texto, extrair_cpfs_distintos_de_texto).

Nenhum destes testes usa PDF real, Airtable, nem qualquer I/O — tudo
opera sobre texto/candidatos já em memória (funções puras).
"""
from __future__ import annotations

import pytest

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.documental.importacao_lote import dominio as importacao_dominio
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.modulo01.dominio_esteira import SituacaoEsteira
from magnata_os.documental.modulo01.politica_identificacao_holerite import (
    CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO,
    CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO,
    MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_AMBIGUO,
    MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_NAO_ENCONTRADO,
    MOTIVO_TRANSICAO_IDENTIFICACAO_PDF_MESTRE_SUSPEITO,
    MOTIVO_TRANSICAO_IDENTIFICACAO_RESOLVIDA,
    DecisaoTransicaoIdentificacao,
    MestreSuspeitoIdentificacaoHolerite,
    correspondencia_para_resolucao_dimensao,
    decidir_transicao_identificacao,
    resolver_identificacao_holerite_de_texto,
)


# ============================================================================
# B. Nome do colaborador (extrair_nome_funcionario_de_texto)
# ============================================================================

class TestExtrairNomeFuncionarioDeTexto:
    def test_extrai_nome_padrao_holerite(self):
        texto = (
            "Recibo de Pagamento\n"
            "Nome do Funcionário\n"
            "001234 JOAO DA SILVA 56789\n"
            "Valor Liquido: 1.000,00\n"
        )
        assert importacao_dominio.extrair_nome_funcionario_de_texto(texto) == "JOAO DA SILVA"

    def test_extrai_nome_padrao_sem_acento(self):
        texto = (
            "Nome do Funcionario\n"
            "007 MARIA DOS SANTOS 11111\n"
        )
        assert importacao_dominio.extrair_nome_funcionario_de_texto(texto) == "MARIA DOS SANTOS"

    def test_sem_marcador_retorna_none(self):
        assert importacao_dominio.extrair_nome_funcionario_de_texto(
            "Documento qualquer sem nenhum marcador conhecido"
        ) is None

    def test_texto_vazio_retorna_none(self):
        assert importacao_dominio.extrair_nome_funcionario_de_texto("") is None

    def test_marcador_sem_linha_seguinte_retorna_none(self):
        assert importacao_dominio.extrair_nome_funcionario_de_texto("Nome do Funcionário") is None

    def test_nunca_retorna_literal_desconhecido(self):
        resultado = importacao_dominio.extrair_nome_funcionario_de_texto("nada aqui bate")
        assert resultado is None
        assert resultado != "Desconhecido"

    def test_colaborador_nao_e_aceito_no_extrator_de_holerite(self):
        """Achado da auditoria read-only prévia: "Colaborador:" é
        específico do formato de Folha de Ponto Manual (v2.99, comentário
        do próprio legado) -- o extrator de Holerite NUNCA deve
        reconhecer esse marcador."""
        texto = "Colaborador: MARIA DA SILVA\nOutras linhas do documento"
        assert importacao_dominio.extrair_nome_funcionario_de_texto(texto) is None


# ============================================================================
# C. Múltiplos CPFs (extrair_cpfs_distintos_de_texto)
# ============================================================================

class TestExtrairCpfsDistintosDeTexto:
    def test_zero_cpfs_retorna_tupla_vazia(self):
        assert importacao_dominio.extrair_cpfs_distintos_de_texto("nenhum cpf aqui") == ()

    def test_um_cpf_retorna_um_normalizado(self):
        resultado = importacao_dominio.extrair_cpfs_distintos_de_texto(
            "CPF: 123.456.789-01\nOutro texto"
        )
        assert resultado == ("12345678901",)

    def test_cpf_repetido_retorna_um_unico(self):
        texto = "CPF: 123.456.789-01\n... página 2 ...\nCPF: 123.456.789-01"
        resultado = importacao_dominio.extrair_cpfs_distintos_de_texto(texto)
        assert resultado == ("12345678901",)

    def test_dois_cpfs_distintos_retorna_dois(self):
        texto = "CPF: 111.222.333-44\nCPF: 555.666.777-88"
        resultado = importacao_dominio.extrair_cpfs_distintos_de_texto(texto)
        assert len(resultado) == 2
        assert set(resultado) == {"11122233344", "55566677788"}

    def test_texto_vazio_retorna_tupla_vazia(self):
        assert importacao_dominio.extrair_cpfs_distintos_de_texto("") == ()

    def test_ordem_e_de_primeira_ocorrencia(self):
        texto = "CPF: 555.666.777-88\nCPF: 111.222.333-44"
        resultado = importacao_dominio.extrair_cpfs_distintos_de_texto(texto)
        assert resultado == ("55566677788", "11122233344")


# ============================================================================
# D. Tradução ResultadoCorrespondencia -> ResolucaoDimensao e política
# ============================================================================

def _candidato(func_id: str, cpf: str | None, nome: str) -> CandidatoFuncionario:
    return CandidatoFuncionario(func_id=func_id, cpf=cpf, nome_normalizado=nome)


class TestResolverIdentificacaoHoleriteDeTexto:
    def test_cpf_exato_resolve_colaborador(self):
        texto = "Nome do Funcionário\n001 JOAO DA SILVA 22222\nCPF: 123.456.789-01"
        candidatos = [_candidato("func-1", "123.456.789-01", "JOAO DA SILVA")]

        resultado = resolver_identificacao_holerite_de_texto(texto, candidatos)

        assert isinstance(resultado, ResolucaoDimensao)
        assert resultado.dimensao == DimensaoResolucao.COLABORADOR
        assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
        assert resultado.valores_confirmados == (ReferenciaCanonica('COLABORADOR', 'func-1'),)

    def test_cpf_ausente_nome_exato_unico_resolve_colaborador(self):
        texto = "Nome do Funcionário\n001 MARIA DOS SANTOS 33333\nsem cpf formatado aqui"
        candidatos = [_candidato("func-2", None, "MARIA DOS SANTOS")]

        resultado = resolver_identificacao_holerite_de_texto(texto, candidatos)

        assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
        assert resultado.valores_confirmados == (ReferenciaCanonica('COLABORADOR', 'func-2'),)

    def test_candidato_ambiguo(self):
        texto = "CPF: 123.456.789-01"
        candidatos = [
            _candidato("func-1", "123.456.789-01", "JOAO DA SILVA"),
            _candidato("func-2", "123.456.789-01", "JOAO DA SILVA JUNIOR"),
        ]

        resultado = resolver_identificacao_holerite_de_texto(texto, candidatos)

        assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA
        assert resultado.valores_confirmados == ()

    def test_nao_encontrado(self):
        texto = "CPF: 999.999.999-99"
        candidatos = [_candidato("func-1", "123.456.789-01", "JOAO DA SILVA")]

        resultado = resolver_identificacao_holerite_de_texto(texto, candidatos)

        assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
        assert resultado.valores_confirmados == ()

    def test_dois_cpfs_distintos_vira_mestre_suspeito_sem_chamar_resolver_funcionario(self, monkeypatch):
        texto = "CPF: 111.222.333-44\nCPF: 555.666.777-88"
        candidatos = [_candidato("func-1", "111.222.333-44", "JOAO DA SILVA")]

        def _resolver_funcionario_nunca_deveria_ser_chamado(*args, **kwargs):
            raise AssertionError(
                "resolver_funcionario NUNCA deve ser chamado quando 2+ CPFs "
                "distintos foram encontrados (mestre suspeito) -- nunca "
                "escolhe o primeiro CPF."
            )

        monkeypatch.setattr(
            importacao_dominio, 'resolver_funcionario', _resolver_funcionario_nunca_deveria_ser_chamado,
        )
        import magnata_os.documental.modulo01.politica_identificacao_holerite as politica_mod
        monkeypatch.setattr(
            politica_mod, 'resolver_funcionario', _resolver_funcionario_nunca_deveria_ser_chamado,
        )

        resultado = resolver_identificacao_holerite_de_texto(texto, candidatos)

        assert isinstance(resultado, MestreSuspeitoIdentificacaoHolerite)
        assert resultado.quantidade_cpfs_distintos == 2

    def test_nunca_carrega_cpf_ou_nome_na_resolucao(self):
        """ResolucaoDimensao nunca deve conter CPF nem nome -- só
        entidade_id (record id) e códigos sanitizados de motivo."""
        texto = "Nome do Funcionário\n001 JOAO DA SILVA 22222\nCPF: 123.456.789-01"
        candidatos = [_candidato("func-1", "123.456.789-01", "JOAO DA SILVA")]

        resultado = resolver_identificacao_holerite_de_texto(texto, candidatos)

        bruto = str(resultado)
        assert "123.456.789-01" not in bruto
        assert "12345678901" not in bruto
        assert "JOAO DA SILVA" not in bruto


class TestMestreSuspeitoIdentificacaoHolerite:
    def test_exige_pelo_menos_dois_cpfs(self):
        with pytest.raises(ValueError):
            MestreSuspeitoIdentificacaoHolerite(quantidade_cpfs_distintos=1)

    def test_aceita_dois_ou_mais(self):
        assert MestreSuspeitoIdentificacaoHolerite(quantidade_cpfs_distintos=2).quantidade_cpfs_distintos == 2


class TestCorrespondenciaParaResolucaoDimensao:
    def test_traducao_nao_reconhecida_levanta_fail_safe(self):
        """Enum fechado -- DUPLICATE nunca deveria chegar aqui vindo de
        resolver_funcionario, mas o fail-safe precisa recusar
        explicitamente, nunca decidir por omissão."""
        from magnata_os.documental.importacao_lote.contratos import (
            ClassificacaoCorrespondencia,
            MotivoSanitizado,
            ResultadoCorrespondencia,
        )
        correspondencia = ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.DUPLICATE, None, MotivoSanitizado.OK, None,
        )
        with pytest.raises(ValueError):
            correspondencia_para_resolucao_dimensao(correspondencia)


# ── Tabela de decisão CLASSIFICACAO -> IDENTIFICACAO ──────────────────────────

def _resolucao(estado: EstadoResolucaoDimensao, entidade_id: str | None = None) -> ResolucaoDimensao:
    valores = (ReferenciaCanonica('COLABORADOR', entidade_id),) if entidade_id else ()
    return ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=estado, valores_confirmados=valores)


class TestDecidirTransicaoIdentificacao:
    def test_resolvida_avanca_concluido_sem_bloqueio(self):
        decisao = decidir_transicao_identificacao(_resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'))
        assert decisao.deve_avancar is True
        assert decisao.situacao_identificacao == SituacaoEsteira.CONCLUIDO
        assert decisao.deve_bloquear is False
        assert decisao.motivo_bloqueio is None
        assert decisao.motivo_transicao == MOTIVO_TRANSICAO_IDENTIFICACAO_RESOLVIDA

    def test_ambigua_avanca_e_bloqueia_com_motivo_proprio(self):
        decisao = decidir_transicao_identificacao(_resolucao(EstadoResolucaoDimensao.AMBIGUA))
        assert decisao.deve_avancar is True
        assert decisao.situacao_identificacao == SituacaoEsteira.BLOQUEADO
        assert decisao.deve_bloquear is True
        assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO
        assert decisao.motivo_bloqueio.resolvivel_automaticamente is False
        assert decisao.motivo_transicao == MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_AMBIGUO
        # Nunca reaproveita o código de bloqueio de mestre suspeito.
        assert decisao.motivo_bloqueio.codigo != CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO

    def test_nao_encontrada_avanca_em_revisao_sem_hard_block(self):
        decisao = decidir_transicao_identificacao(_resolucao(EstadoResolucaoDimensao.NAO_ENCONTRADA))
        assert decisao.deve_avancar is True
        assert decisao.situacao_identificacao == SituacaoEsteira.EM_REVISAO
        assert decisao.deve_bloquear is False
        assert decisao.motivo_bloqueio is None
        assert decisao.motivo_transicao == MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_NAO_ENCONTRADO

    def test_mestre_suspeito_avanca_e_bloqueia_com_motivo_proprio(self):
        decisao = decidir_transicao_identificacao(
            MestreSuspeitoIdentificacaoHolerite(quantidade_cpfs_distintos=3)
        )
        assert decisao.deve_avancar is True
        assert decisao.situacao_identificacao == SituacaoEsteira.BLOQUEADO
        assert decisao.deve_bloquear is True
        assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO
        assert decisao.motivo_bloqueio.resolvivel_automaticamente is False
        assert decisao.motivo_transicao == MOTIVO_TRANSICAO_IDENTIFICACAO_PDF_MESTRE_SUSPEITO
        # Nunca reaproveita o código de bloqueio de colaborador ambíguo --
        # condição documental diferente (auditoria read-only prévia).
        assert decisao.motivo_bloqueio.codigo != CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO

    def test_estado_desconhecido_e_fail_safe_nunca_avanca_em_silencio(self):
        resolucao_invalida = ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.ERRO_TECNICO,
        )
        with pytest.raises(ValueError):
            decidir_transicao_identificacao(resolucao_invalida)

    def test_dimensao_errada_e_recusada(self):
        resolucao_cliente = ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
        )
        with pytest.raises(ValueError):
            decidir_transicao_identificacao(resolucao_cliente)


class TestValidacaoContratoDecisaoTransicaoIdentificacao:
    def test_deve_avancar_false_nao_aceita_campos_de_bloqueio(self):
        with pytest.raises(ValueError):
            DecisaoTransicaoIdentificacao(
                deve_avancar=False, situacao_identificacao=SituacaoEsteira.CONCLUIDO,
                deve_bloquear=False, motivo_bloqueio=None, motivo_transicao=None,
            )

    def test_deve_avancar_true_exige_situacao(self):
        with pytest.raises(ValueError):
            DecisaoTransicaoIdentificacao(
                deve_avancar=True, situacao_identificacao=None,
                deve_bloquear=False, motivo_bloqueio=None, motivo_transicao=None,
            )

    def test_deve_bloquear_exige_motivo(self):
        with pytest.raises(ValueError):
            DecisaoTransicaoIdentificacao(
                deve_avancar=True, situacao_identificacao=SituacaoEsteira.BLOQUEADO,
                deve_bloquear=True, motivo_bloqueio=None, motivo_transicao=None,
            )
