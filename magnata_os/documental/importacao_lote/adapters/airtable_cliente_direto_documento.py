"""Adapter REAL read-only de `FonteClienteDiretoDocumento` (missão
"MERGE PR #108 + FECHAR BLOQUEIOS REAIS DO CORREDOR LIVE V2 + REVISÃO
ADVERSARIAL PRÉ-ENTREGA").

Fecha `cliente_direto` de produção para Extrato e FGTS Guia (§5/§6/§7
da missão) SEM criar 2 adapters distintos e SEM reimplementar
correspondência já testada: reaproveita, tal como estão, 2 peças 100%
reais e já em produção neste mesmo pacote --

  - `LeitorAirtableSomenteLeitura.listar_clientes()` (`airtable_
    leitura.py`) -- lê CNPJ + Nome reais da tabela Clientes (`TABLE_
    CLIENTES`), já usado pela correspondência de cliente de Extrato do
    pipeline de importação em lote (`orquestrador.processar_extrato`);
  - `dominio.resolver_cliente(texto, nome_manifesto, candidatos)` --
    função PURA, já testada, correspondência CNPJ-primeiro com
    `EXACT`/`AMBIGUOUS`/`CONFLICT`/`NOT_FOUND` explícitos, nunca
    reimplementada aqui.

`nome_manifesto=''` é passado deliberadamente: este adapter nunca tem
um campo de manifesto estruturado (o `FonteClienteDiretoDocumento` só
recebe o TEXTO do documento) -- então o fallback por nome de
`resolver_cliente` nunca decide sozinho aqui (nenhum cliente real tem
`nome_normalizado == ''`). Para nunca depender dessa suposição
implícita, o resultado só é aceito quando `criterio_usado ==
'cnpj_exato'` -- checagem EXPLÍCITA no contrato, nunca inferida do
efeito colateral de uma string vazia (mesma disciplina de "nenhum
contrato depende só de docstring para ser seguro" já aplicada ao
UNIDADE_POSTO/escopo de clientes nesta mesma missão)."""
from __future__ import annotations

from typing import Optional

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.contratos import ClassificacaoCorrespondencia
from magnata_os.documental.importacao_lote.dominio import resolver_cliente

from .airtable_leitura import LeitorAirtableSomenteLeitura


class FonteClienteDiretoDocumentoAirtableShadow:
    """Implementa `FonteClienteDiretoDocumento` (`classificacao/fonte_
    cliente_direto_documento.py`) sobre o leitor read-only já
    existente -- nenhuma tabela nova, nenhuma escrita, nenhum campo não
    confirmado em produção."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def resolver_cliente_direto(self, texto_documento: str) -> Optional[ReferenciaCanonica]:
        candidatos = self._leitor.listar_clientes()
        resultado = resolver_cliente(texto_documento, '', candidatos)
        if (
            resultado.classificacao != ClassificacaoCorrespondencia.EXACT
            or resultado.criterio_usado != 'cnpj_exato'
            or resultado.entidade_id is None
        ):
            # Ausência de CNPJ, CNPJ desconhecido, CNPJs de clientes
            # DIFERENTES no mesmo texto, ou (por construção impossível
            # aqui, mas nunca assumido) um match só por nome -- todos
            # devolvem None, nunca um palpite.
            return None
        return ReferenciaCanonica('CLIENTE', resultado.entidade_id)
