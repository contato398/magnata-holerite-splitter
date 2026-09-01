"""COMPOSIÇÃO DE BORDA do orquestrador real read-only (missão
"CONSTRUIR ORQUESTRADOR REAL READ-ONLY DO CORREDOR V2 + PREPARAR
PRIMEIRO LIVE CONTROLADO SEM EXECUTÁ-LO", §19-B; corrigida pelo
"CHECKPOINT FINAL PRÉ-MERGE — PR #110 — CORRIGIR INVENTÁRIO DA
CORRELAÇÃO TRANSITÓRIA").

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

CORREÇÃO (checkpoint final pré-merge ao PR #110, achado real): a
primeira versão desta composição injetava `FonteInventarioPrestacao
AirtableShadow` (só Airtable) direto em `FonteCandidatosRelacaoDocumental
DoInventario` -- um documento processado NESTA execução (que entra em
`self._sink`, nunca escrito no Airtable, por desenho read-only) NUNCA
seria encontrado como candidato por um comprovante processado depois,
no MESMO run. Corrigido com o contrato já existente e nunca
reimplementado, `FonteInventarioPrestacaoComposta`
(`classificacao/fonte_inventario_composta.py`): agrega o inventário
Airtable (externo) com `self._sink` (local, gerado neste run),
deduplicando por `identidade_logica` -- o mesmo documento presente nos
2 nunca vira 2 candidatos.

Mesma correção aplicada ao ESCOPO de clientes: `FonteEscopoClientesPor
InventarioAirtableShadow` sozinha só enxerga clientes com registro NO
AIRTABLE para a competência -- um cliente cujo ÚNICO rastro é o
documento processado neste run (nunca escrito externamente) nunca
apareceria no escopo, e a busca de candidatos nem chegaria a olhar o
inventário local dele. Corrigido com `_EscopoClientesComCicloConhecido`
(abaixo): quando `cliente_do_ciclo` é conhecido (§15 da missão -- "o
cliente é explicitamente conhecido pelo escopo do run... é válido
injetá-lo como contexto operacional, mas nunca inferido do documento"),
ele é sempre incluído no escopo, além do que o Airtable já devolver --
nunca um cliente NOVO inventado, só o que já foi DECLARADO por quem
constrói a execução.

`cliente_do_ciclo` passou de parâmetro por-documento (`processar_
documento`) para parâmetro da EXECUÇÃO inteira (`ExecucaoCorredorReadonly.
__init__`) -- reflete melhor o uso real (§15 da missão: "1 pasta/
manifesto de 1 cliente por vez", o mesmo tipo de conhecimento
operacional que `ContextoCicloPrestacao.competencia_base` já representa
para competência) e permite construir o escopo aumentado UMA VEZ, com o
mesmo ciclo de vida do `sink`. `None` (default) preserva o
comportamento anterior -- nenhum cliente extra incluído no escopo,
nenhuma política de competência por cliente aplicada.

Correlação transitória (§13/§14 da missão): `FonteDadosCorrelacaoEm
Memoria` é injetada UMA VEZ por execução (`ExecucaoCorredorReadonly`,
abaixo) e SOBREVIVE só enquanto o objeto Python existir -- reiniciar o
processo apaga tudo. Isso NUNCA é chamado de persistência (docstring
de `FonteDadosCorrelacaoEmMemoria`, preservada): é só um cache local
de UMA execução controlada, exatamente o que o §13 da missão pede."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_relacao_documental_do_inventario import (
    FonteCandidatosRelacaoDocumentalDoInventario,
    FonteDadosCorrelacaoEmMemoria,
    FonteEscopoClientesPrestacao,
)
from magnata_os.classificacao.fonte_inventario_composta import FonteInventarioPrestacaoComposta
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
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
from .adapters.airtable_colaboradores_esperados_prestacao import (
    FonteColaboradoresEsperadosPrestacaoAirtableShadow,
)
from .adapters.airtable_inventario_prestacao import (
    FonteEscopoClientesPorInventarioAirtableShadow,
    FonteInventarioPrestacaoAirtableShadow,
)
from .adapters.airtable_leitura import LeitorAirtableSomenteLeitura
from .adapters.airtable_unidade_posto_prestacao import FonteUnidadePostoPrestacaoAirtableShadow
from .adapters.airtable_vinculos_prestacao import FonteVinculosPrestacaoAirtableShadow


class _EscopoClientesComCicloConhecido:
    """Aumenta um `FonteEscopoClientesPrestacao` real com o cliente que
    a EXECUÇÃO já sabe que está processando (`cliente_do_ciclo`) --
    NUNCA inferido do documento, só o que foi explicitamente declarado
    por quem construiu `ExecucaoCorredorReadonly` (§15 da missão).
    Nunca substitui a fonte base -- só garante que o cliente conhecido
    nunca fica de fora do escopo só porque o Airtable ainda não tem
    registro dele para aquela competência (ex.: o único rastro de um
    cliente é um documento processado NESTE MESMO run, nunca escrito
    externamente)."""

    def __init__(self, fonte_base: FonteEscopoClientesPrestacao, cliente_do_ciclo: ReferenciaCanonica):
        self._fonte_base = fonte_base
        self._cliente_do_ciclo = cliente_do_ciclo

    def escopo_para_competencia(self, competencia: ReferenciaCanonica) -> Tuple[ReferenciaCanonica, ...]:
        base = self._fonte_base.escopo_para_competencia(competencia)
        if self._cliente_do_ciclo in base:
            return base
        return base + (self._cliente_do_ciclo,)


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
    honestamente NAO_ENCONTRADA sem prova).

    `cliente_do_ciclo`: cliente que ESTA EXECUÇÃO inteira já sabe que
    está processando (§15 da missão) -- nunca inferido do documento.
    Usado para (a) a política de competência esperada por documento
    (repassado a cada `processar_documento`) e (b) aumentar o escopo de
    candidatos de relação (`_EscopoClientesComCicloConhecido`, acima) --
    as 2 únicas formas seguras de usar um cliente já DECLARADO, nunca
    descoberto."""

    def __init__(
        self,
        leitor: LeitorAirtableSomenteLeitura,
        ciclo: ContextoCicloPrestacao,
        competencia_snapshot_comprovada: Optional[Tuple[int, int]] = None,
        cnpj_excluido: Optional[str] = None,
        habilitar_correlacao_transitoria: bool = False,
        cliente_do_ciclo: Optional[ReferenciaCanonica] = None,
    ) -> None:
        self._ciclo = ciclo
        self._cliente_do_ciclo = cliente_do_ciclo
        self._sink = InventarioPrestacaoEmMemoria()
        self._fonte_vinculos = FonteVinculosPrestacaoAirtableShadow(leitor)
        self._fonte_unidade_posto = FonteUnidadePostoPrestacaoAirtableShadow(
            leitor, competencia_snapshot_comprovada,
        )
        self._fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(leitor, cnpj_excluido)

        fonte_escopo: FonteEscopoClientesPrestacao = FonteEscopoClientesPorInventarioAirtableShadow(leitor)
        if cliente_do_ciclo is not None:
            fonte_escopo = _EscopoClientesComCicloConhecido(fonte_escopo, cliente_do_ciclo)

        # Externo (Airtable) + local (gerado neste run, self._sink) --
        # nunca só um dos 2 (ver docstring do módulo). Dedup por
        # identidade_logica já garantido por FonteInventarioPrestacaoComposta,
        # nunca reimplementado aqui.
        self._fonte_inventario_composta = FonteInventarioPrestacaoComposta((
            FonteInventarioPrestacaoAirtableShadow(leitor), self._sink,
        ))

        self._fonte_dados_correlacao = FonteDadosCorrelacaoEmMemoria() if habilitar_correlacao_transitoria else None
        self._fonte_candidatos_relacao = FonteCandidatosRelacaoDocumentalDoInventario(
            fonte_escopo_clientes=fonte_escopo, fonte_inventario=self._fonte_inventario_composta,
            fonte_dados_correlacao=self._fonte_dados_correlacao,
        )

        # Adendo "HOLERITE MULTICOLABORADOR NO CICLO REAL" -- mesmo
        # adapter real já existente (`FonteColaboradoresEsperadosPrestacaoAirtableShadow`,
        # nunca reimplementado), agora wired ao MESMO `leitor` desta
        # execução. Nenhuma regra de negócio nova: só conecta, na borda
        # real, uma fonte que já existia isolada (nunca chamada com
        # Airtable live antes desta missão) ao restante da composição --
        # fechando o gap real que causou a leitura equivocada de "8
        # candidatos" no primeiro live (Holerite é granularidade
        # colaborador, 1:N por cliente/competência -- nunca "escolher 1
        # entre N"; ver docs/decisoes/holerite-multicolaborador-ciclo-real-v1.md).
        self._fonte_colaboradores_esperados = FonteColaboradoresEsperadosPrestacaoAirtableShadow(leitor)

    @property
    def fonte_colaboradores_esperados(self) -> FonteColaboradoresEsperadosPrestacaoAirtableShadow:
        """Fonte real (Cliente -> Locais -> Funcionários Ativos) de
        colaboradores esperados por cliente/competência, wired ao MESMO
        `leitor` desta execução -- reaproveitada, nunca reimplementada.

        Uso pretendido: DEPOIS de processar os N documentos do ciclo via
        `processar_documento` (esta fonte não participa de nenhuma
        resolução por-documento), avaliar a obrigatoriedade do Holerite
        por CARDINALIDADE colaborador --

            colaboradores = execucao.fonte_colaboradores_esperados.colaboradores_esperados_para(cliente, ciclo)
            resultado_holerite = avaliar_obrigatoriedade_holerite(
                cliente, competencia, colaboradores, execucao.fonte_inventario_completa.listar(cliente, competencia))
            pacote = combinar_pacote_com_holerite(pacote, resultado_holerite)

        (`holerite_obrigatorio_prestacao.py`/`pacote_prestacao.py`, já
        existentes, nunca alterados aqui) -- mesma composição que
        `ciclo_prestacao.executar_ciclo_prestacao` já faz na camada pura,
        agora disponível também na borda real, sem duplicar a lógica."""
        return self._fonte_colaboradores_esperados

    @property
    def sink(self) -> InventarioPrestacaoEmMemoria:
        """Inventário GERADO só por esta execução -- para inspeção
        direta (ex.: teste). Para readiness/pacote, preferir `fonte_
        inventario_completa` (abaixo), que já enxerga externo + local
        compostos."""
        return self._sink

    @property
    def fonte_inventario_completa(self) -> FonteInventarioPrestacaoComposta:
        """Externo (Airtable) + local (`sink`, gerado nesta execução),
        já compostos e deduplicados -- a MESMA fonte usada internamente
        para descoberta de candidatos de relação (`__init__`). Reusar
        aqui (`processar_documento(..., fonte_inventario_pacote=
        execucao.fonte_inventario_completa, ...)`) evita que readiness/
        pacote vejam só o inventário externo e percam um documento
        processado neste mesmo run (achado do checkpoint final
        pré-merge ao PR #110, §7 -- mesma classe de bug do candidato de
        relação, fechada aqui de uma vez para as 2 capacidades)."""
        return self._fonte_inventario_composta

    def processar_documento(
        self,
        documento_id: str,
        hash_sha256: str,
        pdf_bytes: Optional[bytes] = None,
        texto: Optional[str] = None,
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
        estabelecido (`EstadoCorredorDocumentoPrestacao`).

        `cliente_do_ciclo` é da EXECUÇÃO (`__init__`), não deste método
        -- nunca varia por chamada dentro da mesma execução (§15 da
        missão: é conhecimento operacional do RUN, não do documento)."""
        if (pdf_bytes is None) == (texto is None):
            raise ValueError('informe exatamente um entre pdf_bytes e texto, nunca os dois nem nenhum')
        texto_final = extrair_texto_pdf(pdf_bytes) if pdf_bytes is not None else texto

        contexto = ContextoExecucaoCorredorPrestacao(
            documento_id=documento_id, hash_sha256=hash_sha256, paginas=(texto_final,),
            ciclo=self._ciclo, cliente_do_ciclo=self._cliente_do_ciclo,
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
