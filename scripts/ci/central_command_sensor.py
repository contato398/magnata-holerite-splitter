#!/usr/bin/env python3
"""Sensor da Central Command — primeira versão da atualização automática.

PROBLEMA QUE ISTO RESOLVE (registrado em ORQUESTRADOR.md §6.2): a Central
Command é hoje regenerada por auditoria manual e fica desatualizada no
minuto em que o código muda. Memória consolidada à mão é documentação;
memória que detecta a própria defasagem é o começo de orquestração.

O QUE ISTO É: um sensor read-only. Lê o estado real do repositório, compara
com o instantâneo declarado em ESTADO.json e reporta a divergência.

O QUE ISTO NÃO É, de propósito:
  - não edita nenhum documento da Central Command;
  - não commita, não faz push, não abre PR;
  - não acessa Airtable, Render, WhatsApp, Gmail nem qualquer rede;
  - não é dependência de build, teste ou deploy — nada quebra sem ele;
  - não decide nada. Só mostra onde memória e realidade divergiram.

Reversível por construção: apagar este arquivo e o ESTADO.json não afeta
nenhuma outra parte do repositório.

USO
    python scripts/ci/central_command_sensor.py            # relatório
    python scripts/ci/central_command_sensor.py --json     # saída JSON
    python scripts/ci/central_command_sensor.py --atualizar # regrava o snapshot
    python scripts/ci/central_command_sensor.py --com-testes # inclui pytest

SAÍDA: 0 sem divergência · 1 com divergência · 2 erro de execução.
O código 1 é informativo — NÃO deve reprovar CI por si só, porque
divergência é o estado normal entre auditorias.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = RAIZ / 'docs' / 'magnata-os' / 'central-command' / 'ESTADO.json'
CC = RAIZ / 'docs' / 'magnata-os' / 'central-command'
MESTRE = RAIZ / 'docs' / 'magnata-os' / 'MAGNATA_OS_CENTRAL_COMMAND.md'


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ('git',) + args, cwd=RAIZ, capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception:
        return ''


def _branches_fora_de_main() -> list[str]:
    """Branches remotas que NÃO são ancestrais de origin/main.

    É a métrica que importa: uma branch fora de main é conhecimento que
    pode desaparecer. Foi assim que a fundação documental quase se perdeu.
    """
    fora = []
    for linha in _git('branch', '-r').splitlines():
        b = linha.strip()
        if not b or 'HEAD' in b or b == 'origin/main':
            continue
        r = subprocess.run(
            ('git', 'merge-base', '--is-ancestor', b, 'origin/main'),
            cwd=RAIZ, capture_output=True, timeout=60,
        )
        if r.returncode != 0:
            fora.append(b.replace('origin/', ''))
    return sorted(fora)


def _links_quebrados() -> list[str]:
    """Link relativo de markdown apontando para arquivo inexistente.

    Regra da missão: nenhuma regra oficial pode apontar para o vazio.
    Ignora o que está dentro de bloco de código — senão um `grep` citado
    em documentação vira falso positivo.
    """
    padrao = re.compile(r'\[[^\]]*\]\(([^)#][^)]*)\)')
    alvos = list((RAIZ / 'docs' / 'magnata-os').rglob('*.md'))
    alvos += [RAIZ / 'CLAUDE.md']
    alvos += list(RAIZ.glob('MAGNATA_*.md'))
    quebrados = []
    for f in alvos:
        if not f.exists():
            continue
        dentro = False
        for linha in f.read_text(encoding='utf-8').split('\n'):
            if linha.strip().startswith('```'):
                dentro = not dentro
                continue
            if dentro:
                continue
            for m in padrao.finditer(linha):
                alvo = m.group(1).split('#')[0].strip()
                if not alvo or alvo.startswith(('http', 'mailto:')):
                    continue
                if not (f.parent / alvo).resolve().exists():
                    quebrados.append(f'{f.relative_to(RAIZ)} -> {alvo}')
    return sorted(quebrados)


def _pii_em_documentacao() -> list[str]:
    """CPF formatado em qualquer .md versionado. Regra de CLAUDE.md §6.

    Só CPF: nome próprio não é detectável por regex sem falso positivo em
    massa, e um detector que grita sempre é um detector que ninguém lê.
    """
    cpf = re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b')
    achados = []
    for f in RAIZ.rglob('*.md'):
        if '.git/' in str(f) or 'node_modules' in str(f):
            continue
        try:
            if cpf.search(f.read_text(encoding='utf-8')):
                achados.append(str(f.relative_to(RAIZ)))
        except Exception:
            continue
    return sorted(achados)


def _resultado_testes() -> dict | None:
    r = subprocess.run(
        (sys.executable, '-m', 'pytest', '-q', '--tb=no'),
        cwd=RAIZ, capture_output=True, text=True, timeout=1800,
    )
    m = re.search(r'(?:(\d+) failed,\s*)?(\d+) passed', r.stdout)
    if not m:
        return None
    return {'falhando': int(m.group(1) or 0), 'passando': int(m.group(2))}


def coletar(com_testes: bool = False) -> dict:
    estado = {
        'main_sha': _git('rev-parse', '--short', 'origin/main'),
        'main_assunto': _git('log', '-1', '--format=%s', 'origin/main'),
        'main_data': _git('log', '-1', '--format=%ai', 'origin/main'),
        'branches_fora_de_main': _branches_fora_de_main(),
        'documentos_central_command': sorted(
            p.name for p in CC.glob('*.md')
        ) if CC.exists() else [],
        'links_quebrados': _links_quebrados(),
        'cpf_em_documentacao': _pii_em_documentacao(),
        'workflows': sorted(
            p.name for p in (RAIZ / '.github' / 'workflows').glob('*.yml')
        ) if (RAIZ / '.github' / 'workflows').exists() else [],
        'autorizacoes_app_py': len(list(
            (RAIZ / '.magnata' / 'app-py-authorizations').glob('*.gitblob')
        )) if (RAIZ / '.magnata' / 'app-py-authorizations').exists() else 0,
    }
    if com_testes:
        estado['testes'] = _resultado_testes()
    return estado


def preservar_baseline(novo: dict, anterior: dict) -> tuple[dict, str | None]:
    """Impede que `--atualizar` sem `--com-testes` apague a baseline de testes.

    DEFEITO QUE ISTO CORRIGE: `coletar()` só produz a chave `testes` quando a
    suíte é executada. Gravar esse dicionário por cima do snapshot apagava
    silenciosamente a baseline anterior — e, sem baseline, `comparar()` deixa
    de detectar regressão. Perda silenciosa de dado é exatamente o que
    `CLAUDE.md` §4 proíbe.

    REGRA: não medir os testes significa **"baseline não atualizada"**, nunca
    **"baseline vazia"**. Se a execução atual não mediu e o snapshot anterior
    tinha uma baseline, ela é carregada adiante sem alteração.

    Retorna o snapshot a gravar e, quando houve preservação, um aviso a
    exibir — preservar é correto, mas nunca deve ser silencioso.
    """
    if novo.get('testes') is not None:
        return novo, None
    baseline = anterior.get('testes')
    if baseline is None:
        return novo, None
    preservado = dict(novo)
    preservado['testes'] = baseline
    aviso = (
        f"baseline de testes PRESERVADA do snapshot anterior "
        f"({baseline.get('passando')} passando, {baseline.get('falhando')} "
        f"falhando) — esta execução não rodou a suíte. Use --com-testes para "
        f"remedir; do contrário a baseline segue sendo a da medição anterior."
    )
    return preservado, aviso


def comparar(atual: dict, anterior: dict) -> list[str]:
    """Divergências entre o estado real e o instantâneo declarado.

    Cada item é uma frase acionável, não um dump de diff — quem lê precisa
    saber o que fazer, não decifrar estruturas.
    """
    div = []

    if anterior.get('main_sha') and atual['main_sha'] != anterior['main_sha']:
        div.append(
            f"main avançou: {anterior['main_sha']} -> {atual['main_sha']} "
            f"({atual['main_assunto'][:70]}). A Central Command pode estar "
            f"descrevendo um estado anterior."
        )

    antes = set(anterior.get('branches_fora_de_main') or [])
    agora = set(atual['branches_fora_de_main'])
    for b in sorted(agora - antes):
        div.append(f"branch NOVA fora de main: {b} — conhecimento ainda não incorporado.")
    for b in sorted(antes - agora):
        div.append(f"branch sumiu de fora de main: {b} — foi mesclada ou APAGADA. Confirmar qual.")

    antes_d = set(anterior.get('documentos_central_command') or [])
    agora_d = set(atual['documentos_central_command'])
    for d in sorted(agora_d - antes_d):
        div.append(f"documento novo na Central Command: {d}")
    for d in sorted(antes_d - agora_d):
        div.append(f"documento REMOVIDO da Central Command: {d} — verificar se foi intencional.")

    if atual['links_quebrados']:
        div.append(
            f"{len(atual['links_quebrados'])} link(s) quebrado(s) — regra oficial "
            f"apontando para arquivo inexistente: " + '; '.join(atual['links_quebrados'][:5])
        )

    if atual['cpf_em_documentacao']:
        div.append(
            "CPF encontrado em documentação versionada (CLAUDE.md §6): "
            + ', '.join(atual['cpf_em_documentacao'])
        )

    antes_w = set(anterior.get('workflows') or [])
    agora_w = set(atual['workflows'])
    if antes_w and agora_w != antes_w:
        div.append(f"workflows mudaram: {sorted(antes_w)} -> {sorted(agora_w)}")

    if anterior.get('autorizacoes_app_py') is not None:
        if atual['autorizacoes_app_py'] != anterior['autorizacoes_app_py']:
            div.append(
                f"autorizações de app.py: {anterior['autorizacoes_app_py']} -> "
                f"{atual['autorizacoes_app_py']} — houve alteração no legado protegido."
            )

    t_at, t_an = atual.get('testes'), anterior.get('testes')
    if t_at and t_an:
        if t_at['falhando'] > t_an['falhando']:
            div.append(
                f"REGRESSÃO: falhas {t_an['falhando']} -> {t_at['falhando']}."
            )
        elif t_at['falhando'] < t_an['falhando']:
            div.append(
                f"melhora: falhas {t_an['falhando']} -> {t_at['falhando']} — "
                f"atualizar o snapshot para não mascarar regressão futura."
            )
    elif t_at:
        div.append(f"testes: {t_at['passando']} passando, {t_at['falhando']} falhando (sem base anterior).")

    return div


def main() -> int:
    ap = argparse.ArgumentParser(description='Sensor read-only da Central Command.')
    ap.add_argument('--json', action='store_true', help='saída em JSON')
    ap.add_argument('--atualizar', action='store_true', help='regrava o snapshot')
    ap.add_argument('--com-testes', action='store_true', help='executa a suíte')
    args = ap.parse_args()

    atual = coletar(com_testes=args.com_testes)
    anterior = {}
    if SNAPSHOT.exists():
        try:
            anterior = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        except Exception as exc:
            print(f'ERRO ao ler {SNAPSHOT.name}: {exc}', file=sys.stderr)
            return 2

    divergencias = comparar(atual, anterior) if anterior else []

    if args.atualizar:
        a_gravar, aviso = preservar_baseline(atual, anterior)
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(
            json.dumps(a_gravar, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        print(f'Snapshot atualizado: {SNAPSHOT.relative_to(RAIZ)}')
        if aviso:  # preservar é correto; preservar em silêncio, não
            print(f'  AVISO: {aviso}')

    if args.json:
        print(json.dumps(
            {'estado': atual, 'divergencias': divergencias},
            ensure_ascii=False, indent=2,
        ))
        return 1 if divergencias else 0

    print('SENSOR DA CENTRAL COMMAND')
    print(f"  main            : {atual['main_sha']} — {atual['main_assunto'][:60]}")
    print(f"  branches fora   : {len(atual['branches_fora_de_main'])}")
    print(f"  docs da CC      : {len(atual['documentos_central_command'])}")
    print(f"  links quebrados : {len(atual['links_quebrados'])}")
    print(f"  CPF em doc      : {len(atual['cpf_em_documentacao'])}")
    print(f"  workflows       : {len(atual['workflows'])}")
    print(f"  autoriz. app.py : {atual['autorizacoes_app_py']}")
    if atual.get('testes'):
        t = atual['testes']
        print(f"  testes          : {t['passando']} passando, {t['falhando']} falhando")

    if not anterior:
        print('\nSem snapshot anterior. Rode com --atualizar para criar a linha de base.')
        return 0

    if divergencias:
        print(f'\n{len(divergencias)} DIVERGÊNCIA(S) entre a memória e o estado real:')
        for d in divergencias:
            print(f'  - {d}')
        print('\nDivergência é normal entre auditorias. Não reprova CI por si só.')
        return 1

    print('\nSem divergência: a Central Command descreve o estado atual.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:  # falha nunca silenciosa (CLAUDE.md §4)
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(2)
