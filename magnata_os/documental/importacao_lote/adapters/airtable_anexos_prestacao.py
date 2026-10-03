"""Adapter de leitura (GET) de anexos (attachments) do Airtable, por
tabela/campo/registro -- missão "Ingestão real em lote de documento"
(ver docs/decisoes/ingestao-documento-lote-real-v1.md).

Reaproveita `LeitorAirtableSomenteLeitura.listar_registros` -- nunca
reimplementa autenticação/paginação. Só devolve os METADADOS do anexo
(id, url, filename, size, type) como o Airtable os expõe -- baixar os
bytes reais é responsabilidade de quem chama
(`ingestao_documentos_lote_real.py`), porque a URL de anexo do Airtable
é assinada e não usa o mesmo header `Authorization: Bearer` da API
REST que `LeitorAirtableSomenteLeitura` já injeta.

Nenhum método de escrita nesta classe/módulo -- mesma disciplina já
documentada em `airtable_leitura.py`/CLAUDE.md do módulo.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

from .airtable_leitura import LeitorAirtableSomenteLeitura

# Airtable aceita filterByFormula bem maior que isto, mas um lote grande
# de OR(...) vira uma URL/formula enorme e difícil de depurar -- agrupar
# em blocos pequenos mantém cada chamada previsível, ao custo aceito de
# mais 1 chamada HTTP por bloco extra (nunca mais que isso).
_TAMANHO_MAXIMO_LOTE_OR = 40


def buscar_anexos_por_registro(
    leitor: LeitorAirtableSomenteLeitura,
    table_id: str,
    field_attachment: str,
    registro_ids: Sequence[str],
) -> Dict[str, Tuple[dict, ...]]:
    """Devolve ``{registro_id: (anexo, anexo, ...)}`` só para os
    registros pedidos, só do campo de anexo informado. Um registro sem
    nenhum anexo nunca aparece nas chaves do retorno -- ausência de
    chave é o sinal de "sem anexo", nunca uma lista vazia escondida."""
    ids_unicos = tuple(sorted({rid for rid in registro_ids if rid}))
    if not ids_unicos:
        return {}

    resultado: Dict[str, Tuple[dict, ...]] = {}
    for inicio in range(0, len(ids_unicos), _TAMANHO_MAXIMO_LOTE_OR):
        bloco = ids_unicos[inicio:inicio + _TAMANHO_MAXIMO_LOTE_OR]
        formula = 'OR(' + ','.join(f'RECORD_ID()="{rid}"' for rid in bloco) + ')'
        registros = leitor.listar_registros(
            table_id=table_id, fields=[field_attachment], filter_by_formula=formula,
        )
        for registro in registros:
            anexos = (registro.get('fields', {}) or {}).get(field_attachment) or []
            if anexos:
                resultado[registro['id']] = tuple(anexos)
    return resultado
