"""Testes de `configuracao_identidade_colaborador.py` -- segredo lido
de ambiente injetado (nunca o `os.environ` real do processo de teste),
falha explícita quando ausente, e suporte a rotação (backfill sob
versão nova antes de promover CURRENT)."""
import pytest

from magnata_os.documental.alocacao.configuracao_identidade_colaborador import (
    SegredoIdentidadeColaboradorAusente,
    carregar_configuracao_segredo,
)


def test_obter_chave_para_versao_le_variavel_correta():
    ambiente = {'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_CHAVE_V1': 'segredo-v1'}
    config = carregar_configuracao_segredo(ambiente)

    assert config.obter_chave_para_versao('v1') == b'segredo-v1'


def test_obter_chave_para_versao_e_case_insensitive_no_sufixo():
    ambiente = {'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_CHAVE_V2': 'segredo-v2'}
    config = carregar_configuracao_segredo(ambiente)

    assert config.obter_chave_para_versao('v2') == b'segredo-v2'


def test_obter_chave_para_versao_ausente_levanta_excecao_dedicada():
    config = carregar_configuracao_segredo({})

    with pytest.raises(SegredoIdentidadeColaboradorAusente):
        config.obter_chave_para_versao('v1')


def test_obter_chave_para_versao_rejeita_versao_vazia():
    config = carregar_configuracao_segredo({})
    with pytest.raises(ValueError):
        config.obter_chave_para_versao('')


def test_versao_atual_le_variavel_dedicada():
    ambiente = {'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL': 'v1'}
    config = carregar_configuracao_segredo(ambiente)

    assert config.versao_atual() == 'v1'


def test_versao_atual_ausente_levanta_excecao_dedicada():
    config = carregar_configuracao_segredo({})
    with pytest.raises(SegredoIdentidadeColaboradorAusente):
        config.versao_atual()


def test_obter_chave_atual_combina_versao_atual_e_chave_correspondente():
    ambiente = {
        'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL': 'v1',
        'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_CHAVE_V1': 'segredo-v1',
    }
    config = carregar_configuracao_segredo(ambiente)

    assert config.obter_chave_atual() == b'segredo-v1'


def test_rotacao_backfill_sob_versao_nova_antes_de_promover_current():
    """Cenário de rotação exigido pela autorização: a chave da versão
    NOVA (v2) já está configurada e pode ser lida explicitamente para
    backfill, MESMO enquanto a variável de versão atual ainda aponta
    para v1 -- promoção (mudar VERSAO_ATUAL) é um passo separado,
    posterior, nunca implícito."""
    ambiente = {
        'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL': 'v1',
        'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_CHAVE_V1': 'segredo-v1',
        'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_CHAVE_V2': 'segredo-v2',
    }
    config = carregar_configuracao_segredo(ambiente)

    # Backfill explícito sob a versão nova -- nunca depende de versao_atual().
    chave_para_backfill = config.obter_chave_para_versao('v2')
    assert chave_para_backfill == b'segredo-v2'

    # Antes da promoção, a chave ATUAL continua sendo a v1.
    assert config.obter_chave_atual() == b'segredo-v1'

    # Promoção = mudar a variável de ambiente (simulada aqui por um
    # novo carregamento com o valor já trocado) -- nunca uma chamada de
    # método deste objeto, nunca um estado mutável em memória.
    ambiente_promovido = dict(ambiente, MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL='v2')
    config_promovida = carregar_configuracao_segredo(ambiente_promovido)
    assert config_promovida.obter_chave_atual() == b'segredo-v2'


def test_carregar_configuracao_segredo_sem_ambiente_usa_os_environ(monkeypatch):
    monkeypatch.setenv('MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL', 'v9')
    config = carregar_configuracao_segredo()
    assert config.versao_atual() == 'v9'
