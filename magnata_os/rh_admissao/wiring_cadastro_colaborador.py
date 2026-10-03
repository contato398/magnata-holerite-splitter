"""Wiring: liga o gatilho do Kit de Admissão (`gatilho_admissao.py`,
INTOCADO) à persistência do Cadastro de Colaborador PRÓPRIO
(`dominio_cadastro_colaborador.py` + `RepositorioColaboradores`).

Por que uma FUNÇÃO NOVA que envolve `processar_kit_admissao`/
`processar_lote_kits_admissao`, em vez de alterá-los: ambos já têm
teste e uso próprios (`tests/test_magnata_os_rh_admissao_gatilho_
admissao.py`); mexer neles misturaria "correção/extensão do gatilho"
com "cadastro persistente novo", violando `/CLAUDE.md` §8 ("mudanças
pequenas e isoladas -- um objetivo por vez"). `processar_kit_admissao`/
`processar_lote_kits_admissao` continuam EXATAMENTE como já estavam.

`repositorio_colaboradores` é OPCIONAL e injetado -- sem ele, chamar as
funções deste módulo é idêntico a chamar `processar_kit_admissao`/
`processar_lote_kits_admissao` direto (nenhuma persistência, nenhum
efeito colateral novo).

REGRA DE PERSISTÊNCIA AUTOMÁTICA (item 5 da missão, registrada também
em `docs/decisoes/cadastro-colaborador-persistente-v1.md` §3):
- kit COM determinação -> persiste `Colaborador` `CADASTRO_COMPLETO`,
  `local_trabalho` preenchido.
- kit SEM determinação -> persiste `Colaborador`
  `AGUARDANDO_LOCAL_TRABALHO`, `local_trabalho` `None`.
- resultado REAPROVEITADO (idempotência do próprio gatilho) -> nenhuma
  escrita nova (nada mudou desde a última vez que este `colaborador_id`
  foi processado).
- resultado `FALHOU` -> nenhuma escrita (nunca persiste um Colaborador
  a partir de dados que o próprio gatilho já rejeitou).
- colaborador JÁ cadastrado com `local_trabalho` DIFERENTE do que este
  kit traz -> NUNCA sobrescreve silenciosamente (mesma regra de
  `aplicar_determinacao_local_trabalho`, sem `motivo_correcao`
  automático aqui) -- o cadastro existente fica como estava; o conflito
  é logado (`EVENTO_WIRING_CADASTRO_COLABORADOR_CONFLITO`), nunca
  lançado para o chamador: corrigir um local de trabalho já definido é
  sempre o canal manual
  (`scripts/determinar_local_trabalho_colaborador_cli.py`, item 6),
  nunca o caminho automático do gatilho.
- qualquer outra falha ao persistir (ex.: Postgres fora do ar) é
  isolada e logada (`EVENTO_WIRING_CADASTRO_COLABORADOR_FALHOU`) --
  nunca derruba o resultado do gatilho nem o processamento dos demais
  kits do lote (`/CLAUDE.md` §4, "falha nunca é silenciosa" + "falha
  isolada não impede o processamento dos demais").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    LocalTrabalhoJaDefinidoError,
    aplicar_determinacao_local_trabalho,
    compor_colaborador_a_partir_do_kit,
)
from magnata_os.rh_admissao.gatilho_admissao import (
    DadosColaboradorKitAdmissao,
    DeterminacaoLocalTrabalho,
    PortaSecullum,
    RegistroGatilhoAdmissaoEmMemoria,
    ResultadoGatilhoAdmissao,
    SituacaoGatilhoAdmissao,
    processar_kit_admissao,
)
from magnata_os.rh_admissao.repositorio_colaboradores import RepositorioColaboradores

_logger = logging.getLogger(__name__)

EVENTO_WIRING_CADASTRO_COLABORADOR_PERSISTIDO = 'wiring_cadastro_colaborador_persistido'
EVENTO_WIRING_CADASTRO_COLABORADOR_CONFLITO = 'wiring_cadastro_colaborador_conflito_local_trabalho'
EVENTO_WIRING_CADASTRO_COLABORADOR_FALHOU = 'wiring_cadastro_colaborador_falhou'


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _persistir_colaborador(
    dados: DadosColaboradorKitAdmissao,
    determinacao: Optional[DeterminacaoLocalTrabalho],
    repositorio_colaboradores: RepositorioColaboradores,
) -> None:
    """Nunca lança para o chamador -- toda falha (conflito de negócio
    ou falha técnica de persistência) é isolada e logada, nunca
    propagada (ver regra no cabeçalho do módulo)."""
    try:
        existente = repositorio_colaboradores.buscar_por_id(dados.colaborador_id)
        if existente is None:
            colaborador = compor_colaborador_a_partir_do_kit(dados, determinacao, agora=_agora())
            repositorio_colaboradores.salvar(colaborador)
        elif determinacao is not None:
            atualizado, _evento = aplicar_determinacao_local_trabalho(existente, determinacao)
            repositorio_colaboradores.salvar(atualizado)
        # existente is not None and determinacao is None: nada de novo a
        # gravar -- o kit continua sem determinação; o cadastro já está
        # no estado que um processamento anterior já deixou.
        _logger.info(
            '%s colaborador_id=%s', EVENTO_WIRING_CADASTRO_COLABORADOR_PERSISTIDO, dados.colaborador_id,
            extra={'evento': EVENTO_WIRING_CADASTRO_COLABORADOR_PERSISTIDO, 'colaborador_id': dados.colaborador_id},
        )
    except LocalTrabalhoJaDefinidoError:
        _logger.warning(
            '%s colaborador_id=%s', EVENTO_WIRING_CADASTRO_COLABORADOR_CONFLITO, dados.colaborador_id,
            extra={'evento': EVENTO_WIRING_CADASTRO_COLABORADOR_CONFLITO, 'colaborador_id': dados.colaborador_id},
        )
    except Exception as exc:  # falha isolada de persistência -- nunca derruba o resultado do gatilho
        _logger.error(
            '%s colaborador_id=%s exception_type=%s', EVENTO_WIRING_CADASTRO_COLABORADOR_FALHOU,
            dados.colaborador_id, type(exc).__name__,
            extra={'evento': EVENTO_WIRING_CADASTRO_COLABORADOR_FALHOU, 'colaborador_id': dados.colaborador_id,
                   'exception_type': type(exc).__name__},
        )


def processar_kit_admissao_com_cadastro(
    dados: DadosColaboradorKitAdmissao,
    determinacao: Optional[DeterminacaoLocalTrabalho],
    *,
    porta: Optional[PortaSecullum] = None,
    registro: Optional[RegistroGatilhoAdmissaoEmMemoria] = None,
    repositorio_colaboradores: Optional[RepositorioColaboradores] = None,
) -> ResultadoGatilhoAdmissao:
    """Envolve `processar_kit_admissao` (INTOCADO) -- mesmo retorno,
    mesmo comportamento -- e, quando `repositorio_colaboradores` é
    injetado, também persiste o `Colaborador` resultante (ver regra no
    cabeçalho deste módulo). Sem `repositorio_colaboradores`, chamar
    esta função é idêntico a chamar `processar_kit_admissao` direto."""
    resultado = processar_kit_admissao(dados, determinacao, porta=porta, registro=registro)

    if (
        repositorio_colaboradores is not None
        and not resultado.reaproveitado
        and resultado.situacao != SituacaoGatilhoAdmissao.FALHOU
    ):
        _persistir_colaborador(dados, determinacao, repositorio_colaboradores)

    return resultado


def processar_lote_kits_admissao_com_cadastro(
    itens: List[Tuple[DadosColaboradorKitAdmissao, Optional[DeterminacaoLocalTrabalho]]],
    *,
    porta: Optional[PortaSecullum] = None,
    registro: Optional[RegistroGatilhoAdmissaoEmMemoria] = None,
    repositorio_colaboradores: Optional[RepositorioColaboradores] = None,
) -> List[ResultadoGatilhoAdmissao]:
    """Equivalente em lote de `processar_kit_admissao_com_cadastro` --
    mesma isolação de falha por item já garantida por
    `processar_lote_kits_admissao` (cada item passa por sua própria
    captura de erro, tanto no gatilho quanto na persistência)."""
    resultados: List[ResultadoGatilhoAdmissao] = []
    for dados, determinacao in itens:
        resultados.append(
            processar_kit_admissao_com_cadastro(
                dados, determinacao,
                porta=porta, registro=registro, repositorio_colaboradores=repositorio_colaboradores,
            )
        )
    return resultados
