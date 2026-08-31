"""COMPOSIÇÃO DE BORDA do orquestrador real read-only (missão
"CONSTRUIR ORQUESTRADOR REAL READ-ONLY DO CORREDOR V2 + PREPARAR
PRIMEIRO LIVE CONTROLADO SEM EXECUTÁ-LO", §19-B).

Este é o único lugar que instancia adapters REAIS (Airtable read-only)
e faz I/O (extração de PDF) para o orquestrador canônico/puro
`magnata_os.classificacao.orquestrador_corredor_readonly` -- mesma
separação Protocol/adapter já usada em toda a sessão, agora aplicada a
COMPOR várias capacidades de uma vez, nunca a criar um segundo motor.

Reaproveita, tal como estão, TODOS os adapters reais já construídos
nesta sessão (nenhum novo adapter Airtable criado aqui):

  - `LeitorAirtableSomenteLeitura` (transporte autenticado já real);
  - `FonteVinculosPrestacaoAirtableShadow` (CLIENTE via vínculo);
  - `FonteUnidadePostoPrestacaoAirtableShadow` (UNIDADE_POSTO, com
    `competencia_snapshot_comprovada` -- nunca None por acaso: sem
    prova explícita, cai honestamente em NAO_ENCONTRADA);
  - `FonteClienteDiretoDocumentoAirtableShadow` (CLIENTE direto via
    CNPJ, Extrato/FGTS Guia);
  - `FonteEscopoClientesPorInventarioAirtableShadow` +
    `FonteInventarioPrestacaoAirtableShadow` -> `FonteCandidatosRelacao
    DocumentalDoInventario` (candidatos de relação documental);
  - `extrair_texto_pdf` (`documental/extracao_texto.py`, já promovida
    e neutra -- nenhuma segunda implementação de leitura de PDF aqui).

Correlação transitória (§13/§14 da missão): `FonteDadosCorrelacaoEm
Memoria` é injetada UMA VEZ por execução (`ExecucaoCorredorReadonly`,
abaixo) e SOBREVIVE só enquanto o objeto Python existir -- reiniciar o
processo apaga tudo. Isso NUNCA é chamado de persistência (docstring
de `FonteDadosCorrelacaoEmMemoria`, preservada): é só um cache local
de UMA execução controlada, exatamente o que o §13 da missão pede."""
from __future__ import annotations

import dataclasses
from typing import Optional, Sequence, Tuple

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_relacao_documental_do_inventario import (
    FonteCandidatosRelacaoDocumentalDoInventario,
    FonteDadosCorrelacaoEmMemoria,
)
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.classificacao.orquestrador_corredor_readonly import (
    ContextoExecucaoCorredorPrestacao,
    ResultadoExecucaoCorredorPrestacao,
    executar_documento_readonly,
)
from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from magnata_os.classificacao.separacao_documental import IdentificadorDePagina
from magnata_os.documental.extracao_texto import extrair_texto_pdf
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

from .adapters.airtable_cliente_direto_documento import FonteClienteDiretoDocumentoAirtableShadow
from .adapters.airtable_inventario_prestacao import (
    FonteEscopoClientesPorInventarioAirtableShadow,
    FonteInventarioPrestacaoAirtableShadow,
)
from .adapters.airtable_leitura import LeitorAirtableSomenteLeitura
from .adapters.airtable_unidade_posto_prestacao import FonteUnidadePostoPrestacaoAirtableShadow
from .adapters.airtable_vinculos_prestacao import FonteVinculosPrestacaoAirtableShadow


class ExecucaoCorredorReadonly:
    """Composição de UMA execução controlada, read-only, do corredor --
    instancia os adapters reais UMA VEZ (reaproveitados por todo
    documento processado nesta execução, nunca recriados por
    documento) e expõe `processar_documento` como o entrypoint
    production-callable (§20 da missão).

    `competencia_snapshot_comprovada`: repassada tal como está para
    `FonteUnidadePostoPrestacaoAirtableShadow` -- responsabilidade de
    QUEM CONSTRÓI esta execução fornecer só quando tiver prova real de
    vigência (nunca inferida aqui); `None` (default) preserva o
    comportamento fail-safe já testado daquele adapter (UNIDADE_POSTO
    honestamente NAO_ENCONTRADA sem prova)."""

    def __init__(
        self,
        leitor: LeitorAirtableSomenteLeitura,
        ciclo: ContextoCicloPrestacao,
        competencia_snapshot_comprovada: Optional[Tuple[int, int]] = None,
        cnpj_excluido: Optional[str] = None,
        habilitar_correlacao_transitoria: bool = False,
    ) -> None:
        self._ciclo = ciclo
        self._sink = InventarioPrestacaoEmMemoria()
        self._fonte_vinculos = FonteVinculosPrestacaoAirtableShadow(leitor)
        self._fonte_unidade_posto = FonteUnidadePostoPrestacaoAirtableShadow(
            leitor, competencia_snapshot_comprovada,
        )
        self._fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(leitor, cnpj_excluido)
        fonte_escopo = FonteEscopoClientesPorInventarioAirtableShadow(leitor)
        fonte_inventario_airtable = FonteInventarioPrestacaoAirtableShadow(leitor)
        self._fonte_dados_correlacao = FonteDadosCorrelacaoEmMemoria() if habilitar_correlacao_transitoria else None
        self._fonte_candidatos_relacao = FonteCandidatosRelacaoDocumentalDoInventario(
            fonte_escopo_clientes=fonte_escopo, fonte_inventario=fonte_inventario_airtable,
            fonte_dados_correlacao=self._fonte_dados_correlacao,
        )

    @property
    def sink(self) -> InventarioPrestacaoEmMemoria:
        """Inventário GERADO por esta execução -- distinto de qualquer
        inventário externo pré-existente (§16 da missão); quem compõe
        pode agregar os dois com `FonteInventarioPrestacaoComposta`
        (`classificacao/fonte_inventario_composta.py`, já existente,
        nunca reimplementada aqui) quando precisar do inventário
        completo para readiness/pacote."""
        return self._sink

    def processar_documento(
        self,
        documento_id: str,
        hash_sha256: str,
        pdf_bytes: Optional[bytes] = None,
        texto: Optional[str] = None,
        cliente_do_ciclo: Optional[ReferenciaCanonica] = None,
        candidatos_colaborador: Sequence[CandidatoFuncionario] = (),
        clientes_broadcast: Tuple[ReferenciaCanonica, ...] = (),
        identificar_pagina: Optional[IdentificadorDePagina] = None,
        personalizar_contexto_do_grupo=None,
        fonte_inventario_pacote: Optional[FonteInventarioPrestacao] = None,
        politica_requisitos: Optional[PoliticaRequisitosPrestacao] = None,
    ) -> Tuple[ResultadoExecucaoCorredorPrestacao, ...]:
        """Entrypoint real (§20 da missão) -- aceita PDF bytes OU texto
        já extraído (exatamente 1 dos 2, nunca os 2 nem nenhum). PDF sem
        texto legível: `extrair_texto_pdf` já devolve string vazia por
        página sem texto (nunca inventa conteúdo); o corredor então
        recebe texto vazio/curto e resolve honestamente para
        TIPO_DESCONHECIDO ou REVISAO_NECESSARIA -- nunca um estado
        NAO_PROCESSAVEL fabricado aqui que não exista no vocabulário já
        estabelecido (`EstadoCorredorDocumentoPrestacao`)."""
        if (pdf_bytes is None) == (texto is None):
            raise ValueError('informe exatamente um entre pdf_bytes e texto, nunca os dois nem nenhum')
        texto_final = extrair_texto_pdf(pdf_bytes) if pdf_bytes is not None else texto

        contexto = ContextoExecucaoCorredorPrestacao(
            documento_id=documento_id, hash_sha256=hash_sha256, paginas=(texto_final,),
            ciclo=self._ciclo, cliente_do_ciclo=cliente_do_ciclo,
            candidatos_colaborador=candidatos_colaborador,
            fonte_vinculos=self._fonte_vinculos,
            fonte_cliente_direto=self._fonte_cliente_direto,
            fonte_unidade_posto=self._fonte_unidade_posto,
            fonte_candidatos_relacao=self._fonte_candidatos_relacao,
            clientes_broadcast=clientes_broadcast,
            identificar_pagina=identificar_pagina,
            personalizar_contexto_do_grupo=personalizar_contexto_do_grupo,
            registrar_dados_correlacao=self._fonte_dados_correlacao is not None,
            fonte_inventario_pacote=fonte_inventario_pacote,
            politica_requisitos=politica_requisitos,
        )
        resultados = executar_documento_readonly(contexto, self._sink)

        if self._fonte_dados_correlacao is not None:
            for resultado in resultados:
                if resultado.dados_correlacao_extraidos is not None:
                    self._fonte_dados_correlacao.registrar(
                        resultado.resultado_corredor.documento_id, resultado.dados_correlacao_extraidos,
                    )
        return resultados
