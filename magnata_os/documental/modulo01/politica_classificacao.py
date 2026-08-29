"""Política pura de transição REGISTRO -> CLASSIFICACAO na esteira
documental (Modulo 01, Fase 3 — gate de classificação shadow).

Traduz uma `DecisaoRoteamentoDocumental` (magnata_os/classificacao/
roteamento_documental.py) numa decisão de transição de etapa. Pura, sem
I/O, sem depender do DTO de apresentação/consulta (`RoteamentoShadowDTO`,
dtos_esteira.py) — só do contrato semântico de classificação em si.
`dominio_esteira.py` continua sem nenhuma dependência de
`magnata_os.classificacao` — só este módulo (uma camada de política,
não de domínio puro) faz essa ponte.

SEMÂNTICA DE CLASSIFICACAO NESTA FASE — a única que este módulo aplica:
"a tentativa de classificação foi realizada e seu resultado operacional
foi registrado na esteira". NUNCA significa: processador disponível,
funcionário identificado, cliente identificado, competência resolvida
ou documento pronto para envio — todas essas são decisões de etapas
futuras (SEPARACAO/IDENTIFICACAO/VALIDACAO em diante), fora de escopo
aqui.

TABELA DE DECISÃO (auditoria read-only prévia, corrigida por revisão
arquitetural — ver PR desta fase):
  RESOLVIDA (tipo conhecido) -> avança, situação CONCLUIDO, sem
    bloqueio — mesmo quando a ação recomendada pelo roteamento ainda é
    REVISAR_HUMANO por falta de processador avulso (motivo
    PROCESSADOR_AINDA_NAO_DISPONIVEL): isso é limitação da PRÓXIMA
    fase (processamento), não defeito da classificação em si — por
    isso NUNCA rebaixa CLASSIFICACAO para EM_REVISAO.
  AMBIGUA -> avança, depois BLOQUEADO (só humano decide qual tipo).
  NAO_RECONHECIDA ("Outro") -> avança, situação EM_REVISAO — soft-flag,
    nunca hard-block nesta fase (mesmo espírito do legado: documento
    continua existindo/visível, só sinalizado para revisão).
  INVALIDA (PDF_INVALIDO) -> avança, depois BLOQUEADO,
    resolvivel_automaticamente=False — NÃO existe hoje nenhum
    mecanismo automático real de re-extração; marcar
    resolvivel_automaticamente=True seria inventar uma capacidade que
    não existe.
  Qualquer outro caso (shadow com erro técnico, shadow não executado)
  NÃO tem `DecisaoRoteamentoDocumental` para traduzir — o chamador
  (servico_lote.py) simplesmente não invoca esta política nesses
  casos; não há uma quinta branch aqui para isso.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from magnata_os.classificacao.roteamento_documental import (
    DecisaoRoteamentoDocumental,
    EstadoClassificacao,
)

from .dominio_esteira import MotivoBloqueio, SituacaoEsteira

# Códigos de MotivoBloqueio centralizados aqui — nunca espalhados como
# strings soltas por outros módulos. Convenção: prefixo "CLASSIFICACAO_"
# para todo bloqueio originado nesta etapa.
CODIGO_BLOQUEIO_AMBIGUA = 'CLASSIFICACAO_AMBIGUA'
CODIGO_BLOQUEIO_PDF_INVALIDO = 'CLASSIFICACAO_PDF_INVALIDO'

# Motivo de transição para o caso RESOLVIDA — próprio da CLASSIFICACAO,
# nunca o motivo do roteamento (`decisao.motivo`), que para RESOLVIDA é
# `PROCESSADOR_AINDA_NAO_DISPONIVEL`: isso descreve uma limitação da
# ETAPA POSTERIOR (processamento), não o resultado da classificação em
# si — que foi concluída com sucesso. Reutilizar o motivo do roteamento
# aqui misturaria as duas dimensões (achado de revisão arquitetural).
MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA = 'CLASSIFICACAO_RESOLVIDA'


@dataclasses.dataclass(frozen=True)
class DecisaoTransicaoClassificacao:
    """Resultado puro da política — diz o que `ServicoAvancoEsteira`
    deve fazer; nunca faz por si só (sem I/O, sem repositório, sem
    side effect). `situacao_classificacao` é a situação FINAL desejada
    após a operação completa (para os casos com `deve_bloquear=True`,
    isso é sempre `BLOQUEADO` — quem aplica decide o meio-termo
    transitório usado na chamada a `avancar_etapa`, nunca esta
    política)."""

    deve_avancar: bool
    situacao_classificacao: Optional[SituacaoEsteira]
    deve_bloquear: bool
    motivo_bloqueio: Optional[MotivoBloqueio]
    motivo_transicao: Optional[str]

    def __post_init__(self) -> None:
        if not self.deve_avancar:
            if (
                self.situacao_classificacao is not None
                or self.deve_bloquear
                or self.motivo_bloqueio is not None
            ):
                raise ValueError(
                    'deve_avancar=False não pode carregar situacao_classificacao, '
                    'deve_bloquear ou motivo_bloqueio')
            return
        if self.situacao_classificacao is None:
            raise ValueError('deve_avancar=True exige situacao_classificacao')
        if self.deve_bloquear and self.motivo_bloqueio is None:
            raise ValueError('deve_bloquear=True exige motivo_bloqueio')
        if not self.deve_bloquear and self.motivo_bloqueio is not None:
            raise ValueError('motivo_bloqueio só pode existir quando deve_bloquear=True')
        if self.deve_bloquear and self.situacao_classificacao != SituacaoEsteira.BLOQUEADO:
            raise ValueError('deve_bloquear=True exige situacao_classificacao=BLOQUEADO')


def decidir_transicao_classificacao(
    decisao: DecisaoRoteamentoDocumental,
) -> DecisaoTransicaoClassificacao:
    """Traduz a `DecisaoRoteamentoDocumental` (já produzida por uma
    única chamada a `decidir_roteamento` — esta função NUNCA reclassifica,
    NUNCA rechama `decidir_roteamento`) na decisão de transição de
    etapa. Pura, determinística, sem I/O.

    `motivo_transicao` sempre carrega o código sanitizado do próprio
    `decisao.motivo` (nunca texto livre, nunca inventado aqui) — vira
    o `motivo_transicao` registrado no evento `ESTEIRA_ETAPA_AVANCADA`
    já existente (servico_avanco_esteira.py), sem exigir nenhum campo
    novo nesse evento.
    """
    if decisao.estado_classificacao == EstadoClassificacao.RESOLVIDA:
        # motivo_transicao é MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA
        # (fixo), nunca `decisao.motivo.value` -- para RESOLVIDA, o
        # motivo do roteamento é PROCESSADOR_AINDA_NAO_DISPONIVEL, que
        # descreve a etapa POSTERIOR (processamento), não a
        # classificação em si (já concluída com sucesso). Ver docstring
        # do módulo.
        return DecisaoTransicaoClassificacao(
            deve_avancar=True,
            situacao_classificacao=SituacaoEsteira.CONCLUIDO,
            deve_bloquear=False,
            motivo_bloqueio=None,
            motivo_transicao=MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA,
        )

    if decisao.estado_classificacao == EstadoClassificacao.AMBIGUA:
        return DecisaoTransicaoClassificacao(
            deve_avancar=True,
            situacao_classificacao=SituacaoEsteira.BLOQUEADO,
            deve_bloquear=True,
            motivo_bloqueio=MotivoBloqueio(
                codigo=CODIGO_BLOQUEIO_AMBIGUA,
                descricao=(
                    'Classificação ambígua — colisão de tipos documentais '
                    'sem precedência histórica comprovada, requer decisão humana'
                ),
                detalhe_tecnico=None,
                resolvivel_automaticamente=False,
            ),
            motivo_transicao=decisao.motivo.value,
        )

    if decisao.estado_classificacao == EstadoClassificacao.NAO_RECONHECIDA:
        return DecisaoTransicaoClassificacao(
            deve_avancar=True,
            situacao_classificacao=SituacaoEsteira.EM_REVISAO,
            deve_bloquear=False,
            motivo_bloqueio=None,
            motivo_transicao=decisao.motivo.value,
        )

    if decisao.estado_classificacao == EstadoClassificacao.INVALIDA:
        return DecisaoTransicaoClassificacao(
            deve_avancar=True,
            situacao_classificacao=SituacaoEsteira.BLOQUEADO,
            deve_bloquear=True,
            motivo_bloqueio=MotivoBloqueio(
                codigo=CODIGO_BLOQUEIO_PDF_INVALIDO,
                descricao=(
                    'PDF inválido ou ilegível — extração de texto falhou, '
                    'requer revisão humana'
                ),
                detalhe_tecnico=None,
                # Nenhum mecanismo automático real de re-extração existe
                # hoje. Marcar True seria inventar uma capacidade que
                # não existe — nunca por hipótese futura.
                resolvivel_automaticamente=False,
            ),
            motivo_transicao=decisao.motivo.value,
        )

    # EstadoClassificacao é um enum fechado (RESOLVIDA/AMBIGUA/
    # NAO_RECONHECIDA/INVALIDA) — as 4 branches acima já cobrem todos
    # os valores possíveis. Esta linha é fail-safe explícito: nunca
    # decide por omissão se um valor novo for adicionado ao enum sem
    # atualizar esta política.
    raise ValueError(
        f'EstadoClassificacao sem política de transição definida: {decisao.estado_classificacao!r}')
