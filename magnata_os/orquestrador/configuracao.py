"""
Configuracao global do Orquestrador — DRY_RUN e KILL_SWITCH.

DRY_RUN: modo simulacao — evento e processado até executar acao, mas
nenhum side effect e executado. Útil para:
- diagnostico
- teste ponta a ponta sem mudança
- validacao de politica sem executar

KILL_SWITCH: desabilita EXECUTE_SAFE automaticamente, forçando
HUMAN_REQUIRED para tudo. Útil para:
- pausar automação sem mudar código
- failsafe operacional
- manutencao

Ambos sao fail-safe por desenho:
- DRY_RUN=true lê de ambiente ou argumento, default False
- KILL_SWITCH=true lê de ambiente ou arquivo, default False
- Se legível: apply
- Se erro ao ler: assume True (falha segura)

Nenhum estado persistido em motor.py — leitura fresca em cada processar().
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def deve_rodar_em_dry_run() -> bool:
    """
    Verifica se modo DRY_RUN está ativado.

    Lê: variável de ambiente ORQUESTRADOR_DRY_RUN (qualquer valor nao-vazio = True).

    Em dry-run, evento e processado até a acao, mas nenhum side effect e
    executado (nenhuma chamada a Acao.executar, nenhuma mudança de estado
    externa). Util para teste e diagnostico.
    """
    return os.environ.get('ORQUESTRADOR_DRY_RUN', '').lower() in ('1', 'true', 'yes')


def esta_kill_switch_ativado(arquivo_kill_switch: Optional[Path] = None) -> bool:
    """
    Verifica se KILL_SWITCH está ativado.

    Procura por arquivo `.orquestrador_kill_switch` na raiz do repositorio
    (ou caminho customizado se passado). Se arquivo existe e é legível,
    kill switch = ativado.

    Em kill switch ativado, politica de autonomia e forçada a HUMAN_REQUIRED
    para tudo — nenhuma acao com nivel > OBSERVE e permitida.

    Failsafe: se nao conseguir ler arquivo (error de I/O, permissao), assume
    kill switch = ativado (falha segura).
    """
    caminho = arquivo_kill_switch or Path('.orquestrador_kill_switch')

    if not caminho.is_absolute():
        caminho = Path.cwd() / caminho

    try:
        return caminho.exists()
    except OSError:
        # Erro ao verificar arquivo = falha segura = assume kill switch ativado
        return True


def modo_seco_executavel(acao_nome: str) -> bool:
    """Retorna True se DRY_RUN esta ativado e a acao nao deve ser executada.

    Usado em motor.py antes de chamar Acao.executar():

        if modo_seco_executavel('atualizar_auto_fact'):
            # registra que teria executado, mas nao executa
            resultado = ResultadoAcao(
                sucesso=True,
                evidencia='DRY_RUN: simulacao realizada sem side effect'
            )
        else:
            resultado = acao.executar(evento)
    """
    return deve_rodar_em_dry_run()


def aplicar_kill_switch_bloqueio(nivel_autonomia: int, arquivo_kill_switch: Optional[Path] = None) -> int:
    """
    Se KILL_SWITCH está ativado, força nivel de autonomia para HUMAN_REQUIRED (5).

    Usado em motor.py após calcular o nivel baseado em politica:

        nivel = nivel_para(evento.type)
        nivel = aplicar_kill_switch_bloqueio(nivel)
        # agora se kill_switch estava ativado, nivel = 5

    Failsafe: erro ao ler kill_switch arquivo = assume ativado.
    """
    if esta_kill_switch_ativado(arquivo_kill_switch):
        return 5  # HUMAN_REQUIRED
    return nivel_autonomia


# Constantes de nivel de autonomia (espelho de politica_autonomia.py)
NIVEL_OBSERVE = 0
NIVEL_DETECT = 1
NIVEL_CLASSIFY = 2
NIVEL_PROPOSE = 3
NIVEL_EXECUTE_SAFE = 4
NIVEL_HUMAN_REQUIRED = 5
