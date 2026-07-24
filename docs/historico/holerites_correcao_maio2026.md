---
name: holerites-correcao-maio2026
description: Correção dos valores financeiros dos holerites Maio 2026/Junho 2026 no magnata-holerite-splitter (app.py v2.5) e cuidados para próximos meses
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

## Resumo da correção (concluída em 2026-06-12)

**Projeto:** magnata-holerite-splitter (Airtable base `appaCpIVj7Q97VhFy`, tabela Holerites `tblVaUgZeFfa5zRcH`)
**Repo:** github.com/contato398/magnata-holerite-splitter (clonado em `C:\Users\Lenovo\magnata-holerite-splitter`)
**Deploy:** Render — https://magnata-holerite-splitter.onrender.com

**Problema:** registros de holerite de Maio 2026 (Mês Contabilidade = Junho 2026) foram criados com
Total Vencimentos, Total Descontos, Valor Líquido e INSS zerados, porque foram criados via
`processar_holerites.py`, que não envia valores financeiros ao Airtable.

**Correção aplicada (commit `e0ecbaf`, push para `origin/main`):**
- Único arquivo alterado: `app.py` → versão 2.5 (confirmar via `/health`)
- Endpoint `/corrigir-valores` reescrito:
  - Filtra por `Folha Mensal = "<mês>"` E `Mês Contabilidade = "<mês>"` (via ARRAYJOIN)
  - Considera "sem valor" quando `Total Vencimentos` é `BLANK()` OU `= 0`
  - Baixa o PDF já anexado ao registro, extrai valores (regex + parse BR `1.234,56`) e faz
    **apenas PATCH** (nunca cria registro novo — sem risco de duplicidade)
  - Suporta `dry_run` (simula, não grava) e `limit` (processa só N registros)

**Resultado:** dry_run (78 registros) → limit=1 (EDUARDO CAETANO, conferido manualmente no Airtable) →
execução final sem limit (77 restantes). **Total: 78 registros atualizados, 0 erros, 0 sem valor.**

## Cuidados para os próximos meses — [[magnata-holerite-splitter-fluxo]]

1. **Não usar `processar_holerites.py`** para gerar holerites mensais — ele não grava valores
   financeiros. Usar `/processar-holerites` do `app.py` v2.5+ (já extrai e grava na criação).
2. Se algum mês futuro ficar com campos zerados, rodar `/corrigir-valores` sempre nesta ordem:
   - `dry_run=true` primeiro
   - depois `limit=1`, conferir manualmente no Airtable
   - só então rodar sem `limit`
3. O endpoint depende do PDF já estar anexado ao campo "PDF HOLERITE" do registro — sem o
   anexo não há como extrair os valores.
4. Casos "afastado INSS" geram `Valor Líquido = 0,00` e `Total Descontos = Total Vencimentos = INSS`
   — isso é esperado, não é erro de extração.
5. Ajustar `folha_mensal` e `mes_contabilidade` para o par correto do mês em questão
   (ex.: "Junho 2026" / "Julho 2026") antes de rodar a correção, para não misturar competências.
6. Antes de qualquer push para o repo, manter compatibilidade com `requirements.txt`/`Procfile`
   do repo (pinned: flask 3.0.3, pdfplumber 0.11.4, pypdf 4.3.1, gunicorn 22.0.0, requests 2.32.3).
