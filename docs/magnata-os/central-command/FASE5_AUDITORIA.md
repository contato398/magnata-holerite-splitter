# FASE 5 — auditoria completa do painel visual

**Etapa 7 da Central Command, 2026-08-22.**
**Nenhum código da Fase 5 foi integrado. Esta é auditoria e estratégia.**

| Campo | Valor |
|---|---|
| Branch | `origin/feat/magnata-os-documental-modulo01-fase5-painel` |
| Commit | `8eeb5aa60a6ab0aa655b91946271ef089a44407a` |
| Data | 2026-07-25 — parado há ~4 semanas |
| Volume | **50 arquivos, 4.868 linhas**, todas adições |
| Posição | 1 commit à frente, **77 atrás** de `main` |

---

## 1. Objetivo original

Painel operacional da esteira documental do Módulo 01 — visualizar
documentos, lotes, bloqueios, ações humanas e itens parados. É a
interface que faltava para a esteira que as Fases 1–4 construíram.

---

## 2. Stack — o achado que muda a avaliação de risco

**Vanilla JavaScript, ES modules, sem build.**

| Verificação | Resultado |
|---|---|
| `package.json` | ❌ não existe |
| Vite / Webpack / tsconfig | ❌ nenhum |
| Dependência npm | ❌ nenhuma |
| Framework | ❌ nenhum — DOM puro |
| Como roda | `python -m http.server --directory frontend` |
| Harness de teste | Próprio, ~120 linhas, **sem dependência** |

Isso é relevante: **não há cadeia de dependências para envelhecer.**
Um frontend com `package.json` parado 4 semanas costuma ter dezenas de
pacotes desatualizados e vulnerabilidades. Aqui não há o que apodrecer —
o custo real de recuperação é muito menor do que "50 arquivos parados"
sugere.

---

## 3. Componentes

| Bloco | Arquivos | Conteúdo |
|---|---|---|
| `src/api/` | 4 | `contracts.js`, `errors.js`, `autorizacao.js`, `mockAdapter.js` — espelham os contratos Python da Fase 4 |
| `src/components/` | 10 | `DocumentoCard`, `EsteiraBoard`, `EsteiraColuna`, `Filtros`, `Header`, `Sidebar`, `Paginacao`, `ResumoCards`, `PainelDetalheDocumento`, `PainelDetalheLote` |
| `src/views/` | 6 | `Dashboard`, `Documentos`, `Bloqueios`, `AcoesHumanas`, `Parados`, `viewHelpers` |
| `src/state/` | 2 | `store.js`, `filtros.js` |
| `src/utils/` | 7 | `dom`, `format`, `icons`, `debounce`, `prioridade`, `responsive` |
| `src/data/` | 1 | `mockData.js` — **toda a fonte de dados** |
| `styles/` | 3 | `tokens.css`, `base.css`, `components.css` |
| `tests/` | 12 | harness próprio + 11 suítes |

---

## 4. Classificação por bloco

| Bloco | Classe | Justificativa |
|---|---|---|
| `styles/` (tokens, base, components) | ✅ **REAPROVEITAR** | Identidade visual oficial já está em `main` (`frontend/assets/brand/`). CSS puro não envelhece |
| `src/utils/` | ✅ **REAPROVEITAR** | Funções puras, testadas, sem acoplamento |
| `src/components/` | ✅ **REAPROVEITAR** | DOM puro; dependem só de `utils` e do contrato |
| `src/state/` | ✅ **REAPROVEITAR** | Store simples, testado |
| `src/views/` | ✅ **REAPROVEITAR** | Consomem componentes + store |
| `src/api/contracts.js`, `errors.js` | ⚠️ **PRECISA DE DECISÃO** | Espelham os contratos Python da Fase 4. **Precisam ser reconferidos** contra `magnata_os/documental/modulo01/api/contratos.py` em `main` hoje — divergência silenciosa é o risco |
| `src/api/mockAdapter.js` + `src/data/mockData.js` | 🟡 **REAPROVEITAR como fixture** | Vira base de teste quando o adapter real existir. Não é código descartável |
| `src/api/autorizacao.js` | ⚠️ **PRECISA DE DECISÃO** | O próprio doc declara: *"o seletor de perfil no cabeçalho é só um mock visual"*. **Não é autenticação.** Publicar assim seria controle de acesso falso |
| `tests/` (12 arquivos) | ✅ **REAPROVEITAR** | Harness sem dependência; roda em qualquer navegador |
| `.claude/launch.json` | ❌ **SUPERADO** | Config de ambiente de uma sessão. Fora de `ALLOWED_PATHS` |
| `MAGNATA_OS_DOCUMENTAL_MODULO01_FASE5.md` | ✅ **REAPROVEITAR** | Documento da fase, honesto sobre limites |

**Nenhum bloco classificado como REFAZER.** O código não apodreceu.

---

## 5. Os dois bloqueios reais de integração

### 5.1 Governança — 49 de 50 arquivos são barrados

Verificado mecanicamente contra `.magnata/patterns.sh`:

- **`ALLOWED_PATHS`: 1 permitido, 49 bloqueados.** `^frontend/` não está
  na lista — só `frontend/CLAUDE.md` (protegido) e
  `frontend/assets/brand/` (protegido).
- **`is_authorized_branch()`: NÃO.** Prefixo `feat/` exige entrada exata
  na enumeração, e essa branch não tem.

✅ **Nenhum arquivo protegido é tocado** — nem `frontend/CLAUDE.md`, nem
`frontend/assets/brand/`, nem `app.py`, nem migrations.

**Consequência:** integrar a Fase 5 exige **primeiro** uma decisão de
governança — adicionar `^frontend/` (ou caminhos exatos) a
`ALLOWED_PATHS`. Não é detalhe de forma: é o gate que impediria o merge.

### 5.2 A API que o painel consumiria não está exposta

`magnata_os/documental/modulo01/api/` existe em `main` (`handlers.py`,
`contratos.py`, `autorizacao.py`, `filtros.py`, `erros.py`,
`serializacao.py`) — mas é **Python puro, sem nenhuma rota HTTP
registrada**. Nada em `app.py` referencia o Módulo 01.

Ou seja: **o painel não tem o que consumir.** Por isso ele roda 100% de
`mockData.js` — e por isso os "Próximos passos" do próprio documento
começam com *"construir `api/client.js` (fetch real contra a API HTTP da
Fase 4, quando ela for exposta)"*.

🔗 A branch `fix/adr-modulo01-http-wiring` é exatamente a decisão que
falta — e também está parada.

---

## 6. Limitações declaradas pelo próprio autor

Registradas com honestidade no documento da fase, não descobertas aqui:

- Sem persistência de estado entre recarregamentos.
- `renderShell()` reconstrói sidebar/header a cada mudança de estado —
  reemite `GET` dos SVGs de marca repetidamente.
- `EsteiraBoard` carrega até 200 documentos de uma vez — não escala para
  milhares.
- Filtros populados a partir da página carregada, não de lista canônica.
- **Sem autenticação real, sem HTTP real, sem deploy.**

---

## 7. Riscos

| Risco | Severidade |
|---|---|
| Contratos JS divergirem dos contratos Python sem ninguém notar | 🟠 Alto — nada verifica isso hoje |
| `autorizacao.js` ser confundido com controle de acesso real | 🔴 **Crítico se publicado** — é mock visual |
| 77 commits de defasagem | 🟢 Baixo — não toca nada que `main` mudou |
| Envelhecimento de dependências | 🟢 **Nulo** — não há dependências |
| Perda da branch | 🟠 Alto — 4.868 linhas em cópia única |

---

## 8. Esforço de recuperação

| Etapa | Esforço |
|---|---|
| Rebasear sobre `main` | 🟢 Baixo — não conflita |
| Ajustar `ALLOWED_PATHS` | 🟢 Baixo — mas é decisão |
| Reconferir contratos JS × Python | 🟡 Médio — leitura comparativa |
| Expor a API por HTTP | 🔴 Alto — depende da ADR parada |
| Autenticação real | 🔴 Alto — fase própria |

**Para ter o painel rodando com dado mockado: baixo.**
**Para ter o painel útil com dado real: alto**, e depende de duas
decisões que não são de frontend.

---

## 9. Valor de negócio

O `RISKS.md` registra como lacuna estrutural: **"não existe painel de RH
— o acompanhamento é consulta manual ao Airtable"**. A Fase 5 é o
protótipo mais próximo disso que existe.

Mas atende a esteira do **Módulo 01**, que não está em produção. O painel
que o RH precisa **hoje** é sobre assinaturas e envios — que vivem no
legado `app.py`. **São coisas diferentes**, e tratá-las como a mesma
seria erro de escopo.

---

## 10. Estratégia de recuperação — proposta, não executada

**Ordem sugerida, cada passo com valor próprio:**

1. **Preservar** — rebasear sobre `main` e manter a branch viva. Custo
   quase zero, elimina o risco de perda.
2. **Decidir `ALLOWED_PATHS`** — sem isso nada de `frontend/` entra.
   Decisão de governança, não de código.
3. **Reconferir contratos JS × Python** — leitura comparativa contra
   `api/contratos.py`. Barato e revela divergência antes de ela custar.
4. **Mesclar como protótipo mockado, explicitamente rotulado** — entra
   como demonstração navegável, não como ferramenta operacional.
   ⚠️ Condição inegociável: `autorizacao.js` marcado como mock visual
   **na própria interface**, não só no documento.
5. **Só então** decidir a fiação HTTP (`fix/adr-modulo01-http-wiring`) e
   a autenticação real — fases próprias.

**O que NÃO fazer:** mesclar e deixar parecer operacional. Um painel com
seletor de perfil que não autentica nada, mostrando dado mockado, é pior
do que não ter painel — cria confiança onde não há garantia.
