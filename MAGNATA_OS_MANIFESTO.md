# Magnata OS — Manifesto

**Status:** documento fundacional, em vigor a partir de 2026-07-22.
**Natureza:** permanente. Não é um plano de sprint, não é uma decisão de fase —
é a constituição do sistema. Planos de migração, decisões de fase e a
arquitetura técnica (`MAGNATA_OS_ARQUITETURA.md`) se ajustam ao longo do tempo;
este manifesto é o que não muda com cada feature.
**Autoridade:** qualquer código, endpoint, tabela, campo, automação de
navegador ou decisão futura que contrarie um princípio abaixo está errado por
definição, independente de estar "funcionando". Funcionar não é a mesma coisa
que estar certo.

---

## 0. Contexto que este manifesto assume como verdadeiro

Este documento não nasce de teoria. Nasce do estado real e medido do sistema
em 2026-07-22:

- `app.py` tem mais de 10.400 linhas, ~182 funções e 37 endpoints — um
  monólito que cresceu por adição incremental, não por design.
- A pilha atual é: Airtable (registro), Render (deploy), Celery + Redis
  (assíncrono), Google Apps Script (captura de e-mail), Evolution API
  (WhatsApp), e automações de navegador pontuais onde não há API.
- Já existem divergências de contrato conhecidas e **não resolvidas por este
  documento** — apenas nomeadas, para que parem de se multiplicar:
  - `Tipo` e `Tipo de Documento` competindo pelo mesmo conceito de categoria
    documental.
  - `Arquivos` e `Arquivos 2` — hoje uma é o anexo físico e a outra é o link
    de referência a essa tabela; o nome não deixa isso óbvio e já causou
    ambiguidade.
  - Estados de processo com significado sobreposto espalhados pelo sistema:
    `Enviar`, `Pendente`, `Processando`, `Concluído`, `Finalizado`, `Pronto`.
- Existem fluxos paralelos para processos que deveriam ser o mesmo processo
  (ex.: geração de fila e disparo repetidos quase-idênticos por canal).
- A migração é gradual, via *strangler pattern* — o legado continua rodando
  enquanto módulos novos assumem responsabilidade pedaço por pedaço. Não há
  reescrita de uma vez.
- Navegador é automação de último recurso, não de primeira escolha.
- O Magnata OS não é "a automação de holerite". É a plataforma de operação da
  empresa. Holerite, ponto, admissão, assinatura e distribuição são módulos
  dela — não o produto inteiro.

Nenhuma ação de código, schema ou infraestrutura foi tomada para produzir este
documento. Ele é declaração de princípio, não implementação.

---

## 1. Operação preservada

Nenhuma evolução do Magnata OS pode interromper, apagar ou comprometer um
processo que já está funcionando em produção. Isso vale mesmo quando o
processo em produção é feio, duplicado ou vai contra um princípio deste
manifesto — a correção migra o processo, não o interrompe. Um funcionário não
deixa de receber holerite porque o time decidiu que o endpoint que gera esse
holerite precisa ser reescrito.

Toda mudança que toque um fluxo em produção precisa responder, antes de
existir: *"se isso falhar às 2 da manhã, o que já estava funcionando ontem
continua funcionando hoje?"*. Se a resposta não for um "sim" claro, a mudança
não está pronta.

---

## 2. Domínio antes do código

Nenhuma funcionalidade é implementada sem que, antes, alguém tenha entendido e
registrado:

- o processo real da empresa (não a suposição sobre o processo);
- os responsáveis por ele;
- as entradas;
- as saídas;
- as regras que governam o caminho normal;
- as exceções que já se sabe que existem;
- as evidências necessárias para provar que o processo aconteceu.

Código que nasce antes dessa compreensão é código que resolve o problema
errado com precisão. O padrão já usado neste projeto — documento curto de
decisão antes de mexer em schema ou fluxo (como os já produzidos em fases
anteriores) — é a prática correta e continua obrigatório, não é burocracia
extra.

---

## 3. Contratos oficiais

Toda informação compartilhada entre módulos tem contrato explícito e
versionado — não um entendimento tácito de que "todo mundo sabe o que aquele
campo quer dizer".

Não é permitido que dois nomes representem o mesmo conceito sem que exista uma
decisão formal de qual é a fonte e qual é a compatibilidade temporária. O caso
de `Tipo` vs. `Tipo de Documento` é exatamente o que este princípio proíbe daqui
para frente: um dos dois é a fonte oficial de categoria documental, o outro é
compatibilidade explícita com prazo, ou é aposentado — nunca os dois como
verdades paralelas e permanentes.

`Arquivos` e `Arquivos 2` não são um exemplo de violação deste princípio — são
um exemplo de nome que não comunica o contrato. Um contrato oficial exige que
o nome (ou, na ausência de poder renomear, a documentação do campo) deixe claro
qual é o anexo físico e qual é a referência de link. Ambíguo no nome é falha de
contrato mesmo quando o dado está certo.

---

## 4. Entidades oficiais

Os conceitos fundamentais do negócio têm definição única, e essa definição não
é reinventada por módulo:

**Colaborador, Cliente, Contrato, Documento, Competência, Envio, Assinatura,
Pagamento.**

Cada um desses é uma entidade com identidade própria — um Colaborador não é
"o que a tabela Funcionários tem hoje", é o conceito de negócio que a tabela
Funcionários tenta representar. Se a tabela mudar, a entidade continua a
mesma. Nenhum módulo cria sua própria versão de "o que é um Documento" —
existe uma definição, e módulos referenciam essa definição.

---

## 5. Estados oficiais

Cada processo tem uma máquina de estados documentada, com um vocabulário
único de nomes de estado. Estados não são criados livremente dentro de rota,
script, formulário ou automação — se um estado novo é genuinamente necessário,
ele entra primeiro na máquina de estados documentada, depois no código.

`Enviar`, `Pendente`, `Processando`, `Concluído`, `Finalizado` e `Pronto`
coexistindo é o retrato exato do que este princípio existe para impedir: nomes
diferentes competindo pelo mesmo significado (ou pior, significados
parecidos-mas-não-iguais que ninguém documentou a diferença). A resolução
disso é trabalho de arquitetura, não deste manifesto — mas a partir de agora
nenhum estado novo é adicionado a essa lista sem decisão explícita de que ele
não duplica um que já existe.

---

## 6. Eventos oficiais

A comunicação entre módulos prefere acontecer por eventos de negócio nomeados
e documentados, não por dois módulos lendo e escrevendo direto no mesmo campo
de tabela sem contrato. Vocabulário inicial de eventos do domínio:

- `DocumentoRecebido`
- `DocumentoClassificado`
- `DocumentoProcessado`
- `EnvioSolicitado`
- `EnvioRealizado`
- `AssinaturaConcluida`
- `ProcessamentoFalhou`

Isso não exige um barramento de eventos formal hoje — na prática atual, um
evento pode ser uma transição de `Status` no Airtable observada por um worker.
O que este princípio exige é que essa transição tenha nome de negócio
reconhecível, não apenas um valor de campo que só faz sentido para quem
escreveu aquela rota.

---

## 7. Responsabilidade única

Cada módulo tem responsabilidade claramente delimitada e não executa, por
baixo dos panos, uma função que pertence a outro domínio. Se o módulo de
Distribuição decide reclassificar um documento porque "só para garantir",
isso é uma violação — reclassificação é do módulo de Classificação, mesmo que
copiar a lógica ali dentro pareça mais rápido no momento.

Quando um endpoint faz três coisas de três domínios diferentes numa função só
(comum no `app.py` atual), isso é reconhecido como débito herdado do legado,
não como padrão a repetir em código novo.

---

## 8. Uma regra, uma fonte

Uma mesma regra de negócio não existe de forma independente em vários lugares.
Quando a migração exigir duplicação temporária (por exemplo, uma regra
reimplementada em módulo novo enquanto o legado ainda roda a antiga), essa
duplicação precisa ter:

- identificação explícita de qual das duas é a fonte oficial no momento;
- um plano registrado para eliminar a outra.

Duplicação sem essas duas coisas não é "temporário" — é uma segunda fonte de
verdade permanente disfarçada, e cedo ou tarde as duas divergem sem que
ninguém perceba qual está certa.

---

## 9. API antes de navegador

Toda integração usa API sempre que ela existir e permitir a operação
necessária. Automação por navegador só é aceitável quando, ao mesmo tempo:

1. não existe API para aquela operação;
2. ou a API existe mas não permite o que precisa ser feito;
3. há justificativa documentada de por que o navegador é necessário;
4. existe mecanismo de auditoria e recuperação de falha para essa automação.

Automação de navegador sem essas quatro condições registradas é dívida técnica
assumida sem aviso — não é uma alternativa neutra à API, é a opção mais frágil
disponível, usada apenas quando não há outra.

---

## 10. Erros explícitos

Uma operação que falhou não retorna nem registra sucesso. Isso vale para
resposta HTTP, campo de `Status`, log e registro de auditoria — todos
precisam representar o resultado real da operação, não o resultado desejado
nem "não travou, então deu certo".

Um endpoint que engole exceção e responde 200 com corpo vazio é uma mentira
estrutural sobre o estado do sistema, e é tratado como bug de arquitetura, não
como detalhe de implementação.

---

## 11. Idempotência

Toda operação que pode ser executada mais de uma vez (reprocessamento manual,
retry automático, reenvio de webhook) tem um mecanismo que impede duplicidade
ou efeito colateral inconsistente — chave natural, hash, ou verificação de
estado antes de agir. "Não vamos rodar de novo por engano" não é um mecanismo,
é uma esperança.

---

## 12. Auditoria obrigatória

Toda operação relevante registra, no mínimo:

- o que aconteceu;
- quando aconteceu;
- quem ou qual sistema executou;
- qual entidade foi afetada;
- qual era o estado anterior;
- qual é o novo estado;
- qual foi o resultado;
- qual erro ocorreu, quando aplicável.

Se uma operação relevante não deixa rastro suficiente para reconstruir essa
lista depois, ela não está pronta para produção, independente de já estar
gerando o resultado certo hoje.

---

## 13. Observabilidade

Processos críticos têm logs estruturados, identificador de correlação (para
seguir uma requisição de ponta a ponta entre webhook, fila, worker e envio) e
um caminho claro de diagnóstico quando algo falha. "Olhar o log do Render e
tentar adivinhar" não é observabilidade, é arqueologia.

---

## 14. Segurança por padrão

Credencial, token e dado sensível não vivem dentro do código-fonte. Acesso
segue o princípio do menor privilégio — um módulo tem acesso ao que precisa
para sua responsabilidade, não a tudo porque é mais simples de configurar uma
vez.

---

## 15. Migração incremental

O sistema legado não é reescrito de uma vez. Módulos novos substituem
funcionalidade antiga gradualmente, via *strangler pattern*, conforme já
definido em `MAGNATA_OS_ARQUITETURA.md`. Uma proposta de "vamos parar tudo e
reescrever" é, por definição, incompatível com este manifesto — a única
migração aceitável é a que mantém a operação rodando o tempo todo (princípio
1).

---

## 16. Compatibilidade controlada

Toda adaptação temporária entre estrutura antiga e nova é explícita — não uma
gambiarra silenciosa escondida numa função utilitária. Ela é testada, e tem um
plano de retirada registrado. Compatibilidade sem prazo de saída é dívida
técnica permanente com nome de solução provisória.

---

## 17. Testes obrigatórios

Funcionalidade nova tem teste compatível com o risco que carrega. Processo
crítico testa, no mínimo:

- caminho de sucesso;
- falhas previsíveis;
- repetição da mesma operação;
- duplicidade de entrada;
- indisponibilidade de sistema externo (Airtable, Secullum, Evolution API,
  SMTP fora do ar);
- retomada correta depois de um erro.

O projeto já tem uma cultura real de arquivos `test_*.py` cobrindo cenários de
concorrência e validação — este princípio formaliza que isso é obrigatório
daqui para frente, não um bônus quando dá tempo.

---

## 18. Tecnologia subordinada ao negócio

Airtable, Render, Redis, Celery, Google Apps Script, Evolution API,
automação de navegador e qualquer ferramenta futura são componentes
substituíveis. O domínio da Magnata — o que é um Colaborador, o que é um
Envio, o que é uma Competência — não depende conceitualmente de nenhuma
dessas ferramentas. Se amanhã o Airtable for trocado por outra coisa, a
definição de Colaborador não muda; só muda onde ela é persistida.

---

## 19. Documentação como parte do sistema

Uma funcionalidade não está concluída sem documentação suficiente para
alguém operar, dar manutenção e auditar sem depender de perguntar a quem
escreveu o código. Documentação não é o que sobra depois que o código
funciona — é parte do que faz o código estar pronto.

---

## 20. Critério de conclusão

Nenhum módulo é considerado parte oficial do Magnata OS só porque está
funcionando em produção. "Funciona" é o mínimo, não o critério. Para ser
oficial, um módulo precisa ter:

- responsabilidade definida (princípio 7);
- contratos documentados (princípio 3);
- estados documentados (princípio 5);
- eventos documentados (princípio 6);
- testes (princípio 17);
- logs (princípio 13);
- auditoria (princípio 12);
- tratamento de erro explícito (princípio 10);
- idempotência quando aplicável (princípio 11);
- documentação operacional (princípio 19);
- estratégia de migração do que ele substitui no legado (princípio 15).

Um módulo pode estar em produção e, ao mesmo tempo, ainda não ser "oficial"
neste sentido — isso é aceitável durante a migração, desde que registrado como
pendente, não apresentado como concluído.

---

## O que o Magnata OS não aceita

- Não aceita estado novo criado dentro de uma rota sem entrar antes na máquina
  de estados documentada.
- Não aceita dois campos ou duas tabelas competindo pelo mesmo conceito sem
  decisão explícita de qual é a fonte.
- Não aceita endpoint que responde sucesso quando a operação falhou.
- Não aceita automação de navegador como primeira opção quando existe API
  capaz de fazer o mesmo.
- Não aceita reescrita completa do legado de uma vez como estratégia de
  migração.
- Não aceita regra de negócio duplicada sem identificação de fonte oficial e
  plano de remoção da duplicata.
- Não aceita credencial ou token dentro do código-fonte.
- Não aceita funcionalidade nova sem nenhum teste, alegando urgência como
  justificativa permanente.
- Não aceita "está funcionando" como sinônimo de "está pronto".
- Não aceita mudança que arrisque interromper um processo real da empresa sem
  que isso tenha sido pesado e assumido conscientemente antes, nunca como
  efeito colateral não percebido.

---

## Definição de pronto

Uma entrega — endpoint, módulo, migração de campo, automação — está pronta
quando, e só quando:

1. o processo de negócio por trás dela está entendido e registrado (princípio
   2), não só o comportamento técnico desejado;
2. todo dado que ela compartilha com outro módulo tem contrato explícito
   (princípio 3), sem nome ambíguo nem sinônimo não resolvido;
3. ela não introduz estado, entidade ou regra paralela a algo que já existe
   sem decisão explícita de convivência ou substituição;
4. falha é distinguível de sucesso em toda camada — resposta, estado, log,
   auditoria;
5. reexecução da mesma operação não produz duplicidade nem efeito colateral
   inesperado;
6. existe teste cobrindo pelo menos o caminho de sucesso e a falha mais
   provável;
7. existe log suficiente para reconstruir o que aconteceu sem acesso ao
   autor original;
8. a operação preservada (princípio 1) foi verificada — nada que já
   funcionava parou de funcionar.

Sem essas oito condições, a entrega é um rascunho em produção, não uma
entrega concluída. Isso não impede colocar algo em produção antes de
satisfazer todas — impede *chamar* isso de concluído antes de satisfazer.

---

## Como tomar decisões arquiteturais

1. Nomear o processo de negócio real por trás da decisão, não a solução
   técnica cogitada.
2. Verificar se algum módulo, contrato, entidade, estado ou evento já
   existente cobre isso, total ou parcialmente (ADD-ONLY, reuse-first).
3. Se exigir algo novo, registrar em documento curto e objetivo: o que muda,
   por que o existente não serve, qual o impacto em operação preservada.
4. Verificar explicitamente contra este manifesto e contra
   `MAGNATA_OS_ARQUITETURA.md` — se houver conflito com um princípio, ele
   precisa ser resolvido ou justificado por escrito antes de codar, nunca
   decidido implicitamente dentro da implementação.
5. Definir como a decisão se encaixa no plano de migração incremental —
   ela é um passo do strangler pattern, ou é uma mudança isolada que não
   afeta a migração?
6. Só depois disso, implementar. Implementação sem os passos 1 a 5 é o
   padrão que criou o `app.py` de 10.400 linhas — não é neutro, é o próprio
   problema se repetindo.

Em caso de dúvida real entre duas opções válidas, a que preserva a operação
em produção e exige menos mudança simultânea em contratos/estados vence — a
opção mais "elegante" que arrisca mais superfície ao mesmo tempo perde.

---

## Relação com o sistema legado

O `app.py` atual — e tudo que ele faz hoje em produção — não é tratado como
erro a ser eliminado com urgência. É tratado como o sistema que paga a conta
hoje e que será substituído pedaço por pedaço, sem parar de pagar essa conta
enquanto isso acontece.

Isso significa, concretamente:

- Nenhum módulo novo é uma razão para desligar código legado equivalente antes
  que o novo tenha sido comprovado em produção fazendo o mesmo trabalho.
- Débito técnico identificado no legado (nomes ambíguos, estados duplicados,
  fluxos paralelos) é registrado e priorizado — não corrigido de passagem
  "já que estamos mexendo ali", porque correção não-planejada em código
  legado é uma das formas mais comuns de quebrar operação preservada.
- Toda extração de módulo do legado (conforme o plano em
  `MAGNATA_OS_ARQUITETURA.md`) mantém os testes existentes daquele
  comportamento passando sem alteração perceptível para quem usa o sistema.
- O legado tem voz nas decisões: se uma arquitetura nova é elegante no papel
  mas exige reescrever cinco integrações estáveis para funcionar, isso é um
  custo real da decisão, não um detalhe de implementação a ignorar.

---

## Compromisso permanente

Este manifesto vale para todo código escrito a partir de 2026-07-22, para toda
decisão de schema, para toda automação nova, e para toda revisão do que já
existe. Ele não é revisto para se adequar a uma pressão de prazo específica —
se um prazo exige violar um princípio aqui, isso é uma decisão explícita e
registrada, com dono e consequência conhecida, nunca um desvio silencioso.

O Magnata OS existe para que a operação da empresa continue rodando de forma
confiável enquanto cresce em complexidade — não para que o código pareça
sofisticado. Todo princípio acima existe a serviço disso. Quando um princípio
e a operação real entrarem em conflito aparente, o primeiro passo é entender
por que o conflito existe, não descartar o princípio nem parar a operação.

Este documento é permanente. O que muda com o tempo é a arquitetura técnica
que o implementa (`MAGNATA_OS_ARQUITETURA.md`) — não os princípios aqui.
