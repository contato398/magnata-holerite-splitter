<!-- PROVENIÊNCIA (Etapa 3 da Central Command, 2026-08-22) — resgate documental.
Origem: branch `feat/magnata-os-claude-powerpack`, HEAD `053acada09dfc70bda71d2293aacbf2bca9ed43e`,
PR #12, FECHADO SEM MERGE em 2026-08-03T17:16:01Z. Texto original preservado;
as únicas alterações são a NOTA DE RECONCILIAÇÃO abaixo (quando existe) e a
de-identificação exigida por `CLAUDE.md` §6/LGPD, ambas declaradas.
Nenhuma decisão aprovada pela Direção foi alterada. -->

# Magnata OS — Arquitetura de Plataforma (v1)

> **NOTA DE RECONCILIAÇÃO — Etapa 3, 2026-08-22.** O mapa de módulos da
> §2 (**nove** módulos, 2026-07-22) foi **superado** por
> `docs/magnata-os/MAGNATA_OS_MODULOS.md` v1.0 (2026-07-25), que declara
> **dez** — o único acréscimo é **RH**, desmembrado; os outros oito mapeiam
> 1:1. Não é contradição: são taxonomias sucessivas, e a de dez é a vigente.
> `CLAUDE.md` §3 cita corretamente a §2 deste arquivo. O restante deste
> documento (princípios, contratos, plano strangler, débitos técnicos)
> **não** foi superado. Ver `docs/magnata-os/central-command/FOUNDATION.md` §8.

**Status:** rascunho para validação — nada implementado a partir deste documento.
**Papel deste documento:** referência viva. Toda implementação futura (endpoint,
tabela, campo, integração) deve ser avaliada contra este documento antes de
codar. Se um pedido conflitar com um princípio ou módulo aqui definido, isso
deve ser levantado explicitamente antes de implementar, não decidido em silêncio
dentro do código.

**Como este documento evolui:** cada mudança relevante de arquitetura (novo
módulo, novo contrato de dados, mudança de máquina de estado) ganha uma entrada
no changelog no final do arquivo, com data e motivo. Não reescrever histórico —
adicionar.

---

## 0. Onde estamos hoje (linha de base, 2026-07-22)

Antes de desenhar o alvo, o estado real medido:

| Fato | Evidência |
|---|---|
| `app.py` é um monólito de 10.410 linhas, 182 funções, 37 rotas Flask | medição direta no repo |
| Extração modular já começou, mas é pequena: `src/ingestao_secullum.py`, `src/services/secullum_ponto.py`, `src/sync_new_employees.py`, `src/report_generator.py` | `src/` tem 4 módulos reais |
| Persistência principal é o Airtable (não há banco relacional próprio) | `requirements.txt` não tem driver de DB; app.py usa API do Airtable |
| Assíncrono via Celery + Redis, 1 worker web + 1 worker Celery no Render | `render.yaml`, `celery_app.py` |
| Padrão repetido de "fila + disparo" por canal (WhatsApp, e-mail, combinado, ponto) | rotas `gerar-fila-envios*` / `disparar-fila*` |
| Cultura de decisão-antes-de-codar já existe, mas por documento avulso e não versionado como sistema | `ARQUITETURA_FASE_2_DECISAO_FINAL.md`, `FASE_A..D` |
| Raiz do repo tem dezenas de arquivos de investigação/scratch (`_*.json`, `_*.txt`) misturados com código de produção | `ls` da raiz |
| Débitos técnicos já identificados e registrados em memória, não neste doc: campo `Tipo de Documento` contaminado com códigos de erro; Render free tier dá 502 sob carga; funcionário específico trava chamadas Secullum | ver §8 |

Isso não é uma crítica — é o ponto de partida real que qualquer plano de
migração precisa respeitar. Não vamos propor uma reescrita do zero.

---

## 1. Princípios de Engenharia (não-negociáveis)

Estes princípios já existem na prática (extraídos do comportamento observado
no projeto) e ficam formalizados aqui. Qualquer decisão de implementação futura
que os contrarie deve justificar a exceção explicitamente.

1. **Airtable é o sistema de registro.** Não introduzir um segundo banco de
   dados "de verdade" paralelo sem decisão explícita — se algo precisar de um
   modelo relacional que o Airtable não aguenta bem, isso é uma decisão de
   arquitetura, não uma implementação silenciosa.
2. **ADD-ONLY, REUSE-FIRST.** Antes de criar campo/tabela nova, provar que não
   existe já um caminho (ex.: `Arquivos 2` → `Emails Savian` já dava Message ID,
   Assunto e hash sem criar nada). Exclusão/renomeação de campo é sempre uma
   decisão separada, nunca acoplada a uma feature nova.
3. **Idempotência por hash/chave natural, não por "não rodar de novo".**
   Documentos são identificados por hash do anexo; envios e registros que podem
   ser reprocessados precisam de uma chave que sobreviva a reprocessamento.
4. **Todo endpoint que grava em massa tem `dry_run` e, quando fizer sentido,
   `limit`.** Nada de "rodar direto em produção" como único modo.
5. **Toda automação assíncrona é observável por status explícito**, não por
   ausência de erro. Um documento nunca fica em estado implícito — ele está em
   um dos estados nomeados da máquina de estados (§5).
6. **Versão sobe em `/health` a cada deploy, e o deploy só é considerado
   concluído depois de confirmado via curl.** (já registrado como padrão em
   memória — formalizado aqui como princípio de arquitetura, não só hábito.)
7. **Decisão antes de código, para qualquer mudança que toque schema do
   Airtable ou máquina de estados.** Documento curto, ADD-ONLY, com contagem
   exata de campos novos — o padrão que já vem sendo seguido em `FASE_A..D` e
   `ARQUITETURA_FASE_2` continua, mas passa a referenciar este documento como
   arquitetura-mãe em vez de ser uma decisão isolada.
8. **Um posto/cliente/funcionário fora do padrão é sinal, não exceção a
   ignorar.** Quando algo trava ou diverge sistematicamente (ex.: paridade
   PAR/ÍMPAR invertida em 31 de 40 casos), tratar como achado de convenção, não
   como 31 bugs — investigar o padrão antes de corrigir item a item.
9. **Espaço de trabalho (repo) e sistema de produção não se misturam.**
   Arquivos de investigação/scratch (`_*.json`, `_*.txt`, PDFs de teste) não
   pertencem à raiz do repositório de produção — ver §7 (faxina) e §9 (regra
   de scratch).

---

## 2. Mapa de Módulos (domínios / bounded contexts)

Cada módulo abaixo é uma responsabilidade coesa. Hoje eles existem *como
comportamento* dentro de `app.py`; o alvo é que cada um vire um pacote em
`src/` com fronteira clara. Um módulo não deve conhecer o schema interno de
outro — ele conversa por contrato de dados (§4) ou por evento de estado (§5).

```
Magnata OS
│
├── 1. Ingestão                — entrada de documentos e dados brutos
│      (e-mail/Gmail Apps Script, upload manual, importação Secullum)
│
├── 2. Classificação            — decide o que é um documento e a quem pertence
│      (tipo de documento, categoria documental, cliente/funcionário, competência)
│
├── 3. Cadastro                 — identidade de Clientes, Funcionários, Locais
│      (pré-cadastro por contrato, sincronização, deduplicação)
│
├── 4. Ponto / Secullum         — integração com o relógio de ponto
│      (cálculo colunar, alertas de crônicos, escalas, bônus assiduidade)
│
├── 5. Folha / Documentos       — geração e correção de holerites, FGTS,
│      benefícios, recibos, guias
│
├── 6. Distribuição             — entrega ao destinatário certo pelo canal certo
│      (fila → disparo, WhatsApp/Evolution, e-mail/SMTP, combinado)
│
├── 7. Assinatura                — assinatura nativa com evidências (IP/CPF)
│
├── 8. Auditoria / Observabilidade — trilha de execução, dry-runs, relatórios
│      de integridade, contagem de pendências
│
└── 9. Plataforma (infra)        — Flask app, Celery worker, Airtable client,
       deploy Render, filas Redis — a "cola" que os módulos acima compartilham
```

### Responsabilidade de cada módulo (contrato de fronteira)

| Módulo | Recebe | Produz | Não faz |
|---|---|---|---|
| Ingestão | e-mail bruto, upload, resposta de API externa | registro em `Processar Arquivos` / `Emails Savian` com status inicial | não classifica, não decide destinatário |
| Classificação | registro pendente + texto extraído do PDF | Cliente, Funcionário, Categoria Documental, Competência, Confiança | não gera PDF, não envia nada |
| Cadastro | contrato, holerite novo, dado de sincronização | registro de Funcionário/Cliente/Local válido (ou pendência de validação) | não decide como o documento será distribuído |
| Ponto/Secullum | dados brutos do relógio de ponto | alertas, cálculo colunar, escala validada | não gera holerite, não envia mensagem |
| Folha/Documentos | dados de cadastro + fonte (Secullum, planilha, contrato) | PDF individual correto, vinculado a Funcionário/Cliente | não decide canal de envio |
| Distribuição | documento classificado e vinculado | mensagem enviada + status de entrega | não reclassifica documento |
| Assinatura | documento que requer assinatura | assinatura com evidência, ou pendência | não gera nem distribui o documento original |
| Auditoria | eventos de todos os módulos acima | relatório, contagem, sinalização de risco | não corrige dado automaticamente — só relata |

---

## 3. Estilo arquitetural: monólito modular, não microsserviços

Dado o tamanho da operação (uma empresa, não uma plataforma multi-tenant em
escala), a recomendação é **não** quebrar em microsserviços separados. O alvo é
um **monólito modular**: um único deploy Flask + um único worker Celery,
organizados internamente em pacotes por domínio (`src/ingestao/`,
`src/classificacao/`, `src/distribuicao/`, etc.), cada um com sua própria
pasta de testes.

Isso preserva a operação simples (dois serviços no Render, como hoje) e ainda
assim dá as fronteiras de responsabilidade que faltam. Trocar por
microsserviços seria over-engineering neste estágio — reavaliar apenas se
surgir necessidade real de escalar um módulo (ex.: Secullum) independente do
resto.

---

## 4. Contratos de Dados (Airtable como sistema de registro)

O Airtable é tratado como o "banco de dados" — logo as tabelas centrais são
contratos entre módulos, não detalhe de implementação. Regras:

- **Um campo pertence a um módulo dono.** Só o módulo dono decide o
  vocabulário de um `singleSelect` ou cria opção nova nele. Outros módulos
  apenas leem.
- **Ligações entre tabelas (`multipleRecordLinks`) são o contrato oficial de
  referência cruzada** — preferir reaproveitar uma cadeia de links existente
  (como `Arquivos 2 → Arquivos → Emails Savian`) a duplicar dado em campo novo.
- **Nenhum campo deve carregar dois significados.** O débito técnico atual em
  `Tipo de Documento` (mistura categoria de documento com código de erro
  técnico do hotfix) é o contra-exemplo a não repetir — está registrado como
  debt em §8, não deve ganhar um terceiro significado por cima.

### Tabelas centrais e módulo dono (visão atual)

| Tabela | Módulo dono | Papel |
|---|---|---|
| Processar Arquivos | Ingestão → Classificação | fila de entrada e resultado de classificação |
| Emails Savian | Ingestão | origem do e-mail (Message ID, Assunto, Conteúdo) |
| Arquivos | Ingestão | anexo físico + hash de idempotência |
| Funcionários | Cadastro | identidade do colaborador, status, escala |
| Clientes | Cadastro | identidade do cliente/posto |
| Locais | Cadastro | unidade física / posto de trabalho |
| Envios de Documentos | Distribuição | fila de envio, canal, status, tentativa |
| Assinaturas | Assinatura | evidência de assinatura nativa |

Qualquer tabela nova ou campo novo deve ser adicionado a esta lista no mesmo
commit que a decisão de schema for tomada — a tabela acima é o índice de
verdade, não o Airtable schema bruto.

---

## 5. Máquina de Estados e Eventos

O sistema não tem um barramento de eventos formal (Kafka etc.) — os "eventos"
são **transições de campo `Status`** dentro do Airtable, consumidas por
polling do worker Celery ou por chamada direta de endpoint. Isso é aceitável
na escala atual, mas precisa ser **um vocabulário único**, não um por módulo.

### Estados canônicos de um documento (Processar Arquivos)

```
Pendente/Enviar → Processando → Concluído
                              → Revisão Manual  (confiança baixa ou sem cliente)
                              → Erro            (falha técnica)
```

### Estados canônicos de um envio (Envios de Documentos)

```
Fila → Enviando → Enviado
               → Falha (com Tentativa incrementada, reentra na Fila até limite)
```

**Regra:** nenhum módulo novo introduz um nome de estado sinônimo (ex.: não
criar "Aguardando" se "Pendente" já existe com o mesmo sentido). Se um estado
novo for genuinamente necessário, ele entra nesta lista canônica primeiro.

---

## 6. Arquitetura de Execução

```
Gmail/Apps Script ──▶ webhook /email/webhook ──▶ Processar Arquivos (Pendente)
                                                          │
                                                   Celery task (tarefas_processar_pdf)
                                                          │
                                            extrai texto → classifica → grava
                                                          │
                                        Concluído / Revisão Manual / Erro
                                                          │
                                              gerar-fila-envios* (Flask, sync)
                                                          │
                                             disparar-fila* (Flask ou Celery)
                                                          │
                                    Evolution API (WhatsApp) / SMTP (e-mail)
```

- **Síncrono (Flask/gunicorn):** endpoints que respondem rápido — geração de
  fila, disparo, consultas, webhooks de recebimento.
- **Assíncrono (Celery/Redis):** processamento de PDF (I/O e CPU pesados,
  `task_soft_time_limit=600s`), qualquer chamada em lote à API do Secullum
  (rate-limited).
- **Regra:** se um endpoint pode ultrapassar ~20-30s (limite prático do Render
  free tier sob carga, já observado como causa de 502), ele deve ser Celery,
  não uma rota síncrona que processa tudo inline.

---

## 7. Plano de Migração (strangler fig)

Não é uma reescrita. `app.py` continua funcionando durante toda a migração —
cada módulo é extraído incrementalmente, com o Flask app importando de
`src/<modulo>/` em vez de ter o código inline. Ordem sugerida (da menor
superfície de risco para a maior):

1. **Faxina de repositório** (baixo risco, alto retorno imediato): mover todo
   `_*.json` / `_*.txt` / scratch da raiz para uma pasta `_scratch/` fora do
   deploy (ou `.gitignore`), sem tocar em nenhuma lógica. Isso não é
   arquitetura de código, é higiene — mas é pré-requisito para qualquer
   extração séria, porque hoje é difícil distinguir arquivo de produção de
   arquivo de investigação só olhando a raiz.
2. **Extrair Distribuição** — já é o módulo mais "fila + disparo" repetitivo
   (WhatsApp, e-mail, combinado, ponto seguem o mesmo padrão 4x). Unificar em
   `src/distribuicao/` com uma função de fila e uma de disparo parametrizadas
   por canal, em vez de 4 pares de rotas quase-duplicadas.
3. **Extrair Classificação** — é o módulo mais recente em decisão
   (`ARQUITETURA_FASE_2`) e ainda não implementado; nasce direto em `src/`, não
   em `app.py`. Primeira oportunidade real de "nascer já modular".
4. **Extrair Ponto/Secullum** completamente — já tem começo em
   `src/services/secullum_ponto.py` e `src/ingestao_secullum.py`; terminar a
   extração do que ainda estiver em `app.py` para esse pacote.
5. **Extrair Cadastro** (Funcionários/Clientes/Locais) — `src/sync_new_employees.py`
   já existe; consolidar todo código de pré-cadastro e deduplicação aqui.
6. **Extrair Folha/Documentos e Assinatura** por último — são os módulos mais
   antigos e mais testados (`test_assinatura_v3_6.py`, `test_fila_envios_v2_23.py`
   etc.), então a extração deve vir acompanhada dos testes existentes passando
   sem alteração de comportamento.

Critério de "pronto" por etapa: os testes existentes daquele domínio continuam
passando, `/health` sobe de versão, e o app.py fica estritamente menor (a rota
passa a chamar `src/<modulo>`, não a conter a lógica).

---

## 8. Débitos Técnicos Conhecidos (registrados, não resolvidos por este doc)

Consolidado do que já estava disperso em memória — centralizado aqui para não
ser esquecido em uma migração futura:

- `Tipo de Documento` (Processar Arquivos) mistura categoria real de documento
  com códigos de erro técnico do hotfix (`UPLOAD_FAILED`, `PROCESSING_ERROR`
  etc.) — não corrigir de passagem, é uma decisão própria.
- Render free tier retorna 502 sob carga — lotes precisam ser pequenos com
  retry, não assumir requisição única grande.
- Chamada Secullum trava para um funcionário específico — precisa de tratamento defensivo antes de qualquer rodada em lote
  que itere todos os funcionários.
- Bug de virada de dia no Secullum ainda instável (dados mudam entre consultas
  consecutivas) — não tratar como cache-friendly.
- `Horario.Descricao` do Secullum não é confiável como fonte — usar
  `Atras./Adian.` nativos.

---

## 9. Regra de Scratch / Higiene de Repositório

Arquivos temporários de investigação (JSON de auditoria, resultado de dry-run,
backups pontuais) **não vão para a raiz do repo de produção**. Usar a pasta de
scratch da sessão (fora do repositório) para isso, e só trazer para o repo o
que for: código, teste, ou documento de decisão de arquitetura. Isso vale
tanto para trabalho futuro quanto para a faxina retroativa descrita em §7.1.

---

## 10. Checklist antes de implementar qualquer coisa nova

1. Qual módulo (§2) é dono disso? Se não for óbvio, é sinal de que a feature
   cruza fronteira e precisa de decisão explícita de onde mora.
2. Existe campo/tabela/cadeia de link que já cobre isso? (princípio ADD-ONLY)
3. Qual estado da máquina de estados (§5) isso entra ou sai? Precisa de estado
   novo, ou um dos canônicos já serve?
4. Isso é síncrono ou assíncrono, e por quê (§6)?
5. Isso teria `dry_run`? Por que não, se não?
6. Isso vai para `src/<modulo>/` ou (só se genuinamente transitório) direto em
   `app.py`?

---

## Changelog

- **2026-07-22** — v1 criado. Primeira formalização da arquitetura de
  plataforma a partir do estado real medido do repositório (10.410 linhas em
  `app.py`, 4 módulos já extraídos em `src/`, padrão fila+disparo repetido em
  4 canais). Rascunho para validação do usuário.
