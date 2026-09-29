import pytest

from _pdf_sintetico import cpf_sintetico, pdf_com_paginas
from magnata_os.classificacao.roteamento_documental import extrair_paginas_seguro
from magnata_os.documental.ocr import CriterioOcr, extrair_paginas_com_ocr

TEXTO_LONGO = f"RECIBO DE PAGAMENTO Colaborador sintetico CPF {cpf_sintetico(90000000001)} competencia 09/2026"


class MotorFake:
    def __init__(self, paginas=None, erro=None):
        self.paginas, self.erro, self.chamadas = paginas, erro, 0

    def extrair_paginas(self, conteudo_pdf):
        self.chamadas += 1
        if self.erro:
            raise self.erro
        return self.paginas


def test_pdf_textual_nunca_passa_por_ocr():
    motor = MotorFake(paginas=("x",))
    extracao = extrair_paginas_com_ocr(pdf_com_paginas([TEXTO_LONGO]), motor)

    assert motor.chamadas == 0
    assert extracao.paginas_por_ocr == () and extracao.tem_texto


def test_so_a_pagina_sem_texto_recebe_ocr():
    conteudo = pdf_com_paginas([TEXTO_LONGO, ""])
    motor = MotorFake(paginas=("ocr pagina 1 que nao deve ser usada", "texto reconhecido por OCR da pagina 2 com conteudo"))

    extracao = extrair_paginas_com_ocr(conteudo, motor)

    assert extracao.paginas_por_ocr == (1,)
    assert "CPF" in extracao.paginas[0] and "OCR da pagina 2" in extracao.paginas[1]
    assert extracao.paginas_sem_texto == ()


@pytest.mark.parametrize("motor", [MotorFake(erro=RuntimeError("motor fora")), MotorFake(paginas=("a", "b", "c"))])
def test_falha_ou_resposta_desalinhada_do_motor_nunca_inventa_texto(motor):
    extracao = extrair_paginas_com_ocr(pdf_com_paginas([TEXTO_LONGO, ""]), motor)

    assert extracao.ocr_falhou is True
    assert extracao.paginas[1] == "" and extracao.paginas_sem_texto == (1,)


def test_ocr_que_devolve_menos_texto_nao_substitui_a_extracao():
    extracao = extrair_paginas_com_ocr(pdf_com_paginas(["curto"]), MotorFake(paginas=("",)))

    assert extracao.paginas == ("curto",) and extracao.paginas_por_ocr == ()


def test_criterio_objetivo_e_configuravel():
    assert CriterioOcr(minimo_caracteres=5).pagina_precisa_ocr("abc") is True
    assert CriterioOcr(minimo_caracteres=5).pagina_precisa_ocr("abc def") is False


def test_extracao_segura_sem_motor_mantem_comportamento_e_com_motor_recupera_escaneado():
    escaneado = pdf_com_paginas(["", ""])

    assert extrair_paginas_seguro(escaneado) is None
    assert extrair_paginas_seguro(escaneado, MotorFake(paginas=(TEXTO_LONGO, ""))) == (TEXTO_LONGO, "")
    assert extrair_paginas_com_ocr(b"nao e pdf", MotorFake(paginas=("x",))) is None
