# Fechamento do fluxo WhatsApp + assinatura eletrônica V1

## Estado

Auditoria concluída sobre `origin/main` em
`b7e431dae27d8f3a295b3fedc8b2376ff5cd6eb7` (merge do PR #148).

Esta decisão fecha o desenho e identifica o primeiro hard gate. Não ativa
WhatsApp, Evolution, Airtable, Render, storage ou banco produtivo. Não altera
`app.py`, schema ou migrations.

## Risco independente: colisão de migrations

A `main` contém `0004_envelope_execucao_autorizada.sql` e seu rollback. O PR
#147, ainda aberto, também propõe `0004_execucoes_prestacao.sql` e seu
rollback. Portanto, o PR #147 não pode ser integrado no estado atual. Ele deve
ser tratado em missão própria, baseada na `main` vigente, com renumeração para
o próximo número livre e nova validação do encadeamento. Nada do PR #147 foi
alterado nesta missão.

## 1. Causa do trabalho manual recente

O teste de três documentos usou duas etapas separadas: carga/validação dos
PDFs para obter referências de Arquivo e três chamadas a
`/assinatura/gerar` com `disparar_whatsapp=false`, seguidas de conferência e
uso dos links retornados.

Isso foi a soma de:

- falta de wiring: nenhuma chamada do Orquestrador chega ao motor de
  assinatura;
- segurança intencional: `/assinatura/gerar` não dispara por padrão;
- contrato do legado: exige `funcionario_id`, tipo e `arquivo_record_id` já
  resolvidos no Airtable;
- link tardio: `_gerar_assinatura_core` gera token aleatório e link somente
  dentro da chamada que também cria o registro;
- falta de executor real: o executor persistente ainda usa porta fake;
- falta de adapter: `PortaTransporteWhatsapp` existe, sem adapter para as
  funções Evolution do legado;
- falta de retorno: assinatura/comprovante ficam no Airtable e não produzem
  checkpoint no novo Orquestrador;
- evidência incompleta: o fluxo de assinatura descarta a resposta estruturada
  da Evolution; as rotas diretas retornam message ID, mas não o persistem;
- ausência de acompanhamento: não há consumidor de webhook Evolution que
  sustente `ENTREGUE` ou `LIDO`.

Scripts e HTML usados para coordenar o teste são ferramentas temporárias, não
o fluxo definitivo.

## 2. O que já está resolvido

O motor legado já possui, sem necessidade de um segundo motor:

- `/assinatura/gerar`, `_gerar_assinatura_core` e `COMUNICADO`;
- pacote atômico `HOLERITE_FOLHA_PONTO`;
- identidade por Record ID + SHA-256 e idempotência;
- token/link, validação dos quatro últimos dígitos do CPF;
- IP, timestamp, User-Agent, carimbo e comprovante PDF;
- cópia dos artefatos finais para o funcionário;
- bloqueio de documento trocado e reenvio do mesmo registro para o pacote.

O mecanismo é assinatura eletrônica com evidências, não assinatura digital
certificada ICP-Brasil.

O novo Orquestrador já possui intenção, preview, otimização, autorização
persistida, `PlanoDisparo`, ações persistidas, Envelope Executável V1,
recuperação pós-restart, revalidação de hashes, descoberta sem claim, claim
CAS exato, checkpoint, retry, ordenação, executor fake e
`PortaTransporteWhatsapp`.

## 3. Lacunas confirmadas

1. Não existe contrato entre Orquestrador e motor de assinatura.
2. O link exato não existe no momento do preview.
3. Não existe adapter do executor persistente para o transporte legado.
4. Não existe persistência canônica do ID externo da Evolution no fluxo.
5. Não existe sinal integrado real de entrega ou leitura.
6. Não existe retorno de `Assinado`/comprovante ao Orquestrador.
7. O fluxo genérico grava `Assinado` antes de tentar carimbo/comprovante e
   trata falha posterior como warning; somente `HOLERITE_FOLHA_PONTO` possui
   ordem fail-safe completa.
8. Os estados descritos no comentário do core não são gravados uniformemente:
   o genérico cria `PREPARADO`; o pacote usa `Pendente` e `FALHA_ENVIO`.
9. Campos aspiracionais de status de envio são placeholders e não existem
   como capacidade utilizável.
10. Crash após aceite da Evolution e antes do checkpoint continua incerto; não
    há prova de idempotência/reconciliação no provedor.

## 4. Conflito preview versus link

`PreviewComunicacao` inclui o SHA-256 do texto exato, e `PlanoDisparo` recusa
texto diferente. Hoje o link nasce em `_gerar_assinatura_core`, junto com a
escrita no Airtable. Se isso ocorrer após a autorização, o texto com link não
existia no preview; inseri-lo depois quebra o hash. Criar o registro antes do
preview resolveria o hash, mas produziria obrigação externa sem autorização.

A solução mínima é reservar localmente um token forte antes do preview, sem
efeito externo, incluir o link exato na mensagem e, somente após autorização,
pedir ao motor existente que crie/recupere a obrigação com o mesmo token. O
link reservado fica inativo até o vínculo.

Isso exige alteração de `app.py`; é hard gate e não foi implementado.

## 5. Arquitetura final

```text
intenção do operador
→ resolver documentos/destinatários pelos adapters existentes
→ reservar token/link local, sem escrita externa
→ montar mensagem exata com o link
→ PreviewComunicacao(assinatura=SIM, comprovante=SIM)
→ autorização persistida do preview exato
→ motor existente cria/recupera obrigação com o token reservado
→ PlanoDisparo de uma ação de texto por destinatário
→ envelope + ação persistente
→ executor recupera, valida e faz claim exato
→ adapter do transporte legado envia
→ checkpoint com evidência opaca e ID externo, quando comprovado
→ observador temporário do motor existente acompanha assinatura
→ validar documento final e comprovante por hash
→ concluir ou escalar exceção
```

Não se cria rota, motor, fila ou storage paralelo. O motor atual continua
responsável pela obrigação e comprovante; o Orquestrador passa a decidir,
persistir, executar e acompanhar.

## 6. Uma comunicação por destinatário

Para assinatura, o padrão é uma ação `texto` contendo mensagem e link. O PDF
não é enviado separadamente quando a página já oferece visualização segura.
O preview mostra destinatários, mensagem exata, documentos/hashes, obrigação
de assinatura e comprovante, mensagens por pessoa e total.

`HOLERITE_FOLHA_PONTO` continua como uma obrigação com dois documentos. Três
documentos independentes continuam sendo três obrigações, cada qual com uma
única comunicação ao destinatário correspondente.

## 7. Evidência e estados defensáveis

```text
PREPARADO → AUTORIZADO → ACEITO_PELO_PROVEDOR → ASSINADO → CONCLUIDO
```

`ENTREGUE` e `LIDO` só existem se sinal real do fornecedor for integrado.
Sem ele, o máximo do transporte é `ACEITO_PELO_PROVEDOR`, e somente quando o
corpo da resposta confirmar semanticamente o aceite.

Evidências reaproveitáveis: `preview_id`, `autorizacao_id`,
`acao_execucao_id`, hashes do envelope/texto/documento, ID da obrigação, ID
externo da Evolution, IP, timestamp, User-Agent, confirmação do CPF, PDF
carimbado, comprovante e hashes finais. A assinatura é confirmação mais forte
que leitura, mas não inventa webhook de entrega retroativamente.

## 8. Wiring mínimo e arquivos futuros

Primeiro gate, em branch exclusiva do legado protegido:

- `app.py`;
- testes específicos de `/assinatura/gerar` e `_gerar_assinatura_core`.

Mudança mínima: aceitar token forte reservado, validar formato/entropia,
preservar o comportamento atual sem o parâmetro, correlacionar a obrigação ao
`acao_execucao_id` por referência opaca já disponível e manter
`disparar_whatsapp=false`.

Depois, em branch separada do core:

- pequeno serviço de composição assinatura→comunicação no Orquestrador;
- adapter explícito do motor legado, sem copiar regras;
- adapter de `PortaExecucaoAcao` para `PortaTransporteWhatsapp`;
- testes com assinatura e transporte fake;
- E2E shadow restart→vínculo→envelope→claim→fake→checkpoint;
- observador da assinatura/comprovante por adapter do legado, sem Airtable no
  domínio.

Migration 0004, storage produtivo e transporte real seguem gates separados.

## 9. Revisão adversarial

| Cenário | Comportamento exigido |
|---|---|
| Restart após autorização | recuperar envelope e obrigação por identidades persistidas |
| Link já existente | retornar a mesma obrigação; nunca criar outra |
| Documento/hash divergente | bloquear antes do envio ou conclusão |
| Destinatário errado | hash bloqueia antes do claim |
| Assinatura concluída | não reenviar; reconciliar comprovante |
| Envio duplicado | CAS impede dois executores; pós-provedor exige reconciliação |
| Crash antes do envio | lease/retry retoma com segurança |
| Crash após envio | estado incerto; nunca reenviar cegamente |
| Comprovante ausente | não concluir; escalar exceção |
| Evolution indisponível | falha temporária + backoff, sem nova obrigação |
| Airtable indisponível | não criar/enviar/concluir; preservar para retry seguro |
| Duas ações ao destinatário | preservar ordenação persistente |

## 10. Hard gates

- `app.py` para token reservado;
- Airtable real do motor;
- aplicação da migration 0004 do envelope;
- storage produtivo;
- Evolution real;
- webhook de entrega/leitura, se suportado;
- Render/deploy;
- qualquer envio real.

## 11. Percentual e próxima autorização

Estimativa para “dou a ordem e o robô envia, acompanha a assinatura e guarda o
comprovante sozinho”: **60%**. As duas fundações existem, mas ainda não estão
ligadas e não há acompanhamento/reconciliação real.

Próxima autorização exata recomendada:

> Autorizar branch exclusiva para alterar somente `app.py` e testes do fluxo
> de assinatura, adicionando suporte compatível a token/link previamente
> reservado e correlação opaca com `acao_execucao_id`, mantendo
> `disparar_whatsapp=false`. Sem Airtable real, Evolution real, migration,
> Render, deploy ou envio. Entregar implementação testada, commit, push e PR,
> sem merge.

Depois desse PR revisado, o core poderá receber a costura shadow com fakes sem
violar o hash do preview nem criar um segundo motor.
