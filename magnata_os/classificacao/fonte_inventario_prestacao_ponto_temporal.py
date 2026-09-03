"""Fonte de inventário de Folha/Cartão de Ponto sobre a identidade
temporal REAL já persistida (missão "WIRING REAL DA FOLHA/CARTÃO DE
PONTO NO INVENTÁRIO DA PRESTAÇÃO", pós-PR #127).

Fecha o corredor:

    ResolucaoDocumentalTemporalPonto (já persistida, PR #127)
    + Documento canônico (já existente, modulo01)
    + resolução histórica de cliente/posto (interseção de período,
      já existente, PR #127 revisão independente)
    -> ItemInventarioPrestacao (já existente, prestacao_readiness.py)

Implementa `FonteInventarioPrestacao` (Protocol já existente,
`inventario_prestacao.py`) — nenhum motor/classificador/inventário
novo. Compõe sem alteração com `FonteInventarioPrestacaoComposta`
(`fonte_inventario_composta.py`), exatamente como qualquer outra fonte
já existente (Holerite, Extrato/FGTS/DCTF).

Diferença deliberada em relação à tentativa revertida no PR #125: esta
fonte NUNCA lê dado bruto do Secullum (batidas diárias) — só a
identidade temporal REAL já resolvida (extração de período do PDF real
+ competência + colaborador), consistente com o gate semântico daquela
revisão ("registro bruto ≠ documento")."""
from __future__ import annotations

from typing import Optional, Protocol, Tuple

from .contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao
from .resolucao_temporal_ponto import (
    FonteAlocacaoHistorica,
    ResolucaoDocumentalTemporalPonto,
    resolver_clientes_por_periodo,
)


class FonteResolucoesTemporaisPonto(Protocol):
    """Porta neutra para leitura das resoluções temporais já
    persistidas — hoje implementada por `RepositorioResolucaoTemporal`
    (memória ou Postgres, `documental/modulo01`), nunca reimplementada
    aqui. `classificacao/` nunca importa `documental/modulo01/`
    diretamente (mesma disciplina de camadas já em vigor: é
    `documental/modulo01` que importa `classificacao/`, nunca o
    inverso) — a injeção acontece na borda (composição/testes)."""

    def listar_todos(self) -> Tuple[ResolucaoDocumentalTemporalPonto, ...]: ...


class FonteExistenciaDocumento(Protocol):
    """Porta neutra e mínima para confirmar que existe um `Documento`
    canônico (`documental/modulo01/dominio.py::Documento`) para o
    `documento_id` de uma resolução — nunca produz item para uma
    resolução órfã (documento removido/inexistente)."""

    def existe(self, documento_id: str) -> bool: ...


class FonteInventarioPrestacaoPontoTemporal:
    """Implementa `FonteInventarioPrestacao` para Folha/Cartão de Ponto
    usando a identidade temporal real já persistida. Read-only: nunca
    escreve nada, nunca chama nenhum método de escrita das portas que
    recebe. Determinística: mesma entrada sempre produz o mesmo
    resultado, na mesma ordem."""

    def __init__(
        self,
        fonte_resolucoes: FonteResolucoesTemporaisPonto,
        fonte_alocacao: FonteAlocacaoHistorica,
        fonte_documentos: FonteExistenciaDocumento,
    ):
        self._fonte_resolucoes = fonte_resolucoes
        self._fonte_alocacao = fonte_alocacao
        self._fonte_documentos = fonte_documentos

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        if competencia.tipo_entidade != 'COMPETENCIA':
            raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')

        itens = []
        for resolucao in self._fonte_resolucoes.listar_todos():
            item = self._item_para_cliente_competencia(resolucao, cliente, competencia)
            if item is not None:
                itens.append(item)
        return tuple(sorted(itens, key=lambda item: item.documento_id))

    def _item_para_cliente_competencia(
        self,
        resolucao: ResolucaoDocumentalTemporalPonto,
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> Optional[ItemInventarioPrestacao]:
        # 1. Documento canônico deve existir -- resolução órfã nunca vira item.
        if not self._fonte_documentos.existe(resolucao.documento_id):
            return None

        # 2. Competência deve estar RESOLVIDA (nunca AMBIGUA/CONFLITO/
        #    NAO_ENCONTRADA) e bater exatamente com a pedida -- nunca
        #    fabrica presença para competência incerta ou diferente.
        if resolucao.resolucao_competencia.estado != EstadoResolucaoDimensao.RESOLVIDA:
            return None
        if len(resolucao.resolucao_competencia.valores_confirmados) != 1:
            return None
        if resolucao.resolucao_competencia.valores_confirmados[0] != competencia:
            return None

        # 3. Colaborador identificável.
        if not resolucao.colaborador_id:
            return None

        # 4. Período confiável (coerente com competência RESOLVIDA --
        #    CONFLITO já limpa o período, então isto é defensivo, nunca
        #    redundante: uma resolução malformada nunca vira item).
        if resolucao.periodo_inicio is None or resolucao.periodo_fim is None:
            return None

        # 5. Cliente/posto resolvido por interseção com alocação
        #    histórica -- nunca escolhido arbitrariamente. Ausência ou
        #    ambiguidade de vínculo NUNCA vira item "presente".
        resolucao_cliente = resolver_clientes_por_periodo(
            self._fonte_alocacao, resolucao.colaborador_id,
            resolucao.periodo_inicio, resolucao.periodo_fim,
        )
        if resolucao_cliente.estado != EstadoResolucaoDimensao.RESOLVIDA:
            return None
        if cliente not in resolucao_cliente.valores_confirmados:
            return None  # documento nao pertence a ESTE cliente (ou pertence, mas nao so a ele)

        return ItemInventarioPrestacao(
            documento_id=resolucao.documento_id,
            tipo_documental=resolucao.tipo_documental,
            cliente=cliente,
            competencia=competencia,
            colaborador=ReferenciaCanonica('COLABORADOR', resolucao.colaborador_id),
        )
