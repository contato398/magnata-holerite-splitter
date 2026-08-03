# magnata_os/ — Regras específicas

Complementa `/CLAUDE.md` (raiz) — não repete o que já está lá. Vale
para todo o pacote Python novo do Magnata OS (hoje,
`documental/modulo01/`).

- **Pureza de domínio.** `dominio.py` e `dominio_esteira.py` (e
  qualquer `dominio*.py` futuro) nunca importam `flask`, biblioteca de
  driver de banco (`psycopg2`, `psycopg`), cliente de armazenamento
  (`boto3`) nem cliente do Airtable. Domínio só conhece tipo Python
  puro (`dataclass`, `Enum`, `datetime`) e os próprios contratos do
  módulo.
- **Todo serviço externo entra por adapter.** Um adapter
  (`adapters/`) fala com o driver real duck-typed contra a interface
  mínima necessária (DB-API 2.0 para Postgres, forma de cliente S3) —
  nunca importa o driver por nome dentro do domínio ou do serviço de
  orquestração.
- **Estados e eventos seguem o vocabulário já estabelecido.** Status
  técnico (`StatusDocumento`) e etapa operacional (`EtapaEsteira`/
  `SituacaoEsteira`) são dimensões separadas — nunca fundir as duas num
  campo só (ver `/CLAUDE.md` §4). Toda transição de estado válida está
  numa máquina de estados explícita (`TRANSICOES_*_PERMITIDAS`), nunca
  um `if` solto decidindo se uma transição é permitida.
- **Idempotência por hash é obrigatória** em qualquer caminho de
  entrada novo — mesmo conteúdo, mesmo hash, nunca cria um segundo
  registro.
- **Nenhuma dependência de framework dentro do domínio ou dos
  serviços de orquestração.** Onde um adapter precisar de uma
  biblioteca de infraestrutura, isso fica isolado dentro do próprio
  adapter, nunca vaza como import direto para quem o usa.
