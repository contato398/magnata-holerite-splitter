"""Política pura e versionada da competência ESPERADA da Prestação de
Contas — fonte independente do documento, nunca inferida dele.

Contexto (missão "DEFINIR E IMPLEMENTAR A FONTE AUTOMÁTICA DE
COMPETÊNCIA ESPERADA"): auditoria do repositório (legado `app.py`,
`scripts/prestacao_readiness_shadow_real.py`, `ConfiguracaoExecucao`)
confirmou que:

  - não existe hoje nenhuma regra JÁ REGISTRADA de deslocamento de
    competência por cliente (nenhuma ocorrência de "cliente X usa mês
    Y" em código ou documentação) — por isso este módulo NUNCA
    codifica um cliente específico; só o MECANISMO de exceção, vazio
    por padrão, mesmo padrão já usado por `OverrideRequisitosPrestacao`/
    `PoliticaRequisitosPrestacao` (politica_requisitos_prestacao.py);
  - o legado (`app.py::mes_anterior_info`, `buscar_mes_contabilidade_
    atual`) já resolve uma competência BASE do ciclo a partir do
    relógio (`datetime.now()`) e de uma consulta a uma tabela real do
    Airtable — mas em seguida deixa o PDF do próprio documento
    SOBRESCREVER esse valor quando diverge ("Competência manda",
    `app.py` linha ~2021). Isso é EXATAMENTE a validação circular que
    esta missão proíbe (`esperada = observada` de forma indireta) — não
    é reaproveitado aqui. Este módulo nunca lê o relógio, nunca lê o
    documento; a competência BASE é sempre um parâmetro explícito de
    quem chama (`ContextoCicloPrestacao`), fornecido uma vez por
    execução — nunca por documento, nunca redescoberta pelo relógio.

Modelo:

    ContextoCicloPrestacao (competência BASE do ciclo, uma vez por
    execução -- fonte independente do documento: config operacional,
    parâmetro de execução do runner, ou calendário/fechamento externo,
    QUALQUER que já exista e seja fornecido de fora)
      +
    PoliticaCompetenciaPrestacao (deslocamentos POR CLIENTE, opcionalmente
    restritos a um tipo documental -- mecanismo, não regra hoje
    conhecida; vazio por padrão)
      +
    cliente (já resolvido, nunca antes disso)
      +
    tipo_documental
      -> competencia_esperada_para(...) -> Optional[Tuple[int, int]]

`None` é sempre "nenhuma competência esperada determinável agora" --
nunca inventado, nunca um default de relógio. Precedência determinística:
deslocamento específico (cliente + tipo_documental) > deslocamento geral
do cliente (tipo_documental=None) > competência base do contexto >
`None` (contexto ausente).
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

from .contratos import ReferenciaCanonica

_MES_MINIMO = 1
_MES_MAXIMO = 12


def _validar_ano_mes(ano_mes: Tuple[int, int], rotulo: str) -> None:
    ano, mes = ano_mes
    if not (_MES_MINIMO <= mes <= _MES_MAXIMO):
        raise ValueError(f'{rotulo}: mes deve estar entre 1 e 12, recebido {mes!r}')
    if isinstance(ano, bool) or not isinstance(ano, int):
        raise ValueError(f'{rotulo}: ano deve ser inteiro, recebido {ano!r}')


@dataclasses.dataclass(frozen=True)
class ContextoCicloPrestacao:
    """Competência BASE de UM ciclo de execução da Prestação de Contas --
    fornecida uma única vez por execução (nunca por documento, nunca
    lida do relógio dentro deste módulo). Representa "qual competência
    este runner está processando agora", uma decisão operacional externa
    a este módulo (config, parâmetro de linha de comando, calendário de
    fechamento já registrado -- qualquer fonte já independente do
    documento)."""

    competencia_base: Tuple[int, int]

    def __post_init__(self) -> None:
        _validar_ano_mes(self.competencia_base, 'competencia_base')


@dataclasses.dataclass(frozen=True)
class DeslocamentoCompetenciaCliente:
    """UM deslocamento explícito de competência esperada para um cliente
    -- mecanismo de exceção, nunca uma regra inventada por este módulo
    (ver auditoria no docstring do módulo: nenhum deslocamento real é
    codificado aqui, a lista fica vazia até uma decisão de negócio
    concreta registrar um). `tipo_documental=None` aplica o deslocamento
    a qualquer tipo documental deste cliente; um valor explícito
    restringe a esse tipo só (precedência sobre o geral -- ver
    `PoliticaCompetenciaPrestacao.competencia_esperada_para`)."""

    cliente: ReferenciaCanonica
    competencia: Tuple[int, int]
    tipo_documental: Optional[str] = None

    def __post_init__(self) -> None:
        if self.cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        if self.tipo_documental is not None and not self.tipo_documental.strip():
            raise ValueError('tipo_documental, quando informado, deve ser texto nao vazio')
        _validar_ano_mes(self.competencia, 'competencia')


@dataclasses.dataclass(frozen=True)
class PoliticaCompetenciaPrestacao:
    """Política pura e versionada -- mesmo papel de
    `PoliticaRequisitosPrestacao` (politica_requisitos_prestacao.py),
    aplicado à dimensão competência esperada em vez de requisitos
    documentais. `deslocamentos=()` (vazio) é o estado real hoje: nenhum
    cliente tem exceção comprovada (ver auditoria) -- toda resolução usa
    só a competência base do contexto até uma decisão de negócio
    concreta adicionar um deslocamento."""

    version: str
    deslocamentos: Tuple[DeslocamentoCompetenciaCliente, ...] = ()

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError('version deve ser texto nao vazio')
        chaves = [
            (item.cliente, item.tipo_documental)
            for item in self.deslocamentos
        ]
        if len(chaves) != len(set(chaves)):
            # Fail-fast na CONSTRUÇÃO -- nunca decide entre dois
            # deslocamentos conflitantes para o mesmo cliente/tipo em
            # tempo de resolução; uma política ambígua nem chega a
            # existir para ser consultada.
            raise ValueError(
                'politica nao pode repetir deslocamento para o mesmo '
                'cliente/tipo_documental')

    def competencia_esperada_para(
        self,
        contexto: Optional[ContextoCicloPrestacao],
        cliente: ReferenciaCanonica,
        tipo_documental: str,
    ) -> Optional[Tuple[int, int]]:
        """Resolve a competência esperada para `cliente`/`tipo_documental`
        -- SEMPRE com `cliente` já resolvido por quem chama (nunca
        calculado arbitrariamente para um cliente ambíguo ou não
        resolvido). `None` é a resposta correta e final quando não há
        deslocamento aplicável nem `contexto` -- nunca um default de
        relógio, nunca uma invenção."""
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')

        especifico = next(
            (
                item.competencia for item in self.deslocamentos
                if item.cliente == cliente and item.tipo_documental == tipo_documental
            ),
            None,
        )
        if especifico is not None:
            return especifico

        geral = next(
            (
                item.competencia for item in self.deslocamentos
                if item.cliente == cliente and item.tipo_documental is None
            ),
            None,
        )
        if geral is not None:
            return geral

        if contexto is None:
            return None
        return contexto.competencia_base
