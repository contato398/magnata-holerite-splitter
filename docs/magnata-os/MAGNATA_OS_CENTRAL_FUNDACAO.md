# Magnata OS Central — Fundação

## Objetivo

Transformar o Magnata OS em uma plataforma operacional multi-domínio, com o Grande Orquestrador como coordenador central, um painel próprio como interface operacional e o Airtable progressivamente rebaixado de dependência estrutural para integração/legado.

## Princípios

1. **Orquestrador primeiro:** domínios produzem intenções; capacidades executam ações autorizadas.
2. **Painel próprio:** o operador trabalha no Magnata OS, não diretamente no Airtable.
3. **Airtable como integração/legado:** pode continuar sendo consultado e alimentado durante a transição, mas não deve ser pré-requisito para executar uma ação segura.
4. **Localização separada de entrega:** encontrar um documento é uma capacidade diferente de enviá-lo.
5. **Canais desacoplados:** WhatsApp e e-mail são canais de execução, não regras de negócio.
6. **Fallback por exceção:** automático é o padrão; manual assistido é Plano B; exceção humana explícita é Plano C.
7. **Rastreabilidade:** cada ação deve ter identidade, estado, tentativa, resultado e evidência.
8. **Idempotência:** repetir uma operação não deve criar duplicidade.
9. **Intervenção humana mínima:** só solicitar ação quando houver erro, conflito, ausência de dado essencial ou decisão que não possa ser tomada com segurança.
10. **Uma única máquina de execução:** a camada Central não cria estados paralelos; reutiliza o ciclo canônico do Orquestrador.

## Arquitetura-alvo

```text
MAGNATA OS — PAINEL CENTRAL
        |
        v
GRANDE ORQUESTRADOR
        |
        +-- Documental / Prestação de Contas
        +-- RH / Ponto
        +-- Financeiro / Fiscal
        +-- Administrativo
        +-- Comercial / Telemarketing
        +-- outros domínios futuros
        |
        v
CAPACIDADES TRANSVERSAIS
  localizar documento | identidade | distribuição | assinatura
  e-mail | WhatsApp | auditoria | notificações | filas/retry
        |
        +--> WhatsApp
        +--> E-mail
        +--> Assinatura digital
        +--> Airtable (integração/legado)
        +--> Postgres / armazenamento operacional
```

## Primeiro módulo operacional

**Prestação de Contas / Documental** será o primeiro módulo integrado ao painel central. Não terá motor de envio próprio nem fluxo paralelo ao Orquestrador.

Fluxo canônico:

`necessidade -> localização -> validação -> preparação -> ordem de distribuição -> gate/política -> execução -> evidência -> fechamento`

A ordem é genérica para **1..N documentos** e **1..N destinatários**. Assinatura e comprovante são requisitos de política/capacidade, não propriedades do tipo documental.

## Modelo de intenção de distribuição

A intenção central deve carregar, no mínimo:

- `intent_id`
- `document_ids[]`
- `document_versions[]`
- `recipient_ids[]`
- `channel`
- `signature_required`
- `receipt_required`
- `state`
- `attempt_count`
- `last_error`
- `created_at`
- `updated_at`
- `evidence_id`
- `fallback_required`

O núcleo não conhece `tipo_documento`, preset específico de holerite, EPI, NR, contrato etc. Essa resolução permanece upstream.

### Estados de execução

A Central reutiliza `EstadoAcaoExecucaoPlano` do Orquestrador:

`PENDING -> EXECUTING -> SUCCEEDED`

ou:

`EXECUTING -> FAILED_RETRYABLE -> EXECUTING`

ou:

`EXECUTING -> FAILED_FINAL`

Não existe um segundo estado `ENVIANDO/CONCLUÍDO` paralelo. A camada de painel poderá apresentar rótulos amigáveis como projeção visual, mas não criará uma segunda fonte de verdade.

### Fallback manual

O fallback é uma **marca de política**, não um novo estado de execução. Quando o canal automático não puder concluir com segurança, a Central marca `fallback_required` e o painel oferece a ação humana mínima. O estado canônico continua pertencendo ao Orquestrador.

## Busca documental

Quando uma solicitação chegar, o sistema deve consultar as fontes disponíveis sem exigir pré-cadastro manual no Airtable.

Ordem de resolução:

1. índice/estado operacional do Magnata OS;
2. armazenamento documental conhecido;
3. Airtable e integrações legadas;
4. e-mail e fontes externas autorizadas;
5. arquivos locais/conectores disponíveis.

A resposta da busca deve registrar onde procurou, quais candidatos encontrou e por que um documento foi selecionado ou bloqueado.

### Capacidade implementada: `magnata_os/central/localizacao.py`

`localizar_documento(necessidade, fontes)` consulta fontes nomeadas em ordem de prioridade e devolve `ResultadoLocalizacao` com decisão, motivo, candidatos e o rastro por fonte (`CONSULTADA`, `FALHOU`, `NAO_CONSULTADA`). Cada fonte segue o formato já existente de `FonteCandidatosDocumentaisPorNecessidade` (`candidatos_para`), então `FonteCandidatosDocumentoInventarioInterna` já é uma fonte válida. A capacidade é genérica na necessidade: não conhece Prestação, tipo documental, cliente ou colaborador.

Localizar não é validar: a capacidade nunca decide se o candidato satisfaz a necessidade de negócio (isso continua no corredor de classificação).

| Decisão | Quando | Segue automático? |
|---|---|---|
| `LOCALIZADO` | exatamente 1 conteúdo (hash) na primeira fonte com candidatos, sem falha em fonte anterior | sim |
| `AMBIGUO` | 2+ conteúdos distintos, ou mesmo `documento_id` com hashes diferentes | não — Plano C |
| `NAO_LOCALIZADO` | nenhuma fonte tem candidato e nenhuma falhou (ausência **nas fontes consultadas**, nunca global) | não seleciona; quem chama decide o próximo passo |
| `INDETERMINADO` | alguma fonte de prioridade maior que a do candidato falhou, ou nenhum candidato com alguma falha | não — Plano C |

Decisões registradas nesta etapa:

1. **Primeira fonte com candidato encerra a busca.** As seguintes ficam no rastro como `NAO_CONSULTADA`. Consequência aceita: ambiguidade entre fontes diferentes não é detectada; dentro da mesma fonte, sim.
2. **Falha de fonte prioritária bloqueia seleção de candidato inferior** (`INDETERMINADO`). A fonte que falhou poderia ter um documento diferente; escolher o candidato de menor prioridade seria adivinhação silenciosa.
3. **Mesmo hash = mesmo conteúdo**: deduplicado, preferindo o menor `documento_id` (determinístico).
4. **Evidência sem dado pessoal**: `como_evidencia()` só carrega ids, hashes, nomes de fonte e o tipo da exceção — nunca a mensagem da exceção nem o nome do arquivo.

Ainda **não** ligado ao ciclo de Prestação (`composicao_ciclo_persistente_prestacao.py` continua recebendo `fonte_candidatos_por_necessidade` diretamente). A ligação muda o comportamento do ciclo — `INDETERMINADO`/`AMBIGUO` precisam de um destino definido (pendência humana) — e é o próximo passo da Fase 3, não desta entrega.

## Entrega

### Plano A — automático

O Orquestrador cria a ordem; o canal executa; o resultado volta para o núcleo de estado.

### Plano B — manual assistido

Somente quando o canal automático falhar ou estiver indisponível. O painel deve apresentar a ação humana mínima: abrir/copiar/enviar e registrar resultado.

### Plano C — exceção

Quando não houver segurança para decidir automaticamente. O painel mostra o motivo, os candidatos e a decisão necessária.

## Painel Central — primeira versão

Reaproveitar a fundação visual já existente na branch histórica `feat/magnata-os-documental-modulo01-fase5-painel`, mas substituir o adapter mock por contratos reais do Magnata OS quando a API estiver disponível.

Visões iniciais:

- Resumo operacional
- Esteira documental
- Documentos
- Envios
- Bloqueios
- Ações humanas
- Parados
- Auditoria
- Saúde dos canais

O primeiro snapshot operacional é **somente leitura** e deriva do repositório de execuções já existente. Não cria uma nova fonte de verdade.

## Fases de execução

### Fase 0 — Fundação (esta branch)

- registrar arquitetura-alvo;
- registrar fronteiras entre Orquestrador, domínios, capacidades e canais;
- definir contrato mínimo de intenção, estado e fallback;
- provar 1..N documentos/destinatários;
- derivar snapshot do estado persistido;
- preservar o legado sem alteração de produção.

### Fase 1 — Núcleo operacional

- consolidar identidade documental e destinatário;
- ligar o contrato central à Ordem genérica existente;
- criar/adaptar persistência sem duplicar `execucoes`/`acoes_execucao_plano`;
- manter Airtable sincronizado, mas não obrigatório para execução.

### Fase 2 — Painel Central

- trazer a fundação visual histórica para uma branch integrada;
- trocar mockAdapter por API real;
- autenticação/autorização real;
- ações humanas controladas;
- visão de saúde e exceções.

### Fase 3 — Prestação de Contas

- ligar a esteira atual ao núcleo central;
- automatizar localização e distribuição;
- WhatsApp/e-mail como capacidades de canal;
- assinatura como capacidade transversal;
- fallback manual assistido.

### Fase 4 — Expansão multiagente

- RH;
- financeiro/fiscal;
- administrativo;
- comercial/telemarketing;
- novos subagentes sob o mesmo Orquestrador.

## Critério de sucesso

O operador não deve precisar abrir o Airtable para descobrir o estado de uma operação cotidiana. O Magnata OS deve mostrar o estado, executar a ação quando autorizada e pedir intervenção apenas em exceções reais.

## Regra de implantação

Nenhuma alteração desta fundação deve substituir o `main` ou afetar produção por si só. Integrações com produção só entram após testes, validação de contratos, idempotência, autenticação e rollback verificáveis.
