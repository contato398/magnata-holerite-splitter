"""Fatiamento de PDF por páginas -- infraestrutura pura (bytes -> bytes).

Reimplementa, sem importar `app.py` (legado protegido), o mesmo padrão
de `extrair_pdf_colaborador` do legado: copiar páginas selecionadas de
um PDF para um PDF novo com pypdf. Determinístico: os mesmos bytes de
origem e os mesmos índices produzem sempre os mesmos bytes (o
`PdfWriter` não grava `/ID` nem data de criação nesse caminho), o que
mantém a idempotência por hash do documento derivado.
"""

from __future__ import annotations

import io
from typing import Sequence


def fatiar_pdf(conteudo: bytes, indices_paginas: Sequence[int]) -> bytes:
    """Devolve um PDF só com as páginas `indices_paginas` (base 0, na
    ordem dada). Índice fora do documento ou lista vazia levanta
    ValueError -- nunca devolve um PDF parcial silencioso."""
    from pypdf import PdfReader, PdfWriter

    if not indices_paginas:
        raise ValueError('ao menos 1 página é obrigatória')
    leitor = PdfReader(io.BytesIO(conteudo))
    total = len(leitor.pages)
    if any(i < 0 or i >= total for i in indices_paginas):
        raise ValueError(f'índice de página fora do documento (total={total})')
    escritor = PdfWriter()
    for indice in indices_paginas:
        escritor.add_page(leitor.pages[indice])
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()
