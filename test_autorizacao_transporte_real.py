"""Gate fail-closed de três barreiras independentes -- as 10 combinações
obrigatórias da missão de ativação, mais a prova estática do default.
"""
import inspect
from unittest.mock import patch

import pytest

from magnata_os.orquestrador.autorizacao_transporte_real import (
    NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL,
    transporte_real_habilitado,
)


def _com_env(valor):
    if valor is None:
        return patch.dict('os.environ', {}, clear=False)
    return patch.dict('os.environ', {NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL: valor})


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
            'magnata_os.orquestrador.autorizacao_transporte_real.deve_rodar_em_dry_run',
            return_value=dry_run,
        ):
            resultado = transporte_real_habilitado(autorizar_transporte_real=codigo)
    assert resultado is esperado, descricao


def test_todas_as_variaveis_ausentes_e_fake_10():
    """10. todas as variáveis ausentes -> fake (default seguro de um
    deploy novo, limpo, sem nenhuma configuração operacional feita)."""
    with _sem_env():
        with patch(
            'magnata_os.orquestrador.autorizacao_transporte_real.deve_rodar_em_dry_run',
            return_value=False,
        ):
            assert transporte_real_habilitado(autorizar_transporte_real=False) is False


def test_default_do_ponto_de_composicao_e_false_literal():
    """Prova estática: o parâmetro é False por padrão -- nunca derivado
    de variável de ambiente no próprio ponto de composição."""
    assinatura = inspect.signature(transporte_real_habilitado)
    assert assinatura.parameters['autorizar_transporte_real'].default is inspect.Parameter.empty
    # autorizar_transporte_real é obrigatório (sem default) NESTA função --
    # é o chamador (ciclo_producao_v1) quem fixa o default False; ver
    # test_ciclo_producao_v1.py::test_autorizar_transporte_real_default_false.


def test_valor_exato_1_e_o_unico_que_habilita_a_barreira_operacional():
    from magnata_os.orquestrador.autorizacao_transporte_real import (
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
    import magnata_os.orquestrador.autorizacao_transporte_real as modulo
    from magnata_os.orquestrador.configuracao import deve_rodar_em_dry_run
    assert modulo.deve_rodar_em_dry_run is deve_rodar_em_dry_run


def test_veto_vence_mesmo_com_as_duas_outras_barreiras_abertas():
    with _sem_env():
        import os
        os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = '1'
        with patch(
            'magnata_os.orquestrador.autorizacao_transporte_real.deve_rodar_em_dry_run',
            return_value=True,
        ):
            assert transporte_real_habilitado(autorizar_transporte_real=True) is False
