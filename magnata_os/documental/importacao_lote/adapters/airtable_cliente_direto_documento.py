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
UNIDADE_POSTO/escopo de clientes nesta mesma missão).

ACHADO DA REVISÃO ADVERSARIAL (checkpoint pré-merge do PR #109, §7):
"CNPJ de outra entidade presente no PDF pode gerar falso cliente?" --
análise: NÃO gera falso POSITIVO -- `resolver_cliente` só casa CNPJs
extraídos do texto contra `candidatos` (clientes REALMENTE
cadastrados); um CNPJ de banco/órgão público/da própria Magnata que
NÃO está cadastrado como Cliente nunca entra em `achados_cnpj`, nunca
produz resolução. O único efeito possível de um 2º CNPJ estranho
CADASTRADO como Cliente (ex.: se a própria Magnata, emissora de todo
Extrato/Guia, estivesse cadastrada como Cliente por engano) é reduzir
COBERTURA (`CONFLICT` -> `None`, nunca uma resolução errada) -- o
mesmo comportamento fail-safe já garantido pela lógica de conflito de
`resolver_cliente`. Mesmo assim, `cnpj_excluido` (parâmetro OPCIONAL,
default `None` -- zero mudança de comportamento sem uso explícito) é
adicionado aqui, espelhando EXATAMENTE o mesmo mecanismo já confiável
de `separacao_documental.estrategia_por_cnpj_cliente(cnpj_excluido=...)`
-- para quando quem compõe o corredor real souber, de fato, qual CNPJ
(ex.: o da própria Magnata) nunca deve competir como candidato,
evitando o `CONFLICT` desnecessário nesse caso específico, sem
introduzir nenhum risco de falso positivo novo (a exclusão só REMOVE
um CNPJ do texto considerado, nunca adiciona candidato)."""
from __future__ import annotations

import re
from typing import Optional

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.contratos import ClassificacaoCorrespondencia
from magnata_os.documental.importacao_lote.dominio import normalizar_cnpj, resolver_cliente

from .airtable_leitura import LeitorAirtableSomenteLeitura

# Mesmo padrão de `dominio._CNPJ_RE` (privado, por isso duplicado aqui
# -- nunca importado com underscore de outro módulo) -- usado só para
# localizar e remover a OCORRÊNCIA textual do `cnpj_excluido`, nunca
# para decidir correspondência (isso continua 100% dentro de
# `resolver_cliente`, nunca reimplementado).
_CNPJ_TEXTO_RE = re.compile(r'\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}')


class FonteClienteDiretoDocumentoAirtableShadow:
    """Implementa `FonteClienteDiretoDocumento` (`classificacao/fonte_
    cliente_direto_documento.py`) sobre o leitor read-only já
    existente -- nenhuma tabela nova, nenhuma escrita, nenhum campo não
    confirmado em produção.

    `cnpj_excluido`: mesmo papel de `separacao_documental.estrategia_
    por_cnpj_cliente(cnpj_excluido=...)` -- um CNPJ (tipicamente o da
    própria Magnata, emissora do documento) que NUNCA deve ser
    considerado candidato a cliente, mesmo que apareça no texto e
    esteja, por engano, cadastrado como Cliente. `None` (default)
    preserva o comportamento original -- nenhum CNPJ excluído."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura, cnpj_excluido: Optional[str] = None):
        self._leitor = leitor
        self._cnpj_excluido = normalizar_cnpj(cnpj_excluido) if cnpj_excluido else None

    def resolver_cliente_direto(self, texto_documento: str) -> Optional[ReferenciaCanonica]:
        texto_para_matching = texto_documento
        if self._cnpj_excluido is not None and texto_documento:
            # Remove do texto considerado só as OCORRÊNCIAS que
            # normalizam para o CNPJ excluído -- nunca filtra por
            # substring solta (evita remover, por engano, um CNPJ
            # diferente que só compartilha alguns dígitos).
            texto_para_matching = _CNPJ_TEXTO_RE.sub(
                lambda m: '' if normalizar_cnpj(m.group(0)) == self._cnpj_excluido else m.group(0),
                texto_documento,
            )
        candidatos = self._leitor.listar_clientes()
        resultado = resolver_cliente(texto_para_matching, '', candidatos)
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
