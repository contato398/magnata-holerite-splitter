"""Normalização PURA de requisitos externos → configuração canônica
(missão "POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fase 7).

Fluxo (nunca pulado): registro externo → adapter (I/O, fora deste
módulo) → `RegistroRequisitoExterno` (forma neutra) → ESTA normalização
→ `RequisitoDocumentalPrestacao` (contrato já existente, reaproveitado)
→ `PoliticaRequisitosPrestacao`.

Airtable (ou qualquer fonte externa) NUNCA define semântica diretamente
— só fornece um valor de texto (`tipo_documental`) e um número
(`quantidade_minima`). Esta função é quem decide se esse valor
corresponde a um tipo documental CANÔNICO conhecido pelo motor geral.
Tipo desconhecido nunca vira requisito silenciosamente: fica
`TIPO_DESCONHECIDO`, explícito, para revisão — nunca um default."""
from __future__ import annotations

import dataclasses
import enum
from typing import Optional, Tuple

from .prestacao_readiness import RequisitoDocumentalPrestacao

# Universo documental canônico produzido pelo motor geral (classificador
# textual + produtores estruturais/fiscais/temporais + finalidade de
# comprovante de pagamento) -- ver docs/decisoes/*.md para a origem de
# cada nome. Atualizar esta lista SÓ quando um novo tipo/finalidade for
# comprovadamente produzido pelo motor -- nunca "para o Airtable aceitar
# de qualquer jeito".
TIPOS_DOCUMENTAIS_CANONICOS = frozenset({
    'Holerite',
    'Folha de Ponto',
    'Extrato da Folha de Pagamento',
    'FGTS',
    'DCTFWeb - Declaração',
    'DCTFWeb - Recibo de Entrega',
    'Guia DCTFWeb/DARF',
    'Guia',
    'Boleto',
    'Nota Fiscal',
    'Certidão',
    'Comprovante de Pagamento - Salário',
    'Comprovante de Pagamento - FGTS',
    'Comprovante de Pagamento - DCTF/DARF',
    'Comprovante de Pagamento - VR/VA',
    'Comprovante de Pagamento - Assiduidade',
    'Comprovante de Pagamento - Diárias',
    'Comprovante de Pagamento - Horas Extras',
})


@dataclasses.dataclass(frozen=True)
class RegistroRequisitoExterno:
    """Forma NEUTRA de 1 linha de configuração externa -- já extraída
    de qualquer fonte (Airtable, planilha, fixture) por um adapter;
    esta forma nunca carrega um dict Airtable cru (nunca `fields`,
    nunca ID de campo)."""

    tipo_documental: str
    quantidade_minima: int = 1


class EstadoNormalizacaoRequisito(str, enum.Enum):
    VALIDO = 'VALIDO'
    TIPO_DESCONHECIDO = 'TIPO_DESCONHECIDO'
    QUANTIDADE_INVALIDA = 'QUANTIDADE_INVALIDA'


@dataclasses.dataclass(frozen=True)
class ResultadoNormalizacaoRequisito:
    estado: EstadoNormalizacaoRequisito
    requisito: Optional[RequisitoDocumentalPrestacao] = None
    motivo: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado == EstadoNormalizacaoRequisito.VALIDO and self.requisito is None:
            raise ValueError('estado VALIDO exige requisito preenchido')
        if self.estado != EstadoNormalizacaoRequisito.VALIDO and self.requisito is not None:
            raise ValueError('estado invalido nao pode carregar requisito')


def normalizar_requisito(registro: RegistroRequisitoExterno) -> ResultadoNormalizacaoRequisito:
    """Valida 1 registro isolado -- nunca decide sozinho o que fazer com
    o resultado (quem chama decide: ignorar, logar como pendência,
    bloquear a política inteira etc.)."""
    if registro.tipo_documental not in TIPOS_DOCUMENTAIS_CANONICOS:
        return ResultadoNormalizacaoRequisito(
            estado=EstadoNormalizacaoRequisito.TIPO_DESCONHECIDO,
            motivo=f'tipo_documental desconhecido pelo motor geral: {registro.tipo_documental!r}',
        )
    if isinstance(registro.quantidade_minima, bool) or not isinstance(registro.quantidade_minima, int) \
            or registro.quantidade_minima < 1:
        return ResultadoNormalizacaoRequisito(
            estado=EstadoNormalizacaoRequisito.QUANTIDADE_INVALIDA,
            motivo='quantidade_minima deve ser inteira positiva',
        )
    return ResultadoNormalizacaoRequisito(
        estado=EstadoNormalizacaoRequisito.VALIDO,
        requisito=RequisitoDocumentalPrestacao(registro.tipo_documental, registro.quantidade_minima),
    )


def normalizar_requisitos(
    registros: Tuple[RegistroRequisitoExterno, ...],
) -> Tuple[Tuple[RequisitoDocumentalPrestacao, ...], Tuple[ResultadoNormalizacaoRequisito, ...]]:
    """Devolve (válidos, todos_os_resultados) -- nunca descarta
    silenciosamente o que falhou; `todos_os_resultados` preserva os
    motivos de cada rejeição para quem orquestra decidir (registrar
    pendência, alertar, etc.)."""
    resultados = tuple(normalizar_requisito(registro) for registro in registros)
    validos = tuple(
        resultado.requisito for resultado in resultados
        if resultado.estado == EstadoNormalizacaoRequisito.VALIDO
    )
    return validos, resultados
