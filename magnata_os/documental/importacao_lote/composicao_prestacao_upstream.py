"""COMPOSIÇÃO DE BORDA -- Prestação upstream real (J3).

`cliente + competência` -> fontes reais -> necessidades -> candidatos
INTERNOS (índice J3) -> aquisição/resolução -> readiness -> pacote ->
partição -> Ordens de colaborador + `IntencaoDistribuicaoCliente`.

Como `composicao_corredor_readonly.py`, é borda: só aqui se compõem
adapters reais (Airtable read-only transitório, Postgres injetado). Não é
um runner paralelo nem um motor novo:

  - o contexto do ciclo é o `ContextoComposicaoPrestacao` já existente;
  - as fontes do corredor são as MESMAS instâncias de
    `ExecucaoCorredorReadonly` (nunca reconstruídas);
  - o snapshot é `diagnosticar_prestacao_upstream` (1 cálculo), do qual
    derivam as Ordens (via `executar_prestacao_contato_ate_pending_
    shadow_v1(..., trios_prontos=...)`, Orquestrador) e as intenções de
    cliente;
  - o backfill reusa `ExecucaoCorredorReadonly.processar_documento` --
    exatamente o produtor da ingestão (nenhuma lógica especial).

Nenhum transporte. Nenhuma escrita no Airtable. Relatório sem PII.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from typing import Dict, Iterable, Optional, Tuple

from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    CADASTRO_REQUISITOS_PRESTACAO_V2,
    FonteRequisitosPrestacaoCanonica,
)
from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    ContextoCicloPrestacao,
    PoliticaCompetenciaPrestacao,
)
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
    DiagnosticoPrestacaoUpstream,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
from magnata_os.classificacao.pacote_prestacao import (
    FonteDestinatarioOrganizacionalCliente,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos, ArquivoNaoEncontrado

from .adapters.airtable_clientes_prestacao import FonteClientesPrestacaoAirtable
from .adapters.airtable_leitura import LeitorAirtableSomenteLeitura
from .composicao_corredor_readonly import ExecucaoCorredorReadonly

_logger = logging.getLogger(__name__)

EVENTO_CLIENTE_SEM_COMPETENCIA_NO_CICLO = 'prestacao_cliente_sem_competencia_no_ciclo'


def _competencia_base_tupla(competencia_base: str) -> Tuple[int, int]:
    ano, mes = competencia_base.split('-')
    return int(ano), int(mes)


class _FonteClientesRestrita:
    """Restringe a fonte real ao(s) cliente(s) pedido(s) -- nunca inclui
    cliente que a fonte não liste como ativo (fail-closed)."""

    def __init__(self, fonte_base, clientes: Tuple[ReferenciaCanonica, ...]) -> None:
        self._fonte_base = fonte_base
        self._clientes = frozenset(clientes)

    def listar_ativos(self, contexto):
        return tuple(c for c in self._fonte_base.listar_ativos(contexto) if c in self._clientes)


def competencias_por_cliente_do_ciclo(
    clientes: Iterable[ReferenciaCanonica],
    ciclo: ContextoCicloPrestacao,
    politica: PoliticaCompetenciaPrestacao = POLITICA_COMPETENCIA_PRESTACAO_V1,
) -> Dict[ReferenciaCanonica, ReferenciaCanonica]:
    """1 competência efetiva por cliente pela MESMA política V1 do
    corredor (V1 não aceita deslocamento por tipo -- `tipo_documental=''`).
    Cliente sem competência determinável fica FORA do mapa e é registrado
    (evento estável) -- o ciclo o omite, nunca inventa uma competência."""
    mapa: Dict[ReferenciaCanonica, ReferenciaCanonica] = {}
    for cliente in clientes:
        competencia = politica.competencia_esperada_para(ciclo, cliente, '')
        if competencia is None:
            _logger.warning(
                '%s cliente=%s', EVENTO_CLIENTE_SEM_COMPETENCIA_NO_CICLO, cliente.entidade_id,
                extra={'evento': EVENTO_CLIENTE_SEM_COMPETENCIA_NO_CICLO, 'cliente': cliente.entidade_id},
            )
            continue
        ano, mes = competencia
        mapa[cliente] = ReferenciaCanonica('COMPETENCIA', f'{ano:04d}-{mes:02d}')
    return mapa


def compor_contexto_prestacao_upstream(
    *,
    leitor: LeitorAirtableSomenteLeitura,
    execucao_corredor: ExecucaoCorredorReadonly,
    competencia_base: str,
    fonte_candidatos_por_necessidade,
    repositorio_documentos,
    armazenamento: ArmazenamentoArquivos,
    repositorio_execucoes_prestacao,
    clientes: Optional[Tuple[ReferenciaCanonica, ...]] = None,
    politica_competencia: PoliticaCompetenciaPrestacao = POLITICA_COMPETENCIA_PRESTACAO_V1,
) -> ContextoComposicaoPrestacao:
    """Monta o `ContextoComposicaoPrestacao` REAL. Fontes:
      - clientes, colaboradores esperados, vínculo, unidade/posto,
        cliente direto, universo de colaboradores: Airtable read-only
        TRANSITÓRIO (decisão J2), atrás dos Protocols já existentes;
      - requisitos: cadastro canônico V2 (interno);
      - candidatos por necessidade: índice J3 (interno, Postgres);
      - documentos/blobs: repositório e armazenamento internos.
    Não lê ambiente; não escreve nada."""
    ciclo = ContextoCicloPrestacao(competencia_base=_competencia_base_tupla(competencia_base))
    fonte_clientes = FonteClientesPrestacaoAirtable(leitor)
    if clientes is not None:
        fonte_clientes = _FonteClientesRestrita(fonte_clientes, clientes)
    return ContextoComposicaoPrestacao(
        competencia_base=competencia_base,
        fonte_clientes=fonte_clientes,
        fonte_requisitos=FonteRequisitosPrestacaoCanonica(CADASTRO_REQUISITOS_PRESTACAO_V2),
        repositorio_execucoes=repositorio_execucoes_prestacao,
        requisitos_base=CADASTRO_REQUISITOS_PRESTACAO_V2.requisitos_base_documentais(),
        competencias_por_cliente=competencias_por_cliente_do_ciclo(
            fonte_clientes.listar_ativos(ciclo), ciclo, politica_competencia,
        ),
        politica_competencia=politica_competencia,
        fonte_colaboradores_esperados=execucao_corredor.fonte_colaboradores_esperados,
        repositorio_documentos=repositorio_documentos,
        armazenamento_arquivos=armazenamento,
        # Tipo universal por colaborador no MESMO vocabulário do motor
        # (`TIPO_HOLERITE`), nunca o default textual divergente do contexto.
        tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
        fonte_candidatos_por_necessidade=fonte_candidatos_por_necessidade,
        candidatos_colaborador=tuple(leitor.listar_funcionarios()),
        fonte_vinculos=execucao_corredor.fonte_vinculos,
        fonte_unidade_posto=execucao_corredor.fonte_unidade_posto,
        fonte_cliente_direto=execucao_corredor.fonte_cliente_direto,
    )


# ---------------------------------------------------------------------------
# Piloto shadow: relatório sanitizado de 1 snapshot
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class RelatorioPilotoPrestacaoUpstream:
    """Somente ids opacos, contagens e motivos -- nunca CPF, nome, e-mail,
    telefone ou conteúdo documental."""

    clientes: Tuple[dict, ...]
    grupos_colaborador: Tuple[dict, ...]
    intencoes_cliente: Tuple[dict, ...]
    bloqueios: Tuple[str, ...]


def montar_relatorio_piloto(
    diagnostico: DiagnosticoPrestacaoUpstream,
    fonte_destinatario: Optional[FonteDestinatarioOrganizacionalCliente] = None,
) -> RelatorioPilotoPrestacaoUpstream:
    clientes = tuple(
        {
            'cliente': d.cliente.entidade_id,
            'competencia': d.competencia.entidade_id,
            'estado_pacote': d.estado_pacote,
            'motivos': list(d.motivos),
            'tipos_faltantes': list(d.tipos_faltantes),
            'necessidades_pendentes': d.necessidades_pendentes,
            'documentos_candidatos': list(d.documentos_candidatos),
            'documentos_elegiveis': list(d.documentos_elegiveis),
            'documentos_rejeitados': list(d.documentos_rejeitados),
        }
        for d in diagnostico.clientes
    )
    grupos = tuple(
        {
            'cliente': cliente.entidade_id,
            'competencia': competencia.entidade_id,
            'colaborador': grupo[0].necessidade.colaborador.entidade_id,
            'documentos': [r.documento_id for r in grupo],
        }
        for cliente, competencia, grupo in diagnostico.grupos_por_colaborador()
    )
    intencoes = []
    bloqueios = []
    for intencao in diagnostico.intencoes_cliente():
        destinatario_resolvido = None
        if fonte_destinatario is not None:
            destinatario_resolvido = bool(fonte_destinatario.enderecos_para(intencao.cliente, intencao.papel_destinatario))
            if not destinatario_resolvido:
                bloqueios.append(
                    f'destinatario_organizacional_ausente cliente={intencao.cliente.entidade_id} '
                    f'papel={intencao.papel_destinatario.value}'
                )
        intencoes.append({
            'intencao_id': intencao.intencao_id,
            'cliente': intencao.cliente.entidade_id,
            'competencia': intencao.competencia.entidade_id,
            'papel_destinatario': intencao.papel_destinatario.value,
            'documentos': list(intencao.documento_ids),
            'destinatario_resolvido': destinatario_resolvido,
        })
    for d in diagnostico.clientes:
        if d.estado_pacote != 'PRONTO':
            bloqueios.append(
                f'readiness cliente={d.cliente.entidade_id} estado={d.estado_pacote} '
                f'motivos={",".join(d.motivos) or "-"} faltantes={",".join(d.tipos_faltantes) or "-"}'
            )
    return RelatorioPilotoPrestacaoUpstream(
        clientes=clientes, grupos_colaborador=grupos, intencoes_cliente=tuple(intencoes),
        bloqueios=tuple(bloqueios),
    )


# ---------------------------------------------------------------------------
# Backfill do índice J3 -- PROJETADO e testado; NUNCA executado nesta fase
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class RelatorioBackfillCorrelacao:
    processados: int = 0
    com_relacao_vigente: int = 0
    sem_relacao: int = 0            # corredor rodou; documento em revisão / não resolvido
    sem_blob: int = 0
    mime_nao_suportado: int = 0
    relacoes_novas: int = 0
    relacoes_reativadas: int = 0
    relacoes_superadas: int = 0      # reprocessamento mudou o escopo (conflito com o índice anterior)
    erros: Tuple[Tuple[str, str], ...] = ()   # (documento_id, tipo da exceção)
    ultimo_documento_id: Optional[str] = None  # ponto de retomada


def executar_backfill_correlacao(
    *,
    documentos: Iterable,
    armazenamento: ArmazenamentoArquivos,
    execucao_corredor: ExecucaoCorredorReadonly,
    candidatos_colaborador: Tuple,
    retomar_apos: Optional[str] = None,
    limite: Optional[int] = None,
) -> RelatorioBackfillCorrelacao:
    """Reprocessa Documentos JÁ EXISTENTES (e seus blobs já armazenados)
    pelo MESMO produtor da ingestão: `execucao_corredor.processar_
    documento`, construída com `registro_correlacao` -- nenhuma lógica
    especial de classificação.

      - idempotente: o índice só grava quando o estado da relação muda;
      - reiniciável: ordem determinística por `documento_id`;
        `retomar_apos` pula tudo até o último processado; `limite` fatia;
      - auditável: relatório com contagens e o ponto de retomada; toda
        observação gravada tem origem, evidência e timestamp;
      - isolado: erro em 1 documento é contado (tipo da exceção, sem
        mensagem crua) e o lote continua;
      - por competência: a execução carrega 1 ciclo (competência
        esperada), como a ingestão -- rodar 1 backfill por competência.
    """
    if not getattr(execucao_corredor, 'produz_indice_correlacao', False):
        # Falha nunca silenciosa: sem produtor, todo documento pareceria
        # "sem_relacao" e nada seria gravado.
        raise RuntimeError('backfill exige execução do corredor COM produtor do índice (registro_correlacao)')
    if not tuple(candidatos_colaborador):
        # Sem universo de colaboradores, todo documento de colaborador iria
        # para revisão e o produtor SUPERARIA relações válidas -- degradação
        # silenciosa. Obrigatório, nunca default vazio.
        raise RuntimeError('backfill exige o universo de colaboradores (candidatos_colaborador) não vazio')
    rel = dict(processados=0, com_relacao_vigente=0, sem_relacao=0, sem_blob=0, mime_nao_suportado=0,
               relacoes_novas=0, relacoes_reativadas=0, relacoes_superadas=0)
    erros = []
    ultimo = None
    for documento in sorted(documentos, key=lambda d: d.documento_id):
        if retomar_apos is not None and documento.documento_id <= retomar_apos:
            continue
        if limite is not None and rel['processados'] + rel['sem_blob'] + rel['mime_nao_suportado'] + len(erros) >= limite:
            break
        ultimo = documento.documento_id
        if documento.mime_type != 'application/pdf':
            rel['mime_nao_suportado'] += 1
            continue
        try:
            with armazenamento.abrir_leitura(documento.hash_sha256) as arquivo:
                conteudo = arquivo.read()
        except ArquivoNaoEncontrado:
            rel['sem_blob'] += 1
            continue
        execucao_corredor.ultimo_registro_correlacao = None  # nunca herda contagem de outro documento
        try:
            execucao_corredor.processar_documento(
                documento.documento_id, documento.hash_sha256, pdf_bytes=conteudo,
                candidatos_colaborador=candidatos_colaborador,
            )
        except Exception as exc:  # isolado e contado; nunca silencioso
            erros.append((documento.documento_id, type(exc).__name__))
            continue
        rel['processados'] += 1
        registro = execucao_corredor.ultimo_registro_correlacao
        if registro is None or (registro.novas + registro.reativadas + registro.inalteradas) == 0:
            rel['sem_relacao'] += 1
        else:
            rel['com_relacao_vigente'] += 1
        if registro is not None:
            rel['relacoes_novas'] += registro.novas
            rel['relacoes_reativadas'] += registro.reativadas
            rel['relacoes_superadas'] += registro.superadas
    return RelatorioBackfillCorrelacao(**rel, erros=tuple(erros), ultimo_documento_id=ultimo)


# ---------------------------------------------------------------------------
# Compositor de ambiente (lê credencial/URL só aqui; não executado em teste)
# ---------------------------------------------------------------------------

def compor_contexto_prestacao_upstream_a_partir_do_ambiente(
    *,
    competencia_base: str,
    armazenamento: ArmazenamentoArquivos,
    clientes: Optional[Tuple[ReferenciaCanonica, ...]] = None,
    ambiente: Optional[dict] = None,
    com_produtor_indice: bool = False,
):
    """Airtable read-only (`AIRTABLE_API_KEY`) + Postgres (`DATABASE_URL`,
    `abrir_conexao`). Devolve `(contexto, execucao_corredor, conexao,
    conexao_indice)` -- `conexao_indice` é `None` sem produtor; quem chama
    fecha as duas.
    Exige a migration orquestrador 0007 aplicada no banco -- sem ela, a
    fonte de candidatos falha explicitamente (nunca vira "sem candidato").
    Somente leitura nos sistemas externos; nenhuma chamada de transporte.

    Por padrão a execução do corredor NÃO recebe o produtor do índice
    (piloto/diagnóstico é leitura pura). `com_produtor_indice=True`
    (ingestão/backfill autorizados) liga o produtor numa conexão PRÓPRIA:
    o commit/rollback do índice nunca afeta a conexão de leitura."""
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        RepositorioCorrelacaoDocumentoPrestacaoPostgres,
        construir_fonte_candidatos_por_necessidade_postgres,
    )
    from magnata_os.classificacao.adapters.postgres_execucoes_prestacao import (
        RepositorioExecucoesPrestacaoPostgres,
    )
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres

    env = os.environ if ambiente is None else ambiente
    chave = env.get('AIRTABLE_API_KEY')
    if not chave:
        raise RuntimeError('AIRTABLE_API_KEY ausente -- composição real não pode prosseguir')
    leitor = LeitorAirtableSomenteLeitura(chave)
    abertas = []
    try:
        conexao = abrir_conexao(ambiente=env)
        abertas.append(conexao)
        conexao_indice = abrir_conexao(ambiente=env) if com_produtor_indice else None
        if conexao_indice is not None:
            abertas.append(conexao_indice)
        registro = (
            RepositorioCorrelacaoDocumentoPrestacaoPostgres(conexao_indice)
            if conexao_indice is not None else None
        )
        execucao = ExecucaoCorredorReadonly(
            leitor, ContextoCicloPrestacao(competencia_base=_competencia_base_tupla(competencia_base)),
            registro_correlacao=registro,
        )
        contexto = compor_contexto_prestacao_upstream(
            leitor=leitor, execucao_corredor=execucao, competencia_base=competencia_base,
            fonte_candidatos_por_necessidade=construir_fonte_candidatos_por_necessidade_postgres(conexao),
            repositorio_documentos=RepositorioDocumentosPostgres(conexao), armazenamento=armazenamento,
            repositorio_execucoes_prestacao=RepositorioExecucoesPrestacaoPostgres(conexao), clientes=clientes,
        )
    except Exception:
        # Falha no meio da composição: nenhuma conexão fica órfã (quem chama
        # só passa a ser dono delas no retorno bem-sucedido).
        for aberta in abertas:
            try:
                aberta.close()
            except Exception:  # noqa: BLE001 -- fechamento best effort; a falha original propaga
                pass
        raise
    return contexto, execucao, conexao, conexao_indice
