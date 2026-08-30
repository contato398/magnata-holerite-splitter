"""Produtores de evidência para o motor geral de compreensão documental
(`resolucao_tipo_documental.py`) — cada função aqui converte o
resultado de um especialista JÁ EXISTENTE (nunca reimplementado) numa
ou mais `HipoteseTipoDocumental`. Nenhuma função aqui decide o tipo
final de um documento — só produz evidência para o resolvedor geral
decidir.

Três produtores, cada um documentado com sua força/limite:

1. TEXTUAL (`hipoteses_textuais_de_classificacao`) — reaproveita
   `classificador_documental.classificar_documento` (as 17 regras +
   precedência histórica, intocadas desde a migração do legado) através
   do tradutor já existente `resultado_classificacao_para_resolucao_
   dimensao` (PR #93). Quando o classificador resolve com confiança
   (RESOLVIDA), produz 1 hipótese forte/moderada; quando encontra uma
   colisão sem precedência (AMBIGUA), produz 1 hipótese FRACA por
   candidato concorrente -- nunca finaliza a decisão sozinho nesse
   caso, mas oferece ao resolvedor geral a chance de um outro produtor
   desempatar (Fase H da missão: remover uma frase característica não
   deve necessariamente perder o reconhecimento, se outra evidência
   real sustentar o mesmo candidato).

2. ENTIDADES/ESTRUTURAL (`contar_entidades_distintas_no_texto`) --
   reaproveita `extrair_cpfs_distintos_de_texto` (importacao_lote/
   dominio.py, já pura, já comprovada para detectar "PDF mestre
   suspeito" no fluxo de Holerite avulso). Aqui GENERALIZADO: a
   contagem nunca decide um tipo por si só -- só alimenta o fail-safe
   genérico de `resolver_tipo_documental` (múltiplas entidades primárias
   distintas nunca resolvem sozinhas para um único tipo, qualquer que
   ele seja).

3. CONTEXTUAL (`hipoteses_contextuais`) -- remetente/assunto/origem.
   SEMPRE produz evidência FRACA, estruturalmente (o dataclass
   `EvidenciaSanitizada` resultante nunca é FORTE/MODERADA aqui) --
   nunca decide sozinho. Recebe `SinalContextual` já sanitizados por
   quem chama (nunca o remetente/assunto bruto) -- a REGRA de "que
   remetente sugere que tipo" é responsabilidade de quem compõe o
   pipeline (ex.: um futuro adapter de e-mail), nunca hardcoded aqui;
   este módulo só sabe traduzir um sinal já identificado em evidência
   fraca, mantendo a política de correspondência remetente->tipo fora
   do motor geral (nunca duplicando `REMETENTE_FISCAL`/`app.py`, que
   continua legado protegido).

Nenhum destes produtores conhece "Holerite"/"Extrato"/"FGTS"/"DCTFWeb"
por nome -- só delegam a especialistas que, esses sim, conhecem os
tipos (classificador_documental.py).
"""
from __future__ import annotations

import dataclasses
from typing import Tuple

from ..documental.importacao_lote.dominio import extrair_cpfs_distintos_de_texto
from .classificador_documental import (
    EstadoClassificacao,
    ResultadoClassificacaoDocumental,
    resultado_classificacao_para_resolucao_dimensao,
)
from .contratos import EstadoResolucaoDimensao, EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental


def hipoteses_textuais_de_classificacao(
    resultado: ResultadoClassificacaoDocumental,
) -> Tuple[HipoteseTipoDocumental, ...]:
    """Traduz o resultado JÁ CALCULADO por `classificar_documento`
    (nunca reclassifica) em hipóteses para o resolvedor geral.

    RESOLVIDA -> 1 hipótese (o tipo vencedor), com a evidência/força já
    calculada por `resultado_classificacao_para_resolucao_dimensao`
    (FORTE se match único e limpo, MODERADA se decidido por precedência
    histórica sobre colisão real).
    AMBIGUA -> 1 hipótese FRACA por candidato concorrente -- nenhum
    vencedor aqui; o resolvedor geral decide se outro produtor desempata.
    NAO_RECONHECIDA/INVALIDA -> nenhuma hipótese (nenhuma evidência
    textual disponível)."""
    if resultado.estado == EstadoClassificacao.RESOLVIDA:
        resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)
        tipo_vencedor = resolucao.valores_confirmados[0].entidade_id
        return (HipoteseTipoDocumental(tipo_documental=tipo_vencedor, evidencias=resolucao.evidencias),)

    if resultado.estado == EstadoClassificacao.AMBIGUA:
        resolucao = resultado_classificacao_para_resolucao_dimensao(resultado)
        assert resolucao.estado == EstadoResolucaoDimensao.AMBIGUA
        return tuple(
            HipoteseTipoDocumental(
                tipo_documental=candidato.entidade_id,
                evidencias=(
                    EvidenciaSanitizada(
                        tipo_evidencia='REGEX_PADRAO_TEXTUAL_EM_COLISAO',
                        fonte='classificador_documental',
                        referencia_fonte=candidato.entidade_id,
                        metodo='regex_colisao_sem_precedencia',
                        forca=NivelConfianca.FRACA,
                    ),
                ),
            )
            for candidato in resolucao.candidatos
        )

    # NAO_RECONHECIDA / INVALIDA -- nenhuma evidência textual.
    return ()


def contar_entidades_distintas_no_texto(texto: str) -> int:
    """Conta quantos CPFs distintos aparecem no texto -- reaproveita
    `extrair_cpfs_distintos_de_texto` (importacao_lote/dominio.py) sem
    alteração. Sinal estrutural GENÉRICO ("quantas entidades primárias
    distintas este documento parece conter"), nunca usado para decidir
    tipo -- só alimenta `resolver_tipo_documental(quantidade_entidades_
    distintas=...)`, que nunca deixa 2+ entidades resolverem sozinhas
    para um único tipo."""
    return len(extrair_cpfs_distintos_de_texto(texto))


@dataclasses.dataclass(frozen=True)
class SinalContextual:
    """UM sinal contextual JÁ IDENTIFICADO e já sanitizado por quem
    chama (nunca o remetente/assunto/origem em texto livre) -- ex.:
    `SinalContextual('REMETENTE_CATEGORIA_FISCAL', 'email_metadata',
    'categoria:fiscal', 'Guia DCTFWeb/DARF')` representa "o remetente
    deste e-mail já foi categorizado externamente como fiscal, o que
    sugeria fracamente o tipo Guia DCTFWeb/DARF" -- nunca o e-mail em
    si. A REGRA de categorização (que remetente é "fiscal") é
    responsabilidade de quem compõe o pipeline, nunca deste módulo."""

    tipo_evidencia: str
    fonte: str
    referencia_fonte: str
    tipo_sugerido: str

    def __post_init__(self) -> None:
        for campo in ('tipo_evidencia', 'fonte', 'referencia_fonte', 'tipo_sugerido'):
            if not getattr(self, campo).strip():
                raise ValueError(f'{campo} deve ser texto nao vazio')


def hipoteses_contextuais(sinais: Tuple[SinalContextual, ...]) -> Tuple[HipoteseTipoDocumental, ...]:
    """Traduz sinais contextuais já identificados em hipóteses SEMPRE
    FRACAS -- estruturalmente, nunca podem decidir um documento sozinhas
    (Fase 6/Fase I da missão: "sinais fracos não derrotam fortes").
    Cada sinal produz 1 hipótese independente; o resolvedor geral decide
    se contribui para reforçar um candidato já sustentado por outro
    produtor."""
    return tuple(
        HipoteseTipoDocumental(
            tipo_documental=sinal.tipo_sugerido,
            evidencias=(
                EvidenciaSanitizada(
                    tipo_evidencia=sinal.tipo_evidencia,
                    fonte=sinal.fonte,
                    referencia_fonte=sinal.referencia_fonte,
                    metodo='sinal_contextual',
                    forca=NivelConfianca.FRACA,
                ),
            ),
        )
        for sinal in sinais
    )
