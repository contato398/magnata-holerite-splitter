"""CLI `scripts/determinar_local_trabalho_colaborador_cli.py`. Cobre:
caminho feliz, colaborador inexistente, colaborador já com local
definido (recusa sem --motivo-correcao, aceita com), e
ConfiguracaoBancoAusente quando DATABASE_URL não está configurada.
Dados 100% sintéticos."""
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import pytest

from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    CadastroColaboradorError,
    Colaborador,
    EventoCorrecaoLocalTrabalho,
    LocalTrabalhoJaDefinidoError,
    SituacaoCadastroColaborador,
)
from scripts.determinar_local_trabalho_colaborador_cli import determinar_local_trabalho, main

CPF_SINTETICO = '900.000.000-01'
NOME_SINTETICO = 'colaborador sintetico teste'
_AGORA = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


class _RepositorioColaboradoresEmMemoria:
    def __init__(self, colaboradores=()) -> None:
        self._por_id: Dict[str, Colaborador] = {c.colaborador_id: c for c in colaboradores}
        self.historico_correcoes: list = []

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
        # Dublê append-only: só adiciona -- nunca edita/remove um evento
        # já registrado (mesma disciplina do adapter Postgres real).
        self.historico_correcoes.append(evento)
        return evento

    def listar_historico_correcao_local_trabalho(
        self, colaborador_id: str,
    ) -> Tuple[EventoCorrecaoLocalTrabalho, ...]:
        return tuple(e for e in self.historico_correcoes if e.colaborador_id == colaborador_id)


def _pendente(colaborador_id='colab-1'):
    return Colaborador(
        colaborador_id=colaborador_id, cpf=CPF_SINTETICO, nome=NOME_SINTETICO,
        situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
    )


def _completo(colaborador_id='colab-1', local_trabalho='Escala A - Dias Pares'):
    return Colaborador(
        colaborador_id=colaborador_id, cpf=CPF_SINTETICO, nome=NOME_SINTETICO,
        situacao_cadastro=SituacaoCadastroColaborador.CADASTRO_COMPLETO, local_trabalho=local_trabalho,
    )


# ---- determinar_local_trabalho (núcleo testável) ----

def test_caminho_feliz_completa_cadastro_pendente():
    repo = _RepositorioColaboradoresEmMemoria([_pendente()])
    persistido, evento = determinar_local_trabalho(
        repo, colaborador_id='colab-1', local_trabalho='Escala A - Dias Pares',
        determinado_por='operador.rh@magnataservicos.com.br', agora=_AGORA,
    )
    assert persistido.situacao_cadastro == SituacaoCadastroColaborador.CADASTRO_COMPLETO
    assert persistido.local_trabalho == 'Escala A - Dias Pares'
    assert evento is None


def test_colaborador_inexistente_e_recusado():
    repo = _RepositorioColaboradoresEmMemoria([])
    with pytest.raises(CadastroColaboradorError):
        determinar_local_trabalho(
            repo, colaborador_id='colab-fantasma', local_trabalho='Escala A',
            determinado_por='operador.rh@magnataservicos.com.br', agora=_AGORA,
        )


def test_local_trabalho_ja_definido_sem_motivo_e_recusado():
    repo = _RepositorioColaboradoresEmMemoria([_completo()])
    with pytest.raises(LocalTrabalhoJaDefinidoError):
        determinar_local_trabalho(
            repo, colaborador_id='colab-1', local_trabalho='Escala B - Dias Impares',
            determinado_por='operador.rh@magnataservicos.com.br', agora=_AGORA,
        )
    # nenhuma escrita deve ter acontecido
    assert repo.buscar_por_id('colab-1').local_trabalho == 'Escala A - Dias Pares'


def test_local_trabalho_ja_definido_com_motivo_e_corrigido():
    repo = _RepositorioColaboradoresEmMemoria([_completo()])
    persistido, evento = determinar_local_trabalho(
        repo, colaborador_id='colab-1', local_trabalho='Escala B - Dias Impares',
        determinado_por='operador.rh@magnataservicos.com.br',
        motivo_correcao='Colaborador transferido de posto', agora=_AGORA,
    )
    assert persistido.local_trabalho == 'Escala B - Dias Impares'
    assert evento is not None
    assert evento.motivo_correcao == 'Colaborador transferido de posto'


def test_correcao_grava_evento_no_historico_append_only():
    """Item 2 da correção do PR #215: a correção não vai só para log --
    também é registrada na tabela/mecanismo append-only, via o método
    novo da porta `RepositorioColaboradores`."""
    repo = _RepositorioColaboradoresEmMemoria([_completo()])
    determinar_local_trabalho(
        repo, colaborador_id='colab-1', local_trabalho='Escala B - Dias Impares',
        determinado_por='operador.rh@magnataservicos.com.br',
        motivo_correcao='Colaborador transferido de posto', agora=_AGORA,
    )

    historico = repo.listar_historico_correcao_local_trabalho('colab-1')
    assert len(historico) == 1
    assert historico[0].local_trabalho_anterior == 'Escala A - Dias Pares'
    assert historico[0].local_trabalho_novo == 'Escala B - Dias Impares'
    assert historico[0].motivo_correcao == 'Colaborador transferido de posto'
    assert historico[0].determinado_por == 'operador.rh@magnataservicos.com.br'


def test_determinacao_normal_sem_correcao_nao_grava_historico():
    """Preencher um `local_trabalho` ainda `None` não é correção --
    nenhum evento deve ir para o histórico append-only (mesmo critério
    já validado no domínio: só correção real gera evento)."""
    repo = _RepositorioColaboradoresEmMemoria([_pendente()])
    determinar_local_trabalho(
        repo, colaborador_id='colab-1', local_trabalho='Escala A - Dias Pares',
        determinado_por='operador.rh@magnataservicos.com.br', agora=_AGORA,
    )

    assert repo.listar_historico_correcao_local_trabalho('colab-1') == ()


# ---- main(): ConfiguracaoBancoAusente (fail-closed sem DATABASE_URL) ----

def test_main_sem_database_url_falha_limpo(monkeypatch, capsys):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    codigo = main([
        '--colaborador-id', 'colab-1',
        '--local-trabalho', 'Escala A - Dias Pares',
        '--determinado-por', 'operador.rh@magnataservicos.com.br',
    ])
    assert codigo == 1
    saida = capsys.readouterr()
    assert 'DATABASE_URL' in saida.err
