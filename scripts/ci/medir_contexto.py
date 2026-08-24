#!/usr/bin/env python3
"""Medição de contexto — quanto custa ler a Central Command, por camada.

PROBLEMA QUE ISTO RESOLVE: `HANDOFF.md` promete "contexto mínimo primeiro,
detalhe só sob demanda" (missão de otimização de contexto/tokens), mas
até agora isso era uma afirmação sem número. Sem medição, "mínimo" é
opinião; com medição, é um fato que se degrada visivelmente conforme os
documentos crescem — e um sensor futuro (`central_command_sensor.py`) pode
comparar contra um valor anterior, do mesmo jeito que já compara SHA e
contagem de documentos.

O QUE ISTO É: leitura read-only de tamanho de arquivo (chars e uma
aproximação grosseira de tokens, chars/4 — não é um tokenizer real, e o
relatório deixa isso explícito). Três camadas, cada uma o que uma sessão
precisa ler para responder uma pergunta cada vez mais profunda:

  TIER 0 · bootstrap mínimo  — o que `HANDOFF.md` manda ler numa sessão
           fria e nada mais (`HANDOFF.md`, `ESTADO.json`, `INDEX.md`).
  TIER 1 · onboarding completo — TIER 0 + os 5 documentos que
           `HANDOFF.md` §2 recomenda antes de agir (`CLAUDE.md`,
           `TAXONOMIA_MEMORIA.md`, `MATRIZ_AUTONOMIA.md`, o mestre
           `MAGNATA_OS_CENTRAL_COMMAND.md` inteiro — HANDOFF pede só
           §0-H a §0-J, medir o arquivo inteiro é a simplificação
           deliberada aqui — e `MACRO_6A_RECONCILIACAO.md`).
  TIER 2 · corpus total       — todo arquivo dentro de
           `docs/magnata-os/central-command/`, qualquer extensão.

O QUE ISTO NÃO É, de propósito:
  - não é um medidor real de tokens de sessão (isso exige instrumentar o
    runtime da conversa, que este script não alcança — a "aproximação
    grosseira" acima é o limite honesto do que dá pra medir de fora);
  - não edita nada, não decide nada, não é dependência de build;
  - não substitui `central_command_sensor.py` — mede tamanho, não
    divergência de conteúdo.

ALERTA DE CONTEXTO (`avaliar()`): 3 estados, só a partir do tamanho do
TIER 0 medido acima — NUNCA a partir de contagem real de tokens de
conversa, que este script não tem como observar. "Quantos arquivos
foram carregados nesta sessão" e "repetição de leitura" também não são
observáveis por um script que roda fora do runtime da conversa — por
isso não entram na classificação, para não fingir um sinal que não
existe.

  NORMAL         — TIER 0 dentro do limite de atenção.
  ATENCAO        — TIER 0 passou do limite de atenção.
  TROCAR_SESSAO  — TIER 0 passou do limite (mais alto) de troca de sessão.

Reversível por construção: apagar este arquivo não afeta mais nada.

USO
    python scripts/ci/medir_contexto.py             # relatório
    python scripts/ci/medir_contexto.py --json       # saída JSON
    python scripts/ci/medir_contexto.py --limite-tier0-tokens 8000
    python scripts/ci/medir_contexto.py --limite-trocar-sessao-tokens 12000

SAÍDA: 0 NORMAL · 1 ATENCAO · 3 TROCAR_SESSAO · 2 erro de execução ou
arquivo do bootstrap ausente (falha nunca é silenciosa, CLAUDE.md §4 —
um bootstrap que não existe é pior do que um grande).
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

TIER0 = [CC / 'HANDOFF.md', CC / 'ESTADO.json', CC / 'INDEX.md']
TIER1_EXTRA = [
    RAIZ / 'CLAUDE.md',
    CC / 'TAXONOMIA_MEMORIA.md',
    CC / 'MATRIZ_AUTONOMIA.md',
    MAGNATA_OS / 'MAGNATA_OS_CENTRAL_COMMAND.md',
    CC / 'MACRO_6A_RECONCILIACAO.md',
]

# Limites default do TIER 0, medidos nesta etapa: ~16,5 mil chars / ~4,1 mil
# tokens aprox. Os limites ficam acima disso de propósito — não é para
# disparar em toda edição pequena, é para avisar se o bootstrap engordar
# sem ninguém decidir isso. TROCAR_SESSAO é 1,5x o limite de ATENCAO — não
# é um segundo número arbitrário, é o mesmo limite com folga adicional
# antes de virar recomendação de troca.
LIMITE_TIER0_TOKENS_PADRAO = 8000
LIMITE_TIER0_TOKENS_TROCAR_SESSAO_PADRAO = 12000

NORMAL, ATENCAO, TROCAR_SESSAO = 'NORMAL', 'ATENCAO', 'TROCAR_SESSAO'

MENSAGEM_TROCAR_SESSAO = (
    'Estado persistido. Recomenda-se iniciar nova sessão usando HANDOFF + ESTADO + INDEX.'
)


def _medir(caminhos: list[pathlib.Path]) -> dict:
    detalhe: dict[str, int] = {}
    faltando: list[str] = []
    total = 0
    for p in caminhos:
        try:
            nome = str(p.relative_to(RAIZ))
        except ValueError:
            nome = str(p)  # fora de RAIZ (ex.: caminho de teste) — não é o caso normal
        if not p.exists():
            faltando.append(nome)
            continue
        n = len(p.read_text(encoding='utf-8', errors='replace'))
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
    """3 estados observáveis, só a partir do tamanho medido do TIER 0.

    Deliberadamente sem "scoring" — duas comparações numéricas, nada mais.
    Não recebe nem inventa sinal de "tokens reais da sessão", "arquivos
    carregados" ou "releitura repetida": nenhum desses é observável por um
    script que roda fora do runtime da conversa (ver docstring do módulo).
    """
    if tier0_tokens > limite_trocar:
        return TROCAR_SESSAO
    if tier0_tokens > limite_atencao:
        return ATENCAO
    return NORMAL


def avaliar(
    limite_atencao: int = LIMITE_TIER0_TOKENS_PADRAO,
    limite_trocar: int = LIMITE_TIER0_TOKENS_TROCAR_SESSAO_PADRAO,
) -> dict:
    """`coletar()` + classificação — é isto que `central_command_sensor.py`
    chama para popular `ESTADO.json['contexto']` (AUTO_FACT, ver
    TAXONOMIA_MEMORIA.md), e sem escrever nada aqui: só mede e classifica."""
    estado = coletar()
    tier0_tokens = estado['tier0_bootstrap_minimo']['tokens_aprox']
    status = classificar_status(tier0_tokens, limite_atencao, limite_trocar)
    return {
        **estado,
        'limite_atencao_tokens': limite_atencao,
        'limite_trocar_sessao_tokens': limite_trocar,
        'status_contexto': status,
        'mensagem': MENSAGEM_TROCAR_SESSAO if status == TROCAR_SESSAO else None,
        'medido_em': datetime.now(timezone.utc).isoformat(),
    }


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
            'ERRO: arquivo(s) do bootstrap mínimo (TIER 0) ausente(s): ' + ', '.join(faltando)
            + ' — uma sessão nova não consegue seguir o protocolo de HANDOFF.md sem eles.',
            file=sys.stderr,
        )
        return 2

    estado = avaliar(args.limite_tier0_tokens, args.limite_trocar_sessao_tokens)
    status = estado['status_contexto']

    if args.json:
        print(json.dumps(estado, ensure_ascii=False, indent=2))
        return {NORMAL: 0, ATENCAO: 1, TROCAR_SESSAO: 3}[status]

    print('MEDIÇÃO DE CONTEXTO — Central Command')
    print("  tokens aprox. = chars // 4 (heurística, não é tokenizer real)\n")
    print(f"  TIER 0 · bootstrap mínimo   : {estado['tier0_bootstrap_minimo']['chars']:>7} chars "
          f"(~{estado['tier0_bootstrap_minimo']['tokens_aprox']} tokens) — {len(estado['tier0_bootstrap_minimo']['arquivos'])} arquivo(s)")
    print(f"  TIER 1 · onboarding completo: {estado['tier1_onboarding_completo']['chars']:>7} chars "
          f"(~{estado['tier1_onboarding_completo']['tokens_aprox']} tokens) — {len(estado['tier1_onboarding_completo']['arquivos'])} arquivo(s)")
    print(f"  TIER 2 · corpus total       : {estado['tier2_corpus_total']['chars']:>7} chars "
          f"(~{estado['tier2_corpus_total']['tokens_aprox']} tokens) — {len(estado['tier2_corpus_total']['arquivos'])} arquivo(s)")
    print()
    print(f"  TIER 0 / TIER 2 = {estado['razao_tier0_sobre_total'] * 100:.1f}% do corpus total")
    print(f"  TIER 1 / TIER 2 = {estado['razao_tier1_sobre_total'] * 100:.1f}% do corpus total")
    print(f"\n  STATUS: {status} (atenção acima de ~{args.limite_tier0_tokens}, "
          f"troca de sessão acima de ~{args.limite_trocar_sessao_tokens})")

    if estado['mensagem']:
        print(f"\n{estado['mensagem']}")
    elif status == ATENCAO:
        print(
            f"\nALERTA: TIER 0 tem ~{estado['tier0_bootstrap_minimo']['tokens_aprox']} tokens aprox., "
            f"acima do limite de atenção. O bootstrap deveria ficar pequeno por desenho — "
            f"revisar o que engordou antes de deixar crescer mais."
        )
    else:
        print(f"\nDentro do limite: TIER 0 em ~{estado['tier0_bootstrap_minimo']['tokens_aprox']} tokens aprox.")

    return {NORMAL: 0, ATENCAO: 1, TROCAR_SESSAO: 3}[status]


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:  # falha nunca silenciosa (CLAUDE.md §4)
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(2)
