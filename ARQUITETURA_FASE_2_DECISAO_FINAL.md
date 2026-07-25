# ARQUITETURA FASE 2 — DECISÃO FINAL (v2, corrigida)
## Revisão Cirúrgica Baseada em Fatos

**Data:** 2026-07-20
**Escopo:** Arquitetura mínima para classificação de documentos em Processar Arquivos
**Restrição:** Apenas decisão arquitetural. Nada implementado. ADD-ONLY. REUSE-FIRST.

---

## CORREÇÃO 0 — ACHADO NOVO QUE MUDA A CONTAGEM

Ao verificar reaproveitamento com mais rigor, apareceu uma cadeia de rastreamento
**já existente e já em produção** que elimina a necessidade de metade dos campos
propostos no relatório anterior:

```
Processar Arquivos.Arquivos 2 (fldLWSmK81i8jbtCG, link)
        ↓
Arquivos (tblRsvhz8oOcUqhkv)
   • Hash do Anexo (fldOB09YlKDEqKSFO)      → JÁ é a chave de idempotência (em uso: linha 5126 do app.py)
   • Emails Savian (fld2yYAHWe0smV5Bb, link) → aponta para o e-mail de origem
        ↓
Emails Savian (tblljRRrraXSipJd1)
   • MESSAGE ID (fldCCdUEMF3hlTngA)   → JÁ é o Gmail Message ID (em uso: F_EMAIL_MSGID, linha 5086)
   • Assunto (fld66diI0hksJE5PS)      → JÁ é o assunto do e-mail
   • Conteúdo (fldzi2kWBoT2kfEhL)     → texto do corpo do e-mail
```

**Consequência:** Gmail Message ID, Assunto do E-mail e Chave de Idempotência **já
existem e já estão em uso em produção**. Não serão criados campos novos para isso.
Gmail Attachment ID não é necessário: o PDF já está fisicamente anexado em
`Arquivos.Attachments`, não é preciso guardar o ID do anexo do Gmail para
reprocessar.

**Remetente ("De"):** não existe campo dedicado em Emails Savian (apenas Name,
Status, Assunto, Conteúdo, Arquivos, MESSAGE ID, Created, Log/Erro). Não é
crítico para a Fase 2 — Assunto e Conteúdo já cobrem essa necessidade como
sinal de classificação. Fica como lacuna conhecida, não bloqueante.

---

## CORREÇÃO 1 — CAMPO "Tipo" (fldJWy7givUDs1aCl) ESTAVA OCIOSO

Processar Arquivos tem DOIS campos de classificação, não um:

| Campo | Field ID | Opções atuais | Uso no código |
|-------|----------|----------------|----------------|
| Tipo | fldJWy7givUDs1aCl | Holerites, Férias, Extrato-Caixa, Extrato-Sicoob, Contratação ou Rescisão, Despesas de Combustível, Extrato Mensal Funcionários, FGTS Digital - Guia Detalhada, Folha Ponto | **Nunca referenciado por Field ID em app.py nem tarefas_processar_pdf.py** — campo ocioso |
| Tipo de Documento | fldvkOVlwCMywGTES | Holerite, Folha de Ponto, Contrato de Experiência, Contrato de Trabalho, Férias, FGTS, Guia, Boleto, Nota Fiscal, Outro, Não Identificado, Ficha de Registro, Rescisão | **Usado por `F_PROC_TIPO_DOC`** — MAS o hotfix grava também códigos técnicos aqui: `UPLOAD_FAILED`, `PDF_URL_MISSING`, `PDF_DOWNLOAD_FAILED`, `EMPLOYEE_NOT_IDENTIFIED`, `PROCESSING_ERROR` |

### Risco identificado (não corrigir agora, apenas registrar)
`Tipo de Documento` está contaminado: mistura categoria real de documento com
código de erro técnico do hotfix. Como `typecast=true` cria opções novas
automaticamente ao gravar, esse campo hoje tem, dentro do Airtable, opções que
não são categorias de documento (são erros). **Não vou propor mudar isso agora**
— alterar o que o hotfix grava ali seria mexer no fluxo assíncrono estabilizado,
fora de escopo. Fica registrado como débito técnico para uma fase futura de
limpeza.

### Decisão
`Tipo` (fldJWy7givUDs1aCl) está ocioso e suas opções já cobrem boa parte da
lista pedida (Holerites, Férias, Extrato, FGTS, Folha Ponto, Contratação/Rescisão).
**Reaproveitar este campo para Categoria Documental.** Não renomear o campo no
Airtable — usar seu Field ID internamente como "categoria documental". Opções
que faltam (DARF/DCTFWeb, VR, VA, Comprovante de Salário, Certidão, Outro) são
adicionadas automaticamente na primeira gravação via `typecast=true` — isso não
é uma alteração de schema feita por nós, é o comportamento padrão do Airtable
ao gravar um valor novo num singleSelect. Nenhuma ação manual no Airtable é
necessária para isso.

---

## CORREÇÃO 2 — "Funcionário(s) Vinculado(s)" JÁ EXISTE EM ENVIOS

O relatório anterior recomendava **criar** um campo de link para Funcionário em
Envios de Documentos. Isso estava errado — o campo já existe:

```
Envios de Documentos.Funcionário(s) Vinculado(s) (fldcm9bAj13phGQqS) — multipleRecordLinks → Funcionários
```

Já é usado em produção (`app.py:5771, 7958`, etc.). **Nenhum campo de
Funcionário precisa ser criado em Envios.**

---

## CORREÇÃO 3 — SEM EXCLUSÃO, RENOMEAÇÃO OU CONSOLIDAÇÃO NESTA FASE

O relatório anterior recomendava remover "Folha Ponto copy" (3x em
Funcionários) e consolidar "Email Contador 1/2/3" (em Clientes e Envios).
**Essa recomendação é retirada.** Fase 2 é ADD-ONLY e REUSE-FIRST. Esses campos
permanecem intocados, independentemente de estarem em uso ou não. Isso não
bloqueia nada da Fase 2 — são tabelas diferentes (Funcionários, Clientes), sem
relação com o fluxo de classificação em Processar Arquivos.

---

## A. LISTA FINAL EXATA — CAMPOS DE PROCESSAR ARQUIVOS (tblXaLXvGJMyFOayc)

| Nome do campo | Tipo | Já existe? | Field ID | Ação | Obrigatório |
|---|---|---|---|---|---|
| Status | singleSelect | Sim | fldvN9T5MiuKZGDi0 | REAPROVEITAR | Agora (já em uso, hotfix) |
| Arquivos | multipleAttachments | Sim | fldQtevv6jAwKVdEN | REAPROVEITAR | Agora (já em uso) |
| Data Processo | dateTime | Sim | flddNzmqp1Im1D02m | REAPROVEITAR | Agora (já em uso) |
| Arquivos 2 | multipleRecordLinks → Arquivos | Sim | fldLWSmK81i8jbtCG | REAPROVEITAR | Agora — dá acesso indireto a Hash do Anexo, MESSAGE ID, Assunto, Conteúdo |
| Tipo de Documento | singleSelect | Sim | fldvkOVlwCMywGTES | REAPROVEITAR (manter uso legado do hotfix, não tocar) | Agora |
| Tipo | singleSelect | Sim | fldJWy7givUDs1aCl | REAPROVEITAR como Categoria Documental | Agora |
| **Cliente** | multipleRecordLinks → Clientes | **Não** | — | **CRIAR** | Agora — crítico |
| **Funcionário** | multipleRecordLinks → Funcionários | **Não** | — | **CRIAR** | Agora — crítico (vazio quando documento é coletivo) |
| **Abrangência** | singleSelect [Individual, Coletivo] | **Não** | — | **CRIAR** | Agora — crítico (pedido explícito) |
| **Competência** | singleLineText | **Não** | — | **CRIAR** | Agora — crítico para agrupar/relatar |
| **Confiança da Classificação** | singleSelect [Alto, Médio, Baixo] | **Não** | — | **CRIAR** | Agora — decide Concluído vs Revisão Manual |
| **Motivo da Revisão Manual** | multilineText | **Não** | — | **CRIAR** | Agora — obrigatório quando Status = Revisão Manual |

**Campos genuinamente novos em Processar Arquivos: 6**

Campos considerados e descartados (já cobertos por cadeia existente, não criar):
- Gmail Message ID → via Arquivos 2 → Arquivos → Emails Savian.MESSAGE ID
- Gmail Attachment ID → desnecessário, PDF já está em Arquivos.Attachments
- Chave de Idempotência → via Arquivos 2 → Arquivos.Hash do Anexo
- Assunto do E-mail → via Arquivos 2 → Arquivos → Emails Savian.Assunto
- Erro Técnico → já existe (de forma não ideal) em Tipo de Documento via hotfix; não duplicar agora

---

## B. LISTA FINAL EXATA — CAMPOS DE ENVIOS DE DOCUMENTOS (tblAu4wgdfTgLOoa4)

**Campos novos nesta etapa: 0 (zero).**

Justificativa — tudo que seria indispensável já existe:

| Necessidade | Campo existente | Field ID |
|---|---|---|
| Status do envio | Status | fldWm7mHYMwQpkQAr |
| Destinatário (empresa) | Cliente | flddPGn6vHiJw7vba |
| Destinatário (pessoa) | Funcionário(s) Vinculado(s) | fldcm9bAj13phGQqS |
| Tipo de envio | Tipo | fld9PU6FeHnIk4XK5 |
| Canal | Canal | fldVDCqA4oMzbZQRj |
| PDFs a enviar | Arquivos | fldiO4G7OO1FAjn5o |
| Erro | Erro | fldxaCcWELeEclZt7 |
| Tentativas | Tentativa | fldYJ6mEUrueSAiM9 |
| ID de mensagem (uso futuro) | ID da Mensagem | fldftsUd7wZX7yOqj |

Conforme instrução do usuário (ponto 7): Envios de Documentos só será
estendido **depois** que a classificação em Processar Arquivos estiver provada
em produção. Competência e Categoria Documental em Envios ficam para essa
etapa futura, não para agora.

---

## C. TOTAL EXATO DE CAMPOS NOVOS

| Tabela | Campos novos |
|---|---|
| Processar Arquivos | 6 |
| Envios de Documentos | 0 |
| **TOTAL** | **6** |

---

## D. FLUXO FINAL

```
[Recebido]
   Processar Arquivos criado com Status = Enviar/Pendente
   Arquivo já linkado via "Arquivos 2" (Hash, Message ID, Assunto, Conteúdo
   acessíveis pela cadeia existente)
        ↓
[Processando]
   Status = Processando (hotfix já garante isto)
        ↓
[Texto extraído]
   PDF lido (funções já existentes: construir_mapa_cpf, extrair_pdf_colaborador)
   CPF procurado no texto
        ↓
[Classificação]
   Tentativa 1 (individual): CPF → Funcionário → Local → Cliente
   Tentativa 2 (coletivo, se CPF ausente ou não encontrado):
       • CNPJ no texto → Clientes.CNPJ
       • Razão social / nome do cliente no texto → Clientes.Nome
       • Assunto do e-mail (via Arquivos 2 → Arquivos → Emails Savian.Assunto)
       • Conteúdo do e-mail (idem, .Conteúdo)
       • Nome/código do Local no texto → Locais.Nome / Locais.CODIGO
       • Competência extraída do texto (regex já existente:
         extrair_competencia_holerite / _detectar_competencia_fiscal)

   Preenche: Cliente, Funcionário (vazio se coletivo), Abrangência,
             Categoria Documental (campo "Tipo"), Competência, Confiança

   Se Confiança = Baixo OU nenhum Cliente identificado:
        → Status = Revisão Manual
        → Motivo da Revisão Manual preenchido (ex.: "CNPJ não localizado no
          texto nem no assunto do e-mail")
   Senão:
        → segue para Concluído
        ↓
[Concluído] ou [Erro]
   Concluído: Status = Concluído (lógica do hotfix mantida)
   Erro: Status = Erro (lógica do hotfix mantida, sem alteração)
```

---

## E. QUATRO TESTES

### Teste 1 — Holerite individual
```
Entrada: PDF de holerite, 1 página, CPF 123.456.789-00 legível no texto
Esperado:
  Funcionário = <encontrado por CPF>
  Cliente = <Cliente do Local do Funcionário>
  Abrangência = Individual
  Categoria Documental (Tipo) = Holerites
  Competência = "Maio/2026" (extraída do texto)
  Confiança = Alto
  Status = Concluído
```

### Teste 2 — Folha de Ponto individual
```
Entrada: PDF de folha de ponto, múltiplas páginas, CPF por página
Esperado:
  Mesmo fluxo do Teste 1, com:
  Categoria Documental (Tipo) = Folha Ponto
  Funcionário identificado por página processada (fluxo já existente do
  master splitter v2.27, não alterado)
  Status = Concluído
```

### Teste 3 — FGTS coletivo sem CPF
```
Entrada: PDF de Guia FGTS Digital, sem CPF individual, mas com CNPJ do
         cliente impresso no documento e/ou no Assunto do e-mail de origem
Esperado:
  CPF não encontrado → cai na tentativa coletiva
  CNPJ do texto bate com Clientes.CNPJ → Cliente identificado
  Funcionário = vazio
  Abrangência = Coletivo
  Categoria Documental (Tipo) = FGTS Digital - Guia Detalhada
  Competência = extraída do texto
  Confiança = Alto (CNPJ é sinal forte) ou Médio (se o match veio só do
              Assunto do e-mail, sinal mais fraco)
  Status = Concluído (se Confiança >= Médio, conforme regra a definir na
           implementação) ou Revisão Manual (se Confiança = Baixo)
```

### Teste 4 — Documento desconhecido → Revisão Manual
```
Entrada: PDF sem CPF, sem CNPJ reconhecível no texto, Assunto do e-mail
         genérico ("Documentos"), Conteúdo do e-mail sem menção a cliente
Esperado:
  Nenhum sinal suficiente para identificar Cliente
  Cliente = vazio
  Funcionário = vazio
  Abrangência = <indeterminado, campo vazio>
  Categoria Documental (Tipo) = Outro (ou categoria mais próxima detectada)
  Confiança = Baixo
  Motivo da Revisão Manual = "Nenhum CPF, CNPJ ou sinal de cliente
                              identificado no texto, assunto ou conteúdo do
                              e-mail"
  Status = Revisão Manual
```

---

## RESUMO EXECUTIVO

| Item | Decisão |
|---|---|
| Campos novos totais | **6**, todos em Processar Arquivos |
| Campos novos em Envios | **0** — reservado para depois de provar a classificação |
| Gmail Message ID | Não criar — já existe via Arquivos → Emails Savian.MESSAGE ID |
| Gmail Attachment ID | Não criar — desnecessário, PDF já anexado fisicamente |
| Chave de idempotência | Não criar — já existe via Arquivos.Hash do Anexo |
| Assunto do e-mail | Não criar — já existe via Emails Savian.Assunto |
| Categoria Documental | Reaproveitar campo ocioso "Tipo" (fldJWy7givUDs1aCl), sem renomear |
| Exclusões/renomeações | Nenhuma — removidas do escopo desta fase |
| Abrangência | Campo novo obrigatório: Individual / Coletivo |
| Sinais para documento coletivo | CNPJ, razão social/nome do cliente, assunto do e-mail, conteúdo do e-mail, nome/código do Local, competência — todos já acessíveis sem novos campos, via texto extraído + cadeia Arquivos→Emails Savian |
| Contratos | Confirmado: não necessário nesta fase (decisão mantida) |
| Tabelas novas | Zero (decisão mantida) |

---

**Nada foi alterado no Airtable, código, Make, Render, Redis ou Worker.**
**Nenhum commit ou push foi feito.**
**Decisão pronta para aprovação de implementação.**
