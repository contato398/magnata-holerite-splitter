# magnata_os/documental/importacao_lote/ — Regras específicas

Complementa `/CLAUDE.md` (raiz) e `magnata_os/CLAUDE.md` — não repete o
que já está lá.

- **`dominio.py` é puro.** Nenhuma função ali faz I/O de rede, lê disco
  ou importa `requests`/`pdfplumber`/cliente Airtable. Extração de texto
  de PDF e chamadas HTTP ficam em `orquestrador.py`/`adapters/`.
- **Nenhuma constante de execução específica (competência, mensagem de
  origem, hash do pacote) vive como constante do módulo.** Tudo isso é
  `ConfiguracaoExecucao`, passado de fora — o módulo é reutilizável para
  qualquer competência futura, não só Julho/2026.
- **`source_service_number` (prefixo numérico do pacote) nunca é tratado
  como ID canônico do Airtable sem prova de correspondência** — é só um
  dado do manifesto carregado para auditoria, nunca usado sozinho para
  decidir `exact`.
- **Correspondência de cliente por CNPJ é sempre tentada antes de nome**,
  mesmo quando dois itens têm nome truncado idêntico no manifesto —
  nunca decidir por nome quando há CNPJ extraível.
- **`adapters/airtable_leitura.py` só tem métodos GET.** Nenhum método de
  escrita nesta classe, nunca — se uma necessidade de escrita aparecer,
  é um adapter novo, revisado à parte, não uma extensão deste.
- **CPF completo só existe em memória, dentro do escopo da função que
  resolve `func_id`.** Nunca é campo de retorno, nunca é logado, nunca
  entra em `ResultadoItem`.
- **IDs de tabela/campo do Airtable duplicados aqui, não importados de
  `app.py`.** `app.py` é legado protegido (CLAUDE.md §7) — este módulo
  não cria dependência de import contra ele. Custo aceito: se o schema
  do Airtable mudar, os dois lugares precisam ser atualizados
  separadamente — registrado, não escondido.

## Camada de escrita (escritor.py, dominio_versionamento.py) — adendo

- **`escritor.py` nunca refaz matching/classificação.** Só consome
  `ResultadoItem` já produzido por `orquestrador.py`/`dominio.py` — só
  processa automaticamente `EXACT` + `pronto_para_gravacao`; qualquer
  outra classificação é ignorada (`IGNORADO_NAO_EXACT`), nunca
  reclassificada aqui.
- **Documento lógico (`documento_logico_id`) nunca inclui hash de
  conteúdo nem PII** (`dominio_versionamento.calcular_documento_logico_id`)
  — separado de `hash_sha256` (conteúdo físico, `documentos`,
  modulo01/dominio.py) de propósito. Hash diferente para o mesmo
  documento lógico é **sempre** `CONFLITO` — nunca supersede sozinho;
  supersessão só por fluxo humano futuro explícito (fora de escopo
  desta fase), nunca chamada automaticamente por `escritor.py`.
- **`substitui_documento_id` só referencia
  `documentos_versionamento_logico`, nunca `documentos` diretamente**
  (migration 0009) — lineage nunca aponta para um documento fora do
  modelo de versionamento.
- **`nome_referencia` (nome do manifesto) só passa adiante para o
  Airtable — nunca persistido em `ItemExecucao`, nunca em
  `ResultadoEscrita`, nunca logado.** Mesma disciplina de `cpf_extraido`
  em `orquestrador.py`: existe em memória só pelo tempo da chamada.
- **`documento_id` nunca é chave primária de item de execução**
  (`itens_importacao_lote`, migration 0009) — nullable e não-único de
  propósito; o mesmo conteúdo pode aparecer em itens de
  execuções/lotes diferentes.
- **Compensação (delete condicional) só quando comprovado**: registro
  criado por ESTA execução (`external_criado_por_esta_execucao`) E
  releitura confirma ausência de anexo. Nunca deleta registro
  pré-existente nem por inferência (ver `escritor._tratar_falha_upload`).
- **`adapters/airtable_escrita.py` é o único lugar de escrita real ao
  Airtable neste módulo** — nunca chamado de verdade nesta fase; toda
  cobertura de teste usa o duplo `_FakeEscritorAirtable`
  (`test_importacao_lote_escrita.py`), nunca rede real.
- **`eventos_itens_importacao_lote` é a trilha do ITEM, nunca duplica
  `eventos_documentais` (trilha do DOCUMENTO).** Todo ponto de
  `escritor.py` que muda um `ItemExecucao` passa por `_persistir_item`
  — nunca um `repositorio_itens.salvar(item)` solto — para que a
  sequência completa (inclusive antes de `documento_id` existir) seja
  reconstruível sem log.
