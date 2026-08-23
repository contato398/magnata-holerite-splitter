# Plano — Consolidação do fluxo Email → Classificação → Airtable → Revisão → Distribuição (WhatsApp/E-mail)

**Branch:** `claude/evolution-api-instances-1s9raa`
**Data:** 2026-08-17
**Status:** Plano de direção aprovado nesta mesma branch — a "próxima
ação concreta proposta" (adapter de e-mail, §"Próxima ação concreta
proposta") **foi implementada** junto com este plano
(`magnata_os/documental/modulo01/adapters/email_captura.py`), em
paralelo ao Gmail Apps Script, sem tocar `app.py`. Continua **sem
nenhuma escrita real** — não conectado a caixa de e-mail real, não
substitui o Apps Script, não liga a Airtable — e a decisão de quando
ligar a uma fonte real continua exigindo autorização de fase separada
(`CLAUDE.md` §6/§12-I). Atualizado nesta nota — não reescrito — na
auditoria/reconciliação de 2026-08-23.

## Contexto

Dinâmica de negócio confirmada pelo usuário: documentos chegam por e-mail
(folha de ponto, contrato de experiência/admissional, rescisão, holerite),
precisam ser identificados, separados, salvos, revisados por humano e só
então encaminhados — normalmente por WhatsApp para o colaborador, e por
e-mail para o cliente/contratante (documentos do mês + certidões, guias,
comprovante de pagamento).

Diagnóstico já registrado em conversa nesta sessão: um cenário no
Make.com (Airtable → Gmail → HTTP para Evolution API) tentava reconstruir
esse fluxo por fora, mapeando o e-mail do remetente como número de
WhatsApp — erro técnico, e sintoma de um problema maior: o fluxo real já
existe em dois lugares (legado `app.py` em produção, e o novo
`magnata_os/documental/modulo01/` em construção) e um terceiro caminho
avulso no Make não se conecta a nenhum dos dois.

## Estado atual (confirmado por leitura de código nesta sessão, não presumido)

### Legado `app.py` — único caminho ponta-a-ponta funcionando hoje

Cobre o fluxo inteiro descrito pelo usuário, já em produção:

| Etapa | Rota(s) |
|---|---|
| Captura de e-mail | `/email/webhook`, `/email/alerta-formato-invalido` |
| Identificar/separar | `/separar`, `/separar/zip`, `/processar-holerites`, `/processar-folha-ponto`, `/processar-doc-cliente`, `/processar-guia`, `/processar-recibos`, `/processar-beneficios*`, `/processar-vr-va` |
| Fila de revisão | `/status-documentos`, `/diagnostico-holerites`, `/processar-fila`, `/tarefas/<id>` |
| Ordem de encaminhar | `/gerar-fila-envios*` (ponto, combinado, e-mail) |
| Disparo WhatsApp | `/disparar-fila-combinado`, `/whatsapp/enviar-texto`, `/webhook/enviar-whatsapp`, `/evolution/status` |
| Disparo e-mail ao cliente | `/disparar-fila-email`, `/webhook/enviar-email-cliente` |
| Assinatura | `/assinatura/gerar`, `/assinatura/gerar-lote`, `/assinatura/processar-reenvios` |

Número de WhatsApp já normalizado corretamente a partir do campo
`Funcionários.WhatsApp` do Airtable (`app.py:1811`,
`_normalizar_telefone_br` / `_normalizar_numero_evolution`) — **não** a
partir do e-mail do remetente.

**Fraqueza reconhecida e já documentada** (não descoberta agora):
`MAGNATA_OS_CAPACIDADES.md` §3.1 classifica "Recebimento de e-mail" como
maturidade 3 ("Legado operacional via Gmail Apps Script", risco Alto) e
"Armazenamento temporário" como maturidade 3 ("Legado via Airtable,
tabela Arquivos", risco Alto). Isso é exatamente o "o Airtable falha
muito, inclusive na captura dos e-mails" relatado pelo usuário.

### Novo `magnata_os/documental/modulo01/` — fundação da esteira, ainda não cobre email/classificação/distribuição

Confirmado por leitura de `MAGNATA_OS_DOCUMENTAL_MODULO01.md` e do
código (`dominio.py`, `servico_entrada.py`, `repositorio.py`, mais
`servico_lote.py`, `dominio_esteira.py`, `servico_avanco_esteira.py`,
`consultas_esteira.py`, `adapters/` com Postgres e S3, `api/` com
handlers/contratos/autorização já mesclados até a Fase 4):

- Já resolve, de forma testada e correta: modelo `Documento` imutável,
  histórico de eventos append-only, idempotência por hash SHA-256,
  máquina de estados oficial (`RECEBIDO` → `REGISTRADO` →
  `DUPLICADO`/`AGUARDANDO_PROCESSAMENTO`/`EM_PROCESSAMENTO`/`EM_REVISAO`/`ERRO`),
  adapters de persistência (Postgres) e armazenamento (S3) desenhados
  por contrato.
- **Explicitamente ainda não faz** (declarado no próprio doc da Fase 1,
  nunca revogado por nenhuma fase seguinte lida nesta sessão): captura
  de e-mail, OCR, classificação de tipo documental, fatiamento/separação,
  vínculo a colaborador/cliente, envio por e-mail/WhatsApp, qualquer
  escrita real no Airtable.
- Ou seja: hoje é a fundação de **Ingestão** (Módulo 1 de
  `MAGNATA_OS_MODULOS.md`), mas ainda não tem adapter que substitua o
  Gmail Apps Script, e não chega perto de **Distribuição** (Módulo 7).

### Roadmap oficial (`MAGNATA_OS_ROADMAP.md`) — divergência já registrada, não nova

O roadmap formal prevê Ingestão só na Fase 3 (~out/2026) e Distribuição
só na Fase 9 (~jul/2027), mas o código do Módulo 01 já avançou mais
rápido na prática (Fase 2–4 mescladas). Essa divergência entre plano e
código já é reconhecida no índice de documentação
(`docs/magnata-os/README.md` §"Quem prevalece em caso de conflito",
item 1: código implementado prevalece sobre o plano, divergência deve
ficar registrada — o que este documento está fazendo agora).

## Recomendação — ordem de trabalho

1. **Não construir nada novo no Make.com.** Qualquer necessidade de
   automação nova entra por `app.py` (se é operação do dia a dia, usando
   o padrão já validado — ex.: campo `WhatsApp` do Airtable, nunca
   e-mail do remetente) ou é desenhada dentro de `magnata_os/` (se é
   parte da reconstrução definitiva). Isso não exige código agora — é
   uma regra operacional a partir de hoje.
2. **Priorizar o Módulo de Ingestão assumir a captura de e-mail**,
   porque é a causa raiz relatada ("nunca funcionou direito"): construir
   um adapter de e-mail (substituto do Gmail Apps Script) que alimenta
   `ServicoEntradaDocumental.registrar_entrada()` já existente — sem
   tocar em `app.py`, rodando em paralelo, comparável por hash contra o
   que o legado captura hoje (mesmo padrão do handoff de importação em
   lote já validado em `MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md`).
3. **Só depois, Classificação** (tipo de documento + vínculo a
   colaborador/cliente) — hoje maturidade 2 ("Identificada, não
   automatizada"), é o módulo que decide "isto é holerite de fulano" e
   hoje é 100% humano/heurístico dentro de `app.py`.
4. **Distribuição continua 100% legado até ter substituto testado** —
   não há atalho: enquanto Fase 9 não chega, `app.py` continua
   sendo o único caminho de envio real de WhatsApp/e-mail. Não faz
   sentido migrar Distribuição antes de Ingestão/Classificação
   estarem prontos — inverteria a ordem de dependência já declarada em
   `MAGNATA_OS_MODULOS.md` §11 (Distribuição depende de Documentação,
   que depende de Ponto/RH/Cadastro, que depende de Classificação, que
   depende de Ingestão).

## Gates que continuam humanos (não dispensados por este plano)

Por `CLAUDE.md` §6 e §12-I: qualquer escrita real no Airtable, qualquer
migration/schema novo, qualquer deploy, qualquer alteração em `app.py`,
e a decisão de quando cada fase nova entra em produção continuam
exigindo autorização específica, numa mensagem distinta da que aprovou
este plano. Este documento registra a decisão de **direção**; não é
autorização de fase para nenhuma escrita externa.

## Próxima ação concreta proposta

Implementar, em branch própria e sem tocar em `app.py`, um adapter de
e-mail para o Módulo 01 (`magnata_os/documental/modulo01/adapters/`)
que alimenta `ServicoEntradaDocumental` — rodando em paralelo ao Gmail
Apps Script, sem substituí-lo ainda, com testes comparando os dois.
Aguardando confirmação para iniciar essa implementação.
