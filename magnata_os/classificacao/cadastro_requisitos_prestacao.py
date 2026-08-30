"""Cadastro CANÔNICO VERSIONADO de requisitos da Prestação de Contas
(missão "CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO", Fases 5-8).

Declarativo em Python — preserva tipagem (validada em tempo de
import), histórico Git, diff legível, zero dependência de Airtable
(cláusula pétrea #5: "Airtable não é o cérebro"). Toda linha carrega
`evidencia` obrigatória citando a origem — nunca um requisito sem
proveniência (cláusula pétrea #3).

DUAS FONTES CANÔNICAS EXISTENTES foram auditadas (Fase 1/3 desta
missão) e DIVERGEM entre si:
  - `politica_requisitos_prestacao.REQUISITOS_BASE_PRESTACAO` (Família
    B): DCTFWeb-Declaração, DCTFWeb-Recibo, Guia DCTFWeb/DARF, FGTS,
    extrato_cliente.
  - `app.py::CAPACIDADES_DOCUMENTO` (legado, tabela de capacidades já
    documentada): Holerite, Extrato da Folha de Pagamento, FGTS,
    DCTFWeb-Recibo, DCTFWeb-Declaração.

INTERSEÇÃO (as duas fontes concordam, tradução de vocabulário
`extrato_cliente` <-> `Extrato da Folha de Pagamento` via
`normalizacao_requisitos_prestacao.TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL`):
FGTS, DCTFWeb-Declaração, DCTFWeb-Recibo, Extrato da Folha de
Pagamento — viram `REQUISITOS_BASE_CANONICOS_V1` (nunca inventam
obrigação: as DUAS fontes já concordavam).

DIVERGÊNCIA (cada uma só numa fonte): Holerite (só em `CAPACIDADES_
DOCUMENTO`) e Guia DCTFWeb/DARF (só em `REQUISITOS_BASE_PRESTACAO`) —
NUNCA promovidos a base universal por uma fonte só (cláusula pétrea
#3: "regra de negócio só entra como canônica se houver evidência
comprovável" — aqui há evidência de CADA um, mas não CONCORDANTE o
suficiente para uma obrigação universal); ficam registrados como
`REQUISITOS_DIVERGENTES_ENTRE_FONTES`, disponíveis para configuração
condicional explícita por cliente quando um humano confirmar."""
from __future__ import annotations

import dataclasses
import enum
from typing import Tuple

from .normalizacao_requisitos_prestacao import (
    TIPOS_DOCUMENTAIS_CANONICOS,
    RegistroRequisitoExterno,
)
from .prestacao_readiness import RequisitoDocumentalPrestacao


class EstadoConfiguracaoRequisito(str, enum.Enum):
    CONFIGURADO_EXIGE = 'CONFIGURADO_EXIGE'
    CONFIGURADO_NAO_EXIGE = 'CONFIGURADO_NAO_EXIGE'
    NAO_CONFIGURADO = 'NAO_CONFIGURADO'


@dataclasses.dataclass(frozen=True)
class RequisitoCanonico:
    """1 linha da base universal -- exige `evidencia` (nunca uma linha
    sem proveniência citável)."""

    tipo_documental: str
    evidencia: str
    quantidade_minima: int = 1

    def __post_init__(self) -> None:
        if self.tipo_documental not in TIPOS_DOCUMENTAIS_CANONICOS:
            raise ValueError(f'tipo_documental fora do universo canonico: {self.tipo_documental!r}')
        if not self.evidencia.strip():
            raise ValueError('evidencia deve ser texto nao vazio -- nunca requisito sem proveniencia')
        if isinstance(self.quantidade_minima, bool) or self.quantidade_minima < 1:
            raise ValueError('quantidade_minima deve ser inteira positiva')


@dataclasses.dataclass(frozen=True)
class ConfiguracaoCondicionalCliente:
    """1 configuração EXPLÍCITA (exige ou não exige) de 1 tipo para 1
    cliente. Ausência de uma entrada aqui para um (cliente, tipo)
    significa `NAO_CONFIGURADO` -- nunca `CONFIGURADO_NAO_EXIGE` por
    omissão (cláusula pétrea #4: "ausência de evidência não vira
    False")."""

    cliente_id: str
    tipo_documental: str
    estado: EstadoConfiguracaoRequisito
    evidencia: str = ''

    def __post_init__(self) -> None:
        if self.tipo_documental not in TIPOS_DOCUMENTAIS_CANONICOS:
            raise ValueError(f'tipo_documental fora do universo canonico: {self.tipo_documental!r}')
        if self.estado == EstadoConfiguracaoRequisito.NAO_CONFIGURADO:
            raise ValueError(
                'NAO_CONFIGURADO nunca e uma entrada explicita -- e a ausencia de entrada; '
                'nao adicione uma linha so para dizer "nao configurado"'
            )
        if not self.evidencia.strip():
            raise ValueError('configuracao explicita (EXIGE/NAO_EXIGE) exige evidencia citada')


@dataclasses.dataclass(frozen=True)
class CadastroRequisitosPrestacao:
    versao: str
    requisitos_base: Tuple[RequisitoCanonico, ...]
    condicionais: Tuple[ConfiguracaoCondicionalCliente, ...] = ()

    def __post_init__(self) -> None:
        if not self.versao.strip():
            raise ValueError('versao deve ser texto nao vazio')
        chaves = [(c.cliente_id, c.tipo_documental) for c in self.condicionais]
        if len(chaves) != len(set(chaves)):
            raise ValueError('cadastro nao pode repetir (cliente_id, tipo_documental) nos condicionais')

    def requisitos_base_documentais(self) -> Tuple[RequisitoDocumentalPrestacao, ...]:
        """Converte a base canônica para o contrato já consumido por
        `PoliticaRequisitosPrestacao`/`executar_ciclo_prestacao` --
        nunca um DTO novo, só a tradução de forma."""
        return tuple(
            RequisitoDocumentalPrestacao(r.tipo_documental, r.quantidade_minima)
            for r in self.requisitos_base
        )

    def registros_condicionais_para(self, cliente_id: str) -> Tuple[RegistroRequisitoExterno, ...]:
        """Requisitos ADICIONAIS explicitamente configurados como
        EXIGE para este cliente -- nunca inclui a base (isso é sempre
        universal, aplicado por `PoliticaRequisitosPrestacao.
        requisitos_base`)."""
        return tuple(
            RegistroRequisitoExterno(c.tipo_documental)
            for c in self.condicionais
            if c.cliente_id == cliente_id and c.estado == EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE
        )

    def estado_condicional(self, cliente_id: str, tipo_documental: str) -> EstadoConfiguracaoRequisito:
        for c in self.condicionais:
            if c.cliente_id == cliente_id and c.tipo_documental == tipo_documental:
                return c.estado
        return EstadoConfiguracaoRequisito.NAO_CONFIGURADO

    def tipos_nao_configurados_para(self, cliente_id: str, tipos_de_interesse: Tuple[str, ...]) -> Tuple[str, ...]:
        """Para uma lista de tipos "de interesse" (ex.: os
        divergentes/condicionais conhecidos), devolve quais continuam
        `NAO_CONFIGURADO` para este cliente -- nunca confundido com
        "faltando" (Fase 13: os dois nunca aparecem juntos em
        `tipos_faltantes`)."""
        return tuple(
            tipo for tipo in tipos_de_interesse
            if self.estado_condicional(cliente_id, tipo) == EstadoConfiguracaoRequisito.NAO_CONFIGURADO
        )


class FonteRequisitosPrestacaoCanonica:
    """Implementa `FonteRequisitosPrestacao` (Protocol, PR #98) sobre
    o cadastro declarativo -- o MESMO `executar_ciclo_prestacao` do PR
    #98 funciona com esta fonte sem nenhuma fixture artificial e sem
    Airtable live (Fase 6)."""

    def __init__(self, cadastro: CadastroRequisitosPrestacao):
        self._cadastro = cadastro

    def registros_para(self, cliente, contexto) -> Tuple[RegistroRequisitoExterno, ...]:
        return self._cadastro.registros_condicionais_para(cliente.entidade_id)

    def requisitos_nao_configurados_para(self, cliente, contexto, tipos_de_interesse: Tuple[str, ...]) -> Tuple[str, ...]:
        """Extensão OPCIONAL (duck-typed, nunca parte obrigatória do
        Protocol `FonteRequisitosPrestacao` -- uma fonte que não a
        implementa simplesmente não produz esta informação extra, ver
        `ciclo_prestacao.py`)."""
        return self._cadastro.tipos_nao_configurados_para(cliente.entidade_id, tipos_de_interesse)


# ============================================================================
# CADASTRO REAL v1 -- só linhas com evidência citável (Fase 3).
# ============================================================================

REQUISITOS_BASE_CANONICOS_V1: Tuple[RequisitoCanonico, ...] = (
    RequisitoCanonico(
        'FGTS',
        evidencia='app.py::CAPACIDADES_DOCUMENTO["FGTS"] + '
                  'politica_requisitos_prestacao.REQUISITOS_BASE_PRESTACAO (ambas fontes concordam)',
    ),
    RequisitoCanonico(
        'DCTFWeb - Declaração',
        evidencia='app.py::CAPACIDADES_DOCUMENTO["DCTFWeb - Declaração"] + REQUISITOS_BASE_PRESTACAO (ambas concordam)',
    ),
    RequisitoCanonico(
        'DCTFWeb - Recibo de Entrega',
        evidencia='app.py::CAPACIDADES_DOCUMENTO["DCTFWeb - Recibo de Entrega"] + REQUISITOS_BASE_PRESTACAO (ambas concordam)',
    ),
    RequisitoCanonico(
        'Extrato da Folha de Pagamento',
        evidencia='app.py::CAPACIDADES_DOCUMENTO["Extrato da Folha de Pagamento"] + '
                  'REQUISITOS_BASE_PRESTACAO["extrato_cliente"] (tradução de vocabulário, ambas concordam)',
    ),
)

# Documentado em UMA fonte canônica só cada -- registrado, NUNCA
# incluído na base universal (Fase 3: "usar a regra mais conservadora
# somente se isso não inventar obrigação; caso contrário NAO_
# CONFIGURADO"). Disponível para `ConfiguracaoCondicionalCliente`
# explícita quando um humano confirmar para um cliente real.
REQUISITOS_DIVERGENTES_ENTRE_FONTES: Tuple[Tuple[str, str], ...] = (
    ('Holerite', 'CAPACIDADES_DOCUMENTO (app.py) inclui; REQUISITOS_BASE_PRESTACAO nao inclui'),
    ('Guia DCTFWeb/DARF', 'REQUISITOS_BASE_PRESTACAO inclui; CAPACIDADES_DOCUMENTO (app.py) nao inclui'),
)

# Nenhuma evidência de "cliente X exige benefício Y" foi encontrada no
# repositório (app.py::CAPACIDADES_BENEFICIOS documenta RECONHECIMENTO,
# nunca OBRIGATORIEDADE -- ver decisão registrada no ADR desta missão).
# Cadastro v1 começa SEM NENHUM cliente configurado -- estrutura pronta
# (`ConfiguracaoCondicionalCliente`), zero linhas inventadas.
CADASTRO_REQUISITOS_PRESTACAO_V1 = CadastroRequisitosPrestacao(
    versao='1', requisitos_base=REQUISITOS_BASE_CANONICOS_V1, condicionais=(),
)
