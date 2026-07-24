---
name: padrao-deploy-render-confirmar-versao
description: Sempre bumpar a string de versão em /health e confirmar via curl antes de declarar um deploy no Render como concluído
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Antes de declarar qualquer deploy do app.py (magnata-holerite-splitter) como concluído, bumpar a string `'versao': 'X.YY'` dentro da rota `/health` no mesmo commit, dar push, e então chamar `GET https://magnata-holerite-splitter.onrender.com/health` via curl até o número bater. Só então comunicar sucesso ao usuário.

**Why:** numa sessão anterior, `/health` respondeu 200 logo após o push mas ainda mostrando a versão antiga — o Render demora 2-5 min para trocar o worker, e responder 200 não significa que o build novo já está no ar (o antigo continua respondendo durante o rollout). Sem o número de versão como marcador, não havia como confirmar de forma inequívoca, e a usuária pediu explicitamente esse bump para "controle correto do histórico".

**How to apply:** todo commit que vá para produção via `git push origin main` (auto-deploy no Render) deve incluir o bump de versão. Usar `ScheduleWakeup` com ~150s de delay para checar `/health` em vez de ficar perguntando ao usuário se já subiu. Só rodar testes reais em produção (curl, Airtable MCP) depois de confirmar a versão nova.
