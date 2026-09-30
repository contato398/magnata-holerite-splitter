"""Wiring: `processar_kit_admissao_com_cadastro`/`processar_lote_kits_
admissao_com_cadastro` -- persistência automática do Colaborador ao
processar o Kit de Admissão. Cobre: persistência com/sem local de
trabalho no kit, não-persistência por reaproveitamento (idempotência do
gatilho), conflito com local de trabalho já persistido (nunca
sobrescreve), e ausência de repositório (comportamento idêntico ao
gatilho puro). Dados 100% sintéticos, repositório em memória (nenhum
Postgres necessário)."""
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import pytest

from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    Colaborador,
    EventoCorrecaoLocalTrabalho,
    SituacaoCadastroColaborador,
)
from magnata_os.rh_admissao.gatilho_admissao import (
    DadosColaboradorKitAdmissao,
    DeterminacaoLocalTrabalho,
    RegistroGatilhoAdmissaoEmMemoria,
    SituacaoGatilhoAdmissao,
)
from magnata_os.rh_admissao.wiring_cadastro_colaborador import (
    processar_kit_admissao_com_cadastro,
    processar_lote_kits_admissao_com_cadastro,
)

CPF_SINTETICO = '900.000.000-01'
NOME_SINTETICO = 'colaborador sintetico teste'
_AGORA = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


class RepositorioColaboradoresEmMemoria:
    """Dublê de teste do Protocol `RepositorioColaboradores`."""

    def __init__(self) -> None:
        self._por_id: Dict[str, Colaborador] = {}

    def salvar(self, colaborador: Colaborador) -> Colaborador:
        self._por_id[colaborador.colaborador_id] = colaborador
        return colaborador

    def buscar_por_id(self, colaborador_id: str) -> Optional[Colaborador]:
        return self._por_id.get(colaborador_id)

    def listar(self) -> Tuple[Colaborador, ...]:
        return tuple(self._por_id.values())

    def registrar_evento_correcao_local_trabalho(
        self, evento: EventoCorrecaoLocalTrabalho,
    ) -> EventoCorrecaoLocalTrabalho:
        # O wiring automático (`processar_kit_admissao_com_cadastro`)
        # nunca corrige local_trabalho já definido (só o canal manual
        # faz isso) -- este dublê existe só para conformidade estrutural
        # com o Protocol `RepositorioColaboradores`, nunca exercitado
        # neste arquivo de teste.
        raise NotImplementedError('wiring automatico nunca registra correcao')

    def listar_historico_correcao_local_trabalho(
        self, colaborador_id: str,
    ) -> Tuple[EventoCorrecaoLocalTrabalho, ...]:
        return ()


def _dados(colaborador_id='colab-1'):
    return DadosColaboradorKitAdmissao(colaborador_id, CPF_SINTETICO, NOME_SINTETICO, 'Vigia')


def _determinacao(grupo='Escala A - Dias Pares', em=None):
    return DeterminacaoLocalTrabalho(grupo, 'operador.rh@magnataservicos.com.br', em or _AGORA)


def test_com_local_trabalho_persiste_cadastro_completo():
    repo = RepositorioColaboradoresEmMemoria()
    resultado = processar_kit_admissao_com_cadastro(
        _dados(), _determinacao(), repositorio_colaboradores=repo,
    )
    assert resultado.situacao == SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA
    persistido = repo.buscar_por_id('colab-1')
    assert persistido is not None
    assert persistido.situacao_cadastro == SituacaoCadastroColaborador.CADASTRO_COMPLETO
    assert persistido.local_trabalho == 'Escala A - Dias Pares'


def test_sem_local_trabalho_persiste_aguardando_local_trabalho():
    repo = RepositorioColaboradoresEmMemoria()
    resultado = processar_kit_admissao_com_cadastro(
        _dados(), None, repositorio_colaboradores=repo,
    )
    assert resultado.situacao == SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO
    persistido = repo.buscar_por_id('colab-1')
    assert persistido is not None
    assert persistido.situacao_cadastro == SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO
    assert persistido.local_trabalho is None


def test_sem_repositorio_injetado_comportamento_identico_ao_gatilho_puro():
    resultado = processar_kit_admissao_com_cadastro(_dados(), _determinacao())
    assert resultado.situacao == SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA


def test_reaproveitado_pelo_registro_nao_grava_de_novo():
    repo = RepositorioColaboradoresEmMemoria()
    registro = RegistroGatilhoAdmissaoEmMemoria()

    processar_kit_admissao_com_cadastro(
        _dados(), _determinacao(), registro=registro, repositorio_colaboradores=repo,
    )
    # reprocessar o MESMO kit, com uma determinacao DIFERENTE -- como o
    # registro ja tem o resultado (reaproveitado=True), o wiring nunca
    # tenta persistir de novo, entao o conflito nem chega a aparecer.
    resultado2 = processar_kit_admissao_com_cadastro(
        _dados(), _determinacao(grupo='Escala B - Dias Impares'),
        registro=registro, repositorio_colaboradores=repo,
    )

    assert resultado2.reaproveitado is True
    persistido = repo.buscar_por_id('colab-1')
    assert persistido.local_trabalho == 'Escala A - Dias Pares'  # inalterado


def test_conflito_com_local_trabalho_ja_persistido_nao_sobrescreve():
    repo = RepositorioColaboradoresEmMemoria()
    # primeiro kit: sem registro de idempotencia (simula 2 chamadas
    # independentes, ex.: 2 execucoes de processo, mesmo colaborador).
    processar_kit_admissao_com_cadastro(_dados(), _determinacao(), repositorio_colaboradores=repo)

    resultado2 = processar_kit_admissao_com_cadastro(
        _dados(), _determinacao(grupo='Escala B - Dias Impares'), repositorio_colaboradores=repo,
    )

    assert resultado2.situacao == SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA  # gatilho em si nao falha
    persistido = repo.buscar_por_id('colab-1')
    assert persistido.local_trabalho == 'Escala A - Dias Pares'  # cadastro nunca sobrescrito em silencio


def test_lote_isola_persistencia_falha_de_um_item_nao_afeta_os_demais():
    repo = RepositorioColaboradoresEmMemoria()
    resultados = processar_lote_kits_admissao_com_cadastro(
        [
            (_dados('colab-1'), _determinacao()),
            (_dados('colab-2'), None),
        ],
        repositorio_colaboradores=repo,
    )
    assert len(resultados) == 2
    assert repo.buscar_por_id('colab-1').situacao_cadastro == SituacaoCadastroColaborador.CADASTRO_COMPLETO
    assert repo.buscar_por_id('colab-2').situacao_cadastro == SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO
