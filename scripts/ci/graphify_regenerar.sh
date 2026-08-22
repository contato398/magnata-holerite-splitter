#!/usr/bin/env bash
# Regenera o snapshot de arquitetura do Graphify — sensor técnico opcional.
#
# POR QUE ESTE SCRIPT EXISTE: até aqui o Graphify era POC manual. Isto o torna
# regenerável por um comando, sem virar dependência crítica de nada.
#
# RESTRIÇÕES DE GRAPHIFY.md §6, implementadas aqui e não só documentadas:
#   1. code-only por AST — nunca backend de LLM;
#   2. nenhuma chave de API é lida ou exigida; as que existirem no ambiente
#      são explicitamente NEUTRALIZADAS antes de invocar a ferramenta;
#   3. roda sobre CÓPIA em diretório temporário, nunca no repositório;
#   4. a cópia EXCLUI qualquer corpus com dado pessoal (CLAUDE.md §6);
#   5. versão pinada exata;
#   6. não commita nada; só grava o snapshot leve se --salvar for passado;
#   7. se o Graphify não estiver instalado, avisa e sai com 0 — nada quebra.
#
# USO
#   scripts/ci/graphify_regenerar.sh                    # relatório
#   scripts/ci/graphify_regenerar.sh --salvar           # grava o snapshot
#   scripts/ci/graphify_regenerar.sh --comparar         # compara com o salvo
set -uo pipefail

VERSAO="@sentropic/graphify@0.17.1"   # pinada — é v0.x, API instável
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="${TMPDIR:-/tmp}/graphify-magnata"
COPIA="$TMP/alvo"
SNAP="$RAIZ/docs/magnata-os/central-command/ARQUITETURA_SNAPSHOT.json"

SALVAR=0; COMPARAR=0
for a in "$@"; do
  case "$a" in
    --salvar) SALVAR=1 ;;
    --comparar) COMPARAR=1 ;;
    *) echo "argumento desconhecido: $a"; exit 2 ;;
  esac
done

command -v npx >/dev/null 2>&1 || {
  echo "npx não disponível. O Graphify é sensor OPCIONAL — nada no Magnata OS depende dele."
  exit 0
}

echo "== 1/4 preparando cópia isolada =="
rm -rf "$COPIA"; mkdir -p "$COPIA"

# Só código. Nada de docs/historico/ (29 arquivos com CPF e nome real),
# nada de scratch, nada de anexo. Ver FORA_DO_GIT.md §1.
for alvo in magnata_os src scripts celery_app.py app.py; do
  [ -e "$RAIZ/$alvo" ] && cp -r "$RAIZ/$alvo" "$COPIA/" 2>/dev/null
done
find "$COPIA" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
find "$COPIA" -name '*.pyc' -delete 2>/dev/null

# Trava de segurança: aborta se houver CPF REAL na cópia.
# Só conta CPF com dígito verificador válido -- fixture sintética de teste
# (111.111.111-11, 123.456.789-00) tem o formato mas falha a validação, e
# barrar essas travaria o sensor sem ganho nenhum de privacidade.
# Esta trava já provou o valor: na primeira execução encontrou 3 CPFs REAIS
# commitados em código versionado, corrigidos no mesmo PR que a criou.
if ! python3 - "$COPIA" <<'VERIFICA'
import re, sys, pathlib
def valido(c):
    d = [int(x) for x in re.sub(r'\D', '', c)]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        if (sum(d[i] * ((n + 1) - i) for i in range(n)) * 10) % 11 % 10 != d[n]:
            return False
    return True
padrao = re.compile(r'[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}')
reais = set()
for f in pathlib.Path(sys.argv[1]).rglob('*'):
    if not f.is_file():
        continue
    try:
        for c in padrao.findall(f.read_text(encoding='utf-8', errors='ignore')):
            if valido(c):
                reais.add(str(f))
    except Exception:
        continue
if reais:
    print('  CPF REAL em:', ', '.join(sorted(reais)[:5]))
    sys.exit(1)
sys.exit(0)
VERIFICA
then
  echo "ABORTADO: a cópia contém CPF real. O Graphify não roda sobre dado pessoal (CLAUDE.md §6)."
  rm -rf "$COPIA"; exit 2
fi
echo "   arquivos .py copiados: $(find "$COPIA" -name '*.py' | wc -l) · nenhum CPF real"

echo "== 2/4 garantindo o Graphify (fora do repositório) =="
mkdir -p "$TMP/ferramenta"
if [ ! -d "$TMP/ferramenta/node_modules/@sentropic/graphify" ]; then
  (cd "$TMP/ferramenta" && npm install --silent --no-fund --no-audit "$VERSAO") || {
    echo "falha ao instalar o Graphify. Sensor opcional — seguindo sem ele."; exit 0; }
fi

echo "== 3/4 extraindo grafo (code-only, sem LLM, sem chave) =="
# Neutraliza qualquer chave presente no ambiente: o Graphify detecta provider
# por chave e passaria a enviar conteúdo para fora. Isto impede isso.
( cd "$COPIA" && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u GOOGLE_API_KEY \
       -u MISTRAL_API_KEY -u COHERE_API_KEY -u GEMINI_API_KEY \
    npx --prefix "$TMP/ferramenta" graphify update "$COPIA" \
      --no-description >/dev/null 2>&1 ) || true

GRAFO="$COPIA/.graphify/graph.json"
[ -f "$GRAFO" ] || { echo "grafo não gerado. Sensor opcional — nada quebra."; exit 0; }

echo "== 4/4 snapshot leve =="
ARGS=(--grafo "$GRAFO")
[ "$SALVAR" -eq 1 ] && ARGS+=(--salvar "$SNAP")
[ "$COMPARAR" -eq 1 ] && [ -f "$SNAP" ] && ARGS+=(--comparar "$SNAP")
python3 "$RAIZ/scripts/ci/graphify_snapshot.py" "${ARGS[@]}"
CODIGO=$?

echo
echo "Grafo bruto mantido FORA do repositório: $GRAFO"
echo "Nenhum artefato pesado foi versionado."
exit $CODIGO
