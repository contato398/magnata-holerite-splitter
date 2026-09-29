"""Gera PDFs sintéticos (texto por página) para testes -- nunca dado real."""

from fpdf import FPDF


def pdf_com_paginas(textos_paginas):
    pdf = FPDF()
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
