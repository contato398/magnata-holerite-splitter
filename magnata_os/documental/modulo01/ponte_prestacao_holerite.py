"""Ponte pura Módulo 01 (Documental) -> Prestação de Contas, Holerite avulso.

Traduz um `HoleriteConfirmadoDTO` (dtos_esteira.py -- fato OBSERVADO já
sanitizado, produzido por `ServicoCriacaoLote._processar_um_arquivo`
quando a identificação de colaborador terminou RESOLVIDA) num
`ItemInventarioPrestacao` (classificacao/prestacao_readiness.py -- o
contrato neutro já consumido por `avaliar_prestacao_shadow`/
`avaliar_prestacao_readiness`), SÓ quando TRÊS condições, cada uma
verificada de forma independente, são verdadeiras:

  1. existe uma competência ESPERADA para este ciclo -- `competencia_
     esperada`, parâmetro EXPLICITAMENTE `Optional`. Este módulo NUNCA a
     infere do documento nem de um default: é o seam deliberado (ver
     auditoria da missão, §5) para que ela seja suprida depois por
     contexto externo independente (mesmo padrão já estabelecido por
     `scripts/prestacao_readiness_shadow_real.py --competencia` e pelo
     parâmetro obrigatório `competencia` de `avaliar_prestacao_shadow`).
     Quando `None` -- nenhuma competência esperada configurada para este
     ciclo -- devolve `None` imediatamente: item fica de fora do
     inventário, resultado explicitamente pendente, NUNCA um `PRONTO`
     por ausência de evidência.
  2. a competência OBSERVADA no documento (extraída do próprio PDF,
     nunca da configuração) é CONFIRMADA contra a esperada. Comparar
     `observada == esperada` é o único uso permitido; nunca o inverso
     (`esperada = observada`), que seria validação circular --
     `magnata_os/documental/importacao_lote/dominio.py::validar_competencia`,
     já pura e reaproveitada aqui sem alteração.
  3. o colaborador (`COLABORADOR`, nunca `FUNCIONARIO` -- convenção já
     estabelecida em `politica_identificacao_holerite.py`) resolve, via
     `FonteVinculosPrestacao` injetada de fora, para EXATAMENTE 1
     cliente -- `resolver_clientes_validado` (classificacao/
     vinculos_prestacao.py) já reaproveitado sem alteração.

Qualquer falha, ambiguidade ou ausência em qualquer uma das três
condições acima devolve `None` -- nunca inventa cliente, nunca inventa
competência esperada, nunca trata ambiguidade como resolvida, nunca
propaga exceção de uma fonte externa para quem chama (mesmo princípio
já usado por `classificacao/inventario_prestacao_resultados.py::
_converter_resultado`, o precedente Família-B para esta mesma tradução).

NUNCA importa `ResultadoItem`/Família B (importacao_lote/contratos.py
`ResultadoItem`) -- este módulo é o caminho NOVO, baseado no pipeline
real do Módulo 01, não uma extensão do conversor shadow legado.
"""
from __future__ import annotations

from typing import Optional, Tuple

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
    competencia_esperada: Optional[Tuple[int, int]],
    fonte_vinculos: FonteVinculosPrestacao,
) -> Optional[ItemInventarioPrestacao]:
    """Traduz UM Holerite avulso já identificado pela esteira num item de
    inventário da Prestação de Contas.

    `competencia_esperada` é `(ano, mes)` -- a competência ESPERADA para
    este ciclo, SEMPRE fornecida por quem chama (fonte independente,
    fora deste módulo), nunca inferida do próprio documento. `None`
    representa explicitamente "nenhuma competência esperada configurada
    ainda para este ciclo" -- devolve `None` sem tentar nenhuma
    comparação (nunca copia a observada como se fosse a esperada).

    Devolve `None` (nunca levanta exceção de fonte externa) quando:
      - `competencia_esperada is None`;
      - a competência observada não é CONFIRMADA contra a esperada
        (ausente, ambígua ou divergente);
      - a fonte de vínculos levanta uma exceção técnica;
      - a resolução de cliente não é RESOLVIDA ou não é exatamente 1
        valor confirmado (ambígua, conflitante, ausente)."""
    if competencia_esperada is None:
        return None
    ano_esperado, mes_esperado = competencia_esperada

    competencia_observada = CompetenciaExtraida(
        status=StatusExtracaoCompetencia(resultado.competencia_status),
        ano_mes=resultado.competencia_ano_mes,
        estrategia=None,
    )
    resultado_competencia = validar_competencia(competencia_observada, ano_esperado, mes_esperado)
    if resultado_competencia != ResultadoCompetencia.CONFIRMADA:
        return None

    competencia = ReferenciaCanonica('COMPETENCIA', f'{ano_esperado:04d}-{mes_esperado:02d}')
    origem = ReferenciaCanonica('COLABORADOR', resultado.colaborador_entidade_id)
    try:
        resolucao = resolver_clientes_validado(fonte_vinculos, origem, competencia)
    except Exception:
        return None
    if resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA or len(resolucao.valores_confirmados) != 1:
        return None
    cliente = resolucao.valores_confirmados[0]

    return ItemInventarioPrestacao(
        documento_id=resultado.documento_id,
        tipo_documental=TipoDocumental.HOLERITE.value,
        cliente=cliente,
        competencia=competencia,
    )


def confirmar_holerites_do_lote(
    resumo_lote: ResumoLote,
    competencia_esperada: Optional[Tuple[int, int]],
    fonte_vinculos: FonteVinculosPrestacao,
) -> Tuple[ItemInventarioPrestacao, ...]:
    """Aplica `confirmar_holerite_para_inventario` a cada item do lote que
    tem `holerite_confirmado` preenchido. Itens sem Holerite confirmado
    (outro tipo documental, identificação ambígua/não encontrada/mestre
    suspeito, documento duplicado, erro técnico de qualquer gate
    anterior) simplesmente não contribuem -- nunca geram exceção nem
    entram no inventário por omissão."""
    itens = []
    for item in resumo_lote.itens:
        if item.holerite_confirmado is None:
            continue
        item_inventario = confirmar_holerite_para_inventario(
            item.holerite_confirmado, competencia_esperada, fonte_vinculos,
        )
        if item_inventario is not None:
            itens.append(item_inventario)
    return tuple(itens)
