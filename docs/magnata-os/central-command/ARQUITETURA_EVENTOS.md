# ARQUITETURA DE EVENTOS — o padrão, e o único caso real que o segue hoje

**Etapa 12, 2026-08-23.** Requisito e desenho, não motor implementado.
Formaliza um padrão que já existe em código — `email_captura.py`,
mesclado no PR #22 — para que a próxima fonte a integrar (Apps Script,
Evolution, um sensor de produção) siga a mesma forma, em vez de cada
adapter reinventar a própria.

---

## 1. O padrão

```
FONTE EXTERNA → ADAPTER → EVENTO NORMALIZADO → SERVIÇO/MÓDULO → ESTADO → ORQUESTRADOR
```

| Estágio | Responsabilidade | O que NUNCA faz |
|---|---|---|
| **Fonte externa** | Sistema real (Gmail, Airtable, Render, Evolution) | Não sabe nada do Magnata OS |
| **Adapter** | Traduz o formato da fonte para um tipo próprio do domínio (`Protocol`, sem driver importado) | **Nunca** contém lógica de negócio — nunca decide "isto é holerite", nunca escreve em duas fontes, nunca reprocessa por conta própria |
| **Evento normalizado** | Estrutura imutável, sem dependência de biblioteca externa | Não carrega bytes/estado de conexão — só o que o domínio precisa |
| **Serviço/módulo** | Aplica regra de negócio, idempotência, transição de estado | Não fala com a fonte externa diretamente |
| **Estado** | Persistido, consultável, com histórico append-only | Não é reconstruído a partir de inferência — só de eventos reais |
| **Orquestrador** | Consulta o estado consolidado, decide se registra/propõe/executa/pede gate — ver `MATRIZ_AUTONOMIA.md` | **Não existe como motor em execução hoje** — ver §3 |

## 2. O único caso real que já segue o padrão inteiro (até o Estado)

`AdapterCapturaEmail` (`magnata_os/documental/modulo01/adapters/email_captura.py`,
mesclado no PR #22):

```
Gmail/IMAP real (ainda não conectado)
   │  FonteMensagensEmail (Protocol — zero import de driver)
   ▼
AdapterCapturaEmail.capturar_novas_mensagens()
   │  MensagemEmailRecebida / AnexoEmailRecebido (dataclasses imutáveis)
   ▼
ServicoCriacaoLote.criar_lote()  ← porta oficial de entrada do Módulo 01
   │
   ▼
Documento (append-only, idempotente por hash SHA-256)
```

Isto **para no Estado** — não há Orquestrador consumindo esse estado
ainda (não existe motor, ver §3). E o Adapter **não está conectado a
nenhuma fonte real** — é o padrão provado com um duplo de teste, não em
produção.

## 3. O que falta para o padrão fechar até "Orquestrador"

Nenhum componente deste repositório hoje:

1. observa o Estado mudar (não há *listener*/*trigger* sobre `Documento`
   novo, `EventoHistorico` novo, ou `ESTADO.json` do sensor mudando);
2. classifica a mudança por criticidade automaticamente;
3. decide entre `AUTO_FACT`/propor/executar/gate sozinho, sem uma sessão
   no meio interpretando.

Isso é o "motor" que a missão desta etapa pede (§16). **Não foi
construído nesta etapa** — construir um motor real (mesmo mínimo)
significa decidir: onde ele roda (processo contínuo? Job de CI? Handler
HTTP?), quem o aciona, e como ele nunca duplica o que o legado `app.py`
já faz para o mesmo evento. São 3 decisões arquiteturais que a missão
autorizada não resolve sozinha — cada uma tem efeito prático em
produção ou infraestrutura, o que `CLAUDE.md` §12-I trata como gate.
Prefiro registrar isso explicitamente a fingir um motor que na prática
seria só um script chamado manualmente com um nome mais grandioso.

## 4. Fontes reais mapeadas contra o padrão — estado de cada uma

| Fonte | Onde entra hoje | Segue o padrão? | Observação |
|---|---|---|---|
| **Gmail (captura de e-mail)** | `apps_script_email_intake.gs` → `/email/webhook` (`app.py`, legado) | 🟡 Parcial — o legado mistura captura+classificação+persistência numa rota só, sem separação Adapter/Evento/Serviço | `AdapterCapturaEmail` é o começo do caminho para separar isso, ainda não conectado |
| **Airtable (dado operacional)** | Lido/escrito direto em dezenas de pontos de `app.py`; `magnata_os/` só via `adapters/airtable_*.py` | 🟡 Parcial — `app.py` não segue o padrão (legado); `magnata_os/` segue (adapters isolados) | Ver `AIRTABLE_DESACOPLAMENTO.md` para o plano de saída |
| **Evolution API (WhatsApp)** | Chamado direto de dentro de `app.py` | 🚫 Não segue — é chamada direta, não evento | Fora de escopo desta etapa |
| **Make.com** | Cenário externo, `customScript`, ativo, sem `try/catch` conhecido (RSK-014 histórico) | 🚫 Não segue — nem é deste repositório | Ver `AIRTABLE_LOGICA_OCULTA.md` ANEXO B |
| **Render (produção)** | Nenhum consumo automático — rede bloqueada desta sessão | 🔴 Não verificável | Ver `ORQUESTRADOR.md` §6.2 |
| **GitHub (PR/CI/branch)** | Consultado **por sessão**, via ferramenta interativa (`pull_request_read`, `get_check_runs`) | 🟡 Parcial — segue o padrão só enquanto uma sessão está ativa; nenhum script do repositório o faz sozinho | Ver `MATRIZ_AUTONOMIA.md` §4 |

## 5. Regra de convivência — nunca duplicar processamento

Todo adapter novo que cobrir uma fonte já coberta pelo legado precisa,
por desenho, responder **antes** de existir:

1. Ele **substitui** o caminho legado (gate humano — decisão de
   negócio) ou **roda em paralelo**, sem side-effect visível
   (WhatsApp, e-mail, escrita real), até decisão de substituição?
2. Se paralelo: como garantir que o mesmo evento não vira dois
   `Documento`/duas mensagens enviadas? Resposta hoje, para e-mail:
   idempotência por hash de conteúdo no Módulo 01 previne duplicar o
   *registro*; **não previne** dois disparos de WhatsApp se dois
   caminhos decidirem agir sobre o mesmo documento — isso continua
   sendo responsabilidade de quem decide ativar um adapter novo, não
   do adapter em si.

`AdapterCapturaEmail` responde a 1 explicitamente na própria docstring
("roda em paralelo, não substitui, não desliga o Apps Script") e não
precisa responder a 2 ainda porque não está conectado a nada real.
