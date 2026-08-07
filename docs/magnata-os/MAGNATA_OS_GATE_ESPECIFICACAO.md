# `magnata gate` — Especificação de arquitetura (proposta, não implementada)

Complementa [`CLAUDE.md`](../../CLAUDE.md) §12 ("Autonomia operacional
ampliada", item F). Este documento é **só especificação** — nenhuma
implementação foi feita nesta fase, conforme instrução explícita de não
ampliar a arquitetura sem necessidade.

## 1. Objetivo

Automatizar as verificações hoje feitas manualmente a cada rodada de
revisão técnica (Ultrareview, gate pré-Git, comprovação de falha
pré-existente) num único comando reprodutível, com relatório
padronizado — reduzindo o custo de repetir essas checagens à mão em
toda fase nova do Magnata OS.

## 2. Escopo funcional

`magnata gate` roda **só leitura + testes locais** — nunca commit,
push, PR, merge, deploy, gravação externa. Produz um relatório único,
estruturado, com veredito objetivo (`PRONTO` / `NÃO PRONTO`, nos termos
de `CLAUDE.md` §10).

### 2.1 Fases

1. **Estado Git** — `pwd`, branch, HEAD, `git status --short --branch`,
   relação com `origin/<default>` (ahead/behind), log recente.
2. **Arquivos protegidos** — hash (`sha256`) de `app.py`, `render.yaml`,
   `Procfile`; diff estrutural (`diff -rq`) de `frontend/` e
   `magnata_os/documental/modulo01/migrations/` contra uma base de
   referência (branch/commit informado). Falha o gate se qualquer um
   divergir sem uma autorização explícita associada à execução (passada
   como parâmetro, nunca inferida).
3. **Testes e baseline de falhas pré-existentes** — roda a suíte geral;
   compara contra uma baseline gravada (lista de testes + assinatura de
   erro esperada, atualizada só por decisão humana) para classificar
   cada falha como `pré-existente` / `regressão nova` / `inconclusiva`,
   sem depender de memória ou de reafirmação não verificada.
4. **PII scan** — varredura por padrão de CPF/CNPJ/telefone/e-mail e por
   palavras-chave de segredo (token, senha, chave, cookie) em todo o
   diff da fase e em qualquer arquivo de teste novo.
5. **Integridade de manifesto/PDF** (quando aplicável ao módulo em
   revisão) — assinatura de arquivo, teto de tamanho, JSON bem formado,
   nos mesmos moldes já implementados em
   `magnata_os/documental/importacao_lote/`.
6. **Ultrareview estrutural** — checklist fixo e versionado (pureza de
   domínio — zero import de Flask/driver/Airtable no núcleo; ausência de
   hard-code de competência/data específica; exceções tratadas nos
   pontos de entrada externos — PDF, ZIP, rede; ausência de path
   traversal; teto de descompressão) rodado como verificação
   automatizada, complementar à revisão humana/Ultrareview manual — não
   substitui julgamento humano em achados ambíguos.
7. **Relatório único** — mesma estrutura de entrega já usada nas
   consolidações desta fase (estado Git, diff, achados, testes,
   regressões, segurança/LGPD, arquivos protegidos, riscos, próximo
   gate), gerada automaticamente, sem depender de composição manual a
   cada rodada.
8. **Readiness** — veredito objetivo sobre se a fase está pronta para os
   próximos gates humanos (commit/push/PR/deploy), nunca decide esses
   gates sozinho — só informa se as condições técnicas para chegar lá
   estão satisfeitas.

## 3. Arquitetura proposta

Mesma separação núcleo/adapter já estabelecida nesta fase
(`magnata_os/documental/importacao_lote/` como referência de padrão):

```
magnata_os/engenharia/gate/          (nome de pacote ilustrativo, a definir)
  dominio.py        # regras puras: classificação de falha, veredito,
                     # checklist estrutural do Ultrareview — sem I/O
  contratos.py       # tipos: RelatorioGate, AchadoUltrareview,
                     # ClassificacaoFalha, VeredictoFase
  adapters/
    git_leitura.py    # subprocess git, só comandos de leitura
    testes.py         # execução de pytest, parsing de resultado
    baseline.py        # leitura/gravação da baseline de falhas conhecidas
    pii_scan.py         # varredura de padrões, reaproveitável fora do gate
  orquestrador.py      # liga tudo, produz o RelatorioGate final
```

- **Domínio puro, testável sem repositório real** — mesma garantia já
  aplicada ao módulo de importação em lote.
- **Baseline de falhas pré-existentes como artefato versionado**, não
  memória de conversa — precisa de decisão sobre onde vive (arquivo no
  repo? tabela em algum lugar?) antes de implementar; não presumido
  aqui.
- **Nenhuma escrita** em nenhum adapter desta capacidade — é
  estruturalmente só-leitura, por desenho, do mesmo jeito que
  `adapters/airtable_leitura.py` só tem métodos GET.

## 4. Decisões em aberto (não resolvidas por este documento)

- Onde a baseline de falhas pré-existentes é armazenada e quem a
  atualiza (deliberadamente fora do escopo desta especificação —
  decisão de processo, não de arquitetura).
- Se `magnata gate` vira um comando de linha de comando, uma skill, ou
  parte do CI de governança já existente
  (`.github/workflows/magnata-governance.yml`) — as três opções são
  compatíveis com esta arquitetura; a escolha fica para quando a
  implementação for de fato autorizada.
- Nomenclatura definitiva do pacote (`magnata_os/engenharia/gate/` é
  ilustrativo, não uma decisão).

## 5. Critérios de aceite para uma futura implementação

- Cada fase (1–8) roda isoladamente e é testável com dados sintéticos.
- Nenhum adapter tem método de escrita.
- O relatório final é determinístico para a mesma entrada (mesmo commit,
  mesma baseline).
- Falso negativo (regressão real classificada como pré-existente) é
  tratado como o pior tipo de defeito possível deste sistema —
  qualquer ambiguidade na classificação deve favorecer marcar como
  "inconclusiva", nunca "pré-existente" por omissão.
