"""Script one-shot do canário nominal WhatsApp + Assinatura V1 (missão
"IMPLEMENTAÇÃO LOCAL CONTROLADA — EXTRAÇÃO EVOLUTION + CANÁRIO NOMINAL
V1").

NUNCA importado nem chamado pelo cron -- `ciclo_producao_v1.py` não
referencia este módulo, e este módulo não se registra em nenhum
scheduler. Um disparo manual único, que termina sozinho.

Opera EXCLUSIVAMENTE sobre 1 par `(event_id, preview_id)` nominal,
definido pelas 2 constantes abaixo -- nunca chama
`listar_pares_elegiveis` (o mecanismo de descoberta ampla usado por
`ciclo_producao_v1.executar_um_ciclo_producao`), nunca processa
nenhum outro par. Isso não é uma allowlist adicional por cima do
legado -- é a ausência total do caminho de descoberta ampla:
`executar_proxima_acao_persistente` (reaproveitada sem alteração) já
é, por construção, restrita ao par que recebe.

Reaproveita integralmente: `RepositorioAcoesExecucaoPlanoPostgres`,
`RepositorioAutorizacoesGatePostgres`,
`RepositorioConclusaoObrigacaoAssinaturaPostgres`,
`executar_proxima_acao_persistente`, `observar_e_registrar_transicao`,
`compor_porta_execucao` (as 3 barreiras, inalteradas) e as composições
de storage/assinatura/conexão já existentes em `ciclo_producao_v1.py`
(reutilizadas aqui por import direto -- nenhuma configuração paralela).

O documento do canário (PDF sintético, sem PII) e a materialização do
`event_id`/`preview_id` nominais são responsabilidade de quem prepara
o canário ANTES de rodar este script (via
`wiring_assinatura_comunicacao_shadow.materializar_assinatura_shadow`,
inalterado) -- este script só EXECUTA uma ação já materializada e
autorizada, nunca cria uma."""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from .adapters.postgres_conclusao_obrigacao_assinatura import (
    RepositorioConclusaoObrigacaoAssinaturaPostgres,
)
from .ciclo_producao_v1 import (
    _compor_armazenamento_a_partir_do_ambiente,
    _compor_conexao_a_partir_do_ambiente,
    _compor_obrigacao_assinatura_a_partir_do_ambiente,
    compor_porta_execucao,
)
from .composicao_transporte_evolution_legado import compor_transporte_evolution_real
from .executor_persistente_fake import (
    ResultadoCicloExecutorPersistente,
    executar_proxima_acao_persistente,
)
from .observador_assinatura import observar_e_registrar_transicao
from .repositorio_acoes_execucao_plano_postgres import RepositorioAcoesExecucaoPlanoPostgres
from .repositorio_autorizacoes_gate_postgres import RepositorioAutorizacoesGatePostgres

logger = logging.getLogger(__name__)

# PLACEHOLDERS -- fail-closed enquanto None (invariante desta missão).
# Só devem ser preenchidos com os valores REAIS de event_id/preview_id
# depois de materializar o preview/autorização reais do canário (fora
# deste script) -- e só via PR revisada, nunca edição solta fora de
# controle de versão.
EVENT_ID_CANARIO_NOMINAL: Optional[str] = None
PREVIEW_ID_CANARIO_NOMINAL: Optional[str] = None

# Autorização estrutural (barreira 1) DESTE script -- literal, código
# revisado, nunca lido de ambiente. Continua sujeita às barreiras 2
# (ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO) e 3 (veto dry-run) dentro
# de compor_porta_execucao -- mesma função, nunca reimplementada aqui.
# `ciclo_producao_v1.main()` (o alvo do Cron Job) continua com
# autorizar_transporte_real=False, inalterado.
AUTORIZACAO_ESTRUTURAL_CANARIO_V1 = True

LIMITE_ACOES_POR_EXECUCAO = 5  # pequeno e explícito -- nunca lote


class CanarioNaoConfiguradoError(RuntimeError):
    """`EVENT_ID_CANARIO_NOMINAL`/`PREVIEW_ID_CANARIO_NOMINAL` ainda não
    foram preenchidos com os valores reais do canário -- fail-closed,
    nunca um valor de teste usado "por engano" em produção."""


@dataclasses.dataclass(frozen=True)
class ResultadoCanarioV1:
    acoes_processadas: Tuple[ResultadoCicloExecutorPersistente, ...]
    todas_sucedidas: bool
    observacao: Optional[Tuple[str, Optional[str]]]  # (acao_execucao_id, estado) ou None


def executar_canario_nominal(
    *,
    event_id: str,
    preview_id: str,
    conexao_postgres,
    armazenamento,
    porta_execucao,
    porta_obrigacao_assinatura,
    instante: datetime,
    claim_referencia: str,
    limite_acoes: int = LIMITE_ACOES_POR_EXECUCAO,
) -> ResultadoCanarioV1:
    """Processa SOMENTE o par `(event_id, preview_id)` informado.

    Continua reivindicando a PRÓXIMA ação do MESMO par só enquanto a
    anterior terminou `SUCCEEDED` (permite canário multi-ação: ex.
    texto + documento); para no primeiro `SEM_ACAO_ELEGIVEL` (fim
    normal, todas as ações esperadas concluídas) OU em qualquer outro
    estado (`FAILED_FINAL` -- que cobre `ENVIO_EXTERNO_INCERTO`,
    nunca retentável por `executar_proxima_acao_persistente`;
    `FAILED_RETRYABLE`; `BLOQUEADO_IDENTIDADE_DIVERGENTE`;
    `CLAIM_PERDIDO`) -- nunca retry automático, nunca continua para
    outra ação depois de qualquer resultado que não seja sucesso
    limpo.

    Só chama `observar_e_registrar_transicao` (a única leitura de
    assinatura desta função) quando TODAS as ações processadas nesta
    chamada terminaram `SUCCEEDED` -- nunca antes, nunca parcial."""
    if not event_id or not preview_id:
        raise CanarioNaoConfiguradoError(
            'event_id/preview_id do canário nominal ausentes -- nunca opera sem '
            'os valores reais definidos explicitamente.'
        )

    repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conexao_postgres)
    repositorio_autorizacoes = RepositorioAutorizacoesGatePostgres(conexao_postgres)

    resultados = []
    for _ in range(limite_acoes):
        resultado = executar_proxima_acao_persistente(
            repositorio_acoes=repositorio_acoes,
            repositorio_autorizacoes=repositorio_autorizacoes,
            armazenamento=armazenamento,
            porta_execucao=porta_execucao,
            event_id=event_id, preview_id=preview_id,
            claim_referencia=claim_referencia, instante=instante,
        )
        resultados.append(resultado)
        logger.info(
            '[CANARIO_V1] acao_execucao_id=%s situacao=%s',
            resultado.acao_execucao_id, resultado.situacao,
        )
        if resultado.situacao == 'SEM_ACAO_ELEGIVEL':
            break
        if resultado.situacao != 'SUCCEEDED':
            # Qualquer coisa que não seja sucesso limpo -- nunca retry
            # automático, nunca continua para outra ação do mesmo par.
            logger.warning(
                '[CANARIO_V1] parando: situacao=%s nao e SUCCEEDED nem SEM_ACAO_ELEGIVEL',
                resultado.situacao,
            )
            break

    # "Todas sucedidas" exige DUAS coisas: (1) o loop terminou de forma
    # limpa via SEM_ACAO_ELEGIVEL -- nunca por ter batido no limite,
    # que deixaria incerto se ainda há ação pendente não processada; e
    # (2) toda ação de fato tentada (excluindo o próprio marcador
    # SEM_ACAO_ELEGIVEL) terminou SUCCEEDED. Sem isso, um resultado
    # [SUCCEEDED, SUCCEEDED, SEM_ACAO_ELEGIVEL] seria incorretamente
    # marcado como falho só por o último elemento não ser 'SUCCEEDED'.
    resultados_de_acao = [r for r in resultados if r.situacao != 'SEM_ACAO_ELEGIVEL']
    todas_sucedidas = (
        bool(resultados) and resultados[-1].situacao == 'SEM_ACAO_ELEGIVEL'
        and bool(resultados_de_acao)
        and all(r.situacao == 'SUCCEEDED' for r in resultados_de_acao)
    )

    observacao = None
    if todas_sucedidas:
        ultima = resultados_de_acao[-1]
        repositorio_conclusao = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao_postgres)
        estado = observar_e_registrar_transicao(
            porta_assinatura=porta_obrigacao_assinatura,
            repositorio_conclusao=repositorio_conclusao,
            acao_execucao_id=ultima.acao_execucao_id,
            instante=instante,
        )
        observacao = (ultima.acao_execucao_id, estado)
        logger.info(
            '[CANARIO_V1] observacao acao_execucao_id=%s estado=%s',
            ultima.acao_execucao_id, estado,
        )
    else:
        logger.warning(
            '[CANARIO_V1] nao observando assinatura -- nem todas as acoes '
            'terminaram SUCCEEDED (%d processadas)', len(resultados),
        )

    return ResultadoCanarioV1(
        acoes_processadas=tuple(resultados), todas_sucedidas=todas_sucedidas, observacao=observacao,
    )


def main() -> int:
    """Entrypoint manual, ÚNICO disparo -- nunca chamado por
    cron/scheduler. Falha fechado antes de qualquer composição real se
    os placeholders não tiverem sido preenchidos."""
    logging.basicConfig(level=logging.INFO)
    if EVENT_ID_CANARIO_NOMINAL is None or PREVIEW_ID_CANARIO_NOMINAL is None:
        raise CanarioNaoConfiguradoError(
            'EVENT_ID_CANARIO_NOMINAL/PREVIEW_ID_CANARIO_NOMINAL ainda não foram '
            'preenchidos -- preencha com os valores reais do canário já '
            'materializado antes de rodar este script (PR revisada).'
        )
    conexao = _compor_conexao_a_partir_do_ambiente()
    try:
        armazenamento = _compor_armazenamento_a_partir_do_ambiente()
        porta_obrigacao_assinatura = _compor_obrigacao_assinatura_a_partir_do_ambiente()
        porta_execucao = compor_porta_execucao(
            autorizar_transporte_real=AUTORIZACAO_ESTRUTURAL_CANARIO_V1,
            transporte_evolution=compor_transporte_evolution_real(),
        )
        instante = datetime.now(timezone.utc)
        resultado = executar_canario_nominal(
            event_id=EVENT_ID_CANARIO_NOMINAL, preview_id=PREVIEW_ID_CANARIO_NOMINAL,
            conexao_postgres=conexao, armazenamento=armazenamento,
            porta_execucao=porta_execucao, porta_obrigacao_assinatura=porta_obrigacao_assinatura,
            instante=instante, claim_referencia=f'canario-v1-{instante.isoformat()}',
        )
        logger.info(
            '[CANARIO_V1] fim acoes_processadas=%d todas_sucedidas=%s observacao=%s',
            len(resultado.acoes_processadas), resultado.todas_sucedidas, resultado.observacao,
        )
        return 0
    finally:
        conexao.close()


if __name__ == '__main__':
    import sys
    sys.exit(main())
