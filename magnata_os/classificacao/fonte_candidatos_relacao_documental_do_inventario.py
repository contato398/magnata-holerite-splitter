"""Fonte REAL (composição, nunca um motor novo) de candidatos para
relação Documento↔Documento (missão "MESCLAR PR #107 + CONSTRUIR OS
DOIS ADAPTERS REAIS QUE BLOQUEIAM A PRIMEIRA VALIDAÇÃO LIVE —
FonteUnidadePostoPrestacao + FonteCandidatosRelacaoDocumental").

Construída sobre 2 Protocols JÁ REAIS e já auditados (nunca uma tabela
Airtable nova, nunca um acesso direto, nunca uma suposição de schema
não confirmada):

  - `FonteClientesPrestacao.listar_ativos` (clientes ativos do ciclo --
    já tem adapter real de produção, `airtable_clientes_prestacao.py`);
  - `FonteInventarioPrestacao.listar` (itens já resolvidos por
    cliente+competência -- já tem adapters reais de produção,
    `airtable_inventario_prestacao.py`/`airtable_holerites_
    prestacao.py`, compostos por `fonte_inventario_composta.
    FonteInventarioPrestacaoComposta`).

Descoberta de candidato (`documento_id`/`tipo_documental`/
`referencias_logicas`) é 100% REAL a partir destes dois Protocols já
existentes -- este módulo só varre "todo cliente ativo × inventário
daquele cliente na competência pedida", filtra por tipo_documental e
deduplica por `documento_id` (um mesmo documento pode aparecer em
múltiplos clientes -- vínculo múltiplo genuíno -- nesse caso as
referências lógicas são UNIDAS, nunca tratadas como candidatos
distintos).

PENDÊNCIA HONESTA, NUNCA ESCONDIDA -- `dados_correlacao`: o inventário
NUNCA carrega identificador de pedido/valor total/etc. (nem deveria:
`ItemInventarioPrestacao` nunca carrega PDF/texto bruto, por desenho).
Esses dados só existem no momento em que o documento é processado
(extraídos do próprio texto,
`relacao_documental.extrair_dados_correlacao_de_texto`) -- e hoje não
são persistidos em lugar nenhum para consulta posterior; não existe
"banco de correlação" de produção. Este módulo expõe essa dependência
como um Protocol PRÓPRIO e nomeado (`FonteDadosCorrelacaoDocumental`),
nunca fabrica o dado que falta: sem uma implementação real desse
Protocol (que exigiria um armazenamento durável -- fora do escopo
desta missão, "não criar banco paralelo sem necessidade comprovada"
combinado com "mudança arquitetural grande fora do escopo" -- gate
humano, não decisão técnica local), um candidato descoberto aqui
simplesmente não carrega `dados_correlacao` (fica com os defaults
vazios do dataclass) -- a resolução de relação correspondente cai
honestamente em `NAO_ENCONTRADA`, nunca finge ter evidência que não
tem. `FonteDadosCorrelacaoEmMemoria` (abaixo) é uma referência local/
piloto -- mesmo padrão de `InventarioPrestacaoEmMemoria` -- nunca a
fonte de registro de produção."""
from __future__ import annotations

import dataclasses
from typing import Dict, Optional, Protocol, Tuple

from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica
from .fonte_candidatos_relacao_documental import CandidatoRelacaoDocumental
from .fonte_clientes_prestacao import FonteClientesPrestacao
from .inventario_prestacao import FonteInventarioPrestacao
from .relacao_documental import DadosCorrelacaoDocumental, TipoRelacaoDocumental


class FonteDadosCorrelacaoDocumental(Protocol):
    """Porta para os dados de correlação JÁ EXTRAÍDOS de um documento
    específico, por `documento_id` -- nunca extrai texto aqui (mesmo
    princípio de `relacao_documental.py`: "se o motor precisar do
    conteúdo, usar a extração/corredor existente, nunca criar uma
    segunda"). `None` quando não há dado registrado para este
    `documento_id` -- nunca inventado."""

    def obter_dados_correlacao(self, documento_id: str) -> Optional[DadosCorrelacaoDocumental]: ...


class FonteDadosCorrelacaoEmMemoria:
    """Referência local/piloto (mesmo padrão de `InventarioPrestacaoEm
    Memoria`) -- NUNCA a fonte de registro de produção (ver docstring
    do módulo). Um dict simples `documento_id -> DadosCorrelacao
    Documental`, escrito por quem já processou o documento e quer
    disponibilizar seus dados de correlação para descoberta de
    candidato depois."""

    def __init__(self) -> None:
        self._dados: Dict[str, DadosCorrelacaoDocumental] = {}

    def registrar(self, documento_id: str, dados: DadosCorrelacaoDocumental) -> None:
        self._dados[documento_id] = dados

    def obter_dados_correlacao(self, documento_id: str) -> Optional[DadosCorrelacaoDocumental]:
        return self._dados.get(documento_id)


class FonteCandidatosRelacaoDocumentalDoInventario:
    """Implementa `FonteCandidatosRelacaoDocumental`
    (`fonte_candidatos_relacao_documental.py`) -- REAL para descoberta
    de identidade (composição de 2 Protocols já auditados, cada um já
    com adapter de produção); depende de uma `FonteDadosCorrelacao
    Documental` injetada para os dados de correlação (ver docstring do
    módulo -- pendência nomeada, nunca escondida)."""

    def __init__(
        self,
        fonte_clientes: FonteClientesPrestacao,
        fonte_inventario: FonteInventarioPrestacao,
        fonte_dados_correlacao: FonteDadosCorrelacaoDocumental,
        contexto_ciclo: ContextoCicloPrestacao,
    ):
        self._fonte_clientes = fonte_clientes
        self._fonte_inventario = fonte_inventario
        self._fonte_dados_correlacao = fonte_dados_correlacao
        self._contexto_ciclo = contexto_ciclo

    def candidatos_para_relacao(
        self,
        documento_id_atual: str,
        tipo_documental_atual: str,
        tipo_documental_candidato: str,
        competencia: Tuple[int, int],
        tipo_relacao: TipoRelacaoDocumental,
    ) -> Tuple[CandidatoRelacaoDocumental, ...]:
        ano, mes = competencia
        competencia_ref = ReferenciaCanonica('COMPETENCIA', f'{ano:04d}-{mes:02d}')
        clientes = self._fonte_clientes.listar_ativos(self._contexto_ciclo)

        candidatos_por_documento: Dict[str, CandidatoRelacaoDocumental] = {}
        for cliente in clientes:
            for item in self._fonte_inventario.listar(cliente, competencia_ref):
                if item.tipo_documental != tipo_documental_candidato:
                    continue
                if item.documento_id == documento_id_atual:
                    continue
                if item.documento_id in candidatos_por_documento:
                    # Mesmo documento_id em outro cliente (vínculo
                    # múltiplo genuíno) -- UNE as referências lógicas,
                    # nunca trata como candidatos distintos.
                    existente = candidatos_por_documento[item.documento_id]
                    novas_referencias = tuple(sorted(
                        set(existente.referencias_logicas) | {item.cliente}, key=lambda r: r.entidade_id,
                    ))
                    candidatos_por_documento[item.documento_id] = dataclasses.replace(
                        existente, referencias_logicas=novas_referencias,
                    )
                    continue
                dados = self._fonte_dados_correlacao.obter_dados_correlacao(item.documento_id)
                candidatos_por_documento[item.documento_id] = CandidatoRelacaoDocumental(
                    documento_id=item.documento_id, tipo_documental=item.tipo_documental,
                    dados_correlacao=dados if dados is not None else DadosCorrelacaoDocumental(),
                    referencias_logicas=(item.cliente,), proveniencia='inventario_prestacao',
                )
        return tuple(candidatos_por_documento[documento_id] for documento_id in sorted(candidatos_por_documento))
