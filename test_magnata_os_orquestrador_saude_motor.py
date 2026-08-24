"""
Testes de saude e metricas do motor Orquestrador.

Verifica:
- Rastreamento de eventos por estado
- Calculo de taxas e saude
- Estado verde/amarelo/vermelho
"""
import pytest

from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.saude_motor import EstadoSaudemotor, MonitorSaudemotor


class TestMonitorSaudemotor:
    """Testes do monitor de saude."""

    def test_saude_inicial_verde_sem_eventos(self):
        """Monitor comeca em VERDE sem eventos processados."""
        monitor = MonitorSaudemotor()
        saude = monitor.obter_saude()

        assert saude.saude == 'VERDE'
        assert saude.eventos_processados_total == 0
        assert saude.taxa_sucesso == 0.0

    def test_registrar_sucesso_incrementa_contador(self):
        """Registrar sucesso incrementa eventos_sucesso."""
        monitor = MonitorSaudemotor()

        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)

        saude = monitor.obter_saude()
        assert saude.eventos_processados_total == 2
        assert saude.eventos_sucesso == 2

    def test_taxa_sucesso_calcula_corretamente(self):
        """Taxa de sucesso = sucesso / total."""
        monitor = MonitorSaudemotor()

        # 2 sucessos, 2 falhas = 50% sucesso
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_RETRYABLE)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_RETRYABLE)

        saude = monitor.obter_saude()
        assert saude.taxa_sucesso == 0.5

    def test_taxa_erro_permanente_calcula_corretamente(self):
        """Taxa de erro permanente = falha_final / total."""
        monitor = MonitorSaudemotor()

        # 1 sucesso, 1 falha perm, 1 retry, 1 gate = 25% erro perm
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_FINAL)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_RETRYABLE)
        monitor.registrar_evento_estado(EstadoExecucao.WAITING_GATE)

        saude = monitor.obter_saude()
        assert saude.taxa_erro_permanente == 0.25

    def test_saude_verde_bom_percentual(self):
        """Saude VERDE quando >60% sucesso e <30% erro perm."""
        monitor = MonitorSaudemotor()

        # 80% sucesso, 5% erro perm = VERDE
        for _ in range(8):
            monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_FINAL)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_RETRYABLE)

        saude = monitor.obter_saude()
        assert saude.saude == 'VERDE'

    def test_saude_amarelo_sucesso_baixo(self):
        """Saude AMARELO quando <60% sucesso."""
        monitor = MonitorSaudemotor()

        # 50% sucesso
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_RETRYABLE)

        saude = monitor.obter_saude()
        assert saude.saude == 'AMARELO'

    def test_saude_vermelho_erro_alto(self):
        """Saude VERMELHO quando >30% erro permanente."""
        monitor = MonitorSaudemotor()

        # 40% erro perm
        for _ in range(3):
            monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_FINAL)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_FINAL)

        saude = monitor.obter_saude()
        assert saude.saude == 'VERMELHO'

    def test_contabiliza_todos_estados(self):
        """Todos os estados sao contabilizados corretamente."""
        monitor = MonitorSaudemotor()

        estados_esperados = {
            EstadoExecucao.SUCCEEDED: 'sucesso',
            EstadoExecucao.FAILED_RETRYABLE: 'falha_retentavel',
            EstadoExecucao.FAILED_FINAL: 'falha_final',
            EstadoExecucao.WAITING_GATE: 'gate_humano',
            EstadoExecucao.IGNORED: 'ignorado',
        }

        for estado in estados_esperados.keys():
            monitor.registrar_evento_estado(estado)

        saude = monitor.obter_saude()
        assert saude.eventos_processados_total == 5
        assert saude.eventos_sucesso == 1
        assert saude.eventos_falha_retentavel == 1
        assert saude.eventos_falha_final == 1
        assert saude.eventos_gate_humano == 1
        assert saude.eventos_ignorados == 1

    def test_registra_multiplos_eventos_mesmo_tipo(self):
        """Registrar multiplos eventos do mesmo tipo incrementa corretamente."""
        monitor = MonitorSaudemotor()

        for _ in range(5):
            monitor.registrar_evento_estado(EstadoExecucao.FAILED_FINAL)

        saude = monitor.obter_saude()
        assert saude.eventos_falha_final == 5
        assert saude.taxa_erro_permanente == 1.0

    def test_resetar_limpa_contadores(self):
        """Resetar zera todos os contadores."""
        monitor = MonitorSaudemotor()

        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.FAILED_FINAL)

        monitor.resetar()
        saude = monitor.obter_saude()

        assert saude.eventos_processados_total == 0
        assert saude.eventos_sucesso == 0
        assert saude.eventos_falha_final == 0
        assert saude.saude == 'VERDE'

    def test_taxa_gate_humano_calcula_corretamente(self):
        """Taxa de gate humano = gate / total."""
        monitor = MonitorSaudemotor()

        # 2 success, 3 gate = 60% gate
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.SUCCEEDED)
        monitor.registrar_evento_estado(EstadoExecucao.WAITING_GATE)
        monitor.registrar_evento_estado(EstadoExecucao.WAITING_GATE)
        monitor.registrar_evento_estado(EstadoExecucao.WAITING_GATE)

        saude = monitor.obter_saude()
        assert saude.taxa_gate_humano == 0.6

    def test_resumo_json_serializa_corretamente(self):
        """resumo_json() serializa EstadoSaudemotor."""
        saude = EstadoSaudemotor(
            eventos_processados_total=10,
            eventos_sucesso=8,
            eventos_falha_retentavel=1,
            eventos_falha_final=1,
            eventos_gate_humano=0,
            eventos_ignorados=0,
            taxa_sucesso=0.8,
            taxa_erro_permanente=0.1,
            taxa_gate_humano=0.0,
            saude='VERDE',
        )

        resumo = saude.resumo_json()

        assert resumo['eventos_processados_total'] == 10
        assert resumo['eventos_sucesso'] == 8
        assert resumo['taxa_sucesso'] == 0.8
        assert resumo['saude'] == 'VERDE'
        assert isinstance(resumo, dict)

    def test_estado_saude_e_immutable(self):
        """EstadoSaudemotor e dataclass immutable."""
        saude = EstadoSaudemotor(
            eventos_processados_total=1,
            eventos_sucesso=1,
            eventos_falha_retentavel=0,
            eventos_falha_final=0,
            eventos_gate_humano=0,
            eventos_ignorados=0,
            taxa_sucesso=1.0,
            taxa_erro_permanente=0.0,
            taxa_gate_humano=0.0,
            saude='VERDE',
        )

        # Tentar modificar deve falhar
        with pytest.raises(AttributeError):
            saude.eventos_sucesso = 2
