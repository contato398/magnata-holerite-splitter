"""Política pura de transição REGISTRO -> CLASSIFICACAO usando o motor
GERAL multi-evidência (missão "INTEGRAÇÃO REAL DO CONTEÚDO DOCUMENTAL AO
MOTOR SEMÂNTICO", Fases 2/3/5/6/7/8/13).

Auditoria (Fase 1) confirmou que `politica_classificacao.py` já é a
ponte real classificação->esteira, mas traduz só a
`DecisaoRoteamentoDocumental` do classificador de 17 regras
(`roteamento_documental.py`, `EstadoClassificacao`, 4 estados) — nunca
alimentada pelos produtores de evidência mais novos (fiscal, ponto,
temporal, rótulo alternativo, finalidade de pagamento) nem pelo
`ResolucaoDimensao`/8-estados do motor geral (`resolucao_tipo_
documental.resolver_tipo_documental`). Este módulo fecha esse gap SEM
duplicar `politica_classificacao.py` nem `ServicoAvancoEsteira`: produz
o MESMO contrato `DecisaoTransicaoClassificacao` já consumido por
`ServicoAvancoEsteira.aplicar_resultado_classificacao` (zero mudança
nessa mecânica), só que a partir do texto extraído + da ponte conteúdo
-> motor (`magnata_os.classificacao.ponte_conteudo_motor_semantico`) +
da reconciliação origem×conteúdo (`magnata_os.classificacao.
reconciliacao_origem_conteudo`) -- nunca um segundo motor, nunca uma
segunda esteira.

Fase 9 (competência esperada × observada): quando `competencia_esperada`
é informada, reaproveita `extrair_competencia_de_texto`/`validar_
competencia` (magnata_os/documental/importacao_lote/dominio.py, já
puras, já usadas por `orquestrador.py` -- nunca uma segunda extração) +
`resolucao_competencia_de_validacao` (resolucao_semantica.py, já
existente) -- NUNCA trata a competência observada no PDF como verdade
por si só; a esperada segue vindo de fora (`ContextoCicloPrestacao`,
responsabilidade de quem chama, nunca hardcoded aqui). DIVERGENTE/
AMBIGUA bloqueiam mesmo com TIPO_DOCUMENTAL já RESOLVIDA (nunca avança
silenciosamente sobre uma competência errada); NAO_EXTRAIVEL (nenhuma
competência declarada no documento) é uma decisão registrada, não
escondida: NÃO bloqueia sozinha -- muitos tipos resolvidos (ex.: Guia
genérica) não têm por que carregar uma linha de competência marcada, e
inventar um bloqueio aqui seria um hard-block sem evidência de erro.

TABELA DE DECISÃO (mesma filosofia de `politica_classificacao.py`,
adaptada ao vocabulário de 8 estados + reconciliação):
  texto is None (Fase 3 -- PDF sem texto extraível, ex.: escaneado sem
    OCR) -> avança, BLOQUEADO, motivo TÉCNICO distinto de "desconhecido"
    -- nunca confundido com NAO_ENCONTRADA (Fase 13: "documento
    desconhecido" é um CONTEÚDO ilegível/genérico, não uma FALHA de
    extração). Nenhum OCR é implementado aqui -- só registrada a
    necessidade técnica (Fase 3: "não implementar OCR agora").
  RESOLVIDA, sem reconciliação ou reconciliação REFORCO/SEM_RESOLUCAO ->
    avança, CONCLUIDO, sem bloqueio -- auto-avanço (Fase 7): a MESMA
    mecânica de `aplicar_resultado_classificacao` já avança sozinha daí
    em diante, sem retorno humano entre estágios desta etapa.
  RESOLVIDA, reconciliação CONFLITO -> avança, BLOQUEADO (Fase 5/6:
    "divergiram: CONFLITO, nunca avança silenciosamente" -- origem
    declarada nunca vence nem perde sozinha contra o conteúdo).
  CONFLITO (do próprio resolvedor -- sinais fortes incompatíveis) ->
    avança, BLOQUEADO.
  AMBIGUA -> avança, BLOQUEADO (só humano decide qual tipo).
  NAO_ENCONTRADA -> avança, EM_REVISAO -- soft-flag (Fase 13:
    DESCONHECIDO, nunca um "Outro" silencioso; humano só recebe estes
    casos, nunca os que já avançaram sozinhos).
  Qualquer outro estado de `ResolucaoDimensao.estado` (NAO_AVALIADA/
  NAO_APLICAVEL/INVALIDA/ERRO_TECNICO) é fail-safe explícito -- o
  próprio `resolver_tipo_documental` documenta que só produz RESOLVIDA/
  AMBIGUA/CONFLITO/NAO_ENCONTRADA (nunca decide ilegibilidade/erro
  técnico sozinho); ver módulo `resolucao_tipo_documental.py`."""
from __future__ import annotations

from typing import Optional, Tuple

from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ResolucaoDimensao
from magnata_os.classificacao.ponte_conteudo_motor_semantico import resolver_tipo_documental_de_texto
from magnata_os.classificacao.reconciliacao_origem_conteudo import (
    ReconciliacaoOrigemConteudo,
    ResultadoReconciliacaoOrigem,
    reconciliar_origem_com_tipo_resolvido,
    tipo_resolvido_da_dimensao,
)
from magnata_os.classificacao.resolucao_semantica import resolucao_competencia_de_validacao
from magnata_os.documental.importacao_lote.dominio import extrair_competencia_de_texto, validar_competencia

from .dominio_esteira import MotivoBloqueio, SituacaoEsteira
from .politica_classificacao import DecisaoTransicaoClassificacao

# Códigos de MotivoBloqueio desta política -- prefixo "CLASSIFICACAO_"
# (mesma convenção de politica_classificacao.py), nunca reaproveitando
# CODIGO_BLOQUEIO_PDF_INVALIDO (esse é "PDF corrompido"; aqui é
# especificamente "texto não extraível", que pode um dia ter um caminho
# de OCR -- distinção deliberada, Fase 3).
CODIGO_BLOQUEIO_TEXTO_NAO_EXTRAIVEL = 'CLASSIFICACAO_TEXTO_NAO_EXTRAIVEL'
CODIGO_BLOQUEIO_CONFLITO_TIPO = 'CLASSIFICACAO_CONFLITO_TIPO_DOCUMENTAL'
CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA = 'CLASSIFICACAO_AMBIGUA_SEMANTICA'
CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES = 'CLASSIFICACAO_ORIGEM_CONTEUDO_DIVERGENTES'
CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE = 'CLASSIFICACAO_COMPETENCIA_DIVERGENTE'
CODIGO_BLOQUEIO_COMPETENCIA_AMBIGUA = 'CLASSIFICACAO_COMPETENCIA_AMBIGUA'

MOTIVO_TRANSICAO_RESOLVIDA_SEMANTICA = 'CLASSIFICACAO_RESOLVIDA_SEMANTICA'
MOTIVO_TRANSICAO_DESCONHECIDO = 'CLASSIFICACAO_TIPO_DESCONHECIDO'


def _decisao_avanca_sem_bloqueio(situacao: SituacaoEsteira, motivo_transicao: str) -> DecisaoTransicaoClassificacao:
    return DecisaoTransicaoClassificacao(
        deve_avancar=True, situacao_classificacao=situacao,
        deve_bloquear=False, motivo_bloqueio=None, motivo_transicao=motivo_transicao,
    )


def _decisao_bloqueia(codigo: str, descricao: str, motivo_transicao: str) -> DecisaoTransicaoClassificacao:
    return DecisaoTransicaoClassificacao(
        deve_avancar=True, situacao_classificacao=SituacaoEsteira.BLOQUEADO,
        deve_bloquear=True,
        motivo_bloqueio=MotivoBloqueio(
            codigo=codigo, descricao=descricao, detalhe_tecnico=None,
            resolvivel_automaticamente=False,
        ),
        motivo_transicao=motivo_transicao,
    )


def decidir_transicao_classificacao_semantica(
    texto: Optional[str],
    tipo_origem: Optional[str] = None,
    competencia_esperada: Optional[Tuple[int, int]] = None,
) -> DecisaoTransicaoClassificacao:
    """Ponto único que combina texto já extraído (Fase 2/3) + motor
    multi-evidência (Fase 4) + reconciliação origem×conteúdo (Fase 5/6)
    numa decisão de transição de etapa, no MESMO contrato já consumido
    por `ServicoAvancoEsteira.aplicar_resultado_classificacao` -- zero
    mudança na mecânica de avanço/bloqueio já existente.

    `texto`: já extraído por fora (ex.: `roteamento_documental.
    extrair_texto_seguro`) -- esta função NUNCA extrai PDF, só decide a
    partir do texto (ou da ausência dele) e opcionalmente de um
    `tipo_origem` externo (nome de tabela, campo de tipo, remetente).

    `tipo_origem`: quando informado, é reconciliado contra o tipo
    RESOLVIDO (nunca contra um `NAO_ENCONTRADA`/AMBIGUA/etc. -- Fase 6:
    tabela de origem nunca prova tipo sozinha, e conteúdo inconclusivo
    nunca vira RESOLVIDO só pela origem).

    `competencia_esperada`: (ano, mes) já resolvido por fora (Fase 9 --
    `ContextoCicloPrestacao`/política de competência esperada da
    prestação, nunca inventado aqui). Só é comparado contra a
    competência OBSERVADA no texto quando TIPO_DOCUMENTAL já é
    RESOLVIDA -- documento sem tipo resolvido não tem competência
    esperada avaliada ainda (a etapa de competência é posterior à de
    tipo, mesma ordem do resolvedor geral)."""
    if texto is None:
        return _decisao_bloqueia(
            CODIGO_BLOQUEIO_TEXTO_NAO_EXTRAIVEL,
            'Texto não extraível do documento (PDF corrompido ou sem camada de texto -- '
            'possível necessidade futura de OCR, não implementada nesta fase)',
            'TEXTO_NAO_EXTRAIVEL',
        )

    resolucao: ResolucaoDimensao = resolver_tipo_documental_de_texto(texto)

    if resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA:
        reconciliacao = _reconciliar_se_aplicavel(tipo_origem, resolucao)
        if reconciliacao is not None and reconciliacao.resultado == ResultadoReconciliacaoOrigem.CONFLITO:
            return _decisao_bloqueia(
                CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES,
                (
                    f'Origem declarada ({reconciliacao.tipo_origem!r}) diverge do tipo '
                    f'resolvido pelo conteúdo ({reconciliacao.tipo_resolvido!r}) -- '
                    'origem nunca vence nem perde sozinha, requer revisão humana'
                ),
                CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES,
            )
        decisao_competencia = _verificar_competencia_se_aplicavel(texto, competencia_esperada)
        if decisao_competencia is not None:
            return decisao_competencia

        # Sem origem para reconciliar (ou REFORCO), e competência
        # esperada×observada coincide (ou não foi avaliada) -- auto-
        # avanço (Fase 7): a MESMA mecânica de `avancar_etapa` já aplica
        # isso, sem retorno humano entre estágios.
        return _decisao_avanca_sem_bloqueio(SituacaoEsteira.CONCLUIDO, MOTIVO_TRANSICAO_RESOLVIDA_SEMANTICA)

    if resolucao.estado == EstadoResolucaoDimensao.CONFLITO:
        return _decisao_bloqueia(
            CODIGO_BLOQUEIO_CONFLITO_TIPO,
            'Conflito no motor semântico -- sinais fortes incompatíveis para o tipo documental',
            CODIGO_BLOQUEIO_CONFLITO_TIPO,
        )

    if resolucao.estado == EstadoResolucaoDimensao.AMBIGUA:
        return _decisao_bloqueia(
            CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA,
            'Classificação semântica ambígua -- candidatos empatados sem evidência dominante',
            CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA,
        )

    if resolucao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA:
        # Fase 13: DESCONHECIDO -- soft-flag, nunca hard-block; humano
        # só recebe este caso, nunca os que já avançaram sozinhos.
        return _decisao_avanca_sem_bloqueio(SituacaoEsteira.EM_REVISAO, MOTIVO_TRANSICAO_DESCONHECIDO)

    # `resolver_tipo_documental` documenta que só produz os 4 estados
    # acima -- fail-safe explícito, nunca decide por omissão.
    raise ValueError(
        f'EstadoResolucaoDimensao sem política de transição semântica definida: {resolucao.estado!r}')


def _reconciliar_se_aplicavel(
    tipo_origem: Optional[str], resolucao: ResolucaoDimensao,
) -> Optional[ReconciliacaoOrigemConteudo]:
    if tipo_origem is None:
        return None
    tipo_resolvido = tipo_resolvido_da_dimensao(resolucao)
    return reconciliar_origem_com_tipo_resolvido(tipo_origem, tipo_resolvido)


def _verificar_competencia_se_aplicavel(
    texto: str, competencia_esperada: Optional[Tuple[int, int]],
) -> Optional[DecisaoTransicaoClassificacao]:
    """Fase 9: só roda quando uma competência esperada foi informada por
    fora. Retorna uma decisão de BLOQUEIO quando esperada×observada
    divergem/são ambíguas -- nunca avança silenciosamente sobre uma
    competência errada; retorna `None` (nada a bloquear) quando
    CONFIRMADA ou quando o documento simplesmente não declara nenhuma
    competência (NAO_EXTRAIVEL -- decisão registrada no docstring do
    módulo, não um bloqueio por si só)."""
    if competencia_esperada is None:
        return None
    ano_esperado, mes_esperado = competencia_esperada
    extraida = extrair_competencia_de_texto(texto)
    resultado_competencia = validar_competencia(extraida, ano_esperado, mes_esperado)
    resolucao_competencia = resolucao_competencia_de_validacao(resultado_competencia, competencia_esperada)

    if resolucao_competencia.estado == EstadoResolucaoDimensao.CONFLITO:
        return _decisao_bloqueia(
            CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE,
            (
                f'Competência observada no documento diverge da esperada '
                f'({ano_esperado:04d}-{mes_esperado:02d}) -- nunca avança silenciosamente'
            ),
            CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE,
        )
    if resolucao_competencia.estado == EstadoResolucaoDimensao.AMBIGUA:
        return _decisao_bloqueia(
            CODIGO_BLOQUEIO_COMPETENCIA_AMBIGUA,
            'Mais de uma competência candidata encontrada no documento -- requer revisão humana',
            CODIGO_BLOQUEIO_COMPETENCIA_AMBIGUA,
        )
    # RESOLVIDA (confirmada) ou NAO_ENCONTRADA (não declarada) -- nenhum
    # bloqueio; ver docstring do módulo para a justificativa de não
    # bloquear NAO_ENCONTRADA sozinha.
    return None
