"""Regressão da medição de contexto e do alerta de 3 estados.

Cobre coisas que o script promete e que não podem regredir em silêncio
(CLAUDE.md §4):

1. bootstrap ausente é ERRO (2), nunca "0 chars" silencioso;
2. classificação NORMAL/ATENCAO/TROCAR_SESSAO é só aritmética sobre o
   TIER 0 medido — nunca inventa "tokens reais de sessão";
3. as três camadas são cumulativas (TIER 0 ⊆ TIER 1 ⊆ TIER 2) contra o
   estado real do repositório — trava a integração, não só a função
   isolada, do mesmo jeito que `test_central_command_sensor.py` faz para
   o sensor;
4. `avaliar()` é o contrato que `central_command_sensor.py` consome para
   popular `ESTADO.json['contexto']` — sua forma não pode mudar em
   silêncio.
"""
import importlib.util
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'medir_contexto', RAIZ / 'scripts' / 'ci' / 'medir_contexto.py'
)
medir = importlib.util.module_from_spec(_spec)
sys.modules['medir_contexto'] = medir
_spec.loader.exec_module(medir)


def test_bootstrap_real_existe_e_tem_as_tres_partes():
    """Contra o repositório de verdade: HANDOFF/ESTADO/INDEX precisam existir."""
    resultado = medir._medir(medir.TIER0)
    assert not resultado['faltando'], resultado['faltando']
    assert len(resultado['arquivos']) == 3
    assert resultado['chars'] > 0


def test_tier0_esta_contido_em_tier1_no_corpus_real():
    """TIER 1 nunca pode ser menor que TIER 0 — é TIER 0 mais 5 arquivos."""
    estado = medir.coletar()
    t0 = estado['tier0_bootstrap_minimo']['chars']
    t1 = estado['tier1_onboarding_completo']['chars']
    t2 = estado['tier2_corpus_total']['chars']
    assert t0 <= t1 <= t2, 'as camadas deixaram de ser cumulativas'


def test_razao_tier0_e_pequena_no_repositorio_real():
    """Confirma numericamente a promessa de HANDOFF.md: contexto mínimo primeiro.

    Não trava um número exato (o corpus cresce) — trava a promessa: o
    bootstrap fica bem abaixo do corpus total, nunca próximo dele.
    """
    estado = medir.coletar()
    assert estado['razao_tier0_sobre_total'] < 0.20, (
        'TIER 0 deixou de ser "mínimo" frente ao corpus — revisar o que mudou'
    )


def test_bootstrap_ausente_e_erro_nao_zero_silencioso(monkeypatch):
    """Falha nunca é silenciosa: bootstrap sumido tem que gritar, não medir 0."""
    monkeypatch.setattr(medir, 'TIER0', [pathlib.Path('/caminho/que/nao/existe.md')])
    monkeypatch.setattr(sys, 'argv', ['medir_contexto.py'])

    codigo = medir.main()

    assert codigo == 2, 'bootstrap ausente precisa retornar erro, não 0'


def test_classificar_status_normal_dentro_dos_dois_limites():
    assert medir.classificar_status(100, limite_atencao=8000, limite_trocar=12000) == medir.NORMAL


def test_classificar_status_atencao_entre_os_dois_limites():
    assert medir.classificar_status(9000, limite_atencao=8000, limite_trocar=12000) == medir.ATENCAO


def test_classificar_status_trocar_sessao_acima_do_limite_maior():
    assert medir.classificar_status(13000, limite_atencao=8000, limite_trocar=12000) == medir.TROCAR_SESSAO


def test_classificar_status_e_so_aritmetica_sem_estado_escondido():
    """Mesma entrada, mesma saída — nada de scoring, nada de estado global."""
    a = medir.classificar_status(9000, 8000, 12000)
    b = medir.classificar_status(9000, 8000, 12000)
    assert a == b == medir.ATENCAO


def test_avaliar_inclui_status_e_mensagem_normal():
    estado = medir.avaliar(limite_atencao=1_000_000, limite_trocar=2_000_000)
    assert estado['status_contexto'] == medir.NORMAL
    assert estado['mensagem'] is None
    assert 'medido_em' in estado


def test_avaliar_produz_mensagem_de_trocar_sessao_quando_estoura_o_limite():
    estado = medir.avaliar(limite_atencao=1, limite_trocar=2)
    assert estado['status_contexto'] == medir.TROCAR_SESSAO
    assert estado['mensagem'] == medir.MENSAGEM_TROCAR_SESSAO


def test_cli_saida_normal_e_codigo_0(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['medir_contexto.py', '--limite-tier0-tokens', '1000000',
                                       '--limite-trocar-sessao-tokens', '2000000'])
    codigo = medir.main()
    saida = capsys.readouterr().out
    assert codigo == 0
    assert 'STATUS: NORMAL' in saida
    assert 'ALERTA' not in saida


def test_cli_saida_atencao_e_codigo_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['medir_contexto.py', '--limite-tier0-tokens', '1',
                                       '--limite-trocar-sessao-tokens', '2000000'])
    codigo = medir.main()
    saida = capsys.readouterr().out
    assert codigo == 1
    assert 'STATUS: ATENCAO' in saida
    assert 'ALERTA' in saida


def test_cli_saida_trocar_sessao_e_codigo_3_com_mensagem_exata(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['medir_contexto.py', '--limite-tier0-tokens', '1',
                                       '--limite-trocar-sessao-tokens', '2'])
    codigo = medir.main()
    saida = capsys.readouterr().out
    assert codigo == 3
    assert 'STATUS: TROCAR_SESSAO' in saida
    assert medir.MENSAGEM_TROCAR_SESSAO in saida


def test_saida_json_tem_as_chaves_que_o_relatorio_promete(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['medir_contexto.py', '--json'])

    medir.main()

    dado = json.loads(capsys.readouterr().out)
    for chave in (
        'tier0_bootstrap_minimo', 'tier1_onboarding_completo', 'tier2_corpus_total',
        'razao_tier0_sobre_total', 'razao_tier1_sobre_total',
        'limite_atencao_tokens', 'limite_trocar_sessao_tokens',
        'status_contexto', 'mensagem', 'medido_em',
    ):
        assert chave in dado, f'chave {chave} sumiu da saída --json'
