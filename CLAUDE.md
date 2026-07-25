# Magnata OS — Constituição de Engenharia

Este arquivo vale para toda sessão, todo skill e todo subagente que
trabalhar neste repositório. Ele não substitui a documentação
fundacional — resume e aponta para ela. Em caso de dúvida de detalhe,
o documento fundacional citado prevalece sobre a frase resumida aqui.

## 1. Missão

- Construir o Magnata OS como plataforma operacional modular da
  Magnata — não "a automação de holerite": holerite, ponto, admissão,
  assinatura e distribuição são módulos dela, não o produto inteiro
  (`MAGNATA_OS_MANIFESTO.md`).
- Migração incremental pelo *strangler pattern* — módulos novos assumem
  responsabilidade pedaço por pedaço; não há reescrita de uma vez.
- Preservar produção e legado até que cada substituição esteja
  validada. Um processo feio, duplicado ou fora do padrão, mas que já
  funciona em produção, nunca é interrompido só por estar errado — é
  migrado.

## 2. Fontes oficiais

- **Índice:** [`docs/magnata-os/README.md`](docs/magnata-os/README.md)
  — aponta a fonte principal de cada assunto, a ordem de leitura e o
  mapa de dependência entre os documentos fundacionais.
- **Precedência em caso de conflito** (do índice, não repetida aqui em
  detalhe):
  1. decisão arquitetural aprovada **e implementada** (código já
     mesclado em `main`);
  2. contratos e estados oficiais (`MAGNATA_OS_CONTRATOS.md`,
     `MAGNATA_OS_ESTADOS.md`);
  3. documentação do módulo (`MAGNATA_OS_MODULO_01_*`,
     `MAGNATA_OS_DOCUMENTAL_MODULO01*`);
  4. roadmap (ainda não existe — ver pendências do Powerpack);
  5. notas e documentos históricos.
  `MAGNATA_OS_MANIFESTO.md` fica fora dessa escala: é autoridade sobre
  princípio, e nenhum item de 1 a 5 pode contrariá-lo.
- **Nenhuma decisão arquitetural é tomada em silêncio.** Se o pedido do
  usuário, o código existente e a documentação divergirem, isso é
  **registrado explicitamente** (num documento de fase, num relatório
  de etapa, ou apontado na resposta ao usuário) — nunca resolvido por
  escolha unilateral não declarada.
- Todo conflito ou decisão nova relevante precisa ficar registrado por
  escrito em algum artefato do repositório (documento de fase, ADR,
  relatório de etapa) — não só na conversa.

## 3. Arquitetura

Visão de orientação rápida, em 6 estágios — mapeamento simplificado dos
**9 módulos oficiais** já documentados em `MAGNATA_OS_ARQUITETURA.md`
§2 (Ingestão, Classificação, Cadastro, Ponto/Secullum, Folha/Documentos,
Distribuição, Assinatura, Auditoria/Observabilidade, Plataforma). Em
caso de dúvida sobre fronteira de responsabilidade de um módulo
específico, `MAGNATA_OS_ARQUITETURA.md` §2 é a fonte detalhada, não
esta lista:

**Entrada → Inteligência → Transformação → Negócio → Entrega → Auditoria**

- Módulos desacoplados — um módulo não importa o interno de outro;
  comunica por contrato.
- **Contratos antes de integrações.** Nenhuma integração nova sem o
  contrato de dados (`MAGNATA_OS_CONTRATOS.md`) já definido para o que
  ela troca.
- **Adapters para todo serviço externo.** Um módulo novo nunca importa
  driver de fornecedor diretamente (`psycopg2`, `boto3`, cliente do
  Airtable) — só a interface, injetada.
- **Domínio sem dependência de Flask, Airtable, Render, Gmail ou
  qualquer fornecedor.** Já é assim em `magnata_os/` (verificado: zero
  import desses nomes no domínio) — todo módulo novo mantém essa
  garantia.
- **PostgreSQL como metadados oficiais futuros; armazenamento
  compatível com S3 para binários futuros.** Já é a direção adotada
  pelos adapters do Módulo 01 (`magnata_os/documental/modulo01/adapters/`).
  **Nota de rastreabilidade:** essa direção ainda não tem uma entrada
  de changelog correspondente em `MAGNATA_OS_ARQUITETURA.md` — pendência
  registrada, não uma contradição a esconder.
- **Airtable é legado/adapter temporário** para o que ainda não migrou
  — continua sendo o sistema de registro do que não foi absorvido por
  um módulo novo (`MAGNATA_OS_ARQUITETURA.md` §4).

## 4. Regras de domínio

- Manter sempre **separados**, nunca fundidos num único campo/estado:
  `etapa_atual`; `situacao`; `motivo_bloqueio`; `proxima_acao` (ver
  `magnata_os/documental/modulo01/dominio_esteira.py` como referência
  já implementada desse princípio).
- **Histórico é imutável e append-only.** Nunca editar nem apagar um
  evento já registrado.
- **Idempotência é obrigatória** em toda operação de entrada — mesmo
  conteúdo processado de novo nunca duplica o resultado.
- **Falha nunca é silenciosa.** Toda falha é propagada, registrada ou
  ambos — nunca mascarada como sucesso.
- **Automação por confiança; ação humana para exceção.** O caminho
  automático é o padrão quando a confiança é alta; o que foge disso vira
  pendência para uma pessoa, nunca uma tentativa de adivinhação
  silenciosa.
- **Arquivo original é imutável.** Uma vez armazenado por hash, o
  conteúdo nunca é sobrescrito — divergência de conteúdo para o mesmo
  hash é erro a relatar, nunca a sobrescrever.

## 5. Nomenclatura pendente

- A documentação fundacional (`MAGNATA_OS_ESTADOS.md`,
  `MAGNATA_OS_MODULO_01_INGESTAO.md`,
  `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`) usa **"Item de
  Ingestão"** como nome da entidade central.
- O código já implementado (`magnata_os/documental/modulo01/dominio.py`)
  usa **"Documento"**.
- **Não renomear** entidade, tabela, classe, contrato ou migration por
  conta própria para "resolver" isso — só com ADR/decisão aprovada
  registrada.
- **Em código novo dentro do módulo já implementado, seguir a
  nomenclatura vigente do código: `Documento`.** Não reintroduzir "Item
  de Ingestão" em código novo só porque é o nome nos documentos.
- O conflito continua registrado na documentação
  (`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` §4.1) até decisão
  formal — não apagar nem "corrigir" essa nota silenciosamente.

## 6. Segurança

- Nunca revelar ou commitar segredo (token, senha, chave, cookie,
  variável de ambiente com valor real).
- Não imprimir token em nenhuma saída, nem parcialmente.
- Não acessar produção sem autorização explícita e específica para
  aquela ação.
- Não alterar Airtable real, não enviar e-mail nem WhatsApp reais, não
  executar deploy, não alterar credencial — em nenhuma dessas cinco
  coisas, mesmo que peça explicitamente para "só testar".
- Usar sempre o menor privilégio necessário para a tarefa (já é
  princípio do Manifesto, §"Segurança e credenciais").
- Dado pessoal (CPF, nome de funcionário real, holerite real) segue a
  LGPD: nunca em teste, nunca em commit, nunca em log, nunca em
  documento de exemplo.

## 7. Arquivos protegidos

- `app.py` é **legado protegido** — alteração só com autorização
  explícita do usuário e numa branch própria para isso, nunca
  misturada com trabalho de módulo novo.
- Não misturar refatoração de legado com construção de módulo novo no
  mesmo commit/branch.
- Não editar uma migration já aplicada — nova mudança é sempre uma
  migration nova.
- Não alterar assets oficiais da marca (`frontend/assets/brand/`) sem
  autorização explícita — nem redesenhar, nem recomprimir, nem trocar
  formato.
- Não commitar arquivo de scratch/investigação (`_*.json`, `_*.txt`
  soltos na raiz, e semelhantes) junto com entrega de código.

## 8. Processo obrigatório

**Antes de implementar:**
- confirmar em qual branch está;
- confirmar que a base local está atualizada com a remota;
- rodar `git status` e entender o que já está pendente antes de tocar
  em qualquer arquivo;
- identificar o escopo exato do pedido — nem mais, nem menos;
- ler o(s) documento(s) fundacional(is) relevante(s) para o que vai ser
  feito.

**Durante:**
- mudanças pequenas e isoladas — um objetivo por vez;
- contrato e teste andam junto com a implementação, não depois;
- nunca expandir escopo em silêncio — se aparecer algo a mais que vale
  a pena, é uma sugestão separada, não um extra incluído sem avisar;
- registrar decisão relevante tomada no caminho.

**Antes de concluir:**
- testes específicos da mudança;
- suíte geral;
- separar explicitamente falha pré-existente de regressão nova —
  nunca apresentar as duas juntas como se fossem a mesma coisa;
- `git diff --check`;
- busca por segredo no diff;
- confirmação de escopo (só o que foi pedido foi alterado);
- commit único e claro, só quando solicitado.

## 9. Git e PR

- Uma finalidade por branch.
- Não abrir PR sem pedido explícito.
- Não fazer merge.
- Não fazer deploy.
- Não apagar branch automaticamente.
- Nunca guardar token em arquivo temporário **dentro do repositório**
  (usar diretório de scratchpad fora do repo, sempre apagando o
  arquivo depois de usado).
- Não alterar `main` diretamente — toda mudança entra por branch.

## 10. Critérios de conclusão

Uma fase só é declarada pronta quando, **todos** ao mesmo tempo:
- o escopo pedido foi entregue;
- os testes específicos passam;
- nenhuma regressão nova foi introduzida;
- a documentação relevante foi atualizada;
- os riscos restantes foram declarados, não escondidos;
- os arquivos protegidos (§7) continuam intactos;
- nenhuma integração real foi acessada fora do que foi explicitamente
  autorizado para aquela tarefa.

Se qualquer um desses não for verdade, a resposta é "NÃO PRONTA" (ou
equivalente), nunca "pronta com ressalva" apresentada como sucesso.

## 11. Forma de trabalho

- Agir com objetividade — resposta direta, sem enrolar.
- Evitar auditoria repetida do que já foi checado nesta mesma sessão.
- Não testar possibilidade aleatória "para ver o que acontece" — 
  investigar a causa com evidência (log, código, teste) antes de agir.
- Ao final de uma tarefa: apresentar resultado, riscos remanescentes e
  próxima ação sugerida — nessa ordem, sem enterrar o risco no meio do
  texto.
- Nunca ocultar falha encontrada, mesmo que não tenha sido perguntada.
- Nunca afirmar sucesso sem ter testado.
