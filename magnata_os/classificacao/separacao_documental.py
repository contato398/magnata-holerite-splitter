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

Fase 2E.3 (missão "FECHAMENTO AMPLO DA COBERTURA DOCUMENTAL") completa
a separação com 2 estratégias adicionais, usando a MESMA engine —
nenhuma engine nova por granularidade:
  - `estrategia_por_cnpj_ou_nome_cliente`: adiciona o fallback por NOME
    normalizado do legado (`_normalizar_texto_busca` + busca de
    substring, agora `normalizar_texto_busca`, pura, portada aqui) —
    só quando NENHUM CNPJ aparece na página (CNPJ exato sempre vence,
    "Fase B" da missão: "CPF/CNPJ exatos > nome"). DESVIO DELIBERADO,
    REGISTRADO, do legado: 2+ nomes de clientes DIFERENTES batendo na
    mesma página é tratado como AMBÍGUO (`ENTIDADE_DESCONHECIDA`, nunca
    escolhe o primeiro por ordem arbitrária) — o legado original
    (`_carregar_indice_clientes`) resolve isso só pela ordenação
    "nome mais longo primeiro" e pega o primeiro que bater, sem
    detectar ambiguidade; a nova regra explícita da missão ("nome
    ambíguo → revisão") é mais segura e nunca inventa cliente.
  - `estrategia_por_cpf_colaborador`: generaliza `construir_mapa_cpf`
    (fatiador de holerite/ponto com múltiplos colaboradores). DESVIO
    DELIBERADO, REGISTRADO: o legado usa o CPF cru como chave (nenhum
    índice pré-existente) — aqui exige um índice CPF→colaborador
    INJETADO (mesmo padrão de `estrategia_por_cnpj_cliente`), porque
    `extrair_cpfs_distintos_de_texto` documenta que "CPF é estritamente
    TRANSITÓRIO — nunca retornado em DTO"; sem índice, o CPF cru viraria
    `GrupoSeparado.entidade_id` (um DTO puro), violando essa regra.
    Exigir índice também cumpre a cláusula pétrea #10 desta missão
    ("não inventar colaborador") — CPF desconhecido nunca vira grupo
    novo, vai para `indices_sem_grupo` como qualquer entidade
    desconhecida.

Nunca inventa cliente/colaborador/competência: uma página sem entidade
conhecida e sem seção corrente aberta vai para `indices_sem_grupo`,
nunca para um grupo arbitrário.
"""
from __future__ import annotations

import dataclasses
import enum
import unicodedata
import re as _re
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..documental.importacao_lote.dominio import (
    extrair_cnpjs_de_texto,
    extrair_cpfs_distintos_de_texto,
    normalizar_cpf,
)


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


def normalizar_texto_busca(texto: str) -> str:
    """Porta pura de `app.py::_normalizar_texto_busca` — NFKD, remove
    acentos (caracteres combinantes), colapsa espaço, maiúsculas.
    Nenhuma mudança de comportamento em relação ao legado."""
    texto_normalizado = unicodedata.normalize('NFKD', texto or '')
    sem_acentos = ''.join(c for c in texto_normalizado if not unicodedata.combining(c))
    return _re.sub(r'\s+', ' ', sem_acentos).strip().upper()


def estrategia_por_cnpj_ou_nome_cliente(
    indice_cnpj_para_cliente: Mapping[str, Tuple[str, str]],
    indice_nomes: Sequence[Tuple[str, str, str]] = (),
    cnpj_excluido: Optional[str] = None,
) -> IdentificadorDePagina:
    """Generaliza `construir_mapa_cliente` por completo (CNPJ exato +
    fallback por nome normalizado) -- ver "DESVIO DELIBERADO" na
    docstring do módulo para a diferença de tratamento de ambiguidade.

    `indice_nomes`: sequência de `(nome_normalizado, cliente_id, nome)`
    -- MESMA forma e MESMA ordenação (nome mais longo primeiro) que
    `app.py::_carregar_indice_clientes` já produz, injetada por quem
    chama (nunca lida daqui -- este módulo continua livre de I/O).
    CNPJ exato sempre vence sobre nome, na própria página."""
    identificar_por_cnpj = estrategia_por_cnpj_cliente(indice_cnpj_para_cliente, cnpj_excluido)

    def identificar(texto_pagina: str) -> IdentificacaoPagina:
        resultado_cnpj = identificar_por_cnpj(texto_pagina)
        if resultado_cnpj.situacao != SituacaoPaginaSeparacao.SEM_MARCADOR:
            # CNPJ (conhecido ou desconhecido) sempre decide -- nome só
            # é consultado quando a página não tem NENHUM CNPJ tomador.
            return resultado_cnpj

        texto_normalizado = normalizar_texto_busca(texto_pagina)
        encontrados = {
            (cliente_id, nome) for nome_norm, cliente_id, nome in indice_nomes
            if nome_norm and nome_norm in texto_normalizado
        }
        if len(encontrados) > 1:
            # Nome ambíguo -- nunca escolhe o primeiro por ordem
            # arbitrária (Fase B da missão: "nome ambíguo -> revisão").
            return IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_DESCONHECIDA)
        if len(encontrados) == 1:
            cliente_id, nome = next(iter(encontrados))
            return IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA, cliente_id, nome)
        return IdentificacaoPagina(SituacaoPaginaSeparacao.SEM_MARCADOR)

    return identificar


def estrategia_por_cpf_colaborador(
    indice_cpf_para_colaborador: Mapping[str, Tuple[str, str]],
) -> IdentificadorDePagina:
    """Generaliza a separação por colaborador (`construir_mapa_cpf`) --
    ver "DESVIO DELIBERADO" na docstring do módulo: exige um índice
    CPF->colaborador INJETADO (nunca o CPF cru como identidade), porque
    CPF é estritamente transitório (nunca em DTO). CPF desconhecido
    nunca vira grupo -- quebra o carry-forward, igual à estratégia de
    cliente para CNPJ desconhecido."""
    def identificar(texto_pagina: str) -> IdentificacaoPagina:
        cpfs_pagina = extrair_cpfs_distintos_de_texto(texto_pagina)
        for cpf in cpfs_pagina:
            if cpf in indice_cpf_para_colaborador:
                colaborador_id, nome = indice_cpf_para_colaborador[cpf]
                return IdentificacaoPagina(
                    SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA, colaborador_id, nome,
                )
        if cpfs_pagina:
            return IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_DESCONHECIDA)
        return IdentificacaoPagina(SituacaoPaginaSeparacao.SEM_MARCADOR)

    return identificar


def indice_cpf_de_candidatos(candidatos: Sequence[object]) -> Dict[str, Tuple[str, None]]:
    """Índice CPF -> (colaborador_id, None) para `estrategia_por_cpf_
    colaborador`, montado a partir de `CandidatoFuncionario` (func_id,
    cpf, nome_normalizado) já presentes no contexto.

    - CPF é chave TRANSITÓRIA em memória -- o índice nunca é logado nem
      devolvido em DTO; o que sai da separação é só `colaborador_id`.
    - `nome` é sempre None: nome real de pessoa nunca entra em grupo.
    - CPF associado a mais de um colaborador é DESCARTADO (ambíguo --
      mesma regra de `resolver_funcionario`): a página vira entidade
      desconhecida, nunca atribuída por adivinhação."""
    por_cpf: Dict[str, set] = {}
    for candidato in candidatos:
        cpf = normalizar_cpf(getattr(candidato, 'cpf', None) or '')
        colaborador_id = getattr(candidato, 'func_id', None)
        if len(cpf) != 11 or not colaborador_id:
            continue
        por_cpf.setdefault(cpf, set()).add(colaborador_id)
    return {
        cpf: (next(iter(ids)), None)
        for cpf, ids in por_cpf.items()
        if len(ids) == 1
    }


_CPF_SEM_FORMATACAO_RE = _re.compile(r'(?<!\d)\d{11}(?!\d)')


def cpfs_da_pagina(texto_pagina: str, indice_cpf_para_colaborador: Mapping[str, object]) -> Tuple[str, ...]:
    """CPFs distintos de uma página, normalizados: todos os formatados
    (`XXX.XXX.XXX-XX`) MAIS os de 11 dígitos sem formatação que sejam de
    um colaborador CONHECIDO do índice.

    Por que só os conhecidos sem formatação: 11 dígitos soltos também
    podem ser PIS/NIT, matrícula ou código de barras -- contar qualquer
    um bloquearia páginas legítimas. Um CPF conhecido sem formatação, ao
    contrário, é evidência forte de que outra pessoa está na página (o
    caso "CPF de B sem pontuação ao lado do de A" que deixava o PDF
    passar como documento só de A). Ordem de primeira ocorrência;
    transitório -- nunca logado nem devolvido em DTO."""
    vistos = list(extrair_cpfs_distintos_de_texto(texto_pagina))
    for candidato in _CPF_SEM_FORMATACAO_RE.findall(texto_pagina or ''):
        if candidato in indice_cpf_para_colaborador and candidato not in vistos:
            vistos.append(candidato)
    return tuple(vistos)


def estrategia_por_cpf_colaborador_estrita(
    indice_cpf_para_colaborador: Mapping[str, Tuple[str, Optional[str]]],
) -> IdentificadorDePagina:
    """Variante ESTRITA de `estrategia_por_cpf_colaborador` para gerar
    documentos derivados que serão ENVIADOS a uma pessoa: a página só
    entra no grupo de um colaborador se contiver exatamente 1 CPF
    distinto e ele for desse colaborador.

    - página sem CPF (resumo geral da folha, capa, CPF sem formatação
      ou quebrado pela extração) -> ENTIDADE_DESCONHECIDA: nunca herda o
      grupo anterior por carry-forward -- herdar colocaria dados de outra
      pessoa no PDF de alguém;
    - página com 2+ CPFs distintos -> ENTIDADE_DESCONHECIDA: nunca vai
      para o primeiro conhecido. Conta também o CPF SEM formatação de um
      colaborador conhecido (`cpfs_da_pagina`).
    Custo aceito: a página de continuação sem CPF de um documento de
    várias páginas fica fora da parte derivada (vai para
    `indices_sem_grupo`, contada no evento), em vez de arriscar misturar
    pessoas."""
    def identificar(texto_pagina: str) -> IdentificacaoPagina:
        cpfs_pagina = cpfs_da_pagina(texto_pagina, indice_cpf_para_colaborador)
        if len(cpfs_pagina) == 1 and cpfs_pagina[0] in indice_cpf_para_colaborador:
            colaborador_id, nome = indice_cpf_para_colaborador[cpfs_pagina[0]]
            return IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA, colaborador_id, nome)
        return IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_DESCONHECIDA)

    return identificar
