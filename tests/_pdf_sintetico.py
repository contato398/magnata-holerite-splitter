"""Gera PDFs sintéticos (texto por página) para testes -- nunca dado real."""

from datetime import datetime, timezone

from fpdf import FPDF

# fpdf2 grava `self.creation_date = datetime.now(timezone.utc)` no construtor
# e esse timestamp (resolução de 1s) entra nos bytes finais do PDF
# (`/CreationDate`) -- ou seja, dois PDFs com o MESMO conteúdo textual
# produzem bytes (e hash sha256) DIFERENTES sempre que as duas chamadas
# caem em segundos de relógio diferentes. Vários testes usam o hash do PDF
# pra casar fake/dublê por conteúdo (ex.: `_MotorOcrFake` em
# `tests/test_orquestrador_prestacao_cliente_competencia_v1.py`, que gera o
# PDF "escaneado" uma vez pra montar o dublê e De NOVO dentro de
# `_dependencias()` pra alimentar o pipeline) -- um relógio que avança entre
# as duas chamadas quebra esse casamento por hash com um `KeyError`
# intermitente, não reproduzível de forma confiável (passa na maioria das
# rodadas, falha raramente, mais sob carga/--cov que atrasa a segunda
# chamada o suficiente). Fixar a data de criação em um valor constante
# resolve a causa: a mesma lista de textos sempre produz os mesmos bytes,
# em qualquer segundo do relógio real.
_DATA_CRIACAO_FIXA = datetime(2000, 1, 1, tzinfo=timezone.utc)


def pdf_com_paginas(textos_paginas):
    pdf = FPDF()
    pdf.set_creation_date(_DATA_CRIACAO_FIXA)
    pdf.set_auto_page_break(False)
    for texto in textos_paginas:
        pdf.add_page()
        pdf.set_font('Helvetica', size=11)
        y = 20
        for linha in texto.split('\n'):
            pdf.text(15, y, linha)
            y += 8
    return bytes(pdf.output())


def cpf_sintetico(n: int) -> str:
    """CPF formatado sintético e deterministico (sem dígito verificador
    válido -- o extrator só olha o formato)."""
    digitos = f'{n:011d}'
    return f'{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:11]}'
