# ADR — Envelope Executável Persistente V1

## Estado

Proposto para revisão. A migration 0004 permanece inerte e não autorizada
para aplicação produtiva.

## Contexto

`acoes_execucao_plano` preserva identidade, autorização, hashes, claim,
retry e checkpoint, mas seus hashes são unidirecionais. Após restart, eles
não permitem reconstruir o destinatário, o texto, a legenda e o nome que
formavam a `AcaoEnvio` autorizada.

O módulo documental já oferece a porta `ArmazenamentoArquivos`, com conteúdo
endereçado por SHA-256, e o precedente operacional de armazenar bytes antes
de persistir sua referência.

## Decisão

Uma ação nova poderá referenciar um único envelope JSON canônico V1 por meio
da coluna nullable `envelope_sha256`. O envelope contém os valores necessários
à reconstrução e os vínculos imutáveis com ação, evento, preview e autorização.
Mídia permanece em blob separado, também endereçado por SHA-256.

A ordem de materialização é `blob de mídia -> blob do envelope -> banco`.
Uma falha no banco pode deixar blob órfão, mas não cria deliberadamente uma
linha apontando para conteúdo que não foi armazenado.

Antes do claim, o executor:

1. descobre uma candidata sem alterar estado;
2. recupera e recalcula o hash do envelope;
3. valida vínculos e hashes dos valores claros;
4. recupera e recalcula o hash da mídia, quando aplicável;
5. confirma o fato `AUTORIZADO` exato;
6. reivindica por CAS o `acao_execucao_id` exato;
7. compara o registro reivindicado ao snapshot verificado;
8. entrega ao executor fake o payload já verificado em memória;
9. grava o checkpoint pelo claim vencedor.

Tanto descoberta quanto claim exato excluem `envelope_sha256 IS NULL`.
Ações legadas são preservadas, mas não são executáveis pelo recuperador V1.

## Limites

- Não existe revogação no contrato atual de autorização; a V1 valida apenas
  existência, decisão `AUTORIZADO` e vínculos exatos suportados pelo legado.
- Não há transação ACID entre armazenamento e PostgreSQL.
- Backend produtivo de `ArmazenamentoArquivos` não foi comprovado nem ativado.
- `EXECUTING` órfão permanece incerto e não é reenviado automaticamente.
- PII sai da tabela operacional, mas existe no envelope protegido; hashes de
  destinatário continuam sendo dados pseudonimizados sensíveis.

## Consequências

Não se cria tabela, storage, fila, motor ou dependência Airtable. A migration
0004 adiciona somente a referência nullable e sua constraint de formato. A
ativação de backend produtivo, a aplicação da migration e qualquer transporte
continuam sujeitos a gates independentes.
