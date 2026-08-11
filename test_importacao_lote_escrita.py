"""
Testes da camada de ESCRITA REAL da importação em lote (Fase de
persistência — ver escritor.py, dominio_versionamento.py,
repositorio_execucao.py). Nenhum destes testes acessa Postgres ou
Airtable reais — tudo roda contra repositórios em memória e um duplo de
teste (`_FakeEscritorAirtable`) que nunca faz rede.

100% dado sintético — nenhum CPF/nome real em nenhum lugar deste arquivo
(ver CLAUDE.md raiz §6, LGPD).

Cobre os cenários A-L (idempotência/retomada/compensação/concorrência) e
M-Y (versionamento, invariantes de banco, auditoria, migration/rollback)
do macrocomando "IMPLEMENTAÇÃO LOCAL INTEGRAL DA PERSISTÊNCIA E ESCRITA
REAL".
"""

from __future__ import annotations

import dataclasses
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.documental.importacao_lote import dominio_versionamento
from magnata_os.documental.importacao_lote.adapters import airtable_escrita
from magnata_os.documental.importacao_lote.contratos import (
    ClassificacaoCorrespondencia,
    ConfiguracaoExecucao,
    MotivoSanitizado,
    ResultadoItem,
    TipoDocumental,
)
from magnata_os.documental.importacao_lote.contratos_execucao import (
    EventoItemExecucao,
    ItemExecucao,
    ResultadoEscrita,
    SituacaoItemExecucao,
    VersionamentoLogico,
)
from magnata_os.documental.importacao_lote.dominio_versionamento import (
    DecisaoVersionamento,
    GrafoVersionamentoInconsistente,
    ResultadoVerificacaoVersao,
    calcular_documento_logico_id,
    construir_proxima_versao,
    determinar_vigente,
    verificar_nova_versao,
)
from magnata_os.documental.importacao_lote.escritor import escrever_item
from magnata_os.documental.importacao_lote.repositorio_execucao import (
    RepositorioEventosItemExecucaoEmMemoria,
    RepositorioItensExecucaoEmMemoria,
    RepositorioVersionamentoLogicoEmMemoria,
)
from magnata_os.documental.modulo01.adapters import conexao as conexao_mod
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)

_MIGRATIONS_DIR = Path(__file__).parent / 'magnata_os' / 'documental' / 'modulo01' / 'migrations'


# ============================================================================
# Fixtures / duplos de teste
# ============================================================================

def _pdf_valido(sufixo: bytes = b'') -> bytes:
    return b'%PDF-1.4\n' + (b'x' * 100) + sufixo


class _FakeEscritorAirtable:
    """Duplo de teste — nunca faz rede. Simula create/upload/releitura/
    delete com flags de injeção de falha, para exercer cada cenário de
    retomada/compensação sem depender de Airtable real."""

    def __init__(self):
        self.registros: dict[str, dict] = {}
        self._contador = 0
        self.chamadas_criar = 0
        self.chamadas_anexar = 0
        self.chamadas_releitura = 0
        self.chamadas_delete = 0
        self.falhar_criar = False
        self.falhar_anexar = False
        self.anexar_excecao_mas_sucesso_no_servidor = False
        self.releitura_override = None  # None = usa o estado real do registro
        self.falhar_delete = False

    def pre_registrar(self, record_id: str, tipo: TipoDocumental, anexo: bool = False) -> None:
        """Simula um registro que já existia (criado por esta execução em
        uma tentativa anterior, ou por outra execução) sem passar por
        `criar_registro` — usado para testar retomada/cenário U."""
        self.registros[record_id] = {'tipo': tipo, 'anexo': anexo}

    def criar_registro(self, tipo, entidade_id, folha_mensal, data_str, mes_cont_id, nome_referencia=''):
        self.chamadas_criar += 1
        if self.falhar_criar:
            raise RuntimeError('falha simulada de create')
        self._contador += 1
        record_id = f'rec{self._contador}'
        self.registros[record_id] = {'tipo': tipo, 'anexo': False}
        return record_id

    def anexar_pdf(self, tipo, record_id, pdf_bytes, filename):
        self.chamadas_anexar += 1
        if self.falhar_anexar:
            if self.anexar_excecao_mas_sucesso_no_servidor:
                self.registros[record_id]['anexo'] = True
            raise RuntimeError('falha simulada de upload')
        self.registros[record_id]['anexo'] = True
        return {}

    def confirmar_attachment(self, tipo, record_id):
        self.chamadas_releitura += 1
        if self.releitura_override is not None:
            return self.releitura_override
        return self.registros.get(record_id, {}).get('anexo', False)

    def deletar_registro_condicional(self, tipo, record_id):
        self.chamadas_delete += 1
        if self.falhar_delete:
            return False
        existia = record_id in self.registros
        self.registros.pop(record_id, None)
        return existia


class _Ambiente:
    """Agrupa os repositórios em memória + duplo de Airtable — reduz
    boilerplate nos testes de escritor.py."""

    def __init__(self):
        self.documentos = RepositorioDocumentosEmMemoria()
        self.historico = RepositorioHistoricoEmMemoria()
        self.itens = RepositorioItensExecucaoEmMemoria()
        self.eventos_item = RepositorioEventosItemExecucaoEmMemoria()
        self.versionamento = RepositorioVersionamentoLogicoEmMemoria()
        self.airtable = _FakeEscritorAirtable()

    def escrever(self, resultado, pdf_bytes, config, lote_id, nome_arquivo='arq.pdf', nome_referencia='ref'):
        return escrever_item(
            resultado, pdf_bytes, nome_arquivo, nome_referencia, config, lote_id,
            self.documentos, self.historico, self.itens, self.eventos_item,
            self.versionamento, self.airtable,
        )


def _resultado_exact(
    manifesto_item_id='holerite:1', entidade_id='funXYZ', tipo=TipoDocumental.HOLERITE,
) -> ResultadoItem:
    return ResultadoItem(
        manifesto_item_id=manifesto_item_id,
        tipo_documental=tipo,
        classificacao=ClassificacaoCorrespondencia.EXACT,
        pronto_para_gravacao=True,
        entidade_resolvida=entidade_id,
        identidade_documental='a' * 64,
        identidade_documental_truncada='a' * 12,
        motivo=MotivoSanitizado.OK,
        criterio_usado='cpf_exato',
    )


def _resultado_nao_exact() -> ResultadoItem:
    return ResultadoItem(
        manifesto_item_id='holerite:99',
        tipo_documental=TipoDocumental.HOLERITE,
        classificacao=ClassificacaoCorrespondencia.NOT_FOUND,
        pronto_para_gravacao=False,
        entidade_resolvida=None,
        identidade_documental=None,
        identidade_documental_truncada=None,
        motivo=MotivoSanitizado.COLABORADOR_NAO_ENCONTRADO,
    )


def _config(mes_cont_id='recMesCont1', ano=2026, mes=7, message_id='msg-abc', pkg='pkg-hash-xyz'):
    return ConfiguracaoExecucao(
        mes_cont_id=mes_cont_id, ano=ano, mes=mes,
        message_id_estavel=message_id, package_sha256=pkg,
    )


def test_confirmar_attachment_em_registro_individual_nao_envia_fields(monkeypatch):
    chamadas = []

    class _Resposta:
        ok = True
        status_code = 200
        text = ''

        def json(self):
            return {'fields': {airtable_escrita.F_HOL_PDF: [{'id': 'att-sintetico'}]}}

    def _get(url, headers, params, timeout):
        chamadas.append(params)
        return _Resposta()

    monkeypatch.setattr(airtable_escrita.requests, 'get', _get)
    adapter = airtable_escrita.EscritorAirtable('token-sintetico')

    assert adapter.confirmar_attachment(TipoDocumental.HOLERITE, 'rec-sintetico') is True
    assert chamadas == [{'returnFieldsByFieldId': 'true'}]


# ============================================================================
# 0. Item não-EXACT nunca é processado automaticamente
# ============================================================================

def test_item_nao_exact_nunca_e_processado_automaticamente():
    amb = _Ambiente()
    resultado = amb.escrever(_resultado_nao_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.processado is False
    assert resultado.situacao == SituacaoItemExecucao.IGNORADO_NAO_EXACT
    assert amb.airtable.chamadas_criar == 0
    assert amb.airtable.chamadas_anexar == 0


# ============================================================================
# A. Mesma execução retomada (crash mid-flight -- item EM_PROCESSAMENTO)
# ============================================================================

def test_A_execucao_retomada_apos_crash_em_processamento_completa():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()

    # Simula um crash: item já existe em EM_PROCESSAMENTO, sem documento
    # nem external_record_id -- exatamente o estado que uma queda no meio
    # do fluxo deixaria para trás.
    agora = datetime.now(timezone.utc)
    amb.itens.criar_se_ausente('lote-1', resultado_item.manifesto_item_id, lambda: ItemExecucao(
        item_importacao_id='item-1', lote_id='lote-1', manifesto_item_id=resultado_item.manifesto_item_id,
        tipo_documental=TipoDocumental.HOLERITE, documento_id=None, identidade_ingestao='ident-1',
        situacao=SituacaoItemExecucao.EM_PROCESSAMENTO, tentativas=1, external_record_id=None,
        external_criado_por_esta_execucao=False, attachment_confirmado=False,
        ultimo_erro_sanitizado=None, criado_em=agora, atualizado_em=agora,
    ))

    resultado = amb.escrever(resultado_item, _pdf_valido(), config, 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO
    assert amb.airtable.chamadas_criar == 1
    assert amb.airtable.chamadas_anexar == 1


# ============================================================================
# B / S. Retry após sucesso (ou após external_id já existente) nunca
# cria um segundo registro no Airtable -- idempotência real.
# ============================================================================

def test_B_S_retry_apos_sucesso_e_idempotente_nunca_recria_no_airtable():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()

    primeiro = amb.escrever(resultado_item, _pdf_valido(), config, 'lote-1')
    assert primeiro.situacao == SituacaoItemExecucao.SUCESSO
    assert amb.airtable.chamadas_criar == 1

    segundo = amb.escrever(resultado_item, _pdf_valido(), config, 'lote-1')
    assert segundo.situacao == SituacaoItemExecucao.SUCESSO
    assert segundo.item_importacao_id == primeiro.item_importacao_id
    # nenhuma chamada nova -- situação terminal, nunca reprocessada.
    assert amb.airtable.chamadas_criar == 1
    assert amb.airtable.chamadas_anexar == 1


# ============================================================================
# C. Mesmo pacote reenviado -- idempotência de EXECUÇÃO garantida por
# índice parcial em lotes_documentais (migration 0009). Teste estrutural
# -- confirma que o índice existe com a forma esperada.
# ============================================================================

def test_C_migration_declara_indice_de_idempotencia_de_execucao():
    sql = (_MIGRATIONS_DIR / '0009_itens_importacao_lote.sql').read_text()
    assert 'idx_lotes_documentais_execucao_unica' in sql
    assert "message_id_estavel" in sql and "package_sha256" in sql
    assert 'UNIQUE INDEX' in sql
    assert "WHERE origem = 'importacao_lote'" in sql


# ============================================================================
# D / W. Mesmo conteúdo (mesmo hash) em LOTES diferentes reaproveita o
# mesmo `documento_id` -- nunca duplica o documento físico nem a versão.
# ============================================================================

def test_D_W_lote_diferente_referencia_mesmo_documento_fisico():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    r1 = amb.escrever(resultado_item, pdf, config, 'lote-A')
    r2 = amb.escrever(resultado_item, pdf, config, 'lote-B')

    assert r1.documento_id == r2.documento_id
    assert len(amb.documentos.listar_todos()) == 1
    # Só uma versão lógica para o documento_logico_id em questão.
    doc_logico = calcular_documento_logico_id(
        TipoDocumental.HOLERITE, config.mes_cont_id, resultado_item.entidade_resolvida)
    assert len(amb.versionamento.listar_por_documento_logico_id(doc_logico)) == 1
    # Dois itens de execução distintos (lotes diferentes) -- nunca um só.
    assert r1.item_importacao_id != r2.item_importacao_id
    # Dois registros no Airtable (um por lote/execução) -- cada lote é uma
    # ocorrência de distribuição própria, mesmo compartilhando o conteúdo.
    assert amb.airtable.chamadas_criar == 2


# ============================================================================
# E. Conteúdo já existente (documento registrado por outro fluxo antes
# do escritor rodar) nunca é duplicado.
# ============================================================================

def test_E_documento_ja_existente_nao_e_duplicado():
    from magnata_os.documental.modulo01 import dominio as dominio_modulo01

    amb = _Ambiente()
    pdf = _pdf_valido()
    hash_sha256 = __import__('hashlib').sha256(pdf).hexdigest()
    agora = datetime.now(timezone.utc)
    documento_preexistente = dominio_modulo01.Documento(
        documento_id='doc-preexistente', arquivo_original='pendente-armazenamento://x',
        nome_original='antigo.pdf', mime_type='application/pdf', tamanho=len(pdf),
        hash_sha256=hash_sha256, origem='outro_fluxo', recebido_em=agora, lote_id=None,
        status=dominio_modulo01.StatusDocumento.REGISTRADO, correlation_id='corr-x',
        criado_em=agora, atualizado_em=agora,
    )
    amb.documentos.salvar(documento_preexistente)

    resultado = amb.escrever(_resultado_exact(), pdf, _config(), 'lote-1')
    assert resultado.documento_id == 'doc-preexistente'
    assert len(amb.documentos.listar_todos()) == 1


# ============================================================================
# F. Crash antes do documento -- PDF inválido detectado dentro do
# próprio escritor (defesa em profundidade, mesmo já validado a montante).
# ============================================================================

def test_F_pdf_invalido_no_escritor_nunca_cria_documento():
    amb = _Ambiente()
    resultado = amb.escrever(_resultado_exact(), b'', _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_RETRYABLE
    assert resultado.documento_id is None
    assert len(amb.documentos.listar_todos()) == 0
    assert amb.airtable.chamadas_criar == 0


# ============================================================================
# G. Crash após documento (Airtable create falha) -- retomada reaproveita
# o MESMO documento, nunca cria um segundo.
# ============================================================================

def test_G_crash_apos_documento_retomada_reaproveita_documento():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.airtable.falhar_criar = True
    primeiro = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert primeiro.situacao == SituacaoItemExecucao.FAILED_RETRYABLE
    assert primeiro.documento_id is not None
    assert len(amb.documentos.listar_todos()) == 1

    amb.airtable.falhar_criar = False
    segundo = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert segundo.situacao == SituacaoItemExecucao.SUCESSO
    assert segundo.documento_id == primeiro.documento_id
    assert len(amb.documentos.listar_todos()) == 1


# ============================================================================
# H. Crash após Airtable create (registro já existe, upload nunca
# tentado) -- retomada pula direto para o upload, nunca recria o registro.
# ============================================================================

def test_H_crash_apos_create_pula_direto_para_upload():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.airtable.pre_registrar('rec-preexistente', TipoDocumental.HOLERITE, anexo=False)
    agora = datetime.now(timezone.utc)
    amb.itens.criar_se_ausente('lote-1', resultado_item.manifesto_item_id, lambda: ItemExecucao(
        item_importacao_id='item-1', lote_id='lote-1', manifesto_item_id=resultado_item.manifesto_item_id,
        tipo_documental=TipoDocumental.HOLERITE, documento_id=None, identidade_ingestao='ident-1',
        situacao=SituacaoItemExecucao.EM_PROCESSAMENTO, tentativas=1,
        external_record_id='rec-preexistente', external_criado_por_esta_execucao=True,
        attachment_confirmado=False, ultimo_erro_sanitizado=None, criado_em=agora, atualizado_em=agora,
    ))

    resultado = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO
    assert amb.airtable.chamadas_criar == 0  # nunca recriou
    assert amb.airtable.chamadas_anexar == 1


def test_H_retomada_confirma_upload_existente_sem_duplicar_anexo():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.airtable.pre_registrar('rec-preexistente', TipoDocumental.HOLERITE, anexo=True)
    agora = datetime.now(timezone.utc)
    amb.itens.criar_se_ausente('lote-1', resultado_item.manifesto_item_id, lambda: ItemExecucao(
        item_importacao_id='item-1', lote_id='lote-1', manifesto_item_id=resultado_item.manifesto_item_id,
        tipo_documental=TipoDocumental.HOLERITE, documento_id=None, identidade_ingestao='ident-1',
        situacao=SituacaoItemExecucao.EM_PROCESSAMENTO, tentativas=1,
        external_record_id='rec-preexistente', external_criado_por_esta_execucao=True,
        attachment_confirmado=False, ultimo_erro_sanitizado=None, criado_em=agora, atualizado_em=agora,
    ))

    resultado = amb.escrever(resultado_item, pdf, config, 'lote-1')
    item = amb.itens.buscar_por_lote_e_manifesto('lote-1', resultado_item.manifesto_item_id)
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO
    assert item.attachment_confirmado is True
    assert amb.airtable.chamadas_criar == 0
    assert amb.airtable.chamadas_anexar == 0


# ============================================================================
# I / V. Crash durante upload -- compensação: criado por esta execução +
# releitura confirma ausência -> delete bem-sucedido = FAILED_COMPENSATED;
# delete falho = FAILED_ORPHANED (cenário V).
# ============================================================================

def test_I_falha_upload_com_compensacao_bem_sucedida():
    amb = _Ambiente()
    amb.airtable.falhar_anexar = True
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_COMPENSATED
    assert amb.airtable.chamadas_delete == 1


def test_V_falha_de_compensacao_vira_failed_orphaned():
    amb = _Ambiente()
    amb.airtable.falhar_anexar = True
    amb.airtable.falhar_delete = True
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_ORPHANED
    assert amb.airtable.chamadas_delete == 1


# ============================================================================
# J / T. Upload com resposta perdida: exceção no upload, mas a releitura
# confirma que o anexo está lá -> SUCESSO, nunca deleta. E o inverso:
# upload "OK" sem exceção mas releitura nega -> nunca SUCESSO por confiar
# só no 2xx (T).
# ============================================================================

def test_J_upload_com_resposta_perdida_mas_sucesso_no_servidor():
    amb = _Ambiente()
    amb.airtable.falhar_anexar = True
    amb.airtable.anexar_excecao_mas_sucesso_no_servidor = True
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO
    assert amb.airtable.chamadas_delete == 0

    # Achado do Ultrareview desta rodada: o resultado RETORNADO dizia
    # SUCESSO mas o item PERSISTIDO ficava preso em EM_PROCESSAMENTO --
    # uma nova chamada reprocessaria (novo upload) violando idempotência.
    # Corrigido em _tratar_falha_upload (persistir antes de retornar no
    # ramo "já confirmado"). Este teste trava a correção.
    item_persistido = amb.itens.buscar_por_lote_e_manifesto('lote-1', resultado.manifesto_item_id)
    assert item_persistido.situacao == SituacaoItemExecucao.SUCESSO
    assert item_persistido.attachment_confirmado is True

    amb.airtable.falhar_anexar = False
    resultado_retry = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado_retry.situacao == SituacaoItemExecucao.SUCESSO
    assert amb.airtable.chamadas_anexar == 1  # nunca fez um segundo upload


def test_T_attachment_confirmado_so_apos_releitura_mesmo_com_upload_2xx():
    amb = _Ambiente()
    amb.airtable.releitura_override = False  # upload "sucesso", mas releitura nega
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_RETRYABLE
    assert amb.airtable.chamadas_releitura >= 1


# ============================================================================
# K. Retry geral após FAILED_RETRYABLE completa com sucesso.
# ============================================================================

def test_K_retry_apos_failed_retryable_completa():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.airtable.releitura_override = False
    primeiro = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert primeiro.situacao == SituacaoItemExecucao.FAILED_RETRYABLE

    amb.airtable.releitura_override = None
    segundo = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert segundo.situacao == SituacaoItemExecucao.SUCESSO


# ============================================================================
# L. Concorrência -- criar_se_ausente sob chamadas simultâneas para o
# MESMO (lote_id, manifesto_item_id) cria exatamente um item.
# ============================================================================

def test_L_concorrencia_criar_se_ausente_cria_exatamente_um_item():
    repo = RepositorioItensExecucaoEmMemoria()
    agora = datetime.now(timezone.utc)
    resultados = []
    barreira = threading.Barrier(10)

    def _tentar(indice):
        barreira.wait()
        item, criado = repo.criar_se_ausente('lote-1', 'holerite:1', lambda: ItemExecucao(
            item_importacao_id=f'item-{indice}', lote_id='lote-1', manifesto_item_id='holerite:1',
            tipo_documental=TipoDocumental.HOLERITE, documento_id=None, identidade_ingestao='ident',
            situacao=SituacaoItemExecucao.PENDENTE, tentativas=0, external_record_id=None,
            external_criado_por_esta_execucao=False, attachment_confirmado=False,
            ultimo_erro_sanitizado=None, criado_em=agora, atualizado_em=agora,
        ))
        resultados.append(criado)

    threads = [threading.Thread(target=_tentar, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(resultados) == 1  # exatamente uma criação venceu a corrida
    assert len(repo.listar_por_lote('lote-1')) == 1


# ============================================================================
# M. Uma versão anterior nunca pode ter dois sucessores confirmados --
# invariante de banco (migration 0009). Teste estrutural + funcional
# contra um duplo de DB-API que simula a constraint.
# ============================================================================

def test_M_migration_declara_unique_parcial_em_substitui_documento_id():
    sql = (_MIGRATIONS_DIR / '0009_itens_importacao_lote.sql').read_text()
    assert 'idx_versionamento_logico_substitui_unico' in sql
    assert 'UNIQUE INDEX' in sql
    assert 'substitui_documento_id' in sql
    assert 'WHERE substitui_documento_id IS NOT NULL' in sql


class _IntegrityErrorFake(Exception):
    pass


class _CursorVersionamentoFalso:
    def __init__(self, banco):
        self._banco = banco
        self._resultado = []

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, sql, params=()):
        sql_norm = ' '.join(sql.split())
        if 'INSERT INTO documentos_versionamento_logico' in sql_norm:
            documento_id, _logico, _versao, substitui, _criado = params
            if documento_id in self._banco:
                self._resultado = []
                return
            if substitui is not None and any(
                v[3] == substitui for v in self._banco.values()
            ):
                raise _IntegrityErrorFake(
                    'duplicate key value violates unique constraint '
                    '"idx_versionamento_logico_substitui_unico"'
                )
            self._banco[documento_id] = tuple(params)
            self._resultado = [(documento_id,)]
        elif 'SELECT' in sql_norm and 'WHERE documento_id' in sql_norm:
            linha = self._banco.get(params[0])
            self._resultado = [linha] if linha else []
        else:
            raise AssertionError(f'SQL nao reconhecido: {sql_norm}')

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


class _ConexaoVersionamentoFalsa:
    def __init__(self):
        self._banco = {}
        self.rollbacks = 0

    def cursor(self):
        return _CursorVersionamentoFalso(self._banco)

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


# torna IntegrityError (nome da classe) visível para _e_violacao_de_integridade
_IntegrityErrorFake.__name__ = 'IntegrityError'


def test_M_segundo_sucessor_confirmado_para_a_mesma_versao_nunca_e_silencioso():
    from magnata_os.documental.importacao_lote.adapters.postgres_execucao import (
        RepositorioVersionamentoLogicoPostgres,
    )

    conexao = _ConexaoVersionamentoFalsa()
    repo = RepositorioVersionamentoLogicoPostgres(conexao)
    agora = datetime.now(timezone.utc)

    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    repo.salvar_se_ausente(v1)

    v2 = VersionamentoLogico('doc-2', 'logico-A', 2, 'doc-1', agora)
    repo.salvar_se_ausente(v2)  # primeiro sucessor -- ok

    v3_conflitante = VersionamentoLogico('doc-3', 'logico-A', 2, 'doc-1', agora)
    # Segundo sucessor para o MESMO doc-1 -- a constraint do banco recusa
    # o INSERT; como doc-3 nunca foi persistido, buscar_por_documento_id
    # não encontra nada -- a falha nunca é mascarada como "já existente".
    with pytest.raises(RuntimeError):
        repo.salvar_se_ausente(v3_conflitante)


# ============================================================================
# N. Lineage nunca aponta para documento fora da estrutura de
# versionamento -- FK de auto-referência na própria tabela, nunca para
# `documentos` diretamente.
# ============================================================================

def test_N_substitui_documento_id_referencia_a_propria_tabela_nao_documentos():
    sql = (_MIGRATIONS_DIR / '0009_itens_importacao_lote.sql').read_text()
    m = re.search(r'substitui_documento_id\s+TEXT\s+REFERENCES\s+(\w+)', sql)
    assert m is not None, 'coluna substitui_documento_id não encontrada com REFERENCES'
    assert m.group(1) == 'documentos_versionamento_logico', (
        'substitui_documento_id deve referenciar documentos_versionamento_logico '
        '(auto-referência), nunca documentos diretamente'
    )


# ============================================================================
# O. documento_logico_id é estável (determinístico) para as mesmas
# entradas, e muda quando qualquer componente de identidade muda.
# ============================================================================

def test_O_documento_logico_id_estavel_e_sensivel_aos_componentes():
    a = calcular_documento_logico_id(TipoDocumental.HOLERITE, 'mesA', 'func1')
    b = calcular_documento_logico_id(TipoDocumental.HOLERITE, 'mesA', 'func1')
    assert a == b  # determinístico

    diferente_mes = calcular_documento_logico_id(TipoDocumental.HOLERITE, 'mesB', 'func1')
    diferente_entidade = calcular_documento_logico_id(TipoDocumental.HOLERITE, 'mesA', 'func2')
    diferente_tipo = calcular_documento_logico_id(TipoDocumental.EXTRATO_CLIENTE, 'mesA', 'func1')
    assert len({a, diferente_mes, diferente_entidade, diferente_tipo}) == 4


# ============================================================================
# P. Hash diferente para o mesmo documento lógico NUNCA supersede
# automaticamente -- é sempre CONFLITO, ambos preservados.
# ============================================================================

def test_P_hash_diferente_nunca_supersede_automaticamente():
    agora = datetime.now(timezone.utc)
    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    decisao = verificar_nova_versao([v1], 'hash-novo-diferente', {'doc-1': 'hash-original'})
    assert decisao.resultado == ResultadoVerificacaoVersao.CONFLITO_HASH_DIFERENTE
    assert decisao.proxima_versao is None  # nunca oferece uma "próxima versão" em conflito


def test_P_mesmo_hash_e_reconhecido_sem_criar_nova_versao():
    agora = datetime.now(timezone.utc)
    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    decisao = verificar_nova_versao([v1], 'hash-original', {'doc-1': 'hash-original'})
    assert decisao.resultado == ResultadoVerificacaoVersao.MESMO_CONTEUDO_JA_REGISTRADO


# ============================================================================
# Q / R. Supersessão explícita cria uma cadeia linear correta, e o
# vigente é sempre calculado pela cadeia (grafo), não por timestamp nem
# pela ordem da lista.
# ============================================================================

def test_Q_construir_proxima_versao_cria_cadeia_linear():
    agora = datetime.now(timezone.utc)
    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    v2 = construir_proxima_versao('logico-A', 'doc-2', v1, agora)
    assert v2.versao_documento == 2
    assert v2.substitui_documento_id == 'doc-1'
    assert v2.documento_logico_id == 'logico-A'


def test_R_vigente_calculado_pela_cadeia_independente_da_ordem_da_lista():
    agora = datetime.now(timezone.utc)
    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    v2 = construir_proxima_versao('logico-A', 'doc-2', v1, agora)
    v3 = construir_proxima_versao('logico-A', 'doc-3', v2, agora)

    assert determinar_vigente([v1, v2, v3]) == v3
    assert determinar_vigente([v3, v1, v2]) == v3  # ordem embaralhada -- mesmo resultado
    assert determinar_vigente([v2, v3, v1]) == v3


def test_R_vigente_none_quando_lista_vazia():
    assert determinar_vigente([]) is None


def test_R_grafo_inconsistente_multiplas_pontas_nunca_e_decidido_por_aproximacao():
    agora = datetime.now(timezone.utc)
    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    v2_solta = VersionamentoLogico('doc-2', 'logico-A', 1, None, agora)  # duas raízes soltas
    with pytest.raises(GrafoVersionamentoInconsistente):
        determinar_vigente([v1, v2_solta])


def test_R_grafo_com_documento_logico_id_misturado_e_rejeitado():
    agora = datetime.now(timezone.utc)
    v1 = VersionamentoLogico('doc-1', 'logico-A', 1, None, agora)
    v2 = VersionamentoLogico('doc-2', 'logico-B', 1, None, agora)
    with pytest.raises(GrafoVersionamentoInconsistente):
        determinar_vigente([v1, v2])


# ============================================================================
# U. Delete condicional nunca remove um registro pré-existente (criado
# por OUTRA execução) -- compensação nunca é sequer tentada nesse caso.
# ============================================================================

def test_U_delete_condicional_nunca_remove_registro_preexistente():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    # Registro pré-existente, criado por OUTRA execução --
    # external_criado_por_esta_execucao=False.
    amb.airtable.pre_registrar('rec-de-outra-execucao', TipoDocumental.HOLERITE, anexo=False)
    agora = datetime.now(timezone.utc)
    amb.itens.criar_se_ausente('lote-1', resultado_item.manifesto_item_id, lambda: ItemExecucao(
        item_importacao_id='item-1', lote_id='lote-1', manifesto_item_id=resultado_item.manifesto_item_id,
        tipo_documental=TipoDocumental.HOLERITE, documento_id=None, identidade_ingestao='ident-1',
        situacao=SituacaoItemExecucao.EM_PROCESSAMENTO, tentativas=1,
        external_record_id='rec-de-outra-execucao', external_criado_por_esta_execucao=False,
        attachment_confirmado=False, ultimo_erro_sanitizado=None, criado_em=agora, atualizado_em=agora,
    ))
    amb.airtable.falhar_anexar = True

    resultado = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_ORPHANED
    assert amb.airtable.chamadas_delete == 0  # nunca tentou apagar
    assert 'rec-de-outra-execucao' in amb.airtable.registros  # continua lá


# ============================================================================
# X. Evento de auditoria (e o próprio ItemExecucao) nunca contém PII.
# ============================================================================

def test_X_evento_de_auditoria_nunca_contem_pii():
    amb = _Ambiente()
    nome_pii_simulado = 'FULANO DE TAL SINTETICO'
    resultado = amb.escrever(
        _resultado_exact(), _pdf_valido(), _config(), 'lote-1', nome_referencia=nome_pii_simulado)
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO

    eventos = amb.historico.listar_todos()
    assert len(eventos) == 1
    detalhes_texto = repr(dict(eventos[0].detalhes))
    assert nome_pii_simulado not in detalhes_texto

    # ItemExecucao estruturalmente não tem nenhum campo que possa carregar
    # nome/CPF -- nem passou perto de ser persistido ali.
    campos_item = {f.name for f in dataclasses.fields(ItemExecucao)}
    assert 'nome_referencia' not in campos_item
    assert 'cpf' not in campos_item
    assert 'nome' not in campos_item


def test_X_conflito_de_versao_tambem_gera_evento_sem_pii():
    amb = _Ambiente()
    config = _config()
    resultado_item = _resultado_exact(entidade_id='func-conflito')

    amb.escrever(resultado_item, _pdf_valido(b'-v1'), config, 'lote-1')
    resultado2 = amb.escrever(
        _resultado_exact(manifesto_item_id='holerite:2', entidade_id='func-conflito'),
        _pdf_valido(b'-v2-conteudo-diferente'), config, 'lote-2',
    )
    assert resultado2.situacao == SituacaoItemExecucao.BLOQUEADO_CONFLITO_VERSAO
    eventos = amb.historico.listar_por_documento(resultado2.documento_id)
    assert len(eventos) == 1
    assert eventos[0].detalhes['situacao'] == 'BLOQUEADO_CONFLITO_VERSAO'


# ============================================================================
# Conflito de versionamento (hash diferente, mesmo documento lógico)
# nunca chega ao Airtable e preserva ambos os documentos.
# ============================================================================

def test_conflito_de_hash_para_mesmo_documento_logico_nunca_grava_no_airtable():
    amb = _Ambiente()
    config = _config()
    resultado_item = _resultado_exact(entidade_id='func-conflito-2')

    r1 = amb.escrever(resultado_item, _pdf_valido(b'-conteudo-1'), config, 'lote-1')
    assert r1.situacao == SituacaoItemExecucao.SUCESSO

    resultado_item_2 = _resultado_exact(manifesto_item_id='holerite:2', entidade_id='func-conflito-2')
    r2 = amb.escrever(resultado_item_2, _pdf_valido(b'-conteudo-2-diferente'), config, 'lote-1')

    assert r2.situacao == SituacaoItemExecucao.BLOQUEADO_CONFLITO_VERSAO
    assert r2.documento_id != r1.documento_id  # ambos preservados, nenhum sobrescrito
    assert len(amb.documentos.listar_todos()) == 2
    assert amb.airtable.chamadas_criar == 1  # só o primeiro (sem conflito) chegou a gravar


# ============================================================================
# Y. Migration e rollback são estruturalmente coerentes -- toda tabela/
# índice criado em 0009 tem um DROP correspondente no rollback, e o
# rollback nunca toca tabelas de fases anteriores (documentos,
# lotes_documentais, eventos_documentais).
# ============================================================================

def test_Y_rollback_desfaz_tudo_que_a_migration_0009_cria():
    forward = (_MIGRATIONS_DIR / '0009_itens_importacao_lote.sql').read_text()
    rollback = (_MIGRATIONS_DIR / '0009_itens_importacao_lote_rollback.sql').read_text()

    tabelas_criadas = set(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', forward))
    indices_criados = set(re.findall(r'CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)', forward))

    for tabela in tabelas_criadas:
        assert f'DROP TABLE IF EXISTS {tabela}' in rollback, f'{tabela} sem DROP no rollback'
    for indice in indices_criados:
        assert f'DROP INDEX IF EXISTS {indice}' in rollback, f'{indice} sem DROP no rollback'

    assert tabelas_criadas == {
        'documentos_versionamento_logico', 'itens_importacao_lote', 'eventos_itens_importacao_lote',
    }


def test_Y_rollback_nunca_toca_tabelas_de_fases_anteriores():
    rollback = (_MIGRATIONS_DIR / '0009_itens_importacao_lote_rollback.sql').read_text()
    for tabela_protegida in ('documentos', 'lotes_documentais', 'eventos_documentais'):
        assert re.search(rf'DROP TABLE IF EXISTS {tabela_protegida}\b', rollback) is None
        assert re.search(rf'ALTER TABLE {tabela_protegida}\b', rollback) is None


# ============================================================================
# CORREÇÃO DE AUDITORIA — eventos_itens_importacao_lote
# ============================================================================
# Trilha append-only do ITEM, completa desde a criação (PENDENTE),
# inclusive ANTES de documento_id existir — cobre exatamente o que
# eventos_documentais (FK documento_id NOT NULL) não consegue
# representar. Cenários A-I do comando de correção desta rodada.
# ============================================================================

def test_correcao_A_evento_item_criado_e_falha_antes_do_documento():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    resultado = amb.escrever(resultado_item, b'', _config(), 'lote-1')  # PDF inválido
    assert resultado.situacao == SituacaoItemExecucao.FAILED_RETRYABLE

    eventos = amb.eventos_item.listar_por_item(resultado.item_importacao_id)
    situacoes = [e.situacao for e in eventos]
    assert situacoes == [
        SituacaoItemExecucao.PENDENTE,
        SituacaoItemExecucao.EM_PROCESSAMENTO,
        SituacaoItemExecucao.FAILED_RETRYABLE,
    ]
    # Nenhum desses eventos tem documento_id -- o processo caiu ANTES do
    # hash/documento existir, e a trilha representa isso fielmente.
    assert all(e.documento_id is None for e in eventos)
    assert all(e.lote_id == 'lote-1' for e in eventos)


def test_correcao_B_retry_antes_de_documento_existir_acumula_eventos():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()

    r1 = amb.escrever(resultado_item, b'', config, 'lote-1')
    r2 = amb.escrever(resultado_item, b'', config, 'lote-1')
    assert r1.item_importacao_id == r2.item_importacao_id

    eventos = amb.eventos_item.listar_por_item(r1.item_importacao_id)
    tentativas_em_processamento = [
        e.tentativas for e in eventos if e.situacao == SituacaoItemExecucao.EM_PROCESSAMENTO
    ]
    assert tentativas_em_processamento == [1, 2]  # duas tentativas, nenhum documento em nenhuma
    assert all(e.documento_id is None for e in eventos)


def test_correcao_C_documento_so_aparece_na_trilha_apos_ser_resolvido():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.airtable.falhar_criar = True
    amb.escrever(resultado_item, pdf, config, 'lote-1')  # tentativa 1: falha no create
    amb.escrever(resultado_item, pdf, config, 'lote-1')  # tentativa 2: falha de novo
    amb.airtable.falhar_criar = False
    resultado_final = amb.escrever(resultado_item, pdf, config, 'lote-1')  # tentativa 3: sucesso
    assert resultado_final.situacao == SituacaoItemExecucao.SUCESSO

    eventos = amb.eventos_item.listar_por_item(resultado_final.item_importacao_id)
    indices_com_documento = [i for i, e in enumerate(eventos) if e.documento_id is not None]
    indices_sem_documento = [i for i, e in enumerate(eventos) if e.documento_id is None]
    assert indices_sem_documento  # existem eventos ANTES do documento
    assert indices_com_documento  # e eventos DEPOIS
    assert max(indices_sem_documento) < min(indices_com_documento)  # ordem correta, nunca invertida
    # Todo evento com documento_id aponta para o MESMO documento (nunca
    # duplicado entre tentativas -- reaproveita por hash).
    assert len({e.documento_id for e in eventos if e.documento_id}) == 1


def test_correcao_D_evento_registra_external_record_id_apos_crash():
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.airtable.pre_registrar('rec-crash', TipoDocumental.HOLERITE, anexo=False)
    agora = datetime.now(timezone.utc)
    amb.itens.criar_se_ausente('lote-1', resultado_item.manifesto_item_id, lambda: ItemExecucao(
        item_importacao_id='item-crash', lote_id='lote-1', manifesto_item_id=resultado_item.manifesto_item_id,
        tipo_documental=TipoDocumental.HOLERITE, documento_id=None, identidade_ingestao='ident-1',
        situacao=SituacaoItemExecucao.EM_PROCESSAMENTO, tentativas=1,
        external_record_id='rec-crash', external_criado_por_esta_execucao=True,
        attachment_confirmado=False, ultimo_erro_sanitizado=None, criado_em=agora, atualizado_em=agora,
    ))

    resultado = amb.escrever(resultado_item, pdf, config, 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO

    eventos = amb.eventos_item.listar_por_item('item-crash')
    assert any(e.detalhes.get('external_record_id') == 'rec-crash' for e in eventos)
    evento_final = eventos[-1]
    assert evento_final.situacao == SituacaoItemExecucao.SUCESSO
    assert evento_final.detalhes['attachment_confirmado'] is True


def test_correcao_E_evento_de_compensacao_registrado_na_trilha_do_item():
    amb = _Ambiente()
    amb.airtable.falhar_anexar = True
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_COMPENSATED

    eventos = amb.eventos_item.listar_por_item(resultado.item_importacao_id)
    assert eventos[-1].situacao == SituacaoItemExecucao.FAILED_COMPENSATED
    assert eventos[-1].erro_sanitizado is not None


def test_correcao_F_evento_orphan_registrado_na_trilha_do_item():
    amb = _Ambiente()
    amb.airtable.falhar_anexar = True
    amb.airtable.falhar_delete = True
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.FAILED_ORPHANED

    eventos = amb.eventos_item.listar_por_item(resultado.item_importacao_id)
    assert eventos[-1].situacao == SituacaoItemExecucao.FAILED_ORPHANED


def test_correcao_G_evento_sucesso_registrado_com_sequencia_completa():
    amb = _Ambiente()
    resultado = amb.escrever(_resultado_exact(), _pdf_valido(), _config(), 'lote-1')
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO

    eventos = amb.eventos_item.listar_por_item(resultado.item_importacao_id)
    situacoes = [e.situacao for e in eventos]
    # Num caminho feliz (sem falha), toda situação intermediária é
    # PENDENTE/EM_PROCESSAMENTO -- nunca um FAILED_* -- terminando em
    # SUCESSO. Vários checkpoints EM_PROCESSAMENTO são esperados (cada
    # marco -- tentativa, documento resolvido, external_record_id
    # obtido -- gera seu próprio evento, é isso que torna a sequência
    # reconstruível sem depender de log).
    assert situacoes[0] == SituacaoItemExecucao.PENDENTE
    assert situacoes[-1] == SituacaoItemExecucao.SUCESSO
    assert set(situacoes[1:-1]) <= {SituacaoItemExecucao.EM_PROCESSAMENTO}
    assert len(situacoes) >= 3

    # documento_id aparece None nos primeiros eventos e não-None a partir
    # de um certo ponto -- nunca "some" depois de aparecer.
    documentos = [e.documento_id for e in eventos]
    primeiro_com_documento = next(i for i, d in enumerate(documentos) if d is not None)
    assert all(d is None for d in documentos[:primeiro_com_documento])
    assert all(d is not None for d in documentos[primeiro_com_documento:])

    # ordem temporal estritamente não-decrescente -- append-only de verdade.
    timestamps = [e.timestamp for e in eventos]
    assert timestamps == sorted(timestamps)


def test_correcao_H_retomada_reconstroi_sequencia_sem_depender_do_estado_final():
    """A prova central desta correção: reconstruir "o que aconteceu com
    este item, em ordem" usando SÓ a trilha de eventos -- nunca o estado
    final do item -- e chegar exatamente na sequência real percorrida.

    Usa só falhas NÃO-terminais (FAILED_RETRYABLE) antes do sucesso --
    FAILED_COMPENSATED/FAILED_ORPHANED são terminais por desenho (exigem
    revisão humana, nunca retry automático) e propositalmente não fazem
    parte deste cenário de retomada bem-sucedida."""
    amb = _Ambiente()
    resultado_item = _resultado_exact()
    config = _config()
    pdf = _pdf_valido()

    amb.escrever(resultado_item, b'', config, 'lote-1')           # 1: PDF inválido -> FAILED_RETRYABLE
    amb.airtable.falhar_criar = True
    amb.escrever(resultado_item, pdf, config, 'lote-1')           # 2: documento ok, create falha -> FAILED_RETRYABLE
    amb.airtable.falhar_criar = False
    amb.airtable.releitura_override = False
    amb.escrever(resultado_item, pdf, config, 'lote-1')           # 3: create ok, confirmação nega -> FAILED_RETRYABLE
    amb.airtable.releitura_override = None
    resultado_final = amb.escrever(resultado_item, pdf, config, 'lote-1')  # 4: sucesso

    assert resultado_final.situacao == SituacaoItemExecucao.SUCESSO
    item_id = resultado_final.item_importacao_id
    eventos = amb.eventos_item.listar_por_item(item_id)

    # Reconstrução pura a partir da trilha -- nunca consulta amb.itens.
    sequencia_reconstruida = [(e.tentativas, e.situacao.value) for e in eventos]

    assert sequencia_reconstruida[0] == (0, 'PENDENTE')
    assert sequencia_reconstruida[-1][1] == 'SUCESSO'
    # A sequência de tentativas nunca regride (não-decrescente) -- prova
    # de que a trilha reflete a ordem real de execução, não uma reescrita.
    tentativas_em_ordem = [t for t, _s in sequencia_reconstruida]
    assert tentativas_em_ordem == sorted(tentativas_em_ordem)
    assert max(tentativas_em_ordem) == 4  # quatro chamadas -> quatro tentativas
    # Passou por pelo menos uma falha (não-terminal) antes do sucesso --
    # a trilha prova que houve retomada, algo que o estado final sozinho
    # (só "SUCESSO") não mostra.
    situacoes_intermediarias = {s for _t, s in sequencia_reconstruida[:-1]}
    assert 'FAILED_RETRYABLE' in situacoes_intermediarias
    # Documento resolvido uma única vez (tentativa 2 em diante) -- nunca
    # duplicado nas tentativas seguintes.
    documentos_distintos = {e.documento_id for e in eventos if e.documento_id}
    assert len(documentos_distintos) == 1


def test_correcao_I_eventos_item_nunca_contem_pii():
    amb = _Ambiente()
    nome_pii_simulado = 'CICLANO DE TAL SINTETICO'
    resultado = amb.escrever(
        _resultado_exact(), _pdf_valido(), _config(), 'lote-1', nome_referencia=nome_pii_simulado)
    assert resultado.situacao == SituacaoItemExecucao.SUCESSO

    eventos = amb.eventos_item.listar_por_item(resultado.item_importacao_id)
    assert len(eventos) >= 1
    for evento in eventos:
        texto = repr({
            'situacao': evento.situacao, 'erro_sanitizado': evento.erro_sanitizado,
            'detalhes': dict(evento.detalhes),
        })
        assert nome_pii_simulado not in texto

    campos_evento = {f.name for f in dataclasses.fields(EventoItemExecucao)}
    assert 'nome_referencia' not in campos_evento
    assert 'cpf' not in campos_evento
    assert 'nome' not in campos_evento


# ============================================================================
# conexao.py -- leitura de DATABASE_URL, sanitização de erro, injeção de
# `conectar` para teste (nenhum teste aqui depende do driver `psycopg`
# estar instalado).
# ============================================================================

def test_conexao_database_url_ausente_levanta_erro_proprio():
    with pytest.raises(conexao_mod.ConfiguracaoBancoAusente):
        conexao_mod.ler_database_url(ambiente={})


def test_conexao_database_url_presente_e_lida():
    url_configurada = 'postgres://' + 'host/db'
    url = conexao_mod.ler_database_url(ambiente={'DATABASE_URL': url_configurada})
    assert url == url_configurada


def test_conexao_abrir_conexao_usa_conectar_injetado_e_desativa_autocommit():
    chamadas = []

    class _ConexaoFake:
        def __init__(self):
            self.autocommit = True

    def _conectar_fake(url):
        chamadas.append(url)
        return _ConexaoFake()

    url_configurada = 'postgres://' + 'host/db'
    conexao = conexao_mod.abrir_conexao(
        database_url=url_configurada, conectar=_conectar_fake)
    assert chamadas == [url_configurada]
    assert conexao.autocommit is False


def test_conexao_falha_de_conexao_nunca_vaza_credencial():
    def _conectar_que_falha(url):
        raise ConnectionError(f'nao foi possivel conectar a {url}')

    usuario = 'usuario_' + 'secreto'
    senha = 'senha_' + 'secreta'
    prefixo = 'postgres://'
    credenciais = f'{usuario}:{senha}'
    url_com_credencial = prefixo + credenciais + '@host/db'
    with pytest.raises(conexao_mod.FalhaConexaoBanco) as exc_info:
        conexao_mod.abrir_conexao(
            database_url=url_com_credencial,
            conectar=_conectar_que_falha,
        )
    mensagem = str(exc_info.value)
    assert 'senha_secreta' not in mensagem
    assert 'usuario_secreto' not in mensagem
    assert '<sanitizado>' in mensagem
