"""Política pura e versionada da JANELA DE DIAS de um ciclo de Folha/
Cartão de Ponto (missão "FONTE DE INVENTÁRIO DE FOLHA/CARTÃO DE PONTO
V1"). Fecha o gap já nomeado em `docs/decisoes/inventario-real-
prestacao-v1.md` ("Folha de Ponto: NECESSITA EVIDÊNCIA — não
construído").

Contexto: ao contrário de Holerite/Extrato/FGTS (1 registro por
competência, campo "Folha Mensal"/"Mês Contabilidade" já pronto), a
tabela real de Ponto (`AT_PONTO = 'tblmgV10s3dZiP8av'`, confirmada em
`src/ingestao_secullum.py`) é 1 REGISTRO POR DIA, sem nenhum campo de
competência — a evidência de presença é agregada por JANELA DE DATAS.
Este módulo resolve, para um cliente/competência já resolvidos, QUAL
janela `[data_inicio, data_fim]` (inclusive) vale para agregar essa
evidência.

Default: mês civil da própria competência (dia 1 até o último dia do
mês) — cobre a esmagadora maioria dos clientes, que fecham a folha de
ponto pelo calendário. Alguns ciclos de ponto não coincidem com o mês
civil — isso é representado como OVERRIDE explícito por cliente, nunca
um `if` de nome de cliente espalhado pelo motor, mesmo padrão já usado
por `competencia_esperada_prestacao.py` para o deslocamento de
competência. `overrides=()` (vazio) é o default seguro — nenhuma
exceção real de ciclo de Ponto está confirmada hoje para nenhum
cliente; a missão que introduziu este módulo usa um cliente SINTÉTICO
com dia de fechamento 28 apenas como caso adversarial de teste (nunca
SKY Tatuí — nenhuma regra de negócio nova foi inventada para ele aqui).

REGRA CONFIRMADA (revisão independente, correção sobre a v1 original
deste módulo): um override representa o DIA DE FECHAMENTO do ciclo
(`dia_fechamento`), nunca o dia de início. O ciclo da competência X é
`[dia seguinte ao fechamento do ciclo anterior, dia_fechamento de X]`,
ambos inclusive — ex.: fechamento=28, competência junho/2026 -> ciclo
29/05/2026 a 28/06/2026 (nunca 28/05 a 28/06 -- essa era a modelagem
INCORRETA da v1 original, corrigida aqui). Por construção, ciclos
consecutivos nunca se sobrepõem e nunca deixam lacuna: o início de um
ciclo é sempre, literalmente, `fim do ciclo anterior + 1 dia`."""
from __future__ import annotations

import calendar
import dataclasses
import datetime
from typing import Optional, Tuple

from .contratos import ReferenciaCanonica

_MES_MINIMO = 1
_MES_MAXIMO = 12


def _competencia_para_ano_mes(competencia: ReferenciaCanonica) -> Tuple[int, int]:
    if competencia.tipo_entidade != 'COMPETENCIA':
        raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')
    try:
        ano_texto, mes_texto = competencia.entidade_id.split('-', maxsplit=1)
        ano, mes = int(ano_texto), int(mes_texto)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError('competencia deve usar o formato AAAA-MM') from exc
    if len(ano_texto) != 4 or len(mes_texto) != 2 or not _MES_MINIMO <= mes <= _MES_MAXIMO:
        raise ValueError('competencia deve usar o formato AAAA-MM')
    return ano, mes


def _mes_anterior(ano: int, mes: int) -> Tuple[int, int]:
    indice_mes_zero = (ano * 12 + (mes - 1)) - 1
    ano_resultado, mes_zero = divmod(indice_mes_zero, 12)
    return ano_resultado, mes_zero + 1


@dataclasses.dataclass(frozen=True)
class JanelaCicloPonto:
    """Intervalo de datas (ambas inclusive) usado para agregar registros
    diários de Ponto numa única competência lógica."""

    data_inicio: datetime.date
    data_fim: datetime.date

    def __post_init__(self) -> None:
        if self.data_fim < self.data_inicio:
            raise ValueError('data_fim nao pode ser anterior a data_inicio')

    def contem(self, dia: datetime.date) -> bool:
        return self.data_inicio <= dia <= self.data_fim


@dataclasses.dataclass(frozen=True)
class CicloPontoClienteOverride:
    """UM override explícito do dia de FECHAMENTO do ciclo de Ponto para
    um cliente — mecanismo de exceção, nunca uma regra inventada por
    este módulo. `dia_fechamento` é o dia do mês em que o ciclo do
    cliente TERMINA (ex.: 28 -> o ciclo da competência de junho/2026
    termina em 28/06/2026 e começa no dia seguinte ao fechamento do
    ciclo anterior, 29/05/2026 -- nunca no próprio dia 28 do mês
    anterior, o que sobreporia 1 dia entre ciclos consecutivos)."""

    cliente: ReferenciaCanonica
    dia_fechamento: int

    def __post_init__(self) -> None:
        if self.cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        if isinstance(self.dia_fechamento, bool) or not isinstance(self.dia_fechamento, int):
            raise ValueError('dia_fechamento deve ser inteiro')
        if not 1 <= self.dia_fechamento <= 28:
            # 28 é o maior dia garantido em qualquer mês (inclusive
            # fevereiro) -- nunca um dia que possa não existir no mês
            # anterior, o que tornaria a janela ambígua.
            raise ValueError('dia_fechamento deve estar entre 1 e 28')


@dataclasses.dataclass(frozen=True)
class PoliticaCicloPontoPrestacao:
    """Política pura e versionada — mesmo papel de
    `PoliticaCompetenciaPrestacao`, aplicada à janela de dias do ciclo
    de Ponto em vez do deslocamento de competência esperada."""

    version: str
    overrides: Tuple[CicloPontoClienteOverride, ...] = ()

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError('version deve ser texto nao vazio')
        clientes = [item.cliente for item in self.overrides]
        if len(clientes) != len(set(clientes)):
            raise ValueError('politica nao pode repetir override para o mesmo cliente')

    def janela_para(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> JanelaCicloPonto:
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        ano, mes = _competencia_para_ano_mes(competencia)

        override = next((item for item in self.overrides if item.cliente == cliente), None)
        if override is None:
            data_inicio = datetime.date(ano, mes, 1)
            ultimo_dia = calendar.monthrange(ano, mes)[1]
            data_fim = datetime.date(ano, mes, ultimo_dia)
            return JanelaCicloPonto(data_inicio, data_fim)

        # Fechamento no dia `dia_fechamento` da própria competência;
        # início = dia SEGUINTE ao fechamento do ciclo anterior -- nunca
        # o mesmo dia do mês anterior (isso sobreporia 1 dia entre
        # ciclos consecutivos). `dia_fechamento <= 28` garante que tanto
        # o fechamento atual quanto o do ciclo anterior sejam datas
        # válidas em QUALQUER mês (inclusive fevereiro não-bissexto);
        # somar 1 dia via `timedelta` rola corretamente para o mês
        # seguinte quando necessário -- nunca aritmética de mês manual.
        data_fim = datetime.date(ano, mes, override.dia_fechamento)
        ano_anterior, mes_anterior = _mes_anterior(ano, mes)
        data_fim_ciclo_anterior = datetime.date(ano_anterior, mes_anterior, override.dia_fechamento)
        data_inicio = data_fim_ciclo_anterior + datetime.timedelta(days=1)
        return JanelaCicloPonto(data_inicio, data_fim)


# Default seguro -- nenhuma exceção real de ciclo de Ponto confirmada
# hoje para nenhum cliente (ver docstring do módulo). Todo cliente usa
# o mês civil até que uma exceção real seja confirmada e registrada
# aqui do mesmo jeito que `DESLOCAMENTO_SKY_TATUI` foi, em
# `competencia_esperada_prestacao.py`.
POLITICA_CICLO_PONTO_PRESTACAO_V1 = PoliticaCicloPontoPrestacao(version='1')
