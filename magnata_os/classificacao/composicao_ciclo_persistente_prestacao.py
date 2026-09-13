"""Composição persistente REAL de ciclos de Prestação de Contas — V1.

FLUXO COMPLETO:

1. Criar ou retomar ExecucaoPrestacao (rastreamento UUID opaco)
2. Executar ciclo_prestacao primeira vez (necessidades documentais)
3. Aquisição readonly por NecessidadeDocumentoPrestacao (porta injetável)
4. Resolução semântica segura
5. Inventário em memória + deduplicação
6. FonteInventarioPrestacaoComposta (base + adquirido)
7. Executar ciclo_prestacao segunda vez (com inventário recomposto)
8. Readiness e pacote lógico
9. Atualizar ExecucaoPrestacao com estado final

Nenhum componente é alterado, todos reutilizados em estado puro.
Dependências injetadas; zero Airtable/psycopg/S3 no domínio.
SEM efeitos colaterais em aquisição; RepositorioExecucoesPrestacao injetado.

CORREÇÃO PÓS-MERGE PR #158 (branch fix/prestacao-pos-pr158-v1): a
versão mesclada em `main` (commit 5da729f) corrigiu parcialmente o
placeholder de extração original, mas manteve 3 problemas fechados
aqui:
  (a) extração usava `extrair_texto_pdf` cru, sem decisão de MIME --
      agora `extrair_texto_seguro` (`roteamento_documental.py`, já
      existente) + checagem explícita de `mime_type`;
  (b) o dict `erros_aquisicao` era escrito e nunca lido em lugar
      nenhum -- observabilidade inexistente apesar do nome; substituído
      por `logging` real, eventos estáveis, nunca `str(exc)` cru;
  (c) uma heurística nova classificava exceção terminal por substring
      de mensagem (`'execucao_prestacao' in str(exc).lower()`) --
      revertida; ver docstring de `executar_ciclo_prestacao_persistente`
      para o rollback completo.
Ver também `_adquirir_inventario_via_corredor`, extraída para tornar o
caminho documento->blob->extração->corredor testável isoladamente
(nenhum teste anterior populava `resolucoes_ancora`/
`competencias_por_cliente`, então esse laço nunca era exercitado de
verdade)."""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Mapping, Optional, Protocol, Sequence, Tuple

from .ciclo_prestacao import (
    ContextoCicloPrestacao,
    NecessidadeDocumentoPrestacao,
    ResultadoCicloPrestacao,
    executar_ciclo_prestacao,
)
from .competencia_esperada_prestacao import PoliticaCompetenciaPrestacao
from .contratos import ReferenciaCanonica, ResultadoResolucaoSemantico
from .execucao_prestacao import (
    ExecucaoPrestacao,
    RepositorioExecucoesPrestacao,
    criar_execucao_prestacao,
)
from magnata_os.documental.modulo01.armazenamento import ArquivoNaoEncontrado
from magnata_os.documental.modulo01.dominio import Documento
from .fonte_clientes_prestacao import FonteClientesPrestacao
from .fonte_colaboradores_esperados_prestacao import (
    FonteColaboradoresEsperadosPrestacao,
)
from .fonte_inventario_composta import FonteInventarioPrestacaoComposta
from .fonte_requisitos_prestacao import FonteRequisitosPrestacao
from .inventario_prestacao import FonteInventarioPrestacao
from .orquestrador_corredor_readonly import (
    ContextoExecucaoCorredorPrestacao,
    executar_documento_readonly,
)
from .inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from .normalizacao_requisitos_prestacao import (
    TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL,
)
from .pacote_prestacao import EstadoPacotePrestacao, PacotePrestacaoCliente
from .politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from .prestacao_readiness import (
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
from .roteamento_documental import extrair_texto_seguro

_logger = logging.getLogger(__name__)

# Nomes de evento ESTÁVEIS para observabilidade da aquisição (correção
# pós-merge PR #158, Incremento 3) -- campo próprio no registro de log
# (`extra={'evento': ...}`), nunca embutidos só em frase livre. Isso
# permite filtrar/agregar por evento sem depender de parsing de texto
# humano, preparando o caminho para observabilidade futura (ex.:
# métricas, alertas) sem reescrever quem loga. Mesmo idioma já adotado
# em `magnata_os/orquestrador/observabilidade.py`: só campos seguros
# (identificadores, nome de tipo de exceção), nunca `str(exc)` cru,
# nunca conteúdo do documento.
EVENTO_BLOB_NAO_ENCONTRADO = 'blob_nao_encontrado'
EVENTO_BLOB_FALHA_LEITURA = 'blob_falha_leitura'
EVENTO_MIME_NAO_SUPORTADO = 'mime_nao_suportado'
EVENTO_PDF_ILEGIVEL = 'pdf_ilegivel'
EVENTO_CORREDOR_FALHOU = 'corredor_falhou'


# ==== AQUISIÇÃO CANÔNICA (COM CORREDOR) ====
# REUTILIZA: RepositorioDocumentos.listar_todos() para fonte de documentos brutos
# Não precisa de Protocol separado — o repositório existente já fornece esta função


# ==== CONTEXT DE DEPENDÊNCIAS ====


@dataclasses.dataclass(frozen=True)
class ContextoComposicaoPrestacao:
    """Contexto com todas as dependências para execução persistente."""

    competencia_base: str
    """Competência base (ex: "2026-09")."""

    fonte_clientes: FonteClientesPrestacao
    fonte_requisitos: FonteRequisitosPrestacao
    repositorio_execucoes: RepositorioExecucoesPrestacao
    """Fontes e persistência — injetadas."""

    requisitos_base: Tuple[RequisitoDocumentalPrestacao, ...] = ()
    """Política base de requisitos."""

    resolucoes_ancora: Mapping[ReferenciaCanonica, ResultadoResolucaoSemantico] = dataclasses.field(default_factory=dict)
    """Resolução semântica por cliente."""

    competencias_por_cliente: Mapping[ReferenciaCanonica, ReferenciaCanonica] = dataclasses.field(default_factory=dict)
    """Competência efetiva já resolvida por cliente."""

    politica_competencia: Optional[PoliticaCompetenciaPrestacao] = None
    """Política de competência (ex: SKY Tatuí offset)."""

    fonte_colaboradores_esperados: Optional[FonteColaboradoresEsperadosPrestacao] = None
    """Fonte de colaboradores esperados (Holerite, Folha)."""

    fonte_inventario_base: Optional[FonteInventarioPrestacao] = None
    """Fonte de inventário base pré-existente (Airtable shadow, etc.).
    Opcional — se não fornecida, composição usa somente inventário adquirido."""

    repositorio_documentos: Optional[object] = None
    """Repositório de documentos para aquisição canônica.
    Reutiliza RepositorioDocumentos.listar_todos() da camada documental.
    Opcional — se não fornecido, composição roda sem aquisição de novos documentos."""

    armazenamento_arquivos: Optional[object] = None
    """Armazenamento de blobs para recuperar conteúdo do documento.
    Necessário junto com repositorio_documentos para aquisição.
    Reutiliza ArmazenamentoArquivos da camada documental."""

    tipos_obrigatorios_por_colaborador: Tuple[str, ...] = ('Holerite da Folha de Pagamento',)
    """Tipos obrigatórios por cardinalidade colaborador."""


# ==== FUNÇÕES PRIMITIVAS (INCREMENTO 1 — revisadas) ====


def criar_e_persistir_execucao(
    competencia_base: str,
    repositorio_execucoes: RepositorioExecucoesPrestacao,
    origem: str = 'composicao-ciclo-persistente-v1',
) -> ExecucaoPrestacao:
    """Cria e persiste uma ExecucaoPrestacao nova."""
    try:
        ano_str, mes_str = competencia_base.split('-')
        _ano = int(ano_str)
        _mes = int(mes_str)
        if not (1 <= _mes <= 12):
            raise ValueError('mês deve estar entre 01 e 12')
    except (ValueError, IndexError) as e:
        raise ValueError(f'competencia_base deve estar em formato AAAA-MM: {competencia_base}') from e

    execucao = criar_execucao_prestacao(
        competencia_base=competencia_base,
        origem=origem,
    )
    repositorio_execucoes.criar(execucao)
    return execucao


def retomar_execucao_por_id(
    execucao_prestacao_id: str,
    repositorio_execucoes: RepositorioExecucoesPrestacao,
) -> ExecucaoPrestacao:
    """Retoma uma ExecucaoPrestacao em estado INICIADA."""
    execucao = repositorio_execucoes.buscar_por_id(execucao_prestacao_id)
    if not execucao:
        raise ValueError(f'ExecucaoPrestacao {execucao_prestacao_id} não encontrada')
    if execucao.estado != 'INICIADA':
        raise ValueError(
            f'ExecucaoPrestacao {execucao_prestacao_id} estado={execucao.estado} '
            f'(apenas INICIADA é retomável)'
        )
    return execucao


def atualizar_execucao_por_estado_pacote(
    execucao_prestacao_id: str,
    estado_pacote: EstadoPacotePrestacao,
    repositorio_execucoes: RepositorioExecucoesPrestacao,
) -> ExecucaoPrestacao:
    """Atualiza ExecucaoPrestacao baseado no estado final do pacote.

    Lógica:
    - PRONTO → CONCLUIDA + concluido_em
    - outro (INCOMPLETO, EM_REVISAO) → INICIADA (retomável)

    NOTA: BLOQUEADO é condição de negócio/documental,
    não erro terminal. Permanece INICIADA.
    """
    if estado_pacote == EstadoPacotePrestacao.PRONTO:
        novo_estado = 'CONCLUIDA'
        concluido_em = datetime.now(timezone.utc)
    else:
        # INCOMPLETO, EM_REVISAO, BLOQUEADO → retomável
        novo_estado = 'INICIADA'
        concluido_em = None

    repositorio_execucoes.atualizar_estado(
        execucao_prestacao_id=execucao_prestacao_id,
        novo_estado=novo_estado,
        concluido_em=concluido_em,
    )

    # Recuperar execução atualizada
    execucao_final = repositorio_execucoes.buscar_por_id(execucao_prestacao_id)
    if not execucao_final:
        raise ValueError(
            f'ExecucaoPrestacao {execucao_prestacao_id} desapareceu após atualização'
        )
    return execucao_final


# ==== INCREMENTO 3: FLUXO REAL COMPLETO ====


def _adquirir_inventario_via_corredor(
    contexto: 'ContextoComposicaoPrestacao',
    ciclo_para_corredor: ContextoCicloPrestacao,
) -> InventarioPrestacaoEmMemoria:
    """Aquisição canônica: para cada Documento bruto já persistido
    (`contexto.repositorio_documentos`), recupera o blob
    (`contexto.armazenamento_arquivos`), extrai o texto pelo extrator
    canônico já existente e executa o corredor, escrevendo no
    inventário em memória devolvido.

    Extraída de `executar_ciclo_prestacao_persistente` (correção
    pós-merge PR #158, Incremento 2) para ser testável isoladamente:
    nenhum teste hoje popula `contexto.resolucoes_ancora`/
    `contexto.competencias_por_cliente`, o que faz `executar_ciclo_
    prestacao` descartar todo cliente antes de gerar `necessidades` --
    sem essa extração, o corpo deste laço nunca é exercitado por
    nenhum teste (confirmado empiricamente na auditoria pós-merge:
    `executar_documento_readonly` chamado 0 vezes mesmo com
    `requisitos_base` preenchido). Mesmo comportamento observável de
    antes; `executar_ciclo_prestacao_persistente` só passou a chamar
    esta função no lugar do laço inline.

    Observabilidade (Incremento 3): cada ponto de falha loga um evento
    ESTÁVEL (`EVENTO_*`, campo próprio, nunca só texto livre) com
    `documento_id`/`hash_sha256` e, quando aplicável,
    `type(exc).__name__` -- NUNCA `str(exc)` cru, nunca conteúdo do
    documento ou PII. Substitui o dict `erros_aquisicao` de `5da729f`,
    que era escrito e nunca lido em lugar nenhum -- observabilidade
    inexistente apesar do nome. 1 documento com problema nunca impede o
    processamento dos demais (mesma política de isolamento já
    existente antes desta correção)."""
    inventario_adquirido = InventarioPrestacaoEmMemoria()
    if not (contexto.repositorio_documentos and contexto.armazenamento_arquivos):
        return inventario_adquirido

    documentos_disponiveis = contexto.repositorio_documentos.listar_todos()

    for documento_bruto in documentos_disponiveis:
        # Recuperar conteúdo do blob pelo hash. Distinguir
        # explicitamente "não encontrado" (`ArquivoNaoEncontrado`, já
        # existente em `armazenamento.py`) de "encontrado mas falhou ao
        # ler" (qualquer outra exceção do backend) -- os dois eram o
        # mesmo `continue` silencioso antes desta correção.
        try:
            with contexto.armazenamento_arquivos.abrir_leitura(
                documento_bruto.hash_sha256
            ) as arquivo:
                conteudo_bytes = arquivo.read()
        except ArquivoNaoEncontrado:
            _logger.warning(
                '%s documento_id=%s hash_sha256=%s',
                EVENTO_BLOB_NAO_ENCONTRADO,
                documento_bruto.documento_id, documento_bruto.hash_sha256,
                extra={
                    'evento': EVENTO_BLOB_NAO_ENCONTRADO,
                    'documento_id': documento_bruto.documento_id,
                    'hash_sha256': documento_bruto.hash_sha256,
                },
            )
            continue
        except Exception as exc:
            # Encontrado mas falhou ao ler -- nunca confundir com
            # "documento ausente". Só o TIPO da exceção é logado, nunca
            # a mensagem crua (pode ecoar conteúdo do backend de
            # armazenamento).
            _logger.error(
                '%s documento_id=%s hash_sha256=%s exception_type=%s',
                EVENTO_BLOB_FALHA_LEITURA,
                documento_bruto.documento_id, documento_bruto.hash_sha256,
                type(exc).__name__,
                extra={
                    'evento': EVENTO_BLOB_FALHA_LEITURA,
                    'documento_id': documento_bruto.documento_id,
                    'hash_sha256': documento_bruto.hash_sha256,
                    'exception_type': type(exc).__name__,
                },
            )
            continue

        # Extração canônica segura, com decisão explícita de MIME
        # (correção pós-merge PR #158, Incremento 2): reutiliza
        # `extrair_texto_seguro` (`classificacao/roteamento_documental.py`,
        # já existente), que por sua vez reaproveita `extrair_texto_pdf`
        # (`documental/extracao_texto.py`) -- mesma extração usada por
        # `processar_holerite`/`processar_extrato` e pelo roteamento
        # avulso. Nenhum parser novo. Só `application/pdf` tem extrator
        # canônico no repositório hoje -- mime não suportado nunca entra
        # no extrator, vira um caminho próprio, distinto de "PDF
        # ilegível".
        if documento_bruto.mime_type != 'application/pdf':
            _logger.warning(
                '%s documento_id=%s hash_sha256=%s mime_type=%s',
                EVENTO_MIME_NAO_SUPORTADO,
                documento_bruto.documento_id, documento_bruto.hash_sha256,
                documento_bruto.mime_type,
                extra={
                    'evento': EVENTO_MIME_NAO_SUPORTADO,
                    'documento_id': documento_bruto.documento_id,
                    'hash_sha256': documento_bruto.hash_sha256,
                    'mime_type': documento_bruto.mime_type,
                },
            )
            continue

        texto_documento = extrair_texto_seguro(conteudo_bytes)
        if texto_documento is None:
            # PDF corrompido/ilegível (ex.: escaneado sem OCR) -- mesma
            # distinção honesta já feita por `extrair_texto_seguro`:
            # nunca uma string vazia tratada como classificável.
            _logger.warning(
                '%s documento_id=%s hash_sha256=%s',
                EVENTO_PDF_ILEGIVEL,
                documento_bruto.documento_id, documento_bruto.hash_sha256,
                extra={
                    'evento': EVENTO_PDF_ILEGIVEL,
                    'documento_id': documento_bruto.documento_id,
                    'hash_sha256': documento_bruto.hash_sha256,
                },
            )
            continue

        # Construir contexto para o corredor (todas as dependências são opcionais)
        contexto_corredor = ContextoExecucaoCorredorPrestacao(
            documento_id=documento_bruto.documento_id,
            hash_sha256=documento_bruto.hash_sha256,
            paginas=(texto_documento,),  # 1 "página" = conteúdo completo extraído
            ciclo=ciclo_para_corredor,
            cliente_do_ciclo=None,  # Deixar corredor decidir
            politica_competencia=contexto.politica_competencia if hasattr(contexto, 'politica_competencia') else None,
            candidatos_colaborador=contexto.tipos_obrigatorios_por_colaborador,
            fonte_vinculos=None,
            fonte_cliente_direto=None,
            fonte_unidade_posto=None,
            fonte_candidatos_relacao=None,
            clientes_broadcast=(),
            identificar_pagina=None,
            personalizar_contexto_do_grupo=None,
            registrar_dados_correlacao=False,
            fonte_inventario_pacote=None,
            politica_requisitos=None,
        )

        # Executar corredor: resolve semanticamente, escreve no
        # inventário. `executar_documento_readonly` é uma função pura
        # sem caminho de falha de negócio desenhado (nunca levanta
        # exceção própria) -- qualquer exceção aqui é inesperada, nunca
        # uma decisão de negócio a mascarar. Logada com evidência
        # mínima antes de seguir para o próximo documento.
        try:
            executar_documento_readonly(contexto_corredor, inventario_adquirido)
        except Exception as exc:
            _logger.error(
                '%s documento_id=%s hash_sha256=%s exception_type=%s',
                EVENTO_CORREDOR_FALHOU,
                documento_bruto.documento_id, documento_bruto.hash_sha256,
                type(exc).__name__,
                extra={
                    'evento': EVENTO_CORREDOR_FALHOU,
                    'documento_id': documento_bruto.documento_id,
                    'hash_sha256': documento_bruto.hash_sha256,
                    'exception_type': type(exc).__name__,
                },
            )
            continue

    return inventario_adquirido


def executar_ciclo_prestacao_persistente(
    contexto: ContextoComposicaoPrestacao,
    execucao_id: Optional[str] = None,
) -> ExecucaoPrestacao:
    """Executa ciclo persistente COMPLETO de Prestação de Contas.

    Fluxo:
    1. Criar ou retomar ExecucaoPrestacao
    2. Executar ciclo_prestacao primeira vez (necessidades)
    3. Aquisição readonly per necessidade
    4. Inventário recomposto
    5. Executar ciclo_prestacao segunda vez (readiness)
    6. Atualizar estado final

    Args:
        contexto: ContextoComposicaoPrestacao com todas dependências
        execucao_id: Se fornecido, retoma; caso contrário, cria novo

    Returns:
        ExecucaoPrestacao finalizada

    Raises:
        ValueError: Se execução não encontrada, estado inválido, etc.
    """
    # ==== PASSO 1: Criar ou retomar ExecucaoPrestacao ====
    if execucao_id:
        execucao = retomar_execucao_por_id(execucao_id, contexto.repositorio_execucoes)
    else:
        execucao = criar_e_persistir_execucao(
            competencia_base=contexto.competencia_base,
            repositorio_execucoes=contexto.repositorio_execucoes,
        )

    try:
        # ==== PASSO 2: Primeira execução do ciclo (sem inventário) ====
        ano_str, mes_str = contexto.competencia_base.split('-')
        ciclo_contexto = ContextoCicloPrestacao(
            competencia_base=(int(ano_str), int(mes_str))
        )

        # Inventário vazio (primeiro pass)
        inventario_vazio = InventarioPrestacaoEmMemoria()

        resultado_ciclo_1 = executar_ciclo_prestacao(
            contexto=ciclo_contexto,
            fonte_clientes=contexto.fonte_clientes,
            fonte_requisitos=contexto.fonte_requisitos,
            fonte_inventario=inventario_vazio,
            requisitos_base=contexto.requisitos_base,
            resolucoes_ancora=contexto.resolucoes_ancora,
            competencias_por_cliente=contexto.competencias_por_cliente,
            fonte_colaboradores_esperados=contexto.fonte_colaboradores_esperados,
            tipos_obrigatorios_por_colaborador=contexto.tipos_obrigatorios_por_colaborador,
        )

        # ==== PASSO 3: Aquisição canônica (documentos brutos → corredor → inventário) ====
        # Coletar todas as necessidades do resultado do ciclo 1
        necessidades: list = []
        for resultado_cliente in resultado_ciclo_1.resultados_por_cliente:
            necessidades.extend(resultado_cliente.necessidades)

        # Aquisição canônica: documentos brutos → corredor → inventário em
        # memória (extraída para `_adquirir_inventario_via_corredor`,
        # testável isoladamente -- mesmo comportamento observável de
        # antes). Só roda quando há repositório+armazenamento E
        # necessidade real; inventário vazio (sem custo de I/O) quando
        # não há nada a adquirir.
        if contexto.repositorio_documentos and contexto.armazenamento_arquivos and necessidades:
            ano_str, mes_str = contexto.competencia_base.split('-')
            ciclo_para_corredor = ContextoCicloPrestacao(
                competencia_base=(int(ano_str), int(mes_str))
            )
            inventario_adquirido = _adquirir_inventario_via_corredor(contexto, ciclo_para_corredor)
        else:
            inventario_adquirido = InventarioPrestacaoEmMemoria()

        # ==== PASSO 4: Compor fonte de inventário ====
        # Usar FonteInventarioPrestacaoComposta para unir:
        # 1. Inventário base pré-existente (se fornecido)
        # 2. Inventário adquirido neste ciclo (documentos processados via corredor)
        # A composição deduplica automaticamente por identidade_logica
        # (documento_id + cliente + colaborador)
        fontes_para_composicao = []
        if contexto.fonte_inventario_base:
            fontes_para_composicao.append(contexto.fonte_inventario_base)

        # SEMPRE adicionar inventário adquirido (pode estar vazio, isso é OK)
        fontes_para_composicao.append(inventario_adquirido)

        fonte_composta = FonteInventarioPrestacaoComposta(
            fontes=tuple(fontes_para_composicao)
        )

        # ==== PASSO 4: Segunda execução do ciclo (com inventário) ====
        resultado_ciclo_2 = executar_ciclo_prestacao(
            contexto=ciclo_contexto,
            fonte_clientes=contexto.fonte_clientes,
            fonte_requisitos=contexto.fonte_requisitos,
            fonte_inventario=fonte_composta,
            requisitos_base=contexto.requisitos_base,
            resolucoes_ancora=contexto.resolucoes_ancora,
            competencias_por_cliente=contexto.competencias_por_cliente,
            fonte_colaboradores_esperados=contexto.fonte_colaboradores_esperados,
            tipos_obrigatorios_por_colaborador=contexto.tipos_obrigatorios_por_colaborador,
        )

        # ==== PASSO 5: Determinar estado final ====
        # Encontrar o "pior" estado entre todos os clientes
        estado_pior_pacote = EstadoPacotePrestacao.PRONTO
        for resultado_cliente in resultado_ciclo_2.resultados_por_cliente:
            if resultado_cliente.pacote.estado == EstadoPacotePrestacao.INCOMPLETO:
                estado_pior_pacote = EstadoPacotePrestacao.INCOMPLETO
            elif resultado_cliente.pacote.estado == EstadoPacotePrestacao.EM_REVISAO:
                if estado_pior_pacote != EstadoPacotePrestacao.INCOMPLETO:
                    estado_pior_pacote = EstadoPacotePrestacao.EM_REVISAO
            elif resultado_cliente.pacote.estado == EstadoPacotePrestacao.BLOQUEADO:
                if estado_pior_pacote in (EstadoPacotePrestacao.PRONTO, EstadoPacotePrestacao.EM_REVISAO):
                    estado_pior_pacote = EstadoPacotePrestacao.BLOQUEADO

        # ==== PASSO 6: Atualizar ExecucaoPrestacao ====
        execucao_final = atualizar_execucao_por_estado_pacote(
            execucao_prestacao_id=execucao.execucao_prestacao_id,
            estado_pacote=estado_pior_pacote,
            repositorio_execucoes=contexto.repositorio_execucoes,
        )

        return execucao_final

    except Exception:
        # ROLLBACK DE REGRESSÃO (correção pós-merge PR #158, Incremento
        # 4): `5da729f` introduziu aqui uma heurística que classificava
        # a exceção como "terminal" (marca FALHA) ou "não terminal"
        # (deixa como estava) usando `isinstance` combinado com
        # correspondência de SUBSTRING no texto da mensagem da exceção
        # (`'execucao_prestacao' in str(exc).lower() or 'repositorio'
        # in str(exc).lower()`). Isso é frágil: uma exceção genuinamente
        # terminal cuja mensagem não contivesse essas palavras deixava
        # de marcar FALHA, e a ExecucaoPrestacao ficava presa em
        # INICIADA indefinidamente, sem nenhum mecanismo que a resuma
        # ou feche -- uma regressão silenciosa do comportamento
        # anterior à PR #158.
        #
        # Este `except` volta a marcar FALHA para QUALQUER exceção não
        # tratada dentro do `try` acima -- comportamento anterior à
        # regressão, restaurado tal como estava. Isso é um ROLLBACK,
        # não uma decisão arquitetural definitiva de que toda exceção
        # deva ser terminal: a classificação terminal x retomável
        # continua sendo uma questão em aberto, fora do escopo desta
        # missão -- exigirá seu próprio Ultraplan/ADR se for retomada.
        try:
            contexto.repositorio_execucoes.atualizar_estado(
                execucao_prestacao_id=execucao.execucao_prestacao_id,
                novo_estado='FALHA',
                concluido_em=datetime.now(timezone.utc),
            )
        except Exception:
            pass  # Já falhou, não mascarar a exceção original

        raise
