"""Política pura de transição CLASSIFICACAO -> IDENTIFICACAO para
Holerite avulso na esteira documental (Modulo 01 — gate de identificação
de colaborador).

Escopo desta microetapa: SÓ Holerite, SÓ Documento avulso (1 PDF = 1
Documento, nunca um pacote/manifesto — ver auditoria read-only prévia).
Nunca reutiliza `processar_holerite`/`ItemManifestoHolerite`/
`ConfiguracaoExecucao` (contratos da Família B, ZIP/manifesto) — só as
funções puras de domínio já existentes (`resolver_funcionario`,
`magnata_os/documental/importacao_lote/dominio.py`) e o contrato neutro
de resolução de dimensão já existente (`ResolucaoDimensao`,
`magnata_os/classificacao/contratos.py`, já usado pelo readiness shadow
de Prestação de Contas para CLIENTE/COMPETENCIA — reaproveitado aqui
para COLABORADOR, nenhum DTO paralelo criado).

NUNCA nesta etapa: extrai/valida competência, usa `mes_cont_id`, checa
duplicidade de Holerite já existente na folha, fabrica manifesto — todas
essas são decisões de uma etapa FUTURA (VALIDACAO/gravação), fora de
escopo aqui (ver auditoria read-only prévia, "fronteiras" entre
IDENTIFICAR FUNCIONÁRIO / VALIDAR COMPETÊNCIA / CALCULAR IDENTIDADE
DOCUMENTAL PARA GRAVAÇÃO).

SEMÂNTICA DE IDENTIFICACAO NESTA FASE — a única que este módulo aplica:
"a tentativa de identificar o colaborador dono do Holerite avulso foi
realizada e seu resultado operacional foi registrado na esteira". NUNCA
significa: competência validada, documento pronto para gravação/envio —
decisões de etapas futuras.

TABELA DE DECISÃO:
  RESOLVIDA (CPF ou nome bateram com exatamente 1 candidato) -> avança,
    situação CONCLUIDO, sem bloqueio.
  AMBIGUA (mais de um candidato correspondeu) -> avança, depois
    BLOQUEADO (só humano decide qual colaborador).
  NAO_ENCONTRADA (nenhum candidato correspondeu) -> avança, situação
    EM_REVISAO — soft-flag, nunca hard-block nesta fase (mesmo espírito
    já usado para NAO_RECONHECIDA em `politica_classificacao.py`).
  MESTRE_SUSPEITO (2+ CPFs distintos no texto) -> avança, depois
    BLOQUEADO. Condição documental DIFERENTE de AMBIGUA (não é colisão
    de candidatos — é sinal de que o PDF pode não ser um Documento
    avulso de verdade); nunca reaproveita o código de bloqueio de
    AMBIGUA nem faz qualquer fatiamento nesta etapa.
  CONFLITO/INVALIDA/ERRO_TECNICO/NAO_AVALIADA/NAO_APLICAVEL -> nunca
    deveriam ocorrer vindos de `resolver_funcionario` (só produz
    EXACT/AMBIGUOUS/NOT_FOUND) — fail-safe explícito abaixo, nunca
    avanço silencioso.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Sequence, Union

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)

from ..importacao_lote.contratos import CandidatoFuncionario, ClassificacaoCorrespondencia, ResultadoCorrespondencia
from ..importacao_lote.dominio import (
    extrair_cpfs_distintos_de_texto,
    extrair_nome_funcionario_de_texto,
    resolver_funcionario,
)
from .dominio_esteira import MotivoBloqueio, SituacaoEsteira

# Códigos de MotivoBloqueio centralizados aqui — nunca espalhados como
# strings soltas por outros módulos. Convenção: prefixo "IDENTIFICACAO_"
# para todo bloqueio originado nesta etapa (mesmo padrão de
# `politica_classificacao.py`, prefixo "CLASSIFICACAO_").
CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO = 'IDENTIFICACAO_COLABORADOR_AMBIGUO'
CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO = 'IDENTIFICACAO_PDF_MESTRE_SUSPEITO'

# Motivos de transição — códigos sanitizados fixos e próprios da
# IDENTIFICACAO, nunca texto livre. Para RESOLVIDA, propositalmente NÃO
# reutiliza `MotivoSanitizado.OK` (genérico demais para o evento de
# transição de etapa) — mesma decisão arquitetural já tomada para
# `MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA`.
MOTIVO_TRANSICAO_IDENTIFICACAO_RESOLVIDA = 'IDENTIFICACAO_RESOLVIDA'
MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_AMBIGUO = CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO
MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_NAO_ENCONTRADO = 'IDENTIFICACAO_COLABORADOR_NAO_ENCONTRADO'
MOTIVO_TRANSICAO_IDENTIFICACAO_PDF_MESTRE_SUSPEITO = CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO


@dataclasses.dataclass(frozen=True)
class MestreSuspeitoIdentificacaoHolerite:
    """Sinal específico e sanitizado de "PDF mestre suspeito" — 2+ CPFs
    distintos encontrados no texto de um Holerite avulso. Condição
    documental DIFERENTE de AMBIGUA (que é sobre colisão de CANDIDATOS
    de colaborador, não sobre o conteúdo do PDF ter mais de uma
    identidade) — nunca reaproveita `EstadoResolucaoDimensao.AMBIGUA`
    nem qualquer código de bloqueio de colaborador ambíguo.

    Só carrega a CONTAGEM de CPFs distintos (nunca os CPFs em si, que
    são estritamente transitórios) — a contagem não é PII, só um
    inteiro auxiliar de observabilidade/depuração."""

    quantidade_cpfs_distintos: int

    def __post_init__(self) -> None:
        if self.quantidade_cpfs_distintos < 2:
            raise ValueError(
                'MestreSuspeitoIdentificacaoHolerite exige quantidade_cpfs_distintos >= 2')


ResultadoIdentificacaoHolerite = Union[ResolucaoDimensao, MestreSuspeitoIdentificacaoHolerite]


def correspondencia_para_resolucao_dimensao(
    correspondencia: ResultadoCorrespondencia,
) -> ResolucaoDimensao:
    """Traduz um `ResultadoCorrespondencia` (importacao_lote/contratos.py
    — já produzido por `resolver_funcionario`, nunca refeito aqui) para
    o contrato neutro `ResolucaoDimensao` (classificacao/contratos.py),
    dimensão COLABORADOR. Auditoria read-only prévia confirmou que este
    contrato já existe e já é usado pelo readiness shadow de Prestação
    de Contas para CLIENTE/COMPETENCIA — reaproveitado aqui, nenhum DTO
    paralelo criado.

    Nunca carrega CPF ou nome — só `entidade_id` (record id do
    Airtable, já resolvido, não é PII) em `valores_confirmados` e o
    código sanitizado de `MotivoSanitizado` em `motivos`."""
    motivos = (correspondencia.motivo.value,)
    metodo = correspondencia.criterio_usado

    if correspondencia.classificacao == ClassificacaoCorrespondencia.EXACT:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('COLABORADOR', correspondencia.entidade_id),),
            metodo=metodo,
            motivos=motivos,
        )
    if correspondencia.classificacao == ClassificacaoCorrespondencia.AMBIGUOUS:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.AMBIGUA,
            metodo=metodo,
            motivos=motivos,
        )
    if correspondencia.classificacao == ClassificacaoCorrespondencia.NOT_FOUND:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            metodo=metodo,
            motivos=motivos,
        )
    if correspondencia.classificacao == ClassificacaoCorrespondencia.CONFLICT:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.CONFLITO,
            metodo=metodo,
            motivos=motivos,
        )
    if correspondencia.classificacao == ClassificacaoCorrespondencia.INVALID:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.INVALIDA,
            metodo=metodo,
            motivos=motivos,
        )

    # ClassificacaoCorrespondencia é um enum fechado; `resolver_funcionario`
    # só produz EXACT/AMBIGUOUS/NOT_FOUND, mas as 5 branches acima já
    # cobrem todos os valores restantes exceto DUPLICATE (que pertence à
    # camada de escrita, nunca a esta correspondência) -- fail-safe
    # explícito, nunca traduz por omissão.
    raise ValueError(
        f'ClassificacaoCorrespondencia sem tradução para ResolucaoDimensao: '
        f'{correspondencia.classificacao!r}')


def resolver_identificacao_holerite_de_texto(
    texto: str,
    candidatos: Sequence[CandidatoFuncionario],
) -> ResultadoIdentificacaoHolerite:
    """Orquestra (pura, sem I/O) a identificação de colaborador a partir
    do MESMO texto já extraído uma única vez pelo chamador (ver
    `magnata_os/classificacao/roteamento_documental.py::
    extrair_texto_seguro` e `servico_lote.py`). Nunca extrai o PDF de
    novo, nunca recebe bytes.

    Ordem: 1) detecta CPFs distintos (`extrair_cpfs_distintos_de_texto`)
    — 2+ vira `MestreSuspeitoIdentificacaoHolerite` sem chamar
    `resolver_funcionario` (nunca escolhe o primeiro CPF); 2) senão,
    extrai nome (`extrair_nome_funcionario_de_texto`, fallback) e chama
    `resolver_funcionario` com o único CPF encontrado (ou None) + nome
    (ou string vazia) + candidatos."""
    cpfs_distintos = extrair_cpfs_distintos_de_texto(texto)
    if len(cpfs_distintos) >= 2:
        return MestreSuspeitoIdentificacaoHolerite(quantidade_cpfs_distintos=len(cpfs_distintos))

    cpf_extraido = cpfs_distintos[0] if cpfs_distintos else None
    nome_extraido = extrair_nome_funcionario_de_texto(texto) or ''
    correspondencia = resolver_funcionario(cpf_extraido, nome_extraido, list(candidatos))
    return correspondencia_para_resolucao_dimensao(correspondencia)


@dataclasses.dataclass(frozen=True)
class DecisaoTransicaoIdentificacao:
    """Resultado puro da política — diz o que `ServicoAvancoEsteira`
    deve fazer; nunca faz por si só (sem I/O, sem repositório, sem side
    effect). Mesma forma de `DecisaoTransicaoClassificacao`
    (politica_classificacao.py) — `situacao_identificacao` é a situação
    FINAL desejada após a operação completa (para `deve_bloquear=True`,
    sempre `BLOQUEADO`; quem aplica decide o meio-termo transitório,
    nunca esta política)."""

    deve_avancar: bool
    situacao_identificacao: Optional[SituacaoEsteira]
    deve_bloquear: bool
    motivo_bloqueio: Optional[MotivoBloqueio]
    motivo_transicao: Optional[str]

    def __post_init__(self) -> None:
        if not self.deve_avancar:
            if (
                self.situacao_identificacao is not None
                or self.deve_bloquear
                or self.motivo_bloqueio is not None
            ):
                raise ValueError(
                    'deve_avancar=False não pode carregar situacao_identificacao, '
                    'deve_bloquear ou motivo_bloqueio')
            return
        if self.situacao_identificacao is None:
            raise ValueError('deve_avancar=True exige situacao_identificacao')
        if self.deve_bloquear and self.motivo_bloqueio is None:
            raise ValueError('deve_bloquear=True exige motivo_bloqueio')
        if not self.deve_bloquear and self.motivo_bloqueio is not None:
            raise ValueError('motivo_bloqueio só pode existir quando deve_bloquear=True')
        if self.deve_bloquear and self.situacao_identificacao != SituacaoEsteira.BLOQUEADO:
            raise ValueError('deve_bloquear=True exige situacao_identificacao=BLOQUEADO')


def decidir_transicao_identificacao(
    resultado: ResultadoIdentificacaoHolerite,
) -> DecisaoTransicaoIdentificacao:
    """Traduz o resultado de `resolver_identificacao_holerite_de_texto`
    na decisão de transição de etapa CLASSIFICACAO -> IDENTIFICACAO.
    Pura, determinística, sem I/O."""
    if isinstance(resultado, MestreSuspeitoIdentificacaoHolerite):
        return DecisaoTransicaoIdentificacao(
            deve_avancar=True,
            situacao_identificacao=SituacaoEsteira.BLOQUEADO,
            deve_bloquear=True,
            motivo_bloqueio=MotivoBloqueio(
                codigo=CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO,
                descricao=(
                    'PDF com múltiplos CPFs distintos — possível documento '
                    'mestre não fatiado, requer revisão humana'
                ),
                detalhe_tecnico=None,
                # Nenhum fatiamento automático existe hoje na esteira para
                # Documento avulso — marcar True seria inventar uma
                # capacidade que não existe.
                resolvivel_automaticamente=False,
            ),
            motivo_transicao=MOTIVO_TRANSICAO_IDENTIFICACAO_PDF_MESTRE_SUSPEITO,
        )

    if resultado.dimensao != DimensaoResolucao.COLABORADOR:
        raise ValueError(
            'decidir_transicao_identificacao exige ResolucaoDimensao de COLABORADOR, '
            f'recebeu dimensao={resultado.dimensao!r}')

    if resultado.estado == EstadoResolucaoDimensao.RESOLVIDA:
        return DecisaoTransicaoIdentificacao(
            deve_avancar=True,
            situacao_identificacao=SituacaoEsteira.CONCLUIDO,
            deve_bloquear=False,
            motivo_bloqueio=None,
            motivo_transicao=MOTIVO_TRANSICAO_IDENTIFICACAO_RESOLVIDA,
        )

    if resultado.estado == EstadoResolucaoDimensao.AMBIGUA:
        return DecisaoTransicaoIdentificacao(
            deve_avancar=True,
            situacao_identificacao=SituacaoEsteira.BLOQUEADO,
            deve_bloquear=True,
            motivo_bloqueio=MotivoBloqueio(
                codigo=CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO,
                descricao=(
                    'Colaborador ambíguo — mais de um candidato correspondeu, '
                    'requer decisão humana'
                ),
                detalhe_tecnico=None,
                resolvivel_automaticamente=False,
            ),
            motivo_transicao=MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_AMBIGUO,
        )

    if resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA:
        return DecisaoTransicaoIdentificacao(
            deve_avancar=True,
            situacao_identificacao=SituacaoEsteira.EM_REVISAO,
            deve_bloquear=False,
            motivo_bloqueio=None,
            motivo_transicao=MOTIVO_TRANSICAO_IDENTIFICACAO_COLABORADOR_NAO_ENCONTRADO,
        )

    # CONFLITO/INVALIDA/ERRO_TECNICO/NAO_AVALIADA/NAO_APLICAVEL: nunca
    # deveriam ocorrer vindos de `resolver_funcionario` (só produz
    # EXACT/AMBIGUOUS/NOT_FOUND, traduzidos acima só para
    # RESOLVIDA/AMBIGUA/NAO_ENCONTRADA). Fail-safe explícito, mesmo
    # padrão de `politica_classificacao.decidir_transicao_classificacao`
    # — nunca decide por omissão se um caso novo aparecer.
    raise ValueError(
        f'EstadoResolucaoDimensao sem política de transição de identificação '
        f'definida: {resultado.estado!r}')
