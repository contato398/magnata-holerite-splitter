#!/usr/bin/env python3
"""Medição de contexto — quanto custa ler a Central Command, por camada.

Princípio: medir o bootstrap sem fazer a própria telemetria inflar o objeto
medido. `ESTADO.json` contém o AUTO_FACT `contexto`; ao medir esse arquivo,
esse bloco é removido apenas da representação usada para a medição. O arquivo
real não é alterado. Assim evitamos realimentação: medir -> persistir métricas
-> ESTADO cresce -> medir mais -> persistir ainda mais.

A aproximação de tokens é deliberadamente simples: chars // 4. Não é um
tokenizer real e nunca é apresentada como contagem real da sessão.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[2]
CC = RAIZ / 'docs' / 'magnata-os' / 'central-command'
MAGNATA_OS = RAIZ / 'docs' / 'magnata-os'
ESTADO = CC / 'ESTADO.json'

TIER0 = [CC / 'HANDOFF.md', ESTADO, CC / 'INDEX.md']
TIER1_EXTRA = [
    RAIZ / 'CLAUDE.md',
    CC / 'TAXONOMIA_MEMORIA.md',
    CC / 'MATRIZ_AUTONOMIA.md',
    MAGNATA_OS / 'MAGNATA_OS_CENTRAL_COMMAND.md',
    CC / 'MACRO_6A_RECONCILIACAO.md',
]

LIMITE_TIER0_TOKENS_PADRAO = 8000
LIMITE_TIER0_TOKENS_TROCAR_SESSAO_PADRAO = 12000

NORMAL, ATENCAO, TROCAR_SESSAO = 'NORMAL', 'ATENCAO', 'TROCAR_SESSAO'
MENSAGEM_TROCAR_SESSAO = (
    'Estado persistido. Recomenda-se iniciar nova sessão usando HANDOFF + ESTADO + INDEX.'
)


def _texto_para_medicao(p: pathlib.Path) -> str:
    """Lê um arquivo para medição sem deixar telemetria medir a si mesma.

    Para `ESTADO.json`, remove somente a chave top-level `contexto` da
    representação usada na medição. Isso não edita o arquivo e não remove
    qualquer outro estado operacional. Em caso de JSON inválido, mede o texto
    bruto: falhar aberto aqui é melhor do que esconder bytes reais.
    """
    texto = p.read_text(encoding='utf-8', errors='replace')
    try:
        mesmo_estado = p.resolve() == ESTADO.resolve()
    except Exception:
        mesmo_estado = p == ESTADO
    if not mesmo_estado:
        return texto
    try:
        dados = json.loads(texto)
    except Exception:
        return texto
    if not isinstance(dados, dict) or 'contexto' not in dados:
        return texto
    dados = dict(dados)
    dados.pop('contexto', None)
    return json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _medir(caminhos: list[pathlib.Path]) -> dict:
    detalhe: dict[str, int] = {}
    faltando: list[str] = []
    total = 0
    for p in caminhos:
        try:
            nome = str(p.relative_to(RAIZ))
        except ValueError:
            nome = str(p)
        if not p.exists():
            faltando.append(nome)
            continue
        n = len(_texto_para_medicao(p))
        detalhe[nome] = n
        total += n
    return {
        'chars': total,
        'tokens_aprox': total // 4,
        'arquivos': detalhe,
        'faltando': faltando,
    }


def _corpus_total() -> dict:
    if not CC.exists():
        return {'chars': 0, 'tokens_aprox': 0, 'arquivos': {}, 'faltando': [str(CC)]}
    caminhos = sorted(p for p in CC.iterdir() if p.is_file())
    return _medir(caminhos)


def coletar() -> dict:
    tier0 = _medir(TIER0)
    tier1 = _medir(TIER0 + TIER1_EXTRA)
    tier2 = _corpus_total()
    razao_tier0 = (tier0['chars'] / tier2['chars']) if tier2['chars'] else 0.0
    razao_tier1 = (tier1['chars'] / tier2['chars']) if tier2['chars'] else 0.0
    return {
        'tier0_bootstrap_minimo': tier0,
        'tier1_onboarding_completo': tier1,
        'tier2_corpus_total': tier2,
        'razao_tier0_sobre_total': round(razao_tier0, 4),
        'razao_tier1_sobre_total': round(razao_tier1, 4),
    }


def classificar_status(tier0_tokens: int, limite_atencao: int, limite_trocar: int) -> str:
    if tier0_tokens > limite_trocar:
        return TROCAR_SESSAO
    if tier0_tokens > limite_atencao:
        return ATENCAO
    return NORMAL


def _resumo_auto_fact(estado: dict, limite_atencao: int, limite_trocar: int, status: str) -> dict:
    """Forma compacta para persistir em ESTADO.json.

    O detalhamento por arquivo pertence ao relatório sob demanda, não à
    memória de bootstrap. Persistimos só sinais úteis para decisão e saúde.
    """
    t0 = estado['tier0_bootstrap_minimo']
    t2 = estado['tier2_corpus_total']
    return {
        'tier0_chars': t0['chars'],
        'tier0_tokens_aprox': t0['tokens_aprox'],
        'tier2_chars': t2['chars'],
        'tier2_tokens_aprox': t2['tokens_aprox'],
        'razao_tier0_sobre_total': estado['razao_tier0_sobre_total'],
        'limite_atencao_tokens': limite_atencao,
        'limite_trocar_sessao_tokens': limite_trocar,
        'status_contexto': status,
        'mensagem': MENSAGEM_TROCAR_SESSAO if status == TROCAR_SESSAO else None,
        'medido_em': datetime.now(timezone.utc).isoformat(),
        'metrica': 'chars//4; ESTADO.contexto excluido da propria medicao',
    }


def avaliar(
    limite_atencao: int = LIMITE_TIER0_TOKENS_PADRAO,
    limite_trocar: int = LIMITE_TIER0_TOKENS_TROCAR_SESSAO_PADRAO,
    *,
    detalhado: bool = False,
) -> dict:
    """Mede/classifica; por padrão retorna AUTO_FACT compacto.

    `central_command_sensor.py` chama sem `detalhado`, portanto ESTADO.json
    recebe somente o resumo compacto. A CLI usa `detalhado=True` para mostrar
    as três camadas quando um humano/agente pede o diagnóstico completo.
    """
    estado = coletar()
    tier0_tokens = estado['tier0_bootstrap_minimo']['tokens_aprox']
    status = classificar_status(tier0_tokens, limite_atencao, limite_trocar)
    resumo = _resumo_auto_fact(estado, limite_atencao, limite_trocar, status)
    return {**estado, **resumo} if detalhado else resumo


def main() -> int:
    ap = argparse.ArgumentParser(description='Mede o custo de contexto da Central Command, por camada.')
    ap.add_argument('--json', action='store_true', help='saída em JSON')
    ap.add_argument(
        '--limite-tier0-tokens', type=int, default=LIMITE_TIER0_TOKENS_PADRAO,
        help=f'estado vira ATENCAO acima deste valor aproximado de tokens (padrão {LIMITE_TIER0_TOKENS_PADRAO})',
    )
    ap.add_argument(
        '--limite-trocar-sessao-tokens', type=int, default=LIMITE_TIER0_TOKENS_TROCAR_SESSAO_PADRAO,
        help=f'estado vira TROCAR_SESSAO acima deste valor (padrão {LIMITE_TIER0_TOKENS_TROCAR_SESSAO_PADRAO})',
    )
    args = ap.parse_args()

    faltando = [str(p) for p in TIER0 if not p.exists()]
    if faltando:
        print(
            'ERRO: arquivo(s) do bootstrap mínimo (TIER 0) ausente(s): ' + ', '.join(faltando),
            file=sys.stderr,
        )
        return 2

    estado = avaliar(
        args.limite_tier0_tokens,
        args.limite_trocar_sessao_tokens,
        detalhado=True,
    )
    status = estado['status_contexto']

    if args.json:
        print(json.dumps(estado, ensure_ascii=False, indent=2))
        return {NORMAL: 0, ATENCAO: 1, TROCAR_SESSAO: 3}[status]

    print('MEDIÇÃO DE CONTEXTO — Central Command')
    print('  tokens aprox. = chars // 4 (heurística, não é tokenizer real)')
    print('  ESTADO.contexto é excluído da própria medição para evitar auto-inflação\n')
    print(f"  TIER 0 · bootstrap mínimo   : {estado['tier0_bootstrap_minimo']['chars']:>7} chars "
          f"(~{estado['tier0_bootstrap_minimo']['tokens_aprox']} tokens) — {len(estado['tier0_bootstrap_minimo']['arquivos'])} arquivo(s)")
    print(f"  TIER 1 · onboarding completo: {estado['tier1_onboarding_completo']['chars']:>7} chars "
          f"(~{estado['tier1_onboarding_completo']['tokens_aprox']} tokens) — {len(estado['tier1_onboarding_completo']['arquivos'])} arquivo(s)")
    print(f"  TIER 2 · corpus total       : {estado['tier2_corpus_total']['chars']:>7} chars "
          f"(~{estado['tier2_corpus_total']['tokens_aprox']} tokens) — {len(estado['tier2_corpus_total']['arquivos'])} arquivo(s)")
    print()
    print(f"  TIER 0 / TIER 2 = {estado['razao_tier0_sobre_total'] * 100:.1f}% do corpus total")
    print(f"  TIER 1 / TIER 2 = {estado['razao_tier1_sobre_total'] * 100:.1f}% do corpus total")
    print(f"\n  STATUS: {status} (atenção acima de ~{args.limite_tier0_tokens}, troca de sessão acima de ~{args.limite_trocar_sessao_tokens})")
    if estado['mensagem']:
        print(f"\n{estado['mensagem']}")
    elif status == ATENCAO:
        print(f"\nALERTA: TIER 0 tem ~{estado['tier0_bootstrap_minimo']['tokens_aprox']} tokens aprox.; revisar crescimento do bootstrap.")
    else:
        print(f"\nDentro do limite: TIER 0 em ~{estado['tier0_bootstrap_minimo']['tokens_aprox']} tokens aprox.")
    return {NORMAL: 0, ATENCAO: 1, TROCAR_SESSAO: 3}[status]


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(2)
