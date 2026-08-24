# Fase 1 do modo sombra de captura de e-mail — implementação concluída

**Data:** 2026-08-24
**Branch:** `fix/gmail-adapter-fase1-inerte`
**Commit:** `1a5fcb8`
**Status:** ✅ Implementado, testado, pronto para revisão

## Resumo executivo

Implementamos a **Fase 1** do plano de modo sombra de captura de e-mail (ver `plano-modo-sombra-captura-email.md`):
um cliente Gmail **real em código, totalmente inerte**: implementa a interface `FonteMensagensEmail` (Protocol já definido em `email_captura.py`), com escopo OAuth travado em `gmail.readonly` (nunca escrita), e zero credencial real, zero rede, 100% testável com duplos.

## O que foi implementado

**Arquivo novo:** `magnata_os/documental/modulo01/adapters/email_gmail_readonly.py` (386 linhas)

- `ClienteGmailReadOnly`: cliente da API Gmail v1, implementa `FonteMensagensEmail`
  - `buscar_novas_mensagens()` → filtra por label dedicada, devolve `Sequence[MensagemEmailRecebida]`
  - Escopo travado em código: `ESCOPOS_READONLY = ('https://www.googleapis.com/auth/gmail.readonly',)`
  - Métodos de LEITURA APENAS: `users().labels().list`, `users().messages().list/get`, `users().messages().attachments().get`
  - Nenhum método de escrita importado/referenciado (`modify`, `trash`, `delete`, `send`, etc.)

- `carregar_credenciais_gmail_readonly(caminho_token)`: carrega token OAuth real
  - Levanta `CredencialGmailAusente` se não informado
  - Nenhum test deste repositório chama com um caminho real

- `construir_recurso_gmail(credenciais)`: constrói recurso `googleapiclient` real
  - Import local (ver docstring do módulo — nunca no topo)
  - Nenhum test deste repositório chama com credencial real

- Helpers puros (`_cabecalho`, `_data_recebimento`, `_extrair_anexos`): 0% dependência de estado

**Testes (12 testes novos, zero falhas):**

- `test_magnata_os_documental_modulo01_email_gmail_readonly.py` (9 testes)
  - Escopo travado em readonly
  - Credencial ausente levanta erro
  - Label não encontrada levanta erro
  - Anexo via attachmentId / inline
  - Mensagens sem anexo
  - Múltiplas mensagens
  - **Prova adversarial: cliente nunca chama método de escrita** (duplo só tem métodos de leitura)
  - Recurso injetado sempre via lambda testável

- `test_magnata_os_documental_modulo01_email_integracao_gmail.py` (3 testes)
  - ClienteGmailReadOnly + AdapterCapturaEmail: processa 2 e-mails, gera 2 lotes
  - Mensagem sem anexo é contabilizada mas não gera lote
  - Múltiplos anexos por mensagem registrados corretamente

- Regressão verificada: 10 testes originais de `email_captura.py` continuam passando (zero quebra)

**requirements.txt** atualizado:
```
google-api-python-client==2.149.0
google-auth==2.35.0
```
(Pinadas, comentadas, marcadas como Fase 1/inerte)

## Garantias de segurança/inércia

✅ **Escopo OAuth**: travado em código para `gmail.readonly` (nunca ampliado por parâmetro)
✅ **Nenhuma credencial real**: `carregar_credenciais_gmail_readonly()` levanta erro sem um caminho real
✅ **Nenhuma rede**: imports de `googleapiclient`/`google.oauth2` são locais (dentro das funções), nunca no topo
✅ **100% testável**: `construir_recurso` injetável; todos os 12 testes usam duplo
✅ **Nenhuma escrita**: duplo do Gmail testa que NUNCA métodos de escrita são chamados
✅ **Implementação simples**: não tem retry/backoff (por desenho — vai ficar fora do adapter, em quem chamar), fail-loud

## Próxima ação: Fase 2 (bloqueada até autorização)

Para conectar este cliente a um Gmail real (Fase 2 do plano `plano-modo-sombra-captura-email.md`):

1. **Autorização de fase explícita** cumprindo `CLAUDE.md` §6(a)-(f) — nenhuma resposta ambígua autoriza isto
2. Emitir um OAuth token real com escopo `gmail.readonly` apenas
3. Passar o caminho do token a `carregar_credenciais_gmail_readonly(caminho_token)`
4. Instanciar `ClienteGmailReadOnly(label='...', credenciais=creds)`

Até lá, este código fica **100% inerte**. Nenhum test, nenhuma produção, nenhuma integração contínua toca Gmail de verdade.

## Documentação relacionada

- `docs/decisoes/plano-modo-sombra-captura-email.md` — plano completo (Fase 0-4)
- `magnata_os/documental/modulo01/adapters/email_captura.py` — adapter que usa o cliente (Protocol)
- `magnata_os/CLAUDE.md` — regras de pureza de domínio e adapter isolation
- `CLAUDE.md` §6 — autorização de fase para escrita externa (Gmail é externa)

## Gate: Revisar antes de qualquer Fase 2

Esta implementação está pronta para:
- ✅ Revisão de código (pull request + aprovação)
- ✅ Mergue em `main`
- ❌ Execução real (Fase 2, bloqueada, exige autorização nova)

Qualquer Fase 2 reinicia o gate com autorização explícita — não pode ser autorizada pela aprovação desta Fase 1.
