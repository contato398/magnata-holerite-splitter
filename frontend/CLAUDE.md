# frontend/ — Regras específicas

Complementa `/CLAUDE.md` (raiz) — não repete o que já está lá. Vale
para tudo dentro de `frontend/`, hoje `assets/brand/` (identidade
visual, Fase de identidade) e o painel da Fase 5
(`src/`, `styles/`, `tests/`, `index.html`, ainda numa branch própria,
não mesclada em `main` no momento em que este arquivo foi criado).

- **Identidade visual oficial vive em `assets/brand/`.** Símbolo,
  logo horizontal e PNGs — nunca redesenhar, recomprimir, recolorir ou
  trocar de formato sem autorização explícita (ver `/CLAUDE.md` §7 e
  `MAGNATA_OS_IDENTIDADE_VISUAL.md`).
- **Os contratos da API da Fase 4
  (`magnata_os/documental/modulo01/api/contratos.py`) são a única fonte
  de forma de dado.** Qualquer tipo/contrato em JavaScript
  (`src/api/contracts.js`, se presente) precisa continuar espelhando
  esses nomes de campo e valores de enum exatamente — nunca inventar
  campo novo do lado do frontend.
- **Acessibilidade não é opcional.** Elemento interativo tem rótulo
  acessível; estado (carregando/vazio/erro/sem permissão) é anunciado,
  não só visual.
- **Responsividade real, não compressão.** Em tela pequena, um
  componente largo (ex.: quadro em colunas) precisa de uma navegação
  adequada para o espaço — nunca só espremer o mesmo layout.
- **Nunca conectar direto ao legado.** Sem chamada a `app.py`, sem rota
  Flask, sem `fetch` contra o legado.
- **Nunca acessar banco ou Airtable diretamente.** Todo dado passa por
  um adapter que espelha os contratos da API (mock hoje; HTTP real numa
  fase futura) — nunca uma chamada direta a Postgres/Airtable/S3 a
  partir do frontend.
