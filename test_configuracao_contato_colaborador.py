"""Testes de `configuracao_contato_colaborador.py` -- mesmo padrão de
`test_configuracao_identidade_colaborador.py`: segredo sempre de
variável de ambiente (nunca hardcoded, nunca inventado), versionamento
obrigatório, chaves Fernet/HMAC sempre separadas."""
import pytest

from magnata_os.documental.alocacao.configuracao_contato_colaborador import (
    SegredoContatoColaboradorAusente,
    carregar_configuracao_segredo_contato,
)


def test_obter_chave_fernet_para_versao_ausente_levanta_erro_nomeado():
    config = carregar_configuracao_segredo_contato(ambiente={})
    with pytest.raises(SegredoContatoColaboradorAusente):
        config.obter_chave_fernet_para_versao('v1')


def test_obter_chave_hmac_para_versao_ausente_levanta_erro_nomeado():
    config = carregar_configuracao_segredo_contato(ambiente={})
    with pytest.raises(SegredoContatoColaboradorAusente):
        config.obter_chave_hmac_para_versao('v1')


def test_versao_atual_ausente_levanta_erro_nomeado():
    config = carregar_configuracao_segredo_contato(ambiente={})
    with pytest.raises(SegredoContatoColaboradorAusente):
        config.versao_atual()


def test_obter_chave_fernet_para_versao_devolve_chave_valida_de_32_bytes_urlsafe():
    import base64
    ambiente = {'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V1': 'segredo-humano-qualquer'}
    config = carregar_configuracao_segredo_contato(ambiente=ambiente)
    chave = config.obter_chave_fernet_para_versao('v1')
    assert isinstance(chave, bytes)
    # Precisa ser aceita pela própria Fernet (formato correto).
    from cryptography.fernet import Fernet
    Fernet(chave)
    assert len(base64.urlsafe_b64decode(chave)) == 32


def test_mesmo_segredo_produz_sempre_a_mesma_chave_fernet_deterministica():
    ambiente = {'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V1': 'segredo-fixo'}
    config = carregar_configuracao_segredo_contato(ambiente=ambiente)
    assert config.obter_chave_fernet_para_versao('v1') == config.obter_chave_fernet_para_versao('v1')


def test_obter_chave_hmac_para_versao_devolve_bytes_do_segredo_bruto():
    ambiente = {'MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_V1': 'segredo-hmac'}
    config = carregar_configuracao_segredo_contato(ambiente=ambiente)
    assert config.obter_chave_hmac_para_versao('v1') == b'segredo-hmac'


def test_chave_fernet_e_chave_hmac_sao_sempre_diferentes_para_mesma_versao():
    """Higiene de separação de chave: nunca a mesma chave serve para
    cifrar e para o hash auxiliar."""
    ambiente = {
        'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V1': 'segredo-unico',
        'MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_V1': 'segredo-unico',
    }
    config = carregar_configuracao_segredo_contato(ambiente=ambiente)
    # Mesmo que o operador configure o MESMO texto para as duas
    # variáveis (erro de configuração plausível), as chaves resultantes
    # nunca são usadas de forma intercambiável -- Fernet deriva via
    # SHA-256+base64, HMAC usa o texto bruto: formatos diferentes,
    # nunca comparáveis/reutilizáveis entre si.
    chave_fernet = config.obter_chave_fernet_para_versao('v1')
    chave_hmac = config.obter_chave_hmac_para_versao('v1')
    assert chave_fernet != chave_hmac


def test_versao_atual_e_atalhos_funcionam_ponta_a_ponta():
    ambiente = {
        'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V2': 'segredo-v2-fernet',
        'MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_V2': 'segredo-v2-hmac',
        'MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL': 'v2',
    }
    config = carregar_configuracao_segredo_contato(ambiente=ambiente)
    assert config.versao_atual() == 'v2'
    assert config.obter_chave_fernet_atual() == config.obter_chave_fernet_para_versao('v2')
    assert config.obter_chave_hmac_atual() == config.obter_chave_hmac_para_versao('v2')


def test_backfill_sob_versao_nova_nao_depende_de_versao_atual():
    """Rotação: consegue obter a chave de uma versão NOVA mesmo sem
    ela estar promovida como 'atual' -- permite backfill antes da
    promoção."""
    ambiente = {
        'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_V3': 'segredo-v3',
        'MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL': 'v1',
    }
    config = carregar_configuracao_segredo_contato(ambiente=ambiente)
    # v3 nao esta promovida, mas ainda pode ser obtida explicitamente.
    assert config.obter_chave_fernet_para_versao('v3') is not None
