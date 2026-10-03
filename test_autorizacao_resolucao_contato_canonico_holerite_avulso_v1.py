"""Gate fail-closed de duas barreiras independentes -- mesma disciplina
de `test_autorizacao_transporte_real.py`, sem a barreira de dry-run
(que não existe aqui, ver docstring do módulo)."""
import inspect
from unittest.mock import patch

import pytest

from magnata_os.orquestrador.autorizacao_resolucao_contato_canonico_holerite_avulso_v1 import (
    NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL,
    resolucao_contato_canonico_holerite_avulso_habilitada,
)


def _sem_env():
    import os
    ambiente = dict(os.environ)
    ambiente.pop(NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL, None)
    return patch.dict('os.environ', ambiente, clear=True)


@pytest.mark.parametrize('codigo,env,esperado,descricao', [
    (False, None, False, '1. código False + env ausente -> desabilitado'),
    (False, '1', False, '2. código False + env=1 ainda assim -> desabilitado'),
    (True, None, False, '3. código True + env ausente -> desabilitado'),
    (True, '0', False, '4. código True + env "0" -> desabilitado'),
    (True, 'true', False, '5. código True + env "true" -> desabilitado'),
    (True, 'yes', False, '6. código True + env "yes" -> desabilitado'),
    (True, '01', False, '7. código True + env "01" -> desabilitado'),
    (True, ' 1', False, '8. código True + env " 1" -> desabilitado'),
    (True, '1', True, '9. código True + env "1" -> HABILITADO'),
])
def test_combinacoes_obrigatorias(codigo, env, esperado, descricao):
    with _sem_env():
        if env is not None:
            import os
            os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = env
        resultado = resolucao_contato_canonico_holerite_avulso_habilitada(
            autorizar_resolucao_contato_canonico=codigo,
        )
    assert resultado is esperado, descricao


def test_default_do_ponto_de_composicao_e_obrigatorio_sem_default_de_ambiente():
    """Prova estática: o parâmetro não tem default implícito -- é o
    chamador (o diff proposto em app.py) quem fixa literalmente `False`,
    nunca derivado de variável de ambiente no próprio ponto de
    composição."""
    assinatura = inspect.signature(resolucao_contato_canonico_holerite_avulso_habilitada)
    assert (
        assinatura.parameters['autorizar_resolucao_contato_canonico'].default
        is inspect.Parameter.empty
    )


def test_valor_exato_1_e_o_unico_que_habilita_a_barreira_operacional():
    from magnata_os.orquestrador.autorizacao_resolucao_contato_canonico_holerite_avulso_v1 import (
        _autorizacao_operacional_explicita,
    )
    invalidos = ['0', 'true', 'True', 'TRUE', 'yes', '01', ' 1', '1 ', '1.0', 'on', '']
    with _sem_env():
        import os
        for valor in invalidos:
            os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = valor
            assert _autorizacao_operacional_explicita() is False, valor
        os.environ[NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL] = '1'
        assert _autorizacao_operacional_explicita() is True


def test_todas_as_variaveis_ausentes_e_desabilitado():
    """Default seguro de um deploy novo, limpo, sem nenhuma configuração
    operacional feita."""
    with _sem_env():
        assert resolucao_contato_canonico_holerite_avulso_habilitada(
            autorizar_resolucao_contato_canonico=False,
        ) is False
