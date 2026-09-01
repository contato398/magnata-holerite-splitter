# Confirmação de Alocação Shadow — V1

Documento de decisão da missão "CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1".
Contexto: `magnata_os/documental/alocacao/eventos.py`/`captura.py`
(mecanismo idempotente de aplicação) mergeados em `main`; PR #115
("WIRING REAL DE VÍNCULO V1 EM MODO SHADOW") ainda aberto, mas
independente desta missão -- esta missão não depende de `wiring.py` e
foi ramificada diretamente de `main`. Branch:
`fix/confirmacao-alocacao-shadow-v1`.

Autorização recebida (mensagem distinta da que descreveu o escopo):
*"Autorizo a implementação integral da Confirmação de Alocação Shadow
V1 no Magnata OS, usando Airtable somente em leitura para identificar
colaborador e posto, com dados fictícios nos testes, sem escrita
externa, sem produção, sem alterar app.py, sem merge e sem deploy."*

## Objetivo

Fechar a lacuna já registrada em duas missões anteriores desta série
(`docs/decisoes/alocacao-vigencia-historica-v1.md`,
`VIGENCIA_FONTE_REAL_ENCONTRADA=FALSE`; e
`docs/decisoes/captura-automatica-vinculo-alocacao-v1.md`, Fase 1:
*"Alocação (posto) não tem NENHUMA fonte de data efetiva hoje"*): não
existe, em lugar nenhum do sistema (legado ou novo), um evento
automático confiável de "colaborador X foi alocado no posto Y, na data
Z". A Fase 6 daquele ADR já havia proposto o "menor mecanismo seguro"
para preencher essa memória: **confirmação humana explícita**, nunca
inferência. Esta missão implementa exatamente esse mecanismo.

## Desenho

`magnata_os/documental/alocacao/confirmacao.py` (novo, puro exceto
pela chamada a `captura.py`/`resolver` injetado):

- `SolicitacaoConfirmacaoAlocacao` — dataclass imutável com
  `colaborador_cpf`, `posto_id`, `data_efetiva`, `tipo`
  (`iniciar`/`encerrar`/`transferir`), `origem_evidencia`,
  `posto_destino_id` (só para `transferir`). `__post_init__` recusa
  qualquer `data_efetiva` que não seja `datetime.date` real — mesma
  disciplina de `eventos.py::_exigir_data`. Não existe nenhum caminho
  neste módulo que produza uma data sozinho; um chamador sem data
  confirmada por uma pessoa simplesmente não consegue construir o
  objeto.
- `aplicar_confirmacao_alocacao(repo, resolver, solicitacao)` — resolve
  identidade via `resolver` (injetado, nunca uma chamada Airtable
  direta aqui) e delega a aplicação do evento inteiramente a
  `captura.py` já existente (`aplicar_alocacao_iniciada`/
  `_encerrada`/`aplicar_transferencia`) — nunca reimplementa
  idempotência, conflito ou atomicidade, que já são responsabilidade
  daquela camada.

## Identificação (leitura real do Airtable, autorizada, sem escrita)

`magnata_os/documental/importacao_lote/adapters/
airtable_resolver_identidade_alocacao.py` (novo) —
`ResolverIdentidadeAlocacaoAirtableShadow`, só métodos GET (via
`LeitorAirtableSomenteLeitura`, já existente, nenhum método novo
adicionado a `airtable_leitura.py`):

- `resolver_colaborador_id(cpf)` — reaproveita `listar_funcionarios()`
  (já existente, mesmo método já usado por `wiring.py` para a mesma
  finalidade); levanta `ColaboradorAmbiguoError` se mais de um
  colaborador casar com o mesmo CPF — nunca escolhe o primeiro.
- `confirmar_posto_existe(posto_id)` — reaproveita `TABLE_LOCAIS`/
  `F_LOCAL_CLIENTE` (já confirmados por auditoria real de schema,
  `docs/decisoes/piloto-real-prestacao-readonly-v1.md`) para validar
  que o record id já informado corresponde a um Local real e atual.

**Decisão explícita: posto é identificado por `posto_id` (Airtable
record id), nunca por nome livre digitado.** Um Field ID de "Nome" para
a tabela Locais não está confirmado em nenhum documento nem código
deste repositório até hoje. Fabricar um sem prova real violaria a
disciplina já estabelecida em todo este pacote de adapters (nunca
inventar Field ID) e teria um efeito silenciosamente perigoso: um ID
errado nunca daria erro, só nunca encontraria nada — pareceria "posto
não identificado" para sempre, sem sinalizar a causa real. A convenção
já usada em todo o subsistema de alocação (`eventos.py`, `captura.py`,
`resolucao.py`) já trata posto como `posto_id` opaco, nunca como nome;
este adapter só estende essa mesma convenção até a fronteira de
identificação. Numa tela futura, o humano confirmando SELECIONA um
Local de uma lista (populada por leitura deste mesmo Airtable) — a
identidade carregada por esse fluxo já seria o record id, nunca um
texto de nome.

**Nenhuma chamada real ao Airtable foi feita nesta implementação.**
Toda a cobertura de teste do adapter usa `Mock()` de
`LeitorAirtableSomenteLeitura` (mesma disciplina de
`FonteColaboradoresEsperadosPrestacaoAirtableShadow`/
`FonteVinculosPrestacaoAirtableShadow`) — a autorização concedida cobre
a CAPACIDADE real de leitura (o adapter é funcional e pronto), não uma
execução live nesta fase.

## Shadow — nunca produção

`repo` é sempre injetado por quem chama `aplicar_confirmacao_alocacao`
— `RepositorioAlocacaoSQLite`/`RepositorioAlocacaoPostgres` (já
existentes), sempre contra um banco local/efêmero nesta missão. Nenhum
Postgres de produção é assumido por padrão em nenhum ponto deste
módulo; a decisão de qual Postgres próprio hospedar essa memória de
verdade é explicitamente o **próximo gate**, fora do escopo desta
missão (ver fechamento abaixo).

## Idempotência, conflito, rateio, transferência

Todos herdados de `captura.py`, já provados por
`test_magnata_os_documental_alocacao_captura_v1.py` — esta missão só
adiciona a fronteira de confirmação humana + identificação por cima,
nunca duplica aquela lógica. Cobertura nova
(`test_magnata_os_documental_alocacao_confirmacao_shadow_v1.py`, 21
testes):

- validação de `SolicitacaoConfirmacaoAlocacao` na construção (data
  ausente, data como string, tipo inválido, `posto_destino_id`
  obrigatório só em `transferir`);
- iniciar/encerrar/transferir com identidade resolvida — aplica e
  persiste corretamente;
- idempotência (reprocessar a mesma solicitação nunca duplica nem
  aplica duas vezes);
- conflito temporal (segunda confirmação com data divergente para o
  mesmo posto aberto propaga `ConflitoTemporalEventoError`, nunca
  sobrescreve);
- rateio (dois postos abertos ao mesmo tempo para o mesmo vínculo,
  nenhum fecha o outro);
- colaborador/posto não identificados — a confirmação é recusada
  (`ColaboradorNaoIdentificadoError`/`PostoNaoIdentificadoError`) e
  **nada é aplicado** (inclusive: falha ao identificar o posto de
  destino numa transferência nunca deixa a origem fechada pela
  metade — mesma garantia de atomicidade que
  `captura.aplicar_transferencia` já oferece);
- `ResolverIdentidadeAlocacaoAirtableShadow` isolado, com CPF exato,
  CPF normalizado (formatos distintos), CPF não encontrado, CPF
  ambíguo (2 colaboradores), posto existente/inexistente — todos com
  `Mock()` de leitor, nunca Airtable real.

## O que NÃO foi feito nesta missão (fora de escopo, registrado)

- Nenhuma tela/UI — a confirmação é só a função Python
  `aplicar_confirmacao_alocacao`, chamável de qualquer front-end
  futuro.
- Nenhuma escrita real no Airtable, nenhuma execução contra Airtable
  live, nenhuma produção, nenhuma alteração em `app.py`.
- Nenhuma decisão sobre onde hospedar a tela nem qual Postgres próprio
  usar para a memória real — **esse é o próximo gate**, explicitamente
  adiado pelo pedido que autorizou esta missão.

## Resultado

`APP_PY_MODIFICADO=False`
`ESCRITA_AIRTABLE_REAL=False`
`AIRTABLE_LIVE_EXECUTADO=False`
`PRODUCAO_TOCADA=False`
`POSTO_IDENTIFICADO_POR=posto_id (Airtable record id), nunca nome`
`FIELD_ID_NOVO_FABRICADO=Nenhum -- só reaproveita TABLE_LOCAIS/F_LOCAL_CLIENTE ja confirmados`
`MECANISMO_REUTILIZADO=captura.py (idempotencia/conflito/atomicidade), eventos.py, listar_funcionarios(), normalizar_cpf`
`PROXIMO_GATE=Decidir onde hospedar a tela de confirmacao e qual Postgres proprio usar para a memoria real (fora de escopo desta missao)`
