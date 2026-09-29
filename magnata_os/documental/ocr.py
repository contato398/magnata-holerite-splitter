"""OCR sob demanda -- porta substituível + critério objetivo de quando usar.

Nenhum motor de OCR existe no repositório (auditado: sem pytesseract,
tesseract, ocrmypdf ou equivalente). Este módulo NÃO finge essa
capacidade: define só

- `MotorOcr`: a porta que um adapter real implementa (ex.: tesseract
  local, serviço de OCR) -- instalar/contratar o motor é decisão humana
  (nova dependência de sistema e possível custo);
- `CriterioOcr`: QUANDO o OCR é necessário, de forma objetiva: página
  cuja extração textual normal tem menos que `minimo_caracteres`
  caracteres úteis (PDF escaneado / imagem). PDF textual nunca passa por
  OCR -- evita custo e falso positivo;
- `extrair_paginas_com_ocr`: extração normal primeiro; OCR só nas páginas
  deficientes, só se houver motor; o OCR substitui uma página apenas
  quando devolve MAIS texto útil que a extração normal. Nunca lança:
  falha do motor mantém a extração normal e fica registrada no
  resultado (`ocr_falhou`), nunca vira texto inventado.

Infraestrutura pura (bytes -> texto), sem domínio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from .extracao_texto import extrair_texto_pdf_por_pagina


class MotorOcr(Protocol):
    def extrair_paginas(self, conteudo_pdf: bytes) -> Tuple[str, ...]:
        """Texto por página, na ordem do PDF (mesmo número de páginas)."""
        ...


@dataclass(frozen=True)
class CriterioOcr:
    minimo_caracteres: int = 30

    def pagina_precisa_ocr(self, texto_pagina: str) -> bool:
        return len(''.join((texto_pagina or '').split())) < self.minimo_caracteres


@dataclass(frozen=True)
class ExtracaoPaginas:
    paginas: Tuple[str, ...]
    paginas_por_ocr: Tuple[int, ...] = ()
    paginas_sem_texto: Tuple[int, ...] = ()
    ocr_falhou: bool = False

    @property
    def tem_texto(self) -> bool:
        return any(p.strip() for p in self.paginas)


def extrair_paginas_com_ocr(
    conteudo: bytes,
    motor: Optional[MotorOcr] = None,
    criterio: CriterioOcr = CriterioOcr(),
) -> Optional[ExtracaoPaginas]:
    """None só quando o PDF não pode ser aberto (corrompido/não-PDF)."""
    if not conteudo:
        return None
    try:
        paginas = list(extrair_texto_pdf_por_pagina(conteudo))
    except Exception:
        return None

    deficientes = [i for i, p in enumerate(paginas) if criterio.pagina_precisa_ocr(p)]
    if not deficientes or motor is None:
        return ExtracaoPaginas(tuple(paginas), paginas_sem_texto=tuple(deficientes))

    try:
        por_ocr = tuple(motor.extrair_paginas(conteudo))
    except Exception:
        return ExtracaoPaginas(tuple(paginas), paginas_sem_texto=tuple(deficientes), ocr_falhou=True)
    if len(por_ocr) != len(paginas):
        # motor devolveu outra contagem de páginas: não há como alinhar
        # com segurança -- nunca mistura página de um lugar com outro
        return ExtracaoPaginas(tuple(paginas), paginas_sem_texto=tuple(deficientes), ocr_falhou=True)

    usadas = []
    for i in deficientes:
        if _uteis(por_ocr[i]) > _uteis(paginas[i]):
            paginas[i] = por_ocr[i]
            usadas.append(i)
    ainda_sem_texto = tuple(i for i in deficientes if criterio.pagina_precisa_ocr(paginas[i]))
    return ExtracaoPaginas(tuple(paginas), paginas_por_ocr=tuple(usadas), paginas_sem_texto=ainda_sem_texto)


def _uteis(texto: str) -> int:
    return len(''.join((texto or '').split()))
