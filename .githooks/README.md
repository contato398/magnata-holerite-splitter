# Git Hooks — Magnata OS

Repositório de hooks locais de segurança e validação.

## Estrutura

- `pre-commit` — Validações antes de commit
- `commit-msg` — Validação de mensagem de commit
- `pre-push` — Bloqueio de push automático
- `post-commit` — Feedback informativo
- `test-hooks.sh` — Suite de testes

## Ativação Local

Execute uma vez no repositório:

```bash
git config core.hooksPath .githooks
```

Isso configura Git para usar hooks deste diretório. Configuração local, reversível.

## Verificar Ativação

```bash
git config core.hooksPath
# Deve retornar: .githooks
```

## Desativar

```bash
git config --unset core.hooksPath
```

## Pre-Push Authorization

Para fazer `git push`, crie um arquivo de autorização temporária:

**PowerShell:**
```powershell
New-Item -ItemType File -Path ".git\MAGNATA_PUSH_AUTHORIZED_ONCE" -Force
git push origin feat/magnata-os-claude-powerpack
```

**Git Bash:**
```bash
touch "$(git rev-parse --git-dir)/MAGNATA_PUSH_AUTHORIZED_ONCE"
git push origin feat/magnata-os-claude-powerpack
```

O arquivo é:
- Criado localmente, nunca versionado
- Válido para um único push
- Removido automaticamente após o push
- Recriado para cada novo push

## Testes

```bash
chmod +x .githooks/test-hooks.sh
.githooks/test-hooks.sh
```

## Referência Completa

Ver: `docs/magnata-os/MAGNATA_AI_HOOKS_LOCAIS.md`
