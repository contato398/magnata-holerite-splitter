# MEMÓRIA SENSÍVEL — requisito arquitetural

**Etapa 6 da Central Command, 2026-08-22.**
**Requisito, não implementação. Nada aqui foi construído, e nada deve
ser construído sem decisão própria.**

---

## 1. O problema, medido

A auditoria de LGPD desta linha de trabalho expôs uma lacuna
**estrutural**, não pontual. Em `docs/historico/`, 31 arquivos:

| Medida | Valor |
|---|---|
| Com CPF real de funcionário | **8** |
| Com nome completo real | **29** |
| Totalmente livres de dado pessoal | **2** |
| Pior caso num único arquivo | **51** candidatos a nome |

`CLAUDE.md` §6 é literal: dado pessoal **nunca** em commit. `git` não
esquece — versionamento distribuído e direito ao esquecimento são
tecnicamente incompatíveis.

**O resultado hoje é binário, e os dois lados são ruins:**

- versionar → viola §6 e a LGPD, de forma permanente e irreversível;
- não versionar → o conhecimento fica preso numa branch frágil, e
  branches deste repositório **são apagadas** (aconteceu nesta sessão).

Foi preciso escolher: preservamos a **lição** em
[`HISTORICO.md`](HISTORICO.md), livre de PII, e o **texto bruto** ficou
fora. Funcionou, mas foi trabalho manual e perdeu detalhe. Não escala.

---

## 2. Duas camadas, separadas por desenho

| | Memória canônica | Memória sensível |
|---|---|---|
| **Conteúdo** | Decisão, arquitetura, proveniência, lição | Fonte bruta com PII, registro nominal, evidência |
| **Onde** | Git (existe hoje) | 🚫 **Não existe** |
| **Quem lê** | Qualquer sessão, qualquer agente | Acesso restrito com trilha |
| **Retenção** | Permanente | Prazo definido, descarte executável |
| **Esquecimento** | Impossível (por desenho) | **Obrigatório** (por lei) |

A Central Command **já pratica** a ponte entre as duas de forma manual:
`HISTORICO.md` referencia cada registro sensível pelo **blob SHA**, sem
expor conteúdo. É esse padrão que a camada segura formalizaria.

---

## 3. O que precisa guardar

| Classe | Exemplo real deste projeto | Sensibilidade |
|---|---|---|
| Históricos operacionais | os 29 arquivos de `docs/historico/` | 🔴 CPF + nome |
| Documentos brutos | holerite, folha de ponto, contrato, rescisão | 🔴 Máxima |
| Evidências de assinatura | IP, CPF parcial, timestamp, hash do PDF | 🔴 Valor jurídico |
| Anexos de e-mail | tudo que entra pelo Apps Script | 🔴 Não classificado na entrada |
| Registros de disparo | CSVs de envio por WhatsApp | 🟠 Nome + telefone |
| Transcrições de sessão | conversas que geraram decisão | 🟡 Variável |

---

## 4. Requisitos mínimos

Derivados de regras que **já existem** no projeto — não inventados aqui.

1. **Fora do Git.** Não negociável (§1).
2. **Referenciável por identificador estável.** A memória canônica
   aponta para um registro sem expor conteúdo — como `HISTORICO.md` já
   faz por blob SHA.
3. **Trilha de acesso append-only.** `CLAUDE.md` §4: histórico é
   imutável. Quem leu, quando, para quê — nunca editável.
4. **Retenção e descarte explícitos.** Cada classe com prazo; descarte
   **executável**, não aspiracional. É a capacidade que o Git não tem.
5. **Sanitização na saída, não na entrada.** O dado entra íntegro e é
   mascarado conforme quem lê. Evita a escolha entre "perder a lição" e
   "expor a pessoa" — exatamente a escolha que esta fase teve que fazer.
6. **Criptografia em repouso e em trânsito**, com chave fora do
   repositório (§6 proíbe segredo em commit).
7. **Índice pesquisável sem expor conteúdo** — buscar "qual registro
   trata de colisão de identidade" sem devolver nome nem CPF.
8. **Idempotência por hash** (§4), como o Módulo 01 já faz.
9. **Falha nunca silenciosa** (§4): acesso negado é registrado, não
   mascarado como "não encontrado".

---

## 5. Onde encaixa na arquitetura

O Módulo 01 **já tem** as peças certas, desenhadas por contrato:

- `adapters/s3_armazenamento.py` — armazenamento de binário por
  interface, sem driver no domínio;
- `dominio.py` — `Documento` imutável, idempotência por SHA-256;
- migration `0003_trigger_eventos_append_only.sql` — histórico
  append-only **garantido por banco**, não por disciplina.

**A camada sensível não é um sistema novo — é uma configuração de
confidencialidade sobre o que já foi desenhado.** O que falta: a
política de acesso, a retenção, a sanitização na leitura e o vínculo
formal com a Central Command.

⚠️ Nada disso está ativo: nenhum bucket real conectado, Postgres não
provisionado.

---

## 6. O que NÃO fazer

- ❌ Mascaramento automático em massa como solução definitiva — foi
  avaliado e rejeitado nesta fase: com 29 arquivos e até 51 nomes num
  só, um escape vira violação permanente.
- ❌ Repositório privado como camada sensível — privado ainda é Git, e
  Git não esquece.
- ❌ Apontar ferramenta de indexação por LLM externo para o corpus
  sensível — ver [`GRAPHIFY.md`](GRAPHIFY.md) §4.
- ❌ Construir antes de decidir retenção. Sem prazo de descarte, é só
  outro lugar onde o dado nunca some.

---

## 7. Próximo passo — decisão, não código

A pergunta que destrava tudo é de negócio, não técnica:

> **Qual o prazo de retenção de cada classe de documento pessoal que a
> Magnata processa, e quem pode ler o quê?**

Sem isso, qualquer implementação é chute. Com isso, a arquitetura acima
vira especificação executável.

**Enquanto não existir:** os 29 históricos com PII continuam em
`origin/fix/recibos-outros-documentos`, commit `1027fc8`. **Não apagar
essa branch** — é a única cópia do registro bruto.
