"""Ciclo único de produção do wiring WhatsApp + Assinatura V1.

Não é um motor novo, não é uma fila nova, não é um scheduler próprio: é
só a composição, num único disparo síncrono, das peças já existentes e
testadas isoladamente (executor persistente, adapters de transporte e
assinatura, repositórios Postgres, observador). Quem agenda repetição é
o Render Cron Job (`render.yaml`) -- este módulo só sabe fazer UM ciclo
e terminar, nunca laça sozinho.

Responsabilidades, na ordem:
1. adquirir advisory lock de sessão (defesa contra overlap entre disparos
   do Cron Job -- CAS por ação continua sendo a defesa final);
2. se não adquirir, sair limpo, sem processar nada;
3. compor storage (`ArmazenamentoArquivosS3`, injetado -- nunca criado
   aqui com credencial real nesta fase) e repositórios Postgres;
4. escolher `ExecutorAcaoDryRun` ou `ExecutorEvolutionLegado` via
   `transporte_real_habilitado` -- nunca decide sozinho;
5. processar todas as ações elegíveis descobertas (`listar_pares_
   elegiveis`), até o limite de segurança por ciclo;
6. rodar o observador de assinatura DEPOIS do executor, para as ações
   já `SUCCEEDED`;
7. liberar o lock sempre, mesmo em erro.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from .adapters.postgres_conclusao_obrigacao_assinatura import (
    RepositorioConclusaoObrigacaoAssinaturaPostgres,
)
from .autorizacao_transporte_real import transporte_real_habilitado
from .executor_persistente_fake import (
    ExecutorAcaoDryRun,
    PortaExecucaoAcao,
    ResultadoCicloExecutorPersistente,
    executar_proxima_acao_persistente,
)
from .obrigacao_assinatura import PortaObrigacaoAssinatura
from .observador_assinatura import observar_e_registrar_transicao
from .repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
)
from .repositorio_autorizacoes_gate_postgres import RepositorioAutorizacoesGatePostgres

logger = logging.getLogger(__name__)

# Chave fixa e determinística do advisory lock de sessão -- nunca deriva
# de dado de execução (isso a tornaria imprevisível/colidível). Postgres
# advisory locks de sessão são liberados automaticamente pelo servidor
# quando a conexão cai (crash, timeout, kill) -- não é preciso (nem
# possível) implementar isso aqui, é garantia do próprio Postgres.
_CHAVE_LOCK_CICLO_PRODUCAO = 0x4D4147_4E415441  # "MAGNATA" em hex, cabe em bigint


@dataclasses.dataclass(frozen=True)
class ResultadoCicloProducao:
    lock_adquirido: bool
    acoes_processadas: Tuple[ResultadoCicloExecutorPersistente, ...]
    observacoes: Tuple[Tuple[str, Optional[str]], ...]


def compor_porta_execucao(
    *, autorizar_transporte_real: bool = False, transporte_evolution=None,
) -> PortaExecucaoAcao:
    """Único ponto de decisão fake-vs-real. `autorizar_transporte_real`
    é `False` por padrão literal -- nunca lido de variável de ambiente
    aqui. Delega inteiramente a decisão a `transporte_real_habilitado`,
    nunca reimplementando a regra das três barreiras."""
    if transporte_real_habilitado(autorizar_transporte_real=autorizar_transporte_real):
        if transporte_evolution is None:
            raise ValueError(
                'transporte_evolution é obrigatório quando o transporte real '
                'está habilitado pelas três barreiras'
            )
        from .adapters.executor_evolution_legado import ExecutorEvolutionLegado
        return ExecutorEvolutionLegado(transporte=transporte_evolution)
    return ExecutorAcaoDryRun()


def _adquirir_lock(conexao) -> bool:
    with conexao.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', (_CHAVE_LOCK_CICLO_PRODUCAO,))
        (adquirido,) = cursor.fetchone()
    return bool(adquirido)


def _liberar_lock(conexao) -> None:
    with conexao.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_unlock(%s)', (_CHAVE_LOCK_CICLO_PRODUCAO,))


def executar_um_ciclo_producao(
    *,
    conexao_postgres,
    armazenamento,
    porta_execucao: PortaExecucaoAcao,
    porta_obrigacao_assinatura: PortaObrigacaoAssinatura,
    instante: datetime,
    claim_referencia: str,
    max_acoes_por_par: int = 10,
    max_pares_por_ciclo: int = 50,
) -> ResultadoCicloProducao:
    """Um disparo completo (executor, depois observador), sempre com
    lock. Todas as dependências são injetadas -- este módulo nunca abre
    conexão, nunca lê variável de ambiente de credencial, nunca importa
    Airtable/Evolution/boto3 diretamente."""
    if not _adquirir_lock(conexao_postgres):
        logger.info('[CICLO_PRODUCAO] lock já em uso por outra execução -- saindo sem processar')
        return ResultadoCicloProducao(lock_adquirido=False, acoes_processadas=(), observacoes=())

    try:
        repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conexao_postgres)
        repositorio_autorizacoes = RepositorioAutorizacoesGatePostgres(conexao_postgres)

        resultados = []
        pares = repositorio_acoes.listar_pares_elegiveis(
            instante=instante, limite=max_pares_por_ciclo,
        )
        for event_id, preview_id in pares:
            for _ in range(max_acoes_por_par):
                resultado = executar_proxima_acao_persistente(
                    repositorio_acoes=repositorio_acoes,
                    repositorio_autorizacoes=repositorio_autorizacoes,
                    armazenamento=armazenamento,
                    porta_execucao=porta_execucao,
                    event_id=event_id,
                    preview_id=preview_id,
                    claim_referencia=claim_referencia,
                    instante=instante,
                )
                resultados.append(resultado)
                logger.info(
                    '[CICLO_PRODUCAO] acao_execucao_id=%s situacao=%s',
                    resultado.acao_execucao_id, resultado.situacao,
                )
                if resultado.situacao == 'SEM_ACAO_ELEGIVEL':
                    break

        repositorio_conclusao = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao_postgres)
        observacoes = []
        for acao in repositorio_acoes.listar_succeeded_recentes():
            try:
                estado = observar_e_registrar_transicao(
                    porta_assinatura=porta_obrigacao_assinatura,
                    repositorio_conclusao=repositorio_conclusao,
                    acao_execucao_id=acao.acao_execucao_id,
                    instante=instante,
                )
            except Exception as exc:
                # Indisponibilidade do adapter legado (Airtable fora do ar,
                # por exemplo): falha SÓ esta acao_execucao_id, nunca
                # registra estado falso, sempre elegível de novo no
                # próximo ciclo -- nada é persistido neste caminho.
                logger.warning(
                    '[CICLO_PRODUCAO] observador falhou para acao_execucao_id=%s classe=%s',
                    acao.acao_execucao_id, type(exc).__name__,
                )
                continue
            observacoes.append((acao.acao_execucao_id, estado))
            logger.info(
                '[CICLO_PRODUCAO] observador acao_execucao_id=%s estado=%s',
                acao.acao_execucao_id, estado,
            )

        return ResultadoCicloProducao(
            lock_adquirido=True,
            acoes_processadas=tuple(resultados),
            observacoes=tuple(observacoes),
        )
    finally:
        _liberar_lock(conexao_postgres)


# ---------------------------------------------------------------------
# Entrypoint de composição a partir do ambiente -- é o alvo declarativo
# do futuro Render Cron Job (`render.yaml`, serviço `magnata-orquestrador-
# ciclo`, NÃO provisionado nesta fase). Só esta seção lê variável de
# ambiente e só ela importa `boto3`/`psycopg` (via `abrir_conexao`) --
# nunca o resto deste módulo, nunca o domínio. Falha de configuração
# aqui é sempre `RuntimeError` explícito, nunca um default silencioso
# que inventaria bucket/URL/credencial.
# ---------------------------------------------------------------------

def _compor_conexao_a_partir_do_ambiente():
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    return abrir_conexao()


def _compor_armazenamento_a_partir_do_ambiente():
    from magnata_os.documental.modulo01.adapters.s3_armazenamento import (
        ArmazenamentoArquivosS3,
    )

    bucket = (os.environ.get('ORQUESTRADOR_S3_BUCKET') or '').strip()
    if not bucket:
        raise RuntimeError(
            'ORQUESTRADOR_S3_BUCKET não configurado -- o ciclo de produção '
            'nunca infere bucket por padrão (fail-closed).'
        )
    prefixo = os.environ.get('ORQUESTRADOR_S3_PREFIXO', 'documentos/')
    import boto3  # import local -- único ponto deste módulo acoplado ao driver
    cliente = boto3.client('s3')
    return ArmazenamentoArquivosS3(cliente, bucket=bucket, prefixo=prefixo)


def _compor_obrigacao_assinatura_a_partir_do_ambiente() -> PortaObrigacaoAssinatura:
    from .adapters.obrigacao_assinatura_legado_http import (
        AdapterObrigacaoAssinaturaLegadoHttp,
    )

    base_url = (os.environ.get('ORQUESTRADOR_ASSINATURA_BASE_URL') or '').strip()
    api_key = (os.environ.get('ORQUESTRADOR_ASSINATURA_API_KEY') or '').strip()
    if not base_url or not api_key:
        raise RuntimeError(
            'ORQUESTRADOR_ASSINATURA_BASE_URL/ORQUESTRADOR_ASSINATURA_API_KEY '
            'não configurados -- o observador de assinatura nunca roda sem '
            'os dois (fail-closed).'
        )
    return AdapterObrigacaoAssinaturaLegadoHttp(base_url=base_url, api_key=api_key)


def main() -> int:
    """Um disparo, terminando sempre -- é isto que o Cron Job repete
    periodicamente (ver render.yaml). `autorizar_transporte_real` fica
    fixado em `False` aqui, literal: ligar o transporte real é sempre
    uma mudança de código revisada em PR (barreira 1), nunca uma opção
    de configuração deste entrypoint."""
    logging.basicConfig(level=logging.INFO)
    conexao = _compor_conexao_a_partir_do_ambiente()
    try:
        armazenamento = _compor_armazenamento_a_partir_do_ambiente()
        porta_obrigacao_assinatura = _compor_obrigacao_assinatura_a_partir_do_ambiente()
        porta_execucao = compor_porta_execucao(autorizar_transporte_real=False)
        instante = datetime.now(timezone.utc)
        resultado = executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=armazenamento,
            porta_execucao=porta_execucao,
            porta_obrigacao_assinatura=porta_obrigacao_assinatura,
            instante=instante,
            claim_referencia=f'cron-ciclo-producao-v1-{instante.isoformat()}',
        )
        logger.info(
            '[CICLO_PRODUCAO] fim lock_adquirido=%s acoes_processadas=%d observacoes=%d',
            resultado.lock_adquirido, len(resultado.acoes_processadas), len(resultado.observacoes),
        )
        return 0
    finally:
        conexao.close()


if __name__ == '__main__':
    import sys
    sys.exit(main())
