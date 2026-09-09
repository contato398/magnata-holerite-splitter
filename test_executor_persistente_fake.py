"""Ciclo completo verificar -> claim exato -> fake -> checkpoint, sem rede."""
import ast
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
)
from magnata_os.orquestrador.autorizacao_gate import (
    DecisaoGate,
    RegistroAutorizacaoGate,
    RepositorioAutorizacoesGateEmMemoria,
)
from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.envelope_execucao_autorizada import (
    EnvelopeExecucaoError,
    armazenar_acao_e_envelope_v1,
)
from magnata_os.orquestrador.executor_persistente_fake import (
    ResultadoExecucaoPorta,
    executar_proxima_acao_persistente,
)
from magnata_os.orquestrador.plano_comunicacao import AcaoEnvio, PlanoDisparo
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    criar_registro_acao_plano,
)

AGORA = datetime(2099, 5, 1, tzinfo=timezone.utc)


def _autorizacao():
    return RegistroAutorizacaoGate(
        autorizacao_id='auth-executor-v1', event_id='evento-executor-v1',
        preview_id='preview-executor-v1', decisao=DecisaoGate.AUTORIZADO,
        ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='teste:sintetico',
    )


def _cenario(armazenamento=None):
    acao = AcaoEnvio(
        destinatario='destinatario:sintetico', ordem=1, tipo='documento',
        nome='arquivo-sintetico.bin', conteudo=b'bytes-sinteticos',
        legenda='legenda sintetica',
    )
    plano = PlanoDisparo(
        preview_id='preview-executor-v1',
        destinatarios=(acao.destinatario,), acoes=(acao,),
        mensagens_por_pessoa=1, total_notificacoes=1,
    )
    registro = criar_registro_acao_plano(
        event_id='evento-executor-v1', plano=plano,
        autorizacao=_autorizacao(), acao=acao, criado_em=AGORA,
    )
    armazenamento = armazenamento or ArmazenamentoArquivosEmMemoria()
    envelope = armazenar_acao_e_envelope_v1(
        armazenamento=armazenamento, registro=registro, acao=acao,
    )
    registro = dataclasses.replace(registro, envelope_sha256=envelope)
    autorizacoes = RepositorioAutorizacoesGateEmMemoria()
    autorizacoes.registrar_se_novo(_autorizacao())
    return acao, registro, armazenamento, autorizacoes


class _RepositorioAcoesEmMemoria:
    def __init__(self, registro, *, claim_perdido=False, divergente=False,
                 eventos=None):
        self.registro = registro
        self.claim_perdido = claim_perdido
        self.divergente = divergente
        self.chamadas = []
        self.eventos = eventos

    def buscar_proxima_elegivel(self, **kwargs):
        self.chamadas.append('buscar')
        if self.eventos is not None:
            self.eventos.append('buscar')
        if self.registro.envelope_sha256 is None:
            return None
        if self.registro.estado not in {
            EstadoAcaoExecucaoPlano.PENDING,
            EstadoAcaoExecucaoPlano.FAILED_RETRYABLE,
        }:
            return None
        return self.registro

    def reivindicar_acao_exata(self, *, acao_execucao_id, claim_referencia,
                               reivindicado_em):
        self.chamadas.append(('claim', acao_execucao_id))
        if self.eventos is not None:
            self.eventos.append('claim')
        if self.claim_perdido or acao_execucao_id != self.registro.acao_execucao_id:
            return None
        self.registro = dataclasses.replace(
            self.registro,
            estado=EstadoAcaoExecucaoPlano.EXECUTING,
            attempt=self.registro.attempt + 1,
            claim_sha256='c' * 64,
            reivindicado_em=reivindicado_em,
            envelope_sha256=(
                'd' * 64 if self.divergente else self.registro.envelope_sha256
            ),
        )
        return self.registro

    def marcar_sucesso(self, **kwargs):
        self.chamadas.append('sucesso')
        if self.eventos is not None:
            self.eventos.append('checkpoint')
        self.registro = dataclasses.replace(
            self.registro, estado=EstadoAcaoExecucaoPlano.SUCCEEDED,
            resultado_referencia=kwargs['resultado_referencia'],
            concluido_em=kwargs['atualizado_em'],
        )
        return self.registro

    def marcar_falha(self, **kwargs):
        self.chamadas.append(('falha', kwargs['retentavel']))
        self.registro = dataclasses.replace(
            self.registro,
            estado=(EstadoAcaoExecucaoPlano.FAILED_RETRYABLE
                    if kwargs['retentavel']
                    else EstadoAcaoExecucaoPlano.FAILED_FINAL),
            ultimo_erro_classe=kwargs['erro_classe'],
            proxima_tentativa_em=kwargs.get('proxima_tentativa_em'),
        )
        return self.registro


class _PortaCaptura:
    def __init__(self, falha=None, eventos=None):
        self.acoes = []
        self.falha = falha
        self.eventos = eventos

    def executar(self, acao):
        self.acoes.append(acao)
        if self.eventos is not None:
            self.eventos.append('fake')
        if self.falha:
            raise self.falha
        return ResultadoExecucaoPorta('fake:resultado-opaco', b'evidencia-fake')


def _executar(repo, armazenamento, autorizacoes, porta):
    return executar_proxima_acao_persistente(
        repositorio_acoes=repo,
        repositorio_autorizacoes=autorizacoes,
        armazenamento=armazenamento,
        porta_execucao=porta,
        event_id='evento-executor-v1',
        preview_id='preview-executor-v1',
        claim_referencia='worker:sintetico:1',
        instante=AGORA,
    )


def test_restart_recupera_valida_claima_exato_executa_fake_e_checkpointa():
    acao, registro, armazenamento, autorizacoes = _cenario()
    repo = _RepositorioAcoesEmMemoria(registro)
    porta = _PortaCaptura()
    resultado = _executar(repo, armazenamento, autorizacoes, porta)
    assert resultado.situacao == 'SUCCEEDED'
    assert resultado.registro_final.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    assert porta.acoes == [acao]
    assert repo.chamadas == [
        'buscar', ('claim', registro.acao_execucao_id), 'sucesso',
    ]


def test_payload_e_lido_so_antes_do_claim_e_reutilizado_apos_cas():
    eventos = []

    class _StorageObservavel(ArmazenamentoArquivosEmMemoria):
        def abrir_leitura(self, hash_sha256):
            eventos.append('ler_blob')
            return super().abrir_leitura(hash_sha256)

    armazenamento = _StorageObservavel()
    _, registro, armazenamento, autorizacoes = _cenario(armazenamento)
    repo = _RepositorioAcoesEmMemoria(registro, eventos=eventos)
    porta = _PortaCaptura(eventos=eventos)
    assert _executar(repo, armazenamento, autorizacoes, porta).situacao == 'SUCCEEDED'
    assert eventos == [
        'buscar', 'ler_blob', 'ler_blob', 'claim', 'fake', 'checkpoint',
    ]


def test_race_do_claim_exato_nunca_entrega_outra_acao_ao_fake():
    _, registro, armazenamento, autorizacoes = _cenario()
    repo = _RepositorioAcoesEmMemoria(registro, claim_perdido=True)
    porta = _PortaCaptura()
    resultado = _executar(repo, armazenamento, autorizacoes, porta)
    assert resultado.situacao == 'CLAIM_PERDIDO'
    assert porta.acoes == []
    assert repo.chamadas == ['buscar', ('claim', registro.acao_execucao_id)]


def test_snapshot_divergente_apos_claim_bloqueia_efeito_e_finaliza_fechado():
    _, registro, armazenamento, autorizacoes = _cenario()
    repo = _RepositorioAcoesEmMemoria(registro, divergente=True)
    porta = _PortaCaptura()
    resultado = _executar(repo, armazenamento, autorizacoes, porta)
    assert resultado.situacao == 'BLOQUEADO_IDENTIDADE_DIVERGENTE'
    assert resultado.registro_final.estado == EstadoAcaoExecucaoPlano.FAILED_FINAL
    assert porta.acoes == []


def test_falha_transitoria_usa_retry_existente_e_incremento_do_claim():
    _, registro, armazenamento, autorizacoes = _cenario()
    repo = _RepositorioAcoesEmMemoria(registro)
    porta = _PortaCaptura(FalhaTransitoria())
    resultado = _executar(repo, armazenamento, autorizacoes, porta)
    assert resultado.situacao == 'FAILED_RETRYABLE'
    assert resultado.registro_final.attempt == 1
    assert resultado.registro_final.proxima_tentativa_em > AGORA


def test_envelope_null_e_executing_orfao_nao_chegam_ao_claim_nem_fake():
    _, registro, armazenamento, autorizacoes = _cenario()
    for protegido in (
        dataclasses.replace(registro, envelope_sha256=None),
        dataclasses.replace(registro, estado=EstadoAcaoExecucaoPlano.EXECUTING),
    ):
        repo = _RepositorioAcoesEmMemoria(protegido)
        porta = _PortaCaptura()
        resultado = _executar(repo, armazenamento, autorizacoes, porta)
        assert resultado.situacao == 'SEM_ACAO_ELEGIVEL'
        assert porta.acoes == []
        assert repo.chamadas == ['buscar']


def test_envelope_adulterado_falha_antes_do_claim():
    _, registro, armazenamento, autorizacoes = _cenario()
    armazenamento._objetos[registro.envelope_sha256] = b'adulterado'
    repo = _RepositorioAcoesEmMemoria(registro)
    porta = _PortaCaptura()
    with pytest.raises(EnvelopeExecucaoError):
        _executar(repo, armazenamento, autorizacoes, porta)
    assert repo.chamadas == ['buscar']
    assert porta.acoes == []


def test_executor_nao_importa_transporte_e_nao_conhece_sistemas_externos():
    fonte = Path(
        'magnata_os/orquestrador/executor_persistente_fake.py'
    ).read_text(encoding='utf-8')
    arvore = ast.parse(fonte)
    importados = {
        alias.name.lower()
        for no in ast.walk(arvore)
        if isinstance(no, (ast.Import, ast.ImportFrom))
        for alias in no.names
    }
    assert not any('transporte' in nome for nome in importados)
    assert not any('whatsapp' in nome for nome in importados)
    assert not any('evolution' in nome for nome in importados)
    assert not any('airtable' in nome for nome in importados)
    assert '/whatsapp/enviar-' not in fonte
