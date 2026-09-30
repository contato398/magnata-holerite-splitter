# Painel Operacional (Fase 5) — Recuperação do Frontend, V1

## Objetivo

Recuperar o painel Vanilla JS da Fase 5 (`docs/magnata-os/central-command/FASE5_AUDITORIA.md`)
e ligá-lo a dados reais, sem duplicar o trabalho já pronto na branch
órfã `origin/feat/magnata-os-documental-modulo01-fase5-painel`.

## Por que esta branch está separada da que registra o blueprint em `app.py`

Uma missão anterior implementou o backend (API HTTP real,
`magnata_os/documental/modulo01/adapters/blueprint_esteira.py`) e o
frontend juntos, na mesma branch/commit que também tocava `app.py`
(2 linhas, registro do blueprint). Isso viola `/CLAUDE.md` §7 de duas
formas: (1) `app.py` só pode ser alterado em branch própria, dedicada
só a isso; (2) não pode ser misturado com construção de módulo novo no
mesmo commit/branch. A mudança em `app.py` foi separada para a branch
`fix/magnata-os-app-py-registro-blueprint-esteira-v1`, aguardando
autorização humana explícita (blob exato), antes de qualquer commit
nela. Esta branch (`fix/magnata-os-painel-fase5-frontend-v1`) contém
só o frontend — zero alteração em `app.py` ou em qualquer arquivo
Python do backend.

## O que entra

- `frontend/index.html`, `frontend/src/**`, `frontend/styles/**`,
  `frontend/tests/**` — recuperados de
  `origin/feat/magnata-os-documental-modulo01-fase5-painel`, sem
  alteração de conteúdo em relação a essa branch, exceto pela adição
  de `frontend/src/api/apiAdapter.js` (client HTTP real, drop-in de
  `mockAdapter.js`) e o ajuste de `frontend/src/app.js` para checar
  sessão (`GET /auth/me`) antes de montar qualquer tela.
- `frontend/CLAUDE.md` e `frontend/assets/brand/` continuam intocados
  e protegidos — não fazem parte deste diff.

## O que não entra / gate remanescente

- **A API real que `apiAdapter.js` chama só existe depois que a
  branch backend for autorizada e mesclada.** Até lá, este painel só
  funciona em modo demonstração (`?mock=1`, usa `mockAdapter.js`) —
  não é uma regressão desta branch, é uma dependência declarada.
- Nenhum deploy, nenhuma exposição pública. Roda só localmente
  (`python -m http.server --directory frontend`).
- Nenhuma alteração em `app.py`, migration, schema, Airtable, Postgres
  real, credencial.

## Riscos declarados

- Enquanto a branch backend não for mesclada, quem abrir este painel
  sem `?mock=1` vê a tela de "sessão ausente/API indisponível" — é o
  comportamento esperado (fail-closed), não um bug a esconder.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
