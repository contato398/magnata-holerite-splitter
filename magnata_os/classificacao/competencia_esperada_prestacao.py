"""Política pura e versionada da competência ESPERADA da Prestação de
Contas — fonte independente do documento, nunca inferida dele.

Contexto (missão "DEFINIR E IMPLEMENTAR A FONTE AUTOMÁTICA DE
COMPETÊNCIA ESPERADA" + missão corretiva "ATIVAR REGRA DE COMPETÊNCIA
DO SKY TATUÍ"): auditoria do repositório (legado `app.py`,
`scripts/prestacao_readiness_shadow_real.py`, `ConfiguracaoExecucao`)
confirmou que:

  - não existe hoje nenhuma regra JÁ REGISTRADA de deslocamento de
    competência por cliente ALÉM da exceção do SKY Tatuí (única
    confirmada por leitura somente-GET no Airtable em 2026-08-30 --
    ver `REFERENCIA_CLIENTE_SKY_TATUI`/`POLITICA_COMPETENCIA_
    PRESTACAO_V1` abaixo e docs/decisoes/
    competencia-esperada-prestacao-v1.md). Este módulo NUNCA codifica
    um cliente por NOME livre -- só por referência canônica
    (`ReferenciaCanonica("CLIENTE", record_id)`) já comprovada;
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
    restritos a um tipo documental -- cada um ABSOLUTO (competência fixa)
    OU RELATIVO (offset em meses sobre a base do contexto, nunca os dois
    ao mesmo tempo); vazia por padrão, com a exceção real do SKY Tatuí
    disponível como constante pronta -- `POLITICA_COMPETENCIA_
    PRESTACAO_V1`, abaixo)
      +
    cliente (já resolvido, nunca antes disso)
      +
    tipo_documental
      -> competencia_esperada_para(...) -> Optional[Tuple[int, int]]

`None` é sempre "nenhuma competência esperada determinável agora" --
nunca inventado, nunca um default de relógio. Precedência determinística:
deslocamento específico (cliente + tipo_documental) > deslocamento geral
do cliente (tipo_documental=None) > competência base do contexto >
`None` (contexto ausente, inclusive quando o deslocamento aplicável é
RELATIVO e não há base para aplicar o offset).
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


def _aplicar_offset_meses(ano_mes: Tuple[int, int], offset_meses: int) -> Tuple[int, int]:
    """Desloca `ano_mes` por `offset_meses` (negativo = meses ANTES),
    tratando virada de ano corretamente -- aritmética inteira pura,
    nunca `datetime`/`calendar`. Ex.: `((2027, 1), -1) -> (2026, 12)`."""
    ano, mes = ano_mes
    indice_mes_zero = (ano * 12 + (mes - 1)) + offset_meses
    ano_resultado, mes_zero = divmod(indice_mes_zero, 12)
    return (ano_resultado, mes_zero + 1)


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
    -- mecanismo de exceção, nunca uma regra inventada por este módulo.
    `tipo_documental=None` aplica o deslocamento a qualquer tipo
    documental deste cliente; um valor explícito restringe a esse tipo
    só (precedência sobre o geral -- ver `PoliticaCompetenciaPrestacao.
    competencia_esperada_para`).

    Exatamente UMA das duas formas deve ser usada, nunca as duas nem
    nenhuma:
      - `competencia`: um valor ABSOLUTO fixo (ano, mes) -- correto só
        quando a exceção realmente não varia com o ciclo (raro; preserve
        esta forma por compatibilidade, mas prefira `offset_meses`
        sempre que a regra de negócio for relativa ao ciclo, como é o
        caso real hoje -- ver `DESLOCAMENTO_SKY_TATUI` abaixo);
      - `offset_meses`: um deslocamento RELATIVO (nunca zero) aplicado
        sobre `ContextoCicloPrestacao.competencia_base` no momento da
        resolução (`_aplicar_offset_meses`) -- nunca uma competência
        fixa hardcoded; funciona para qualquer competência base,
        incluindo virada de ano."""

    cliente: ReferenciaCanonica
    competencia: Optional[Tuple[int, int]] = None
    tipo_documental: Optional[str] = None
    offset_meses: Optional[int] = None

    def __post_init__(self) -> None:
        if self.cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        if self.tipo_documental is not None and not self.tipo_documental.strip():
            raise ValueError('tipo_documental, quando informado, deve ser texto nao vazio')
        if (self.competencia is None) == (self.offset_meses is None):
            raise ValueError(
                'informe exatamente um entre competencia (absoluta) e '
                'offset_meses (relativo) -- nunca os dois, nunca nenhum')
        if self.competencia is not None:
            _validar_ano_mes(self.competencia, 'competencia')
        else:
            if isinstance(self.offset_meses, bool) or not isinstance(self.offset_meses, int):
                raise ValueError(f'offset_meses deve ser inteiro, recebido {self.offset_meses!r}')
            if self.offset_meses == 0:
                raise ValueError(
                    'offset_meses=0 nao e deslocamento -- omita o deslocamento '
                    'inteiro para que o cliente use a competencia base')


@dataclasses.dataclass(frozen=True)
class PoliticaCompetenciaPrestacao:
    """Política pura e versionada -- mesmo papel de
    `PoliticaRequisitosPrestacao` (politica_requisitos_prestacao.py),
    aplicado à dimensão competência esperada em vez de requisitos
    documentais. `deslocamentos=()` (vazio) é o default seguro para
    quem não tem exceção nenhuma -- a exceção real e confirmada do SKY
    Tatuí já vem pronta em `POLITICA_COMPETENCIA_PRESTACAO_V1`, abaixo,
    para quem compõe o corredor real reaproveitar sem duplicar a
    regra."""

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
        relógio, nunca uma invenção. Um deslocamento RELATIVO sem
        `contexto` também devolve `None` (nada para aplicar o offset
        sobre -- nunca inventa uma base)."""
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')

        aplicavel = next(
            (
                item for item in self.deslocamentos
                if item.cliente == cliente and item.tipo_documental == tipo_documental
            ),
            None,
        )
        if aplicavel is None:
            aplicavel = next(
                (
                    item for item in self.deslocamentos
                    if item.cliente == cliente and item.tipo_documental is None
                ),
                None,
            )

        if aplicavel is not None:
            if aplicavel.competencia is not None:
                return aplicavel.competencia
            if contexto is None:
                return None
            return _aplicar_offset_meses(contexto.competencia_base, aplicavel.offset_meses)

        if contexto is None:
            return None
        return contexto.competencia_base


# ============================================================================
# Exceção operacional REAL confirmada -- SKY Tatuí
# ============================================================================
#
# Referência canônica confirmada por leitura somente-GET no Airtable em
# 2026-08-30 (base appaCpIVj7Q97VhFy, tabela Clientes
# tbl0znyuCEzoCHtCV, cliente "EDIFICIO SKY TATUI") -- ver
# docs/decisoes/competencia-esperada-prestacao-v1.md. Identidade
# operacional é SEMPRE o record id abaixo, nunca o nome livre.
REFERENCIA_CLIENTE_SKY_TATUI = ReferenciaCanonica('CLIENTE', 'recrqv5NvbC37WfSl')

# Regra de negócio confirmada: este cliente usa competência esperada =
# competência base do ciclo MENOS 1 mês (nunca uma competência fixa --
# válido para qualquer competência base, inclusive virada de ano).
DESLOCAMENTO_SKY_TATUI = DeslocamentoCompetenciaCliente(
    cliente=REFERENCIA_CLIENTE_SKY_TATUI,
    offset_meses=-1,
)

# Política real pronta para reuso por quem compõe o corredor -- evita
# duplicar a regra do SKY Tatuí em mais de um lugar. Clientes sem
# exceção continuam usando a competência base normalmente.
POLITICA_COMPETENCIA_PRESTACAO_V1 = PoliticaCompetenciaPrestacao(
    version='1',
    deslocamentos=(DESLOCAMENTO_SKY_TATUI,),
)
