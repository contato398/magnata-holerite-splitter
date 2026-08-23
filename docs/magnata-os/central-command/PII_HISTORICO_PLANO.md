# PII no histórico do Git — plano de saneamento

**Etapa 11 da Central Command, 2026-08-23.**
**Levantamento somente leitura. Nada foi reescrito, forçado ou apagado.**
**Nenhum valor de dado pessoal é reproduzido neste documento.**

> Este documento existe porque o PR #38 resolveu **metade** do problema.
> A árvore atual está limpa; o histórico e as outras branches, não.

---

## 1. O que foi medido

Rastreei **3 alvos reais** — 2 CPFs com dígito verificador válido e
1 nome próprio de funcionário — recuperando os valores dos *blobs*
anteriores à correção e usando-os apenas como chave de busca. **Os
valores nunca foram impressos, gravados nem versionados.**

### 1.1 Correção declarada de um erro meu

A primeira varredura acusou **42 de 42** pontas de branch contaminadas,
incluindo `origin/main`. Estava errado: meu heurístico de "nome próprio"
(linha em maiúsculas com 3+ palavras) capturou a declaração de variável
`TEXTO_CARTAO_PONTO_REAL = """`. Refeito com o alvo correto — a linha
exata removida no commit da sanitização.

**O número certo é 40 de 42.** Registro o erro porque um falso positivo
que inflava o alarme é tão perigoso quanto um falso negativo: ambos
destroem a confiança no detector.

---

## 2. Onde o dado ainda está alcançável

| Local | Estado |
|---|---|
| **`origin/main`** | ✅ **LIMPA** — árvore atual sem nenhum dos 3 alvos |
| `origin/fix/lgpd-cpf-real-em-codigo` | ✅ limpa (é a branch da correção) |
| **Outras 40 pontas de branch remota** | 🔴 **CONTAMINADAS na árvore atual** |
| **Histórico de `main`** | 🔴 alcançável por `git log -S`, `git show`, `git blame` |

### 2.1 Isto é pior do que "só o histórico"

Nas 40 branches o dado não está no passado — está no **arquivo atual**
daquela branch. Um `git checkout` em qualquer uma delas materializa o CPF
real no disco. Não é preciso arqueologia.

### 2.2 Arquivos envolvidos — 4

| Arquivo | Alcance |
|---|---|
| `src/sync_new_employees.py` | 39 branches |
| `test_leitura_ponto.py` | 40 branches |
| `test_folha_ponto_v2_21.py` | 39 branches |
| `docs/historico/automacao_cadastro_holerite_sync_new_employees.md` | 1 branch (`fix/recibos-outros-documentos`) |

O 4º é o mais fácil de esquecer: entrou por um commit **documental**, não
de código, e por isso não aparece em nenhuma auditoria focada em `src/`.

### 2.3 Commits de origem — referência técnica

| Commit | Data | Papel |
|---|---|---|
| `20ddbde` | 2026-07-09 | **Introduz os 3 alvos.** Commit de funcionalidade (`v2.93`, diagnóstico 12x36) |
| `1027fc8` | 2026-07-23 | Propaga 1 CPF para documentação histórica |
| `a988fe9` | 2026-08-22 | Remove os CPFs (PR #38) |
| `b12d94d` | 2026-08-23 | Remove o nome (lacuna que o #38 deixou) |

---

## 3. Impacto de cada caminho — nenhum executado

### 3.1 ⭐ Opção recomendada: **saneamento por avanço, não por reescrita**

Levar as branches vivas adiante a partir de `main` — que já está limpa —
e aposentar as mortas, **sem reescrever nada**.

| | |
|---|---|
| **Como** | Para cada branch que ainda carrega trabalho útil: rebase/merge sobre `main` limpa. Para as demais: fechar o PR e arquivar a branch |
| **Impacto** | Nenhuma reescrita, nenhum force push, nenhuma URL de PR quebrada |
| **Risco** | 🟢 **Baixo.** Operações normais de Git, reversíveis |
| **Rollback** | Trivial — nada foi destruído |
| **Resolve** | As 40 pontas contaminadas |
| **NÃO resolve** | O histórico de `main` (`20ddbde` continua alcançável) |

### 3.2 `git filter-repo` — reescrita de histórico

| | |
|---|---|
| **Impacto** | **Todo SHA a partir de `20ddbde` muda.** ~1 mês de histórico |
| **Quebra** | Todo link `commit/<sha>`; a rastreabilidade de PRs mesclados; os 13 `.gitblob` de autorização de `app.py`, que **casam por hash de conteúdo** |
| **Risco** | 🔴 **Alto.** Exige force push em `main` e em todas as branches |
| **Rollback** | Só por backup completo **anterior**, feito antes e verificado |
| **Resolve** | O histórico — o único caminho que resolve |
| **Gate** | 🔴 `CLAUDE.md` §12-I: reescrever histórico **e** force push **e** operação destrutiva. Três gates de uma vez |

⚠️ **Ponto que costuma passar batido:** o GitHub **não apaga** os objetos
antigos por conta do force push. Commits ficam alcançáveis por URL direta
até um `gc` do lado do servidor, que só o suporte executa. **Force push
não é, sozinho, a exclusão do dado.**

### 3.3 Não fazer nada além do #38

| | |
|---|---|
| **Impacto** | A árvore atual está limpa; quem clona `main` hoje não recebe PII no working tree — mas recebe **o histórico inteiro** |
| **Risco** | 🟠 O dado permanece acessível a qualquer pessoa com acesso de leitura |
| **Quando é aceitável** | Se o repositório for **privado**, com acesso restrito e registrado, e a Direção aceitar o risco **por escrito** |

---

## 4. Forks, clones e caches — o limite honesto

| Vetor | Situação |
|---|---|
| Forks | **Não verificado** — precisa de checagem na interface do GitHub |
| Clones locais | 🔴 **Inalcançáveis por qualquer ação no servidor.** Quem clonou, tem |
| PRs antigos | O diff de um PR mesclado exibe o conteúdo na interface, independente do estado da branch |
| Caches/CI | Artefatos de execuções antigas podem conter o dado |

🔴 **Nenhuma reescrita alcança um clone que já existe.** Isto não é
argumento contra sanear — é o motivo pelo qual sanear **não substitui**
a avaliação de exposição real.

---

## 5. Rotação de segredo — não se aplica

Os 3 alvos são **dado pessoal**, não credencial. Não há o que rotacionar:
um CPF não pode ser trocado. É exatamente por isso que a exposição de PII
é mais grave que a de um token — **um token você revoga; um CPF, não.**

⚠️ **Item separado, não coberto por este plano:** a URL do webhook do
Make.com está em texto claro dentro de uma automação do Airtable
(AT-13). **Essa** é credencial e **é** rotacionável. Não está no Git e
não é tocada por nenhuma opção acima.

---

## 6. Comunicação necessária

| Quem | O quê |
|---|---|
| **Direção** | Que houve exposição de PII em repositório versionado, por quanto tempo, e qual opção foi escolhida |
| **Quem tenha clone local** | Se houver reescrita: descartar o clone e clonar de novo. Um `git pull` sobre histórico reescrito **reintroduz** os commits antigos |
| **Titular do dado** | ⚠️ **Avaliação jurídica, não técnica.** A LGPD prevê comunicação ao titular e à ANPD em incidente com risco relevante. **Não classifico isso**, e não defino prazo |

---

## 7. Gate humano — o que trava cada caminho

| Ação | Gate |
|---|---|
| Rebase das 40 branches sobre `main` | 🟡 Normal — mas apagar branch é gate (`CLAUDE.md` §9) |
| `git filter-repo` | 🔴 Reescrita + force push + destrutivo |
| Force push em `main` | 🔴 Explicitamente vedado por §12-I |
| Apagar branch | 🔴 §9: *"não apagar branch automaticamente"* |
| Contato com ANPD/titular | 🔴 Decisão jurídica da Direção |

---

## 8. Recomendação em uma frase

**Sanear por avanço (3.1) resolve 40 dos 41 focos sem risco nenhum e não
precisa de decisão difícil.** O 41º — o histórico de `main` — precisa de
uma decisão de risco que só a Direção pode tomar, e que deve ser tomada
sabendo que **nem a reescrita apaga o que já foi clonado.**
