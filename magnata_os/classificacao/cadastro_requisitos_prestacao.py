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

ADENDO DE REGRA DE NEGÓCIO — HOLERITE (2026-08-30, confirmado pelo
negócio numa mensagem distinta, corrigindo o registro original desta
missão): "HOLERITE É OBRIGATÓRIO EM TODA PRESTAÇÃO DE CONTAS" —
substitui o tratamento anterior de Holerite como item divergente/
NAO_CONFIGURADO. Holerite É base universal, mas NUNCA avaliado pela
contagem plana de `REQUISITOS_BASE_CANONICOS_V1` (o próprio adendo:
"não basta verificar presença do tipo Holerite no inventário") —
preserva granularidade COLABORADOR, avaliado por CARDINALIDADE
(`holerite_obrigatorio_prestacao.avaliar_obrigatoriedade_holerite`:
cliente → colaboradores esperados → 1 Holerite por colaborador
aplicável). Ver `HOLERITE_TIPO_DOCUMENTAL`/`HOLERITE_EVIDENCIA` abaixo.

DIVERGÊNCIA REMANESCENTE EM V1 (só numa fonte): Guia DCTFWeb/DARF (só em
`REQUISITOS_BASE_PRESTACAO`) — registrado em
`REQUISITOS_DIVERGENTES_ENTRE_FONTES` (V1).

CADASTRO V2 (missão "FECHAMENTO DA BASE CANÔNICA + PREPARAÇÃO DO
PRIMEIRO CICLO PILOTO REAL READ-ONLY", 2026-08-30) — V1 permanece
intacto (histórico, nunca sobrescrito); V2 é o cadastro EFETIVO a
partir desta missão, com 2 decisões de negócio novas, cada uma
confirmada pelo humano numa mensagem distinta:
  1) Guia DCTFWeb/DARF PROMOVIDO à base universal (sai de
     `REQUISITOS_DIVERGENTES_ENTRE_FONTES`, entra em
     `REQUISITOS_BASE_CANONICOS_V2`).
  2) Holerite REVERTIDO de "base universal avaliada por cardinalidade
     para todo cliente" (Adendo, vigente em V1) para "tipo_documental
     CONDICIONAL, avaliado por cardinalidade só quando o cliente tiver
     `ConfiguracaoCondicionalCliente(..., CONFIGURADO_EXIGE)` explícita
     para Holerite" — nunca voltou a ser base universal (nunca esteve
     em `REQUISITOS_BASE_CANONICOS_V1`/`V2`), só deixou de ser
     avaliado incondicionalmente para todo cliente. Ver seção "CADASTRO
     V2" mais abaixo neste arquivo para o detalhe completo."""
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

# Holerite -- PROMOVIDO a requisito UNIVERSAL por decisão de negócio
# explícita (Adendo de Regra de Negócio -- Holerite, 2026-08-30).
# NUNCA em `REQUISITOS_BASE_CANONICOS_V1` (contagem plana, insuficiente
# para Holerite por decisão do próprio adendo) -- avaliado à parte, por
# CARDINALIDADE colaborador (`holerite_obrigatorio_prestacao.py`).
HOLERITE_TIPO_DOCUMENTAL = 'Holerite'
HOLERITE_EVIDENCIA = (
    'Adendo de Regra de Negócio -- Holerite (confirmado pelo negócio, '
    '2026-08-30, mensagem distinta): "HOLERITE E OBRIGATORIO EM TODA '
    'PRESTACAO DE CONTAS" -- substitui o registro divergente anterior '
    'desta missao. Granularidade COLABORADOR preservada; nunca avaliado '
    'pela contagem plana de REQUISITOS_BASE_CANONICOS_V1.'
)

# Documentado em UMA fonte canônica só -- registrado, NUNCA incluído na
# base universal (Fase 3: "usar a regra mais conservadora somente se
# isso não inventar obrigação; caso contrário NAO_CONFIGURADO").
# Disponível para `ConfiguracaoCondicionalCliente` explícita quando um
# humano confirmar para um cliente real.
REQUISITOS_DIVERGENTES_ENTRE_FONTES: Tuple[Tuple[str, str], ...] = (
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

# ============================================================================
# CADASTRO V2 -- missão "FECHAMENTO DA BASE CANÔNICA + PREPARAÇÃO DO
# PRIMEIRO CICLO PILOTO REAL READ-ONLY" (2026-08-30).
#
# V1 (acima) NUNCA é sobrescrito em silêncio -- permanece intacto como
# registro histórico do que foi decidido na missão anterior. V2 é uma
# versão NOVA e EXPLÍCITA, com 2 decisões de negócio confirmadas pelo
# humano numa mensagem distinta desta mesma sessão:
#
#   1) Guia DCTFWeb/DARF é documento comum/base -- PROMOVIDO de
#      `REQUISITOS_DIVERGENTES_ENTRE_FONTES` (V1) para a base universal
#      em V2. Reverte, só para este tipo, a cautela da Fase 3 original
#      ("só interseção das 2 fontes vira base") -- o humano confirmou
#      que a fonte `REQUISITOS_BASE_PRESTACAO` já é suficiente aqui,
#      mesmo sem `CAPACIDADES_DOCUMENTO` (app.py) concordar.
#   2) Holerite NÃO é promovido a requisito universal -- REVERTE o
#      "Adendo de Regra de Negócio -- Holerite" (vigente em V1, também
#      confirmado numa mensagem distinta) por uma nova decisão do
#      negócio, também numa mensagem distinta: "Holerite é documento
#      individualizado por colaborador/cliente e deve ser exigido
#      conforme aplicabilidade/política do cliente/ciclo. Ausência de
#      configuração específica NÃO significa automaticamente que todo
#      cliente exige Holerite." Holerite JAMAIS esteve em
#      `REQUISITOS_BASE_CANONICOS_V1`/`V2` (isso não muda) -- o que
#      muda é que, a partir de V2, ele também deixa de ser avaliado
#      incondicionalmente para TODO cliente (como `ciclo_prestacao.py`
#      fazia sempre que uma fonte de colaboradores esperados era
#      informada). Holerite passa a ser um `tipo_documental`
#      CONDICIONAL como qualquer outro: só avaliado quando o cadastro
#      tiver uma `ConfiguracaoCondicionalCliente(tipo_documental=
#      HOLERITE_TIPO_DOCUMENTAL, estado=CONFIGURADO_EXIGE, ...)`
#      explícita para aquele cliente. O MECANISMO de avaliação por
#      cardinalidade colaborador (`holerite_obrigatorio_prestacao.
#      avaliar_obrigatoriedade_holerite`) não foi descartado -- continua
#      sendo o único jeito correto de avaliar Holerite quando ele
#      ESTIVER configurado (nunca a contagem plana); só passa a ser
#      acionado apenas nesse caso, nunca por padrão. O texto original do
#      adendo (`HOLERITE_EVIDENCIA` acima) fica preservado tal como
#      redigido -- registro histórico da decisão original, nunca
#      apagado (ver docs/decisoes/cadastro-canonico-requisitos-
#      prestacao-v1.md e a reversão registrada em docs/decisoes/
#      fechamento-base-canonica-ciclo-piloto-readonly-v1.md).
# ============================================================================

REQUISITOS_BASE_CANONICOS_V2: Tuple[RequisitoCanonico, ...] = REQUISITOS_BASE_CANONICOS_V1 + (
    RequisitoCanonico(
        'Guia DCTFWeb/DARF',
        evidencia='Decisao de negocio explicita (missao FECHAMENTO DA BASE CANONICA, '
                  '2026-08-30, confirmada pelo humano numa mensagem distinta): Guia '
                  'DCTFWeb/DARF e documento comum/base -- promovido de '
                  'REQUISITOS_DIVERGENTES_ENTRE_FONTES (V1) para a base universal em V2. '
                  'Documentado em politica_requisitos_prestacao.REQUISITOS_BASE_PRESTACAO; '
                  'a ausencia em app.py::CAPACIDADES_DOCUMENTO deixou de ser motivo '
                  'suficiente para excluir da base (decisao humana, nao inferencia automatica).',
    ),
)

# Em V2 não sobra nenhum item divergente entre as 2 fontes originais --
# a única divergência conhecida (Guia DCTFWeb/DARF) foi resolvida acima
# por decisão humana explícita. Mantida como tupla vazia TIPADA (nunca
# apagada) para que uma FUTURA divergência real seja registrada aqui,
# nunca inventada nem silenciosamente ignorada.
REQUISITOS_DIVERGENTES_ENTRE_FONTES_V2: Tuple[Tuple[str, str], ...] = ()

# Cadastro V2 -- mesma disciplina de V1: zero clientes condicionais
# inventados. Holerite e qualquer benefício (Horas Extras, Assiduidade,
# VR, VA, Diárias, Almoço/Janta, Assinatura) continuam disponíveis como
# `tipo_documental` para `ConfiguracaoCondicionalCliente` quando um
# humano confirmar para um cliente real -- nenhum foi configurado aqui.
CADASTRO_REQUISITOS_PRESTACAO_V2 = CadastroRequisitosPrestacao(
    versao='2', requisitos_base=REQUISITOS_BASE_CANONICOS_V2, condicionais=(),
)
