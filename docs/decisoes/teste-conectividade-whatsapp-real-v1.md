# Decisão — Teste de Conectividade WhatsApp Real V1

**Branch:** `fix/teste-conectividade-whatsapp-real-v1`
**Data:** 2026-10-01
**Status:** Script construído e testado (dublê em memória, zero rede
real). NENHUMA mensagem real foi enviada nesta missão — o disparo real
é manual, feito pelo próprio usuário (dono do produto), depois do
merge.

## 1. Objetivo

Confirmar que o canal de transporte WhatsApp real (Evolution) funciona
fisicamente — credencial certa, número certo, mensagem chega — antes
de qualquer disparo de canário nominal com pipeline de evento/
assinatura por trás. Sem documento, sem assinatura, sem outro
destinatário além do próprio número do usuário.

## 2. Autorização de fase

Esta missão foi autorizada pelo usuário (dono do produto) numa
mensagem distinta daquela que redigiu/propôs este trabalho — requisito
(e) de `CLAUDE.md` §6 cumprido. O escopo autorizado foi
especificamente: construir o script e, SEPARADAMENTE, o próprio
usuário rodá-lo manualmente mais tarde para enviar exatamente 1
mensagem de texto real, só para o seu próprio número. Nenhuma outra
classe de escrita externa (Airtable, e-mail, outro destinatário de
WhatsApp, deploy, migration) foi autorizada por esta fase.

Esta tarefa (construção) não exercita a autorização — nenhuma chamada
de rede real foi feita, nenhuma variável de ambiente real foi
configurada. O primeiro efeito externo real só pode acontecer quando o
usuário, já com o PR mesclado, exportar manualmente
`ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO=1` no seu próprio ambiente e
rodar o script — nunca a partir desta sessão.

## 3. Por que é diferente do canário nominal (`executar_canario_v1.py`)

`executar_canario_v1.py` (Etapa C, já em produção) opera sobre um par
`(event_id, preview_id)` real do pipeline de eventos — reivindica a
próxima ação persistente, observa transição de assinatura, tem
`CanarioNaoConfiguradoError` para placeholders de ID. Ele existe para
validar o fluxo de negócio completo (documento → envio → assinatura).

Este script (`scripts/testar_conectividade_whatsapp_real_cli.py`) não
tem nenhum evento, ação, documento ou obrigação de assinatura por
trás — é só uma chamada direta a `enviar_texto` com um número e um
texto informados na hora pelo operador via CLI. Não reivindica ação
persistente, não observa assinatura, não lê nenhum repositório
Postgres. Reaproveita exatamente a mesma composição de transporte
(`compor_transporte_evolution_real`) e a mesma função de decisão
(`transporte_real_habilitado`) — nenhuma lógica HTTP, autenticação ou
decisão de barreira é duplicada ou reimplementada.

## 4. As 3 barreiras preservadas, sem bypass

```
REAL = AUTORIZACAO_ESTRUTURAL_TESTE_CONECTIVIDADE_V1 is True
       AND ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO == "1" (exato)
       AND NOT ORQUESTRADOR_DRY_RUN (veto)
```

- **Barreira 1 (estrutural, própria deste script):**
  `AUTORIZACAO_ESTRUTURAL_TESTE_CONECTIVIDADE_V1 = True`, constante
  literal em `scripts/testar_conectividade_whatsapp_real_cli.py`,
  revisável só via PR, nunca lida de ambiente — mesmo padrão de
  `executar_canario_v1.AUTORIZACAO_ESTRUTURAL_CANARIO_V1`. Não
  substitui as barreiras 2 e 3; é só o argumento explícito
  `autorizar_transporte_real` passado para
  `transporte_real_habilitado`.
- **Barreira 2 (operacional positiva):** decidida inteiramente dentro
  de `autorizacao_transporte_real.transporte_real_habilitado` —
  arquivo NÃO tocado, só consumido por import, exigindo o valor exato
  `ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO == "1"`.
- **Barreira 3 (veto dry-run):** idem, `ORQUESTRADOR_DRY_RUN` bloqueia
  sempre, independente das outras duas — mesma função, nenhuma cópia.

Se `transporte_real_habilitado(...)` retorna `False`, o script levanta
`TransporteRealNaoHabilitadoError` e termina — **nenhuma composição de
transporte, nenhuma chamada HTTP é tentada**.

## 5. O que o script faz, exatamente

1. CLI (`--numero` obrigatório, `--texto` opcional com default de
   mensagem de teste identificável) — nunca lê número de nenhuma fonte
   automática, nunca aceita lista, nunca itera.
2. Valida o formato do número (`+` opcional + 8 a 15 dígitos) —
   fail-closed: formato inválido recusa antes de qualquer tentativa de
   composição/envio.
3. Chama `transporte_real_habilitado(autorizar_transporte_real=True)`.
4. Só se `True`: compõe `compor_transporte_evolution_real()` (função
   já existente, reaproveitada sem alteração) e chama
   `.enviar_texto(numero=..., texto=...)` exatamente 1 vez.
5. Mostra o ID externo retornado pela Evolution (evidência de
   sucesso) — nunca o número completo em texto puro; o número é
   mascarado (só os 2 últimos dígitos, mesmo princípio de
   `app.py:_mascarar_cpf`).

## 6. O que continua proibido nesta fase

- Nenhuma lista de números, nenhuma iteração, nenhum lote.
- Nenhuma alteração em `autorizacao_transporte_real.py` (consumido
  apenas via import).
- Nenhuma alteração em `app.py` (não importado, não tocado).
- Nenhuma migration nova ou aplicada.
- Nenhuma referência em cron, scheduler ou `render.yaml` — invocação
  manual apenas.
- Nenhuma variável de ambiente real configurada por esta sessão.
- Nenhuma chamada de rede real nesta missão — todos os 19 testes usam
  um dublê de `PortaTransporteWhatsapp` em memória.

## 7. Validação técnica

- 19/19 testes novos verdes
  (`test_testar_conectividade_whatsapp_real_cli.py`): barreira 2
  ausente (zero chamada HTTP), barreira 3 vetando mesmo com barreira 2
  presente, barreira 2 com valor não-exato, as duas barreiras
  liberadas (exatamente 1 chamada a `enviar_texto` com os argumentos
  exatos), validação de número inválido (vários formatos), resposta
  sem ID externo, e confirmação de que o número completo nunca aparece
  em texto puro em stdout nem em log capturado (só mascarado).
- Suíte geral: sem regressão (ver relatório de execução da missão).

## 8. Próxima etapa

Após merge: o usuário, no seu próprio ambiente, exporta manualmente
`ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO=1` (nunca a partir desta
sessão) e roda o script uma vez, com o próprio número. Isso encerra o
teste de conectividade — não habilita nenhuma automação contínua, não
altera `ciclo_producao_v1.main()` (que continua com
`autorizar_transporte_real=False`).
