# Roteamento por Canal (Plano A WhatsApp / Plano B E-mail) — Prestação -> Distribuição Documental, V1 shadow

## Objetivo

Ligar a saída PENDING da Prestação de Contas ao contrato genérico de
Distribuição Documental do Grande Orquestrador com **capacidade de
roteamento por canal** — WhatsApp como Plano A (automático), e-mail
como Plano B (fallback quando o Plano A não resolve) — sempre em modo
sombra/dry-run, sem nenhum transporte real.

## Estado encontrado antes desta mudança (registrado explicitamente)

Ao investigar o pedido desta tarefa, o elo "Prestação PENDING ->
contrato de distribuição genérico" **já existia, mesclado em `main`**,
implementado em incrementos anteriores documentados em
`docs/decisoes/prestacao-distribuicao-documental-v1.md`
(`wiring_prestacao_distribuicao_documental_shadow.py`,
`executar_prestacao_ate_distribuicao_documental_shadow`) e em
`magnata_os/orquestrador/resolver_parametros_ordem_prestacao_contato_v1.py`
(primeira implementação real de `ResolverParametrosOrdemPrestacao`,
usando o Contato Canônico de Colaborador V1). A descrição desta tarefa
("hoje nada consome o PENDING da Prestação e entrega pro contrato de
distribuição") não correspondia mais ao código em `main` no momento da
execução — isto é registrado aqui, por escrito, em vez de resolvido em
silêncio (`/CLAUDE.md` §2).

O que de fato **não existia**: nenhum componente decidia entre 2
canais. Todos os presets de `politica_preset_distribuicao_documental.py`
são fixos em `canal='WHATSAPP'`, e o único resolvedor real
(`construir_resolvedor_parametros_ordem_prestacao_contato_v1`) resolve
um único canal por vez, sem fallback. Esse é o gap real fechado por
este incremento.

## Decisão arquitetural

- **Combinador genérico, não um segundo motor**: novo módulo
  `magnata_os/orquestrador/resolver_parametros_ordem_prestacao_fallback_canal_v1.py`
  (`construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1`)
  — recebe 2 `ResolverParametrosOrdemPrestacao` já prontos (Plano A e
  Plano B) e devolve um terceiro com a MESMA assinatura, plugável
  direto em `executar_prestacao_ate_distribuicao_documental_shadow`
  (`resolver_parametros_ordem=...`) sem qualquer alteração no
  composition root nem no núcleo genérico
  (`wiring_distribuicao_documental_shadow.py`) — nenhum dos dois foi
  tocado.
- **Política de fallback**: tenta Plano A; se devolver `None` (canal
  indisponível para aquele colaborador — fail-closed, nunca uma
  exceção, mesma disciplina já usada por `resolver_contato_colaborador_
  para_ordem`), tenta Plano B; se Plano B também devolver `None`, o
  combinador devolve `None` — fail-closed, zero Ordem para aquele
  cliente/colaborador, que vira pendência humana (Plano C, mesmo
  vocabulário de `MAGNATA_OS_CENTRAL_FUNDACAO.md` §"Fallback por
  exceção" — nunca uma tentativa de adivinhar destinatário/canal).
- **Zero I/O, zero transporte**: o combinador não conhece WhatsApp,
  e-mail, Evolution, Gmail, SMTP nem `app.py` — só compõe 2 funções já
  prontas. Verificado por checagem estrutural via AST
  (`test_zero_import_de_transporte_neste_combinador_de_canal`), mesma
  técnica já usada pelos testes irmãos deste pacote.
- **Plano A (WhatsApp)**: nesta V1, esta integração usa o resolvedor
  REAL já existente,
  `construir_resolvedor_parametros_ordem_prestacao_contato_v1` (Contato
  Canônico de Colaborador V1, `canal=CANAL_WHATSAPP`) — reaproveitado,
  não reconstruído.
- **Plano B (e-mail)**: **decisão de arquitetura explicitamente NÃO
  tomada nesta V1** (ver seção abaixo "O que NÃO foi feito"). O
  combinador é genérico o bastante para aceitar qualquer
  `ResolverParametrosOrdemPrestacao` de e-mail assim que ele existir —
  mas construir esse resolvedor real (de onde vem o e-mail de um
  colaborador? `contato_colaborador.py` com um novo `canal='email'`?
  Airtable? outra fonte?) é uma decisão de produto/arquitetura própria,
  fora do escopo desta tarefa, e não foi tomada em silêncio aqui.

## Testes (`test_resolver_parametros_ordem_prestacao_fallback_canal_v1.py`)

- Unidade pura do combinador: Plano A resolvido nunca chama Plano B;
  Plano A indisponível cai para Plano B; nenhum canal disponível ->
  `None` fail-closed; determinismo (mesma entrada, mesma saída, 2x);
  argumentos repassados integralmente; zero import de transporte (AST).
- Integração ponta a ponta, reaproveitando os fakes já existentes de
  `test_wiring_prestacao_ate_distribuicao_documental_shadow.py` (nunca
  reconstruídos): 2 clientes sintéticos, 1 só com WhatsApp (Plano A) e
  1 só com e-mail (Plano B), ambos chegam a PENDING roteados pelo canal
  certo; cliente sem nenhum canal fica isolado (zero Ordem só para ele,
  Plano C) sem travar o cliente vizinho que tem canal disponível
  (exigência explícita desta missão: "falha de um destinatário não
  trava os demais"); replay (2 execuções idênticas) não duplica a ação
  PENDING.
- Todos os dados de teste são sintéticos (telefone/e-mail fictícios,
  `*.invalid`) — nenhum CPF, nome ou contato real.

## Segurança — por que é seguro (modo sombra)

- Nenhuma linha deste incremento importa `requests`/`boto3`/cliente
  Evolution/cliente Gmail/SMTP/`app.py` — verificado por AST em teste.
- O caminho de execução inteiro (Prestação -> combinador -> Ordem ->
  `materializar_distribuicao_documental_shadow`) já termina em
  PENDING, sem nenhum efeito de transporte, com ou sem este incremento
  — este wiring não abre nenhum caminho de escrita externa que hoje não
  existisse já protegido pela barreira tripla
  (`autorizacao_transporte_real.py`), porque não chama nenhum código de
  transporte, direta ou indiretamente.
- `canal` continua um campo opaco no núcleo genérico
  (`OrdemDistribuicaoDocumental.canal`) — nunca validado contra uma
  lista de canais suportados por transporte real, nunca usado para
  decidir se algo é de fato enviado (o núcleo nunca envia nada em modo
  sombra, independente do valor de `canal`).

## O que NÃO foi feito nesta correção (gate remanescente, fora de escopo)

- **Resolução real de e-mail por colaborador**: não existe hoje uma
  fonte canônica de e-mail (equivalente a `contato_colaborador.py` para
  WhatsApp) — decisão de produto + implementação futura, deliberadamente
  fora de escopo aqui, para não tomar uma decisão de arquitetura
  ambígua (onde/como armazenar e-mail, qual criptografia, qual
  migration) em silêncio dentro de uma tarefa de wiring.
- Qualquer alteração em `app.py`, migration, schema, Evolution, Gmail
  real, worker, Render, produção, env/secrets.
- Ativação real de transporte (barreiras já existentes, inalteradas —
  este incremento nunca as toca).
- Qualquer alteração nos presets existentes
  (`politica_preset_distribuicao_documental.py`) ou no núcleo genérico
  (`wiring_distribuicao_documental_shadow.py`) — ambos permanecem
  intocados.

## Arquivos

Criados: `magnata_os/orquestrador/resolver_parametros_ordem_prestacao_fallback_canal_v1.py`,
`test_resolver_parametros_ordem_prestacao_fallback_canal_v1.py`,
este documento.

Não tocados: `app.py`, todas as migrations, `wiring_distribuicao_
documental_shadow.py`, `wiring_prestacao_distribuicao_documental_
shadow.py`, `politica_preset_distribuicao_documental.py`,
`contato_colaborador.py`, `resolver_parametros_ordem_prestacao_
contato_v1.py`, `distribuir_documento_v1.py`, `ciclo_producao_v1.py`,
`autorizacao_transporte_real.py`, Evolution, Gmail, worker.
