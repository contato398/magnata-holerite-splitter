# Intérprete de Ordem em Linguagem Natural do Operador V1

## Necessidade de negócio (registrada por completo, não só na conversa)

Pedido literal do dono do produto: dar a ordem em texto livre, do tipo
"manda pro Fulano e pro Beltrano o holerite de setembro, com assinatura
digital e comprovante", e o sistema montar sozinho a mesma
`SelecaoEnvioOperador` que hoje o operador monta manualmente em JSON
para `scripts/selecao_envio_operador_cli.py` (`docs/decisoes/selecao-
envio-operador-v1.md`, PR #210). Comportamento central pedido, no
enunciado da missão: **"se perceber qualquer problema ou dificuldade
antes de enviar, aí sim pode pedir orientação"** -- ou seja, o
intérprete nunca adivinha; qualquer dúvida real vira pendência
explícita para o humano.

## O que foi construído

1. **Núcleo puro** --
   `magnata_os/orquestrador/interpretar_ordem_operador_v1.py`:
   - `ResultadoInterpretacaoOrdem`: união clara (`/CLAUDE.md` §4,
     dimensões nunca fundidas) entre `selecao` pronta
     (`SelecaoEnvioOperador`, contrato de `selecao_envio_operador_v1.py`,
     **INTOCADO**) e `duvidas` (tupla de `DuvidaInterpretacaoOrdem`,
     nunca os dois campos preenchidos nem os dois vazios ao mesmo
     tempo -- validado no próprio `__post_init__`).
   - `DuvidaInterpretacaoOrdem`: 1 dúvida real e específica
     (`codigo`/`descricao`/`trecho_ordem`), nunca uma exceção genérica
     nem uma escolha arbitrária.
   - `interpretar_ordem_contra_linhas_diagnostico(ordem_texto, linhas,
     diretorio_nomes=None)`: função pura, determinística e idempotente
     (todo conjunto usado para decisão é ordenado explicitamente, nunca
     depende de ordem de iteração de `set`/`dict`) que:
     1. localiza o cliente (diagnóstico precisa cobrir exatamente 1 --
        mesmo padrão de escopo das 3 CLIs anteriores, `--cliente X
        --competencia Y`);
     2. reconhece o tipo de documento pedido por um vocabulário natural
        pequeno e documentado (holerite/contracheque, folha de ponto,
        extrato, FGTS, comprovante de pagamento, nota fiscal, boleto,
        certidão, guia) e confere contra o(s) `tipo_documental` real(is)
        do diagnóstico por correspondência de tokens (tolera
        maiúscula/minúscula, acento e a forma exata da string);
     3. resolve a competência: citada explicitamente (ISO `AAAA-MM`,
        `MM/AAAA` ou "mês [de ano]") OU **implícita**, quando o
        diagnóstico só cobre 1 competência para o cliente;
     4. extrai 1..N destinatários citados após conectores
        ("pro"/"pra"/"para"), tolerando "e"/vírgula entre nomes;
     5. resolve cada nome contra os candidatos do diagnóstico pelo
        critério objetivo abaixo;
     6. para cada combinação resolvida, confirma que o `tipo_documental`
        existe e está `PRONTO` para aquele colaborador/competência;
     7. se **qualquer** etapa acima tiver dúvida, devolve TODAS as
        dúvidas encontradas (nunca para na primeira) e `selecao=None`;
        só devolve `SelecaoEnvioOperador` quando zero dúvidas existirem.
   - Parsing **determinístico** (regex/heurística sobre texto livre em
     português) -- **ZERO dependência de API de LLM externa**. Isso é
     deliberado, não uma limitação técnica: uma chamada a um modelo de
     linguagem externo seria uma escrita/chamada externa nova, fora do
     escopo autorizado desta missão (`/CLAUDE.md` §6) e tornaria o
     critério de "dúvida real" uma caixa-preta não auditável -- o
     critério usado aqui é 100% objetivo e está documentado abaixo,
     nunca uma inferência de modelo.

2. **CLI** -- `scripts/interpretar_ordem_operador_cli.py`:
   - Lê `--diagnostico` (MESMO formato de `DiagnosticoPrestacao.
     como_dict()` já usado pelas 3 CLIs anteriores), `--ordem` (texto) e
     opcionalmente `--diretorio-nomes` (ver lacuna de contrato abaixo).
   - Imprime `ResultadoInterpretacaoOrdem.como_dict()` -- quando pronto,
     no MESMO formato `{"itens": [...]}` que `--selecao` já espera em
     `selecao_envio_operador_cli.py`/`prestacao_compor_ordem_
     selecionada_cli.py` -- pode ser salvo direto e usado sem adaptação.
   - Mesmo espírito das 3 CLIs anteriores: script manual, leitura de
     arquivos locais, nenhuma autenticação/rota HTTP nova.

## Critério objetivo de "correspondência de nome inequívoca" (documentado, não uma caixa-preta)

1. **Correspondência EXATA** de nome completo normalizado (acento e
   caixa ignorados) contra 1 único candidato do diagnóstico -> match
   inequívoco.
2. Sem correspondência exata: **correspondência PARCIAL** -- todo token
   do nome citado precisa estar presente, em qualquer ordem, nos tokens
   do nome candidato. Só é aceita quando resolve para **exatamente 1**
   candidato.
3. **0 candidatos** (exatos ou parciais) -> dúvida
   `DESTINATARIO_NAO_ENCONTRADO`.
4. **2+ candidatos** (exatos ou parciais) -> dúvida
   `DESTINATARIO_AMBIGUO`, nunca uma escolha arbitrária entre eles.

O mesmo tipo de critério objetivo (nunca um "parece razoável") vale
para tipo documental (`DOCUMENTO_NAO_ENCONTRADO`/`DOCUMENTO_AMBIGUO`) e
competência (`COMPETENCIA_AUSENTE_E_NAO_INFERIVEL`/`COMPETENCIA_
AMBIGUA_OU_NAO_ENCONTRADA`).

## Lacuna de contrato encontrada e registrada (não resolvida em silêncio, `/CLAUDE.md` §2)

A missão pediu correspondência "contra os nomes reais presentes no
`DiagnosticoPrestacao`". Investigação (antes de qualquer código, como
exige `/CLAUDE.md` §8) confirmou que isso **não é possível como
enunciado**: `DiagnosticoPrestacao.como_dict()` **nunca carrega nome de
colaborador**, só `colaborador_id` -- um `ReferenciaCanonica('COLABORADOR',
id_interno)` deliberadamente sanitizado, por desenho, em toda a cadeia
(`composicao_ciclo_persistente_prestacao.py`, comentário "nunca CPF,
nome de pessoa"; todos os adapters de `documental/importacao_lote/
adapters/`, ex. `airtable_holerites_prestacao.py`: "Colaborador SEMPRE
sanitizado"). Isso é proteção de dado pessoal deliberada (LGPD,
`/CLAUDE.md` §6), não um bug a corrigir.

**Decisão adotada, registrada explicitamente:** este módulo recebe um
`diretorio_nomes` **separado e opcional** (`Mapping[colaborador_id,
nome]`), nunca misturado ao diagnóstico em si -- o `DiagnosticoPrestacao`
continua exatamente como é hoje, sem nenhum campo de PII novo. A CLI
expõe isso como `--diretorio-nomes` (JSON local, opcional). **Sem ele,
o próprio `colaborador_id` é usado como "nome" de correspondência** --
suficiente para os testes/ambiente sintético deste repositório (onde
`colaborador_id` já costuma ser um texto legível, ex. `colab-1`), mas
**insuficiente para um operador real digitando nome de pessoa física
contra um diagnóstico real**, cujo `colaborador_id` é um id opaco do
Airtable (`recXXXXXXXX`).

**Pendência aberta, não resolvida nesta missão:** de onde viria esse
`diretorio_nomes` em produção (um adapter novo de leitura read-only do
Airtable? uma tabela interna já prevista em `magnata_os/documental/
alocacao/contato_colaborador.py`?) é uma decisão arquitetural nova, que
exigiria contrato e possivelmente um novo adapter de leitura -- fora do
escopo desta missão (que pediu só o intérprete e sua CLI) e por isso
não decidida aqui em silêncio.

## O que NÃO entra (gate remanescente, modo sombra intacto)

- **Isto é pura interpretação/composição de seleção -- não é ativação
  de transporte real, não é uma nova barreira de segurança, não muda
  `autorizacao_transporte_real.py`** (arquivo não tocado, não importado
  por este módulo).
- O intérprete **nunca** importa `porta_execucao`, `transporte_real_
  habilitado`, nem qualquer adapter de transporte real. Produz só
  `SelecaoEnvioOperador` (dados em memória) ou uma pendência -- nunca
  cria Ordem, nunca chama Postgres/Airtable/WhatsApp, nunca despacha
  assinatura real.
- O passo seguinte (`selecao_envio_operador_cli.py` -- validar contra o
  diagnóstico -- e `prestacao_compor_ordem_selecionada_cli.py` --
  compor a Ordem, sempre em PENDING) continua **exatamente como está**,
  sem nenhuma alteração de comportamento. A saída desta CLI nova é só
  mais uma forma de produzir o `selecao.json` que esses dois já
  consomem.
- ZERO alteração em `app.py`. ZERO migration. ZERO variável de ambiente
  de transporte real habilitada.

## Limitações declaradas do parser (honestidade > aparência de completo)

- **Vocabulário de tipo documental é pequeno e fixo** (ver lista acima)
  -- um sinônimo fora dele (`TIPOS_DOCUMENTAIS_CANONICOS`,
  `normalizacao_requisitos_prestacao.py`, tem mais entradas que as
  cobertas aqui, ex. "DCTFWeb") gera `TIPO_DOCUMENTAL_NAO_IDENTIFICADO`
  em vez de reconhecer a intenção -- extensível (é só adicionar entrada
  em `_ALIASES_TIPO_DOCUMENTAL`), não coberto nesta versão.
- **Extração de destinatário é regex sobre conectores
  "pro"/"pra"/"para"**, não um parser sintático real. Uma ordem
  fraseada de forma muito diferente ("os documentos do Fulano" sem
  conector, ou o conector no meio de uma oração complexa) pode não
  extrair nenhum destinatário -- o que vira `DESTINATARIO_NAO_
  IDENTIFICADO` (dúvida, nunca um silêncio ou uma Ordem errada), mas
  exige que o operador reformule a ordem.
- **Nomes compostos separados só por "e" livre (sem conector repetido)
  são divididos em destinatários separados** (ex.: "para Fulano e
  Beltrano" vira 2 destinatários) -- um nome próprio que legitimamente
  contivesse a palavra solta "e" seria quebrado incorretamente. Não
  coberto nesta versão; caso real não observado nos dados sintéticos
  testados.
- **Acentos são normalizados (removidos) em todo o texto processado**,
  inclusive no `trecho_ordem` de uma dúvida -- uma dúvida mostrará
  "Sao Paulo" em vez de "São Paulo", por exemplo. Cosmético, não afeta
  a correção da correspondência (que já ignora acento por critério).
- **1 ordem == 1 tipo de documento para todos os destinatários citados**
  -- "manda pro Fulano o holerite e pro Beltrano a folha de ponto" (2
  tipos diferentes na mesma ordem) não é suportado nesta versão; o
  primeiro tipo reconhecido no texto é aplicado a todos os destinatários
  extraídos.
- **Ambiguidade de cliente**: se o diagnóstico informado cobrir mais de
  1 cliente (`clientes` com múltiplos `cliente_id`), o intérprete
  devolve `CLIENTE_AMBIGUO_NO_DIAGNOSTICO` -- esta versão não tenta
  extrair o nome do cliente da ordem, só resolve diagnóstico já
  escopado a 1 cliente (mesmo padrão das CLIs anteriores,
  `--cliente X --competencia Y`).

## Testes rodados

- `test_interpretar_ordem_operador_v1.py`: contrato da união
  (`ResultadoInterpretacaoOrdem`), caminho feliz (1 e N destinatários,
  com/sem assinatura, competência explícita em 3 formatos e implícita),
  cada tipo de dúvida (nome ambíguo, destinatário não encontrado,
  documento não encontrado, documento não pronto, competência ausente
  e não inferível, tipo documental não reconhecido), fallback sem
  `diretorio_nomes`, e idempotência (caminho feliz e caminho com
  dúvida).
- `tests/test_scripts_interpretar_ordem_operador_cli.py`: CLI ponta a
  ponta com arquivos locais (`tmp_path`), incluindo `main`/`argparse`/
  erro de arquivo inexistente.
- Suíte completa (`python -m pytest -q`): 3094 passed, 103 skipped, 0
  failed -- nenhuma regressão.
