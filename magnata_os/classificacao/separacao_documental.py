"""Separação MASTER → FILHOS (missão "CAPACIDADES TRANSVERSAIS DO MOTOR
DOCUMENTAL", Fase 2E.2, Fase E).

Generaliza, numa engine PURA e PLUGÁVEL, o algoritmo de carry-forward
por seção já provado em produção pelo legado
(`app.py::construir_mapa_cliente`, fatiador do Extrato Mensal/FGTS por
tomador — ver docstring original citada abaixo). Nunca importa `app.py`
(legado protegido); extrai só a REGRA de como decidir a que grupo cada
página pertence, preservando ordem e carry-forward.

Regra original (`construir_mapa_cliente`, preservada aqui sem
alteração de comportamento):
  1) página com CNPJ/nome de cliente conhecido → identifica a seção
     (vira o "tomador atual") e a página entra para ele;
  2) página SEM identificação e sem outro CNPJ tomador → DETALHE:
     herda o tomador atual (carry-forward);
  3) página com um CNPJ tomador DESCONHECIDO (não cadastrado) → nova
     seção de cliente não cadastrado: QUEBRA o carry-forward (zera o
     tomador atual) e vai para sem-grupo — evita grudar na seção
     anterior.

A engine (`separar_por_carry_forward`) NÃO sabe o que é "cliente" — só
conhece 3 situações genéricas por página (`SituacaoPaginaSeparacao`):
ENTIDADE_CONHECIDA / ENTIDADE_DESCONHECIDA / SEM_MARCADOR. Quem decide
qual situação uma página representa é uma ESTRATÉGIA plugável
(`IdentificadorDePagina`) — a mesma engine serve para cliente,
colaborador, ou qualquer granularidade futura, desde que alguém forneça
o identificador de página certo (nunca uma arquitetura nova por
granularidade).

Nesta missão, só a estratégia por CNPJ/cliente
(`estrategia_por_cnpj_cliente`) foi portada — reaproveita
`extrair_cnpjs_de_texto` (já pura, já em `importacao_lote/dominio.py`).
GAPS REAIS, registrados e não escondidos (ver ADR):
  - o fallback por NOME normalizado do legado (`_normalizar_texto_
    busca` + busca de substring) depende de uma função só existente em
    `app.py` — não portado nesta missão, permanece cobrindo só o
    caminho por CNPJ exato;
  - a estratégia por CPF/colaborador (`construir_mapa_cpf`, fatiador de
    holerite com múltiplos colaboradores) depende de extratores
    (`extrair_nome_funcionario`, `extrair_valores_holerite`) ainda não
    portados para `magnata_os` — fica para missão futura pelo mesmo
    motivo: portar exigiria reimplementar extração ainda presa a
    `app.py`, o que expandiria esta missão além do "menor produtor
    possível" pedido pela Fase E.

Nunca inventa cliente/competência: uma página sem entidade conhecida e
sem seção corrente aberta vai para `indices_sem_grupo`, nunca para um
grupo arbitrário.
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..documental.importacao_lote.dominio import extrair_cnpjs_de_texto


class SituacaoPaginaSeparacao(str, enum.Enum):
    ENTIDADE_CONHECIDA = 'ENTIDADE_CONHECIDA'
    ENTIDADE_DESCONHECIDA = 'ENTIDADE_DESCONHECIDA'
    SEM_MARCADOR = 'SEM_MARCADOR'


@dataclasses.dataclass(frozen=True)
class IdentificacaoPagina:
    """Resultado de identificar UMA página — devolvido pela estratégia
    plugável, consumido pela engine genérica."""

    situacao: SituacaoPaginaSeparacao
    entidade_id: Optional[str] = None
    nome: Optional[str] = None

    def __post_init__(self) -> None:
        if self.situacao == SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA and not self.entidade_id:
            raise ValueError('ENTIDADE_CONHECIDA exige entidade_id')
        if self.situacao != SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA and (
            self.entidade_id is not None or self.nome is not None
        ):
            raise ValueError('entidade_id/nome só fazem sentido em ENTIDADE_CONHECIDA')


IdentificadorDePagina = Callable[[str], IdentificacaoPagina]


@dataclasses.dataclass(frozen=True)
class GrupoSeparado:
    """Um grupo (futuro "filho") já separado — entidade + páginas na
    ordem original do documento (nunca reordenadas)."""

    entidade_id: str
    nome: Optional[str]
    indices_paginas: Tuple[int, ...]


@dataclasses.dataclass(frozen=True)
class ResultadoSeparacaoDocumento:
    grupos: Tuple[GrupoSeparado, ...]
    indices_sem_grupo: Tuple[int, ...]
    total_paginas: int


def separar_por_carry_forward(
    paginas: Sequence[str],
    identificar_pagina: IdentificadorDePagina,
) -> ResultadoSeparacaoDocumento:
    """Engine pura, genérica e determinística — ver docstring do
    módulo. Preserva ordem de página em cada grupo; nunca inventa
    entidade; cada página do documento aparece em EXATAMENTE um lugar
    (um grupo ou `indices_sem_grupo`, nunca os dois, nunca nenhum)."""
    grupos_ordem: List[str] = []
    grupos_paginas: Dict[str, List[int]] = {}
    grupos_nome: Dict[str, Optional[str]] = {}
    sem_grupo: List[int] = []
    entidade_atual: Optional[str] = None

    for indice, texto_pagina in enumerate(paginas):
        identificacao = identificar_pagina(texto_pagina)

        if identificacao.situacao == SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA:
            entidade_atual = identificacao.entidade_id
            if entidade_atual not in grupos_paginas:
                grupos_paginas[entidade_atual] = []
                grupos_nome[entidade_atual] = identificacao.nome
                grupos_ordem.append(entidade_atual)
            grupos_paginas[entidade_atual].append(indice)
            continue

        if identificacao.situacao == SituacaoPaginaSeparacao.ENTIDADE_DESCONHECIDA:
            # Quebra o carry-forward -- nunca gruda uma seção
            # desconhecida na entidade anterior.
            entidade_atual = None
            sem_grupo.append(indice)
            continue

        # SEM_MARCADOR -- página de detalhe, herda a seção corrente.
        if entidade_atual is not None:
            grupos_paginas[entidade_atual].append(indice)
        else:
            sem_grupo.append(indice)

    grupos = tuple(
        GrupoSeparado(
            entidade_id=entidade_id,
            nome=grupos_nome[entidade_id],
            indices_paginas=tuple(grupos_paginas[entidade_id]),
        )
        for entidade_id in grupos_ordem
    )
    return ResultadoSeparacaoDocumento(
        grupos=grupos,
        indices_sem_grupo=tuple(sem_grupo),
        total_paginas=len(paginas),
    )


def texto_do_grupo(paginas: Sequence[str], grupo: GrupoSeparado) -> str:
    """Reconstrói o texto de um filho já separado — junção, na ordem
    original, do texto das páginas do grupo. Usado para reentrada no
    motor (Fase F): o filho vira um "documento" comum de texto único,
    igual a qualquer outro."""
    return '\n'.join(paginas[indice] for indice in grupo.indices_paginas)


def estrategia_por_cnpj_cliente(
    indice_cnpj_para_cliente: Mapping[str, Tuple[str, str]],
    cnpj_excluido: Optional[str] = None,
) -> IdentificadorDePagina:
    """Generaliza a parte CNPJ-exato de `construir_mapa_cliente`
    (`app.py`) numa estratégia plugável para `separar_por_carry_
    forward`. O índice cliente é INJETADO (nunca lido daqui — quem
    chama já resolveu o índice, ex. via adapter Airtable, mantendo este
    módulo livre de I/O, seguindo a mesma regra de adapter injetado já
    usada em `vinculos_prestacao.FonteVinculosPrestacao`).

    `cnpj_excluido` reproduz a exclusão do CNPJ do próprio empregador
    (Magnata) do legado — sem isso, uma página do próprio empregador se
    identificaria como "cliente" e nunca separaria nada corretamente.
    """
    def identificar(texto_pagina: str) -> IdentificacaoPagina:
        cnpjs_tomador = [
            cnpj for cnpj in extrair_cnpjs_de_texto(texto_pagina)
            if cnpj != cnpj_excluido
        ]
        for cnpj in cnpjs_tomador:
            if cnpj in indice_cnpj_para_cliente:
                cliente_id, nome = indice_cnpj_para_cliente[cnpj]
                return IdentificacaoPagina(
                    SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA, cliente_id, nome,
                )
        if cnpjs_tomador:
            return IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_DESCONHECIDA)
        return IdentificacaoPagina(SituacaoPaginaSeparacao.SEM_MARCADOR)

    return identificar
