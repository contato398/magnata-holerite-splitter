---
name: artifact-nao-abre-usar-pdf
description: Links de Artifact (claude.ai/code/artifact/...) não abrem no ambiente deste usuário; usar PDF via Edge headless como entrega padrão para documentos longos
metadata: 
  node_type: memory
  type: feedback
  originSessionId: aa03776e-e1d0-4966-80f8-990a966bd5e6
---

Neste ambiente (Windows, sessão via Claude Code), links de Artifact publicados não abrem para o usuário — aconteceu 2x (documento "Raio-X" e a "Auditoria Prestação de Contas"), mesmo com `<meta charset="UTF-8">` como primeira linha do HTML (o que corrigiu um problema de exibição anterior, mas não este). A causa exata não foi confirmada (possivelmente a sessão/browser do usuário não resolve o link), mas o padrão de falha é consistente e reprodutível.

**Solução que funciona de forma confiável**: gerar o HTML normalmente (mesmo arquivo usado para o Artifact) e depois renderizar para PDF via Microsoft Edge headless, salvando direto em `C:\Users\Lenovo\Downloads\`:

```
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="C:\Users\Lenovo\Downloads\NOME.pdf" "file:///CAMINHO/ARQUIVO.html"
```

(rodar via PowerShell tool, não Bash — o Bash wrapper engoliu o output/erro na primeira tentativa desta sessão). Uma linha de erro benigna `LoadEnclaveImageW failed` no stderr é normal e pode ser ignorada. Verificar o PDF com `pdfplumber` (contar páginas + extrair texto da primeira página) antes de declarar sucesso — não presumir que renderizou certo só porque o arquivo existe.

**Como aplicar**: para qualquer entregável longo/formatado (relatórios, checkpoints, auditorias) destinado a este usuário, ir direto para o caminho HTML→PDF em Downloads em vez de tentar o Artifact primeiro — economiza uma rodada de "não abriu". Se o usuário pedir explicitamente um Artifact ou não houver problema de abertura relatado numa sessão futura, pode-se tentar de novo (o bug pode ser específico do ambiente/dia), mas o fallback deve ser imediato ao primeiro sinal de "não abre".
