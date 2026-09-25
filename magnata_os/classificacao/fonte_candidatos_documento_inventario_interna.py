"""Fonte interna de candidatos documentais por necessidade (Prestação V1.1 Incremento 1).

Implementa `FonteCandidatosDocumentaisPorNecessidade` consultando inventário
canônico INTERNO (`FonteInventarioPrestacao`) sem Airtable, Gmail ou rede.

Reutiliza:
- FonteInventarioPrestacao (Protocol já existente)
- RepositorioDocumentos (Protocol já existente)
- ItemInventarioPrestacao (contrato já existente)
- NecessidadeDocumentoPrestacao (contrato já existente)

Comportamento:
1. Recebe UMA NecessidadeDocumentoPrestacao
2. Consulta source_inventario.listar(cliente, competencia)
3. Filtra por tipo_documental + colaborador (se presente na necessidade)
4. Recupera Documento completo por documento_id via repositorio_documentos
5. Ignora falha-fechada: Documento não encontrado → não retorna
6. Retorna Tuple[Documento, ...] determinística

NUNCA:
- consulta Airtable
- consulta Gmail
- infere por timestamp
- usa fuzzy match
- acessa rede
- fabrica metadata

Preserva documento_id e hash_sha256 do Documento original.
"""
from __future__ import annotations

from typing import Tuple

from magnata_os.documental.modulo01.dominio import Documento
from .ciclo_prestacao import NecessidadeDocumentoPrestacao
from .fonte_candidatos_por_necessidade import FonteCandidatosDocumentaisPorNecessidade
from .inventario_prestacao import FonteInventarioPrestacao
from .normalizacao_requisitos_prestacao import TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL


def _tipo_canonico(tipo: str) -> str:
    """Mesma tradução de vocabulário que a elegibilidade J1b já usa
    (`_tipo_resolvido_atende_necessidade`): necessidade em vocabulário
    Família B e item em vocabulário do motor designam o MESMO tipo.
    Nunca aproxima tipos diferentes -- só a tradução conhecida."""
    return TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL.get(tipo, tipo)


class FonteCandidatosDocumentoInventarioInterna:
    """Implementa FonteCandidatosDocumentaisPorNecessidade consultando
    inventário interno (sem Airtable/Gmail/rede).
    """

    def __init__(
        self,
        fonte_inventario: FonteInventarioPrestacao,
        repositorio_documentos: object,  # RepositorioDocumentos (Protocol)
    ):
        """
        Args:
            fonte_inventario: Fonte de inventário (ex: InventarioPrestacaoEmMemoria)
            repositorio_documentos: Repositório para recuperar Documento por ID
        """
        self._fonte_inventario = fonte_inventario
        self._repositorio_documentos = repositorio_documentos

    def candidatos_para(
        self, necessidade: NecessidadeDocumentoPrestacao,
    ) -> Tuple[Documento, ...]:
        """Retorna candidatos reais para uma necessidade específica.

        Filtra inventário por:
        1. cliente esperado
        2. competência esperada
        3. tipo_documental esperado
        4. colaborador esperado (opcional)

        Args:
            necessidade: NecessidadeDocumentoPrestacao com cliente, competência,
                tipo_documental, colaborador(opt)

        Returns:
            Tuple[Documento, ...]: documentos candidatos (vazio se nenhum corresponde)
        """
        # Consultar inventário por cliente/competência
        itens = self._fonte_inventario.listar(
            necessidade.cliente,
            necessidade.competencia,
        )

        # Filtrar por tipo_documental
        tipo_esperado = _tipo_canonico(necessidade.tipo_documental)
        itens_tipo_ok = [
            item for item in itens
            if _tipo_canonico(item.tipo_documental) == tipo_esperado
        ]

        # Filtrar por colaborador (se necessidade exige um específico)
        if necessidade.colaborador is not None:
            itens_filtrados = [
                item for item in itens_tipo_ok
                if item.colaborador == necessidade.colaborador
            ]
        else:
            # Se necessidade NÃO exige colaborador, remover itens que têm
            # (documentos individuais, não por colaborador)
            itens_filtrados = [
                item for item in itens_tipo_ok
                if item.colaborador is None
            ]

        # Recuperar Documento por documento_id
        # Fail-closed: ignora items cujo documento não exista
        # (mesmo documento em 2+ itens -- ex.: 2 origens do índice -- vira 1 candidato)
        candidatos = {}
        for item in itens_filtrados:
            if item.documento_id in candidatos:
                continue
            documento = self._repositorio_documentos.buscar_por_id(item.documento_id)
            if documento is not None:
                candidatos[item.documento_id] = documento

        # Retornar determinístico (ordenado por documento_id)
        return tuple(sorted(candidatos.values(), key=lambda d: d.documento_id))
