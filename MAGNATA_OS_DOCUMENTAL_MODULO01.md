# Magnata OS Documental — Módulo 01 (Entrada Central)

**Status:** fundação — só o núcleo de domínio e o serviço de entrada.
**Não é rota HTTP, não é job, não é integração com Airtable.** Vive
inteiramente fora do `app.py` legado, sem tocar nele.

## Objetivo desta fase

Construir a fundação da esteira documental central: o modelo canônico de
`Documento`, o histórico de eventos, e um serviço único de entrada que
registra qualquer documento novo de forma idempotente — antes de
qualquer OCR, classificação, fatiamento, vínculo ou envio.

## Estrutura

```
magnata_os/
└── documental/
    └── modulo01/
        ├── dominio.py           # Documento, StatusDocumento, EventoHistorico
        ├── repositorio.py       # interfaces + implementação em memória
        └── servico_entrada.py   # ServicoEntradaDocumental
```

## Modelo de `Documento`

Campos: `documento_id`, `arquivo_original`, `nome_original`, `mime_type`,
`tamanho`, `hash_sha256`, `origem`, `recebido_em`, `lote_id`, `status`,
`correlation_id`, `criado_em`, `atualizado_em`.

Entidade **imutável** (`dataclass(frozen=True)`) — uma transição de
status produz uma nova instância via `transicionar_status()`, nunca muta
a existente. `arquivo_original` é, nesta fase, uma **referência**
(`pendente-armazenamento://<hash>`), não os bytes do arquivo — não há
adapter de armazenamento físico ainda; isso é decisão de fase futura.

`documento_id` é gerado por `gerar_documento_id()` (hoje `uuid.uuid4()`),
encapsulado numa única função para que trocar a estratégia de geração
(ex.: UUIDv7, quando essa decisão for tomada) não exija mudar nenhum
chamador.

## Status oficiais

`RECEBIDO`, `REGISTRADO`, `DUPLICADO`, `AGUARDANDO_PROCESSAMENTO`,
`EM_PROCESSAMENTO`, `EM_REVISAO`, `ERRO`.

O serviço de entrada, hoje, só produz a transição `RECEBIDO →
REGISTRADO` (dois eventos de histórico separados). Os demais status
existem porque já fazem parte do vocabulário oficial da máquina de
estados — nenhuma fase futura pode inventar um estado novo sem decisão
explícita, mas usá-los (ex.: mover para `AGUARDANDO_PROCESSAMENTO` após
uma etapa de triagem) é trabalho de um módulo futuro, não deste.

## Idempotência

`ServicoEntradaDocumental.registrar_entrada()` calcula o SHA-256 do
conteúdo recebido e consulta o repositório por esse hash antes de criar
qualquer coisa:

- **hash novo** → cria o `Documento`, salva, transiciona para
  `REGISTRADO`, registra 2 eventos (`DOCUMENTO_RECEBIDO`,
  `DOCUMENTO_REGISTRADO`);
- **hash já existente** → **não cria um segundo `Documento`**, retorna o
  existente sem alterá-lo, e registra um evento `TENTATIVA_DUPLICADA` no
  histórico (com o `correlation_id` daquela tentativa específica,
  distinto do `correlation_id` do documento original).

## Histórico de eventos

`EventoHistorico` é append-only (nunca editado nem apagado): `documento_id`,
`evento`, `status_anterior`, `status_novo`, `timestamp`, `correlation_id`,
`detalhes`. Cada evento carrega o `correlation_id` da operação que o
gerou — pode divergir do `correlation_id` do `Documento` (que é fixado na
criação e nunca muda) quando o evento vem de uma tentativa duplicada
posterior.

## Erros explícitos

- `ArquivoAusente` — conteúdo vazio ou ausente; levantado antes de
  qualquer acesso a repositório.
- `HashInvalido` — usado por `consultar_por_hash()` quando a string
  passada não é um SHA-256 válido (64 hex chars).
- `FalhaPersistencia` — encapsula qualquer erro do repositório ao salvar;
  nunca é engolida, e nenhum evento de histórico "de sucesso" é
  registrado quando a persistência falha.

## O que esta fase explicitamente NÃO faz

OCR; classificação de documento; fatiamento/separação; vínculo com
funcionário; vínculo com cliente; envio (e-mail/WhatsApp); qualquer
acesso real ao Airtable; qualquer alteração no `app.py` ou nos fluxos
legados; deploy.

## Testes

```bash
pytest test_magnata_os_documental_modulo01.py -v
```

13 testes, tudo em memória — nenhum acesso a Airtable, rede ou disco.
Cobrem: primeiro registro, IDs distintos por conteúdo distinto, os 7
status oficiais, duplicidade por hash, idempotência em múltiplas
tentativas, ordem e conteúdo do histórico, arquivo ausente, hash
inválido (consulta), hash válido não registrado, falha de persistência
(sem histórico falso de sucesso), e propagação/geração de
`correlation_id`.
