# ADR J3: índice de correlação entre Documento interno e escopo da Prestação (V1)

- **Data:** 2026-09-25
- **Branch:** `fix/prestacao-upstream-real-v1`
- **Base:** `main` @ `de69fb2`
- **Continua:** `auditoria-gate-j-composicao-prestacao-v1.md` §14 (gate J3 diagnosticado)
- **Autorização humana:** ADR, migration aditiva com rollback, testes e documentação.
- **Não autorizado:** aplicar a migration no banco real, fazer backfill real, deploy, envio ou qualquer mutação em produção.

## 1. Problema

O ciclo da Prestação não sabia quais Documentos internos são candidatos a cada necessidade (cliente, competência, tipo, colaborador opcional):
- `fonte_candidatos_por_necessidade` ficava `None` na produção;
- todo inventário real usava record-id do Airtable como `documento_id`;
- `resolucao_documental_temporal` (0010) não tem produtor e, por decisão original, não guarda cliente.

Resultado: nenhum cliente real chegava a PRONTO.

## 2. Decisão

### 2.1 Reutilizar o contrato de relação que já existia

A relação é `ItemInventarioPrestacao`: `documento_id`, tipo, cliente, competência e colaborador opcional. O corredor da Prestação já produz 1 item por cliente legítimo: vínculo múltiplo, broadcast e, no ponto, transferência de posto dentro do período. O índice é a versão **persistida e histórica** desse inventário.

- **Módulo de domínio:** `classificacao/correlacao_documento_prestacao.py` (puro).
- **Adapter:** `classificacao/adapters/postgres_correlacao_documento_prestacao.py`.
- **Decisão única:** `planejar_observacoes` é usada pelo twin em memória e pelo adapter Postgres; nenhuma regra é duplicada entre eles.

### 2.2 Schema: migration orquestrador 0007 (aditiva, inerte)

- **Tabela:** `magnata_orquestrador.correlacao_documento_prestacao`, append-only com o trigger `bloquear_mutacao_auditoria` (0001), igual à 0006.
- **Colunas:** `relacao_id` (sha256 das 5 dimensões), `sequencia`, `documento_id` (FK para `documentos`), `cliente_id`, `competencia` (`AAAA-MM`, com CHECK), `tipo_documental`, `colaborador_id` (NULL indica nível cliente), `estado` (`VIGENTE`|`SUPERADA`), `origem`, `evidencia_sha256` e `registrado_em`.
- **Por que em `orquestrador/migrations` e não em `modulo01/migrations`:**
  - `modulo01/migrations/` é caminho protegido (bloqueio absoluto no hook);
  - a persistência da Prestação já vive no pacote do orquestrador (0005 `execucoes_prestacao`);
  - a dependência de `documentos` (modulo01 0001) está declarada na própria migration, e a FK é a garantia no banco.
- **Por que não uma coluna `cliente_id` na 0010:** a decisão original da 0010 fica preservada. Cliente e posto não são propriedade única da resolução temporal. Aqui ficam **relações** 1:N, e o Documento canônico continua único em `documentos`.

### 2.3 Unicidade: `UNIQUE (relacao_id, origem, sequencia)`

`UNIQUE(documento_id)` estaria errado, porque o mesmo documento tem N relações legítimas (2 clientes no período, broadcast, vínculo múltiplo). A identidade lógica da relação são as **5 dimensões**. A `identidade_logica` do item (documento, cliente, colaborador) não inclui competência nem tipo. Uma relação é uma sequência de versões.

- **Replay:** o produtor só grava quando o estado muda (`VIGENTE` → nada).
- **Concorrência:** `pg_advisory_xact_lock(6007, hashtext(documento|origem))` na mesma transação da leitura e da escrita. O mesmo padrão do Gate 1 (6006) já foi provado em CI. `UNIQUE` é a segunda barreira, no banco.
- **Relações distintas coexistem:** cada uma tem seu `relacao_id`.
- **A mesma relação vinda de dois produtores** (por exemplo, a Folha de Ponto resolvida pelo corredor e pela resolução temporal) tem uma história **por origem**. Por isso `origem` faz parte da chave de versão. A relação está disponível enquanto estiver `VIGENTE` em alguma origem.
  - *Achado da revisão independente:* a primeira versão tinha `UNIQUE (relacao_id, sequencia)`, e a segunda origem colidia. Corrigido antes de qualquer aplicação, com teste unitário e teste real de duas origens.

### 2.4 Histórico: append-only

Segue o padrão já adotado para estado que muda (Gate 1/0006, auditoria/0001):
- revisão → relação vira `SUPERADA` (sequência +1);
- de volta a resolvido → `VIGENTE` de novo (+1);
- nova evidência que muda o escopo → a relação antiga vira `SUPERADA` e a nova nasce `VIGENTE`.

Nada é editado ou apagado. O estado corrente é a maior `sequencia` por (`relacao_id`, `origem`). A reconciliação de um reprocessamento é sempre por (documento, **origem**): um produtor nunca supera o que outro observou.

**Escopo de superação por competência:**
- O corredor valida a competência contra o ciclo da execução. Um documento reprocessado sob outro ciclo vai para revisão por **conflito com o ciclo**, e não por nova evidência sobre o documento.
- Por isso `competencias_superaveis` limita o que uma execução pode superar às competências que ela consegue validar, que são exatamente a que o corredor usa como esperada mais as dos itens resolvidos:
  - com `cliente_do_ciclo`, a da política; a base **não** entra, porque o corredor não a valida nesse caso (achado da re-revisão);
  - sem `cliente_do_ciclo`, a base do ciclo.
- Relações de outra competência ficam intocadas. Sem esse limite, backfills de meses diferentes ficariam alternando as relações entre `VIGENTE` e `SUPERADA` (achado da revisão independente, corrigido e testado).
- O produtor de ponto não usa escopo: a competência dele vem do próprio documento, não do ciclo.

## 3. Produtor, dentro do fluxo documental existente

Auditei os pontos candidatos:
- a ingestão modulo01 (`ServicoCriacaoLote`) só persiste etapa e situação, e resolve apenas o tipo e o colaborador do Holerite;
- a importação em lote não tem chamador de produção.

O ponto que resolve as 5 dimensões com evidência do **conteúdo** é o corredor da Prestação: `ExecucaoCorredorReadonly.processar_documento` → `executar_documento_readonly`, o mesmo que já alimenta o sink de inventário.

- **Corredor:** `ExecucaoCorredorReadonly(..., registro_correlacao=...)`.
  - O padrão `None` preserva o comportamento anterior.
  - Depois de cada documento, `registrar_correlacoes_do_corredor` grava os itens que o corredor já produziu. Esses itens só existem para `RESOLVIDO_E_AVANCOU`, pela regra de `avancar_para_inventario`, que foi reaproveitada.
  - Documento em revisão gera um conjunto vazio, e as relações antes vigentes viram `SUPERADA`: o índice reflete a revisão.
  - Documento **derivado** de separação (`id:grupo`) não é um Documento interno. É ignorado com o evento `correlacao_documento_derivado_ignorada` e nunca promovido.
  - A evidência é o sha256 dos `semantic_result_id`, sem conteúdo.
- **Ponto (Folha/Cartão):** `registrar_correlacoes_de_ponto` usa o resultado de `resolver_documento_ponto`, ou seja, a 0010 mais a alocação temporal. Gera 1 relação por cliente cuja alocação intersecta o período. Sem período, colaborador ou alocação, não gera relação.

**Evidência independente:** a relação nasce do conteúdo do documento contra as fontes de referência no momento da ingestão (vínculo, cliente direto por CNPJ, alocação), **nunca** da necessidade que depois a consulta. Não se fabrica cliente, competência nem colaborador.

**Pendência declarada:** a resolução temporal de ponto ainda não tem orquestrador de produção (a 0010 não tem chamador real). O produtor de ponto está pronto e testado, mas ligá-lo depende desse orquestrador.

## 4. Consumidor e elegibilidade

- **Consumidor:** `construir_fonte_candidatos_por_necessidade_postgres(conexao)` = `FonteCandidatosDocumentoInventarioInterna`, que já existia, sobre o índice e o `RepositorioDocumentosPostgres`. Devolve `Documento` interno real (garantido pela FK).
- **Única extensão:** o filtro de tipo passou a usar a **mesma** tradução de vocabulário que a elegibilidade J1b (`TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL`). Também deduplica o mesmo documento vindo de duas origens.
- **Elegibilidade:** o índice recorta o universo de busca e não substitui nada. Cada candidato continua passando pelo corredor na aquisição e por `_elegivel_para_distribuicao`: pessoa certa, cliente certo, competência certa, tipo certo, estado `RESOLVIDO_E_AVANCOU` sem revisão.
- **Nível cliente:** necessidade com colaborador NULL só recebe relação com colaborador NULL. `IntencaoDistribuicaoCliente` continua saindo do mesmo gate de readiness e elegibilidade, ou seja, só de relações comprovadas.

## 5. Destinatário organizacional do cliente (bridge transitório)

Decisão humana: manter temporariamente a fonte real existente no Airtable, read-only e atrás de Protocol.

- **Protocol:** `FonteDestinatarioOrganizacionalCliente.enderecos_para(cliente, papel)`, em `pacote_prestacao.py`, sem Airtable.
- **Adapter:** `importacao_lote/adapters/airtable_destinatario_cliente.py` mais o método read-only `LeitorAirtableSomenteLeitura.listar_campos_destinatario_clientes`.
- **Campos auditados no legado** (`app.py::_gerar_fila_envios_email`): `Email` (texto) e `Email Contador` (lookup, lista).
- **Mapeamento:** 1 campo para 1 papel (`CLIENTE_INSTITUCIONAL`, `CONTADOR_DO_CLIENTE`). O fallback do legado ("sem `Email`, usar o primeiro `Email Contador`") **não** foi reproduzido: é regra de entrega, e adotá-la cabe à política de canal.
- **Validação:** endereço sem forma mínima de e-mail é descartado, nunca consertado. Isso inclui o campo `Email` com vários endereços num texto só (`a@x; b@y`): ele é descartado inteiro (fail-closed), e o cliente fica sem `CLIENTE_INSTITUCIONAL` até existir fonte estruturada.
- **Onde é usado:** a intenção não carrega endereço. O relatório do piloto só diz se o papel tem destinatário, nunca o endereço.

## 6. Composition root e piloto shadow

- **Composition root:** `importacao_lote/composicao_prestacao_upstream.py` (borda).
  - `compor_contexto_prestacao_upstream` monta o `ContextoComposicaoPrestacao` real:
    - fontes Airtable transitórias (as **mesmas** instâncias de `ExecucaoCorredorReadonly`, expostas por propriedades);
    - cadastro canônico V2;
    - índice J3 como fonte de candidatos;
    - `competencias_por_cliente` pela política V1;
    - `tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,)`, que corrige a deriva de vocabulário registrada no §11.1 do Gate J.
  - `compor_contexto_prestacao_upstream_a_partir_do_ambiente` lê `AIRTABLE_API_KEY` e `DATABASE_URL` só ali.
    - Por padrão é **leitura pura**: o corredor não recebe produtor do índice.
    - `com_produtor_indice=True` (ingestão ou backfill autorizados) liga o produtor numa **conexão própria**, de modo que o commit ou rollback do índice nunca afeta a conexão de leitura.
- **Snapshot único:** `diagnosticar_prestacao_upstream` faz 1 cálculo. Dele saem as Ordens, via `executar_prestacao_contato_ate_pending_shadow_v1(..., trios_prontos=...)` até PENDING, e as intenções de cliente. Não há dois snapshots divergentes.
- **Relatório do piloto:** `montar_relatorio_piloto` é sanitizado. Traz clientes, estado do pacote, motivos, faltantes, candidatos, aceitos, rejeitados, grupos por colaborador, intenções, se há destinatário e os bloqueios.
- **Piloto real: não executado.** Motivos:
  - a 0007 não está aplicada em nenhum banco real, e aplicá-la não foi autorizado;
  - esta sessão não tem Postgres nem `DATABASE_URL`.

  A cadeia foi provada com corredor real e dados sintéticos: em memória localmente, e no Postgres efêmero da CI (§8).

## 7. Backfill: projetado e testado, nunca executado

`executar_backfill_correlacao` reprocessa Documentos **já existentes**, lendo o blob já armazenado, pelo **mesmo** `ExecucaoCorredorReadonly.processar_documento` da ingestão. Não há lógica especial de classificação.

- **Idempotente:** o índice só grava mudança.
- **Reiniciável:** ordem por `documento_id`, com `retomar_apos` e `limite`.
- **Auditável:** relatório de contagens mais ponto de retomada; cada observação tem origem, evidência e timestamp.
- **Isolado:** erro por documento é contado pelo tipo da exceção, e o lote segue.
- **Execução por competência:** 1 ciclo por execução, como a ingestão.
- **Exige produtor:** sem `registro_correlacao`, o backfill falha explicitamente em vez de reportar tudo como `sem_relacao`.

**Estimativa:** esta sessão não tem acesso ao banco real, então não há números. O próprio relatório do backfill é o instrumento de estimativa numa primeira rodada controlada (limite pequeno, em staging, com autorização):

| Campo | O que mede |
|---|---|
| `com_relacao_vigente` | elegíveis |
| `sem_blob` | documentos sem blob |
| `sem_relacao` | em revisão ou não resolvidos |
| `relacoes_superadas` | conflitos com o índice anterior |
| `processados` / `ultimo_documento_id` | reprocessamento |
| `mime_nao_suportado` | fora do corredor PDF |

Sem migration aplicada, o backfill não roda.

## 8. Provas

- **Unitários** (`test_correlacao_documento_prestacao.py`, 37 testes, incluindo duas origens, dois ciclos e o escopo do produtor):
  - identidade e decisão;
  - FK e record-id externo;
  - replay;
  - 1:N;
  - revisão → resolvido;
  - troca de escopo;
  - origens;
  - necessidade exata versus cliente, competência, tipo e colaborador errados;
  - colaborador NULL no nível cliente;
  - tradução de vocabulário;
  - produtores (corredor, derivado, revisão, ponto com 1 e 2 clientes, sem evidência);
  - destinatário;
  - backfill;
  - composition root;
  - adapter Postgres com cursor fake (lock, plano, transação, rollback, `listar`).
- **Corredor real** (`test_aquisicao_prestacao_corredor_real_j1.py`, seção J3): o índice alimenta o ciclo até PRONTO, Ordens A/B até PENDING, intenção do Extrato; sem índice, o cliente fica em revisão; o documento de A nunca é candidato de B; documento em revisão na ingestão não vira relação.
- **Postgres real** (`test_correlacao_documento_prestacao_postgres_real.py`, job `postgres-real`):
  - FK;
  - replay e coexistência;
  - histórico append-only;
  - trigger bloqueando UPDATE e DELETE;
  - `UNIQUE`;
  - `CHECK` de competência;
  - concorrência de 6 processos gerando 1 linha;
  - consumidor devolvendo Documento interno;
  - ponto com 2 clientes e 1 Documento;
  - ciclo real lendo só o índice Postgres até PRONTO, Ordens por colaborador e intenção separada;
  - ciclo sem o holerite de B ficando fora de PRONTO;
  - rollback e reaplicação;
  - mesma relação de duas origens, com histórias independentes;
  - reprocessamento sob outro ciclo sem superar a relação de outra competência.

  **Não roda nesta sessão, que não tem Postgres.** Roda na CI depois de push/PR. O cenário do ciclo foi validado localmente com o twin em memória (mesma função).

## 9. Governança

- **Entradas nominais exatas:** `.magnata/patterns.sh` (arquivos novos), `.githooks/pre-commit` (os 2 testes novos) e `.github/workflows/magnata-testes.yml` (o teste real no job `postgres-real`). Nenhuma proteção foi afrouxada.
- **Pendente para a publicação:** o gate `protected_migrations` exige, no mesmo diff do PR, `.magnata/migration-authorizations/pr-<N>.gitblob` com os blobs exatos da 0007 e do rollback. `<N>` só existe quando o PR é aberto. Localmente esse gate bloqueia, como esperado.

## 10. Riscos remanescentes

1. **A 0007 depende de `documentos` (modulo01 0001) e de `magnata_orquestrador` (0001).** Aplicar em produção exige conferir as duas antes. É gate humano.
2. **O índice só é tão bom quanto as fontes da ingestão.** Vínculo, clientes e cliente direto continuam em Airtable transitório (J2). A aquisição revalida tudo.
3. **DCTFWeb** (perfil `broadcast_estrutural`, `clientes_broadcast=()`) não gera relação nem fica elegível. Com a base V2 exigindo DCTFWeb, **nenhum cliente real chega a PRONTO** até essa granularidade ser decidida. É regra de negócio, fora deste escopo e não alterada.
4. **O produtor de ponto não tem orquestrador de produção** (§3).
5. **`colaborador_id` do índice é o id vigente**, hoje o record-id do Airtable (decisão J2 de identidade pendente). É um id opaco de colaborador, não de documento.
6. **O fallback de destinatário do legado não foi reproduzido:** um cliente sem `Email` fica sem destinatário `CLIENTE_INSTITUCIONAL` até a política de canal decidir.
7. **Competência deslocada (SKY Tatuí):** um documento só é indexado por uma execução cujo ciclo valida a competência dele (a base do ciclo, ou `cliente_do_ciclo` com a política). A ingestão ou o backfill desses clientes precisa rodar com o ciclo ou o cliente correspondentes. Com o escopo de superação, execuções de outros meses nunca apagam essas relações.
8. **Resultado vazio do corredor** (PDF sem página processada) não registra nada: relações antes `VIGENTE` permanecem. Isso é seguro porque a aquisição revalida cada candidato.
9. **Leituras do adapter** não fazem commit, no mesmo padrão dos demais repositórios. Quem mantém a conexão aberta encerra a transação. Os testes reais fecham toda conexão no teardown.
