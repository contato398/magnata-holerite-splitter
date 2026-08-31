"""Identificação GENÉRICA de colaborador a partir de texto (missão
"CORREDOR AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fase 8: "generalizar o avanço
de IDENTIFICACAO... extrair/reutilizar o padrão genérico quando
possível... não destruir a política específica de Holerite").

Auditoria (Fase 3): `politica_identificacao_holerite.py` já resolve
IDENTIFICACAO para Holerite avulso, mas todo o NÚCLEO da lógica
(`extrair_cpfs_distintos_de_texto` + `extrair_nome_funcionario_de_texto`
+ `resolver_funcionario` + tradução do resultado para `ResolucaoDimensao`
COLABORADOR) já é inteiramente genérico — nada ali conhece "Holerite"
por nome, exceto os nomes das próprias funções/dataclasses. Este módulo
EXTRAI esse núcleo (mesmo padrão já usado nesta e na missão anterior
para `decidir_por_estado_dimensao`/`reconciliar_origem_com_tipo_
resolvido`) para que QUALQUER família com granularidade colaborador
(Folha de Ponto, Comprovante de Pagamento por finalidade, etc.) reuse a
MESMA lógica — nunca uma segunda implementação.

`politica_identificacao_holerite.py` CONTINUA existindo, com o MESMO
nome público, mesmo comportamento, mesmos testes — apenas delegando a
este módulo internamente (ver alias no final do arquivo lá)."""
from __future__ import annotations

import dataclasses
from typing import Optional, Sequence, Union

from magnata_os.documental.importacao_lote.contratos import ClassificacaoCorrespondencia, ResultadoCorrespondencia
from magnata_os.documental.importacao_lote.dominio import (
    extrair_cpfs_distintos_de_texto,
    extrair_nome_funcionario_de_texto,
    resolver_funcionario,
)

from .contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EvidenciaSanitizada,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)


@dataclasses.dataclass(frozen=True)
class DocumentoComMultiplasIdentidades:
    """Sinal genérico de "documento com 2+ CPFs distintos no texto" —
    condição documental DIFERENTE de AMBIGUA (que é sobre colisão de
    CANDIDATOS de cadastro, não sobre o conteúdo do documento ter mais
    de uma identidade). Só carrega a CONTAGEM (nunca os CPFs em si —
    nunca PII)."""

    quantidade_cpfs_distintos: int

    def __post_init__(self) -> None:
        if self.quantidade_cpfs_distintos < 2:
            raise ValueError(
                'DocumentoComMultiplasIdentidades exige quantidade_cpfs_distintos >= 2')


ResultadoIdentificacaoColaborador = Union[ResolucaoDimensao, DocumentoComMultiplasIdentidades]


def multiplas_identidades_para_resolucao_dimensao(
    resultado: DocumentoComMultiplasIdentidades,
) -> ResolucaoDimensao:
    """Traduz `DocumentoComMultiplasIdentidades` para `ResolucaoDimensao`
    (COLABORADOR, CONFLITO) — necessário só para quem compõe uma
    resolução semântica consolidada. CONFLITO, nunca AMBIGUA: é uma
    condição documental (2+ identidades no mesmo texto), não uma
    colisão de candidatos de cadastro."""
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.COLABORADOR,
        estado=EstadoResolucaoDimensao.CONFLITO,
        metodo='deteccao_documento_com_multiplas_identidades',
        motivos=('multiplas_identidades_distintas_no_documento',),
    )


# Força de evidência por critério de correspondência -- CPF exato
# sempre mais forte que nome (mesmo princípio já em `resolver_
# funcionario`: CPF tentado antes de nome, nunca o inverso).
_FORCA_POR_CRITERIO = {
    'cpf_exato': NivelConfianca.FORTE,
    'nome_normalizado_exato': NivelConfianca.MODERADA,
}


def _evidencia_de_criterio(
    criterio_usado: Optional[str], entidade_candidata: Optional[ReferenciaCanonica],
) -> tuple:
    if criterio_usado is None:
        return ()
    forca = _FORCA_POR_CRITERIO.get(criterio_usado)
    if forca is None:
        raise ValueError(f'criterio_usado sem força de evidência definida: {criterio_usado!r}')
    return (
        EvidenciaSanitizada(
            tipo_evidencia='CORRESPONDENCIA_FUNCIONARIO',
            fonte='resolver_funcionario',
            referencia_fonte=criterio_usado,
            metodo=criterio_usado,
            forca=forca,
            entidade_candidata=entidade_candidata,
        ),
    )


def correspondencia_para_resolucao_dimensao(
    correspondencia: ResultadoCorrespondencia,
) -> ResolucaoDimensao:
    """Traduz um `ResultadoCorrespondencia` (já produzido por
    `resolver_funcionario`, nunca refeito aqui) para `ResolucaoDimensao`
    da dimensão COLABORADOR. Nunca carrega CPF/nome — só `entidade_id`
    já resolvido, o código sanitizado do motivo, e o critério de
    correspondência como `EvidenciaSanitizada`."""
    motivos = (correspondencia.motivo.value,)
    metodo = correspondencia.criterio_usado

    if correspondencia.classificacao == ClassificacaoCorrespondencia.EXACT:
        entidade = ReferenciaCanonica('COLABORADOR', correspondencia.entidade_id)
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(entidade,),
            evidencias=_evidencia_de_criterio(metodo, entidade),
            metodo=metodo,
            confianca=ConfiancaResolucao(_FORCA_POR_CRITERIO.get(metodo, NivelConfianca.INDETERMINADA)),
            motivos=motivos,
        )
    if correspondencia.classificacao == ClassificacaoCorrespondencia.AMBIGUOUS:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COLABORADOR,
            estado=EstadoResolucaoDimensao.AMBIGUA,
            evidencias=_evidencia_de_criterio(metodo, None),
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
    # cobrem todos os valores restantes exceto DUPLICATE (camada de
    # escrita, nunca esta correspondência) -- fail-safe explícito.
    raise ValueError(
        f'ClassificacaoCorrespondencia sem tradução para ResolucaoDimensao: '
        f'{correspondencia.classificacao!r}')


def resolver_colaborador_de_texto(
    texto: str,
    candidatos: Sequence,
) -> ResultadoIdentificacaoColaborador:
    """Orquestra (pura, sem I/O) a identificação de colaborador a partir
    do MESMO texto já extraído uma única vez pelo chamador. Genérico a
    QUALQUER família documental com granularidade colaborador — nunca
    assume Holerite nem qualquer outro tipo.

    Ordem: 1) detecta CPFs distintos — 2+ vira
    `DocumentoComMultiplasIdentidades` sem chamar `resolver_funcionario`
    (nunca escolhe o primeiro CPF); 2) senão, extrai nome (fallback) e
    chama `resolver_funcionario` com o único CPF encontrado (ou None) +
    nome (ou string vazia) + candidatos."""
    cpfs_distintos = extrair_cpfs_distintos_de_texto(texto)
    if len(cpfs_distintos) >= 2:
        return DocumentoComMultiplasIdentidades(quantidade_cpfs_distintos=len(cpfs_distintos))

    cpf_extraido = cpfs_distintos[0] if cpfs_distintos else None
    nome_extraido = extrair_nome_funcionario_de_texto(texto) or ''
    correspondencia = resolver_funcionario(cpf_extraido, nome_extraido, list(candidatos))
    return correspondencia_para_resolucao_dimensao(correspondencia)
