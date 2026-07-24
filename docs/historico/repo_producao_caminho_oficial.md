---
name: repo_producao_caminho_oficial
description: "Caminho oficial do repo de produção é C:\\Users\\Lenovo\\magnata-holerite-splitter, NÃO o Downloads"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

O repositório de produção oficial do `magnata-holerite-splitter` é
**`C:\Users\Lenovo\magnata-holerite-splitter`** (git, remote GitHub
`contato398/magnata-holerite-splitter`, branch `main`, auto-deploy Render →
`https://magnata-holerite-splitter.onrender.com`).

**Why:** A pasta de trabalho `C:\Users\Lenovo\Downloads` contém cópias VELHAS e
soltas (`app.py` lá estava em v2.5/v2.6, de 12/06) além de dezenas de scripts
one-off. Em 24/06, ao implementar a integração Secullum (v2.49), quase commitei
no `Downloads/app.py` errado — que nem é repo git e teria sido um rollback de
~43 versões. O `app.py` real estava em v2.48.

**How to apply:** Para QUALQUER mudança que vá para produção/deploy (editar
`app.py`, criar módulos, commit/push), trabalhar SEMPRE em
`C:\Users\Lenovo\magnata-holerite-splitter`. Antes de editar, confirmar a versão
em `/health` do arquivo vs. a esperada na memória; se divergir, é sinal de
arquivo errado/estale. Downloads serve só como scratch. Ver [[padrao_deploy_render_confirmar_versao]].
