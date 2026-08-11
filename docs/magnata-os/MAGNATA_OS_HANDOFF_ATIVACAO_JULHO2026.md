# Handoff executável — Ativação real da esteira documental (Julho/2026)

Runbook para uma sessão/ambiente com acesso efetivo a Render (Postgres)
e escrita real no Airtable concluir a ativação já implementada,
testada e revisada nesta sessão. Esta sessão **não tem** ferramenta de
provisionamento Render/Postgres e **decidiu não executar** escrita real
no Airtable — ver `CLAUDE.md` §6 e o histórico de decisão desta fase.
Este documento é o produto do trabalho que *pôde* ser concluído aqui:
tudo verificado, congelado e pronto para execução mecânica em outro
lugar.

**Nada neste documento contém CPF, nome de funcionário real,
`DATABASE_URL` ou segredo.** Onde uma referência a dado real é
necessária, é sempre por ID de registro Airtable (não-PII) ou por
contagem agregada.

## 0. Pré-requisitos de quem for executar isto

- Acesso ao Render com permissão para provisionar um Postgres gerenciado.
- Acesso de escrita ao Airtable (base `appaCpIVj7Q97VhFy`), tabelas
  `Holerites` (`tblVaUgZeFfa5zRcH`) e `Extratos Mensais`
  (`tblJCUcFBVTH5W2kP`).
- Este repositório, branch `claude/magnata-email-reconciliation-hru0jm`,
  com os commits `29aca4c`, `884bf67`, `80bf8f6`, `ae101c4`, `e3eb40d`
  aplicados (verificar com `git log --oneline -6`).
- O pacote de Julho/2026 (ver §2 — hash obrigatório de conferir antes
  de prosseguir).
- Autorização por fase já concedida nos termos de `CLAUDE.md` §6 (esta
  sessão já recebeu e documentou essa autorização — ver histórico de
  commits `e3eb40d` e a troca de mensagens que a precedeu).

## 1. Estado local confirmado nesta sessão (evidência, não presunção)

- `app.py`, `frontend/`, migrations `0001`-`0008`: diff zero confirmado.
- Suíte geral: 381 passed / 5 failed — as 5 falhas são pré-existentes em
  `app.py` (`test_fase_c_async_separar.py`,
  `test_fila_envios_v2_23.py`, `test_sanitizacao_v2_20.py`×3), zero
  regressão nova introduzida por esta fase.
- Módulo de importação em lote: 75/75 (dry-run 30 + escrita 45).
- `CLAUDE.md` §6 corrigido e consolidado (commit `e3eb40d`) — mecanismo
  de autorização por fase, com salvaguarda de confirmação em mensagem
  distinta.

## 2. Fonte documental — reconfirmada nesta sessão, hoje

| Item | Valor | Como foi confirmado |
|---|---|---|
| Gmail message | `19fcd0ad97d9fac8` | referência histórica já validada em fase anterior (Gate 1); não re-lida nesta rodada |
| Pacote (arquivo local) | `Documentos_Julho_2026__Organizados__Pacote_Completo.zip` | presente em `/root/.claude/uploads/2be82269-b045-528f-bc3d-567e9a825bdf/7ec9f2ba-Documentos_Julho_2026__Organizados__Pacote_Completo.zip` nesta sessão — **não existe fora dela**; quem executar o handoff precisa obter o pacote de novo (Drive ID `1YZmpkCqiGVoZoIZB_u93Ju7o9FVDZA7s`) e recalcular o hash |
| `package_sha256` esperado | `2ec28209274afb1a255c6fe2d31f889413387e20fcc4d5e56006a2def74ce404` | recalculado agora nesta sessão via `pacote.calcular_sha256_arquivo` — **bateu** com o hash já validado no Gate 1 histórico |
| Competência canônica | `recsSyWoh5HzM3o2p` — Folha Mensal "Julho 2026", Data "2026-07-01" | lido agora (leitura real, Airtable), campo de duplicidade = "Não" |
| Competência duplicada (NUNCA usar/alterar) | `recmR7Pae0YxWpo0q` — Data "2026-07-05", campo de duplicidade = "Sim" | lido agora, confirmado que é a mesma registrada como duplicada nas fases anteriores — **não tocado** |
| `message_id_estavel` desta execução | `19fcd0ad97d9fac8` | herdado da configuração já validada — nunca reconstituído a partir de texto de data |

**Se o hash recalculado não bater** com o valor acima ao obter o pacote
de novo: PARE. Isso é divergência de fonte da verdade (gate real, não
bloqueio técnico) — não seguir com um pacote diferente do já validado.

## 3. Dry-run — reconfirmado nesta sessão com leitura AO VIVO do cadastro

Executado agora (não reaproveitado cegamente do dry-run de 07/08):
releitura completa de Funcionários (159 registros) e Clientes (28
registros) via Airtable, releitura de dedup (Holerites/Extratos já
existentes na folha "Julho 2026" = **zero em ambas as tabelas**),
reclassificação completa dos 135 itens do manifesto.

**Resultado — idêntico item a item ao dry-run de 07/08/2026** (cadastro
não mudou: 0 funcionários adicionados/removidos, 0 clientes
adicionados/removidos, 0 documentos pré-existentes na folha):

| Métrica | Valor |
|---|---|
| Total de itens no manifesto | 135 |
| Holerites processados | 114 |
| Extratos processados | 21 |
| Relatórios gerais excluídos do fluxo | 3 (`ExtratoServiço_Julho2026_ORIGINAL_COMPLETO.pdf`, `RelatoriodeLiquidos_Julho2026.pdf`, `RelatoriodeLiquidos_Julho2026.pdf`) |
| `exact` (prontos para gravação) | 114 (97 holerites + 17 extratos) |
| `not_found` (fila de exceção — NUNCA automatizar) | 21 |

**Este número (114) é o resultado de uma verificação de hoje, não uma
constante travada.** Se `04.` mudar o cadastro entre agora e a
execução real, refaça a leitura + classificação (script abaixo) antes
de escrever qualquer coisa.

### Script de referência (reexecutável)

O script usado está preservado em
`/tmp/.../scratchpad/dry_run/executar_dry_run.py` **desta sessão** (não
sobrevive a ela) e é reproduzido em essência abaixo — quem executar o
handoff deve reconstituí-lo ou pedir para a próxima sessão gerar um
equivalente, sempre contra o pacote/hash validados em `§2`:

```python
from magnata_os.documental.importacao_lote.contratos import (
    CandidatoCliente, CandidatoFuncionario, ConfiguracaoExecucao)
from magnata_os.documental.importacao_lote.adapters import pacote
from magnata_os.documental.importacao_lote.orquestrador import (
    processar_extrato, processar_holerite)
from magnata_os.documental.importacao_lote import dominio

config = ConfiguracaoExecucao(
    mes_cont_id='recsSyWoh5HzM3o2p', ano=2026, mes=7,
    message_id_estavel='19fcd0ad97d9fac8',
    package_sha256=pacote.calcular_sha256_arquivo(ZIP_PATH),  # deve bater com §2
    mes_cont_id_duplicado_bloqueado=('recmR7Pae0YxWpo0q',),
)
# candidatos_funcionario / candidatos_cliente: ler ao vivo via Airtable
# MCP (TABLE_FUNC=tblNd8G66kjwos3eP, TABLE_CLIENTES=tbl0znyuCEzoCHtCV)
# — NUNCA reaproveitar leitura de mais de poucas horas atrás sem
# reconfirmar. Dedup (func_ids_ja_com_holerite / cliente_ids_ja_com_extrato):
# reler holerites/extratos já existentes na folha "Julho 2026" antes de
# cada execução real.
```

## 4. Canário — candidato selecionado (determinístico, sem PII)

Selecionado pelo primeiro holerite `exact` em ordem numérica de página
do manifesto — critério determinístico, reprodutível, não é uma
escolha subjetiva:

```json
{
  "manifesto_item_id": "holerite:1",
  "tipo_documental": "holerite",
  "classificacao": "exact",
  "pronto_para_gravacao": true,
  "entidade_resolvida": "recOveUljAAQIs6qU",
  "identidade_documental_truncada": "80ef025eec87",
  "motivo": "ok",
  "criterio_usado": "cpf_exato"
}
```

Verificado antes da seleção: `recOveUljAAQIs6qU` (Funcionário) **não**
tem holerite existente na folha "Julho 2026" (dedup zero confirmado em
`§3`) — o canário vai exercitar o caminho completo `criar_registro` +
`anexar_pdf` + `confirmar_attachment`, não um caminho de reuso.

## 5. Passo a passo — Postgres real

1. No Render, provisionar **um** Postgres gerenciado dedicado ao
   Magnata OS (nome sugerido: `magnata-os-db`, mesmo nome já declarado
   em `render.yaml`). Escolher o menor plano tecnicamente adequado que
   **não implique nova contratação/despesa não previamente
   autorizada** — se toda opção disponível implicar despesa nova, isso
   é gate financeiro real (`CLAUDE.md` §6-b, critérios de interrupção)
   e para aqui até decisão humana.
2. Obter a connection string com segurança — nunca colar em log, chat,
   commit ou neste documento.
3. Confirmar que é o banco **novo**, vazio (`SELECT count(*) FROM
   information_schema.tables WHERE table_schema='public';` deve
   retornar próximo de zero antes de aplicar qualquer migration).
4. Aplicar as migrations, em ordem, **nunca editando as antigas**:
   `0001` → `0002` → `0003` → `0004` → `0005` → `0006` → `0007` →
   `0008` → `0009_itens_importacao_lote.sql`. O rollback de `0009`
   existe em `0009_itens_importacao_lote_rollback.sql` — não usar
   contra dados reais depois que o canário/lote começar (só antes, se
   for útil validar migration+rollback num recurso efêmero primeiro).
5. Health check (todos sintéticos, removidos ao final — banco tem que
   ficar limpo):
   - `SELECT 1`;
   - conferir existência de `documentos`, `eventos_documentais`,
     `lotes_documentais`, `estados_esteira_documental`,
     `itens_importacao_lote`, `documentos_versionamento_logico`,
     `eventos_itens_importacao_lote`, e os índices/triggers de cada
     migration;
   - inserir um `Documento` sintético (hash falso, nunca um hash real
     do pacote), um evento em `eventos_documentais`, tentar
     `UPDATE`/`DELETE` nesse evento e confirmar que a trigger da
     migration `0003` rejeita;
   - inserir um `ItemExecucao` sintético + 2-3
     `EventoItemExecucao` (via `repositorio_execucao`/
     `postgres_execucao`, não SQL cru) simulando uma transição
     PENDENTE→EM_PROCESSAMENTO→SUCESSO, e reconstituir a sequência só a
     partir de `eventos_itens_importacao_lote` (mesma prova que
     `test_correcao_H_*` já faz em memória — repetir contra o banco
     real valida que o comportamento é o mesmo);
   - `DELETE`/rollback de **tudo** que foi inserido nesta etapa antes
     de prosseguir para o canário real.
6. **Não** injetar `DATABASE_URL` nos serviços web/worker do Render
   nesta fase — isso provocaria redeploy fora do escopo autorizado. A
   execução real (canário + lote) roda a partir da sessão de execução
   segura (local/CLI), usando `magnata_os.documental.modulo01.adapters.conexao.abrir_conexao(database_url=...)`
   diretamente — nunca via variável de ambiente dos serviços Render
   nesta fase.

## 6. Passo a passo — canário real

Usar exatamente `escritor.escrever_item(...)` (assinatura em
`magnata_os/documental/importacao_lote/escritor.py`), com:

- `repositorio_documentos` / `repositorio_historico`: adapters Postgres
  (`magnata_os/documental/modulo01/adapters/postgres_repositorio.py`)
  contra a conexão real;
- `repositorio_itens` / `repositorio_eventos_item` /
  `repositorio_versionamento`: adapters Postgres
  (`magnata_os/documental/importacao_lote/adapters/postgres_execucao.py`);
- `escritor_airtable`: `EscritorAirtable(api_key=...)` de
  `adapters/airtable_escrita.py`, API key nunca em texto/log;
- `resultado`: o item `holerite:1` do dry-run reconfirmado em `§4`;
- `pdf_bytes`/`nome_arquivo`: lidos do pacote validado (`pacote.ler_pdf_holerite_bytes`);
- `nome_referencia`: nome do manifesto para este item — só passa
  adiante para o Airtable, nunca persistido/logado (mesma disciplina
  já testada em `test_correcao_I_eventos_item_nunca_contem_pii`).

Critérios de aprovação automática do canário (só prosseguir para `§7`
se **todos**):

- `ResultadoEscrita.situacao == SUCESSO`;
- `attachment_confirmado == True` no `ItemExecucao` persistido;
- releitura do registro no Airtable confirma o PDF anexado;
- `eventos_itens_importacao_lote` reconstitui a sequência completa
  (PENDENTE → ... → SUCESSO) sem lacuna;
- nenhum evento contém PII (checar `detalhes` manualmente uma vez);
- nenhuma duplicata criada (só 1 registro Airtable para este
  `entidade_resolvida` na folha "Julho 2026").

Se falhar: classificar (infraestrutura transitória / bug de código /
dado específico do candidato / falha sistêmica) e seguir exatamente o
protocolo já especificado no histórico desta fase — nunca forçar o
lote com o canário em estado ambíguo.

## 7. Passo a passo — lote dos itens seguros

Iterar sobre os 114 itens `exact`/`pronto_para_gravacao` do dry-run
reconfirmado (`§3`), chamando `escrever_item` um a um, cada um com seu
próprio `lote_id` (ou todos sob o mesmo `lote_id` da execução — decisão
de quem executa, ambas as formas são suportadas pela cardinalidade da
migration `0009`). Checkpoint automático por item via
`ItemExecucao`/`eventos_itens_importacao_lote` — uma queda no meio
retoma sozinha numa nova chamada.

Nunca processar os 21 `not_found` automaticamente — ficam de fila de
exceção, fora deste handoff.

## 8. Reconciliação final

Cruzar: manifesto (135) × dry-run reconfirmado × Postgres
(`itens_importacao_lote` + `documentos`) × Airtable (Holerites +
Extratos da folha "Julho 2026"). Todo item deve ter uma situação
terminal explicável — nenhum pode "sumir". Consulta de referência:

```sql
SELECT situacao, count(*) FROM itens_importacao_lote
WHERE lote_id = '<lote_id da execução>'
GROUP BY situacao;
```

somada aos 21 `not_found` (nunca entram nesta tabela, ficam só no
relatório do dry-run) deve somar 135.

## 9. O que este handoff NUNCA autoriza

`push`, `PR`, `merge`, `deploy`, envio de e-mail/WhatsApp reais,
alteração de Apps Script, alteração de `app.py`, criação automática de
funcionário/cliente, resolução automática dos 21 `not_found`,
alteração da competência duplicada ou dos processos históricos
travados. Tudo isso permanece exatamente como já registrado em
`CLAUDE.md` e nas fases anteriores desta mesma sessão.

## 10. Próximo gate constitucional

Depois de concluído: `push`/`PR`/`merge`/`deploy` e o início da
próxima macrofase (Prestação de Contas / Distribuição Documental)
continuam exigindo decisão humana separada — nunca decorrem
automaticamente da conclusão deste handoff.
