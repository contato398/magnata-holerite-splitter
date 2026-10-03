"""Gate fail-closed de três barreiras independentes para o cutover do
reenvio do pacote Holerite+Ponto -- mesmo padrão de
test_autorizacao_transporte_real.py, adaptado ao gate novo.
"""
import inspect
from unittest.mock import patch

import pytest

from magnata_os.orquestrador.autorizacao_reenvio_pacote_real import (
    NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL,
    reenvio_pacote_via_orquestrador_habilitado,
)


def _sem_env():
    import os
    ambiente = dict(os.environ)
    ambiente.pop(NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL, None)
    return patch.dict('os.environ', ambiente, clear=True)


@pytest.mark.parametrize('codigo,env,dry_run,esperado,descricao', [
    (False, None, False, False, '1. código False + qualquer env -> fake'),
    (False, '1', False, False, '1b. código False + env=1 ainda assim -> fake'),
    (True, None, False, False, '2. código True + env ausente -> fake'),
    (True, '0', False, False, '3. código True + env "0" -> fake'),
    (True, 'true', False, False, '4. código True + env "true" -> fake'),
    (True, 'yes', False, False, '5. código True + env "yes" -> fake'),
    (True, '01', False, False, '6. código True + env "01" -> fake'),
    (True, ' 1', False, False, '7. código True + env " 1" -> fake'),
    (True, '1', True, False, '8. código True + env "1" + dry-run ativo -> fake'),
    (True, '1', False, True, '9. código True + env "1" + dry-run inativo -> REAL'),
])
def test_combinacoes_obrigatorias(codigo, env, dry_run, esperado, descricao):
    with _sem_env():
        if env is not None:
            import os
            os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = env
        with patch(
            'magnata_os.orquestrador.autorizacao_reenvio_pacote_real.deve_rodar_em_dry_run',
            return_value=dry_run,
        ):
            resultado = reenvio_pacote_via_orquestrador_habilitado(
                autorizar_reenvio_via_orquestrador=codigo,
            )
    assert resultado is esperado, descricao


def test_todas_as_variaveis_ausentes_e_fake_10():
    """10. todas as variáveis ausentes -> fake (default seguro de um
    deploy novo, limpo, sem nenhuma configuração operacional feita)."""
    with _sem_env():
        with patch(
            'magnata_os.orquestrador.autorizacao_reenvio_pacote_real.deve_rodar_em_dry_run',
            return_value=False,
        ):
            assert reenvio_pacote_via_orquestrador_habilitado(
                autorizar_reenvio_via_orquestrador=False,
            ) is False


def test_default_do_ponto_de_composicao_e_obrigatorio_nunca_implicito():
    """Prova estática: o parâmetro não tem default nesta função -- é o
    chamador (futuro ponto de composição em app.py) quem fixa False,
    nunca deriva de variável de ambiente aqui."""
    assinatura = inspect.signature(reenvio_pacote_via_orquestrador_habilitado)
    assert (
        assinatura.parameters['autorizar_reenvio_via_orquestrador'].default
        is inspect.Parameter.empty
    )


def test_valor_exato_1_e_o_unico_que_habilita_a_barreira_operacional():
    from magnata_os.orquestrador.autorizacao_reenvio_pacote_real import (
        _autorizacao_operacional_explicita,
    )
    invalidos = ['0', 'true', 'True', 'TRUE', 'yes', '01', ' 1', '1 ', '1.0', 'on', '']
    with _sem_env():
        for valor in invalidos:
            import os
            os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = valor
            assert _autorizacao_operacional_explicita() is False, valor
        os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = '1'
        assert _autorizacao_operacional_explicita() is True


def test_deve_rodar_em_dry_run_e_reaproveitada_nao_reimplementada():
    """Garante que a semântica histórica de configuracao.py nunca é
    duplicada aqui -- qualquer correção futura naquele módulo se propaga
    automaticamente."""
    import magnata_os.orquestrador.autorizacao_reenvio_pacote_real as modulo
    from magnata_os.orquestrador.configuracao import deve_rodar_em_dry_run
    assert modulo.deve_rodar_em_dry_run is deve_rodar_em_dry_run


def test_veto_vence_mesmo_com_as_duas_outras_barreiras_abertas():
    with _sem_env():
        import os
        os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = '1'
        with patch(
            'magnata_os.orquestrador.autorizacao_reenvio_pacote_real.deve_rodar_em_dry_run',
            return_value=True,
        ):
            assert reenvio_pacote_via_orquestrador_habilitado(
                autorizar_reenvio_via_orquestrador=True,
            ) is False
