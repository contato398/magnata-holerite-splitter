# ORQUESTRADOR — núcleos de negócio e arquitetura de fontes

**Etapa 5 da Central Command, 2026-08-22.**
**Natureza: registro de requisito e de evidência. Não é arquitetura
aprovada, não é ADR, não autoriza construir nada.**

---

## 1. Os oito núcleos — classificação por evidência

A visão macro do Magnata OS prevê a Central Command coordenando oito
núcleos de negócio. Abaixo, **o que a evidência sustenta hoje** — sem
inventar implementação e sem rebaixar o que existe.

**Legenda:** `EXISTE` (código real, em produção) · `EM CONSTRUÇÃO`
(código novo, testado, ainda não em produção) · `EXISTE FORA DESTE
REPOSITÓRIO` (opera, mas por outra ferramenta ou processo manual) ·
`PLANEJADO` (documentado, não construído) · `SEM EVIDÊNCIA`.

| Núcleo | Classificação | Evidência verificada | Módulo oficial correspondente |
|---|---|---|---|
| **Documental** | ✅ **EXISTE** + 🟡 **EM CONSTRUÇÃO** | Legado: `app.py` (split, geração, assinatura, distribuição), em produção. Novo: `magnata_os/documental/modulo01/` Fases 1-4 mescladas e testadas, **nada em produção** | 1 Ingestão · 2 Classificação · 6 Documentos |
| **RH** | ✅ **EXISTE** (legado) | Kit Admissão, vínculo trabalhista, `test_kit_admissao_identidade.py`. `Vínculo Trabalhista` é vocabulário oficial aprovado em 2026-07-22 | 3 Cadastro · 4 RH · 5 Ponto |
| **Operações** | ✅ **EXISTE** (difuso) | Filas de envio, disparo, reconciliação, Celery, `importacao_lote/`. Não é núcleo isolado — é consequência dos outros | 7 Distribuição · 9 Auditoria · 10 Plataforma |
| **Contábil/Fiscal** | ✅ **EXISTE** (parcial) | Remetentes DP/Fiscal (`docs/decisoes/remetentes-dp-fiscal.md`), `test_seguranca_rotas_dp_fiscal.py`, `test_competencia_fiscal.py`, rotas de guias e FGTS, pipeline fiscal `v2.67`/`v2.97` | 6 Documentos (guias, FGTS) — **sem módulo fiscal formal** |
| **Financeiro** | 🔍 **SEM EVIDÊNCIA no repositório** | Nenhum código de contas a pagar/receber, faturamento ou fluxo de caixa. **Mas a empresa opera** — logo, ou existe fora daqui, ou é aspiracional | — |
| **Comercial** | 🔍 **SEM EVIDÊNCIA no repositório** | `Contrato Comercial` é **vocabulário oficial aprovado** (Modelo Conceitual, 2026-07-22) — o conceito existe na arquitetura; a implementação, não | — (conceito aprovado, sem módulo) |
| **Marketing** | 🚫 **SEM EVIDÊNCIA** | Zero ocorrências do termo em qualquer `.md` ou `.py` do repositório | — |
| **Diretoria/BI** | 🚫 **PLANEJADO** | "Painel operacional" catalogado em `MAGNATA_OS_CAPACIDADES.md` §3.9, maturidade 2 (identificada, sem implementação). A Direção aparece como **autoridade decisória**, não como consumidora de painel | — |

### 1.1 Correção a uma leitura anterior

Rodadas anteriores classificaram **Comercial** como "zero, não aparece em
nenhum documento fundacional". **Isso estava errado** e fica corrigido
aqui: com a fundação resgatada, `Contrato Comercial` aparece no **Modelo
Conceitual aprovado pela Direção em 2026-07-22**, no topo da hierarquia
de Cliente. O conceito é oficial desde julho. O que não existe é código.

A evidência mudou porque a fonte estava fora de `main` — é exatamente o
tipo de erro que este PR existe para tornar impossível.

### 1.2 A pergunta que só a Direção responde

Para **Financeiro**, **Comercial**, **Marketing** e **Diretoria/BI** a
distinção que falta não é técnica:

> Esses núcleos **já operam fora deste repositório** (outro sistema,
> planilha, processo manual), ou são **aspiracionais** para o Magnata OS?

No primeiro caso, o trabalho é **integração** — mapear a fonte externa e
trazê-la para a Central Command como sistema de registro reconhecido. No
segundo, é **construção**, e entra no roadmap. São caminhos opostos, e
adivinhar seria decidir arquitetura em silêncio.

---

## 2. Divergência de taxonomia — registrada para ADR futura

Coexistem **três** recortes, todos com fonte real:

| Recorte | Fonte | Data | Situação |
|---|---|---|---|
| **9 módulos** | `MAGNATA_OS_ARQUITETURA.md` §2 | 2026-07-22 | ❌ **SUPERADO** pelo de 10 |
| **10 módulos** | `docs/magnata-os/MAGNATA_OS_MODULOS.md` v1.0 | 2026-07-25 | ✅ **VIGENTE** — acrescenta RH; os outros 8 mapeiam 1:1 |
| **8 núcleos de negócio** | Direção, nesta linha de trabalho | 2026-08 | ⚠️ **SEM ADR** |

Os dois primeiros têm sucessão resolvida e documentada. **O terceiro
não.** Os 8 núcleos são recorte de **negócio**; os 10 módulos são recorte
**funcional**. Sobrepõem-se parcialmente e **não são intercambiáveis**.

**Isto não é resolvido aqui.** Adotar os 8 núcleos como taxonomia oficial
é decisão arquitetural e exige ADR — `CLAUDE.md` §2. Enquanto não houver
ADR, **os 10 módulos continuam sendo a taxonomia vigente**, e os 8
núcleos são visão de destino.

---

## 3. Arquitetura de fontes de verdade — fronteiras

Registro de **fronteira**, para que nenhuma camada seja usada como se
fosse outra. Nada aqui autoriza instalar, migrar ou conectar.

| Camada | É verdade sobre | **Não** é verdade sobre | Estado |
|---|---|---|---|
| **Central Command** | Memória, decisão, estado consolidado, proveniência | Código atual, dado operacional, execução | ✅ Existe (este PR) |
| **GitHub** | Versionamento, evolução técnica, quem mudou o quê | Se o código está em produção | ✅ Existe |
| **Graphify** | Mapa automático de código, dependências, acoplamento | Decisão de negócio, dado de cliente | 🚫 **Não instalado** |
| **Produção (Render)** | Execução real — o que de fato roda | Intenção, decisão | ✅ Existe · 🔍 não verificável desta sessão |
| **Airtable / bancos** | Dado operacional (colaborador, cliente, documento) | Arquitetura, decisão | ✅ Airtable ativo · Postgres 🚫 não provisionado |
| **Gmail / WhatsApp** | Eventos e canais de entrada e saída | Estado consolidado | ✅ Existem |
| **Arquivo seguro** | Fonte histórica sensível com PII | Memória pública | 🚫 **Não existe** — requisito em [`FORA_DO_GIT.md`](FORA_DO_GIT.md) §7 |

### 3.1 Graphify — o que precisa ser confirmado antes

Não instalado, nenhuma referência no repositório. Antes de qualquer
decisão de adoção, três perguntas sem resposta hoje:

1. **O que extrai de fato** — grafo de imports? schema de banco? chamadas
   HTTP? A utilidade muda completamente conforme a resposta.
2. **Roda local e read-only?** Se enviar código para serviço externo,
   cruza o gate de escrita externa de `CLAUDE.md` §6.
3. **Onde o resultado é versionado?** Arquivo gerado no repositório
   (auditável) ou serviço externo (não auditável)?

**Onde faria sentido, se as respostas forem favoráveis:** substituir por
verificação mecânica o que esta consolidação fez à mão — conferir se
`MAGNATA_OS_MODULOS.md` e a matriz arquitetural ainda descrevem o código
real, e verificar automaticamente a regra "domínio não importa
Flask/driver/Airtable", hoje confirmada por `grep`.

**Onde não substitui nada:** auditoria de branch não mesclada, documento
fantasma, decisão de negócio. Isso é raciocínio sobre histórico e texto,
não estrutura de código.

---

## 4. O que a arquitetura documental de hoje já garante ao amanhã

Verificado nesta fase, não presumido:

1. **Proveniência em cada arquivo resgatado** — origem, branch, HEAD, PR.
   Uma fonte automática futura pode conferir contra o Git.
2. **Separação entre memória e dado operacional já é prática** —
   `HISTORICO.md` referencia registros sensíveis por blob SHA sem expor
   conteúdo. É o padrão que a camada segura vai formalizar.
3. **Fronteiras nomeadas** (§3) — nenhuma camada é usada como se fosse
   outra.
4. **Distinção preservada em todo o corpo documental:** discutido ≠
   autorizado ≠ implementado ≠ testado ≠ integrado ≠ implantado ≠
   funcionando em produção.
5. **Nada foi convertido de plano em realidade** — os três documentos com
   divergência conhecida levam nota visível, e plano continua rotulado
   como plano.

O que **não** está garantido: atualização automática. Hoje a Central
Command é regenerada por auditoria manual e fica desatualizada assim que
o código muda. Automatizar isso é a próxima fase — e é o que transforma
memória em orquestração.

---

## 5. Etapa 6 — correções por evidência nova (2026-08-22, pós-merge)

Duas afirmações das seções acima **estão superadas**. Registradas aqui,
não reescritas.

### 5.1 Financeiro e Comercial existem — fora deste repositório

A §1 classificou **Financeiro** e **Comercial** como `SEM EVIDÊNCIA`.
**Superado.** A leitura do schema do Airtable (31 tabelas, sem nenhum
registro, sem PII) encontrou:

| Núcleo | Onde estava | Classificação corrigida |
|---|---|---|
| **Financeiro** | `Pagamentos` · `Recebimentos` · `Despesas` · `Patrimônio` | ✅ **EXISTE FORA DESTE REPOSITÓRIO** |
| **Comercial** | `Clientes` (36 campos) · `Locais` | ✅ **EXISTE FORA DESTE REPOSITÓRIO** |
| **Contábil/Fiscal** | + `Contabilidade Mensal` · `Certidões` · `FGTS Digital` · `Escritórios Contabilidade` | ✅ **EXISTE** — mais amplo do que o registrado |
| **Marketing** | nenhuma tabela | 🚫 `SEM EVIDÊNCIA` — **confirmado nas duas fontes** |
| **Diretoria/BI** | `DIA HOJE` · `DIA QR CODE` | 🔍 `A CONFIRMAR` — parecem painéis operacionais |

**Por que eu errei:** procurei evidência só no código. Os núcleos de
negócio da Magnata não são código — são planilhas operacionais no
Airtable. É o mesmo padrão de erro da fundação documental: a fonte
existia, fora do lugar onde eu olhei.

**Consequência de arquitetura:** para Financeiro e Comercial o trabalho
é **integração**, não construção. Detalhe em
[`AIRTABLE_DESACOPLAMENTO.md`](AIRTABLE_DESACOPLAMENTO.md).

### 5.2 Graphify não é analisador estático

A §3 descreveu o Graphify como ferramenta de "mapa automático de código".
**Incompleto.** É extrator de grafo de conhecimento com **backend de
LLM**, que *também* tem um modo code-only por AST. A distinção é
crítica porque o modo padrão **envia conteúdo para um provider externo**.
Avaliação com POC executada em [`GRAPHIFY.md`](GRAPHIFY.md).

---

## 6. Arquitetura de fontes do Grande Orquestrador

Para cada fonte: que verdade fornece, autoridade, frequência, risco e
**como a Central Command reage quando há divergência**.

| Fonte | Verdade que fornece | Autoridade | Frequência | Risco | Reação da Central Command à divergência |
|---|---|---|---|---|---|
| **Direção da Magnata** | Decisão de negócio, vocabulário oficial, prioridade | 🥇 **Máxima — vence todas** | Evento | Decisão não registrada se perde | Registra e **para**. Nenhuma outra fonte a contradiz. `DEC-ENT-010/011/012` seguem pendentes há um mês |
| **Código em `main`** | O que o sistema **faz** | 🥈 Alta — vence plano e documento | Por commit | Merge não feito = conhecimento fantasma (PR #12) | **Código prevalece sobre plano**; divergência é registrada, nunca corrigida em silêncio |
| **Produção (Render)** | O que **executa de fato** | 🥇 Máxima sobre execução | Contínua | Divergir de `main` sem ninguém ver | `main` ≠ produção é **incidente**, não nota de rodapé. Hoje **não verificável** desta sessão |
| **GitHub** | Versionamento, autoria, PRs, CI | 🥈 Alta sobre histórico técnico | Por evento | Branch apagada = perda | `merged_at`, nunca `merged`. Branch fora de `main` é risco até provado o contrário |
| **Airtable** | Dado operacional real | 🥇 Máxima sobre dado; **nenhuma** sobre arquitetura | Contínua | Regra de negócio em fórmula não versionada | Dado do Airtable vence memória. **Regra** dentro do Airtable é dívida a extrair, não fonte a obedecer |
| **Graphify** *(se adotado)* | Foto estrutural do código | 🥉 Média — derivada, nunca origem | Sob demanda | 58% das arestas são inferência | Só `EXTRACTED` sustenta afirmação. Contradiz o código? **O código vence** |
| **Gmail / Apps Script** | Eventos de entrada | Média sobre "chegou" | Contínua | Maturidade 3, risco alto declarado | Documento sem evento é lacuna a investigar |
| **WhatsApp / Evolution** | Eventos de saída | Média sobre "foi enviado" | Contínua | Não prova leitura nem clique | **"Enviado" nunca é "recebido" nem "lido"** |
| **Memória sensível** *(não existe)* | Fonte bruta com PII | Alta sobre fato histórico | Evento | Não existe hoje | Referencia por identificador, **nunca** copia conteúdo. [`MEMORIA_SENSIVEL.md`](MEMORIA_SENSIVEL.md) |
| **Central Command** | Estado consolidado, decisão, proveniência | Alta sobre **memória**; nenhuma sobre execução | Por auditoria | Envelhece em silêncio | **Nunca vence uma fonte primária.** Divergiu? A Central Command está errada e é regenerada |

### 6.1 Regra de arbitragem, em uma linha

> **Direção > produção (execução) > código em `main` > dado operacional
> > memória consolidada > derivados.**
> A Central Command **nunca** ganha de fonte primária. Ela registra a
> divergência e é corrigida por ela.

### 6.2 O que falta para o Orquestrador existir de fato

| Peça | Estado |
|---|---|
| Memória, decisão, proveniência | ✅ **Existe** — em `main` desde o merge de `9f8a53f` |
| Verdade sobre versionamento | ✅ Existe (GitHub) |
| Verdade sobre dado operacional | ✅ Existe (Airtable) |
| Verdade sobre estrutura do código | 🟡 Possível — Graphify com restrições |
| Verdade sobre execução real | 🔴 **Não verificável** de sessão remota — rede bloqueada |
| Memória sensível | 🔴 **Não existe** |
| **Atualização automática** | 🔴 **Não existe** — hoje toda a Central Command é regenerada por auditoria manual |

**A peça que falta e define a próxima fase é a última.** Memória
consolidada à mão é documentação; memória que se atualiza sozinha é
orquestração.
