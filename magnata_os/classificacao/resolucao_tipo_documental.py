"""Motor GERAL de compreensão documental — resolução multi-evidência da
dimensão TIPO_DOCUMENTAL (missão "MOTOR GERAL DE COMPREENSÃO
DOCUMENTAL", Fase 2E).

PRINCÍPIO CENTRAL: regex textual não é mais a única autoridade sobre
"que documento é este" — passa a ser UM PRODUTOR DE EVIDÊNCIA entre
vários possíveis (textual, entidades, estrutural, contextual,
relacional). Este módulo é o RESOLVEDOR GERAL que combina evidências de
QUALQUER produtor e decide RESOLVIDA/AMBIGUA/NAO_ENCONTRADA/CONFLITO —
nunca contém `if tipo == X`, nunca conhece Holerite/Extrato/FGTS/DCTFWeb
por nome (prova estrutural AST em
`test_magnata_os_classificacao_resolucao_tipo_documental.py`).

MODELO (Fase B da missão — a menor abstração necessária, SEM recriar
`ResultadoResolucaoSemantico`):

    documento
      -> produtores de evidência (cada um já existente ou novo, cada um
         em seu próprio módulo — este arquivo não implementa nenhum
         produtor específico de tipo, só os dois produtores GENÉRICOS
         abaixo: contextual e a leitura de `ResultadoClassificacaoDocumental`
         já produzido por `classificador_documental.py`, PR anterior)
      -> HipoteseTipoDocumental (tipo candidato + evidências que o
         sustentam, cada evidência já no contrato canônico
         `EvidenciaSanitizada`)
      -> resolver_tipo_documental(hipoteses, ...) -> ResolucaoDimensao
         (dimensão TIPO_DOCUMENTAL, contrato canônico já existente)
      -> compor_resolucao_semantica (magnata_os/classificacao/
         resolucao_semantica.py, PR #93) -- sem nenhuma alteração.

REGRA DE COMBINAÇÃO DE FORÇA (única, documentada, nunca uma escala
paralela — usa só FORTE/MODERADA/FRACA/INDETERMINADA já existentes):
  - qualquer evidência FORTE -> força combinada FORTE;
  - 2 ou mais evidências MODERADA (nenhuma FORTE) -> FORTE (reforço
    mútuo de sinais moderados independentes vira confiança forte);
  - exatamente 1 evidência MODERADA -> MODERADA;
  - 2 ou mais evidências FRACA (nenhuma FORTE/MODERADA) -> MODERADA
    (reforço mútuo de sinais fracos);
  - exatamente 1 evidência FRACA -> FRACA;
  - nenhuma evidência -> INDETERMINADA.
Esta é UMA política explícita, não a única possível — documentada aqui
para poder ser revisada, nunca escondida dentro de um número mágico.

REGRA DE RESOLUÇÃO (Fase D + Fase I da missão):
  - nenhuma hipótese com evidência -> NAO_ENCONTRADA;
  - exatamente 1 hipótese com evidência, força FORTE ou MODERADA, e
    nenhum indício de múltiplas entidades distintas -> RESOLVIDA;
  - exatamente 1 hipótese, mas só força FRACA -> NAO_ENCONTRADA
    (evidência insuficiente — nunca força RESOLVIDA "a qualquer custo",
    Fase H);
  - exatamely 1 hipótese, força suficiente, MAS `quantidade_entidades_
    distintas >= 2` -> CONFLITO (generalização do "PDF mestre suspeito"
    já comprovado para Holerite avulso — aqui nunca especializado a um
    tipo, é um fail-safe genérico: documento com evidência de múltiplas
    entidades primárias nunca resolve sozinho para um único tipo,
    qualquer que ele seja);
  - 2+ hipóteses empatadas na força mais alta, sendo essa força FORTE
    -> CONFLITO (dois sinais fortes incompatíveis, Fase I: "dois fortes
    incompatíveis -> CONFLITO/revisão");
  - 2+ hipóteses empatadas em MODERADA ou FRACA -> AMBIGUA.

Este módulo NUNCA decide por si só se um documento está "ilegível"/
"inválido" (`EstadoResolucaoDimensao.INVALIDA`) ou se um produtor
falhou tecnicamente (`ERRO_TECNICO`) — essas duas situações são
decididas pelo PRODUTOR/orquestrador ANTES de sequer chamar este
resolvedor (mesmo padrão já usado por `roteamento_documental.
decidir_roteamento_de_texto`: `texto is None` nunca chega ao
classificador). Chamar este resolvedor pressupõe que o texto (quando
existe) já foi extraído com sucesso.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

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
class HipoteseTipoDocumental:
    """UM tipo candidato + as evidências (de QUALQUER produtor) que o
    sustentam. Várias `HipoteseTipoDocumental` do MESMO `tipo_documental`
    (vindas de produtores diferentes) são agrupadas por
    `resolver_tipo_documental` antes de calcular a força combinada --
    quem produz uma hipótese nunca precisa saber se outras já existem
    para o mesmo tipo."""

    tipo_documental: str
    evidencias: Tuple[EvidenciaSanitizada, ...]

    def __post_init__(self) -> None:
        if not self.tipo_documental.strip():
            raise ValueError('tipo_documental deve ser texto nao vazio')


def _forca_combinada(evidencias: Tuple[EvidenciaSanitizada, ...]) -> NivelConfianca:
    """Ver docstring do módulo, "REGRA DE COMBINAÇÃO DE FORÇA"."""
    forcas = [evidencia.forca for evidencia in evidencias]
    if NivelConfianca.FORTE in forcas:
        return NivelConfianca.FORTE
    quantidade_moderada = forcas.count(NivelConfianca.MODERADA)
    quantidade_fraca = forcas.count(NivelConfianca.FRACA)
    if quantidade_moderada >= 2:
        return NivelConfianca.FORTE
    if quantidade_moderada == 1:
        return NivelConfianca.MODERADA
    if quantidade_fraca >= 2:
        return NivelConfianca.MODERADA
    if quantidade_fraca == 1:
        return NivelConfianca.FRACA
    return NivelConfianca.INDETERMINADA


_ORDEM_FORCA = {
    NivelConfianca.FORTE: 3,
    NivelConfianca.MODERADA: 2,
    NivelConfianca.FRACA: 1,
    NivelConfianca.INDETERMINADA: 0,
}


def _agrupar_por_tipo(
    hipoteses: Tuple[HipoteseTipoDocumental, ...],
) -> dict:
    agrupado: dict = {}
    for hipotese in hipoteses:
        agrupado.setdefault(hipotese.tipo_documental, []).extend(hipotese.evidencias)
    return agrupado


def resolver_tipo_documental(
    hipoteses: Tuple[HipoteseTipoDocumental, ...],
    *,
    quantidade_entidades_distintas: Optional[int] = None,
) -> ResolucaoDimensao:
    """Resolve a dimensão TIPO_DOCUMENTAL a partir de hipóteses já
    coletadas de QUALQUER produtor de evidência. Determinístico, sem
    I/O. Nunca conhece nenhum tipo documental por nome -- só compara
    força de evidência entre candidatos.

    `quantidade_entidades_distintas`: sinal estrutural GENÉRICO opcional
    ("quantas entidades primárias distintas este documento parece
    conter" -- ex.: contagem de CPFs distintos, mas o resolvedor não
    sabe disso, só recebe o número). `>= 2` nunca deixa o resultado ser
    RESOLVIDA, mesmo com uma única hipótese fortemente sustentada --
    generaliza o fail-safe de "PDF mestre suspeito" já comprovado
    (antes só para Holerite avulso) para qualquer tipo documental."""
    agrupado = _agrupar_por_tipo(hipoteses)
    candidatos_com_evidencia = {
        tipo: evidencias for tipo, evidencias in agrupado.items() if evidencias
    }

    if not candidatos_com_evidencia:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.TIPO_DOCUMENTAL,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            metodo='resolvedor_geral_multi_evidencia_v1',
            motivos=('nenhuma_evidencia_de_tipo_documental',),
        )

    forca_por_tipo = {
        tipo: _forca_combinada(tuple(evidencias))
        for tipo, evidencias in candidatos_com_evidencia.items()
    }
    forca_maxima = max(forca_por_tipo.values(), key=lambda forca: _ORDEM_FORCA[forca])
    tipos_no_topo = tuple(sorted(
        tipo for tipo, forca in forca_por_tipo.items() if forca == forca_maxima
    ))

    if len(tipos_no_topo) == 1:
        tipo_vencedor = tipos_no_topo[0]
        evidencias_vencedoras = tuple(candidatos_com_evidencia[tipo_vencedor])

        if forca_maxima == NivelConfianca.FRACA:
            # Evidência insuficiente -- nunca força RESOLVIDA "a
            # qualquer custo" (Fase H da missão).
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.TIPO_DOCUMENTAL,
                estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
                candidatos=(ReferenciaCanonica('TIPO_DOCUMENTAL', tipo_vencedor),),
                evidencias=evidencias_vencedoras,
                metodo='resolvedor_geral_multi_evidencia_v1',
                motivos=('evidencia_insuficiente',),
            )

        if quantidade_entidades_distintas is not None and quantidade_entidades_distintas >= 2:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.TIPO_DOCUMENTAL,
                estado=EstadoResolucaoDimensao.CONFLITO,
                metodo='resolvedor_geral_multi_evidencia_v1',
                motivos=('multiplas_entidades_distintas_no_documento',),
            )

        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.TIPO_DOCUMENTAL,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', tipo_vencedor),),
            evidencias=evidencias_vencedoras,
            metodo='resolvedor_geral_multi_evidencia_v1',
            confianca=ConfiancaResolucao(forca_maxima),
        )

    # 2+ candidatos empatados na força mais alta.
    candidatos = tuple(ReferenciaCanonica('TIPO_DOCUMENTAL', tipo) for tipo in tipos_no_topo)
    if forca_maxima == NivelConfianca.FORTE:
        # Dois (ou mais) sinais FORTES incompatíveis -- nunca decidido
        # por ordem arbitrária (Fase I: "dois fortes incompatíveis ->
        # CONFLITO/revisão").
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.TIPO_DOCUMENTAL,
            estado=EstadoResolucaoDimensao.CONFLITO,
            candidatos=candidatos,
            metodo='resolvedor_geral_multi_evidencia_v1',
            motivos=('sinais_fortes_incompativeis',),
        )

    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.TIPO_DOCUMENTAL,
        estado=EstadoResolucaoDimensao.AMBIGUA,
        candidatos=candidatos,
        metodo='resolvedor_geral_multi_evidencia_v1',
        motivos=('candidatos_empatados_sem_evidencia_dominante',),
    )
