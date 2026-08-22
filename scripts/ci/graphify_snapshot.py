#!/usr/bin/env python3
"""Sensor técnico do Graphify — snapshot leve da estrutura do código.

CONTEXTO (GRAPHIFY.md, veredito ADOTAR COM RESTRIÇÕES): o `graph.json` do
Graphify tem 1,4 MB para 38 arquivos e 58% das arestas são `INFERRED` com
confiança média 0,5 — cara ou coroa. Commitar isso seria guardar
principalmente ruído.

Este script converte o grafo bruto num snapshot pequeno com SÓ o que é
evidência, e compara snapshots sucessivos para detectar mudança de
arquitetura.

RESTRIÇÕES IMPLEMENTADAS AQUI (não só documentadas):
  - lê apenas `graph.json` já gerado — NUNCA invoca LLM, nunca envia nada;
  - descarta toda aresta que não seja `EXTRACTED` (AST real);
  - o Graphify NÃO é dependência: sem `graph.json`, sai com aviso e
    código 0. Nada no Magnata OS depende deste script;
  - não escreve em `main`, não commita, não acessa rede.

A geração do grafo é feita FORA daqui, em diretório isolado:
    npm install @sentropic/graphify@0.17.1        # em /tmp, nunca no repo
    npx graphify update /caminho/da/copia         # code-only, sem chave

⚠️ Nunca apontar o Graphify para corpus com dado pessoal — `docs/historico/`,
anexos, evidências de assinatura. `CLAUDE.md` §6.

USO
    python scripts/ci/graphify_snapshot.py --grafo /tmp/poc-alvo/.graphify/graph.json
    python scripts/ci/graphify_snapshot.py --grafo <...> --salvar docs/magnata-os/central-command/ARQUITETURA_SNAPSHOT.json
    python scripts/ci/graphify_snapshot.py --grafo <...> --comparar <snapshot-anterior.json>

SAÍDA: 0 sem mudança estrutural · 1 com mudança · 2 erro.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

# Drivers de fornecedor que o DOMÍNIO nunca deve importar (CLAUDE.md §3).
# Hoje isso é conferido por grep manual a cada auditoria; com o grafo vira
# mecânico.
FORNECEDORES = ('flask', 'psycopg', 'boto3', 'requests', 'celery', 'redis', 'pyairtable')

# Um adapter PODE — e deve — falar com o fornecedor: é exatamente o padrão que
# CLAUDE.md §3 exige ("adapters para todo serviço externo"). A primeira versão
# deste detector acusava `escritor.py -> airtable_escrita.py` como violação,
# que é o oposto da verdade: é a arquitetura correta funcionando. Detector que
# grita em código certo é pior que detector nenhum — ninguém lê o segundo alerta.
CAMINHOS_ADAPTER = ('/adapters/', 'adapters/')


def _e_dominio(caminho: str) -> bool:
    """É código de domínio (onde a regra vale) e não um adapter?"""
    if not caminho.startswith('magnata_os/'):
        return False
    return not any(a in caminho for a in CAMINHOS_ADAPTER)


def resumir(grafo: dict) -> dict:
    """Extrai o snapshot leve. Só `EXTRACTED` — `INFERRED` é hipótese."""
    nos = grafo.get('nodes') or []
    links = grafo.get('links') or []

    extraidas = [l for l in links if l.get('confidence') == 'EXTRACTED']
    descartadas = len(links) - len(extraidas)

    arquivos = sorted({n['source_file'] for n in nos if n.get('source_file')})
    modulos = sorted({f.rsplit('/', 1)[0] for f in arquivos if '/' in f})

    # grau só por aresta EXTRACTED — "abstração central" precisa ser evidência
    grau = Counter()
    for l in extraidas:
        grau[l.get('source')] += 1
        grau[l.get('target')] += 1
    rotulo = {n['id']: n.get('label', n['id']) for n in nos}

    imports = sorted({
        f"{rotulo.get(l['source'], l['source'])} -> {rotulo.get(l['target'], l['target'])}"
        for l in extraidas if l.get('relation') == 'imports_from'
    })

    # violação de acoplamento: domínio importando driver de fornecedor
    violacoes = sorted({
        f"{l.get('source_file')}: {rotulo.get(l['target'], l['target'])}"
        for l in extraidas
        if l.get('relation') in ('imports_from', 'uses')
        and _e_dominio(l.get('source_file') or '')
        and any(v in str(rotulo.get(l['target'], '')).lower() for v in FORNECEDORES)
    })

    return {
        'arquivos': arquivos,
        'modulos': modulos,
        'simbolos': sorted({rotulo[n['id']] for n in nos}),
        'total_nos': len(nos),
        'arestas_extracted': len(extraidas),
        'arestas_descartadas_inferred': descartadas,
        'relacoes_por_tipo': dict(Counter(l.get('relation') for l in extraidas).most_common()),
        'comunidades': len({n.get('community') for n in nos if n.get('community') is not None}),
        'abstracoes_centrais': [
            {'simbolo': rotulo.get(i, i), 'grau_extracted': g}
            for i, g in grau.most_common(15)
        ],
        'imports_from': imports,
        'violacoes_de_acoplamento': violacoes,
    }


def comparar(atual: dict, anterior: dict) -> list[str]:
    """Só mudança ESTRUTURAL. Variação de contagem sem mudança de conjunto
    não é notícia — vira ruído e ninguém lê."""
    div = []

    for campo, nome in (('arquivos', 'arquivo'), ('modulos', 'módulo'), ('simbolos', 'símbolo')):
        antes, agora = set(anterior.get(campo) or []), set(atual.get(campo) or [])
        novos, sumidos = sorted(agora - antes), sorted(antes - agora)
        if novos:
            div.append(f"{nome}(s) NOVO(S) ({len(novos)}): " + ', '.join(novos[:8]) + ('…' if len(novos) > 8 else ''))
        if sumidos:
            div.append(f"{nome}(s) REMOVIDO(S) ({len(sumidos)}): " + ', '.join(sumidos[:8]) + ('…' if len(sumidos) > 8 else ''))

    antes_i, agora_i = set(anterior.get('imports_from') or []), set(atual.get('imports_from') or [])
    for i in sorted(agora_i - antes_i):
        div.append(f"dependência NOVA: {i}")
    for i in sorted(antes_i - agora_i):
        div.append(f"dependência removida: {i}")

    antes_v, agora_v = set(anterior.get('violacoes_de_acoplamento') or []), set(atual.get('violacoes_de_acoplamento') or [])
    for v in sorted(agora_v - antes_v):
        div.append(f"VIOLAÇÃO DE ACOPLAMENTO NOVA (CLAUDE.md §3): {v}")

    if anterior.get('comunidades') and atual['comunidades'] != anterior['comunidades']:
        div.append(
            f"comunidades: {anterior['comunidades']} -> {atual['comunidades']} "
            f"— a topologia mudou; conferir se a documentação de módulos acompanhou."
        )
    return div


def main() -> int:
    ap = argparse.ArgumentParser(description='Snapshot leve de arquitetura a partir do Graphify.')
    ap.add_argument('--grafo', required=True, help='caminho do graph.json gerado pelo Graphify')
    ap.add_argument('--salvar', help='grava o snapshot leve neste caminho')
    ap.add_argument('--comparar', help='snapshot anterior para comparar')
    args = ap.parse_args()

    caminho = pathlib.Path(args.grafo)
    if not caminho.exists():
        # Degradação graciosa: o Graphify não é requisito de nada.
        print(f'graph.json não encontrado em {caminho}.')
        print('O Graphify não é dependência do Magnata OS — nada quebra por isso.')
        print('Para gerar: npx graphify update <copia-isolada>  (code-only, sem chave).')
        return 0

    snap = resumir(json.loads(caminho.read_text(encoding='utf-8')))

    print('SNAPSHOT DE ARQUITETURA (somente arestas EXTRACTED)')
    print(f"  arquivos            : {len(snap['arquivos'])}")
    print(f"  módulos             : {len(snap['modulos'])}")
    print(f"  símbolos            : {len(snap['simbolos'])}")
    print(f"  nós                 : {snap['total_nos']}")
    print(f"  arestas EXTRACTED   : {snap['arestas_extracted']}")
    print(f"  arestas descartadas : {snap['arestas_descartadas_inferred']} (INFERRED — hipótese, não evidência)")
    print(f"  comunidades         : {snap['comunidades']}")
    print(f"  relações            : {snap['relacoes_por_tipo']}")
    if snap['violacoes_de_acoplamento']:
        print(f"  ⚠ VIOLAÇÕES DE ACOPLAMENTO: {len(snap['violacoes_de_acoplamento'])}")
        for v in snap['violacoes_de_acoplamento'][:10]:
            print(f"      {v}")
    else:
        print('  acoplamento         : nenhuma violação de CLAUDE.md §3 detectada')
    print('  abstrações centrais :', ', '.join(
        f"{a['simbolo']}({a['grau_extracted']})" for a in snap['abstracoes_centrais'][:8]))

    if args.salvar:
        p = pathlib.Path(args.salvar)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(f'\nSnapshot salvo: {p} ({p.stat().st_size / 1024:.0f} KB)')

    if args.comparar:
        ant = pathlib.Path(args.comparar)
        if not ant.exists():
            print(f'\nSnapshot anterior não existe: {ant}')
            return 0
        div = comparar(snap, json.loads(ant.read_text(encoding='utf-8')))
        if div:
            print(f'\n{len(div)} MUDANÇA(S) ESTRUTURAL(IS):')
            for d in div:
                print(f'  - {d}')
            return 1
        print('\nSem mudança estrutural.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:  # falha nunca silenciosa (CLAUDE.md §4)
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(2)
