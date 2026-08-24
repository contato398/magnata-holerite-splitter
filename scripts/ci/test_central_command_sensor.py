"""Regressão do sensor da Central Command.

Cobre um defeito real, encontrado em uso na Etapa 10: rodar

    python scripts/ci/central_command_sensor.py --atualizar

SEM `--com-testes` gravava um snapshot sem a chave `testes`, apagando
silenciosamente a baseline. Sem baseline, `comparar()` para de detectar
regressão — ou seja, o sensor perdia justamente a função de alarme, e sem
avisar ninguém. `CLAUDE.md` §4: falha nunca é silenciosa.

A regra que estes testes travam: **não medir não é medir zero.**
"""
import importlib.util
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'central_command_sensor', RAIZ / 'scripts' / 'ci' / 'central_command_sensor.py'
)
sensor = importlib.util.module_from_spec(_spec)
sys.modules['central_command_sensor'] = sensor
_spec.loader.exec_module(sensor)

BASELINE = {'passando': 642, 'falhando': 0}


def test_atualizar_sem_medir_preserva_a_baseline():
    """O caso que quebrou: snapshot novo sem `testes`, anterior com baseline."""
    novo = {'main_sha': 'bbbbbbb'}
    anterior = {'main_sha': 'aaaaaaa', 'testes': BASELINE}

    gravar, aviso = sensor.preservar_baseline(novo, anterior)

    assert gravar['testes'] == BASELINE, 'a baseline não pode sumir por omissão'
    assert aviso, 'preservar em silêncio também é falha silenciosa'
    assert '642' in aviso


def test_preservar_nao_muta_o_dicionario_recebido():
    novo = {'main_sha': 'bbbbbbb'}
    gravar, _ = sensor.preservar_baseline(novo, {'testes': BASELINE})
    assert 'testes' not in novo, 'preservar_baseline não pode alterar o argumento'
    assert gravar is not novo


def test_medicao_nova_sobrescreve_a_baseline_antiga():
    """Preservar nunca pode mascarar uma medição real, inclusive pior."""
    novo = {'testes': {'passando': 640, 'falhando': 2}}
    gravar, aviso = sensor.preservar_baseline(novo, {'testes': BASELINE})

    assert gravar['testes'] == {'passando': 640, 'falhando': 2}
    assert aviso is None, 'não há o que avisar quando a suíte foi medida'


def test_sem_baseline_anterior_nao_inventa_nada():
    """Compatibilidade retroativa: snapshot legado sem a chave `testes`."""
    gravar, aviso = sensor.preservar_baseline({'main_sha': 'x'}, {'main_sha': 'w'})

    assert 'testes' not in gravar, 'ausência de baseline não vira baseline vazia'
    assert aviso is None


def test_baseline_preservada_nao_produz_falso_alarme_de_regressao():
    """Fecha o ciclo: o valor preservado atravessa `comparar()` sem ruído."""
    vazio = {
        'main_sha': 'aaaaaaa', 'main_assunto': '', 'branches_fora_de_main': [],
        'documentos_central_command': [], 'links_quebrados': [],
        'cpf_em_documentacao': [], 'workflows': [], 'autorizacoes_app_py': 0,
    }
    anterior = dict(vazio, testes=BASELINE)
    gravar, _ = sensor.preservar_baseline(dict(vazio), anterior)

    divergencias = sensor.comparar(gravar, anterior)

    assert not any('REGRESS' in d.upper() for d in divergencias)
    assert not any('melhora' in d for d in divergencias)


def test_main_atualizar_sem_com_testes_grava_a_baseline_preservada(tmp_path, monkeypatch, capsys):
    """Trava a LIGAÇÃO, não só a função.

    Este teste existe porque a primeira versão da suíte não pegava o defeito:
    todos os casos exercitavam `preservar_baseline()` isolada, então
    desconectá-la de `main()` passava despercebido. Aqui o caminho real de
    gravação é executado de ponta a ponta.
    """
    import json

    snapshot = tmp_path / 'ESTADO.json'
    snapshot.write_text(
        json.dumps({'main_sha': 'aaaaaaa', 'testes': BASELINE}), encoding='utf-8'
    )
    monkeypatch.setattr(sensor, 'SNAPSHOT', snapshot)
    monkeypatch.setattr(sensor, 'RAIZ', tmp_path)
    monkeypatch.setattr(
        sensor, 'coletar',
        lambda com_testes=False: {
            'main_sha': 'bbbbbbb', 'main_assunto': 'novo',
            'branches_fora_de_main': [], 'documentos_central_command': [],
            'links_quebrados': [], 'cpf_em_documentacao': [],
            'workflows': [], 'autorizacoes_app_py': 0,
            'contexto': sensor.medir_contexto.avaliar(),
            'graphify_snapshot_status': 'ausente', 'session_handoff_freshness': 'indeterminado',
        },
    )
    monkeypatch.setattr(sys, 'argv', ['central_command_sensor.py', '--atualizar'])

    sensor.main()

    gravado = json.loads(snapshot.read_text(encoding='utf-8'))
    assert gravado['testes'] == BASELINE, (
        'main() gravou o snapshot sem preservar a baseline — o defeito voltou'
    )
    assert 'AVISO' in capsys.readouterr().out


def test_zero_falhas_e_baseline_valida_e_nao_ausencia():
    """`0 falhando` é falsy em Python — o bug clássico que isto trava."""
    anterior = {'testes': {'passando': 100, 'falhando': 0}}
    gravar, aviso = sensor.preservar_baseline({}, anterior)

    assert gravar['testes']['falhando'] == 0
    assert gravar['testes']['passando'] == 100
    assert aviso is not None


# --- integração com medir_contexto.py e o Orquestrador (Etapa 13) --------
#
# atualizar_auto_fact.executar() (magnata_os/orquestrador/acoes/) chama
# sensor.coletar(com_testes=True) e grava o dicionário inteiro em
# ESTADO.json -- os testes abaixo travam que 'contexto',
# 'graphify_snapshot_status' e 'session_handoff_freshness' sempre estejam
# presentes nesse dicionário, porque é esse o único fio que liga esta
# medição ao Grande Orquestrador.

def test_coletar_real_inclui_o_bloco_de_contexto():
    """Contra o repositório de verdade -- não mockado."""
    atual = sensor.coletar(com_testes=False)

    assert 'contexto' in atual
    assert atual['contexto']['status_contexto'] in ('NORMAL', 'ATENCAO', 'TROCAR_SESSAO')
    assert atual['graphify_snapshot_status'] in ('ausente', 'desatualizado', 'sem_sinal_de_mudanca')
    assert atual['session_handoff_freshness'] in ('ausente', 'atual', 'desatualizado', 'indeterminado')


def test_graphify_snapshot_status_ausente_quando_snapshot_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    assert sensor._graphify_snapshot_status() == 'ausente'


def test_graphify_snapshot_status_desatualizado_quando_arquivo_listado_sumiu(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    monkeypatch.setattr(sensor, 'RAIZ', tmp_path)
    (tmp_path / 'ARQUITETURA_SNAPSHOT.json').write_text(
        json.dumps({'arquivos': ['nao_existe_mais.py']}), encoding='utf-8'
    )
    assert sensor._graphify_snapshot_status() == 'desatualizado'


def test_graphify_snapshot_status_sem_sinal_quando_arquivos_listados_existem(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    monkeypatch.setattr(sensor, 'RAIZ', tmp_path)
    presente = tmp_path / 'existe.py'
    presente.write_text('# ok', encoding='utf-8')
    (tmp_path / 'ARQUITETURA_SNAPSHOT.json').write_text(
        json.dumps({'arquivos': ['existe.py']}), encoding='utf-8'
    )
    assert sensor._graphify_snapshot_status() == 'sem_sinal_de_mudanca'


def test_session_handoff_freshness_ausente_sem_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    assert sensor._session_handoff_freshness('abc1234') == 'ausente'


def test_session_handoff_freshness_atual_quando_sha_bate(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    (tmp_path / 'HANDOFF.md').write_text('| **`main`** | `abc1234` — teste |', encoding='utf-8')
    assert sensor._session_handoff_freshness('abc1234') == 'atual'


def test_session_handoff_freshness_desatualizado_quando_sha_diverge(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    (tmp_path / 'HANDOFF.md').write_text('| **`main`** | `1409454` — teste |', encoding='utf-8')
    assert sensor._session_handoff_freshness('76b0046') == 'desatualizado'


def test_session_handoff_freshness_indeterminado_quando_formato_nao_bate(tmp_path, monkeypatch):
    monkeypatch.setattr(sensor, 'CC', tmp_path)
    (tmp_path / 'HANDOFF.md').write_text('sem tabela nenhuma aqui', encoding='utf-8')
    assert sensor._session_handoff_freshness('76b0046') == 'indeterminado'
