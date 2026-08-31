"""Orquestrador REAL, READ-ONLY, do corredor `classificacao/` (missão
"CONSTRUIR ORQUESTRADOR REAL READ-ONLY DO CORREDOR V2 + PREPARAR
PRIMEIRO LIVE CONTROLADO SEM EXECUTÁ-LO").

Fecha o achado maior registrado em `docs/decisoes/corredor-live-v2-
bloqueios-reais-v1.md` §1.1: "nenhum orquestrador de produção real
existe hoje para o corredor `classificacao/` -- `ContextoResolucaoDocumento
Prestacao(` só é construído em teste, em todo o repositório."

Este módulo é o "ORQUESTRADOR CANÔNICO/PURO" (§19-A da missão): recebe
só Protocols e valores já resolvidos, nunca importa Airtable/requests/
pdfplumber (confirmado por `test_magnata_os_classificacao_arquitetura_
sem_dependencia_airtable.py`) -- a "COMPOSIÇÃO DE BORDA" que instancia
adapters REAIS e extrai PDF vive em `magnata_os/documental/importacao_
lote/composicao_corredor_readonly.py` (mesma separação já usada em toda
a sessão: Protocol aqui, adapter real lá).

NÃO É "GrandeOrquestrador2" (Fase 20 de `resolucao_documento_prestacao.
py`, princípio preservado aqui): este módulo só COSTURA peças já
existentes, na ordem certa -- nenhuma delas é reimplementada:

  texto/páginas
    -> processar_documento_com_separacao_se_necessaria (já existente)
    -> avancar_para_inventario (já existente)
    -> resolver_relacao_e_avancar (já existente, quando aplicável)

A ÚNICA coisa genuinely NOVA aqui é a ORDEM/COMPOSIÇÃO das 2 decisões
que precisam ser tomadas ANTES de chamar o corredor (porque o corredor
já existente as recebe como VALOR, nunca como fonte a consultar
sozinho -- por desenho, "nunca inventar dado"):

  1. `competencia_esperada`: resolvida aqui via `PoliticaCompetenciaPrestacao.
     competencia_esperada_para(ciclo, cliente_do_ciclo, tipo_provisorio)`
     -- reaproveita a MESMA política pura já existente (`competencia_
     esperada_prestacao.py`, `POLITICA_COMPETENCIA_PRESTACAO_V1`, regra
     SKY Tatuí já registrada), nunca uma segunda regra. `tipo_provisorio`
     vem de uma chamada, SEM efeito colateral, à MESMA ponte semântica
     que o corredor já usa internamente (`resolver_tipo_documental_de_
     texto`) -- chamá-la aqui só para decidir a política de competência
     não duplica a decisão real de tipo (essa continua sendo tomada,
     de novo e com autoridade, dentro de `processar_documento_prestacao`).
     `cliente_do_ciclo`: quando o runner já sabe qual cliente está
     processando (ex.: 1 pasta/manifesto de 1 cliente por vez -- o
     mesmo tipo de conhecimento operacional que `ContextoCicloPrestacao.
     competencia_base` já representa para competência) -- NUNCA
     inferido do documento; `None` cai no default seguro (competência
     base do ciclo, sem deslocamento por cliente).
  2. `cliente_direto`: resolvido aqui via `FonteClienteDiretoDocumento.
     resolver_cliente_direto(texto)` (Protocol já existente, adapter
     real já existente) ANTES de montar o contexto -- porque
     `ContextoResolucaoDocumentoPrestacao.cliente_direto` já é,
     estruturalmente, um VALOR pré-resolvido (nunca uma fonte
     consultada pelo corredor)."""
from __future__ import annotations

import dataclasses
from typing import Optional, Sequence, Tuple

from .competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    ContextoCicloPrestacao,
    PoliticaCompetenciaPrestacao,
)
from .contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from .corredor_relacao_documental import (
    ContextoRelacaoDocumentoPrestacao,
    ResultadoRelacaoDocumentoPrestacao,
    resolver_relacao_e_avancar,
)
from .fonte_candidatos_relacao_documental import FonteCandidatosRelacaoDocumental
from .fonte_cliente_direto_documento import FonteClienteDiretoDocumento
from .inventario_prestacao import FonteInventarioPrestacao
from .inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from .pacote_prestacao import PacotePrestacaoCliente, avaliar_e_montar_pacote
from .politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from .ponte_conteudo_motor_semantico import resolver_tipo_documental_de_texto
from .prestacao_readiness import ItemInventarioPrestacao
from .relacao_documental import DadosCorrelacaoDocumental, extrair_dados_correlacao_de_texto
from .resolucao_documento_prestacao import (
    ContextoResolucaoDocumentoPrestacao,
    EstadoCorredorDocumentoPrestacao,
    ResultadoProcessamentoDocumentoPrestacao,
    avancar_para_inventario,
    processar_documento_com_separacao_se_necessaria,
)
from .separacao_documental import IdentificadorDePagina
from .vinculo_unidade_prestacao import FonteUnidadePostoPrestacao
from .vinculos_prestacao import FonteVinculosPrestacao


def _tipo_provisorio(texto: str) -> Optional[str]:
    """Melhor esforço, sem efeito colateral: consulta a MESMA ponte
    semântica que o corredor usa internamente para decidir tipo
    documental, só para escolher a política de competência esperada
    ANTES de o corredor rodar de verdade. `None` quando não resolve com
    certeza (AMBIGUA/CONFLITO/DESCONHECIDO/texto vazio) -- nunca chuta;
    o pior caso é cair no fallback `competencia_base` sem deslocamento
    por cliente, nunca um erro nem uma competência inventada."""
    if not texto:
        return None
    resolucao = resolver_tipo_documental_de_texto(texto)
    if resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA or len(resolucao.valores_confirmados) != 1:
        return None
    return resolucao.valores_confirmados[0].entidade_id


def _competencia_tupla(referencia: ReferenciaCanonica) -> Tuple[int, int]:
    ano_texto, mes_texto = referencia.entidade_id.split('-', maxsplit=1)
    return (int(ano_texto), int(mes_texto))


@dataclasses.dataclass(frozen=True)
class ContextoExecucaoCorredorPrestacao:
    """Entrada do orquestrador -- só o necessário, nada de segredo/token/
    objeto HTTP cru/registro Airtable bruto/payload externo (§5 da
    missão). Fontes/adapters são sempre Protocols, injetados por quem
    compõe a borda -- este módulo nunca sabe se são reais ou fakes."""

    documento_id: str
    hash_sha256: str
    paginas: Tuple[str, ...]
    """Texto já extraído, por página -- 1 elemento quando a extração
    real disponível hoje (`extracao_texto.extrair_texto_pdf`) foi usada
    (ela devolve 1 string já concatenada, sem separação por página --
    limitação honesta desta V1, registrada no ADR: separação master
    automática via páginas reais precisa de uma extração por página que
    não existe hoje, não fabricada aqui); N elementos quando quem chama
    já tem o texto por página (ex.: teste, ou uma extração futura)."""
    ciclo: ContextoCicloPrestacao
    cliente_do_ciclo: Optional[ReferenciaCanonica] = None
    """Cliente que ESTE RUN já sabe que está processando (ex.: 1 pasta/
    manifesto de 1 cliente) -- NUNCA inferido do documento. Usado só
    para escolher a política de competência esperada (§1 do módulo);
    `None` é seguro (cai no default sem deslocamento por cliente)."""
    politica_competencia: PoliticaCompetenciaPrestacao = POLITICA_COMPETENCIA_PRESTACAO_V1
    candidatos_colaborador: Sequence = ()
    fonte_vinculos: Optional[FonteVinculosPrestacao] = None
    fonte_cliente_direto: Optional[FonteClienteDiretoDocumento] = None
    fonte_unidade_posto: Optional[FonteUnidadePostoPrestacao] = None
    fonte_candidatos_relacao: Optional[FonteCandidatosRelacaoDocumental] = None
    clientes_broadcast: Tuple[ReferenciaCanonica, ...] = ()
    identificar_pagina: Optional[IdentificadorDePagina] = None
    personalizar_contexto_do_grupo: Optional[object] = None
    registrar_dados_correlacao: bool = False
    """Quando `True`, os `dados_correlacao` extraídos do texto deste
    documento são devolvidos no resultado para que quem compõe a borda
    decida se registra numa `FonteDadosCorrelacaoEmMemoria` transitória
    (§13/§14 da missão) -- este módulo NUNCA persiste nada sozinho,
    nunca decide se a correlação transitória é apropriada para a
    execução corrente."""
    fonte_inventario_pacote: Optional[FonteInventarioPrestacao] = None
    """Fonte de inventário usada só para MONTAR o pacote lógico deste
    documento (§17/§18 da missão) -- deliberadamente SEPARADA do `sink`
    (§16: "distinguir inventário externo pré-existente vs inventário
    gerado neste run"); quem compõe decide se é o próprio `sink`, uma
    fonte externa, ou uma `FonteInventarioPrestacaoComposta` (já
    existente) agregando os dois. `None` (default) -- nenhum pacote é
    montado, nunca um pacote fabricado sem fonte real."""
    politica_requisitos: Optional[PoliticaRequisitosPrestacao] = None
    """Necessária junto com `fonte_inventario_pacote` para montar
    pacote/readiness -- os 2 precisam estar presentes, nunca só 1."""


@dataclasses.dataclass(frozen=True)
class ResultadoExecucaoCorredorPrestacao:
    """Saída do orquestrador -- 1 por documento efetivamente processado
    (1 quando não houve separação master; N quando houve, 1 por
    filho)."""

    resultado_corredor: ResultadoProcessamentoDocumentoPrestacao
    itens_inventario: Tuple[ItemInventarioPrestacao, ...] = ()
    resolucao_relacao: Optional[ResultadoRelacaoDocumentoPrestacao] = None
    dados_correlacao_extraidos: Optional[DadosCorrelacaoDocumental] = None
    pacote: Optional[PacotePrestacaoCliente] = None
    """Montado (§17/§18 da missão) só quando `fonte_inventario_pacote` +
    `politica_requisitos` foram informados E a dimensão CLIENTE deste
    documento resolveu para EXATAMENTE 1 valor -- nunca um pacote
    "médio"/agregado para múltiplos clientes (broadcast/vínculo
    múltiplo) fabricado aqui; esses casos ficam `None`, nunca um
    palpite de qual cliente o pacote representaria."""


def executar_documento_readonly(
    contexto: ContextoExecucaoCorredorPrestacao, sink: InventarioPrestacaoEmMemoria,
) -> Tuple[ResultadoExecucaoCorredorPrestacao, ...]:
    """Entrypoint canônico -- production-callable (§20 da missão): monta
    o `ContextoResolucaoDocumentoPrestacao`, chama o corredor já
    existente, avança para inventário, e (quando aplicável) resolve
    relação documental. NUNCA escreve externamente -- só no `sink`
    local/in-memory já existente (mesma disciplina de `resolver_relacao_
    e_avancar`/`avancar_para_inventario`, nunca alterada aqui)."""
    texto_completo = '\n'.join(contexto.paginas) if contexto.paginas else ''

    cliente_direto: Optional[ReferenciaCanonica] = None
    if contexto.fonte_cliente_direto is not None and texto_completo:
        cliente_direto = contexto.fonte_cliente_direto.resolver_cliente_direto(texto_completo)

    competencia_esperada: Optional[Tuple[int, int]] = None
    if contexto.cliente_do_ciclo is not None:
        tipo_provisorio = _tipo_provisorio(texto_completo)
        competencia_esperada = contexto.politica_competencia.competencia_esperada_para(
            contexto.ciclo, contexto.cliente_do_ciclo, tipo_provisorio or '',
        )
    elif contexto.ciclo is not None:
        competencia_esperada = contexto.ciclo.competencia_base

    contexto_base = ContextoResolucaoDocumentoPrestacao(
        documento_id=contexto.documento_id,
        hash_sha256=contexto.hash_sha256,
        competencia_esperada=competencia_esperada,
        candidatos_colaborador=contexto.candidatos_colaborador,
        fonte_vinculos=contexto.fonte_vinculos,
        cliente_direto=cliente_direto,
        fonte_unidade_posto=contexto.fonte_unidade_posto,
    )

    resultados_corredor = processar_documento_com_separacao_se_necessaria(
        list(contexto.paginas), contexto_base,
        identificar_pagina=contexto.identificar_pagina,
        personalizar_contexto_do_grupo=contexto.personalizar_contexto_do_grupo,
    )

    saida = []
    for resultado in resultados_corredor:
        itens = avancar_para_inventario(resultado, sink, contexto.clientes_broadcast)

        dados_correlacao_extraidos = None
        resolucao_relacao = None
        if resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU and resultado.tipo_documental:
            texto_filho = texto_completo  # separação master reusa o mesmo texto de origem por filho hoje (paginas nao fatiadas por filho neste nivel -- o corredor de separação já cuidou da fatia real internamente; aqui só extraímos correlação do texto completo, honesto para o caso unitário, que é o caso real hoje)
            # Extraída sempre que qualquer um dos 2 usos existir --
            # registro transitório (devolvida no resultado só quando
            # pedido, nunca decidido aqui) OU uso imediato deste MESMO
            # documento como comprovante (abaixo). Extrair 2x nunca
            # aconteceu -- 1 chamada, 2 destinos possíveis.
            dados_correlacao_deste_documento = None
            if contexto.registrar_dados_correlacao or contexto.fonte_candidatos_relacao is not None:
                dados_correlacao_deste_documento = extrair_dados_correlacao_de_texto(texto_filho)
            if contexto.registrar_dados_correlacao:
                dados_correlacao_extraidos = dados_correlacao_deste_documento

            if contexto.fonte_candidatos_relacao is not None:
                resolucao_competencia = next(
                    (
                        r for r in resultado.resolucao_semantica.resolucoes
                        if r.dimensao == DimensaoResolucao.COMPETENCIA
                    ),
                    None,
                )
                if (
                    resolucao_competencia is not None
                    and resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA
                    and len(resolucao_competencia.valores_confirmados) == 1
                ):
                    competencia_doc = _competencia_tupla(resolucao_competencia.valores_confirmados[0])
                    contexto_relacao = ContextoRelacaoDocumentoPrestacao(
                        documento_id=resultado.documento_id,
                        tipo_documental=resultado.tipo_documental,
                        competencia=competencia_doc,
                        dados_correlacao=dados_correlacao_deste_documento or DadosCorrelacaoDocumental(),
                        fonte_candidatos=contexto.fonte_candidatos_relacao,
                    )
                    resolucao_relacao = resolver_relacao_e_avancar(contexto_relacao, sink)

        pacote = None
        if (
            resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
            and contexto.fonte_inventario_pacote is not None
            and contexto.politica_requisitos is not None
        ):
            resolucao_cliente = next(
                (r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.CLIENTE),
                None,
            )
            resolucao_competencia_pacote = next(
                (r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.COMPETENCIA),
                None,
            )
            if (
                resolucao_cliente is not None
                and resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
                and len(resolucao_cliente.valores_confirmados) == 1
                and resolucao_competencia_pacote is not None
                and resolucao_competencia_pacote.estado == EstadoResolucaoDimensao.RESOLVIDA
                and len(resolucao_competencia_pacote.valores_confirmados) == 1
            ):
                pacote = avaliar_e_montar_pacote(
                    cliente=resolucao_cliente.valores_confirmados[0],
                    competencia=resolucao_competencia_pacote.valores_confirmados[0],
                    resolucao=resultado.resolucao_semantica,
                    fonte_inventario=contexto.fonte_inventario_pacote,
                    politica=contexto.politica_requisitos,
                )

        saida.append(ResultadoExecucaoCorredorPrestacao(
            resultado_corredor=resultado, itens_inventario=itens,
            resolucao_relacao=resolucao_relacao, dados_correlacao_extraidos=dados_correlacao_extraidos,
            pacote=pacote,
        ))
    return tuple(saida)
