# Capacidades transversais do motor documental (Fase 2E.2)

**Data:** 2026-08-30
**Branch:** `fix/capacidades-transversais-documentais`
**Base canônica:** `main @ 332226ebc12a783b1074bc87ba74088b4b460f42` (PR #94 mesclado)
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

O motor geral de compreensão documental (PR #94) resolve `TIPO_
DOCUMENTAL` combinando evidência textual/entidades/contextual, mas
ainda tratava cada documento como "1 PDF = 1 entidade" e não distinguia
a FINALIDADE de um comprovante de pagamento genérico. Esta missão
adiciona 4 capacidades transversais — reutilizáveis por qualquer tipo
documental, nunca especializadas — sem criar nenhum motor paralelo:

1. **Evidência estrutural** (`evidencia_estrutural_documental.py`) —
   contagem de CNPJs/CPFs distintos no documento INTEIRO (preservando
   fronteira de página), nunca a lista bruta.
2. **Detecção de granularidade** (`resolucao_master_documental.py`) —
   UNITÁRIO / POTENCIALMENTE_MASTER / INCONCLUSIVO, a partir só de
   evidência estrutural, nunca do tipo documental.
3. **Separação MASTER → FILHOS** (`separacao_documental.py`) — engine
   pura e plugável que generaliza o carry-forward já provado em
   produção por `app.py::construir_mapa_cliente`.
4. **Finalidade de comprovante de pagamento**
   (`finalidade_comprovante_pagamento.py`) — refina "Comprovante de
   Pagamento" em Salário/FGTS/DCTF-DARF/VR-VA/Assiduidade/Diárias via
   evidência combinada, reaproveitando o MESMO `resolver_tipo_
   documental` (nenhuma regra de combinação nova).

Mais uma peça pequena, aditiva, em `modulo01`
(`decisao_pos_classificacao.py`) liga a decisão de granularidade a
`EtapaEsteira` sem alterar `TRANSICOES_ETAPA_PERMITIDAS` (já permitia
as duas transições necessárias).

## Decisões arquiteturais registradas

### 1. Granularidade NÃO usa `DimensaoResolucao`/`ResolucaoDimensao`

`DimensaoResolucao` tem 6 membros fixos e `ResultadoResolucaoSemantico.
__post_init__` exige que o conjunto de dimensões resolvidas seja
EXATAMENTE igual ao declarado pelo perfil de aplicabilidade em uso —
adicionar um 7º membro seria uma mudança de contrato compartilhado,
efeito em todo perfil já validado, para um sinal sem nenhum consumidor
formal de perfil ainda. A missão pediu explicitamente para evitar
enum/contrato novo "a menos que comprovadamente necessário" — aqui não
era. `DecisaoGranularidadeDocumento` é uma dataclass pequena e própria,
reaproveitando as PEÇAS genéricas já existentes (`EvidenciaSanitizada`,
`NivelConfianca`, `ConfiancaResolucao`), nunca duplicando o vocabulário
de força/evidência — só sem o "envelope" `ResolucaoDimensao`.

### 2. `dominio_esteira.py` não foi tocado

`TRANSICOES_ETAPA_PERMITIDAS` já permite `CLASSIFICACAO -> SEPARACAO` e
`CLASSIFICACAO -> IDENTIFICACAO` sem nenhuma alteração — a Fase K
("ligar, se seguro, sem forçar") foi cumprida com um arquivo NOVO e
pequeno (`decisao_pos_classificacao.py`, em `modulo01`, mesma direção
de dependência já usada por `ponte_prestacao_holerite.py`) que só
SUGERE a próxima etapa a partir de `DecisaoGranularidadeDocumento` —
nunca chama `avancar_etapa`/`validar_transicao_etapa` sozinho.
INCONCLUSIVO nunca sugere etapa (fica para decisão humana explícita —
`/CLAUDE.md` §4, "automação por confiança; ação humana para exceção").

### 3. Evidência estrutural nunca expõe CPF/CNPJ bruto

Seguindo a mesma regra já documentada em `importacao_lote/dominio.py`
("[CPF] é estritamente TRANSITÓRIO... o único uso legítimo é contar
quantos distintos existem... nunca retornado em DTO, evento ou log"),
`EvidenciaEstruturalDocumento` só tem campos inteiros (contagens) —
provado por teste (`test_evidencia_nunca_expoe_cpf_ou_cnpj_bruto`).

## O que foi criado

- **`magnata_os/classificacao/evidencia_estrutural_documental.py`** —
  `EvidenciaEstruturalDocumento`, `analisar_estrutura_documento`,
  `evidencias_sanitizadas_de_estrutura`. Reaproveita `extrair_cnpjs_
  de_texto`/`extrair_cpfs_distintos_de_texto` (já puros).
- **`magnata_os/classificacao/resolucao_master_documental.py`** —
  `EstadoGranularidadeDocumento`, `DecisaoGranularidadeDocumento`,
  `detectar_granularidade_documento`. Regra: >=2 CNPJs ou >=2 CPFs
  distintos → POTENCIALMENTE_MASTER; exatamente 1 → UNITÁRIO; nenhum →
  INCONCLUSIVO (nunca força UNITÁRIO por padrão otimista).
- **`magnata_os/classificacao/separacao_documental.py`** — engine
  `separar_por_carry_forward` (genérica, plugável via
  `IdentificadorDePagina`/`SituacaoPaginaSeparacao`) + estratégia
  concreta `estrategia_por_cnpj_cliente` (generaliza a parte CNPJ-exato
  de `construir_mapa_cliente`) + `texto_do_grupo` (reconstrói o filho
  para reentrada). Nunca importa `app.py`.
- **`magnata_os/classificacao/finalidade_comprovante_pagamento.py`** —
  `SinalFinalidadePagamento`, `OcorrenciaSinalFinalidade`,
  `hipoteses_de_finalidade_pagamento`, `sinais_textuais_de_finalidade_
  pagamento`. Reaproveita `resolver_tipo_documental` sem alteração.
- **`magnata_os/documental/modulo01/decisao_pos_classificacao.py`** —
  `proxima_etapa_sugerida_apos_classificacao`.

## Reentrada no motor (Fase F) — prova

`test_magnata_os_classificacao_separacao_documental.py::
test_filhos_separados_reentram_no_mesmo_motor_sem_pipeline_paralelo`:
um master de 2 clientes é separado; cada filho passa pelas MESMAS
`classificar_documento` → `hipoteses_textuais_de_classificacao` →
`resolver_tipo_documental` já usadas por qualquer documento —
nenhuma função nova "para filhos". Antes da separação, o documento
completo (2 entidades distintas) nunca resolve sozinho (CONFLITO) —
mesmo fail-safe genérico da Fase 2E anterior.

## Gaps reais registrados (não escondidos)

- **Fallback por nome normalizado** (`_normalizar_texto_busca` do
  legado) não portado — a estratégia de cliente cobre só CNPJ exato.
  Um cliente sem CNPJ na página (só nome) não é resolvido por esta
  versão.
- **Separação por CPF/colaborador** (`construir_mapa_cpf`) não
  portada — depende de `extrair_nome_funcionario`/`extrair_valores_
  holerite`, ainda só em `app.py`. A DETECÇÃO de múltiplos CPFs já
  funciona (genérica, mesma função), só a separação em si não.
- **OCR** (Fase J) — auditoria confirmou NENHUMA infraestrutura OCR
  reaproveitável no repositório (`grep -rniE "ocr|tesseract"` só
  retorna comentários "fora de escopo"/"fase futura"). Ponto de
  entrada futuro já preparado: qualquer produtor de texto por página
  (`Tuple[str, ...]`) alimenta as MESMAS funções (`analisar_estrutura_
  documento`, `classificar_documento`) sem nenhuma mudança de
  interface.
- **Estrutura geométrica real** (posição de página, `extract_tables()`
  de verdade) continua não implementada — os sinais "estruturais" hoje
  são contagem de entidades e presença de padrão textual, não layout.

## Cobertura do universo documental — atualização

Itens que MUDARAM de estado desde `motor-geral-compreensao-documental-
v1.md` (os 24 sem mudança relevante nesta missão continuam iguais —
matriz completa não repetida aqui):

| Item | Estado anterior | Estado agora | Motivo |
|---|---|---|---|
| Extrato Mensal por cliente | NECESSITA SEPARAÇÃO | RECONHECIMENTO PARCIAL (separação por CNPJ pronta; nome ainda não) | `separacao_documental.py` |
| FGTS por cliente | NECESSITA SEPARAÇÃO | RECONHECIMENTO PARCIAL (idem) | `separacao_documental.py` |
| Comprovante de Pagamento (genérico) | NECESSITA EVIDÊNCIA ADICIONAL | RECONHECIMENTO PARCIAL (salário/FGTS/DCTF-DARF/VR-VA/assiduidade/diárias resolvíveis por descrição específica; estrutura bancária isolada continua inconclusiva por design) | `finalidade_comprovante_pagamento.py` |
| Documento com múltiplos colaboradores | AINDA NÃO MODELADO (implícito) | NECESSITA SEPARAÇÃO (detecção pronta via CPF; separação em si é gap registrado) | `resolucao_master_documental.py` |

Nenhum item saiu do mapa; nenhum item retrocedeu de estado.

## Documentação relacionada

- `docs/decisoes/motor-geral-compreensao-documental-v1.md` — motor
  geral de TIPO_DOCUMENTAL (PR #94), reaproveitado sem alteração.
- `docs/decisoes/resolucao-semantica-fase2e-v1.md` — compositor geral.
