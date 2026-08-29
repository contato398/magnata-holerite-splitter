"""Ponte pura Módulo 01 (Documental) -> Prestação de Contas, Holerite avulso.

Traduz um `HoleriteConfirmadoDTO` (dtos_esteira.py -- fato OBSERVADO já
sanitizado, produzido por `ServicoCriacaoLote._processar_um_arquivo`
quando a identificação de colaborador terminou RESOLVIDA) num
`ItemInventarioPrestacao` (classificacao/prestacao_readiness.py -- o
contrato neutro já consumido por `avaliar_prestacao_shadow`/
`avaliar_prestacao_readiness`).

ORDEM (revisada pela missão "DEFINIR E IMPLEMENTAR A FONTE AUTOMÁTICA DE
COMPETÊNCIA ESPERADA" -- auditoria confirmou que a competência esperada
pode depender do CLIENTE, então o cliente precisa estar resolvido ANTES
de se poder perguntar "qual é a competência esperada para ele"):

  1. a competência OBSERVADA no documento (extraída do próprio PDF)
     precisa existir e ser um valor único (`StatusExtracaoCompetencia.
     ENCONTRADA`) -- sem isso não há nem referência temporal para
     resolver o vínculo (passo 2), então a ponte nunca prossegue.
  2. o colaborador (`COLABORADOR`, nunca `FUNCIONARIO` -- convenção já
     estabelecida em `politica_identificacao_holerite.py`) resolve, via
     `FonteVinculosPrestacao` injetada de fora, para EXATAMENTE 1
     cliente -- usando a competência OBSERVADA como referência temporal
     do vínculo (nunca a esperada, que ainda não existe neste ponto; e
     nunca uma validação -- é só "a qual cliente este colaborador
     pertencia no período que o documento diz ser o dele", uma pergunta
     organizacional, não uma comparação de competência).
  3. com o cliente já resolvido, a competência ESPERADA é obtida de
     `PoliticaCompetenciaPrestacao.competencia_esperada_para` (módulo
     novo `classificacao/competencia_esperada_prestacao.py`) -- fonte
     SEMPRE independente do documento (contexto de ciclo + eventual
     deslocamento por cliente), nunca a observada copiada. `None` =
     nenhuma competência esperada determinável agora -> a ponte para
     aqui, sem inventar.
  4. a competência observada é então validada CONTRA a esperada
     (`validar_competencia`, importacao_lote/dominio.py, já pura e
     reaproveitada sem alteração) -- `observada == esperada` é o único
     uso permitido; nunca o inverso.

Qualquer falha, ambiguidade ou ausência em qualquer um dos 4 passos
acima devolve `None` -- nunca inventa cliente, nunca inventa competência
esperada, nunca trata ambiguidade como resolvida, nunca propaga exceção
de uma fonte externa para quem chama (mesmo princípio já usado por
`classificacao/inventario_prestacao_resultados.py::_converter_resultado`,
o precedente Família-B para esta mesma tradução).

NUNCA importa `ResultadoItem`/Família B (importacao_lote/contratos.py
`ResultadoItem`) -- este módulo é o caminho NOVO, baseado no pipeline
real do Módulo 01, não uma extensão do conversor shadow legado.
"""
from __future__ import annotations

from typing import Optional, Tuple

from magnata_os.classificacao.competencia_esperada_prestacao import (
    ContextoCicloPrestacao,
    PoliticaCompetenciaPrestacao,
)
from magnata_os.classificacao.contratos import (
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.vinculos_prestacao import (
    FonteVinculosPrestacao,
    resolver_clientes_validado,
)

from ..importacao_lote.contratos import (
    CompetenciaExtraida,
    ResultadoCompetencia,
    StatusExtracaoCompetencia,
    TipoDocumental,
)
from ..importacao_lote.dominio import validar_competencia
from .dtos_esteira import HoleriteConfirmadoDTO, ResumoLote


def confirmar_holerite_para_inventario(
    resultado: HoleriteConfirmadoDTO,
    contexto: Optional[ContextoCicloPrestacao],
    politica_competencia: PoliticaCompetenciaPrestacao,
    fonte_vinculos: FonteVinculosPrestacao,
) -> Optional[ItemInventarioPrestacao]:
    """Traduz UM Holerite avulso já identificado pela esteira num item de
    inventário da Prestação de Contas -- ver ordem completa no docstring
    do módulo. Devolve `None` (nunca levanta exceção de fonte externa)
    quando:
      - a competência observada não tem um valor único (`ENCONTRADA`);
      - a fonte de vínculos levanta uma exceção técnica, ou a resolução
        de cliente não é RESOLVIDA com exatamente 1 valor confirmado;
      - `politica_competencia.competencia_esperada_para` devolve `None`
        (nenhuma competência esperada determinável agora para este
        cliente/tipo);
      - a competência observada não é CONFIRMADA contra a esperada
        (ambígua ou divergente)."""
    competencia_observada = CompetenciaExtraida(
        status=StatusExtracaoCompetencia(resultado.competencia_status),
        ano_mes=resultado.competencia_ano_mes,
        estrategia=None,
    )
    if competencia_observada.status != StatusExtracaoCompetencia.ENCONTRADA:
        return None
    ano_observado, mes_observado = competencia_observada.ano_mes

    referencia_observada = ReferenciaCanonica(
        'COMPETENCIA', f'{ano_observado:04d}-{mes_observado:02d}')
    origem = ReferenciaCanonica('COLABORADOR', resultado.colaborador_entidade_id)
    try:
        resolucao_cliente = resolver_clientes_validado(fonte_vinculos, origem, referencia_observada)
    except Exception:
        return None
    if (
        resolucao_cliente.estado != EstadoResolucaoDimensao.RESOLVIDA
        or len(resolucao_cliente.valores_confirmados) != 1
    ):
        return None
    cliente = resolucao_cliente.valores_confirmados[0]

    tipo_documental = TipoDocumental.HOLERITE.value
    competencia_esperada = politica_competencia.competencia_esperada_para(
        contexto, cliente, tipo_documental)
    if competencia_esperada is None:
        return None
    ano_esperado, mes_esperado = competencia_esperada

    resultado_competencia = validar_competencia(competencia_observada, ano_esperado, mes_esperado)
    if resultado_competencia != ResultadoCompetencia.CONFIRMADA:
        return None

    competencia = ReferenciaCanonica('COMPETENCIA', f'{ano_esperado:04d}-{mes_esperado:02d}')
    return ItemInventarioPrestacao(
        documento_id=resultado.documento_id,
        tipo_documental=tipo_documental,
        cliente=cliente,
        competencia=competencia,
    )


def confirmar_holerites_do_lote(
    resumo_lote: ResumoLote,
    contexto: Optional[ContextoCicloPrestacao],
    politica_competencia: PoliticaCompetenciaPrestacao,
    fonte_vinculos: FonteVinculosPrestacao,
) -> Tuple[ItemInventarioPrestacao, ...]:
    """Aplica `confirmar_holerite_para_inventario` a cada item do lote que
    tem `holerite_confirmado` preenchido. Itens de clientes diferentes no
    mesmo lote recebem, cada um, sua própria competência esperada
    (resolvida por cliente via `politica_competencia`) -- nunca uma
    competência única aplicada indistintamente ao lote inteiro. Itens
    sem Holerite confirmado (outro tipo documental, identificação
    ambígua/não encontrada/mestre suspeito, documento duplicado, erro
    técnico de qualquer gate anterior) simplesmente não contribuem --
    nunca geram exceção nem entram no inventário por omissão."""
    itens = []
    for item in resumo_lote.itens:
        if item.holerite_confirmado is None:
            continue
        item_inventario = confirmar_holerite_para_inventario(
            item.holerite_confirmado, contexto, politica_competencia, fonte_vinculos,
        )
        if item_inventario is not None:
            itens.append(item_inventario)
    return tuple(itens)
