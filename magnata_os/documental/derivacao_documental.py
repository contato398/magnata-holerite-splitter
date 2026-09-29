"""Documentos derivados de um PDF composto (vários documentos num só arquivo).

Caso real que motivou: um PDF de 12 páginas com um documento por página.
Enquanto o arquivo inteiro era um único `Documento`, nenhum dos 12 era
encontrável -- o texto combinado tinha 12 pessoas e ia para revisão.

Aplica DEC-ENT-015 (`MAGNATA_OS_DECISOES_ENTIDADES.md`): quando a parte
separada muda de titularidade, ela é avaliada como um Documento DERIVADO,
com proveniência rastreável até o original -- nunca um id sintético
`pai:entidade` sem bytes. Cada derivado:

- tem os PRÓPRIOS bytes (só as páginas do grupo) e o PRÓPRIO hash;
- entra pela porta oficial de entrada (`registrar_entrada`, a mesma de
  `AdaptadorEntradaDuravel`/`ServicoEntradaDocumental`), então herda a
  idempotência por hash: derivar de novo o mesmo PDF nunca duplica;
- herda o `lote_id` do original (a data do e-mail continua valendo para
  o desempate por versão);
- registra a proveniência nos `metadados` do evento de entrada
  (histórico append-only): id e hash do original, páginas (base 1),
  entidade do grupo e estratégia. Sem CPF e sem nome.

O original nunca é alterado nem removido.

Genérico: não conhece Prestação, tipo documental nem colaborador -- só
grupos de páginas já decididos por quem chama (ex.: a separação por CPF
de `classificacao/separacao_documental.py`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence, Tuple

from .fatiamento_pdf import fatiar_pdf
from .modulo01.dominio import Documento


ORIGEM_DERIVADO_SEPARACAO = 'derivado_separacao'


class EntradaDocumental(Protocol):
    """Mesma assinatura de `ServicoEntradaDocumental.registrar_entrada`."""

    def registrar_entrada(
        self,
        conteudo: bytes,
        nome_original: str,
        mime_type: str,
        origem: str,
        correlation_id: Optional[str] = None,
        lote_id: Optional[str] = None,
        metadados: Optional[dict] = None,
    ) -> Documento: ...


@dataclass(frozen=True)
class GrupoPaginas:
    entidade_id: str
    indices_paginas: Tuple[int, ...]  # base 0, ordem original


@dataclass(frozen=True)
class DocumentoDerivado:
    entidade_id: str
    indices_paginas: Tuple[int, ...]
    documento: Documento


def derivar_documentos(
    documento_pai: Documento,
    conteudo_pai: bytes,
    grupos: Sequence[GrupoPaginas],
    estrategia: str,
    entrada: EntradaDocumental,
    buscar_por_hash: Optional[Callable[[str], Optional[Documento]]] = None,
) -> Tuple[DocumentoDerivado, ...]:
    """Registra um Documento derivado por grupo. Um único grupo que cobre
    todas as páginas não é derivado (seria o próprio original): devolve
    tupla vazia. Falha ao fatiar ou registrar é propagada -- quem chama
    decide o isolamento; nunca um derivado parcial silencioso.

    `buscar_por_hash` (ex.: `RepositorioDocumentos.buscar_por_hash`):
    derivado já registrado é reaproveitado sem nova chamada de entrada --
    rodar o ciclo de novo não acumula eventos `TENTATIVA_DUPLICADA` no
    histórico."""
    if not grupos:
        return ()
    total_paginas = _total_paginas_cobertas(grupos)
    if len(grupos) == 1 and total_paginas == _contar_paginas(conteudo_pai):
        return ()

    derivados = []
    for grupo in grupos:
        conteudo = fatiar_pdf(conteudo_pai, grupo.indices_paginas)
        paginas_base_1 = [i + 1 for i in grupo.indices_paginas]
        existente = buscar_por_hash(hashlib.sha256(conteudo).hexdigest()) if buscar_por_hash else None
        if existente is not None:
            derivados.append(DocumentoDerivado(grupo.entidade_id, tuple(grupo.indices_paginas), existente))
            continue
        documento = entrada.registrar_entrada(
            conteudo,
            _nome_derivado(documento_pai.hash_sha256, paginas_base_1),
            'application/pdf',
            ORIGEM_DERIVADO_SEPARACAO,
            correlation_id=documento_pai.correlation_id,
            lote_id=documento_pai.lote_id,
            metadados={
                'documento_pai_id': documento_pai.documento_id,
                'hash_pai': documento_pai.hash_sha256,
                'paginas': paginas_base_1,
                'entidade_id': grupo.entidade_id,
                'estrategia': estrategia,
            },
        )
        derivados.append(DocumentoDerivado(grupo.entidade_id, tuple(grupo.indices_paginas), documento))
    return tuple(derivados)


def _nome_derivado(hash_pai: str, paginas_base_1: Sequence[int]) -> str:
    """Nome NEUTRO, só com identificador técnico: o nome do original
    pode conter nomes de pessoas, e este nome vira o nome do anexo
    enviado ao destinatário."""
    if list(paginas_base_1) == list(range(paginas_base_1[0], paginas_base_1[-1] + 1)):
        faixa = (
            f'{paginas_base_1[0]}' if len(paginas_base_1) == 1
            else f'{paginas_base_1[0]}-{paginas_base_1[-1]}'
        )
    else:
        faixa = '_'.join(str(p) for p in paginas_base_1)
    return f'documento_{hash_pai[:12]}_pag{faixa}.pdf'


def _total_paginas_cobertas(grupos: Sequence[GrupoPaginas]) -> int:
    return len({i for g in grupos for i in g.indices_paginas})


def _contar_paginas(conteudo: bytes) -> int:
    import io

    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(conteudo)).pages)
