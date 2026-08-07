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
