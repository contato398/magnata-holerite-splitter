"""Escritor — orquestração da ESCRITA REAL de um item já classificado
pelo dry-run (`orquestrador.py`/`dominio.py`). Fase 4.

Nunca refaz matching/classificação (isso já aconteceu — `resultado` é o
`ResultadoItem` final do dry-run). Só processa automaticamente itens
`EXACT` + `pronto_para_gravacao`; qualquer outra classificação é
ignorada aqui (fila de exceção humana, fora deste módulo).

Fluxo (macrocomando desta fase, §8):
  item de execução (idempotente por lote+manifesto)
  → documento físico por hash (reaproveita modulo01/repositorio.py)
  → identidade lógica / versionamento (nunca supersede sozinho)
  → Airtable create (pulado se já existe external_record_id)
  → upload (pulado se já confirmado)
  → confirmação por releitura
  → evento de auditoria (quando documento_id existir)
  → compensação condicional em falha de upload

Cada checkpoint é persistido antes do próximo passo — uma nova chamada
com o MESMO (lote_id, manifesto_item_id) sempre retoma do ponto salvo,
nunca reprocessa do zero um item em situação terminal (ver
`contratos_execucao.SITUACOES_TERMINAIS`).

Todo checkpoint passa por `_persistir_item`, que salva o `ItemExecucao`
E registra um `EventoItemExecucao` na trilha append-only do item
(`eventos_itens_importacao_lote`, migration 0009 — correção de
auditoria) — cobre exatamente a fase ANTES de `documento_id` existir,
que `eventos_documentais` (FK documento_id NOT NULL) não representa.
A sequência completa (execução → item → estados → tentativas →
transições → falhas → retomadas) é reconstruível só a partir dessa
trilha, sem depender de log.

`nome_referencia` (nome do manifesto, PII) só passa adiante para o
Airtable — nunca é persistido em `ItemExecucao`, nunca aparece em
`ResultadoEscrita`, nunca é logado (mesma disciplina de `cpf_extraido`
em orquestrador.py).
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from ..modulo01.dominio import Documento, EventoHistorico, StatusDocumento, gerar_correlation_id, gerar_documento_id
from ..modulo01.repositorio import RepositorioDocumentos, RepositorioHistorico
from . import dominio, dominio_versionamento
from .adapters.airtable_escrita import EscritorAirtable, formatar_folha_mensal
from .contratos import ConfiguracaoExecucao, ResultadoItem
from .contratos_execucao import (
    SITUACOES_TERMINAIS,
    EventoItemExecucao,
    ItemExecucao,
    ResultadoEscrita,
    SituacaoItemExecucao,
    VersionamentoLogico,
)
from .dominio_versionamento import ResultadoVerificacaoVersao
from .repositorio_execucao import (
    RepositorioEventosItemExecucao,
    RepositorioItensExecucao,
    RepositorioVersionamentoLogico,
)

# Situações finais que valem um evento de auditoria (ver eventos_documentais,
# §13 do macrocomando) — nunca em toda transição intermediária, só quando o
# item chega a um resultado que interessa auditar.
_SITUACOES_AUDITADAS = frozenset({
    SituacaoItemExecucao.SUCESSO,
    SituacaoItemExecucao.FAILED_COMPENSATED,
    SituacaoItemExecucao.FAILED_ORPHANED,
    SituacaoItemExecucao.BLOQUEADO_CONFLITO_VERSAO,
})


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


def gerar_item_execucao_id() -> str:
    return str(uuid.uuid4())


def _sanitizar_erro(exc: Exception) -> str:
    """Nunca propaga a exceção crua para o registro persistido — só o
    tipo + os primeiros 500 caracteres da mensagem (mesmo teto de
    `ErroEscritaAirtable.body_text`). Não há CPF/nome nessas mensagens
    por construção (vêm de HTTP/validação, não de dado de negócio)."""
    return f'{type(exc).__name__}: {str(exc)[:500]}'


def _persistir_item(
    item: ItemExecucao,
    lote_id: str,
    repositorio_itens: RepositorioItensExecucao,
    repositorio_eventos_item: RepositorioEventosItemExecucao,
) -> None:
    """Persiste o item E registra o evento correspondente na trilha
    append-only do ITEM (`eventos_itens_importacao_lote`) — correção de
    auditoria desta rodada. TODO ponto do fluxo que muda o item passa
    por aqui (nunca um `repositorio_itens.salvar(item)` solto), para que
    a sequência completa de transições seja reconstruível sem depender
    de log, inclusive antes de `documento_id` existir. `detalhes` nunca
    contém PII — só IDs/flags já sanitizados do próprio `ItemExecucao`."""
    repositorio_itens.salvar(item)
    repositorio_eventos_item.registrar(EventoItemExecucao(
        item_importacao_id=item.item_importacao_id,
        lote_id=lote_id,
        documento_id=item.documento_id,
        situacao=item.situacao,
        tentativas=item.tentativas,
        erro_sanitizado=item.ultimo_erro_sanitizado,
        timestamp=item.atualizado_em,
        detalhes={
            'external_record_id': item.external_record_id,
            'external_criado_por_esta_execucao': item.external_criado_por_esta_execucao,
            'attachment_confirmado': item.attachment_confirmado,
        },
    ))


def escrever_item(
    resultado: ResultadoItem,
    pdf_bytes: bytes,
    nome_arquivo: str,
    nome_referencia: str,
    config: ConfiguracaoExecucao,
    lote_id: str,
    repositorio_documentos: RepositorioDocumentos,
    repositorio_historico: RepositorioHistorico,
    repositorio_itens: RepositorioItensExecucao,
    repositorio_eventos_item: RepositorioEventosItemExecucao,
    repositorio_versionamento: RepositorioVersionamentoLogico,
    escritor_airtable: EscritorAirtable,
    gerador_item_execucao_id: Callable[[], str] = gerar_item_execucao_id,
    gerador_documento_id: Callable[[], str] = gerar_documento_id,
    relogio: Callable[[], datetime] = _relogio_padrao,
) -> ResultadoEscrita:
    # ── 0. Só EXACT + pronto_para_gravacao é candidato automático ──────────
    if resultado.classificacao.value != 'exact' or not resultado.pronto_para_gravacao:
        return ResultadoEscrita(
            item_importacao_id=None, manifesto_item_id=resultado.manifesto_item_id,
            situacao=SituacaoItemExecucao.IGNORADO_NAO_EXACT, documento_id=None,
            external_record_id=None, processado=False,
            motivo=f'classificacao={resultado.classificacao.value} nao e candidato automatico',
        )

    agora = relogio()
    identidade_ingestao = dominio.calcular_identidade_ingestao(
        config.message_id_estavel, config.package_sha256, resultado.manifesto_item_id)

    def _fabricar_item() -> ItemExecucao:
        return ItemExecucao(
            item_importacao_id=gerador_item_execucao_id(),
            lote_id=lote_id,
            manifesto_item_id=resultado.manifesto_item_id,
            tipo_documental=resultado.tipo_documental,
            documento_id=None,
            identidade_ingestao=identidade_ingestao,
            situacao=SituacaoItemExecucao.PENDENTE,
            tentativas=0,
            external_record_id=None,
            external_criado_por_esta_execucao=False,
            attachment_confirmado=False,
            ultimo_erro_sanitizado=None,
            criado_em=agora,
            atualizado_em=agora,
        )

    item, _criado_agora = repositorio_itens.criar_se_ausente(
        lote_id, resultado.manifesto_item_id, _fabricar_item)
    if _criado_agora:
        # criar_se_ausente já persiste o item (atomicamente, via
        # repositório) -- só falta o evento de criação, que _persistir_item
        # faria de novo o salvar() desnecessariamente. Registrado direto.
        repositorio_eventos_item.registrar(EventoItemExecucao(
            item_importacao_id=item.item_importacao_id, lote_id=lote_id, documento_id=None,
            situacao=item.situacao, tentativas=item.tentativas, erro_sanitizado=None,
            timestamp=item.criado_em, detalhes={'evento': 'item_criado'},
        ))

    # ── 1. Idempotência: item em situação terminal nunca é reprocessado ────
    if item.situacao in SITUACOES_TERMINAIS:
        return ResultadoEscrita(
            item_importacao_id=item.item_importacao_id, manifesto_item_id=resultado.manifesto_item_id,
            situacao=item.situacao, documento_id=item.documento_id,
            external_record_id=item.external_record_id, processado=True,
            motivo='situacao terminal -- nao reprocessado (idempotente)',
        )

    item = dataclasses.replace(
        item, situacao=SituacaoItemExecucao.EM_PROCESSAMENTO,
        tentativas=item.tentativas + 1, atualizado_em=agora,
    )
    _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)

    # ── 2. Documento físico por hash (reaproveita modulo01/repositorio.py) ─
    validacao = dominio.validar_pdf_bytes(pdf_bytes)
    if not validacao.valido:
        item = dataclasses.replace(
            item, situacao=SituacaoItemExecucao.FAILED_RETRYABLE,
            ultimo_erro_sanitizado=f'pdf_invalido_no_escritor:{validacao.motivo.value}',
            atualizado_em=relogio(),
        )
        _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
        return _resultado_de(item, resultado, processado=True)

    def _fabricar_documento() -> Documento:
        # status=REGISTRADO diretamente (não RECEBIDO -> transicionar) --
        # diferente de ServicoEntradaDocumental (Fase 1), este conteúdo já
        # chegou aqui validado E com entidade resolvida pelo dry-run
        # (classificar_item já exigiu EXACT+pronto_para_gravacao antes de
        # `escrever_item` ser chamado) -- não há um estágio "recebido, mas
        # ainda não registrado" a representar. Construção direta, nunca
        # via `transicionar_status` (que rejeitaria mudar o status de uma
        # instância já existente, não construir uma nova).
        return Documento(
            documento_id=gerador_documento_id(),
            arquivo_original=f'pendente-armazenamento://{validacao.hash_sha256}',
            nome_original=nome_arquivo,
            mime_type='application/pdf',
            tamanho=validacao.tamanho_bytes,
            hash_sha256=validacao.hash_sha256,
            origem='importacao_lote',
            recebido_em=agora,
            lote_id=lote_id,
            status=StatusDocumento.REGISTRADO,
            correlation_id=gerar_correlation_id(),
            criado_em=agora,
            atualizado_em=agora,
        )

    documento, _documento_criado_agora = repositorio_documentos.salvar_se_ausente_por_hash(
        validacao.hash_sha256, _fabricar_documento)

    item = dataclasses.replace(item, documento_id=documento.documento_id, atualizado_em=relogio())
    _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)

    # ── 3. Identidade lógica / versionamento (nunca supersede sozinho) ─────
    versionamento_existente = repositorio_versionamento.buscar_por_documento_id(documento.documento_id)
    if versionamento_existente is None:
        documento_logico_id = dominio_versionamento.calcular_documento_logico_id(
            resultado.tipo_documental, config.mes_cont_id, resultado.entidade_resolvida)
        versoes_existentes = repositorio_versionamento.listar_por_documento_logico_id(documento_logico_id)

        hash_por_documento_id = {}
        for v in versoes_existentes:
            doc_v = repositorio_documentos.buscar_por_id(v.documento_id)
            if doc_v is not None:
                hash_por_documento_id[v.documento_id] = doc_v.hash_sha256

        decisao = dominio_versionamento.verificar_nova_versao(
            versoes_existentes, documento.hash_sha256, hash_por_documento_id)

        if decisao.resultado == ResultadoVerificacaoVersao.CONFLITO_HASH_DIFERENTE:
            item = dataclasses.replace(
                item, situacao=SituacaoItemExecucao.BLOQUEADO_CONFLITO_VERSAO,
                ultimo_erro_sanitizado='conflito_versao_documento_logico', atualizado_em=relogio(),
            )
            _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
            _registrar_evento_se_aplicavel(item, resultado, lote_id, repositorio_historico, relogio())
            return _resultado_de(item, resultado, processado=True)

        if decisao.resultado == ResultadoVerificacaoVersao.PRIMEIRA_VERSAO:
            repositorio_versionamento.salvar_se_ausente(VersionamentoLogico(
                documento_id=documento.documento_id,
                documento_logico_id=documento_logico_id,
                versao_documento=decisao.proxima_versao or 1,
                substitui_documento_id=None,
                criado_em=relogio(),
            ))
        # MESMO_CONTEUDO_JA_REGISTRADO: nada a fazer -- mesmo hash já teria
        # o mesmo documento_id e cairia no `versionamento_existente is not
        # None` acima; mantido aqui só como caminho defensivo, nunca escrito.

    # ── 4. Airtable create (pulado se já existe external_record_id) ────────
    folha_mensal = formatar_folha_mensal(config.ano, config.mes)
    data_str = f'{config.ano:04d}-{config.mes:02d}-01'

    if item.external_record_id is None:
        try:
            external_id = escritor_airtable.criar_registro(
                resultado.tipo_documental, resultado.entidade_resolvida, folha_mensal,
                data_str, config.mes_cont_id, nome_referencia=nome_referencia,
            )
        except Exception as exc:
            item = dataclasses.replace(
                item, situacao=SituacaoItemExecucao.FAILED_RETRYABLE,
                ultimo_erro_sanitizado=_sanitizar_erro(exc), atualizado_em=relogio(),
            )
            _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
            return _resultado_de(item, resultado, processado=True)

        # Persistido ANTES de qualquer upload -- crítico para compensação
        # (§10): precisamos saber que este external_id foi criado por ESTA
        # execução antes de arriscar deletar em caso de falha adiante.
        item = dataclasses.replace(
            item, external_record_id=external_id, external_criado_por_esta_execucao=True,
            atualizado_em=relogio(),
        )
        _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
    else:
        external_id = item.external_record_id

    # ── 5. Upload + confirmação por releitura (pulado se já confirmado) ────
    if not item.attachment_confirmado:
        # Uma tentativa anterior pode ter concluído o upload e caído antes
        # de persistir o checkpoint de confirmação. Releia primeiro para
        # que a retomada nunca acrescente o mesmo anexo uma segunda vez.
        try:
            ja_confirmado = escritor_airtable.confirmar_attachment(
                resultado.tipo_documental, external_id)
        except Exception:
            ja_confirmado = False

        if ja_confirmado:
            item = dataclasses.replace(
                item, situacao=SituacaoItemExecucao.SUCESSO,
                attachment_confirmado=True, atualizado_em=relogio())
            _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
            _registrar_evento_se_aplicavel(
                item, resultado, lote_id, repositorio_historico, relogio())
            return _resultado_de(item, resultado, processado=True)

        try:
            escritor_airtable.anexar_pdf(resultado.tipo_documental, external_id, pdf_bytes, nome_arquivo)
        except Exception as exc:
            item = _tratar_falha_upload(
                item, resultado, external_id, exc, escritor_airtable, relogio,
                lote_id, repositorio_itens, repositorio_eventos_item,
            )
            _registrar_evento_se_aplicavel(item, resultado, lote_id, repositorio_historico, relogio())
            return _resultado_de(item, resultado, processado=True)

        confirmado = escritor_airtable.confirmar_attachment(resultado.tipo_documental, external_id)
        if not confirmado:
            item = dataclasses.replace(
                item, situacao=SituacaoItemExecucao.FAILED_RETRYABLE,
                ultimo_erro_sanitizado='attachment_nao_confirmado_apos_releitura',
                atualizado_em=relogio(),
            )
            _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
            return _resultado_de(item, resultado, processado=True)

        item = dataclasses.replace(
            item, situacao=SituacaoItemExecucao.SUCESSO, attachment_confirmado=True, atualizado_em=relogio())
    else:
        item = dataclasses.replace(item, situacao=SituacaoItemExecucao.SUCESSO, atualizado_em=relogio())

    _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
    _registrar_evento_se_aplicavel(item, resultado, lote_id, repositorio_historico, relogio())
    return _resultado_de(item, resultado, processado=True)


def _tratar_falha_upload(
    item: ItemExecucao, resultado: ResultadoItem, external_id: str, exc: Exception,
    escritor_airtable: EscritorAirtable, relogio: Callable[[], datetime],
    lote_id: str, repositorio_itens: RepositorioItensExecucao,
    repositorio_eventos_item: RepositorioEventosItemExecucao,
) -> ItemExecucao:
    """§10 do macrocomando: upload falhou. Antes de decidir compensar,
    confere (por releitura) se o anexo não está lá de fato -- uma
    resposta perdida por timeout pode ter tido sucesso no servidor. Só
    compensa (delete condicional) quando: (a) o registro foi criado por
    ESTA execução, e (b) a releitura confirma que ainda não há anexo.
    Nunca deleta registro pré-existente nem por inferência."""
    try:
        ja_confirmado = escritor_airtable.confirmar_attachment(resultado.tipo_documental, external_id)
    except Exception:
        ja_confirmado = False  # releitura também falhou -- trata como não confirmado, conservador

    if ja_confirmado:
        item = dataclasses.replace(
            item, situacao=SituacaoItemExecucao.SUCESSO, attachment_confirmado=True, atualizado_em=relogio())
        _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
        return item

    seguro_compensar = item.external_criado_por_esta_execucao
    if seguro_compensar:
        deletado = escritor_airtable.deletar_registro_condicional(resultado.tipo_documental, external_id)
        nova_situacao = (
            SituacaoItemExecucao.FAILED_COMPENSATED if deletado
            else SituacaoItemExecucao.FAILED_ORPHANED
        )
    else:
        nova_situacao = SituacaoItemExecucao.FAILED_ORPHANED

    item = dataclasses.replace(
        item, situacao=nova_situacao, ultimo_erro_sanitizado=_sanitizar_erro(exc), atualizado_em=relogio())
    _persistir_item(item, lote_id, repositorio_itens, repositorio_eventos_item)
    return item


def _registrar_evento_se_aplicavel(
    item: ItemExecucao, resultado: ResultadoItem, lote_id: str,
    repositorio_historico: Optional[RepositorioHistorico], quando: datetime,
) -> None:
    """§13: evento de auditoria só quando documento_id existe e a situação
    é uma das auditadas (resultado final que interessa rastrear) --
    nunca em toda transição intermediária. `detalhes` nunca contém PII
    (só IDs e códigos sanitizados)."""
    if repositorio_historico is None or item.documento_id is None:
        return
    if item.situacao not in _SITUACOES_AUDITADAS:
        return
    repositorio_historico.registrar(EventoHistorico(
        documento_id=item.documento_id,
        evento='IMPORTACAO_LOTE_ITEM_ESCRITO',
        status_anterior=None,
        status_novo=None,
        timestamp=quando,
        correlation_id=lote_id,
        detalhes={
            'lote_id': lote_id,
            'item_importacao_id': item.item_importacao_id,
            'manifesto_item_id': resultado.manifesto_item_id,
            'tipo_documental': resultado.tipo_documental.value,
            'situacao': item.situacao.value,
            'external_record_id': item.external_record_id,
        },
    ))


def _resultado_de(item: ItemExecucao, resultado: ResultadoItem, processado: bool) -> ResultadoEscrita:
    return ResultadoEscrita(
        item_importacao_id=item.item_importacao_id,
        manifesto_item_id=resultado.manifesto_item_id,
        situacao=item.situacao,
        documento_id=item.documento_id,
        external_record_id=item.external_record_id,
        processado=processado,
        motivo=item.ultimo_erro_sanitizado,
    )
