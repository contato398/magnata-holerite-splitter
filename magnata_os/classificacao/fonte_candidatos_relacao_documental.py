"""Fonte GENÉRICA de candidatos para relação semântica Documento↔
Documento (missão "CORRIGIR METADADOS + MERGE PR #106 + COSTURA
AUTOMÁTICA DE RELAÇÃO DOCUMENTO↔DOCUMENTO NO CORREDOR V1").

Fecha o gap final registrado no PR #106: a capacidade de RESOLVER uma
relação (`relacao_documental.py`) já existia, mas nada no corredor
sabia "quais documentos considerar como candidatos". Este módulo é SÓ
a porta -- nunca decide a relação em si (isso continua exclusivamente
em `relacao_documental.resolver_relacao_documental_dentre_candidatos`,
nunca reavaliado aqui, §3 da missão).

PROIBIDO (explícito da missão, §2): `FonteComprovanteIfood`,
`FontePedidosVR`, `RepositorioFGTSComprovantes` ou qualquer fonte por
família/fornecedor -- esta é a ÚNICA porta, genérica, para QUALQUER
par de tipos.

Candidato NUNCA carrega PDF bruto, texto bruto, CPF, nome ou segredo
(§4) -- só o necessário: `documento_id`, `tipo_documental` já
resolvido, `dados_correlacao` JÁ EXTRAÍDOS
(`relacao_documental.DadosCorrelacaoDocumental` -- nunca uma segunda
extração de texto aqui, reaproveita o corredor/extração já existente),
`referencias_logicas` (as referências -- tipicamente clientes -- já
resolvidas PARA O PRÓPRIO CANDIDATO, quando ele já foi processado
normalmente pelo corredor) e proveniência sanitizada."""
from __future__ import annotations

import dataclasses
from typing import Optional, Protocol, Tuple

from .contratos import ReferenciaCanonica
from .relacao_documental import DadosCorrelacaoDocumental, TipoRelacaoDocumental


@dataclasses.dataclass(frozen=True)
class CandidatoRelacaoDocumental:
    """Um candidato SANITIZADO ao lado VARIÁVEL de uma relação -- nunca
    a relação em si (§3: "candidato não é relação"). Formulação
    neutra de propósito (corrigida na revisão final pré-merge ao PR
    #107): dependendo de qual documento já está fixo em mãos de quem
    resolve, o candidato pode disputar `documento_a_id` (relatante,
    caso mais comum no corredor -- um comprovante fixo procurando o
    relatório/guia que ele comprova) OU `documento_b_id` (comprovante,
    uso de `resolver_relacao_documental_dentre_candidatos`). Este
    dataclass nunca sabe qual dos dois -- só quem chama
    `resolver_relacao_documental_dentre_candidatos`/`resolver_relacao_
    documental_para_comprovante_dentre_candidatos` decide isso."""

    documento_id: str
    tipo_documental: str
    dados_correlacao: DadosCorrelacaoDocumental = dataclasses.field(default_factory=DadosCorrelacaoDocumental)
    referencias_logicas: Tuple[ReferenciaCanonica, ...] = ()
    """Referências (tipicamente `CLIENTE`) já resolvidas para ESTE
    candidato, quando ele mesmo já passou pelo corredor normal (ex.: um
    Relatório de Benefícios já resolvido carrega os clientes de todos
    os colaboradores que contém). Vazio quando o candidato não tem
    (ou ainda não tem) nenhuma referência própria resolvida -- nunca
    inventado aqui."""
    proveniencia: Optional[str] = None
    """Código sanitizado de auditoria (ex.: 'inventario_memoria',
    'lote_ingestao') -- nunca um detalhe de schema/tabela externa."""

    def __post_init__(self) -> None:
        if not self.documento_id or not self.documento_id.strip():
            raise ValueError('documento_id deve ser texto nao vazio')
        if not self.tipo_documental or not self.tipo_documental.strip():
            raise ValueError('tipo_documental deve ser texto nao vazio')


class FonteCandidatosRelacaoDocumental(Protocol):
    """Fonte substituível (Protocol duck-typed, mesmo padrão de
    `FonteVinculoPrestacao`/`FonteUnidadePostoPrestacao`) -- nunca
    Airtable direto no core."""

    def candidatos_para_relacao(
        self,
        documento_id_atual: str,
        tipo_documental_atual: str,
        tipo_documental_candidato: str,
        competencia: Tuple[int, int],
        tipo_relacao: TipoRelacaoDocumental,
    ) -> Tuple[CandidatoRelacaoDocumental, ...]: ...


def resolver_candidatos_validado(
    fonte: FonteCandidatosRelacaoDocumental,
    documento_id_atual: str,
    tipo_documental_atual: str,
    tipo_documental_candidato: str,
    competencia: Tuple[int, int],
    tipo_relacao: TipoRelacaoDocumental,
) -> Tuple[CandidatoRelacaoDocumental, ...]:
    """Executa a porta e valida só as invariantes estruturais -- mesmo
    padrão de `vinculo_unidade_prestacao.resolver_vinculo_validado`,
    nunca duplicado."""
    if not documento_id_atual or not documento_id_atual.strip():
        raise ValueError('documento_id_atual deve ser texto nao vazio')
    if not tipo_documental_candidato or not tipo_documental_candidato.strip():
        raise ValueError('tipo_documental_candidato deve ser texto nao vazio')

    candidatos = fonte.candidatos_para_relacao(
        documento_id_atual, tipo_documental_atual, tipo_documental_candidato, competencia, tipo_relacao,
    )
    if any(candidato.documento_id == documento_id_atual for candidato in candidatos):
        raise ValueError('fonte de candidatos nunca pode devolver o proprio documento atual como candidato')
    if any(candidato.tipo_documental != tipo_documental_candidato for candidato in candidatos):
        raise ValueError('fonte de candidatos devolveu tipo_documental fora do tipo pedido')
    if any(
        candidato.dados_correlacao.competencia not in (None, competencia) for candidato in candidatos
    ):
        raise ValueError('fonte de candidatos devolveu candidato de competencia diferente da pedida')
    return candidatos


class FonteCandidatosRelacaoDocumentalComposta:
    """Agrega N fontes já existentes do MESMO Protocol (mesmo padrão de
    `fonte_inventario_composta.FonteInventarioPrestacaoComposta`) --
    nunca reimplementa busca por família. Todas as fontes autorizadas
    são consultadas (união, deduplicada por `documento_id`) antes de
    devolver `NAO_ENCONTRADA` -- "não mandar para humano antes de
    esgotar fontes já autorizadas" (§12 da missão). Fontes LIVE
    (Airtable/Gmail) não são compostas aqui -- essa composição usa
    `estrategia_aquisicao_documental.py`, fora do escopo desta missão
    (§26: nenhum acesso live nesta missão)."""

    def __init__(self, fontes: Tuple[FonteCandidatosRelacaoDocumental, ...]):
        self._fontes = tuple(fontes)

    def candidatos_para_relacao(
        self,
        documento_id_atual: str,
        tipo_documental_atual: str,
        tipo_documental_candidato: str,
        competencia: Tuple[int, int],
        tipo_relacao: TipoRelacaoDocumental,
    ) -> Tuple[CandidatoRelacaoDocumental, ...]:
        vistos: dict = {}
        for fonte in self._fontes:
            for candidato in fonte.candidatos_para_relacao(
                documento_id_atual, tipo_documental_atual, tipo_documental_candidato, competencia, tipo_relacao,
            ):
                if candidato.documento_id not in vistos:
                    vistos[candidato.documento_id] = candidato
        return tuple(vistos[documento_id] for documento_id in sorted(vistos))
