"""
Materializador documental generico owner-aware -- Modulo 01 (Documental).

Contrato puro (Protocol + tipos de retorno/erro), sem I/O, sem Airtable,
sem `requests` -- mesma disciplina de pureza de dominio de `dominio.py`/
`armazenamento.py` (ver `magnata_os/CLAUDE.md`). O adapter real (que fala
com o Airtable legado) vive em `adapters/materializador_arquivo_legado.py`.

Objetivo funcional (ADR: `docs/decisoes/pacote-holerite-folha-ponto.md`,
adendo "Fase 1 Ownership + Bridge Segura" -- "Materializador generico
owner-aware de Holerite -> TABLE_ARQUIVOS ... proximo incremento"):

    Documento canonico + destinatario autoritativo (funcionario_id)
        -> registro utilizavel no legado TABLE_ARQUIVOS
        -> arquivo_record_id
        -> segue pelo motor legado de assinatura sem nenhuma mudanca
           em `_gerar_assinatura_core`/`_gerar_pacote_assinatura_holerite_ponto`.

A unidade operacional da bridge e sempre `Documento + destinatario`,
nunca so o hash: `hash_sha256` e identidade de CONTEUDO (o mesmo PDF pode
legitimamente ser entregue a mais de um colaborador no futuro), nunca a
identidade da relacao documento-destinatario. Por isso toda ambiguidade
de ownership em candidatos do mesmo hash e fail-closed -- nunca resolvida
por inferencia (ver `OwnerAusenteMaterializacao`/`OwnerMalformadoMaterializacao`/
`AmbiguidadeMaterializacao` abaixo).

`HashInconsistente` e REUTILIZADA de `armazenamento.py` (mesma semantica
exata: o hash informado nao bate com o SHA-256 real do conteudo desta
chamada) -- nunca redefinida aqui.

Nesta V1: nao existe correlacao reversa persistida `arquivo_record_id ->
documento_id` dentro do Airtable (TABLE_ARQUIVOS nao tem, e este
incremento nao cria, nenhum campo para isso). `documento_id` continua
sendo a identidade logica autoritativa no Documental; `hash_sha256`
preserva identidade de conteudo na bridge; `arquivo_record_id` e a
identidade operacional do legado de assinatura. `ResultadoMaterializacao`
preserva a correlacao so DURANTE a operacao (em memoria, ecoada da
chamada) -- resolver isso de forma duravel e sem heuristica fica para a
camada F2 (`resolucao_documental_temporal`) ou um mapeamento canonico
futuro, nenhum dos dois criado aqui.
"""
from __future__ import annotations

import dataclasses
from typing import Protocol

from .armazenamento import HashInconsistente
from .dominio import Documento

__all__ = [
    'ResultadoMaterializacao',
    'TamanhoInconsistente',
    'OwnerAusenteMaterializacao',
    'OwnerMalformadoMaterializacao',
    'AmbiguidadeMaterializacao',
    'MaterializadorArquivoLegado',
    'HashInconsistente',
]


@dataclasses.dataclass(frozen=True)
class ResultadoMaterializacao:
    """`funcionario_id` e obrigatorio -- a unidade operacional da bridge
    e sempre Documento + destinatario, nunca so o hash. `documento_id` e
    `hash_sha256` sao ecoados da chamada (nunca lidos de volta do
    Airtable), preservando a correlacao so durante a operacao -- ver
    docstring do modulo sobre a ausencia de correlacao reversa
    persistida nesta V1."""

    arquivo_record_id: str
    documento_id: str
    funcionario_id: str
    hash_sha256: str
    reutilizado: bool


class TamanhoInconsistente(Exception):
    """`len(conteudo_bytes)` nao bate com `documento.tamanho` -- nova,
    sem equivalente no legado (`ArmazenamentoArquivos` so valida hash,
    nao tamanho, por isso nao ha uma exceção correspondente a reutilizar)."""


class OwnerAusenteMaterializacao(Exception):
    """Um candidato com o mesmo hash tem `F_ARQ_FUNCIONARIO_OWNER`
    ausente/vazio -- BLOQUEIA toda a operacao. Nunca descartado
    silenciosamente: um owner indeterminavel pode ser exatamente um
    registro legado/orfao da MESMA relacao documento-destinatario que
    estamos tentando materializar agora -- ignorar e criar outro
    registro transformaria incerteza em duplicacao silenciosa."""


class OwnerMalformadoMaterializacao(Exception):
    """Um candidato com o mesmo hash tem owner multiplo (mais de um
    link) ou um valor que nao e um Record ID valido -- BLOQUEIA toda a
    operacao, mesmo motivo de `OwnerAusenteMaterializacao`."""


class AmbiguidadeMaterializacao(Exception):
    """Mais de um candidato com o mesmo hash tem owner exatamente igual
    a `funcionario_id` da chamada -- nunca escolhido silenciosamente
    entre eles."""


class MaterializadorArquivoLegado(Protocol):
    """Porta owner-aware para materializar um `Documento` canonico como
    registro utilizavel pelo motor legado de assinatura (`TABLE_ARQUIVOS`).

    Contrato de validacao obrigatoria ANTES de qualquer chamada de rede
    (ver adapter real para a sequencia completa): `documento.documento_id`
    nao vazio; `documento.hash_sha256` em formato valido;
    `funcionario_id` em formato de Record ID valido; `conteudo_bytes` nao
    vazio; `len(conteudo_bytes) == documento.tamanho` (senao
    `TamanhoInconsistente`); `sha256(conteudo_bytes) ==
    documento.hash_sha256` (senao `HashInconsistente`, reutilizada de
    `armazenamento.py`) -- nunca confia apenas no que `documento` afirma
    sem recalcular.
    """

    def materializar(
        self,
        *,
        documento: Documento,
        conteudo_bytes: bytes,
        funcionario_id: str,
    ) -> ResultadoMaterializacao:
        """Cria ou reutiliza deterministicamente um registro em
        TABLE_ARQUIVOS para `documento` + `funcionario_id`, gravando
        F_ARQ_FUNCIONARIO_OWNER, e devolve o `arquivo_record_id`
        resultante -- nunca retorna sucesso sem attachment confirmado."""
        ...
