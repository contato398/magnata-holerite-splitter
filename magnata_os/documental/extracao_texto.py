"""Extração de texto de PDF — função pública e neutra, reutilizável por
qualquer módulo do core novo (importacao_lote, classificacao, futuros).

Promovida de `magnata_os/documental/importacao_lote/orquestrador.py`
(antes `_extrair_texto_pdf`, privada e acoplada àquele módulo) para este
local neutro — MESMA lógica, sem duplicação. `processar_holerite`/
`processar_extrato` (orquestrador.py) continuam com o comportamento
idêntico, agora importando esta função em vez de definir a própria
cópia.

Import de `pdfplumber` é feito dentro da função (não no topo do módulo)
— mesmo padrão de antes da promoção, para não pagar o custo de import
da biblioteca em quem só usa outra parte do pacote documental.
"""

from __future__ import annotations

import io


def extrair_texto_pdf(conteudo: bytes) -> str:
    """Extrai o texto de todas as páginas de um PDF a partir dos bytes.

    Não trata exceção de PDF corrompido/ilegível aqui — quem chama
    decide a política de isolamento de falha. Ver:
    - `processar_holerite`/`processar_extrato` (importacao_lote/
      orquestrador.py): capturam exceção por item, nunca derrubam o
      lote inteiro.
    - `roteamento_documental.py` (classificacao/): trata falha de
      extração como decisão de revisão humana, nunca como exceção não
      tratada.
    """
    return ''.join(pagina + '\n' for pagina in extrair_texto_pdf_por_pagina(conteudo))


def extrair_texto_pdf_por_pagina(conteudo: bytes) -> tuple[str, ...]:
    """Mesma extração de `extrair_texto_pdf`, preservando a fronteira de
    página (uma string por página, na ordem do PDF). Necessária para
    separar um PDF que contém vários documentos (ex.: 12 holerites, um
    por página) -- juntar as páginas apaga exatamente a informação que
    diz onde cada documento começa. Mesma política de exceção de
    `extrair_texto_pdf`: quem chama decide."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        return tuple((pagina.extract_text() or '') for pagina in pdf.pages)
