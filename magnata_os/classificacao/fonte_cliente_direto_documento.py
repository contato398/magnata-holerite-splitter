"""Fonte CANÔNICA e SUBSTITUÍVEL de `cliente_direto` para famílias de
granularidade cliente (missão "MERGE PR #108 + FECHAR BLOQUEIOS REAIS
DO CORREDOR LIVE V2 + REVISÃO ADVERSARIAL PRÉ-ENTREGA").

Fecha, com um contrato PRÓPRIO e nomeado -- nunca inferência ad-hoc
dentro do corredor --, a lacuna registrada em `docs/decisoes/adapters-
reais-unidade-posto-candidatos-relacao-v1.md`: "nenhum adapter de
produção resolve `cliente_direto` a partir de origem de intake para um
documento único" (Extrato, FGTS Guia).

Capacidade COMPARTILHADA (§7 da missão: "se ambos dependem da mesma
capacidade, criar/reusar um contrato comum, nunca 2 adapters
distintos") -- Extrato e FGTS Guia são as 2 famílias de granularidade
cliente hoje cadastradas (`perfil_aplicabilidade_documental.py`,
`_perfil_granularidade_cliente`), e as 2 usam exatamente a mesma
pergunta: "este documento único, sem separação master→filhos, prova
qual cliente por evidência própria?" -- um Protocol só, nunca um por
família.

REGRA PÉTREA (§4 da missão, aplicada aqui): `cliente_direto` só pode
vir de EVIDÊNCIA REAL -- nunca de nome de tabela, nome de arquivo,
pasta, remetente, "este tipo normalmente pertence a X" ou primeiro
cliente ativo. A única evidência aceita por este contrato é CNPJ
extraído do PRÓPRIO TEXTO do documento, batendo EXATAMENTE contra 1
cliente cadastrado -- o mesmo critério `criterio_usado == 'cnpj_exato'`
já usado e testado em `importacao_lote.dominio.resolver_cliente`
(reaproveitado pelo adapter real, nunca reimplementado) e em
`separacao_documental.estrategia_por_cnpj_cliente` (mesma disciplina,
usada para separar documento MASTER). Nome de cliente NUNCA é usado
aqui como evidência: batização por nome contra o texto integral de um
PDF (ao contrário de um campo de manifesto estruturado, `nome_
manifesto`) tem risco real de falso positivo por substring -- fora de
escopo aceitável para uma fonte que, por contrato, só devolve
`RESOLVIDA` quando há certeza estrutural.

CNPJ ausente, CNPJ desconhecido, ou 2+ CNPJs de clientes DIFERENTES no
mesmo texto -- os 3 casos devolvem `None` (nunca resolvido, nunca
adivinhado) -- consistente com `ClassificacaoCorrespondencia.
NOT_FOUND`/`CONFLICT`/ausência de CNPJ em `resolver_cliente`."""
from __future__ import annotations

from typing import Optional, Protocol

from .contratos import ReferenciaCanonica


class FonteClienteDiretoDocumento(Protocol):
    """Porta substituível: dado o texto já extraído de um documento de
    granularidade cliente (Extrato, FGTS Guia -- qualquer família
    futura que se cadastre em `_perfil_granularidade_cliente`), devolve
    o cliente comprovado por evidência própria do documento, ou `None`
    quando a evidência é insuficiente. Quem orquestra decide quando
    chamar esta fonte e como usar o resultado (ex.: preencher
    `ContextoResolucaoDocumentoPrestacao.cliente_direto`) -- este
    Protocol nunca decide isso sozinho, nunca é injetado como fonte
    substituível dentro do corredor genérico (mesma disciplina de
    `cliente_direto` já ser um VALOR pré-resolvido, nunca uma fonte
    consultada durante a resolução de dimensões)."""

    def resolver_cliente_direto(self, texto_documento: str) -> Optional[ReferenciaCanonica]: ...
