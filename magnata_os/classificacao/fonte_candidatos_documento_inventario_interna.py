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
        itens_tipo_ok = [
            item for item in itens
            if item.tipo_documental == necessidade.tipo_documental
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
        candidatos = []
        for item in itens_filtrados:
            documento = self._repositorio_documentos.buscar_por_id(item.documento_id)
            if documento is not None:
                candidatos.append(documento)

        # Retornar determinístico (ordenado por documento_id)
        return tuple(sorted(candidatos, key=lambda d: d.documento_id))
