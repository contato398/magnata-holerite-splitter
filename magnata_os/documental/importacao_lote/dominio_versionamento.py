"""Núcleo puro de identidade lógica e versionamento de documento —
camada de ESCRITA (Fase 4), deliberadamente separada da classificação do
dry-run (`dominio.py`) — "não misturar matching/classificação novamente"
(macrocomando desta fase, §8).

Documento LÓGICO = tipo + competência + entidade, nunca o conteúdo do
PDF — isso é `hash_sha256`, que vive em `documentos` (conteúdo físico,
modulo01/dominio.py), nunca duplicado aqui. Nenhuma PII: só IDs já
resolvidos, mesma regra de `dominio.calcular_identidade_documental`.

Regra de pureza (magnata_os/CLAUDE.md): nada aqui faz I/O nem importa
driver de banco/Airtable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Sequence

from .contratos import TipoDocumental
from .contratos_execucao import VersionamentoLogico


def calcular_documento_logico_id(tipo: TipoDocumental, mes_cont_id: str, entidade_id: str) -> str:
    """Identidade lógica — SEM hash de conteúdo (ao contrário de
    `dominio.calcular_identidade_documental`, que inclui o hash e serve à
    detecção de duplicidade do dry-run). Duas versões físicas diferentes
    do "mesmo documento" (ex.: holerite corrigido) compartilham este
    mesmo `documento_logico_id` — é exatamente isso que torna possível
    modelar supersessão sem confundir com documento novo."""
    base = f'{tipo.value}|{mes_cont_id}|{entidade_id}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


class ResultadoVerificacaoVersao(str, Enum):
    PRIMEIRA_VERSAO = 'primeira_versao'
    MESMO_CONTEUDO_JA_REGISTRADO = 'mesmo_conteudo_ja_registrado'
    CONFLITO_HASH_DIFERENTE = 'conflito_hash_diferente'


@dataclass(frozen=True)
class DecisaoVersionamento:
    resultado: ResultadoVerificacaoVersao
    proxima_versao: Optional[int]
    versao_vigente_documento_id: Optional[str]


class GrafoVersionamentoInconsistente(Exception):
    """O conjunto de versões de um documento_logico_id não forma uma
    cadeia linear única (ciclo, mais de uma ponta solta, ou versões de
    mais de um documento_logico_id misturadas). Nunca decidido por
    aproximação — sempre levantado, nunca mascarado."""


def determinar_vigente(versoes: Sequence[VersionamentoLogico]) -> Optional[VersionamentoLogico]:
    """Vigente = a versão que nunca aparece como `substitui_documento_id`
    de nenhuma outra (a ponta da cadeia). `None` se `versoes` for vazio.
    Levanta GrafoVersionamentoInconsistente se as versões misturarem mais
    de um documento_logico_id, ou se não houver exatamente uma ponta —
    nunca escolhe "a mais recente por timestamp" como atalho, porque isso
    esconderia uma inconsistência real de dados."""
    if not versoes:
        return None

    logicos = {v.documento_logico_id for v in versoes}
    if len(logicos) > 1:
        raise GrafoVersionamentoInconsistente(
            f'determinar_vigente recebeu versões de {len(logicos)} documento_logico_id '
            f'diferentes — esperado exatamente 1.'
        )

    substituidos = {v.substitui_documento_id for v in versoes if v.substitui_documento_id}
    pontas = [v for v in versoes if v.documento_id not in substituidos]
    if len(pontas) != 1:
        raise GrafoVersionamentoInconsistente(
            f'Grafo de versionamento não é uma cadeia linear única: '
            f'{len(pontas)} ponta(s) encontrada(s) (esperado exatamente 1).'
        )
    return pontas[0]


def verificar_nova_versao(
    versoes_existentes: Sequence[VersionamentoLogico],
    hash_sha256_novo: str,
    hash_sha256_por_documento_id: Dict[str, str],
) -> DecisaoVersionamento:
    """Decide o que fazer quando um `documento_logico_id` recebe um novo
    conteúdo (hash). NUNCA decide supersessão sozinha — hash diferente
    para o mesmo documento lógico é sempre CONFLITO, preservado para
    decisão humana posterior (mesmo princípio de
    `dominio.classificar_item`: nunca gravado automaticamente quando há
    ambiguidade)."""
    if not versoes_existentes:
        return DecisaoVersionamento(ResultadoVerificacaoVersao.PRIMEIRA_VERSAO, 1, None)

    vigente = determinar_vigente(versoes_existentes)
    hash_vigente = hash_sha256_por_documento_id.get(vigente.documento_id)
    if hash_vigente == hash_sha256_novo:
        return DecisaoVersionamento(
            ResultadoVerificacaoVersao.MESMO_CONTEUDO_JA_REGISTRADO, None, vigente.documento_id)

    return DecisaoVersionamento(
        ResultadoVerificacaoVersao.CONFLITO_HASH_DIFERENTE, None, vigente.documento_id)


def construir_proxima_versao(
    documento_logico_id: str,
    documento_id_novo: str,
    versao_vigente: VersionamentoLogico,
    quando: datetime,
) -> VersionamentoLogico:
    """Constrói o registro da PRÓXIMA versão, substituindo explicitamente
    a vigente atual. Função pura — não grava nada, não decide sozinha
    QUANDO deve ser chamada. `escritor.py` NUNCA chama esta função
    automaticamente: supersessão só acontece por um fluxo de correção
    explicitamente autorizado por humano, fora do escopo desta fase (ver
    CLAUDE.md §12-I, "decisão empresarial ambígua" — gate humano que
    permanece)."""
    return VersionamentoLogico(
        documento_id=documento_id_novo,
        documento_logico_id=documento_logico_id,
        versao_documento=versao_vigente.versao_documento + 1,
        substitui_documento_id=versao_vigente.documento_id,
        criado_em=quando,
    )
