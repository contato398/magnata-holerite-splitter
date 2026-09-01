# Wiring Real de Vínculo V1 em Modo Shadow

Documento de decisão da missão "WIRING REAL DE VÍNCULO V1 EM MODO
SHADOW". Contexto: PR #114 (atomicidade da transferência) mergeado; o
mecanismo de captura está completo e testado, mas nunca alimentado por
dado real -- esta missão conecta a metade que TEM fonte confiável
(vínculo) ao extrator já existente, sempre em modo shadow (repositório
sintético/efêmero, nunca produção). Branch: `fix/wiring-vinculo-shadow-v1`.

## FASE 1 — Arqueologia de wiring

Auditado com leitura completa (não amostral) de
`src/sync_new_employees.py` e da função `app.py::extrair_dados_rescisao`:

```
PONTO_ADMISSAO=src/sync_new_employees.py::processar_holerite_record -> extrair_dados_holerite (regex puro) -> criar_ou_completar_funcionario (escrita Airtable real, SEM gate de confirmação humana -- diferente do fluxo de Kit Admissão de app.py)
PONTO_RESCISAO=app.py::_processar_rescisao_stub -> extrair_dados_rescisao (regex puro, DENTRO de app.py) -> sempre cria Pendência, NUNCA altera Status automaticamente (gate de confirmação humana explícito, documentado no próprio código: "inativar alguém por engano tem custo alto")
IDENTIDADE_CANONICA_ADMISSAO=CPF (casado via sync_new_employees.buscar_funcionario_por_cpf, mesmo mecanismo do resto do legado)
IDENTIDADE_CANONICA_RESCISAO=CPF (casado via app.py::buscar_funcionario_por_cpf, mesmo padrão)
DATA_EFETIVA_ADMISSAO=Sim -- "Data de Admissão" extraída do header do holerite real, string DD/MM/AAAA
DATA_EFETIVA_RESCISAO=Sim -- "Data de rescisão/desligamento" extraída do TRCT real, mesma disciplina
EXISTE_SERVICO_REUTILIZAVEL=Sim para os DOIS extratores -- ambos já são funções PURAS (regex, zero I/O): extrair_dados_holerite (sync_new_employees.py) e extrair_dados_rescisao (app.py)
APP_PY_PRECISA_SER_MODIFICADO=Não para admissão. Para rescisão, reaproveitar o extrator exigiria IMPORTAR de app.py (nunca editá-lo) -- mesmo assim, viola a disciplina de decoupling já documentada em magnata_os/documental/importacao_lote/CLAUDE.md ("app.py é legado protegido... este módulo não cria dependência de import contra ele"). Gate mantido, não presumido.
SYNC_NEW_EMPLOYEES_PRECISA_SER_MODIFICADO=Não -- extrator já é público e puro; reutilizado por IMPORT (leitura, zero edição no arquivo)
```

**Achado adicional relevante**: o fluxo de admissão de
`sync_new_employees.py` **não tem gate de confirmação humana** (grava
direto quando `dry_run=False`) -- diferente do Kit Admissão de
`app.py` e do fluxo de rescisão, ambos gated. Isso não muda nada nesta
missão (meu wiring nunca escreve em lugar nenhum, shadow puro), mas é
um fato relevante registrado para a decisão futura de habilitar
produção.

## FASE 2 — Menor ponto de integração

Reuso por **import direto** da função pura já existente
(`src.sync_new_employees.extrair_dados_holerite`) -- nenhum
serviço/adapter/entrypoint novo criado para a extração em si; só o
módulo de composição (`wiring.py`) que costura extração + identidade
(injetada) + evento canônico. `sync_new_employees.py` **não foi
modificado** -- só importado (leitura).

**Rescisão: parada deliberada no gate, conforme instruído.**
`app.py::extrair_dados_rescisao` não foi importado nem reimplementado
-- a função de wiring equivalente (`construir_vinculo_encerrado_de_rescisao`)
**não foi criada nesta missão**. Ver "Não implementado" abaixo.

## FASE 3 — Shadow first

`wiring.construir_vinculo_iniciado_de_holerite(texto, resolver_colaborador_id)`
é uma função pura: recebe texto já extraído (nunca baixa PDF, nunca
acessa Airtable) e um `resolver_colaborador_id` INJETADO (Protocol
implícito, mesma disciplina de todo o projeto) -- nesta missão, sempre
um resolvedor sintético (dict CPF->id) nos testes, nunca uma chamada
Airtable real. O evento resultante é aplicado via
`captura.aplicar_vinculo_iniciado` contra `RepositorioAlocacaoSQLite`
(shadow, efêmero) ou `RepositorioAlocacaoPostgres` (só no container
efêmero de CI) -- nunca uma conexão de produção assumida
automaticamente em código algum.

## FASE 4 — Admissão (implementada e testada)

11 testes novos (SQLite) + 1 (Postgres real, CI): extração real via
texto sintético fiel ao formato documentado no próprio
`sync_new_employees.py`; CPF ausente/data ausente/colaborador não
identificado sempre levantam exceção explícita, nunca escolhem
candidato arbitrário; mesmo documento 2× e 2 documentos com a mesma
admissão são idempotentes; datas conflitantes levantam
`ConflitoTemporalEventoError`; falha do repositório + retry provados
com `monkeypatch`.

## FASE 5/6 — Rescisão: não implementada (gate) + fato documental × ação operacional

**Rescisão não implementada nesta missão** -- exatamente o gate
antecipado pela própria missão. `construir_vinculo_encerrado_de_rescisao`
não existe; nenhum atalho foi inventado (nem reimplementação de regex,
nem import de `app.py`).

**Princípio já preservado por desenho, não por código extra**: o
módulo `wiring.py` só constrói e aplica eventos de `vinculo_trabalhista`
-- nunca decide ativar/inativar Status no Airtable, nunca aciona
folha/FGTS/benefícios. Mesmo quando a rescisão for implementada (missão
futura), gerar `VinculoEncerrado` continuará sendo só um FATO TEMPORAL
registrado -- a AÇÃO OPERACIONAL (inativar o colaborador) permanece
exclusivamente do fluxo humano já existente e protegido no legado
(Pendência de confirmação de 1 clique).

## FASE 7 — Postgres real efêmero

`test_sequencia_admissao_documental_ate_readmissao_contra_postgres_real`
(CI): admissão documental (extrator real) → `VinculoIniciado` →
persistência real → encerramento (evento canônico direto, já provado
na missão anterior -- rescisão via documento fora do escopo) →
readmissão via novo documento sintético → novo vínculo. Dados 100%
sintéticos, nunca o CPF/nome de nenhum colaborador real da Magnata.

## FASE 10 — Duas revisões adversariais

**Primeira (identidade, datas, idempotência, readmissão, conflito,
fato documental × ação operacional, falha/retry):** identidade sempre
resolvida por injeção, nunca inferida; ausência de CPF/data sempre
levanta exceção específica antes mesmo de tentar construir o evento;
readmissão sempre cria vínculo novo (provado com documentos reais de
wiring, não só com chamada direta ao evento); nenhuma escolha
arbitrária em nenhum ponto; `wiring.py` nunca toca Status/folha/FGTS.

**Segunda (integração com legado, duplicação, acoplamento,
regressões, produção, segurança, readiness):** zero duplicação de
regex (import direto do extrator real); `sync_new_employees.py`
intocado; `app.py` intocado; suíte completa 1783 passed (1772 antes +
11 novos), mesmos 5 failed/34 errors pré-existentes, zero regressão;
zero escrita Airtable/produção em qualquer teste; acoplamento
transitivo a `flask`/`requests`/`pdfplumber` via o import do extrator
é um custo real, registrado explicitamente (não escondido) --
alternativa seria reimplementar regex (proibido) ou editar
`sync_new_employees.py` para promover a função (fora do escopo mínimo).

## Preservado

`app.py` intocado. `src/sync_new_employees.py` intocado (só importado).
Zero escrita Airtable. Zero produção. Zero dado real (CPF/nome
sempre fictícios em todos os testes). Zero deploy. Rescisão
permanece explicitamente gated, sem atalho.
