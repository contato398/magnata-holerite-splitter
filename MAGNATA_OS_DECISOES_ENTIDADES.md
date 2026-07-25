# Magnata OS — Pauta de Decisões Funcionais sobre Entidades

**Status:** pauta aberta. Nenhuma decisão abaixo é definitiva — todas aguardam
resposta dos responsáveis da Magnata.
**Origem:** cada item deriva diretamente da Seção 11 ("Decisões que o código
não consegue responder") de `MAGNATA_OS_ENTIDADES.md`, mais duas decisões
adicionais criadas nesta pauta a partir dos agrupamentos provisórios sinalizados
na Seção 5 daquele documento (`Distribuição/Envio` e `Solicitação de
Assinatura/Assinatura`).
**Regra de uso:** nenhuma recomendação preliminar aqui deve ser tratada como
decisão tomada. Um item só está resolvido quando o campo "Decisão da Magnata"
deixa de dizer `PENDENTE`.

---

## Modelo Conceitual Aprovado (registrado em 2026-07-22)

Decisão da Direção da Magnata, aplicável a partir desta data. Este modelo
conceitual passa a orientar `MAGNATA_OS_ENTIDADES.md` e as decisões
individuais desta pauta, mesmo antes de qualquer migração técnica:

```text
Empresa Magnata
└── Cliente
    └── Contrato Comercial
        └── Posto de Trabalho

Colaborador
└── Vínculo Trabalhista
    └── Alocação
        └── Posto de Trabalho
```

`Contrato Comercial`, `Vínculo Trabalhista` e `Alocação` passam a fazer parte
do modelo conceitual oficial do Magnata OS a partir de agora — mesmo que
nenhum dos três integre o núcleo técnico mínimo da primeira migração
documental (`MAGNATA_OS_ARQUITETURA.md` §7; `MAGNATA_OS_ENTIDADES.md` §12).
Ou seja: o vocabulário é oficial e deve orientar qualquer decisão futura, mas
a implementação técnica desses três conceitos como tabelas/campos no
Airtable continua sendo trabalho de fases posteriores, não desta pauta.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (mapa de
relacionamentos, §6, e modelo mínimo, §12 — precisam refletir este modelo
conceitual na próxima revisão daquele documento), `MAGNATA_OS_ARQUITETURA.md`
(contratos de dados, §4).

---

## Modelo Conceitual Documental (registrado em 2026-07-22)

Decisão da Direção da Magnata, complementar ao "Modelo Conceitual Aprovado"
acima — este cobre especificamente o núcleo documental (Documento, Arquivo,
Competência, Tipo Documental):

```text
Tipo Documental
└── Documento
    ├── Titularidade
    ├── Competência ou período
    ├── Relação com Cliente
    ├── Relação com Colaborador/Vínculo
    └── Arquivos
        ├── Original
        ├── Processado
        ├── Corrigido
        └── Assinado
```

Registrado também:
- Item de Ingestão existe **antes** da classificação — é o estágio anterior
  ao Documento (chegada do e-mail/anexo, ainda sem Categoria, Competência ou
  Cliente definidos).
- Após a classificação, o Arquivo deve ser vinculado a um Documento.
- Um Item de Ingestão pode originar um ou vários Documentos (ex.: um e-mail
  com Kit de Admissão gera múltiplos Documentos a partir dos mesmos
  Arquivos).
- Um Documento pode receber Arquivos originados de mais de um Item de
  Ingestão, desde que isso seja auditável (ex.: um Documento cujo Arquivo de
  correção chegou por um e-mail diferente do original).

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidades Documento,
Arquivo e Item de Ingestão — mapa de relacionamentos §6 precisa refletir Item
de Ingestão como estágio anterior ao Documento, com possibilidade de origem
N:N entre os dois quando auditável), `MAGNATA_OS_ARQUITETURA.md` (contratos
de dados, §4).

---

## Modelo Conceitual de Distribuição e Entrega (registrado em 2026-07-22)

Decisão da Direção da Magnata, complementar aos dois modelos conceituais
acima — cobre especificamente Distribuição, Envio, Tentativa de Envio e
Evidência de Entrega:

```text
Distribuição
├── finalidade
├── Documentos e Arquivos
├── Destinatários
├── condições de conclusão
└── Envios
    ├── Destinatário
    ├── endereço utilizado
    ├── Canal
    ├── provedor técnico
    ├── Tentativas de Envio
    ├── Evidências de Entrega
    └── possível Envio anterior
```

Registrado também:
- Distribuição, Envio e Tentativa de Envio passam a ser entidades
  conceitualmente separadas (ver DEC-ENT-013, DEC-ENT-007).
- Evidência de Entrega pode ser entidade própria ou registro imutável
  associado ao Envio — a decisão técnica final (qual das duas) ocorrerá na
  revisão de Entidades e Eventos, não nesta pauta.
- Reenvio não apaga nem reutiliza silenciosamente o Envio anterior — cria um
  novo Envio com referência ao anterior (ver DEC-ENT-007).

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio precisa se desdobrar em Distribuição, Envio, Tentativa de Envio e,
possivelmente, Evidência de Entrega; mapa de relacionamentos, §6),
`MAGNATA_OS_ARQUITETURA.md` (módulo Distribuição, §2; contratos de dados,
§4).

---

## Modelo Conceitual de Assinatura (registrado em 2026-07-22)

Decisão da Direção da Magnata, complementar aos modelos conceituais acima —
cobre especificamente Solicitação de Assinatura, Signatário, Assinatura,
Link e Evidência:

```text
Documento
├── Arquivos
├── Distribuições e Envios
└── Solicitação de Assinatura [opcional]
    ├── política de conclusão
    ├── Links de Assinatura
    ├── Signatários
    │   └── Assinaturas
    │       └── Evidências
    └── Arquivo assinado resultante
```

Registrado também:
- Solicitação de Assinatura, Signatário e Assinatura são entidades
  diferentes (DEC-ENT-014, DEC-ENT-023).
- Link é uma credencial temporária (DEC-ENT-024) — não é a Solicitação, nem
  a Assinatura.
- Evidência pode ser entidade própria ou registro imutável (DEC-ENT-025).
- Arquivo assinado é derivação ou versão do Arquivo apresentado
  (DEC-ENT-026, consistente com DEC-ENT-017).
- Nem todo Documento possui Solicitação de Assinatura — é um ramo opcional
  da árvore acima (ver DEC-ENT-022).
- Nem todo Envio possui finalidade de assinatura — um Envio pode servir só
  para entregar o Link, ou para distribuir o Documento sem qualquer relação
  com assinatura.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Solicitação de
Assinatura/Assinatura precisa se desdobrar em Solicitação, Signatário,
Assinatura, Link e Evidência; mapa de relacionamentos, §6),
`MAGNATA_OS_ARQUITETURA.md` (módulo Assinatura, §2; contratos de dados, §4).

---

## DEC-ENT-001 — Cliente e Condomínio: correspondência 1:1?

**Pergunta:** um condomínio sempre corresponde a um Cliente no Airtable, ou
pode haver um Cliente representando vários condomínios (ou o inverso)?

**Por que essa decisão importa:** o sistema hoje trata "Cliente" e
"Condomínio" como sinônimos, sem distinção de dado
(`MAGNATA_OS_ENTIDADES.md`, entidade Cliente, seção "Problemas encontrados").
Se essa suposição for falsa em algum caso real, documentos coletivos
(Extrato, FGTS, Guias) podem estar sendo endereçados ao Cliente errado ou
faltando destinatários.

**Exemplo real ou cenário:** uma administradora de condomínios que gerencia
três condomínios diferentes contrata a Magnata sob um único CNPJ — hoje isso
viraria um único registro de Cliente, mas cada condomínio pode precisar de
Locais, Colaboradores e documentos separados.

**Opções identificadas:**
- A) Manter 1:1 — cada condomínio é sempre um Cliente próprio.
- B) Permitir um Cliente "guarda-chuva" com múltiplos condomínios como
  Postos de Trabalho distintos, mas documentos/faturamento no nível do
  Cliente.
- C) Criar uma entidade própria de Condomínio, separada de Cliente.

**Riscos de cada opção:**
- A) Simples, mas pode já estar errado para algum cliente real hoje sem que
  ninguém tenha percebido.
- B) Exige nada de mudança de schema, só disciplina de cadastro — risco baixo.
- C) Maior custo de modelagem e migração; só se justifica se a distinção for
  frequente e relevante para faturamento ou comunicação separada.

**Decisão registrada (não é mais preliminar):** aprovada uma variação mais
ampla da opção B. Cliente representa a organização contratante da Magnata.
Condomínio **não** será sinônimo estrutural obrigatório de Cliente — será,
inicialmente, uma **classificação/tipo de Cliente**, ao lado de outros tipos
possíveis (empresa, indústria, hospital, escola, loteamento, associação,
órgão público). Não será criada, nesta etapa, uma entidade técnica separada
para Condomínio — salvo se, no futuro, surgirem atributos ou comportamentos
exclusivos que justifiquem a separação, reabrindo esta decisão.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Cliente — a
correspondência 1:1 hoje descrita precisa ser revisada para "Cliente com
atributo Tipo, incluindo Condomínio como um dos tipos possíveis"),
`MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-002 — Colaborador com vínculo simultâneo em mais de um Cliente

**Pergunta:** um Colaborador pode ter mais de um vínculo trabalhista
simultâneo (ex.: dois contratos em clientes diferentes ao mesmo tempo)? Isso
também determina se "múltiplas alocações simultâneas" (mais de um Posto de
Trabalho ao mesmo tempo) é um cenário real a suportar.

**Por que essa decisão importa:** o registro técnico atual (`Funcionários`)
assume um Status/Cargo/Local por Colaborador — não há hoje suporte a mais de
um vínculo ativo simultâneo. Se isso acontece na prática, holerites, ponto e
documentos podem estar sendo misturados entre vínculos diferentes da mesma
pessoa.

**Exemplo real ou cenário:** um colaborador que presta serviço meio período
em dois postos de clientes diferentes, cada um com contrato e pagamento
próprios.

**Opções identificadas:**
- A) Não suportar — cada CPF tem um único vínculo ativo por vez (situação
  atual).
- B) Suportar múltiplos vínculos simultâneos, exigindo separar Colaborador
  (pessoa) de Vínculo (contrato específico) como entidades distintas.

**Riscos de cada opção:**
- A) Simples de manter, mas se o cenário já existe na operação, holerites e
  ponto de vínculos diferentes podem estar sendo tratados como um só,
  mascarando inconsistência.
- B) Exige separar Pessoa/Vínculo — mudança de modelo maior, com migração de
  dados de `Funcionários` para duas tabelas.

**Decisão registrada (não é mais preliminar):** aprovada a opção B, com
condição de faseamento. Colaborador representa a pessoa no contexto
profissional da Magnata; Vínculo Trabalhista representa cada relação
trabalhista/contratual dessa pessoa com a empresa — passam a ser conceitos
formalmente distintos no modelo conceitual (ver "Modelo Conceitual
Aprovado"). Uma pessoa desligada e depois readmitida conserva sua identidade
de Colaborador e recebe um **novo** Vínculo. Datas de admissão e
desligamento, salário, cargo, regime, matrícula e situação passam a
pertencer, prioritariamente, ao Vínculo — não à identidade permanente do
Colaborador. Na primeira fase documental, Colaborador pode continuar como
entidade operacional principal; a separação técnica formal do Vínculo deve
ocorrer antes da migração completa dos módulos de RH, folha, admissão,
férias e rescisão.

Quanto à simultaneidade: a situação normal é um único Vínculo ativo por
Colaborador com a Magnata. Mais de um vínculo ativo simultâneo só é admitido
com fundamento jurídico e operacional válido e expressamente registrado — o
sistema não deve criar vínculos duplicados para representar mudança de
cliente, posto, escala ou cobertura (isso passa a ser papel da Alocação, ver
DEC-ENT-016).

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Colaborador —
precisa ganhar a entidade companheira Vínculo Trabalhista, com nota de que
admissão/desligamento/cargo/salário/matrícula migram para lá; §9, §12),
`MAGNATA_OS_ARQUITETURA.md` (módulo Cadastro).

---

## DEC-ENT-003 — Posto de Trabalho compartilhado entre Clientes (rateio)

**Pergunta:** um Posto de Trabalho pode pertencer a mais de um Cliente ao
mesmo tempo (rateio de custo entre condomínios, por exemplo)? Isso também
resolve a fronteira Cliente × Posto de Trabalho para os casos de exceção.

**Por que essa decisão importa:** o modelo atual assume 1:N estrito (`Locais.
Cliente` é um link único). Se existir rateio real, relatórios por Cliente
(faturamento, indicadores de posto) podem estar atribuindo 100% do custo/
indicador a um único Cliente quando deveria ser dividido.

**Exemplo real ou cenário:** um posto de portaria compartilhado por dois
condomínios vizinhos com um acordo de rateio de custo do colaborador.

**Opções identificadas:**
- A) Manter 1:N estrito — todo Posto pertence a exatamente um Cliente
  (situação atual).
- B) Permitir múltiplos Clientes por Posto, com percentual de rateio como
  atributo da relação.

**Riscos de cada opção:**
- A) Simples, mas se o rateio existe na prática hoje, provavelmente está
  sendo resolvido por fora do sistema (planilha paralela, ajuste manual).
- B) Exige modelar a relação Cliente↔Posto como tabela associativa com
  atributo (percentual), não mais um link direto simples.

**Decisão registrada (não é mais preliminar):** aprovada a opção A, com o
mecanismo de rateio deslocado para outro conceito. Um Posto de Trabalho
**não poderá pertencer simultaneamente a clientes diferentes** — a relação
Cliente↔Posto continua 1:N estrita. Posto de Trabalho representa uma posição
ou necessidade operacional prevista (ex.: Portaria Principal, Portaria de
Serviço, Limpeza, Zeladoria, Ronda, Controlador de Acesso Diurno/Noturno) —
não uma pessoa; um colaborador não é proprietário permanente de um posto.
Futuramente, o Posto também deverá se relacionar a um Contrato Comercial
(ver "Modelo Conceitual Aprovado").

Quando um colaborador trabalha para mais de um cliente, isso não vira Posto
compartilhado — vira **alocações distintas por cliente e posto** (ver
DEC-ENT-016, Alocação), cada uma podendo registrar percentual, horas, dias,
turno ou outro critério de rateio, permitindo apuração de custo, prestação
de contas, jornada e responsabilidade contratual por cliente.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Posto de
Trabalho — remover a hipótese de rateio por múltiplos Clientes por Posto;
registrar a relação futura com Contrato Comercial e com a nova entidade
Alocação, §9), `MAGNATA_OS_ARQUITETURA.md` (§4).

---

## DEC-ENT-004 — Documento pertencente a mais de uma Competência

**Pergunta:** um Documento pode pertencer a mais de uma Competência (ex.:
período de transição de mês, ou documento retroativo que cobre dois meses)?

**Por que essa decisão importa:** hoje `Competência` é um campo único por
Documento. Se um documento legitimamente cobre duas competências, ele está
sendo forçado a "escolher" uma, o que pode causar ausência em relatórios
mensais da competência não escolhida.

**Exemplo real ou cenário:** um acerto retroativo que corrige valores de Maio
mas é processado e distribuído em Julho — hoje entraria como Competência
"Maio" ou "Julho", nunca as duas.

**Opções identificadas:**
- A) Manter Competência única por Documento (situação atual), com convenção
  clara de qual competência prevalece em caso de ambiguidade.
- B) Permitir múltiplas Competências por Documento (campo de múltipla
  seleção ou relação).

**Riscos de cada opção:**
- A) Simples, mas exige uma convenção explícita de desempate hoje inexistente
  (ver achado do v2.48 sobre competência por extenso).
- B) Mais correto para casos retroativos, mas aumenta a complexidade de todo
  relatório que hoje assume "1 documento = 1 competência".

**Decisão registrada (não é mais preliminar):** aprovada a opção A, com
estrutura conceitual explícita. Competência representa o período de negócio
ao qual o Documento se refere — diferente da data de criação, upload,
processamento, pagamento ou envio. Competência não deve ser inferida
exclusivamente pelo nome ou pela data do Arquivo. Um Documento deve possuir
classificação de competência compatível com seu tipo, usando um destes três
formatos conceituais:
- `MENSAL` — registra ano e mês (ex.: holerite de um mês específico).
- `PERIODO` — registra data inicial e data final, quando conhecidas (ex.:
  documento retroativo que cobre uma faixa de tempo).
- `NAO_APLICAVEL` — quando o Documento não tem competência de negócio real;
  não inventar competência nesse caso.

A implementação técnica dos nomes de campo para representar isso nos
contratos de dados será definida posteriormente — esta decisão fixa o
conceito, não o schema.

**Documento com múltiplas competências:** a regra normal é um Documento
possuir uma única competência principal. Documentos que abrangem vários
meses devem ser tratados como Documento de tipo `PERIODO`, não como lista
livre de competências soltas. Quando um Arquivo recebido contiver vários
documentos de competências diferentes, o processamento deve gerar Documentos
separados sempre que for possível identificar os limites entre eles. Não se
deve duplicar um mesmo Documento apenas para atribuir-lhe várias
competências.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Documento —
substituir o campo único `Competência` (texto livre) pelo conceito
`MENSAL`/`PERIODO`/`NAO_APLICAVEL`), `MAGNATA_OS_ARQUITETURA.md` (contratos
de dados).

---

## DEC-ENT-005 — Titularidade do Holerite: Colaborador, Vínculo, ou ambos?

**Pergunta:** um Holerite pertence ao Colaborador, ao Vínculo, ou aos dois —
e se um Colaborador tiver mais de um vínculo ao longo do tempo, como o
histórico de holerites deve ser reagrupado?

**Por que essa decisão importa:** liga-se diretamente a DEC-ENT-002. Sem
resposta, não é possível decidir se a separação Pessoa/Vínculo é
justificável para o histórico de holerites de alguém que foi desligado e
recontratado, por exemplo.

**Exemplo real ou cenário:** um colaborador desligado em 2025 e recontratado
em 2026 — os holerites do primeiro período devem aparecer junto com os do
segundo, ou como históricos de vínculos distintos?

**Opções identificadas:**
- A) Holerite pertence ao Colaborador (CPF), independente de quantos vínculos
  ele teve — histórico único e contínuo (situação atual, implícita).
- B) Holerite pertence ao Vínculo específico — histórico segmentado por
  período de contrato.

**Riscos de cada opção:**
- A) Simples, mas mistura períodos de vínculos diferentes como se fossem um
  histórico contínuo, o que pode confundir relatórios de tempo de casa ou
  cálculos que dependam de continuidade de vínculo.
- B) Mais correto para fins trabalhistas, mas exige a entidade Vínculo existir
  de fato (depende de DEC-ENT-002).

**Decisão registrada (não é mais preliminar):** aprovada a opção B, com
faseamento consistente com DEC-ENT-002. O holerite pertence prioritariamente
ao Vínculo Trabalhista. Deve manter relação com o Colaborador correspondente,
e deve possuir Competência (ver DEC-ENT-004). Pode possuir relação com
Cliente, Posto de Trabalho ou Alocação para fins operacionais, de
distribuição, rateio e prestação de contas — mas Cliente ou Posto não
substituem a titularidade do Vínculo. Durante a primeira fase, enquanto
Vínculo não estiver tecnicamente separado (DEC-ENT-002), Colaborador pode ser
usado como referência operacional para o holerite, desde que a futura
migração para Vínculo permaneça prevista e não seja tratada como decisão
definitiva de titularidade.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Colaborador e
futura entidade Vínculo Trabalhista — Holerite precisa referenciar Vínculo
como titular principal, com Colaborador como referência operacional
transitória), `MAGNATA_OS_ARQUITETURA.md` (contratos de dados).

---

## DEC-ENT-006 — Documento comum a vários Clientes: replicar ou relacionar?

**Pergunta:** um Documento comum a vários clientes (ex.: uma nota fiscal de
fornecedor comum) é replicado fisicamente por cliente, ou é um único registro
relacionado a vários clientes?

**Por que essa decisão importa:** define se "Documento" pode ter uma relação
N:N com Cliente, ou se a regra é sempre 1 Documento = 1 Cliente (com
duplicação física do PDF quando necessário, como já ocorre hoje em alguns
fluxos de fatiamento por CNPJ).

**Exemplo real ou cenário:** uma guia coletiva que, por regra fiscal, cobre
mais de um cliente ao mesmo tempo (situação já mencionada na Fase 2 da
Classificação, para Guias/FGTS coletivos).

**Opções identificadas:**
- A) Duplicar fisicamente o PDF por cliente (situação atual predominante,
  via fatiamento).
- B) Um único Documento relacionado a vários Clientes (N:N), sem duplicar o
  arquivo físico.

**Riscos de cada opção:**
- A) Simples e já implementado, mas gera redundância de armazenamento e risco
  de os PDFs duplicados divergirem se um for corrigido e o outro não.
- B) Evita redundância, mas exige que Distribuição saiba lidar com "um
  Documento, vários destinatários" sem confundir com Envio individual.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Um
Documento comum existe uma única vez; o mesmo Documento pode estar
relacionado a vários Clientes. O Arquivo oficial não deve ser duplicado
apenas para permitir distribuição — cada Cliente pode receber um Envio
separado referenciando o mesmo Documento e o mesmo Arquivo. A distribuição
individualizada não cria automaticamente novos Documentos. Quando houver
conteúdo efetivamente personalizado por Cliente, deve ser criado um Documento
derivado ou um Arquivo gerado especificamente, com origem e relacionamento
rastreáveis — não uma cópia silenciosa. Exemplos de documentos
potencialmente comuns: guia geral de FGTS, DARF/DCTFWeb, certidões, extrato
da folha, comprovantes gerais, documentos institucionais.

Esta decisão substitui, como alvo de arquitetura, a prática atual
predominante de fatiamento físico por cliente (opção A, hoje em produção). A
migração do comportamento atual para o modelo N:N é trabalho de fase
posterior (`MAGNATA_OS_ARQUITETURA.md` §7), não uma mudança imediata de
código.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Documento —
mudar de "1 Documento = 1 Cliente com duplicação física" para "1 Documento
N:N Clientes, Arquivo único"), `ARQUITETURA_FASE_2_DECISAO_FINAL.md`,
`MAGNATA_OS_ARQUITETURA.md` (módulo Distribuição — Envio passa a referenciar
Documento comum sem duplicar Arquivo).

---

## DEC-ENT-007 — Reenvio: novo Envio ou nova Tentativa?

**Pergunta:** o reenvio de um Envio cria um novo registro de Envio, ou
incrementa a Tentativa do Envio existente? Isso também resolve a fronteira
entre Envio e Tentativa de Envio.

**Por que essa decisão importa:** o campo `Tentativa` já existe
(`MAGNATA_OS_ENTIDADES.md`, entidade Distribuição/Envio), sugerindo que a
intenção original era "mesmo Envio, tentativa incrementada" — mas isso nunca
foi confirmado como regra de negócio aplicada uniformemente em todos os
fluxos de reenvio.

**Exemplo real ou cenário:** um envio de holerite via WhatsApp falha por
número inválido; depois de corrigido o cadastro, o envio é refeito — isso
deve aparecer como o mesmo registro de Envio com Tentativa 2, ou como um novo
Envio?

**Opções identificadas:**
- A) Mesmo Envio, Tentativa incrementada (parece ser a intenção original do
  campo `Tentativa`).
- B) Novo registro de Envio a cada reenvio, com histórico de Envios
  relacionados.

**Riscos de cada opção:**
- A) Mais simples de consultar ("qual o status atual deste envio"), mas perde
  granularidade de quando cada tentativa individual ocorreu, se não houver
  também um timestamp por tentativa.
- B) Preserva histórico completo, mas multiplica registros e exige agrupar
  por "envio lógico" para saber o estado atual.

**Decisão registrada (não é mais preliminar):** aprovada uma síntese das duas
opções, distinguindo dois conceitos que a pergunta original tratava como um
só. Tentativa de Envio representa cada execução técnica para concluir um
Envio — timeout, repetição automática, retry do Celery e nova chamada ao
mesmo provedor são novas Tentativas do **mesmo** Envio, quando a intenção de
negócio não mudou (corresponde à opção A original). Reenvio representa uma
nova **decisão operacional** de realizar novamente a entrega — um Reenvio
cria um **novo** Envio (corresponde à opção B original), que mantém
referência ao Envio anterior e ao motivo do reenvio; cada novo Envio tem
suas próprias Tentativas. Não se cria um novo Envio apenas porque ocorreu
retry técnico; e não se registra como simples Tentativa um novo envio
solicitado por usuário, mudança de Arquivo, mudança de destinatário, mudança
de canal ou repetição deliberada da entrega.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio — precisa da distinção Tentativa×Reenvio e dos atributos "Envio
anterior"/"motivo do reenvio"), `MAGNATA_OS_ARQUITETURA.md` (máquina de
estados, §5).

---

## DEC-ENT-008 — Assinatura com múltiplos signatários

**Pergunta:** uma Assinatura pode ter mais de um signatário (documento
coletivo assinado por vários colaboradores em sequência)?

**Por que essa decisão importa:** o modelo atual assume 1:1 Assinatura↔
Colaborador (`F_ASS_FUNCIONARIO`, link único). Se algum documento exigir
assinatura de múltiplas pessoas (ex.: termo com testemunha, ou documento
coletivo de equipe), o modelo atual não comporta isso sem duplicar o
registro de Assinatura por pessoa.

**Exemplo real ou cenário:** um termo de responsabilidade de equipamento
compartilhado que exige assinatura do colaborador e de um responsável
adicional.

**Opções identificadas:**
- A) Manter 1:1 — cada signatário gera sua própria Solicitação de Assinatura
  (mesmo documento, registros de assinatura separados).
- B) Modelar Assinatura com múltiplos signatários por registro, com status
  individual por signatário.

**Riscos de cada opção:**
- A) Simples e já suportado pelo modelo atual, mas gera N registros de
  Assinatura para o "mesmo" documento, o que pode confundir relatórios de
  "documento assinado" se não houver agrupamento.
- B) Mais correto para o caso de múltiplos signatários, mas exige mudança de
  modelo (relação N:N Assinatura↔Colaborador com status por parte).

**Decisão registrada (não é mais preliminar):** aprovada a opção B, com
política configurável. Uma Solicitação de Assinatura pode possuir um ou
vários Signatários (ver DEC-ENT-023). A política de conclusão indica se:
todos devem assinar, qualquer um pode assinar, existe quantidade mínima, ou
existe ordem sequencial — adotados conceitualmente os valores `TODOS`,
`QUALQUER_UM`, `QUANTIDADE_MINIMA`, `SEQUENCIAL` (nomes técnicos finais a
definir nos contratos de dados). A Solicitação só pode ser concluída quando
sua política for satisfeita (ver DEC-ENT-027, estado `CONCLUIDA`).
Assinaturas parciais permanecem registradas e auditáveis — não são
descartadas nem escondidas enquanto a política não for satisfeita. A recusa
ou expiração de um Signatário é avaliada conforme a política da Solicitação,
sem encerrar automaticamente os demais casos (ex.: sob `QUALQUER_UM`, a
recusa de um Signatário não invalida a possibilidade de outro assinar).

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Solicitação de
Assinatura — precisa do atributo de política de conclusão e da relação N:N
com Signatário), `MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-009 — Evidência mínima de entrega concluída

**Pergunta:** qual é a evidência mínima exigida pela empresa (não pelo
código) para considerar uma entrega de documento "concluída" — o envio foi
disparado sem erro, ou a leitura precisa ser confirmada pelo destinatário?

**Por que essa decisão importa:** hoje o campo `Status` do Envio mistura
`Enviado` (o disparo não falhou) com `Lido` (o destinatário abriu o link do
recibo) no mesmo vocabulário de estado — sem uma definição de negócio clara
de qual dos dois conta como "entrega concluída" para fins de auditoria/
compliance.

**Exemplo real ou cenário:** em uma eventual disputa trabalhista sobre se um
holerite foi entregue, a empresa precisa saber se "enviado" já é prova
suficiente, ou se só "lido" comprova a entrega.

**Opções identificadas:**
- A) `Enviado` já conta como entrega concluída (o disparo sem erro é
  suficiente).
- B) Só `Lido` (confirmação de leitura) conta como entrega concluída —
  `Enviado` é um estado intermediário.
- C) Depender do tipo de documento (ex.: holerite exige leitura confirmada;
  comunicado geral não exige).

**Riscos de cada opção:**
- A) Mais simples, mas juridicamente mais fraco como prova de entrega.
- B) Mais forte como prova, mas depende do destinatário abrir o link — pode
  gerar documentos "pendentes" por tempo indefinido se o destinatário nunca
  abrir.
- C) Mais preciso, mas exige regra por categoria documental, aumentando a
  complexidade do modelo de estado.

**Decisão registrada (não é mais preliminar):** aprovada a opção C, com
níveis conceituais de evidência explícitos, escalonados por rigor crescente:

1. `REGISTRADO_INTERNAMENTE` — Envio criado no Magnata OS.
2. `ACEITO_PELO_PROVEDOR` — o provedor aceitou a solicitação sem erro
   imediato.
3. `ENVIADO_PELO_PROVEDOR` — o provedor informa que despachou ou processou a
   mensagem.
4. `ENTREGUE` — existe confirmação de entrega ao servidor, dispositivo ou
   conta destinatária.
5. `LIDO_OU_ABERTO` — existe evidência de leitura ou abertura, quando
   suportada pelo canal.
6. `CONFIRMADO_PELO_DESTINATARIO` — houve ação inequívoca (resposta,
   confirmação, download autenticado ou assinatura).

Regras associadas: HTTP 200/201 não comprova, por si só, entrega ao
destinatário — é, no máximo, `ACEITO_PELO_PROVEDOR`. Aceitação do provedor
não deve ser registrada como leitura ou confirmação. Canais que não
fornecem determinado nível de evidência não devem inventá-lo. Para envio
operacional comum, o critério mínimo pode ser `ACEITO_PELO_PROVEDOR` sem
erro posterior conhecido. Para processos com exigência jurídica, contratual
ou de auditoria (ex.: holerite, documento de rescisão), a condição de
conclusão deve ser configurada conforme a finalidade — entrega, leitura,
acesso autenticado, confirmação do destinatário, ou assinatura. A política
específica por tipo de processo será definida nos contratos e capacidades,
em documento posterior — esta decisão fixa o vocabulário e a regra de
escalonamento, não a política final por tipo de documento.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio — o campo único `Status`, hoje misturando `Enviado`/`Lido`, precisa
migrar para o vocabulário de evidência em camadas), `MAGNATA_OS_ARQUITETURA.md`
(máquina de estados, §5), `MAGNATA_OS_MANIFESTO.md` (princípio 12, Auditoria
Obrigatória — sem necessidade de alteração de texto lá, só referência).

---

## DEC-ENT-010 — Natureza do Alerta de Ponto: vira Pendência Documental?

**Pergunta:** um Alerta de Ponto deve, em algum momento, se transformar em
uma Pendência Documental (por exemplo, gerar um documento de justificativa
formal), ou os dois fluxos são e devem permanecer completamente
independentes?

**Por que essa decisão importa:** hoje os dois compartilham a mesma tabela
(`Pendências/Revisar`) por acidente de implementação, não por decisão de que
deveriam se relacionar (achado crítico #2 da auditoria de entidades). Definir
isso determina se a separação recomendada em `MAGNATA_OS_ENTIDADES.md` (§7)
deve, além de separar as tabelas, também desenhar uma ponte formal entre as
duas entidades.

**Exemplo real ou cenário:** um colaborador crônico em atraso gera Alertas de
Ponto recorrentes — em algum momento isso deveria virar um documento formal
de advertência ou justificativa, ligado ao histórico de alertas?

**Opções identificadas:**
- A) Independentes — Alerta de Ponto é só um dado interno de RH; nunca vira
  Documento.
- B) Um Alerta de Ponto (ou acúmulo deles) pode gerar uma Pendência
  Documental formal, com rastreabilidade da origem.

**Riscos de cada opção:**
- A) Mais simples, mas mantém dois domínios que hoje já colidem
  acidentalmente numa tabela só — sem justificar por que colidem.
- B) Cria uma ponte de negócio real, mas exige desenhar a regra de quando um
  Alerta "vira" Pendência (limiar de recorrência? decisão manual?).

**Recomendação preliminar (sujeita à validação do negócio):** independente da
resposta, a separação técnica das duas tabelas (achado crítico) deveria
acontecer de qualquer forma — esta decisão só define se, depois de
separadas, uma ponte formal entre elas deve existir.

**Decisão da Magnata:** `PENDENTE`
**Responsável pela decisão:** `PENDENTE`
**Data da decisão:** `PENDENTE`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidades Pendência
Documental e Alerta de Ponto, §6, §7).

---

## DEC-ENT-011 — Significado de negócio de `Fechamento` e `SBJ`

**Pergunta:** o que exatamente significam as tabelas `Fechamento` e `SBJ` do
ponto de vista do negócio — quem consulta esses dados hoje e para qual
decisão?

**Por que essa decisão importa:** o levantamento de código não conseguiu
confirmar a granularidade exata de `Fechamento` nem o significado da sigla
`SBJ` — são marcados como `[INFERÊNCIA]` em `MAGNATA_OS_ENTIDADES.md`. Sem
essa resposta, essas duas entidades não podem ser formalizadas com segurança.

**Exemplo real ou cenário:** não aplicável — esta é uma pergunta de
esclarecimento, não de escolha entre alternativas de modelagem.

**Opções identificadas:** não aplicável (pergunta de esclarecimento factual,
não de decisão entre alternativas).

**Riscos de cada opção:** não aplicável.

**Recomendação preliminar (sujeita à validação do negócio):** agendar uma
leitura completa de `src/services/secullum_ponto.py` junto com quem usa esses
relatórios no dia a dia, antes de qualquer formalização de schema para Ponto.

**Decisão da Magnata:** `PENDENTE`
**Responsável pela decisão:** `PENDENTE`
**Data da decisão:** `PENDENTE`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (glossário, §3 e §4).

---

## DEC-ENT-012 — Existência real de `Finalizado` e `Pronto` no Airtable

**Pergunta:** existem, de fato, estados `Finalizado` e `Pronto` configurados
diretamente no Airtable (fora do que o código escreve)? Se sim, em qual
tabela/campo, e eles são sinônimos de estados já canônicos, ou representam
algo genuinamente diferente?

**Por que essa decisão importa:** esses dois nomes foram citados como
divergência conhecida, mas a leitura de `app.py` não encontrou nenhuma
ocorrência literal deles — apenas uma descrição textual próxima
("Pronto para enviar WhatsApp") associada a um campo placeholder ainda não
criado no Airtable. Sem verificação direta do schema, não é possível saber se
são estados reais, e a máquina de estados canônica não pode ser fechada com
segurança.

**Exemplo real ou cenário:** não aplicável — pergunta de verificação factual.

**Opções identificadas:**
- A) São opções reais criadas manualmente na interface do Airtable, sinônimas
  de `Concluído`/`Enviado` — devem ser aposentadas em favor do vocabulário
  canônico.
- B) São opções reais com significado genuinamente distinto — precisam
  entrar na máquina de estados canônica como estados próprios.
- C) Não existem de fato — foram citados por lembrança imprecisa, e não há
  ação necessária.

**Riscos de cada opção:** não aplicável até a verificação factual ocorrer;
qualquer decisão de schema tomada antes dessa verificação corre risco de
resolver um problema que pode não existir da forma descrita.

**Recomendação preliminar (sujeita à validação do negócio):** verificar
diretamente o schema do Airtable (via API ou interface) antes de qualquer
outra ação sobre este item — é a única decisão desta pauta que depende de
uma consulta técnica simples, não de uma escolha de negócio.

**Decisão da Magnata:** `PENDENTE`
**Responsável pela decisão:** `PENDENTE`
**Data da decisão:** `PENDENTE`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (§3, §10),
`MAGNATA_OS_ARQUITETURA.md` (máquina de estados, §5).

---

## DEC-ENT-013 — Distribuição × Envio: uma entidade ou duas?

**Pergunta:** `Distribuição` e `Envio` devem continuar modelados como uma
única entidade (situação provisória atual), ou o negócio identifica um ciclo
de vida próprio para "Distribuição" (o ato de decidir o que/quem/quando
distribuir) separado do "Envio" (o registro técnico de uma tentativa de
entrega por canal)?

**Por que essa decisão importa:** esta pauta nasce diretamente da nota
provisória adicionada à Seção 5 de `MAGNATA_OS_ENTIDADES.md` nesta rodada de
correção — o agrupamento atual reflete o que o código já trata como um
conceito só, mas isso não foi validado como decisão arquitetural definitiva.

**Exemplo real ou cenário:** se no futuro a Magnata quiser um relatório de
"quantos documentos foram distribuídos este mês" independente de quantos
Envios (tentativas/canais) cada um gerou, isso já sugere que Distribuição
precisa de identidade própria, separada de Envio.

**Opções identificadas:**
- A) Manter uma entidade só (situação atual) — Distribuição é só o nome do
  módulo/capacidade, Envio é o registro.
- B) Separar formalmente: Distribuição como o "pedido de distribuir" (pode
  gerar 1 ou vários Envios, por canal ou por destinatário) e Envio como o
  registro técnico de cada tentativa.

**Riscos de cada opção:**
- A) Mais simples, mas já mistura granularidades (módulo vs. registro) —
  risco baixo enquanto o volume de canais/destinatários por documento for
  pequeno.
- B) Mais correto para relatórios agregados, mas exige mudança de schema
  (nova tabela/relação) sem benefício claro se o cenário do exemplo acima não
  for uma necessidade real hoje.

**Decisão registrada (não é mais preliminar):** aprovada a opção B — inverte
a recomendação preliminar anterior. Distribuição e Envio são entidades
diferentes. Distribuição representa a decisão, obrigação ou intenção de
entregar determinados Documentos e Arquivos a determinados destinatários;
Envio representa cada entrega concreta realizada ou tentada por um canal e
para um destinatário. Uma Distribuição pode gerar um ou vários Envios.
Conforme o caso, uma Distribuição define: finalidade, Documentos, Arquivos,
destinatários, canais permitidos, competência, regras de agrupamento e
condições de conclusão. Cada combinação relevante de destinatário e canal
gera um Envio próprio. A conclusão de um Envio não significa
automaticamente a conclusão de toda a Distribuição — isso depende das
condições de conclusão definidas pela Distribuição (ver DEC-ENT-009, níveis
de evidência).

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (§5 — a nota provisória
de agrupamento único deixa de valer; Distribuição e Envio precisam virar
entidades separadas, com Distribuição 1:N Envio), `MAGNATA_OS_ARQUITETURA.md`
(módulo Distribuição, §2 — a unificação de fila+disparo por canal, já
recomendada no plano de migração, passa a se apoiar neste modelo de
Distribuição→Envios).

---

## DEC-ENT-014 — Solicitação de Assinatura × Assinatura: uma entidade ou duas?

**Pergunta:** `Solicitação de Assinatura` (o pedido, ainda pendente) e
`Assinatura` (a evidência, já concluída) devem continuar modelados como uma
única entidade com estados (situação provisória atual), ou o negócio
identifica motivo para tratá-los como duas entidades com ciclos de vida
distintos?

**Por que essa decisão importa:** assim como DEC-ENT-013, esta pauta nasce da
nota provisória adicionada à Seção 5 nesta rodada. Hoje ambos vivem no mesmo
registro técnico (`Assinaturas`), com `Status` transicionando de `Pendente`
para `Assinado`/`Expirado` — funcional, mas sem separação formal entre "o que
foi pedido" e "o que foi provado".

**Exemplo real ou cenário:** se a Magnata precisar um dia de um relatório de
"quantas solicitações de assinatura foram feitas versus quantas geraram
evidência válida", isso já indica que separar as duas entidades traria
clareza — hoje esse relatório teria que inferir isso a partir do `Status`.

**Opções identificadas:**
- A) Manter uma entidade só com estados (situação atual).
- B) Separar Solicitação de Assinatura (pedido, com expiração) de Assinatura
  (evidência concluída), com relação 1:0..1 entre elas.

**Riscos de cada opção:**
- A) Mais simples e já funcional, mas mistura "intenção" com "prova" no
  mesmo registro — mesmo problema conceitual, em menor escala, do que a
  mistura de Documento×Assinatura já identificada como achado crítico.
- B) Mais correto conceitualmente, mas exige migração de schema sem
  benefício imediato claro além de clareza de relatório.

**Decisão registrada (não é mais preliminar):** aprovada a opção B — inverte
a recomendação preliminar anterior. Solicitação de Assinatura representa o
processo criado para obter uma ou mais assinaturas sobre um Documento e um
Arquivo específicos. Assinatura representa o ato individual realizado por um
Signatário (ver DEC-ENT-023). São entidades diferentes. Uma Solicitação pode
existir sem nenhuma Assinatura realizada; pode possuir uma ou várias
Assinaturas (ver DEC-ENT-008, múltiplos signatários). Uma Assinatura
individual não representa necessariamente a conclusão da Solicitação — a
conclusão depende da política de conclusão aplicável (DEC-ENT-008). A
Solicitação deve referenciar o Documento e o Arquivo apresentados por
identificador canônico, nunca por texto livre — corrigindo o achado crítico
da referência textual solta (`F_ASS_PROCESSAR_ID`) hoje usada entre
Assinatura e Processar Arquivos. Cada Assinatura deve referenciar:
Solicitação, Signatário, Arquivo apresentado, e evidências correspondentes
(ver DEC-ENT-025). Relacionamentos futuros devem usar identificadores
canônicos.

**Relação com Distribuição:** Distribuição e Solicitação de Assinatura são
processos independentes — a decisão `DEC-ENT-022` permanece como fonte
oficial da aplicabilidade da assinatura. A Solicitação pode utilizar um
Envio para entregar o Link de Assinatura (DEC-ENT-024) ao Signatário; o
Envio do Link não representa a Assinatura, e a falha no Envio do Link não
transforma automaticamente o Documento em erro. Quando a finalidade exigir
assinatura, Distribuição e Solicitação podem ser relacionadas por
identificadores próprios, mas cada processo mantém estados, tentativas e
evidências independentes.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (§5 — a nota provisória
de agrupamento único deixa de valer; Solicitação de Assinatura e Assinatura
precisam virar entidades separadas, com Solicitação 1:N Assinatura;
referência a Documento/Arquivo por texto livre precisa virar link
canônico), `MAGNATA_OS_ARQUITETURA.md` (módulo Assinatura, §2; contratos de
dados, §4).

---

## DEC-ENT-015 — Documento × Arquivo: confirmar que a distinção atual é suficiente

**Pergunta:** a distinção já modelada entre Documento (conceito lógico:
categoria, competência, destinatário) e Arquivo (o PDF físico) cobre todos os
casos reais de negócio, ou existe algum cenário em que a empresa precisa
tratar um Documento sem nenhum Arquivo físico associado (ex.: um registro de
intenção antes do PDF chegar)?

**Por que essa decisão importa:** diferente das demais decisões desta pauta,
`MAGNATA_OS_ENTIDADES.md` não encontrou nenhuma ambiguidade real aqui — a
entidade Arquivo é descrita como "o conceito mais estável e menos ambíguo do
levantamento", sem decisão pendente de negócio identificada. Este item existe
como um pedido de ratificação formal, não como um dilema em aberto — incluído
nesta pauta porque foi explicitamente solicitado, não porque o documento de
entidades tenha identificado um problema aqui.

**Exemplo real ou cenário:** nenhum cenário de ambiguidade foi identificado
na leitura do código; não há um caso real documentado que contradiga o
modelo atual.

**Opções identificadas:**
- A) Ratificar o modelo atual como está (Documento lógico, Arquivo físico,
  1:N) — nenhuma mudança necessária.
- B) Caso o negócio identifique um cenário real de Documento sem Arquivo
  (não encontrado nesta investigação), avaliar suporte a isso separadamente.

**Riscos de cada opção:**
- A) Nenhum risco identificado — é a continuação do que já funciona.
- B) Não se aplica sem um cenário real concreto trazido pelo negócio.

**Decisão registrada (não é mais preliminar):** aprovada, ampliando a opção A
com regras explícitas de relação. Documento representa um objeto de negócio
com significado próprio; Arquivo representa uma manifestação digital ou
física do Documento — não são sinônimos. Um Documento pode possuir um ou
vários Arquivos. Um Arquivo deve pertencer a um Documento, salvo arquivos
ainda não classificados dentro de Item de Ingestão (que existem antes da
classificação — ver "Modelo Conceitual Documental"). PDFs originais, PDFs
fatiados, versões corrigidas e arquivos assinados são Arquivos diferentes
relacionados ao mesmo Documento, **quando preservarem o mesmo significado de
negócio** — ex.: holerite de João, competência Junho/2026: PDF recebido da
contabilidade = Arquivo original; página fatiada = Arquivo processado;
versão substitutiva = Arquivo corrigido; versão pós-assinatura = Arquivo
assinado — todos o mesmo Documento (ver também DEC-ENT-017, versões de
Arquivo). Quando houver mudança real de significado, titularidade,
competência ou conteúdo jurídico, deve ser avaliada a criação de um novo
Documento derivado, não apenas um novo Arquivo do mesmo Documento.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidades Documento e
Arquivo, §5 e §9 — precisam incorporar a regra de "mesmo significado de
negócio = mesmo Documento, novo Arquivo" e a exceção de Item de Ingestão),
`MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-016 — Alocação: conceito registrado, distinto de Vínculo

**Pergunta:** como representar onde, em qual Posto de Trabalho e durante qual
período um Colaborador efetivamente trabalha — e como isso se diferencia de
Vínculo Trabalhista (a relação contratual em si)?

**Por que essa decisão importa:** sem um conceito de Alocação separado do
Vínculo, toda transferência, cobertura, substituição ou trabalho volante
teria que ser representada como mudança de Vínculo (ou, pior, como campo
solto de "Local atual" dentro do Colaborador, como ocorre hoje em
`Funcionários`) — perdendo o histórico de onde a pessoa efetivamente
trabalhou em cada período, e sem suporte a rateio entre clientes (ver
DEC-ENT-003, DEC-ENT-006).

**Exemplo real ou cenário:** um Colaborador com um único Vínculo ativo que,
ao longo do mês, cobre turnos em dois Postos diferentes por escala, ou é
temporariamente transferido de Posto — hoje isso não tem onde ser registrado
como histórico formal, só como o "Local" atual do Funcionário.

**Opções identificadas:**
- A) Não separar — continuar usando o campo de Local/Posto atual dentro do
  próprio registro de Colaborador/Vínculo, sem histórico de alocação.
- B) Criar Alocação como conceito próprio: um Vínculo pode ter várias
  Alocações ao longo do tempo, e mais de uma Alocação no mesmo período
  quando a operação real exigir (ex.: rateio entre clientes).

**Riscos de cada opção:**
- A) Mais simples, mas sem histórico de onde a pessoa trabalhou em cada
  período — perde-se rastreabilidade de transferência, cobertura e rateio
  entre clientes.
- B) Exige nova entidade e nova relação (Vínculo 1:N Alocação, Alocação N:1
  Posto), mas é a única forma de suportar rateio e histórico de
  transferência sem duplicar Vínculo.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Alocação
representa onde, em qual Posto de Trabalho e durante qual período o
Colaborador trabalha — é um conceito diferente de Vínculo. Transferências,
coberturas, substituições e trabalho volante são representados por mudanças
ou períodos de Alocação, não por novo Vínculo. Um único Vínculo pode ter
várias Alocações ao longo do tempo, e pode haver mais de uma Alocação no
mesmo período quando a operação real exigir (ex.: rateio entre clientes,
DEC-ENT-003/DEC-ENT-006).

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (nova entidade Alocação
a incluir na Seção 5, com relação a Vínculo Trabalhista e a Posto de
Trabalho; mapa de relacionamentos, §6), `MAGNATA_OS_ARQUITETURA.md` (módulo
Cadastro/Ponto — Alocação passa a ser a unidade de rateio e histórico de
transferência).

---

## DEC-ENT-017 — Versões de Arquivo: histórico e vigência

**Pergunta:** como representar que um mesmo Documento pode ter vários
Arquivos ao longo do tempo (original, processado, corrigido, assinado) sem
perder o histórico quando um Arquivo é substituído?

**Por que essa decisão importa:** liga-se diretamente a DEC-ENT-015. Sem uma
noção formal de versão/vigência, uma correção de Arquivo (ex.: holerite
corrigido) pode sobrescrever silenciosamente o anterior, perdendo evidência
de auditoria de qual versão foi originalmente distribuída a cada
destinatário.

**Exemplo real ou cenário:** um holerite é enviado; depois um erro de valor é
identificado e uma versão corrigida é gerada — é preciso saber, depois, que
existiu uma versão anterior, qual foi enviada a quem, e qual é a vigente
hoje.

**Opções identificadas:**
- A) Sobrescrever o Arquivo anterior ao corrigir (situação de risco, sem
  histórico).
- B) Cada Arquivo é imutável e versionado; a correção cria um novo Arquivo
  relacionado ao anterior, com marcação de vigência.

**Riscos de cada opção:**
- A) Simples, mas destrói evidência de auditoria — incompatível com o
  princípio de Auditoria Obrigatória já registrado em
  `MAGNATA_OS_MANIFESTO.md` (princípio 12).
- B) Exige atributos adicionais por Arquivo (origem, hash, data, ator,
  Arquivo de origem quando derivado, situação de vigência), mas preserva
  histórico completo.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Um
Arquivo corrigido ou substitutivo não apaga silenciosamente o anterior. Cada
Arquivo possui versão ou ordem de criação dentro do Documento, permitindo
identificar: Arquivo original, Arquivo derivado, Arquivo corrigido, Arquivo
assinado, e Arquivo vigente (o que está em uso corrente). Cada Arquivo
registra, conceitualmente: origem, hash, data de criação, sistema ou ator
responsável, Arquivo de origem (quando derivado), e situação de vigência. A
política de retenção pode variar conforme o tipo documental, mas o histórico
relevante para auditoria não deve ser apagado sem regra formal.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Arquivo —
precisa ganhar atributos conceituais de versão, vigência, origem e relação
Arquivo→Arquivo de origem quando derivado, §5 e §8), `MAGNATA_OS_ARQUITETURA.md`
(contratos de dados, §4).

---

## DEC-ENT-018 — Destinatário e endereço utilizado

**Pergunta:** o que é, de fato, um Destinatário de um Envio — a pessoa/
organização/função autorizada a receber, ou apenas o e-mail/telefone usado
naquele momento? O que acontece quando o cadastro (e-mail, telefone) muda
depois que um Envio já foi feito?

**Por que essa decisão importa:** hoje `Envios de Documentos.Destinatário`
é texto livre (WhatsApp ou e-mail — `MAGNATA_OS_ENTIDADES.md`, entidade
Distribuição/Envio) — não há separação entre "quem" recebe e "qual endereço"
foi usado. Se o cadastro de telefone/e-mail de alguém mudar depois, o
histórico de para onde um documento foi efetivamente enviado pode ficar
ambíguo ou ser sobrescrito silenciosamente.

**Exemplo real ou cenário:** um colaborador troca de número de WhatsApp;
meses depois, uma auditoria pergunta para qual número o holerite de Março
foi enviado — se o Envio não preservar o endereço usado naquele momento, a
resposta fica dependente do cadastro atual, que já mudou.

**Opções identificadas:**
- A) Manter Destinatário como texto livre no Envio, sem entidade própria
  (situação atual).
- B) Destinatário como conceito (pessoa/organização/função autorizada), com
  o Envio preservando separadamente o endereço efetivamente usado no
  momento do envio.

**Riscos de cada opção:**
- A) Mais simples, mas perde rastreabilidade histórica quando o cadastro
  muda — risco já real, dado o padrão de troca de número observado no
  projeto.
- B) Exige que o Envio grave o endereço como valor próprio (não uma
  referência que resolve para o cadastro atual), mas resolve o risco acima.

**Decisão registrada (não é mais preliminar):** aprovada a opção B.
Destinatário representa a pessoa, organização, função ou parte autorizada a
receber a comunicação — e-mail e telefone **não são** a identidade do
Destinatário, são só um dos endereços possíveis dele. O Envio deve registrar
o endereço efetivamente utilizado (e-mail, telefone, identificador de
portal, ou outro endereço de canal), preservado no histórico mesmo que o
cadastro do Destinatário seja alterado depois. Destinatários podem estar
relacionados a: Colaborador, Cliente, responsável do Cliente, síndico,
administradora, contador, Signatário, ou outro contato autorizado. A
definição técnica de uma entidade Pessoa ou Contato própria pode ocorrer em
etapa posterior — esta decisão fixa o conceito, não o schema.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio — `Destinatário` texto livre precisa virar referência a quem recebe +
campo próprio de endereço usado, imutável por Envio), `MAGNATA_OS_ARQUITETURA.md`
(contratos de dados, §4).

---

## DEC-ENT-019 — Canal e provedor técnico

**Pergunta:** "Canal" (WhatsApp, e-mail) e "provedor técnico" (Evolution
API, SMTP, Gmail) devem ser tratados como o mesmo conceito, ou como
conceitos separados?

**Por que essa decisão importa:** hoje o código mistura os dois — o campo
`Canal` (`F_ENVIO_CANAL`) guarda "E-mail/WhatsApp", mas trocar de provedor
técnico (ex.: trocar a instância da Evolution API, ou trocar de SMTP) não
deveria, em tese, mudar o que o negócio entende por canal. Sem separar os
dois, uma futura troca de fornecedor técnico arrisca exigir mudança de
vocabulário de negócio.

**Exemplo real ou cenário:** a Magnata troca o provedor de envio de WhatsApp
— o Canal continua sendo "WhatsApp" para o negócio, mas o provedor técnico
por trás mudou.

**Opções identificadas:**
- A) Não separar — Canal e provedor são a mesma coisa (situação atual
  implícita).
- B) Separar: Canal é conceito de negócio (`EMAIL`, `WHATSAPP`, `PORTAL`,
  `DOWNLOAD`, `OUTRO`); provedor é o mecanismo técnico por trás (Evolution
  API, SMTP, Gmail, Apps Script, automação de navegador).

**Riscos de cada opção:**
- A) Mais simples hoje, mas qualquer troca de fornecedor técnico vira,
  incorretamente, uma mudança de "canal" para quem lê relatórios.
- B) Exige um campo a mais no Envio (provedor, além de canal), mas isola o
  vocabulário de negócio de decisões de fornecedor.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Canal é
o meio de negócio pelo qual a comunicação é entregue — adotados
inicialmente os canais conceituais `EMAIL`, `WHATSAPP`, `PORTAL`,
`DOWNLOAD`, `OUTRO`. Evolution API, SMTP, Gmail, Apps Script e automação de
navegador são provedores ou mecanismos técnicos, não canais de negócio. Um
Envio deve registrar separadamente: canal, provedor técnico, e
identificador externo (quando existente). A troca de provedor não deve
alterar o significado funcional do canal.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio — separar `Canal` de provedor/mecanismo técnico), `MAGNATA_OS_ARQUITETURA.md`
(contratos de dados, §4).

---

## DEC-ENT-020 — Estados conceituais do Envio

**Pergunta:** que vocabulário de estados um Envio deve percorrer, dado que o
`Status` atual (`Preparando`, `Enviado`, `Erro`, e também `Concluído`/`Lido`
em alguns pontos do código) já mistura processamento técnico com evidência
de entrega (ver DEC-ENT-009)?

**Por que essa decisão importa:** sem um vocabulário conceitual único e mais
granular, cada canal ou fluxo de disparo tende a inventar seu próprio
sub-vocabulário de status — como já ocorre hoje entre Processar Arquivos,
Envios de Documentos e Assinaturas (achados críticos já registrados em
`MAGNATA_OS_ENTIDADES.md`, §10).

**Exemplo real ou cenário:** hoje, um Envio cujo disparo foi aceito pelo
provedor mas nunca confirmado como entregue ao dispositivo do destinatário
aparece como `Enviado` — sem diferenciar "o provedor aceitou" de "o
dispositivo recebeu".

**Opções identificadas:**
- A) Manter o vocabulário atual, por canal, sem unificação.
- B) Adotar um vocabulário conceitual único, mapeado aos níveis de evidência
  da DEC-ENT-009, reconhecendo que nem todo canal percorre todos os estados.

**Riscos de cada opção:**
- A) Mais simples de não mexer agora, mas perpetua a fragmentação de
  vocabulário já identificada como achado crítico.
- B) Exige disciplina para não avançar um Envio para um estado sem a
  evidência correspondente — mas alinha todos os canais a um vocabulário
  comum.

**Decisão registrada (não é mais preliminar):** aprovada a opção B, como
vocabulário **conceitual**, não como schema final. Estados aprovados
inicialmente: `PLANEJADO`, `EM_FILA`, `EM_PROCESSAMENTO`,
`ACEITO_PELO_PROVEDOR`, `ENVIADO`, `ENTREGUE`, `LIDO`, `CONFIRMADO`,
`FALHA_TEMPORARIA`, `FALHA_DEFINITIVA`, `CANCELADO`. Esses nomes ainda não
são nomes finais de campos ou valores do Airtable — a máquina de estados
formal será criada em documento próprio. Um Envio não deve avançar para um
estado cuja evidência não exista (ver DEC-ENT-009). Nem todos os canais
percorrerão todos os estados (ex.: `DOWNLOAD` pode não ter `ENTREGUE`
distinto de `ACEITO_PELO_PROVEDOR`). Estados legados (`Preparando`,
`Enviado`, `Concluído`, `Lido`, `Erro`, e demais variações já encontradas)
serão mapeados para este vocabulário futuramente, não substituídos agora.
`Concluído`, quando o vocabulário for adotado tecnicamente, deve significar
o atendimento da condição de conclusão da finalidade da Distribuição (ver
DEC-ENT-013), não apenas resposta positiva de uma API.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio — vocabulário de `Status` a revisar à luz deste vocabulário
conceitual), `MAGNATA_OS_ARQUITETURA.md` (máquina de estados, §5 — precisa
reconciliar os estados legados já achados, incluindo `Finalizado`/`Pronto`
pendente de verificação em DEC-ENT-012).

---

## DEC-ENT-021 — Auditoria do Envio

**Pergunta:** o que, no mínimo, um registro de Envio precisa preservar para
que uma auditoria futura consiga reconstruir o que aconteceu, sem depender
de log de aplicação?

**Por que essa decisão importa:** liga-se diretamente ao achado de que hoje
a auditoria vive em `logger.*` disperso pelo código, não em registro
persistente (`MAGNATA_OS_ENTIDADES.md`, §9 e §10, achado #9) — e ao
princípio 12 do Manifesto (Auditoria Obrigatória).

**Exemplo real ou cenário:** uma disputa sobre se e quando um documento foi
entregue exige reconstruir, meses depois, toda a linha do tempo de um Envio
específico — hoje isso depende de vasculhar logs do Render, não de consultar
um registro.

**Opções identificadas:** não aplicável — este item registra o conjunto
mínimo de atributos conceituais a preservar, não uma escolha entre
alternativas excludentes.

**Riscos de não preservar isso:** impossibilidade de reconstruir, após o
fato, o histórico de um Envio para fins de auditoria, compliance ou disputa
trabalhista.

**Decisão registrada (não é mais preliminar):** aprovado que cada Envio deve
preservar, conceitualmente: Distribuição de origem; destinatário; endereço
usado; canal; provedor; Documentos; Arquivos; data da solicitação; data de
entrada na fila; datas das Tentativas; estado atual; resultado;
identificador externo; Envio anterior (em caso de reenvio); motivo do
reenvio; evidências recebidas; erros; ator ou sistema solicitante; e
identificador de correlação.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Distribuição/
Envio — lista de atributos mínimos precisa ser expandida conforme esta
decisão), `MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-022 — Aplicabilidade da Assinatura: quando uma Solicitação de Assinatura é exigida

**Pergunta:** todo Documento distribuído precisa, em algum momento, de uma
Solicitação de Assinatura? E quando um Documento é assinado, isso deveria
refletir no estado do próprio Documento (como ocorre hoje) ou permanecer
como um processo à parte?

**Por que essa decisão importa:** liga-se diretamente ao achado crítico #1
de `MAGNATA_OS_ENTIDADES.md` (§3, §10) — hoje o código atualiza o `Status`
de **Processar Arquivos** para `'Assinado'` ao concluir uma assinatura
(`app.py:9896`), misturando o ciclo de vida do Documento com o da
Assinatura. Sem uma regra explícita de "quando a assinatura se aplica", essa
mistura tende a se repetir em qualquer novo fluxo que envolva assinatura.
Também se relaciona a DEC-ENT-013 (Distribuição × Envio) e DEC-ENT-014
(Solicitação de Assinatura × Assinatura), que ainda está `PENDENTE`.

**Exemplo real ou cenário:** um Extrato Mensal é distribuído por e-mail para
um Cliente só para prestação de contas — não há razão de negócio para exigir
assinatura. Já um Contrato de Experiência, distribuído a um Colaborador,
exige assinatura para ter validade. Hoje nada no sistema distingue
formalmente esses dois casos antes de decidir se cria uma Solicitação de
Assinatura.

**Opções identificadas:**
- A) Tratar assinatura como parte implícita do fluxo de distribuição de
  certos tipos de documento, decidida dentro da própria rota de envio
  (situação atual, de fato).
- B) Tratar Distribuição e Solicitação de Assinatura como processos
  independentes, em que a segunda só é criada quando uma regra explícita
  (Tipo Documental, finalidade, regra de negócio, obrigação contratual ou
  decisão operacional autorizada) a exigir.

**Riscos de cada opção:**
- A) Mais simples de codar caso a caso, mas é exatamente o que já produziu o
  achado crítico (Status de Documento contaminado com estado de Assinatura)
  — cada nova rota de envio que "também" cuida de assinatura tende a
  reproduzir o mesmo acoplamento.
- B) Exige que cada Tipo Documental/finalidade declare explicitamente se
  exige assinatura, mas elimina o acoplamento e permite que Distribuição e
  Assinatura evoluam (e concluam) de forma independente.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Nem todo
Documento enviado ou distribuído necessita de assinatura digital.
Distribuição e Solicitação de Assinatura são processos independentes. Um
Documento pode: ser armazenado sem distribuição; ser distribuído apenas para
informação ou prestação de contas; ser distribuído com exigência de
confirmação de entrega ou leitura; ou ser submetido a uma Solicitação de
Assinatura — essas opções não são mutuamente exclusivas ao longo do tempo,
mas nenhuma delas decorre automaticamente de outra.

A criação de uma Solicitação de Assinatura só ocorre quando houver exigência
definida pelo Tipo Documental, pela finalidade do processo, por regra de
negócio, por obrigação contratual, ou por decisão operacional autorizada. O
simples fato de um Documento ser enviado não cria automaticamente uma
Solicitação de Assinatura.

Confirmação de entrega, confirmação de leitura, ciência e Assinatura são
evidências diferentes (ver também os níveis de evidência da DEC-ENT-009). Um
Documento entregue ou lido não deve ser marcado como assinado sem uma
Assinatura individual válida e sua respectiva evidência — isto formaliza,
como regra de negócio, a correção do achado crítico #1: o estado de
"assinado" pertence à Assinatura, nunca é inferido a partir de entrega ou
leitura, nem escrito como estado do Documento.

A política de assinatura deve ser configurável por Tipo Documental e
finalidade, sem ficar fixa dentro das rotas de envio. A ausência de
necessidade de assinatura não representa pendência ou falha do Documento — é
um caminho normal e completo. A Distribuição pode ser concluída
independentemente de assinatura quando sua finalidade exigir apenas entrega,
leitura ou disponibilização (ver DEC-ENT-013, condições de conclusão da
Distribuição). Quando a finalidade exigir assinatura, a conclusão da
Distribuição e a conclusão da Solicitação de Assinatura permanecem
relacionadas — mas com estados e evidências próprios, nunca um campo de
estado compartilhado entre as duas.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (achado crítico #1, §3 e
§10 — a mistura de `Status` de Processar Arquivos com `'Assinado'` passa a
ter regra de negócio formal que a proíbe; entidade Solicitação de
Assinatura/Assinatura precisa ganhar o atributo de "gatilho de exigência" por
Tipo Documental/finalidade), `MAGNATA_OS_ARQUITETURA.md` (máquina de
estados, §5 — `Assinado` deixa de ser um estado válido de Documento; módulo
Assinatura, §2).

---

## DEC-ENT-023 — Signatário: papel distinto de Colaborador/Destinatário/Usuário

**Pergunta:** quem, tecnicamente, é a "pessoa" dentro de uma Solicitação de
Assinatura — é sempre um Colaborador, ou pode ser qualquer parte autorizada
(um síndico, um fiador, uma testemunha) sem vínculo formal com a Magnata?

**Por que essa decisão importa:** o modelo atual assume que quem assina é
sempre um Funcionário (`F_ASS_FUNCIONARIO`, link direto a Funcionários).
Isso não comporta signatários que não são colaboradores (ex.: um
representante do Cliente assinando um termo, ou uma testemunha).

**Exemplo real ou cenário:** um termo de responsabilidade de equipamento
assinado pelo colaborador **e** por um gestor do posto como testemunha — o
gestor pode não ter registro de Colaborador ativo (pode ser terceirizado, ou
representante do Cliente).

**Opções identificadas:**
- A) Manter Signatário = sempre Colaborador (situação atual, via
  `F_ASS_FUNCIONARIO`).
- B) Signatário como papel próprio dentro da Solicitação, relacionável a
  Colaborador, representante de Cliente, responsável legal, testemunha,
  gestor, ou outro participante autorizado.

**Riscos de cada opção:**
- A) Mais simples, mas impede assinatura de qualquer parte que não seja
  Colaborador — bloqueia casos reais de testemunha/representante do
  Cliente.
- B) Exige desacoplar Signatário de Colaborador, mas cobre todos os casos
  reais de negócio sem forçar um cadastro de Colaborador fictício.

**Decisão registrada (não é mais preliminar):** aprovada a opção B.
Signatário representa o papel de uma pessoa ou parte dentro de uma
Solicitação específica — não é sinônimo automático de Colaborador,
Destinatário, Usuário, Contato, ou responsável do Cliente. Um Signatário
pode estar relacionado a: Colaborador, representante de Cliente, responsável
legal, testemunha, gestor, ou outro participante autorizado. O Signatário
deve preservar conceitualmente: pessoa ou parte relacionada; nome utilizado
no momento da Solicitação; CPF ou outro identificador juridicamente
necessário, quando aplicável; contato utilizado; papel na assinatura; ordem
(relevante sob política `SEQUENCIAL`, DEC-ENT-008); autenticação exigida; e
estado individual (ver DEC-ENT-028). Alterações futuras no cadastro da
pessoa (ex.: Colaborador corrige nome ou CPF) não apagam os dados utilizados
na assinatura — o Signatário preserva o retrato daquele momento.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (nova entidade
Signatário, distinta de Colaborador — `F_ASS_FUNCIONARIO` deixa de ser a
única forma de vincular quem assina), `MAGNATA_OS_ARQUITETURA.md` (contratos
de dados, §4).

---

## DEC-ENT-024 — Link de Assinatura: credencial temporária, não a Solicitação

**Pergunta:** o link de acesso usado para assinar (`/assinatura/<hash_token>`)
é a própria Solicitação, ou é um meio de acesso separado dela, com ciclo de
vida próprio (validade, expiração, revogação)?

**Por que essa decisão importa:** hoje `Hash Token` (`F_ASS_HASH`) é só um
campo dentro do registro de Assinatura, sem conceito próprio de
expiração/revogação separado do restante da Solicitação. Sem isso, gerar um
novo link (ex.: reenviar por perda do original) não tem regra clara sobre o
que acontece com o link anterior.

**Exemplo real ou cenário:** um Signatário perde a mensagem de WhatsApp com o
link; um novo link é gerado — o link antigo deveria parar de funcionar
imediatamente, mas isso precisa ser regra explícita, não acidente de
implementação.

**Opções identificadas:**
- A) Link como só um campo (hash) dentro da Assinatura/Solicitação, sem
  ciclo de vida próprio (situação atual).
- B) Link de Assinatura como conceito próprio — credencial temporária, com
  validade, expiração, revogação e histórico.

**Riscos de cada opção:**
- A) Mais simples, mas sem regra clara de revogação/expiração ao gerar novo
  link — risco de dois links simultâneos válidos sem controle.
- B) Exige atributos adicionais, mas permite auditar quantos links foram
  gerados, qual está vigente, e por que um foi revogado.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Link de
Assinatura é uma credencial ou meio temporário de acesso — não é a
Solicitação, e não é a Assinatura. O Link se relaciona à Solicitação e,
quando aplicável, a um Signatário específico. Deve preservar
conceitualmente: token seguro; data de criação; validade; data de
expiração; situação; regras de uso; limite de acessos, quando aplicável;
data de revogação; e motivo da revogação. Tokens completos não devem
aparecer em logs comuns. Link expirado ou revogado não permite nova
assinatura. A geração de um novo Link não apaga o histórico do anterior. A
substituição de Link não cria, por si só, uma nova Solicitação.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (nova entidade Link de
Assinatura, hoje só o campo `Hash Token` dentro de Assinaturas),
`MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-025 — Evidência da Assinatura: o que preservar, e limites de suficiência jurídica

**Pergunta:** o que, no mínimo, uma Assinatura precisa preservar como
evidência — e essa evidência, por si só, comprova validade jurídica?

**Por que essa decisão importa:** hoje a Assinatura já preserva IP, User
Agent, CPF informado e timestamp (achado positivo já registrado em
`MAGNATA_OS_ENTIDADES.md`), mas não há definição explícita de quais desses
elementos bastam para qual finalidade, nem limite claro sobre o que o
sistema pode ou não declarar sobre validade jurídica.

**Exemplo real ou cenário:** uma disputa questiona se um Contrato de
Experiência foi realmente assinado pelo colaborador — a resposta depende de
quais evidências foram de fato preservadas (hash do arquivo antes/depois,
IP, sessão) e de o sistema não ter alegado uma validade jurídica que não
pode sustentar sozinho.

**Opções identificadas:** não aplicável — este item registra o conjunto
mínimo de evidências a preservar e os limites de suficiência, não uma
escolha entre alternativas excludentes.

**Riscos de não preservar isso:** evidência insuficiente para sustentar a
validade de uma assinatura quando questionada; ou, no sentido oposto, o
sistema declarando validade jurídica sem fundamento técnico para sustentá-la.

**Decisão registrada (não é mais preliminar):** aprovado que a Evidência da
Assinatura preserve, conforme o método utilizado: Solicitação; Assinatura;
Signatário; Documento; Arquivo apresentado; Arquivo resultante; data e hora;
método de autenticação; identificador da sessão; endereço IP, quando
juridicamente permitido e necessário; informações do dispositivo ou agente,
quando aplicável; hash do Arquivo antes da assinatura; hash do Arquivo
resultante; aceite registrado; versão dos termos apresentados; identificador
de correlação; resultado; falhas; e eventos relevantes.

Limites explícitos: exibição de tela de sucesso não é evidência suficiente
por si só. Imagem isolada de assinatura não comprova automaticamente
autoria, integridade ou validade. A suficiência jurídica depende do tipo
documental, método de autenticação, finalidade e requisitos aplicáveis — o
Magnata OS registra fatos e evidências, sem declarar validade jurídica
absoluta sem fundamento específico. A Evidência pode ser entidade própria ou
registro imutável vinculado à Assinatura — a decisão técnica definitiva
ocorrerá posteriormente, na revisão de Entidades e Eventos.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Assinatura —
lista de evidências mínimas a expandir conforme esta decisão),
`MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-026 — Arquivo Assinado: novo Arquivo, nunca sobrescrita

**Pergunta:** quando um Documento é assinado, o PDF resultante substitui o
Arquivo original, ou vira um novo Arquivo relacionado a ele?

**Por que essa decisão importa:** liga-se diretamente a DEC-ENT-015
(Documento × Arquivo) e DEC-ENT-017 (Versões de Arquivo) — sem regra
explícita para o caso específico de assinatura, o Arquivo assinado poderia
sobrescrever o apresentado, perdendo a evidência de qual era o conteúdo
original antes de assinar.

**Exemplo real ou cenário:** um Kit de Admissão consolidado é apresentado
para assinatura; depois de assinado, existe um PDF com a assinatura
incorporada — é preciso saber que existiu uma versão sem assinatura, qual
foi mostrada ao Signatário, e qual é a vigente após a assinatura.

**Opções identificadas:**
- A) Sobrescrever o Arquivo apresentado com o Arquivo assinado (risco,
  perda de evidência do "antes").
- B) Arquivo assinado como novo Arquivo, referenciando o Arquivo de origem,
  seguindo a política de versões já aprovada (DEC-ENT-017).

**Riscos de cada opção:**
- A) Simples, mas destrói a evidência de qual conteúdo foi efetivamente
  apresentado ao Signatário antes da assinatura.
- B) Consistente com DEC-ENT-017, mas exige que o Arquivo assinado carregue
  atributos próprios de origem e vigência.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. O
Arquivo assinado é preservado como novo Arquivo — o Arquivo apresentado para
assinatura não é sobrescrito. O Arquivo assinado referencia o Arquivo de
origem, e preserva conceitualmente: Solicitação de origem; Assinaturas
incorporadas; hash; versão; data de geração; ator ou mecanismo gerador; e
situação de vigência (consistente com DEC-ENT-017). Quando a assinatura
altera somente a formalização do mesmo conteúdo, o Arquivo assinado continua
relacionado ao **mesmo** Documento (consistente com DEC-ENT-015). Quando
houver alteração material do conteúdo, deve ser avaliada a criação de novo
Documento ou versão documental formal. A existência de um Arquivo assinado
não apaga nem invalida automaticamente o Arquivo apresentado.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Arquivo —
Arquivo assinado como caso concreto da política de versões já aprovada),
`MAGNATA_OS_ARQUITETURA.md` (contratos de dados, §4).

---

## DEC-ENT-027 — Estados conceituais da Solicitação de Assinatura

**Pergunta:** que vocabulário de estados uma Solicitação de Assinatura deve
percorrer, agora que ela é uma entidade separada da Assinatura individual
(DEC-ENT-014) e pode ter múltiplos Signatários (DEC-ENT-008)?

**Por que essa decisão importa:** o vocabulário atual (`Pendente`,
`Assinado`, `Expirado`) foi pensado para 1 Signatário só — não distingue
"enviado mas ninguém assinou ainda" de "alguns assinaram, outros não", nem
separa isso do estado de cada Assinatura individual.

**Exemplo real ou cenário:** uma Solicitação com política `TODOS` e 3
Signatários, onde 1 já assinou — a Solicitação não está `Assinada` (só um
assinou), nem `Pendente` no sentido de "nada aconteceu ainda".

**Opções identificadas:**
- A) Manter vocabulário atual de 3 estados, sem distinguir parcialidade.
- B) Adotar vocabulário mais granular, cobrindo rascunho, envio, assinatura
  parcial e conclusão conforme a política.

**Riscos de cada opção:**
- A) Mais simples, mas não comporta múltiplos Signatários com clareza.
- B) Mais estados para gerenciar, mas reflete corretamente o que já foi
  aprovado em DEC-ENT-008.

**Decisão registrada (não é mais preliminar):** aprovada a opção B, como
vocabulário **conceitual**. Estados aprovados inicialmente: `RASCUNHO`,
`PREPARADA`, `ENVIADA`, `EM_ASSINATURA`, `PARCIALMENTE_ASSINADA`,
`CONCLUIDA`, `RECUSADA`, `EXPIRADA`, `CANCELADA`, `ERRO`. São estados
conceituais, não nomes finais de campos — a máquina de estados formal será
criada posteriormente. `ENVIADA` significa que o acesso ou convite foi
disponibilizado, não que houve assinatura. `PARCIALMENTE_ASSINADA` significa
que existe ao menos uma Assinatura válida, mas a política de conclusão
(DEC-ENT-008) ainda não foi satisfeita. `CONCLUIDA` significa que a política
de conclusão foi satisfeita — não apenas que uma Assinatura existe. A
existência de uma Assinatura individual não implica conclusão quando houver
outros Signatários obrigatórios. Estados legados (`Pendente`, `Assinado`,
`Expirado`) serão mapeados para este vocabulário futuramente, não
substituídos agora.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Solicitação de
Assinatura — vocabulário de `Status` a revisar), `MAGNATA_OS_ARQUITETURA.md`
(máquina de estados, §5).

---

## DEC-ENT-028 — Estados conceituais da Assinatura individual

**Pergunta:** que vocabulário de estados uma Assinatura individual (de um
Signatário específico) deve percorrer, separado do estado da Solicitação
como um todo?

**Por que essa decisão importa:** sem um ciclo de estados próprio por
Signatário, não é possível saber, numa Solicitação com múltiplos
Signatários, quem já acessou o link, quem assinou, e quem recusou —
distinção necessária para a política de conclusão (DEC-ENT-008) funcionar.

**Exemplo real ou cenário:** de 3 Signatários numa Solicitação, 1 assinou, 1
acessou o link mas não assinou ainda, e 1 nem acessou — cada um precisa de
um estado individual rastreável.

**Opções identificadas:**
- A) Não ter estado individual — só o estado agregado da Solicitação.
- B) Cada Signatário tem seu próprio ciclo de estados.

**Riscos de cada opção:**
- A) Mais simples, mas impossibilita saber individualmente quem já agiu e
  quem falta, especialmente sob política `SEQUENCIAL` ou
  `QUANTIDADE_MINIMA`.
- B) Mais granular, mas exige rastrear estado por Signatário, não só por
  Solicitação.

**Decisão registrada (não é mais preliminar):** aprovada a opção B. Cada
Signatário possui ciclo individual, com estados conceituais: `PENDENTE`,
`ACESSADA`, `ASSINADA`, `RECUSADA`, `EXPIRADA`, `INVALIDADA`. `ACESSADA` não
significa `ASSINADA`. `ASSINADA` exige evidência compatível (ver
DEC-ENT-025). `RECUSADA` preserva o ato e o momento da recusa. `INVALIDADA`
não apaga o histórico anterior. A Solicitação pode continuar aberta após uma
Assinatura individual concluída (ex.: aguardando os demais Signatários sob
política `TODOS`). O estado individual não deve ser reutilizado como estado
genérico do Documento — reforça a regra já aprovada em DEC-ENT-022 contra o
achado crítico de `Status` de Documento contaminado com estado de
Assinatura.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Assinatura —
vocabulário de estado individual por Signatário), `MAGNATA_OS_ARQUITETURA.md`
(máquina de estados, §5).

---

## DEC-ENT-029 — Idempotência da criação da Solicitação de Assinatura

**Pergunta:** um retry técnico (timeout, repetição automática de webhook,
nova chamada por falha de rede) na criação de uma Solicitação de Assinatura
deve criar uma nova Solicitação a cada vez, ou reconhecer que é a mesma
operação repetida?

**Por que essa decisão importa:** o sistema já tem uma Chave de Idempotência
SHA-256 para Assinaturas (`F_ASS_CHAVE_IDEMPOTENCIA`), mas sem regra
explícita de negócio, corre-se o risco de confundir essa chave técnica com o
identificador canônico da Solicitação, ou de tratar um pedido
deliberadamente novo (ex.: reenviar para assinatura depois de uma correção)
como se fosse duplicidade técnica.

**Exemplo real ou cenário:** uma chamada de API para gerar Solicitação de
Assinatura sofre timeout e é repetida automaticamente pelo Celery — isso não
deve gerar duas Solicitações para o mesmo Documento; mas se um humano decide
deliberadamente gerar uma nova Solicitação para uma versão corrigida do
Documento, isso é uma nova Solicitação legítima, não duplicidade.

**Opções identificadas:** não aplicável — este item registra a regra de
idempotência a aplicar, não uma escolha entre alternativas excludentes.

**Riscos de não ter essa regra:** duplicidade de Solicitações por retry
técnico (gerando confusão para o Signatário, que recebe múltiplos links); ou
o oposto, bloqueio indevido de uma nova Solicitação legítima por ela
coincidir tecnicamente com uma chave de idempotência antiga.

**Decisão registrada (não é mais preliminar):** aprovado que a criação da
Solicitação seja idempotente quando houver repetição do mesmo comando
técnico. Retry, timeout ou repetição automática não deve criar Solicitações
duplicadas. A chave de idempotência pertence à operação de criação — ela não
substitui o identificador canônico da Solicitação. Uma nova Solicitação
deliberada para o mesmo Documento possui nova identidade; quando aplicável,
a nova Solicitação referencia a anterior e registra o motivo (consistente
com o padrão já aprovado para Reenvio, DEC-ENT-007). PDF SHA-256, Request
ID, chave de idempotência e identificadores externos são conceitos
diferentes — podem colaborar na prevenção de duplicidade, mas não devem ser
usados indistintamente uns pelos outros. A definição final das chaves
ocorrerá nos contratos de dados.

**Decisão da Magnata:** `APROVADA`
**Responsável pela decisão:** `Direção da Magnata`
**Data da decisão:** `2026-07-22`
**Documentos impactados:** `MAGNATA_OS_ENTIDADES.md` (entidade Solicitação de
Assinatura — distinção entre chave de idempotência e identificador
canônico), `MAGNATA_OS_ARQUITETURA.md` (princípio 11 do Manifesto,
Idempotência — referência; contratos de dados, §4).

---

## Confirmação de escopo

Nenhum código, tabela do Airtable, configuração, rota ou automação foi
alterado para produzir este documento. As decisões DEC-ENT-001, DEC-ENT-002,
DEC-ENT-003, DEC-ENT-004, DEC-ENT-005, DEC-ENT-006, DEC-ENT-007, DEC-ENT-008,
DEC-ENT-009, DEC-ENT-013, DEC-ENT-014, DEC-ENT-015, DEC-ENT-016, DEC-ENT-017,
DEC-ENT-018, DEC-ENT-019, DEC-ENT-020, DEC-ENT-021, DEC-ENT-022, DEC-ENT-023,
DEC-ENT-024, DEC-ENT-025, DEC-ENT-026, DEC-ENT-027, DEC-ENT-028, DEC-ENT-029,
o "Modelo Conceitual Aprovado", o "Modelo Conceitual Documental", o "Modelo
Conceitual de Distribuição e Entrega" e o "Modelo Conceitual de Assinatura"
estão marcados `APROVADA` pela Direção da Magnata em 2026-07-22. As demais
(DEC-ENT-010, DEC-ENT-011, DEC-ENT-012) permanecem `PENDENTE` —
recomendações preliminares ali continuam sendo sugestões, não decisões, até
resposta explícita dos responsáveis da Magnata. `DEC-ENT-022` foi preservada
sem alteração de conteúdo nesta rodada — só passou a ser referenciada, com
identidade e texto intactos, pelas novas decisões 014, 023 a 029 e pelo novo
"Modelo Conceitual de Assinatura".
