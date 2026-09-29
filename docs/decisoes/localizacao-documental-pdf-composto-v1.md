# Localização documental central — PDF composto, busca por conteúdo e diagnóstico (V1)

- **Data:** 2026-09-29
- **Base:** PR #195 (`fix/magnata-os-central-foundation`, fundação do Magnata OS Central) + localização central (`magnata_os/central/localizacao.py`)
- **Natureza:** código de domínio e composição, testado com fakes na fronteira. Nenhuma migration, nenhum secret, nenhum acesso a Airtable/Gmail/Evolution/Postgres real, nenhum transporte. `app.py` intocado.

## 1. Problema

Incidente real relatado pela operação: um PDF de 12 páginas, com um documento por página, chegou e foi armazenado. A busca por um desses documentos não o achou; o operador o encontrou manualmente numa das 12 páginas.

A causa foi verificada no código:

1. a extração juntava todas as páginas num texto só (`documental/extracao_texto.py`);
2. o arquivo inteiro era **um** `Documento`. O texto tinha 12 CPFs, então COLABORADOR ficava em CONFLITO e o documento ia para revisão;
3. a separação por página já existia (`separacao_documental.py`), mas nunca rodava. A aquisição passava `paginas=(texto,)` e `identificar_pagina=None`. Essa pendência já estava registrada em `orquestrador-readonly-corredor-v2.md` §4;
4. o inventário só conhece o que já foi resolvido, e um PDF composto nunca é resolvido inteiro. Sem índice, ninguém o oferecia como candidato.

## 2. O que foi construído

| Peça | Onde | Reuso |
|---|---|---|
| Texto por página | `documental/extracao_texto.py::extrair_texto_pdf_por_pagina`, `classificacao/roteamento_documental.py::extrair_paginas_seguro` | mesma extração pdfplumber; `extrair_texto_pdf` agora deriva dela com resultado idêntico |
| Fatiamento de PDF | `documental/fatiamento_pdf.py::fatiar_pdf` | padrão de `extrair_pdf_colaborador` do legado, reimplementado sem importar `app.py`; determinístico |
| Documentos derivados | `documental/derivacao_documental.py::derivar_documentos` | porta oficial `registrar_entrada` (`AdaptadorEntradaDuravel`), idempotência por hash, histórico append-only |
| Índice CPF → colaborador | `classificacao/separacao_documental.py::indice_cpf_de_candidatos` | alimenta `estrategia_por_cpf_colaborador`, que já existia |
| Troca do composto pela parte do colaborador | `composicao_ciclo_persistente_prestacao.py::_expandir_documentos_compostos` (campo `entrada_documentos_derivados`) | `analisar_estrutura_documento`, `separar_por_carry_forward`; âncora e elegibilidade inalteradas |
| Busca por conteúdo | `classificacao/fonte_candidatos_por_conteudo.py::FonteCandidatosPorConteudo` | protocolo `candidatos_para` da localização central |
| Rastro com contagens | `central/localizacao.py::ConsultaFonte.detalhes` | `resumo_ultima_consulta()` opcional de cada fonte |
| Diagnóstico da Prestação | `composicao_ciclo_persistente_prestacao.py::diagnosticar_prestacao` | a mesma descoberta, localização, aquisição e readiness do ciclo real |
| Isolamento por destinatário no executor | `orquestrador/ciclo_producao_v1.py` | executor e repositórios inalterados |

## 3. Decisões registradas

### D1 — Busca por conteúdo (conflito com regra anterior, resolvido explicitamente)

`fonte_candidatos_por_necessidade.py` dizia que os candidatos nunca devem vir "a partir da resolução semântica do próprio documento", para evitar validação circular. A missão aprovada pelo operador pede o contrário (§11): "o motor deve ser capaz de encontrar um documento cujo filename seja completamente inútil".

**Decisão.** A fonte por conteúdo correlaciona pelo **CPF do colaborador** presente em alguma página. Isso é identidade, não a resolução semântica do corredor. Cliente, competência e tipo continuam validados de forma independente pelo corredor e por `_elegivel_para_distribuicao`: um documento da pessoa certa com mês ou cliente errado aparece como `ENCONTRADO_NAO_ELEGIVEL` e não é distribuído.

**Limite aceito.** A dimensão COLABORADOR passa a ser encontrada e validada pelo mesmo sinal (CPF). Necessidades sem colaborador (Extrato, FGTS, DCTFWeb) não são atendidas por esta fonte nesta etapa.

O texto da regra antiga foi mantido. Esta decisão a complementa, não a apaga.

### D2 — Documento derivado sem mudança de schema

A proveniência (id e hash do original, páginas, entidade e estratégia) fica nos `metadados` do evento `DOCUMENTO_RECEBIDO` do histórico, que é append-only. O derivado herda o `lote_id` do original, então a data do e-mail continua valendo para o desempate por versão. O original nunca é alterado.

Uma consulta "filhos de um original" exigiria uma tabela ou índice próprio. Isso é migration e, portanto, um gate humano. Não foi feito.

O nome do derivado é neutro: `documento_<12 primeiros caracteres do hash do original>_pag<N>.pdf`. Esse nome vira o nome do anexo enviado, e o nome do original pode conter nomes de outras pessoas, por isso nunca é herdado.

Um derivado que já existe no repositório (mesmo hash) é reaproveitado sem nova chamada de entrada, e a derivação fica em cache por execução. Rodar o ciclo de novo não acumula eventos `TENTATIVA_DUPLICADA` no histórico.

### D2b — Separação ESTRITA para documentos que serão enviados

A separação já existente (`estrategia_por_cpf_colaborador`) usa carry-forward: uma página sem CPF herda o grupo da página anterior. Para gerar um documento que será **enviado** a uma pessoa, isso é inseguro. Uma página de resumo geral da folha, ou o holerite de outra pessoa com CPF sem formatação, iria parar no PDF do colaborador anterior. A revisão adversarial desta etapa confirmou esse risco com um teste.

**Decisão.** A derivação usa `estrategia_por_cpf_colaborador_estrita`: a página só entra no grupo de alguém se tiver exatamente 1 CPF, e esse CPF for daquela pessoa. Página sem CPF ou com 2 ou mais CPFs fica fora de todos os grupos. A quantidade dessas páginas é registrada no evento `documento_composto_separado`.

**Custo aceito.** A página de continuação sem CPF de um holerite de várias páginas não entra na parte derivada.

**Risco residual fechado (etapa J3/J4).** Antes, um PDF com o CPF formatado de A e o CPF de B **sem formatação** contava só 1 CPF e seguia inteiro, como documento de A. Agora `cpfs_da_pagina` também conta os 11 dígitos sem formatação, mas **só** quando eles pertencem a um colaborador conhecido do índice. Qualquer sequência de 11 dígitos não serve, porque PIS/NIT e matrícula também têm 11 dígitos e bloqueariam páginas legítimas. A página de um CPF sem formatação passa a ser corretamente atribuída a essa pessoa.

### D3 — Quando não há parte do colaborador, o composto segue inalterado

O composto vai para o corredor como antes e cai em revisão. Pelas regras de elegibilidade ele nunca é distribuído: todas as execuções precisam confirmar o colaborador da necessidade. O motivo fica registrado no evento `documento_composto_nao_separado`.

### D3b — Diagnóstico é somente leitura; busca por conteúdo nunca escolhe por cima de lacuna

`diagnosticar_prestacao` simula a derivação em memória, sobre o armazenamento real e só para leitura (`_ArmazenamentoSobreposto`). Nenhum Documento, blob ou evento é gravado. Derivados que já existem são reaproveitados por hash.

Na fonte por conteúdo, qualquer arquivo ilegível leva a busca a `INDETERMINADO`, mesmo quando outro documento bate. O arquivo ilegível poderia ser uma versão corrigida. A falha de leitura não fica em cache: a próxima necessidade tenta ler de novo. Documentos derivados nunca são devolvidos diretamente pela fonte, que devolve sempre o original. Assim um derivado de um agrupamento anterior nunca concorre com o atual.

### D4 — Executor: isolar sem mascarar

Uma exceção num par (evento, preview), por exemplo envelope ilegível ou autorização ausente, não impede os pares seguintes no mesmo ciclo. A transação pendente daquele par é desfeita com `rollback`; o advisory lock é de sessão e não é afetado. A primeira falha é relançada **ao final** do ciclo, depois do observador de assinatura, então o disparo termina com erro, como os testes existentes exigem. O log registra só a classe da exceção.

### D5 — OCR fica fora desta etapa

Não existe OCR no repositório. PDF sem texto aparece como `documentos_sem_texto` no rastro e como `EM_REVISAO` no diagnóstico. Nunca é tratado como "não existe".

## 4. Prova

`tests/test_prestacao_localizacao_pdf_composto_e2e.py`: PDF sintético de 12 páginas, armazenado como um Documento vindo de e-mail, com nome de arquivo inútil e sem inventário. O caminho testado é necessidade → fonte por conteúdo → separação por CPF → 12 derivados → corredor → readiness PRONTO → 12 Ordens → Evento → Preview → Autorização → ações PENDING, sem transporte.

O teste também prova:
- sem separação, o mesmo PDF não atende ninguém (comportamento anterior);
- replay não duplica derivados nem ações;
- um colaborador fora do PDF fica sem documento, com o rastro da busca;
- o diagnóstico classifica PRONTO, AUSENTE, EM_REVISAO, ENCONTRADO_NAO_ELEGIVEL, FONTE_INDISPONIVEL e SEM_FONTE.

O corredor é o único ponto substituído, na mesma convenção dos testes de integração existentes. O fake lê o texto real do PDF recebido e só resolve quando há exatamente um CPF.

## 5. Etapa J3/J4 — índice documental e "Prestação do cliente X, competência Y"

### D6 — J2 decidido pelo operador: interno primeiro, Airtable só como ponte somente leitura

A missão aprovada diz "Airtable apenas como bridge transitório onde necessário". A composição real (`orquestrador/composicao_prestacao_real_v1.py`) usa:

- **Fontes internas:** requisitos canônicos em código (`CADASTRO_REQUISITOS_PRESTACAO_V2`), política de competência V1, Postgres (documentos, histórico, lotes, execuções), S3, porta oficial de entrada e alocação histórica para unidade/posto.
- **Airtable, só leitura e pelos adapters que já existem:** clientes ativos, colaboradores esperados, vínculos, candidatos a colaborador (CPF) e cliente por CNPJ. Hoje não há fonte interna equivalente para nenhum deles. O CPF não serve como fonte interna porque a identidade interna guarda só HMAC.
- **Snapshot Funcionário→Local de hoje:** só vale para uma competência se o operador declarar explicitamente (`--snapshot-airtable-comprovado`). Nunca é presumido.
- **Leitor Airtable com cache por execução:** a busca por conteúdo resolveria cliente página a página.

Por que fica na borda (`orquestrador/`) e não em `classificacao/`: a composição importa adapters do Airtable, e o domínio continua sem essa dependência.

### D7 — J3: o índice só recebe documento elegível; a persistência é gate humano

`_alimentar_indice_documental` registra no índice só documentos que o corredor conferiu contra a necessidade (cliente, competência, tipo e colaborador). Na próxima execução, o documento é achado pelo índice antes da busca por conteúdo. O diagnóstico nunca grava no índice. Falha ao gravar gera o evento `indice_documental_falhou` e não derruba o ciclo: o índice acelera a localização, mas não decide.

A tabela (migration 0011) e o adapter Postgres estão numa PR própria (#197), testados contra um Postgres real efêmero. O manifesto em `.magnata/migration-authorizations/` é, pelo formato do projeto, uma **autorização humana específica**, e por isso não foi escrito pelo agente. Até lá, a composição real roda sem índice persistente, só com a busca por conteúdo.

### D8 — Necessidades do CLIENTE atendidas por conteúdo; separação de PDF composto por cliente fica para depois

A busca por conteúdo passou a atender Extrato, FGTS, DCTFWeb e guias pelo **CNPJ exato** do cliente, usando a mesma porta `fonte_cliente_direto` que o corredor usa. Documento de outro cliente nunca é candidato. O corredor e a elegibilidade continuam conferindo tipo e competência.

Documento institucional nunca vira Ordem de colaborador: a partição por colaborador que já existia (J1b) descarta esses documentos, e há teste que cobre isso.

**Não feito nesta etapa: separar um PDF com documentos de VÁRIOS clientes.** A página de continuação de um documento institucional costuma não repetir o CNPJ, então separar de forma estrita cortaria documentos. Sem separação, um PDF desse tipo cai em revisão, nunca em escolha silenciosa.

### D9 — Diagnóstico: "achado mas não elegível" só para o tipo pedido

A busca por conteúdo de cliente devolve todos os documentos daquele cliente. Por isso, `ENCONTRADO_NAO_ELEGIVEL` passou a significar apenas "achei um documento **do tipo pedido**, mas de outro mês, cliente ou pessoa". Quando todos os candidatos foram entendidos e são de outros tipos, o resultado é `AUSENTE`.

### Ponto de entrada

```
python -m magnata_os.orquestrador.prestacao_cliente_competencia_v1 --cliente recXXX --competencia 2026-09
```

- **Sem opções extras:** faz só o diagnóstico, somente leitura.
- **Com `--ate-pending --preset <sem assinatura> --mensagem "..."`:** gera as Ordens até PENDING pelo caminho que já existe, e só quando o pacote está PRONTO. Não há transporte.

Rodar contra o ambiente real é um gate humano (produção).

## 6. O que continua bloqueado por gate material

| Item | Gate |
|---|---|
| J3 — índice persistente (PR #197 pronta: migration, rollback, adapter e testes em Postgres real) | manifesto de autorização humana, depois aplicação da migration no banco real |
| Rodar a Prestação real (`prestacao_cliente_competencia_v1`, composição J4 pronta) contra Postgres/S3/Airtable de produção | acesso à produção |
| Separar PDF composto com documentos de vários clientes | decisão de regra para páginas de continuação sem CNPJ |
| Distribuir documentos institucionais ao cliente (hoje só colaborador recebe Ordem) | decisão de negócio (destinatário, canal e preset do cliente) |
| Fonte Gmail por necessidade (busca com `q=`) | credencial Gmail e ativação (`fase1-gmail-readonly-inerte.md`) |
| Fonte Airtable com download de anexo | acesso externo; o adapter precisa ingerir por hash |
| OCR | nova dependência de sistema (tesseract ou similar) e possível custo |
| Autorização humana real para pacotes com N documentos | hoje só existe para 1 documento sem assinatura (`materializar_documento_pre_canario_operador_real_v1`) |
| Transporte real | três barreiras de `autorizacao_transporte_real.py`, inalteradas |
