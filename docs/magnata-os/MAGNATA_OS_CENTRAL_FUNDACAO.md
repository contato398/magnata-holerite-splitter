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

`necessidade -> localização -> validação -> preparação -> ordem de distribuição -> canal -> evidência -> fechamento`

## Modelo de estado mínimo

Toda operação de distribuição deve conseguir representar, no mínimo:

- `intent_id`
- `document_id`
- `document_version`
- `recipient_id`
- `channel`
- `status`
- `attempt_count`
- `last_error`
- `created_at`
- `updated_at`
- `evidence_id`
- `fallback_required`

Estados recomendados:

`PENDING -> PREPARANDO -> PRONTO -> ENVIANDO -> ENTREGUE -> ASSINATURA_PENDENTE -> CONCLUIDO`

Com saídas controladas para:

`BLOQUEADO`, `ERRO_RETRY`, `FALLBACK_MANUAL`, `CANCELADO`.

## Busca documental

Quando uma solicitação chegar, o sistema deve consultar as fontes disponíveis sem exigir pré-cadastro manual no Airtable.

Ordem de resolução:

1. índice/estado operacional do Magnata OS;
2. armazenamento documental conhecido;
3. Airtable e integrações legadas;
4. e-mail e fontes externas autorizadas;
5. arquivos locais/conectores disponíveis.

A resposta da busca deve registrar onde procurou, quais candidatos encontrou e por que um documento foi selecionado ou bloqueado.

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

## Fases de execução

### Fase 0 — Fundação (esta branch)

- registrar arquitetura-alvo;
- registrar fronteiras entre Orquestrador, domínios, capacidades e canais;
- definir contrato mínimo de estado e fallback;
- preservar o legado sem alteração de produção.

### Fase 1 — Núcleo operacional

- expor estado operacional via API;
- consolidar identidade documental e destinatário;
- criar serviço de distribuição idempotente;
- criar observabilidade de tentativas/erros;
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
