"""Índice documental (J3) lido como ACELERADOR, nunca como fonte única.

Problema que resolve: com o índice como primeira fonte da localização,
um acerto encerraria a busca -- uma versão corrigida reenviada depois
nunca seria vista (a primeira ficaria "congelada").

Regra:
- índice sem nada para a necessidade -> busca por conteúdo completa
  (comportamento de antes);
- índice com candidatos -> devolve esses candidatos MAIS o que a busca
  por conteúdo achar entre os documentos registrados DEPOIS do mais
  recente deles (`Documento.criado_em`). A busca fica barata (só o que
  é novo) e uma versão nova sempre entra na disputa; quem decide qual
  vale é a regra de versão aplicada DEPOIS da conferência
  (`data_versao_documento`), nunca a ordem das fontes.

Falha da busca por conteúdo propaga (a localização registra a fonte
como FALHOU -> INDETERMINADO): índice + lacuna nunca vira escolha
silenciosa.
"""
from __future__ import annotations

from typing import Mapping, Tuple

from magnata_os.documental.modulo01.dominio import Documento

from .ciclo_prestacao import NecessidadeDocumentoPrestacao
from .fonte_candidatos_documento_inventario_interna import FonteCandidatosDocumentoInventarioInterna


class FonteIndiceComFrescor:
    def __init__(self, indice: object, repositorio_documentos: object, fonte_conteudo: object) -> None:
        self._indice = FonteCandidatosDocumentoInventarioInterna(indice, repositorio_documentos)
        self._conteudo = fonte_conteudo
        self._resumo: Mapping[str, int] = {}

    def candidatos_para(self, necessidade: NecessidadeDocumentoPrestacao) -> Tuple[Documento, ...]:
        indexados = self._indice.candidatos_para(necessidade)
        if not indexados:
            achados = tuple(self._conteudo.candidatos_para(necessidade))
            self._resumo = {'documentos_do_indice': 0, **self._resumo_conteudo()}
            return achados
        corte = max(d.criado_em for d in indexados)
        novos = tuple(self._conteudo.candidatos_para(necessidade, criados_apos=corte))
        self._resumo = {'documentos_do_indice': len(indexados), **self._resumo_conteudo()}
        vistos = {}
        for documento in indexados + novos:
            vistos.setdefault(documento.documento_id, documento)
        return tuple(sorted(vistos.values(), key=lambda d: d.documento_id))

    def resumo_ultima_consulta(self) -> Mapping[str, int]:
        return dict(self._resumo)

    def _resumo_conteudo(self) -> Mapping[str, int]:
        resumo = getattr(self._conteudo, 'resumo_ultima_consulta', None)
        return dict(resumo()) if callable(resumo) else {}
