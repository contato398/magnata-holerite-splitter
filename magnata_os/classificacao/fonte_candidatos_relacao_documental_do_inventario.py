"""Fonte REAL (composição, nunca um motor novo) de candidatos para
relação Documento↔Documento (missão "MESCLAR PR #107 + CONSTRUIR OS
DOIS ADAPTERS REAIS QUE BLOQUEIAM A PRIMEIRA VALIDAÇÃO LIVE —
FonteUnidadePostoPrestacao + FonteCandidatosRelacaoDocumental";
corrigido pelo "ADENDO PRÉ-MERGE — PR #108 — ESCOPO HISTÓRICO DE
CANDIDATOS + AUSÊNCIA EXPLÍCITA DE DADOS DE CORRELAÇÃO").

Construída sobre Protocols JÁ REAIS e já auditados (nunca uma tabela
Airtable nova, nunca um acesso direto, nunca uma suposição de schema
não confirmada):

  - `FonteEscopoClientesPrestacao.escopo_para_competencia` (o conjunto
    de clientes a considerar para UMA competência específica --
    Protocol novo, ver seção "CORREÇÃO" abaixo);
  - `FonteInventarioPrestacao.listar` (itens já resolvidos por
    cliente+competência -- já tem adapters reais de produção,
    `airtable_inventario_prestacao.py`/`airtable_holerites_
    prestacao.py`, compostos por `fonte_inventario_composta.
    FonteInventarioPrestacaoComposta`).

Descoberta de candidato (`documento_id`/`tipo_documental`/
`referencias_logicas`) é 100% REAL a partir destes Protocols já
existentes -- este módulo só varre "todo cliente do escopo × inventário
daquele cliente na competência pedida", filtra por tipo_documental e
deduplica por `documento_id` (um mesmo documento pode aparecer em
múltiplos clientes -- vínculo múltiplo genuíno -- nesse caso as
referências lógicas são UNIDAS, nunca tratadas como candidatos
distintos).

CORREÇÃO (adendo pré-merge ao PR #108, achado real): a primeira versão
deste módulo usava `FonteClientesPrestacao.listar_ativos` (clientes
ATIVOS HOJE) como o universo de busca para QUALQUER competência --
isso perde, silenciosamente, um documento legítimo de um cliente que
era ativo NA COMPETÊNCIA pedida mas está inativo hoje. "Ativo hoje" e
"aplicável historicamente" são conceitos DIFERENTES (§10 do adendo).

Auditoria (§8/§9 do adendo): nenhuma fonte real já existente no
repositório enumera "clientes presentes no inventário de uma
competência" independente de atividade atual -- confirmado por
inspeção de `fonte_inventario_composta.py`/adapters de inventário
(todos exigem um `cliente` já conhecido como parâmetro de entrada).
Criar essa enumeração de verdade contra o Airtable real exigiria
conhecimento de schema não auditado nesta missão -- não fabricado.

Solução adotada (Opção C do adendo, §9: "receber o conjunto de
clientes candidatos do contexto de execução, se esse conjunto tiver
origem temporal comprovada"): o universo de clientes passa a ser um
Protocol PRÓPRIO e explícito, `FonteEscopoClientesPrestacao`, resolvido
POR COMPETÊNCIA (nunca fixo, nunca amarrado a "hoje"). `EscopoClientes
AtivosDoCiclo` (abaixo) é uma implementação de referência que usa
`FonteClientesPrestacao.listar_ativos` -- documentada como válida
SOMENTE quando a competência pedida é a corrente do próprio ciclo
(§10: "para ciclo corrente, clientes ativos podem ser um pré-filtro
operacional válido"); nunca use para competência histórica.
`EscopoClientesFixo` é a alternativa para quando quem chama já tem um
conjunto de clientes com proveniência temporal real (ex.: um registro
histórico específico) -- estruturalmente vinculado a UMA competência
comprovada (`competencia_comprovada` no construtor, nunca "fixo" como
sinônimo de "válido para qualquer competência"); decisão de quem
compõe o corredor, nunca inferida aqui.

PENDÊNCIA HONESTA, NUNCA ESCONDIDA -- `dados_correlacao`: o inventário
NUNCA carrega identificador de pedido/valor total/etc. (nem deveria:
`ItemInventarioPrestacao` nunca carrega PDF/texto bruto, por desenho).
Esses dados só existem no momento em que o documento é processado
(extraídos do próprio texto,
`relacao_documental.extrair_dados_correlacao_de_texto`) -- e hoje não
são persistidos em lugar nenhum para consulta posterior; não existe
"banco de correlação" de produção. Este módulo expõe essa dependência
como um Protocol PRÓPRIO e nomeado (`FonteDadosCorrelacaoDocumental`),
`Optional` no construtor (adendo §12: "não exigir que produção injete
um fake/in-memory apenas para representar 'não existe dado'") -- sem
fonte injetada (`None`, o default), ou sem dado registrado para um
`documento_id`, o candidato existe (identidade é real) mas
`dados_correlacao` fica com os defaults vazios do dataclass -- a
resolução de relação correspondente cai honestamente em
`NAO_ENCONTRADA`, nunca finge ter evidência que não tem.
`FonteDadosCorrelacaoEmMemoria` (abaixo) é uma referência local/piloto
-- mesmo padrão de `InventarioPrestacaoEmMemoria` -- nunca a fonte de
registro de produção."""
from __future__ import annotations

import dataclasses
from typing import Dict, Optional, Protocol, Tuple

from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica
from .fonte_candidatos_relacao_documental import CandidatoRelacaoDocumental
from .fonte_clientes_prestacao import FonteClientesPrestacao
from .inventario_prestacao import FonteInventarioPrestacao
from .relacao_documental import DadosCorrelacaoDocumental, TipoRelacaoDocumental


class FonteEscopoClientesPrestacao(Protocol):
    """Porta para o CONJUNTO de clientes a considerar como escopo de
    busca PARA UMA COMPETÊNCIA -- nunca "clientes ativos hoje" como
    universo implícito para qualquer competência (§7/§10 do adendo:
    "ativo hoje" não equivale a "aplicável historicamente"). Quem
    implementa decide a origem e a responsabilidade de prová-la
    temporalmente correta -- este módulo nunca infere isso sozinho."""

    def escopo_para_competencia(self, competencia: ReferenciaCanonica) -> Tuple[ReferenciaCanonica, ...]: ...


class EscopoClientesAtivosDoCiclo:
    """Implementação de referência sobre `FonteClientesPrestacao.
    listar_ativos` (já real, já com adapter de produção) -- válida
    SOMENTE quando a competência pedida é a competência CORRENTE do
    próprio `contexto_ciclo` (pré-filtro operacional aceitável para o
    ciclo em processamento agora, §10 do adendo). NUNCA usar para
    competência histórica -- `escopo_para_competencia` devolve `()`
    (vazio, nunca uma lista potencialmente errada) quando a competência
    pedida diverge da competência corrente do ciclo."""

    def __init__(self, fonte_clientes: FonteClientesPrestacao, contexto_ciclo: ContextoCicloPrestacao):
        self._fonte_clientes = fonte_clientes
        self._contexto_ciclo = contexto_ciclo
        ano, mes = contexto_ciclo.competencia_base
        self._competencia_corrente_id = f'{ano:04d}-{mes:02d}'

    def escopo_para_competencia(self, competencia: ReferenciaCanonica) -> Tuple[ReferenciaCanonica, ...]:
        if competencia.entidade_id != self._competencia_corrente_id:
            return ()
        return self._fonte_clientes.listar_ativos(self._contexto_ciclo)


class EscopoClientesFixo:
    """Implementação de referência para quando quem chama já tem um
    conjunto de clientes com proveniência temporal REAL (ex.: um
    registro histórico específico, já resolvido fora deste módulo) --
    nunca "ativos hoje" travestido de histórico.

    CORREÇÃO (adendo pré-merge final ao PR #108, achado real): a versão
    anterior devolvia o MESMO escopo para QUALQUER competência
    perguntada, deixando IMPLÍCITA (só em docstring, nunca no contrato)
    a afirmação "este conjunto é válido para qualquer competência" --
    exatamente o mesmo erro já corrigido em `FonteUnidadePostoPrestacao
    AirtableShadow` (competência consultada != vigência comprovada da
    fonte), agora corrigido aqui também: `competencia_comprovada` é
    parte do CONSTRUTOR (`ReferenciaCanonica('COMPETENCIA', ...)`,
    mesmo tipo já usado em toda parte do repositório para competência --
    nunca uma tupla solta) -- a vigência fica estrutural, nunca
    dependente de comentário. `escopo_para_competencia` só devolve os
    clientes quando a competência pedida é EXATAMENTE a comprovada;
    para qualquer outra, devolve `()` -- nunca reutiliza silenciosamente
    o mesmo escopo histórico em outro mês."""

    def __init__(self, competencia_comprovada: ReferenciaCanonica, clientes: Tuple[ReferenciaCanonica, ...]):
        if competencia_comprovada.tipo_entidade != 'COMPETENCIA':
            raise ValueError('competencia_comprovada deve ser referencia canonica de COMPETENCIA')
        self._competencia_comprovada = competencia_comprovada
        self._clientes = clientes

    def escopo_para_competencia(self, competencia: ReferenciaCanonica) -> Tuple[ReferenciaCanonica, ...]:
        if competencia != self._competencia_comprovada:
            return ()
        return self._clientes


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
    de identidade (composição de Protocols já auditados, cada um já com
    adapter de produção ou implementação de referência documentada);
    `fonte_dados_correlacao` é OPCIONAL (ver docstring do módulo --
    pendência nomeada, nunca escondida, nunca exigida como fake
    obrigatório)."""

    def __init__(
        self,
        fonte_escopo_clientes: FonteEscopoClientesPrestacao,
        fonte_inventario: FonteInventarioPrestacao,
        fonte_dados_correlacao: Optional[FonteDadosCorrelacaoDocumental] = None,
    ):
        self._fonte_escopo_clientes = fonte_escopo_clientes
        self._fonte_inventario = fonte_inventario
        self._fonte_dados_correlacao = fonte_dados_correlacao

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
        clientes = self._fonte_escopo_clientes.escopo_para_competencia(competencia_ref)

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
                dados = (
                    self._fonte_dados_correlacao.obter_dados_correlacao(item.documento_id)
                    if self._fonte_dados_correlacao is not None else None
                )
                candidatos_por_documento[item.documento_id] = CandidatoRelacaoDocumental(
                    documento_id=item.documento_id, tipo_documental=item.tipo_documental,
                    dados_correlacao=dados if dados is not None else DadosCorrelacaoDocumental(),
                    referencias_logicas=(item.cliente,), proveniencia='inventario_prestacao',
                )
        return tuple(candidatos_por_documento[documento_id] for documento_id in sorted(candidatos_por_documento))
