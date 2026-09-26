"""Composição persistente REAL de ciclos de Prestação de Contas — V1.

FLUXO COMPLETO (evolução do contrato do ciclo de Prestação V1,
Incremento 7 -- ver docstring de `executar_ciclo_prestacao_persistente`
para o detalhe de cada passo):

1. Validar política de competência V1 (fail-closed por tipo_documental)
2. Criar ou retomar ExecucaoPrestacao (rastreamento UUID opaco)
3. Descoberta de necessidades documentais SEM exigir nenhuma âncora
   (`executar_ciclo_prestacao_descoberta`)
4. Aquisição ORIENTADA POR NECESSIDADE (`adquirir_por_necessidades`,
   correção pós-Ultraplan "Correlação Necessidade → Aquisição →
   Resolução"): só candidatos de `contexto.fonte_candidatos_por_
   necessidade` são processados -- cliente/competência esperados vêm
   sempre da própria necessidade, nunca do que o documento resolve;
   sem essa fonte, nenhuma aquisição roda (nunca cai de volta para a
   aquisição em bloco legada, `_adquirir_inventario_via_corredor`,
   mantida só como primitiva testável isoladamente)
5. Seleção/validação de âncora real por cliente, avaliada só DENTRO do
   vínculo necessidade->documento preservado no passo 4
   (`avaliar_candidatos_ancora`) -- nunca uma resolução fabricada
6. FonteInventarioPrestacaoComposta (base + adquirido)
7. Executar ciclo_prestacao com a âncora real (ou ausência explícita)
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
    executar_ciclo_prestacao_descoberta,
)
from .competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    PoliticaCompetenciaPrestacao,
    verificar_politica_sem_override_por_tipo,
)
from .contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResultadoResolucaoSemantico,
)
from .execucao_prestacao import (
    ExecucaoPrestacao,
    RepositorioExecucoesPrestacao,
    criar_execucao_prestacao,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.modulo01.armazenamento import ArquivoNaoEncontrado
from magnata_os.documental.modulo01.dominio import Documento
from .fonte_candidatos_por_necessidade import FonteCandidatosDocumentaisPorNecessidade
from .fonte_cliente_direto_documento import FonteClienteDiretoDocumento
from .fonte_clientes_prestacao import FonteClientesPrestacao
from .fonte_colaboradores_esperados_prestacao import (
    FonteColaboradoresEsperadosPrestacao,
)
from .fonte_inventario_composta import FonteInventarioPrestacaoComposta
from .fonte_requisitos_prestacao import FonteRequisitosPrestacao
from .inventario_prestacao import FonteInventarioPrestacao
from .orquestrador_corredor_readonly import (
    ContextoExecucaoCorredorPrestacao,
    ResultadoExecucaoCorredorPrestacao,
    executar_documento_readonly,
)
from .inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from .normalizacao_requisitos_prestacao import (
    TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL,
)
from .pacote_prestacao import (
    EstadoPacotePrestacao,
    IntencaoDistribuicaoCliente,
    IntencaoDistribuicaoClienteError,
    PacotePrestacaoCliente,
    montar_intencao_distribuicao_cliente,
)
from .politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from .prestacao_readiness import (
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
from .resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from .roteamento_documental import extrair_texto_seguro
from .vinculo_unidade_prestacao import FonteUnidadePostoPrestacao
from .vinculos_prestacao import FonteVinculosPrestacao

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
    """NÃO CONSULTADO por `executar_ciclo_prestacao_persistente`
    (correção pós-auditoria, evolução do contrato do ciclo de
    Prestação V1): auditoria de todos os callers reais encontrou ZERO
    caller de produção/wiring que popule este campo -- só testes, com
    dados sintéticos -- e não há como provar, pelo contrato, que uma
    entrada aqui é uma resolução real (documento/hash/proveniência
    reais) aplicável ao cliente/competência atual. `executar_ciclo_
    prestacao_persistente` decide a âncora de cada cliente SÓ a partir
    de evidência REAL desta própria execução
    (`avaliar_candidatos_ancora`); sem evidência real, o cliente fica
    explicitamente sem âncora (REVISAR), nunca com uma entrada daqui
    usada sem prova. Mantido só para não quebrar assinatura de quem já
    constrói este dataclass; `executar_ciclo_prestacao` (função de
    mais baixo nível, chamada por este módulo) continua aceitando
    `resolucoes_ancora` como parâmetro explícito próprio, sem relação
    com este campo."""

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

    fonte_candidatos_por_necessidade: Optional[FonteCandidatosDocumentaisPorNecessidade] = None
    """Correção pós-Ultraplan "Correlação Necessidade → Aquisição →
    Resolução": única porta que preserva uma associação REAL e
    independente entre necessidade (cliente/competência/tipo/
    colaborador esperados) e documento candidato -- ver docstring
    completa em `fonte_candidatos_por_necessidade.py`. `None`
    (default, produção hoje): nenhuma aquisição orientada por
    necessidade roda -- NUNCA cai de volta para aquisição em bloco
    (`_adquirir_inventario_via_corredor` continua existindo como
    primitiva testável isoladamente, mas não é mais chamada por
    `executar_ciclo_prestacao_persistente`); ausência desta fonte é
    ausência de evidência contextual, tratada como
    `sem_evidencia_documental_real` → REVISAR, nunca um fallback
    silencioso."""

    # ---- Gate J1: fontes de resolução de dimensões do corredor ----
    # Antes do J1 a aquisição fixava as 3 fontes abaixo em `None` e
    # passava `tipos_obrigatorios_por_colaborador` (tipos documentais,
    # `str`) como `candidatos_colaborador` -- o corredor real levantava
    # `AttributeError` em todo documento de granularidade colaborador
    # (engolido como `corredor_falhou`) e nenhuma dimensão CLIENTE/
    # UNIDADE_POSTO podia ser resolvida (ver docs/decisoes/auditoria-
    # gate-j-composicao-prestacao-v1.md). Estes campos só REPASSAM ao
    # corredor as mesmas portas que `ContextoExecucaoCorredorPrestacao`
    # já declara -- nenhum contrato novo. Default = ausência explícita:
    # a dimensão correspondente fica NAO_AVALIADA/NAO_ENCONTRADA (REVISAR),
    # nunca fabricada. `fonte_candidatos_relacao` NÃO entra aqui: não
    # resolve dimensão nenhuma (só relação documental pós-resolução).

    candidatos_colaborador: Tuple[CandidatoFuncionario, ...] = dataclasses.field(default=(), repr=False)
    """Universo de colaboradores contra o qual o corredor identifica o
    colaborador pelo CONTEÚDO do documento (CPF/nome, `resolver_
    funcionario`). Carrega CPF em memória -- nunca logado, nunca
    persistido por este módulo, fora do `repr` do contexto (nenhum
    traceback/log que imprima o contexto expõe CPF). Validado em
    `__post_init__`: só `CandidatoFuncionario`, nunca tipo documental
    (regressão do J1)."""

    fonte_vinculos: Optional[FonteVinculosPrestacao] = None
    """COLABORADOR -> CLIENTE na competência (granularidade colaborador)."""

    fonte_unidade_posto: Optional[FonteUnidadePostoPrestacao] = None
    """COLABORADOR -> UNIDADE_POSTO na competência (hoje exigido pelo
    perfil de Holerite)."""

    fonte_cliente_direto: Optional[FonteClienteDiretoDocumento] = None
    """Cliente comprovado pelo próprio texto (granularidade cliente:
    Extrato, FGTS Guia)."""

    def __post_init__(self) -> None:
        candidatos = tuple(self.candidatos_colaborador)
        invalidos = [c for c in candidatos if not isinstance(c, CandidatoFuncionario)]
        if invalidos:
            raise TypeError(
                'candidatos_colaborador aceita somente CandidatoFuncionario '
                f'(recebido: {sorted({type(c).__name__ for c in invalidos})})'
            )
        object.__setattr__(self, 'candidatos_colaborador', candidatos)


def _contexto_corredor(
    contexto: 'ContextoComposicaoPrestacao',
    documento_bruto: Documento,
    texto_documento: str,
    ciclo_para_corredor: ContextoCicloPrestacao,
    cliente_do_ciclo: Optional[ReferenciaCanonica],
) -> ContextoExecucaoCorredorPrestacao:
    """Único ponto que monta o contexto do corredor para a aquisição
    (Gate J1) -- as duas aquisições (`adquirir_por_necessidades` e a
    primitiva em bloco) passam a repassar as MESMAS fontes, nunca uma
    cópia divergente da outra.

    `politica_competencia=None` no contexto (não informada) NÃO é mais
    repassado como `None`: o corredor chamava `.competencia_esperada_
    para` em `None` sempre que `cliente_do_ciclo` estava presente (todo
    documento de `adquirir_por_necessidades`) -- `AttributeError`,
    engolido como `corredor_falhou`. Sem política informada, vale o
    default canônico que o próprio `ContextoExecucaoCorredorPrestacao`
    já declara (`POLITICA_COMPETENCIA_PRESTACAO_V1`)."""
    politica_competencia = (
        contexto.politica_competencia
        if contexto.politica_competencia is not None
        else POLITICA_COMPETENCIA_PRESTACAO_V1
    )
    return ContextoExecucaoCorredorPrestacao(
        documento_id=documento_bruto.documento_id,
        hash_sha256=documento_bruto.hash_sha256,
        paginas=(texto_documento,),  # 1 "página" = conteúdo completo extraído
        ciclo=ciclo_para_corredor,
        cliente_do_ciclo=cliente_do_ciclo,
        politica_competencia=politica_competencia,
        candidatos_colaborador=contexto.candidatos_colaborador,
        fonte_vinculos=contexto.fonte_vinculos,
        fonte_cliente_direto=contexto.fonte_cliente_direto,
        fonte_unidade_posto=contexto.fonte_unidade_posto,
        fonte_candidatos_relacao=None,
        clientes_broadcast=(),
        identificar_pagina=None,
        personalizar_contexto_do_grupo=None,
        registrar_dados_correlacao=False,
        fonte_inventario_pacote=None,
        politica_requisitos=None,
    )


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


def _ler_e_extrair_texto(
    contexto: 'ContextoComposicaoPrestacao',
    documento_bruto: Documento,
) -> Optional[str]:
    """Blob -> checagem de MIME -> texto, com a MESMA observabilidade
    de sempre (Incremento 3: evento ESTÁVEL por ponto de falha, nunca
    `str(exc)` cru). Extraída de `_adquirir_inventario_via_corredor`
    para ser reaproveitada também pela aquisição orientada por
    necessidade (`adquirir_por_necessidades`, correção pós-Ultraplan
    "Correlação Necessidade → Aquisição → Resolução") -- mesmo
    comportamento observável de antes, nenhuma duplicação de lógica.
    `None` em qualquer falha (já logada aqui); quem chama só decide
    pular o documento."""
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
        return None
    except Exception as exc:
        # Encontrado mas falhou ao ler -- nunca confundir com
        # "documento ausente". Só o TIPO da exceção é logado, nunca a
        # mensagem crua (pode ecoar conteúdo do backend de
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
        return None

    # Extração canônica segura, com decisão explícita de MIME
    # (correção pós-merge PR #158, Incremento 2): reutiliza
    # `extrair_texto_seguro` (`classificacao/roteamento_documental.py`,
    # já existente), que por sua vez reaproveita `extrair_texto_pdf`
    # (`documental/extracao_texto.py`) -- mesma extração usada por
    # `processar_holerite`/`processar_extrato` e pelo roteamento
    # avulso. Nenhum parser novo. Só `application/pdf` tem extrator
    # canônico no repositório hoje -- mime não suportado nunca entra
    # no extrator, vira um caminho próprio, distinto de "PDF ilegível".
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
        return None

    texto_documento = extrair_texto_seguro(conteudo_bytes)
    if texto_documento is None:
        # PDF corrompido/ilegível (ex.: escaneado sem OCR) -- mesma
        # distinção honesta já feita por `extrair_texto_seguro`: nunca
        # uma string vazia tratada como classificável.
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
        return None
    return texto_documento


@dataclasses.dataclass(frozen=True)
class _ResultadoAquisicaoDocumento:
    """Transporte interno/privado (evolução do contrato do ciclo de
    Prestação V1, Incremento 4): associa 1 documento bruto processado
    nesta aquisição aos resultados REAIS produzidos pelo corredor --
    antes desta correção, `executar_documento_readonly` já devolvia
    esses resultados (incluindo `resolucao_semantica` real, com
    proveniência: `resolver_id`/`resolver_version`) e
    `_adquirir_inventario_via_corredor` os descartava completamente,
    só escrevendo no `sink`. Não é um contrato público novo -- não sai
    deste módulo; a fase seguinte (seleção de âncora real) consome
    isto diretamente, nunca reconstrói ou fabrica uma resolução."""

    documento_id: str
    hash_sha256: str
    resultados_corredor: Tuple[ResultadoExecucaoCorredorPrestacao, ...] = ()


def _adquirir_inventario_via_corredor(
    contexto: 'ContextoComposicaoPrestacao',
    ciclo_para_corredor: ContextoCicloPrestacao,
) -> Tuple[InventarioPrestacaoEmMemoria, Tuple[_ResultadoAquisicaoDocumento, ...]]:
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
    existente antes desta correção).

    Retenção da resolução real (evolução do contrato do ciclo de
    Prestação V1, Incremento 4): além do inventário, devolve 1
    `_ResultadoAquisicaoDocumento` por documento efetivamente
    processado pelo corredor com sucesso (nunca para um documento que
    caiu num `continue` de erro acima -- blob ausente, blob ilegível,
    MIME não suportado, PDF ilegível ou o próprio corredor falhando).
    Antes desta correção, o retorno de `executar_documento_readonly`
    (que já carrega a resolução semântica REAL, com proveniência) era
    completamente descartado; a fase de seleção de âncora (Incremento
    5) depende de ter acesso a essa resolução real -- nunca de uma
    fabricada a partir de cliente+competência.

    NÃO É MAIS CHAMADA por `executar_ciclo_prestacao_persistente`
    (correção pós-Ultraplan "Correlação Necessidade → Aquisição →
    Resolução"): processa documentos em BLOCO
    (`repositorio_documentos.listar_todos()`), sem nenhuma associação
    real e independente entre documento e cliente/competência esperado
    -- exatamente o que a correção elimina do caminho final (ver
    `adquirir_por_necessidades`, que a substitui). Mantida como
    PRIMITIVA testável isoladamente (mesmo papel de sempre: blob ->
    extração -> corredor -> inventário), reutilizada por `_adquirir_
    por_necessidades` só na parte de extração (`_ler_e_extrair_
    texto`)."""
    inventario_adquirido = InventarioPrestacaoEmMemoria()
    resultados_aquisicao: list = []
    if not (contexto.repositorio_documentos and contexto.armazenamento_arquivos):
        return inventario_adquirido, tuple(resultados_aquisicao)

    documentos_disponiveis = contexto.repositorio_documentos.listar_todos()

    for documento_bruto in documentos_disponiveis:
        texto_documento = _ler_e_extrair_texto(contexto, documento_bruto)
        if texto_documento is None:
            continue

        # Construir contexto para o corredor (todas as dependências são opcionais)
        contexto_corredor = _contexto_corredor(
            contexto, documento_bruto, texto_documento, ciclo_para_corredor,
            cliente_do_ciclo=None,  # Deixar corredor decidir
        )

        # Executar corredor: resolve semanticamente, escreve no
        # inventário. `executar_documento_readonly` é uma função pura
        # sem caminho de falha de negócio desenhado (nunca levanta
        # exceção própria) -- qualquer exceção aqui é inesperada, nunca
        # uma decisão de negócio a mascarar. Logada com evidência
        # mínima antes de seguir para o próximo documento.
        #
        # Incremento 4: o retorno REAL (proveniência incluída) é
        # retido em `resultados_aquisicao` -- antes desta correção era
        # descartado aqui mesmo em caso de sucesso.
        try:
            resultados_corredor = executar_documento_readonly(
                contexto_corredor, inventario_adquirido
            )
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

        resultados_aquisicao.append(
            _ResultadoAquisicaoDocumento(
                documento_id=documento_bruto.documento_id,
                hash_sha256=documento_bruto.hash_sha256,
                resultados_corredor=tuple(resultados_corredor),
            )
        )

    return inventario_adquirido, tuple(resultados_aquisicao)


# ==== CORREÇÃO PÓS-ULTRAPLAN: "CORRELAÇÃO NECESSIDADE → AQUISIÇÃO →
# RESOLUÇÃO" ====
# Aquisição ORIENTADA POR NECESSIDADE -- substitui a aquisição em
# bloco (`_adquirir_inventario_via_corredor`, acima) como caminho
# usado por `executar_ciclo_prestacao_persistente`. Ver auditoria
# completa (relatório da sessão) e docstring de
# `fonte_candidatos_por_necessidade.py` para o raciocínio; resumo:
# processar TODOS os documentos em bloco não preserva nenhuma
# associação real entre documento e a necessidade/cliente/competência
# que motivou buscá-lo -- qualquer tentativa de reconstruir essa
# associação a partir do que o próprio documento resolve foi avaliada
# e rejeitada. Esta função só processa candidatos devolvidos por
# `contexto.fonte_candidatos_por_necessidade` -- o cliente/competência
# esperados vêm SEMPRE da própria `NecessidadeDocumentoPrestacao`,
# nunca inferidos do resolvido.


@dataclasses.dataclass(frozen=True)
class ResultadoAquisicaoPorNecessidade:
    """Associa 1 candidato processado à necessidade REAL que motivou
    buscá-lo -- cliente/competência esperados vêm da PRÓPRIA
    `necessidade` (contrato já completo, `ciclo_prestacao.py`), nunca
    inferidos do que o documento resolveu.

    Promovido de privado (`_ResultadoAquisicaoPorNecessidade`) para
    público nesta correção (Ultraplan "Incremento Vertical Prestação ->
    Ordem -> PENDING V1") -- mudança de VISIBILIDADE apenas: mesma
    assinatura, mesmo shape, mesma semântica. Motivo: `necessidade.
    colaborador` (via este tipo) é exatamente o vínculo que
    `wiring_prestacao_distribuicao_documental_shadow.py` precisa
    reaproveitar para montar `OrdemDistribuicaoDocumental` sem
    reconstruir a correlação necessidade<->documento<->colaborador, que
    `executar_ciclo_prestacao_persistente` descarta a partir de
    `resultados_aquisicao` (ela só extrai cliente/competência para o
    bucket de seleção de âncora). Único caller de produção antes desta
    correção: `executar_ciclo_prestacao_persistente` (mesmo módulo,
    logo abaixo) -- inalterado por este rename."""

    necessidade: NecessidadeDocumentoPrestacao
    documento_id: str
    hash_sha256: str
    resultados_corredor: Tuple[ResultadoExecucaoCorredorPrestacao, ...] = ()


def adquirir_por_necessidades(
    contexto: 'ContextoComposicaoPrestacao',
    necessidades: Tuple[NecessidadeDocumentoPrestacao, ...],
    ciclo_para_corredor: ContextoCicloPrestacao,
) -> Tuple[InventarioPrestacaoEmMemoria, Tuple[ResultadoAquisicaoPorNecessidade, ...]]:
    """Para CADA necessidade, consulta `contexto.fonte_candidatos_por_
    necessidade.candidatos_para(necessidade)` -- NUNCA `repositorio_
    documentos.listar_todos()` em bloco. `cliente_do_ciclo` do
    corredor é ajustado para `necessidade.cliente` -- o campo já existe
    em `ContextoExecucaoCorredorPrestacao`, já documentado como "NUNCA
    inferido do documento", usado até aqui só para escolher a política
    de competência esperada; esta correção o usa também como o
    transporte do contexto esperado desta necessidade. A dimensão
    CLIENTE do documento continua resolvida 100% do conteúdo
    (`fonte_cliente_direto`/`fonte_vinculos`), nunca enviesada por
    `cliente_do_ciclo` -- por isso um candidato pode legitimamente
    divergir do que a necessidade esperava, e essa divergência
    permanece detectável.

    SEM `contexto.fonte_candidatos_por_necessidade` (`None`, produção
    hoje): devolve inventário vazio e nenhum resultado -- NUNCA cai de
    volta para `_adquirir_inventario_via_corredor`/aquisição em bloco.
    Ausência da fonte é ausência de evidência contextual; quem chama
    trata isso como `sem_evidencia_documental_real` → REVISAR, nunca um
    fallback silencioso.

    Deduplicação física SEM perder a associação necessidade->documento
    (requisito explícito desta correção): o texto extraído de um blob
    é cacheado só por `hash_sha256` (extração é invariável ao
    contexto -- é função pura do conteúdo, nunca de quem pediu). O
    resultado do CORREDOR é cacheado por (`documento_id`,
    `hash_sha256`, cliente, competência) da necessidade -- nunca só por
    (hash, cliente, competência), porque o resultado do corredor
    carrega IDENTIDADE/PROVENIÊNCIA amarrada a `documento_id`
    (`ContextoExecucaoCorredorPrestacao.documento_id` propaga para
    `resolucao_semantica.documento_id`); dois `Documento` distintos que
    por acaso compartilhem o mesmo hash NUNCA podem reaproveitar o
    resultado calculado para o outro -- isso misturaria a proveniência
    de um documento com a identidade de outro (correção pós-
    Ultrareview: a chave anterior, só por hash+cliente+competência,
    permitia exatamente essa mistura). Também nunca só por hash porque
    a resolução da dimensão COMPETÊNCIA depende de `competencia_
    esperada` (`_resolver_competencia`, `resolucao_documento_
    prestacao.py`): o MESMO documento avaliado sob expectativas
    diferentes pode legitimamente resolver diferente. Um candidato
    repetido para 2+ necessidades do MESMO documento/cliente/competência
    (tipos documentais diferentes, ex.: HOLERITE e FGTS do mesmo
    cliente/mês) reaproveita o resultado cacheado -- MESMO ASSIM, 1
    `ResultadoAquisicaoPorNecessidade` é registrado por (necessidade,
    documento): o vínculo nunca desaparece, mesmo quando o
    processamento físico é reaproveitado."""
    inventario_adquirido = InventarioPrestacaoEmMemoria()
    resultados: list = []
    if contexto.fonte_candidatos_por_necessidade is None:
        return inventario_adquirido, tuple(resultados)
    if not (contexto.repositorio_documentos and contexto.armazenamento_arquivos):
        # `candidatos_para` devolve `Documento`; ainda precisamos do
        # armazenamento real para ler o blob -- sem os dois, nenhuma
        # aquisição real é possível (mesma exigência de sempre).
        return inventario_adquirido, tuple(resultados)

    texto_por_hash: dict = {}
    corredor_por_chave: dict = {}

    for necessidade in necessidades:
        candidatos = contexto.fonte_candidatos_por_necessidade.candidatos_para(necessidade)
        for documento_bruto in candidatos:
            if documento_bruto.hash_sha256 not in texto_por_hash:
                texto_por_hash[documento_bruto.hash_sha256] = _ler_e_extrair_texto(
                    contexto, documento_bruto
                )
            texto_documento = texto_por_hash[documento_bruto.hash_sha256]
            if texto_documento is None:
                continue

            chave_cache = (
                documento_bruto.documento_id, documento_bruto.hash_sha256,
                necessidade.cliente, necessidade.competencia,
            )
            if chave_cache not in corredor_por_chave:
                contexto_corredor = _contexto_corredor(
                    contexto, documento_bruto, texto_documento, ciclo_para_corredor,
                    cliente_do_ciclo=necessidade.cliente,  # ESPERADO, nunca inferido do documento
                )
                try:
                    resultado_corredor_cru = executar_documento_readonly(
                        contexto_corredor, inventario_adquirido
                    )
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
                    resultado_corredor_cru = ()
                corredor_por_chave[chave_cache] = tuple(resultado_corredor_cru)

            resultados_corredor = corredor_por_chave[chave_cache]
            if not resultados_corredor:
                continue

            resultados.append(
                ResultadoAquisicaoPorNecessidade(
                    necessidade=necessidade,
                    documento_id=documento_bruto.documento_id,
                    hash_sha256=documento_bruto.hash_sha256,
                    resultados_corredor=resultados_corredor,
                )
            )

    return inventario_adquirido, tuple(resultados)


# ==== EVOLUÇÃO DO CONTRATO DO CICLO DE PRESTAÇÃO V1 -- INCREMENTO 5 ====
# Seleção/validação de âncora real. NUNCA cria um novo
# `ResultadoResolucaoSemantico` -- só examina candidatos já reais (ver
# Incremento 4: vêm de `resultado_corredor.resolucao_semantica`, nunca
# fabricados a partir de cliente+competência). Distinção deliberada de
# `avaliar_prestacao_readiness` (`prestacao_readiness.py`): aquela
# função faz as checagens cruzadas finais assumindo que UMA âncora já
# foi escolhida; esta função é quem decide, entre 0..N evidências
# reais concorrentes para o MESMO cliente/competência esperado, se
# existe uma âncora e qual é -- sem isso, as checagens cruzadas de
# `avaliar_prestacao_readiness` seriam tautológicas.


def _dimensao_resolvida_com_valor_unico(
    resultado: ResultadoResolucaoSemantico, dimensao: DimensaoResolucao,
) -> Optional[ReferenciaCanonica]:
    """Devolve o único valor confirmado de `dimensao` em `resultado` só
    quando a dimensão está presente, no estado RESOLVIDA e com
    EXATAMENTE 1 valor confirmado -- qualquer outra forma (dimensão
    ausente, AMBIGUA/CONFLITO/NAO_ENCONTRADA/etc., 0 ou 2+ valores)
    devolve `None`, tratada pelo chamador como candidato não-validável
    (nunca uma escolha arbitrária entre valores)."""
    resolucao_dimensao = next(
        (item for item in resultado.resolucoes if item.dimensao == dimensao), None,
    )
    if resolucao_dimensao is None:
        return None
    if resolucao_dimensao.estado != EstadoResolucaoDimensao.RESOLVIDA:
        return None
    if len(resolucao_dimensao.valores_confirmados) != 1:
        return None
    return resolucao_dimensao.valores_confirmados[0]


@dataclasses.dataclass(frozen=True)
class ResultadoAvaliacaoCandidatosAncora:
    """Saída de `avaliar_candidatos_ancora` -- exatamente 1 dos 2 campos
    é significativo por vez: `ancora` presente (motivo_ausencia=None)
    OU `motivo_ausencia` presente (ancora=None). Nunca os dois juntos,
    nunca os dois ausentes."""

    ancora: Optional[ResultadoResolucaoSemantico] = None
    motivo_ausencia: Optional[str] = None


MOTIVO_SEM_EVIDENCIA_DOCUMENTAL_REAL = 'sem_evidencia_documental_real'
MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES = 'resolucoes_ancora_divergentes'


def avaliar_candidatos_ancora(
    candidatos: Tuple[ResultadoResolucaoSemantico, ...],
    cliente_esperado: ReferenciaCanonica,
    competencia_esperada: ReferenciaCanonica,
) -> ResultadoAvaliacaoCandidatosAncora:
    """Avalia 0..N resoluções semânticas REAIS (nunca fabricadas) já
    produzidas por documentos desta aquisição e decide se existe uma
    âncora válida para `cliente_esperado`/`competencia_esperada`.

    Um candidato é VALIDÁVEL só quando: `necessita_revisao_humana` é
    False E as dimensões CLIENTE e COMPETÊNCIA estão, cada uma,
    RESOLVIDA com exatamente 1 valor confirmado. Um candidato em
    revisão (ambíguo, em conflito, não encontrado, técnica ou
    humanamente pendente) NUNCA vira autoridade de âncora -- ele só
    contribui para um resultado "sem âncora válida" (mesmo motivo de 0
    candidatos: não há, hoje, uma distinção de negócio pedida entre
    "nenhum documento" e "documentos só com evidência inconclusiva").

    Entre os candidatos validáveis:
    - se qualquer um resolve para um cliente/competência DIFERENTE do
      esperado -- inclusive quando outros concordam com o esperado --
      o resultado é DIVERGÊNCIA explícita
      (`resolucoes_ancora_divergentes`), nunca um agrupamento
      silencioso sob outro cliente e nunca uma escolha de lado, mesmo
      que exista um candidato "certo" na mistura;
    - senão, entre os que concordam com o esperado ("concordantes"): 1
      é usado diretamente; N é resolvido por um desempate
      DETERMINÍSTICO por `semantic_result_id` (ordem alfabética do
      hash) -- isto NUNCA decide validade nem resolve conflito
      nenhum, todos os N já foram provados equivalentes/concordantes
      acima; só escolhe um representante determinístico entre
      evidências reais e concordantes.

    Determinístico e independente da ordem de `candidatos` -- o
    desempate usa `min()` por uma chave estável, nunca "o primeiro da
    lista"."""
    candidatos_validaveis: list = []
    for candidato in candidatos:
        if candidato.necessita_revisao_humana:
            continue
        cliente_real = _dimensao_resolvida_com_valor_unico(candidato, DimensaoResolucao.CLIENTE)
        competencia_real = _dimensao_resolvida_com_valor_unico(candidato, DimensaoResolucao.COMPETENCIA)
        if cliente_real is None or competencia_real is None:
            continue
        candidatos_validaveis.append((candidato, cliente_real, competencia_real))

    if not candidatos_validaveis:
        return ResultadoAvaliacaoCandidatosAncora(
            motivo_ausencia=MOTIVO_SEM_EVIDENCIA_DOCUMENTAL_REAL
        )

    divergentes = [
        candidato for candidato, cliente_real, competencia_real in candidatos_validaveis
        if cliente_real != cliente_esperado or competencia_real != competencia_esperada
    ]
    if divergentes:
        return ResultadoAvaliacaoCandidatosAncora(
            motivo_ausencia=MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES
        )

    concordantes = tuple(candidato for candidato, _, _ in candidatos_validaveis)
    escolhido = min(concordantes, key=lambda candidato: candidato.semantic_result_id)
    return ResultadoAvaliacaoCandidatosAncora(ancora=escolhido)


def _descobrir_adquirir_e_recalcular_readiness(
    contexto: 'ContextoComposicaoPrestacao', ciclo_contexto: ContextoCicloPrestacao,
) -> Tuple[Tuple[ResultadoAquisicaoPorNecessidade, ...], ResultadoCicloPrestacao]:
    """Extraído de `executar_ciclo_prestacao_persistente` (antigos
    passos 3-7: descoberta -> aquisição por necessidade -> seleção de
    âncora -> composição de inventário -> segunda execução do ciclo
    com readiness real), para ser reutilizado por composições que
    também precisam do vínculo necessidade->documento->colaborador
    preservado (`ResultadoAquisicaoPorNecessidade`), não só do estado
    final de readiness -- sem duplicar esta lógica em dois lugares
    (Ultraplan "Delta Final A-F -- Cliente+Competência -> PENDING").

    Comportamento IDÊNTICO ao que já existia inline em
    `executar_ciclo_prestacao_persistente` antes desta extração --
    puro refactor, mesma sequência de chamadas, mesmos argumentos.
    `executar_ciclo_prestacao_persistente` chama esta função e seu
    retorno público (`ExecucaoPrestacao`) permanece exatamente o
    mesmo; verificado pela suíte de testes já existente, que não foi
    alterada por esta extração."""
    inventario_vazio = InventarioPrestacaoEmMemoria()
    resultado_descoberta = executar_ciclo_prestacao_descoberta(
        contexto=ciclo_contexto,
        fonte_clientes=contexto.fonte_clientes,
        fonte_requisitos=contexto.fonte_requisitos,
        fonte_inventario=inventario_vazio,
        requisitos_base=contexto.requisitos_base,
        competencias_por_cliente=contexto.competencias_por_cliente,
        fonte_colaboradores_esperados=contexto.fonte_colaboradores_esperados,
        tipos_obrigatorios_por_colaborador=contexto.tipos_obrigatorios_por_colaborador,
    )

    necessidades: list = []
    for resultado_cliente in resultado_descoberta.resultados_por_cliente:
        necessidades.extend(resultado_cliente.necessidades)

    inventario_adquirido, resultados_aquisicao = adquirir_por_necessidades(
        contexto, tuple(necessidades), ciclo_contexto,
    )

    candidatos_por_bucket: dict = {}
    for resultado_aquisicao in resultados_aquisicao:
        chave_bucket = (
            resultado_aquisicao.necessidade.cliente,
            resultado_aquisicao.necessidade.competencia,
        )
        candidatos_vistos = candidatos_por_bucket.setdefault(chave_bucket, {})
        for resultado_execucao in resultado_aquisicao.resultados_corredor:
            resolucao = resultado_execucao.resultado_corredor.resolucao_semantica
            if resolucao is not None:
                candidatos_vistos[resolucao.semantic_result_id] = resolucao

    resolucoes_ancora_efetivas: dict = {}
    for resultado_cliente in resultado_descoberta.resultados_por_cliente:
        cliente = resultado_cliente.cliente
        competencia = resultado_cliente.competencia
        candidatos_do_vinculo = tuple(
            candidatos_por_bucket.get((cliente, competencia), {}).values()
        )
        avaliacao = avaliar_candidatos_ancora(candidatos_do_vinculo, cliente, competencia)
        if avaliacao.ancora is not None:
            resolucoes_ancora_efetivas[cliente] = avaliacao.ancora

    fontes_para_composicao = []
    if contexto.fonte_inventario_base:
        fontes_para_composicao.append(contexto.fonte_inventario_base)
    fontes_para_composicao.append(inventario_adquirido)
    fonte_composta = FonteInventarioPrestacaoComposta(fontes=tuple(fontes_para_composicao))

    resultado_ciclo_2 = executar_ciclo_prestacao(
        contexto=ciclo_contexto,
        fonte_clientes=contexto.fonte_clientes,
        fonte_requisitos=contexto.fonte_requisitos,
        fonte_inventario=fonte_composta,
        requisitos_base=contexto.requisitos_base,
        resolucoes_ancora=resolucoes_ancora_efetivas,
        competencias_por_cliente=contexto.competencias_por_cliente,
        fonte_colaboradores_esperados=contexto.fonte_colaboradores_esperados,
        tipos_obrigatorios_por_colaborador=contexto.tipos_obrigatorios_por_colaborador,
    )

    return resultados_aquisicao, resultado_ciclo_2


EVENTO_DOCUMENTO_INELEGIVEL_DISTRIBUICAO = 'documento_inelegivel_distribuicao'


def _tipo_resolvido_atende_necessidade(
    resolucao: ResultadoResolucaoSemantico, necessidade: NecessidadeDocumentoPrestacao,
) -> bool:
    """Gate J1b ("pessoa certa, documento errado"): o TIPO documental
    que o corredor resolveu (valor único) precisa ser o tipo da
    necessidade que buscou o documento -- senão o documento de A que
    satisfaz outra necessidade de A entraria na distribuição como se
    fosse o documento pedido. Comparação genérica, sem nenhum nome de
    tipo: ambos os lados usam o vocabulário canônico do motor, e a
    única tradução conhecida entre vocabulários
    (`TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL`) é reaproveitada, nunca
    reescrita. Regra da elegibilidade da Prestação -- a distribuição
    genérica nunca olha tipo."""
    tipo_resolvido = _dimensao_resolvida_com_valor_unico(resolucao, DimensaoResolucao.TIPO_DOCUMENTAL)
    if tipo_resolvido is None:
        return False

    def _canonico(tipo: str) -> str:
        return TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL.get(tipo, tipo)

    return _canonico(tipo_resolvido.entidade_id) == _canonico(necessidade.tipo_documental)


def _elegivel_para_distribuicao(resultado: ResultadoAquisicaoPorNecessidade) -> bool:
    """Gate J1 (achado da revisão adversarial): `adquirir_por_
    necessidades` registra 1 resultado por (necessidade, candidato)
    QUALQUER que seja o estado do corredor -- correto para a avaliação
    de âncora, mas `resultados_aquisicao_prontos_por_cliente` os
    repassava TODOS à distribuição assim que o cliente ficava PRONTO.
    Antes do J1 isso era inalcançável (o corredor real quebrava em todo
    documento); com o corredor real funcionando, um candidato em
    REVISAO_NECESSARIA -- ou RESOLVIDO para OUTRO colaborador/cliente/
    competência que não o da necessidade -- entraria na Ordem do
    colaborador da necessidade (documento de uma pessoa enviado a
    outra).

    Elegível só quando TODA execução do corredor para o documento
    terminou `RESOLVIDO_E_AVANCOU`, sem revisão humana, e a resolução
    REAL confirma, com valor único, exatamente o cliente/competência da
    necessidade -- e o colaborador, quando a necessidade tem um. Nunca
    corrige nem reatribui: inelegível é só omitido da distribuição e
    registrado (evento estável, só identificadores)."""
    necessidade = resultado.necessidade
    esperado = {
        DimensaoResolucao.CLIENTE: necessidade.cliente,
        DimensaoResolucao.COMPETENCIA: necessidade.competencia,
    }
    if necessidade.colaborador is not None:
        esperado[DimensaoResolucao.COLABORADOR] = necessidade.colaborador

    elegivel = bool(resultado.resultados_corredor)
    for execucao in resultado.resultados_corredor:
        corredor = execucao.resultado_corredor
        resolucao = corredor.resolucao_semantica
        if (
            corredor.estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
            or resolucao is None
            or resolucao.necessita_revisao_humana
            or any(
                _dimensao_resolvida_com_valor_unico(resolucao, dimensao) != valor
                for dimensao, valor in esperado.items()
            )
            or not _tipo_resolvido_atende_necessidade(resolucao, necessidade)
        ):
            elegivel = False
            break

    if not elegivel:
        _logger.warning(
            '%s documento_id=%s cliente=%s competencia=%s',
            EVENTO_DOCUMENTO_INELEGIVEL_DISTRIBUICAO,
            resultado.documento_id, necessidade.cliente.entidade_id, necessidade.competencia.entidade_id,
            extra={
                'evento': EVENTO_DOCUMENTO_INELEGIVEL_DISTRIBUICAO,
                'documento_id': resultado.documento_id,
                'cliente': necessidade.cliente.entidade_id,
                'competencia': necessidade.competencia.entidade_id,
            },
        )
    return elegivel


def resultados_aquisicao_prontos_por_cliente(
    contexto: 'ContextoComposicaoPrestacao',
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Para cada (cliente, competência) cujo `pacote.estado ==
    EstadoPacotePrestacao.PRONTO`, devolve os
    `ResultadoAquisicaoPorNecessidade` daquele vínculo -- prontos para
    o Orquestrador montar `OrdemDistribuicaoDocumental`
    (`wiring_prestacao_distribuicao_documental_shadow.py`).

    Clientes/competências NÃO prontos são simplesmente omitidos do
    retorno -- STOP silencioso e isolado por cliente (nunca contamina
    os demais: `executar_ciclo_prestacao`/`avaliar_candidatos_ancora`
    já avaliam cada (cliente, competência) de forma independente,
    garantia pré-existente reaproveitada aqui, não recriada).

    Reutiliza EXATAMENTE a mesma composição de
    `executar_ciclo_prestacao_persistente` via
    `_descobrir_adquirir_e_recalcular_readiness` -- não recalcula nada
    com lógica própria, não introduz um segundo motor de descoberta/
    aquisição/readiness.

    Deliberadamente NÃO cria nem atualiza `ExecucaoPrestacao` -- esta
    função é só leitura + readiness + aquisição, sem efeito colateral
    de rastreamento de execução (isso continua responsabilidade
    exclusiva de quem chamar `executar_ciclo_prestacao_persistente`
    separadamente, se precisar de rastreamento; esta função nunca cria
    um segundo `execucao_id`, porque nunca cria nenhum)."""
    if contexto.politica_competencia is not None:
        verificar_politica_sem_override_por_tipo(contexto.politica_competencia)

    ano_str, mes_str = contexto.competencia_base.split('-')
    ciclo_contexto = ContextoCicloPrestacao(competencia_base=(int(ano_str), int(mes_str)))

    resultados_aquisicao, resultado_ciclo_2 = _descobrir_adquirir_e_recalcular_readiness(
        contexto, ciclo_contexto,
    )
    return _trios_prontos(resultados_aquisicao, resultado_ciclo_2)


def _trios_prontos(
    resultados_aquisicao: Tuple[ResultadoAquisicaoPorNecessidade, ...],
    resultado_ciclo_2: ResultadoCicloPrestacao,
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Gate de readiness POR CLIENTE + elegibilidade J1 sobre um
    snapshot JÁ calculado -- extraído de `resultados_aquisicao_prontos_
    por_cliente` (comportamento idêntico) para que o diagnóstico da
    Prestação upstream use exatamente o mesmo filtro, sem recomputar."""
    saida: list = []
    for resultado_cliente in resultado_ciclo_2.resultados_por_cliente:
        if resultado_cliente.pacote.estado != EstadoPacotePrestacao.PRONTO:
            continue  # fail-closed por cliente: readiness insuficiente -> zero Ordem para ele
        resultados_do_cliente = tuple(
            ra for ra in resultados_aquisicao
            if ra.necessidade.cliente == resultado_cliente.cliente
            and ra.necessidade.competencia == resultado_cliente.competencia
            and _elegivel_para_distribuicao(ra)
        )
        if not resultados_do_cliente:
            continue  # PRONTO sem aquisição própria nesta execução (ex.: documento já no inventário base) -- nada a distribuir aqui
        saida.append((resultado_cliente.cliente, resultado_cliente.competencia, resultados_do_cliente))
    return tuple(saida)


# ==== GATE J1b: UNIDADE DE DISTRIBUIÇÃO = CLIENTE + COMPETÊNCIA +
# COLABORADOR ====
# `OrdemDistribuicaoDocumental` é, por contrato, de destinatário ÚNICO
# (`funcionario_id` + `destinatario`), e `montar_ordem_distribuicao_
# documental_de_prestacao` rejeita mistura de colaboradores. Entregar o
# pacote do cliente inteiro a esse elo fazia todo cliente com 2+
# colaboradores prontos produzir ZERO Ordens. O legado confirma a
# unidade: o envio individual (`/webhook/enviar-whatsapp`, `app.py`) é
# por funcionário e só com documentos individuais (Holerite, Folha
# Ponto); documentos de nível cliente vão no pacote de e-mail POR
# CLIENTE (`/gerar-fila-envios-email`, `/webhook/enviar-email-cliente`),
# nunca ao colaborador.

EVENTO_DOCUMENTO_NIVEL_CLIENTE_FORA_ORDEM_COLABORADOR = 'documento_nivel_cliente_fora_ordem_colaborador'


def _particionar_por_colaborador(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    resultados: Tuple[ResultadoAquisicaoPorNecessidade, ...],
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Particiona os resultados JÁ ELEGÍVEIS de 1 cliente/competência em
    1 grupo por colaborador da necessidade -- a identidade do
    colaborador vem sempre de `necessidade.colaborador`, nunca inferida
    aqui nem pelo canal.

    - Resultado de necessidade SEM colaborador (nível cliente: Extrato,
      FGTS, DCTFWeb, guias) nunca entra em grupo nenhum -- nem anexado a
      um colaborador arbitrário, nem duplicado entre todos; é omitido e
      registrado. Sua distribuição (pacote do cliente) é outra
      capacidade, fora desta.
    - O mesmo documento (`documento_id` + `hash_sha256`) que satisfaz 2+
      necessidades do MESMO colaborador aparece 1 vez na Ordem (primeira
      ocorrência); o vínculo necessidade->documento continua existindo
      em `resultados_aquisicao`, só não é repetido na Ordem.
    - Grupos em ordem determinística por `colaborador.entidade_id`;
      dentro do grupo, documentos ordenados por (`documento_id`,
      `hash_sha256`) -- a posição do documento faz parte da identidade
      da Ordem (`event_id`), então a ordem em que a fonte de candidatos
      devolveu os documentos nunca pode gerar uma Ordem "nova" para o
      mesmo conjunto (replay duplicado). Nunca depende da ordem de
      listagem de colaboradores nem de documentos."""
    grupos: dict = {}
    for resultado in resultados:
        colaborador = resultado.necessidade.colaborador
        if colaborador is None:
            # WARNING, não INFO: o destino DE DOMÍNIO desse documento é a
            # intenção do cliente (`intencoes_distribuicao_cliente_prontas`),
            # mas a ENTREGA ao cliente ainda não existe -- lacuna conhecida
            # que precisa ficar visível, nunca silenciosa.
            _logger.warning(
                '%s documento_id=%s cliente=%s competencia=%s',
                EVENTO_DOCUMENTO_NIVEL_CLIENTE_FORA_ORDEM_COLABORADOR,
                resultado.documento_id, cliente.entidade_id, competencia.entidade_id,
                extra={
                    'evento': EVENTO_DOCUMENTO_NIVEL_CLIENTE_FORA_ORDEM_COLABORADOR,
                    'documento_id': resultado.documento_id,
                    'cliente': cliente.entidade_id,
                    'competencia': competencia.entidade_id,
                },
            )
            continue
        documentos_do_colaborador = grupos.setdefault(colaborador.entidade_id, {})
        documentos_do_colaborador.setdefault((resultado.documento_id, resultado.hash_sha256), resultado)
    return tuple(
        (cliente, competencia, tuple(grupos[colaborador_id][chave] for chave in sorted(grupos[colaborador_id])))
        for colaborador_id in sorted(grupos)
    )


def resultados_aquisicao_prontos_por_colaborador(
    contexto: 'ContextoComposicaoPrestacao',
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Mesma saída de `resultados_aquisicao_prontos_por_cliente` (mesmo
    formato de trio, mesmo gate de readiness POR CLIENTE, mesmo filtro
    de elegibilidade do J1), particionada em 1 trio por (cliente,
    competência, colaborador) -- a unidade que `OrdemDistribuicao
    Documental` aceita. Cada trio vira, a jusante, 1 Ordem de
    destinatário único; o `event_id` já difere por colaborador
    (`funcionario_id`/`destinatario`/documentos fazem parte da
    identidade da Ordem)."""
    saida: list = []
    for cliente, competencia, resultados in resultados_aquisicao_prontos_por_cliente(contexto):
        saida.extend(_particionar_por_colaborador(cliente, competencia, resultados))
    return tuple(saida)


# ==== NÍVEL CLIENTE: INTENÇÃO DE DISTRIBUIÇÃO DO CLIENTE ====
# Complemento do Gate J1b: o que `_particionar_por_colaborador` omite
# (necessidade sem colaborador) passa a ter destino no DOMÍNIO -- uma
# `IntencaoDistribuicaoCliente` por cliente+competência, sem
# `funcionario_id`, sem endereço, sem canal. Mesmo gate de readiness e
# mesma elegibilidade (`resultados_aquisicao_prontos_por_cliente` +
# `_elegivel_para_distribuicao`), nunca uma regra paralela.

EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE = 'documento_com_colaborador_fora_intencao_cliente'
EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO = 'cliente_falhou_intencao_distribuicao'


def _documento_identifica_colaborador(resultado: ResultadoAquisicaoPorNecessidade) -> bool:
    """O documento tem granularidade de PESSOA? Então nunca entra no
    pacote do cliente, mesmo que a necessidade que o buscou seja de nível
    cliente (granularidades diferentes; cf. o inverso em
    `_particionar_por_colaborador`). Fail-closed por si só (não depende de
    a elegibilidade já ter barrado antes): basta a dimensão COLABORADOR
    existir na resolução em qualquer estado diferente de NAO_APLICAVEL --
    confirmada, ambígua ou não encontrada. Resolução ausente também não
    prova nível cliente. Genérico: olha a dimensão, nunca o nome do tipo."""
    for execucao in resultado.resultados_corredor:
        resolucao = execucao.resultado_corredor.resolucao_semantica
        if resolucao is None:
            return True
        for item in resolucao.resolucoes:
            if (
                item.dimensao == DimensaoResolucao.COLABORADOR
                and item.estado != EstadoResolucaoDimensao.NAO_APLICAVEL
            ):
                return True
    return False


def _separar_nivel_cliente(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    resultados: Tuple[ResultadoAquisicaoPorNecessidade, ...],
) -> Tuple[ResultadoAquisicaoPorNecessidade, ...]:
    """Dos resultados JÁ ELEGÍVEIS de 1 cliente/competência, devolve só
    os de nível cliente (`necessidade.colaborador is None`) cujo documento
    não identifica colaborador -- ordem determinística por (`documento_id`,
    `hash_sha256`, tipo da necessidade), independente da ordem da fonte."""
    selecionados = []
    for resultado in resultados:
        if resultado.necessidade.colaborador is not None:
            continue  # vai (ou já foi) para a Ordem do próprio colaborador
        if _documento_identifica_colaborador(resultado):
            _logger.warning(
                '%s documento_id=%s cliente=%s competencia=%s',
                EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE,
                resultado.documento_id, cliente.entidade_id, competencia.entidade_id,
                extra={
                    'evento': EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE,
                    'documento_id': resultado.documento_id,
                    'cliente': cliente.entidade_id,
                    'competencia': competencia.entidade_id,
                },
            )
            continue
        selecionados.append(resultado)
    return tuple(sorted(
        selecionados,
        key=lambda r: (r.documento_id, r.hash_sha256, r.necessidade.tipo_documental),
    ))


def particionar_nivel_cliente(
    trios_prontos: Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...],
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Pura, sobre trios JÁ calculados por `resultados_aquisicao_prontos_
    por_cliente` -- permite a um composition root derivar Ordens de
    colaborador (`_particionar_por_colaborador`) e intenções de cliente do
    MESMO snapshot, sem rodar descoberta/aquisição/readiness duas vezes."""
    saida: list = []
    for cliente, competencia, resultados in trios_prontos:
        nivel_cliente = _separar_nivel_cliente(cliente, competencia, resultados)
        if nivel_cliente:
            saida.append((cliente, competencia, nivel_cliente))
    return tuple(saida)


def resultados_aquisicao_prontos_nivel_cliente(
    contexto: 'ContextoComposicaoPrestacao',
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Mesmo gate de readiness POR CLIENTE e mesma elegibilidade de
    `resultados_aquisicao_prontos_por_cliente`, restrito aos resultados de
    nível cliente -- 1 trio por (cliente, competência) com ao menos 1
    documento de nível cliente elegível. Cliente sem nenhum é omitido."""
    return particionar_nivel_cliente(resultados_aquisicao_prontos_por_cliente(contexto))


def intencoes_distribuicao_cliente_de_trios(
    trios_nivel_cliente: Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...],
) -> Tuple[IntencaoDistribuicaoCliente, ...]:
    """Monta as intenções a partir de trios de nível cliente já
    separados (`particionar_nivel_cliente`). Isolamento: erro de DOMÍNIO
    de 1 cliente (`IntencaoDistribuicaoClienteError`) é registrado com
    evento estável e não impede os demais; qualquer outra exceção
    (sistêmica) propaga -- nunca vira "documento faltante"."""
    intencoes: list = []
    for cliente, competencia, resultados in trios_nivel_cliente:
        try:
            intencoes.append(montar_intencao_distribuicao_cliente(
                cliente=cliente, competencia=competencia, resultados_aquisicao=resultados,
            ))
        except IntencaoDistribuicaoClienteError as exc:
            _logger.error(
                '%s cliente=%s competencia=%s exception_type=%s',
                EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO,
                cliente.entidade_id, competencia.entidade_id, type(exc).__name__,
                extra={
                    'evento': EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO,
                    'cliente': cliente.entidade_id,
                    'competencia': competencia.entidade_id,
                    'exception_type': type(exc).__name__,
                },
            )
    return tuple(intencoes)


def intencoes_distribuicao_cliente_prontas(
    contexto: 'ContextoComposicaoPrestacao',
) -> Tuple[IntencaoDistribuicaoCliente, ...]:
    """1 `IntencaoDistribuicaoCliente` por cliente+competência PRONTO com
    documentos de nível cliente elegíveis. Para na INTENÇÃO: nenhum
    destinatário concreto, nenhum canal, nenhum Orquestrador, nenhum
    transporte.

    LIMITE DECLARADO: a intenção contém só os documentos de nível cliente
    ADQUIRIDOS NESTA EXECUÇÃO (mesmo recorte das Ordens de colaborador).
    Documento que satisfaz a readiness só via `fonte_inventario_base`
    (hoje ids Airtable) não entra -- se o cliente depender dele, a
    intenção é um SUBCONJUNTO do pacote. Fechar isso depende do índice
    interno documento<->necessidade (J3), nunca de promover id Airtable a
    documento interno."""
    return intencoes_distribuicao_cliente_de_trios(resultados_aquisicao_prontos_nivel_cliente(contexto))


# ==== DIAGNÓSTICO DE SNAPSHOT ÚNICO (composition root / piloto) ====


def particionar_por_colaborador(
    trios_prontos: Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...],
) -> Tuple[Tuple[ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]], ...]:
    """Mesma partição de `resultados_aquisicao_prontos_por_colaborador`,
    sobre trios JÁ calculados (nunca recomputa o ciclo)."""
    saida: list = []
    for cliente, competencia, resultados in trios_prontos:
        saida.extend(_particionar_por_colaborador(cliente, competencia, resultados))
    return tuple(saida)


@dataclasses.dataclass(frozen=True)
class DiagnosticoClientePrestacao:
    """Visão SANITIZADA de 1 cliente/competência no snapshot: só ids
    opacos e contagens -- nunca CPF, nome, e-mail ou conteúdo."""

    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    estado_pacote: str
    motivos: Tuple[str, ...]
    tipos_faltantes: Tuple[str, ...]
    necessidades_pendentes: int
    documentos_candidatos: Tuple[str, ...]
    documentos_elegiveis: Tuple[str, ...]
    documentos_rejeitados: Tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class DiagnosticoPrestacaoUpstream:
    """1 ÚNICO cálculo de descoberta -> aquisição -> readiness, do qual
    derivam, sem recomputar, as Ordens de colaborador e as intenções de
    cliente -- nunca 2 snapshots divergentes."""

    clientes: Tuple[DiagnosticoClientePrestacao, ...]
    trios_prontos: Tuple = dataclasses.field(repr=False, default=())

    def grupos_por_colaborador(self):
        return particionar_por_colaborador(self.trios_prontos)

    def intencoes_cliente(self) -> Tuple[IntencaoDistribuicaoCliente, ...]:
        return intencoes_distribuicao_cliente_de_trios(particionar_nivel_cliente(self.trios_prontos))


def diagnosticar_prestacao_upstream(contexto: 'ContextoComposicaoPrestacao') -> DiagnosticoPrestacaoUpstream:
    """Mesma composição de `resultados_aquisicao_prontos_por_cliente`
    (política de competência, descoberta, aquisição por necessidade,
    âncora, readiness, `_trios_prontos`), expondo também o diagnóstico por
    cliente para o relatório do piloto shadow. Leitura pura: não cria
    `ExecucaoPrestacao`, não escreve nada."""
    if contexto.politica_competencia is not None:
        verificar_politica_sem_override_por_tipo(contexto.politica_competencia)
    ano_str, mes_str = contexto.competencia_base.split('-')
    ciclo_contexto = ContextoCicloPrestacao(competencia_base=(int(ano_str), int(mes_str)))

    resultados_aquisicao, resultado_ciclo_2 = _descobrir_adquirir_e_recalcular_readiness(contexto, ciclo_contexto)
    trios = _trios_prontos(resultados_aquisicao, resultado_ciclo_2)

    clientes = []
    for resultado_cliente in resultado_ciclo_2.resultados_por_cliente:
        do_cliente = [
            ra for ra in resultados_aquisicao
            if ra.necessidade.cliente == resultado_cliente.cliente
            and ra.necessidade.competencia == resultado_cliente.competencia
        ]
        elegiveis = sorted({ra.documento_id for ra in do_cliente if _elegivel_para_distribuicao(ra)})
        candidatos = sorted({ra.documento_id for ra in do_cliente})
        pacote = resultado_cliente.pacote
        clientes.append(DiagnosticoClientePrestacao(
            cliente=resultado_cliente.cliente,
            competencia=resultado_cliente.competencia,
            estado_pacote=pacote.estado.value,
            motivos=tuple(pacote.motivos),
            tipos_faltantes=tuple(pacote.tipos_faltantes),
            necessidades_pendentes=len(resultado_cliente.necessidades),
            documentos_candidatos=tuple(candidatos),
            documentos_elegiveis=tuple(elegiveis),
            documentos_rejeitados=tuple(d for d in candidatos if d not in set(elegiveis)),
        ))
    return DiagnosticoPrestacaoUpstream(clientes=tuple(clientes), trios_prontos=trios)


def executar_ciclo_prestacao_persistente(
    contexto: ContextoComposicaoPrestacao,
    execucao_id: Optional[str] = None,
) -> ExecucaoPrestacao:
    """Executa ciclo persistente COMPLETO de Prestação de Contas.

    Fluxo (correção pós-Ultraplan "Correlação Necessidade → Aquisição
    → Resolução", sobre a evolução do contrato do ciclo de Prestação
    V1, Incremento 7): descoberta sem âncora -> aquisição ORIENTADA POR
    NECESSIDADE, com vínculo necessidade->documento preservado ->
    avaliação/seleção de âncoras reais DENTRO desse vínculo -> readiness
    com âncora real ou ausência explícita -> atualização da execução.

    1. Criar ou retomar ExecucaoPrestacao
    2. Validar política de competência V1 (fail-closed: nenhum
       deslocamento por tipo_documental suportado nesta V1)
    3. Descoberta de necessidades SEM exigir nenhuma âncora
       (`executar_ciclo_prestacao_descoberta`)
    4. Aquisição ORIENTADA POR NECESSIDADE (`_adquirir_por_
       necessidades`): para cada `NecessidadeDocumentoPrestacao`,
       consulta `contexto.fonte_candidatos_por_necessidade` (nunca
       `repositorio_documentos.listar_todos()` em bloco) -- o
       cliente/competência esperados vêm SEMPRE da própria necessidade,
       nunca inferidos do que o documento resolve. SEM essa fonte
       (`None`, produção hoje), nenhuma aquisição roda -- NUNCA cai de
       volta para a aquisição em bloco legada.
    5. Seleção/validação de âncora real por cliente
       (`avaliar_candidatos_ancora`, INALTERADA, nunca fabricada) --
       avaliada só entre candidatos do MESMO vínculo necessidade-
       >documento (agrupados por cliente/competência esperado da
       necessidade que os buscou), nunca o pool global de toda a
       execução (auditoria pós-Incremento 7/pós-Ultraplan: um pool
       global gera divergência cruzada entre clientes sem nenhuma
       relação real entre si). SEM fallback para `contexto.
       resolucoes_ancora` -- nenhum caller real hoje prova que essas
       entradas são resoluções reais aplicáveis; sem evidência real
       dentro do vínculo legítimo, o cliente fica sem âncora (REVISAR
       explícito, nunca uma pré-informada não verificável)
    6. Segunda execução do ciclo (readiness com âncora real, ou
       ausência explícita -- nunca uma resolução fabricada)
    7. Atualizar estado final da ExecucaoPrestacao

    Args:
        contexto: ContextoComposicaoPrestacao com todas dependências
        execucao_id: Se fornecido, retoma; caso contrário, cria novo

    Returns:
        ExecucaoPrestacao finalizada

    Raises:
        ValueError: Se execução não encontrada, estado inválido, etc.
        PoliticaCompetenciaPorTipoNaoSuportadaError: Se
            `contexto.politica_competencia` tiver deslocamento de
            competência específico por tipo_documental -- contrato V1
            só suporta 1 competência geral por cliente (levantada ANTES
            de criar/retomar a ExecucaoPrestacao -- config inválida
            nunca chega a virar uma execução rastreada).
    """
    # ==== PASSO 1: Validar política de competência V1 ====
    # Fail-closed (evolução do contrato do ciclo de Prestação V1,
    # Incremento 3): levantada aqui, ANTES de criar/retomar a
    # ExecucaoPrestacao -- mesmo padrão de `criar_e_persistir_execucao`
    # (valida `competencia_base` antes de persistir). `None` (política
    # não informada) nunca é avaliado -- comportamento anterior
    # preservado para quem não usa `PoliticaCompetenciaPrestacao`.
    if contexto.politica_competencia is not None:
        verificar_politica_sem_override_por_tipo(contexto.politica_competencia)

    # ==== PASSO 2: Criar ou retomar ExecucaoPrestacao ====
    if execucao_id:
        execucao = retomar_execucao_por_id(execucao_id, contexto.repositorio_execucoes)
    else:
        execucao = criar_e_persistir_execucao(
            competencia_base=contexto.competencia_base,
            repositorio_execucoes=contexto.repositorio_execucoes,
        )

    try:
        ano_str, mes_str = contexto.competencia_base.split('-')
        ciclo_contexto = ContextoCicloPrestacao(
            competencia_base=(int(ano_str), int(mes_str))
        )

        # ==== PASSOS 3-7: descoberta -> aquisição por necessidade ->
        # âncora -> composição de inventário -> segunda execução do
        # ciclo (readiness) ====
        # Extraído para `_descobrir_adquirir_e_recalcular_readiness`
        # (Ultraplan "Delta Final A-F -- Cliente+Competência ->
        # PENDING"), reutilizado também por
        # `resultados_aquisicao_prontos_por_cliente` -- comportamento
        # idêntico ao que existia inline aqui antes da extração.
        _resultados_aquisicao_nao_usados, resultado_ciclo_2 = (
            _descobrir_adquirir_e_recalcular_readiness(contexto, ciclo_contexto)
        )

        # ==== PASSO 8: Determinar estado final ====
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

        # ==== PASSO 9: Atualizar ExecucaoPrestacao ====
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
