"""Fonte de inventário de Folha/Cartão de Ponto (missão "FONTE DE
INVENTÁRIO DE FOLHA/CARTÃO DE PONTO V1") — fecha o gap já nomeado em
`docs/decisoes/inventario-real-prestacao-v1.md".

Implementa `FonteInventarioPrestacao` (porta já existente,
`inventario_prestacao.py`) reaproveitando, sem duplicar:
  - `TIPO_FOLHA_DE_PONTO` (tipo canônico já usado pelo classificador
    geral, `produtores_evidencia_ponto.py`/`classificador_documental.py`);
  - `resolver_clientes_validado`/`FonteVinculosPrestacao`
    (vínculo histórico colaborador->cliente, `vinculos_prestacao.py`),
    exatamente o mesmo mecanismo já usado por
    `FonteInventarioHoleritesAirtableShadow` para Holerite;
  - `PoliticaCicloPontoPrestacao` (`ciclo_ponto_prestacao.py`, novo
    nesta missão) para a janela de dias da competência.

Ponto é 1 registro POR DIA (schema real confirmado em
`src/ingestao_secullum.py`), nunca 1 registro por competência — por
isso esta fonte AGREGA N registros diários num único item lógico por
colaborador/competência (mesma cardinalidade de item que Holerite: 1
`ItemInventarioPrestacao` por colaborador, nunca 1 por dia — a
completude de dias dentro do mês é responsabilidade de outra missão,
fora de escopo aqui, cláusula pétrea #9: nunca reimplementar
extração/cálculo de horas).

Nunca usa nome de arquivo como verdade (não recebe nem lê nome de
arquivo). Nunca reconstrói vínculo do passado com o cadastro atual: a
resolução de cliente é sempre feita para a COMPETÊNCIA pedida, pelo
mesmo `FonteVinculosPrestacao` histórico já usado no resto do corredor
— esta fonte não tem cadastro próprio de colaborador/cliente algum."""
from __future__ import annotations

import dataclasses
import datetime
from typing import Dict, FrozenSet, Optional, Protocol, Set, Tuple

from .contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from .ciclo_ponto_prestacao import PoliticaCicloPontoPrestacao
from .prestacao_readiness import ItemInventarioPrestacao
from .produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO
from .vinculos_prestacao import FonteVinculosPrestacao, resolver_clientes_validado


@dataclasses.dataclass(frozen=True)
class RegistroPontoBruto:
    """1 registro diário bruto de Ponto — evidência, nunca verdade
    semântica por si só (regra pétrea #3/#4 da missão). `colaborador`
    é sempre `ReferenciaCanonica('FUNCIONARIO', ...)`, SANITIZADA (nunca
    CPF/nome) — mesmo tipo de origem que `resolver_clientes_validado`
    já aceita para Holerite. `batidas` é a assinatura MÍNIMA usada só
    para detectar duplicidade conflitante (2 registros do mesmo dia com
    horários diferentes) — nunca usada para calcular jornada/horas
    (fora de escopo)."""

    documento_id: str
    colaborador: ReferenciaCanonica
    data: datetime.date
    batidas: Tuple[str, ...] = ()
    possui_marcacao: bool = True
    """`False` representa um registro do dia sem nenhuma batida (ex.:
    falta) -- nunca conta como evidência de presença, mas também nunca
    é tratado como conflito."""

    def __post_init__(self) -> None:
        if self.colaborador.tipo_entidade != 'FUNCIONARIO':
            raise ValueError("colaborador deve ser referencia canonica de FUNCIONARIO")
        if not self.documento_id.strip():
            raise ValueError('documento_id deve ser texto nao vazio')


class FonteRegistrosPontoBrutos(Protocol):
    """Porta neutra e substituível para a origem dos registros diários
    brutos — Airtable é só UMA implementação possível (read-only),
    nunca a única; Postgres/arquivo/memória servem igualmente, desde
    que devolvam `RegistroPontoBruto`."""

    def listar_no_intervalo(
        self, data_inicio: datetime.date, data_fim: datetime.date,
    ) -> Tuple[RegistroPontoBruto, ...]: ...


def _assinatura(registro: RegistroPontoBruto) -> FrozenSet[str]:
    return frozenset(registro.batidas)


class FonteInventarioPontoPrestacao:
    """Implementa `FonteInventarioPrestacao` para a família Folha de
    Ponto, agregando registros diários numa janela de ciclo (mês civil
    por padrão, com override por cliente — `ciclo_ponto_prestacao.py`)."""

    def __init__(
        self,
        fonte_registros: FonteRegistrosPontoBrutos,
        fonte_vinculos: FonteVinculosPrestacao,
        politica_ciclo: Optional[PoliticaCicloPontoPrestacao] = None,
    ):
        self._fonte_registros = fonte_registros
        self._fonte_vinculos = fonte_vinculos
        from .ciclo_ponto_prestacao import POLITICA_CICLO_PONTO_PRESTACAO_V1
        self._politica_ciclo = politica_ciclo or POLITICA_CICLO_PONTO_PRESTACAO_V1

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        if competencia.tipo_entidade != 'COMPETENCIA':
            raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')

        janela = self._politica_ciclo.janela_para(cliente, competencia)
        registros = self._fonte_registros.listar_no_intervalo(
            janela.data_inicio, janela.data_fim,
        )

        # Agrupa por (funcionario_id, dia) para detectar duplicidade
        # CONFLITANTE (regra 11): 2+ registros do MESMO dia com
        # assinaturas de batida DIFERENTES nunca viram evidência --
        # nunca produzem falso COMPLETO. Duas cópias EQUIVALENTES
        # (mesma assinatura, inclusive vazias) colapsam sem conflito.
        por_func_dia: Dict[Tuple[str, datetime.date], list] = {}
        for registro in registros:
            if not registro.possui_marcacao:
                continue
            if not janela.contem(registro.data):
                continue
            chave = (registro.colaborador.entidade_id, registro.data)
            por_func_dia.setdefault(chave, []).append(registro)

        dias_validos_por_func: Dict[str, Set[datetime.date]] = {}
        for (func_id, dia), regs in por_func_dia.items():
            assinaturas = {_assinatura(r) for r in regs}
            if len(assinaturas) > 1:
                continue  # duplicidade conflitante -- dia descartado, nunca inventado
            dias_validos_por_func.setdefault(func_id, set()).add(dia)

        itens = []
        for func_id, dias in dias_validos_por_func.items():
            if not dias:
                continue
            origem = ReferenciaCanonica('FUNCIONARIO', func_id)
            try:
                resolucao = resolver_clientes_validado(self._fonte_vinculos, origem, competencia)
            except ValueError:
                continue
            if resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA:
                continue  # vinculo nao resolvido -- nunca inventa, item simplesmente nao aparece
            if cliente not in resolucao.valores_confirmados:
                continue
            documento_id = f'ponto:{func_id}:{competencia.entidade_id}'
            itens.append(ItemInventarioPrestacao(
                documento_id=documento_id, tipo_documental=TIPO_FOLHA_DE_PONTO,
                cliente=cliente, competencia=competencia,
                colaborador=ReferenciaCanonica('COLABORADOR', func_id),
            ))
        return tuple(sorted(itens, key=lambda item: item.documento_id))
