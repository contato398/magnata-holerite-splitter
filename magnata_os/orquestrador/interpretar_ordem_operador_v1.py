"""Intérprete de ordem em linguagem natural do operador -- traduz uma
frase livre em português ("manda pro Fulano e pro Beltrano o holerite
de setembro, com assinatura digital e comprovante") na mesma
`SelecaoEnvioOperador`/`ItemSelecaoEnvioOperador` (`selecao_envio_
operador_v1.py`, INTOCADO) que hoje um humano monta manualmente em
JSON para `scripts/selecao_envio_operador_cli.py`.

Necessidade de negócio (registrada aqui por completo, não só na
conversa, `/CLAUDE.md` §2): o operador quer dar a ordem em texto livre,
sem montar JSON na mão. O comportamento central pedido é o oposto de
"adivinhar": "se perceber qualquer problema ou dificuldade antes de
enviar, aí sim pode pedir orientação" -- por isso este módulo NUNCA
resolve uma ambiguidade sozinho. Qualquer dúvida real (nome ambíguo,
documento não encontrado/não pronto, competência ausente e não
inferível, destinatário não identificado) vira um item explícito de
`ResultadoInterpretacaoOrdem.duvidas` -- nunca uma exceção genérica,
nunca uma escolha silenciosa.

Parsing determinístico (regex/heurística), sem nenhuma dependência de
LLM/API externa -- fora de escopo desta missão e seria uma escrita
externa nova não autorizada (`/CLAUDE.md` §6). Domínio puro: nenhum
import de Flask, driver de banco, boto3, cliente Airtable nem qualquer
I/O -- só texto e as mesmas dataclasses de `selecao_envio_operador_v1`
(`magnata_os/CLAUDE.md`, "pureza de domínio").

**LACUNA DE CONTRATO REGISTRADA (não resolvida em silêncio, `/CLAUDE.md`
§2):** a missão pede correspondência "contra os nomes reais presentes
no `DiagnosticoPrestacao`" -- mas `DiagnosticoPrestacao.como_dict()`
NUNCA carrega nome de colaborador, só `colaborador_id`
(`ReferenciaCanonica('COLABORADOR', id_interno)`, sempre sanitizado por
desenho -- ver comentário "nunca CPF, nome de pessoa" em
`composicao_ciclo_persistente_prestacao.py` e em todos os adapters de
`documental/importacao_lote/adapters/`). Isso é proteção de dado
pessoal deliberada (LGPD, `/CLAUDE.md` §6), não um bug. Resolução
adotada aqui, registrada como decisão explícita (ver
`docs/decisoes/interpretar-ordem-operador-v1.md`): este módulo recebe
um `diretorio_nomes` SEPARADO e OPCIONAL (`Mapping[colaborador_id,
nome]`), nunca misturado ao diagnóstico em si -- o diagnóstico
continua exatamente como é hoje, sem nenhum campo de PII novo. Sem
`diretorio_nomes`, o `colaborador_id` é usado como o próprio "nome"
de correspondência (suficiente para ambiente sintético/teste; para um
operador real digitando nome de pessoa física contra um `colaborador_id`
opaco de Airtable, isso é uma limitação declarada, não escondida --
de onde viria esse diretório em produção fica como pendência aberta,
não resolvida nesta missão).

Este módulo só produz `SelecaoEnvioOperador` (contrato já validado a
jusante por `validar_selecao_contra_diagnostico`) ou uma pendência --
NUNCA chama nada de transporte real, nunca importa `porta_execucao`/
`transporte_real_habilitado`/`autorizacao_transporte_real`, nunca
despacha assinatura real. Continua 100% modo sombra.
"""
from __future__ import annotations

import dataclasses
import re
import unicodedata
from typing import FrozenSet, List, Mapping, Optional, Sequence, Tuple

from magnata_os.orquestrador.selecao_envio_operador_v1 import (
    ItemSelecaoEnvioOperador,
    SelecaoEnvioOperador,
)

__all__ = [
    'InterpretacaoOrdemOperadorError',
    'DuvidaInterpretacaoOrdem',
    'ResultadoInterpretacaoOrdem',
    'interpretar_ordem_contra_linhas_diagnostico',
]


class InterpretacaoOrdemOperadorError(ValueError):
    """Erro ESTRUTURAL (entrada mal formada demais para sequer tentar
    interpretar) -- nunca uma dúvida de negócio. Dúvida de negócio
    (nome ambíguo, documento não pronto, competência ausente...) NUNCA
    levanta exceção: vira item de `ResultadoInterpretacaoOrdem.duvidas`
    (ver princípio de `/CLAUDE.md` §4: dimensões nunca fundidas --
    "erro de entrada" e "pendência de negócio" são coisas diferentes)."""


@dataclasses.dataclass(frozen=True)
class DuvidaInterpretacaoOrdem:
    """1 dúvida real, específica, para o humano decidir -- nunca uma
    tentativa de adivinhar. `codigo` é estável e legível por máquina
    (para o futuro painel); `descricao` é o texto para o humano;
    `trecho_ordem` é o pedaço exato da ordem (ou o texto completo,
    quando a dúvida não se localiza num trecho específico) que gerou a
    dúvida."""

    codigo: str
    descricao: str
    trecho_ordem: str

    def __post_init__(self) -> None:
        for campo in ('codigo', 'descricao', 'trecho_ordem'):
            valor = getattr(self, campo)
            if not isinstance(valor, str) or (campo != 'trecho_ordem' and not valor.strip()):
                raise InterpretacaoOrdemOperadorError(f'DuvidaInterpretacaoOrdem.{campo} deve ser texto não vazio')


@dataclasses.dataclass(frozen=True)
class ResultadoInterpretacaoOrdem:
    """União clara -- `/CLAUDE.md` §4, dimensões separadas, nunca
    fundidas num campo só: OU `selecao` está pronta (`duvidas == ()`)
    OU existe ao menos 1 dúvida (`selecao is None`). Nunca os dois ao
    mesmo tempo, nunca os dois vazios."""

    selecao: Optional[SelecaoEnvioOperador]
    duvidas: Tuple[DuvidaInterpretacaoOrdem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.duvidas, tuple) or any(not isinstance(d, DuvidaInterpretacaoOrdem) for d in self.duvidas):
            raise InterpretacaoOrdemOperadorError('duvidas deve ser uma tupla de DuvidaInterpretacaoOrdem')
        if self.selecao is not None and not isinstance(self.selecao, SelecaoEnvioOperador):
            raise InterpretacaoOrdemOperadorError('selecao deve ser SelecaoEnvioOperador ou None')
        if self.selecao is None and not self.duvidas:
            raise InterpretacaoOrdemOperadorError(
                'ResultadoInterpretacaoOrdem sem selecao pronta precisa de ao menos 1 duvida -- '
                'nunca um resultado vazio'
            )
        if self.selecao is not None and self.duvidas:
            raise InterpretacaoOrdemOperadorError(
                'ResultadoInterpretacaoOrdem nunca mistura selecao pronta com duvidas pendentes'
            )

    @property
    def pronta(self) -> bool:
        return self.selecao is not None

    def como_dict(self) -> dict:
        """Mesmo formato (status/itens) já usado por `selecao_envio_
        operador_cli.py`/`prestacao_compor_ordem_selecionada_cli.py` --
        vocabulário reaproveitado, nunca um paralelo novo."""
        if self.pronta:
            return {
                'status': 'SELECAO_INTERPRETADA_PRONTA_PARA_VALIDACAO',
                'itens': [
                    {
                        'cliente_id': item.cliente_id,
                        'competencia_id': item.competencia_id,
                        'colaborador_id': item.colaborador_id,
                        'tipos_documentais': list(item.tipos_documentais),
                        'exigir_assinatura_digital_e_comprovante': item.exigir_assinatura_digital_e_comprovante,
                    }
                    for item in self.selecao.itens
                ],
                'aviso': (
                    'ESTA INTERPRETAÇÃO NÃO CRIA ORDEM NEM ENVIA NADA -- é só a tradução da ordem em '
                    'texto para SelecaoEnvioOperador. Validar contra o diagnóstico '
                    '(selecao_envio_operador_cli.py) e compor a Ordem '
                    '(prestacao_compor_ordem_selecionada_cli.py) continuam passos manuais separados.'
                ),
            }
        return {
            'status': 'PENDENCIA_DE_ESCLARECIMENTO',
            'duvidas': [
                {'codigo': d.codigo, 'descricao': d.descricao, 'trecho_ordem': d.trecho_ordem}
                for d in self.duvidas
            ],
            'aviso': 'A ordem tem ao menos 1 dúvida real -- nenhuma SelecaoEnvioOperador foi produzida.',
        }


# ---------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------

def _remover_acentos(texto: str) -> str:
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')


def _normalizar_nome(nome: str) -> str:
    sem_acento = _remover_acentos(nome).lower()
    return re.sub(r'\s+', ' ', sem_acento).strip()


def _tokens(nome_normalizado: str) -> Tuple[str, ...]:
    return tuple(t for t in nome_normalizado.split(' ') if t)


# ---------------------------------------------------------------------
# Tipo documental -- vocabulário natural -> família canônica, ordenado
# do alias mais específico (mais palavras) para o mais genérico -- o
# primeiro que aparecer no texto vence (1 tipo documental por ordem,
# escopo desta versão).
# ---------------------------------------------------------------------

_ALIASES_TIPO_DOCUMENTAL: Tuple[Tuple[str, str], ...] = (
    ('comprovante de pagamento do salario', 'comprovante_pagamento_salario'),
    ('comprovante de pagamento - salario', 'comprovante_pagamento_salario'),
    ('comprovante de pagamento salario', 'comprovante_pagamento_salario'),
    ('comprovante de salario', 'comprovante_pagamento_salario'),
    ('extrato da folha de pagamento', 'extrato_folha_pagamento'),
    ('extrato de pagamento', 'extrato_folha_pagamento'),
    ('folha de ponto', 'folha_de_ponto'),
    ('nota fiscal', 'nota_fiscal'),
    ('guia dctfweb', 'guia'),
    ('contracheque', 'holerite'),
    ('holerite', 'holerite'),
    ('fgts', 'fgts'),
    ('boleto', 'boleto'),
    ('certidao', 'certidao'),
    ('extrato', 'extrato_folha_pagamento'),
    ('ponto', 'folha_de_ponto'),
    ('comprovante', 'comprovante_pagamento_salario'),
    ('guia', 'guia'),
)

_STOPWORDS_TIPO_DOCUMENTAL = frozenset({'de', 'da', 'do'})


def _tokens_significativos_tipo(texto_normalizado: str) -> FrozenSet[str]:
    brutos = re.split(r'[^a-z0-9]+', texto_normalizado)
    return frozenset(t for t in brutos if t and t not in _STOPWORDS_TIPO_DOCUMENTAL)


def _localizar_familia_tipo_documental(texto_sa_lower: str) -> Optional[str]:
    for alias, familia in _ALIASES_TIPO_DOCUMENTAL:
        if alias in texto_sa_lower:
            return familia
    return None


def _tipo_documental_bate_na_familia(tipo_documental_real: str, familia: str) -> bool:
    """Critério objetivo: todo token da família (ex.: 'comprovante',
    'pagamento', 'salario') precisa aparecer entre os tokens
    significativos do `tipo_documental` real do diagnóstico -- tolera
    maiúscula/minúscula, acento e a ordem/forma exata das palavras
    (ex.: 'Comprovante de Pagamento - Salário' bate com a família
    'comprovante_pagamento_salario')."""
    tokens_familia = frozenset(familia.split('_'))
    tokens_real = _tokens_significativos_tipo(_remover_acentos(tipo_documental_real).lower())
    return tokens_familia.issubset(tokens_real)


# ---------------------------------------------------------------------
# Competência
# ---------------------------------------------------------------------

_MESES = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6,
    'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12,
}

_PADRAO_COMPETENCIA_ISO = re.compile(r'\b(\d{4})-(\d{2})\b')
_PADRAO_COMPETENCIA_MES_ANO_BARRA = re.compile(r'\b(\d{1,2})/(\d{4})\b')
_PADRAO_MES_NOME = re.compile(r'\b(' + '|'.join(_MESES) + r')\b(?:\s+de\s+(\d{4})|/(\d{4}))?')


@dataclasses.dataclass(frozen=True)
class _CompetenciaExtraida:
    competencia_id: Optional[str]  # 'AAAA-MM' já com ano resolvido, ou None
    mes_sem_ano: Optional[int]     # mês citado, mas sem ano -- precisa inferir


def _extrair_competencia_da_ordem(texto_sa_lower: str) -> Optional[_CompetenciaExtraida]:
    match = _PADRAO_COMPETENCIA_ISO.search(texto_sa_lower)
    if match:
        return _CompetenciaExtraida(competencia_id=f'{match.group(1)}-{match.group(2)}', mes_sem_ano=None)
    match = _PADRAO_COMPETENCIA_MES_ANO_BARRA.search(texto_sa_lower)
    if match:
        return _CompetenciaExtraida(
            competencia_id=f'{int(match.group(2)):04d}-{int(match.group(1)):02d}', mes_sem_ano=None,
        )
    match = _PADRAO_MES_NOME.search(texto_sa_lower)
    if match:
        mes = _MESES[match.group(1)]
        ano = match.group(2) or match.group(3)
        if ano:
            return _CompetenciaExtraida(competencia_id=f'{int(ano):04d}-{mes:02d}', mes_sem_ano=None)
        return _CompetenciaExtraida(competencia_id=None, mes_sem_ano=mes)
    return None


# ---------------------------------------------------------------------
# Assinatura digital + comprovante
# ---------------------------------------------------------------------

_PADRAO_SEM_ASSINATURA = re.compile(r'\b(sem|nao)\b[^.,]{0,25}\bassinatura\b')
_PADRAO_COM_ASSINATURA = re.compile(r'\bassinatura\b')


def _extrair_exigir_assinatura(texto_sa_lower: str) -> bool:
    """Ausência de menção a "assinatura" = `False` (assinatura+
    comprovante é sempre opt-in explícito, nunca um default assumido) --
    isso NÃO é uma dúvida, é o comportamento seguro já estabelecido pelo
    resto do pipeline (seleção vazia = padrão seguro, `selecao_envio_
    operador_v1.py`)."""
    if _PADRAO_SEM_ASSINATURA.search(texto_sa_lower):
        return False
    return bool(_PADRAO_COM_ASSINATURA.search(texto_sa_lower))


# ---------------------------------------------------------------------
# Destinatários
# ---------------------------------------------------------------------

_PADRAO_DESTINATARIO = re.compile(
    r'\b(?:pro|pra|para)\b\s+(?:o\s+|a\s+)?'
    r'(?P<nome>[^.]+?)'
    r'(?=\s+e\s+(?:pro|pra|para)\b|\s+\b(?:o|a|os|as|com|sem)\b|\s*$)',
    re.IGNORECASE,
)
_PADRAO_SEPARADOR_NOME = re.compile(r',|\be\b', re.IGNORECASE)


def _extrair_destinatarios(texto_sa: str) -> List[str]:
    """Extrai os nomes citados após conectores ('pro'/'pra'/'para'),
    tolerando 1 ou N destinatários na mesma ordem ("pro Fulano e pro
    Beltrano", "para Fulano, Beltrano e Cicrano"). LIMITAÇÃO DECLARADA:
    um segmento de nome é também dividido por ' e ' mesmo sem conector
    repetido (para cobrir "para Fulano e Beltrano") -- um nome próprio
    que legitimamente contivesse a palavra solta "e" seria quebrado
    incorretamente; não coberto nesta versão."""
    nomes: List[str] = []
    for match in _PADRAO_DESTINATARIO.finditer(texto_sa):
        bruto = match.group('nome')
        for pedaco in _PADRAO_SEPARADOR_NOME.split(bruto):
            nome = pedaco.strip(' \t.,;:')
            if nome and nome not in nomes:
                nomes.append(nome)
    return nomes


def _resolver_destinatario(
    nome_citado: str,
    candidatos: Sequence[Tuple[str, str]],
) -> Tuple[Optional[str], Optional[DuvidaInterpretacaoOrdem]]:
    """Critério objetivo e documentado (ver docs/decisoes/interpretar-
    ordem-operador-v1.md):
        1) correspondência EXATA de nome completo normalizado -> match
           inequívoco;
        2) sem exata, correspondência PARCIAL (todo token do nome
           citado presente, em qualquer ordem, nos tokens do nome
           candidato) -- só aceita se resolver para EXATAMENTE 1
           candidato; 0 ou 2+ candidatos vira dúvida, nunca escolha
           arbitrária."""
    nome_norm = _normalizar_nome(nome_citado)
    tokens_citados = frozenset(_tokens(nome_norm))

    exatos = [(cid, nl) for cid, nl in candidatos if _normalizar_nome(nl) == nome_norm]
    if len(exatos) == 1:
        return exatos[0][0], None
    if len(exatos) > 1:
        nomes_legiveis = ', '.join(sorted(nl for _, nl in exatos))
        return None, DuvidaInterpretacaoOrdem(
            codigo='DESTINATARIO_AMBIGUO',
            descricao=(
                f'"{nome_citado}" corresponde a mais de um destinatário com o mesmo nome completo no '
                f'diagnóstico ({nomes_legiveis}) -- escolha explícita necessária.'
            ),
            trecho_ordem=nome_citado,
        )

    parciais = [
        (cid, nl) for cid, nl in candidatos
        if tokens_citados and tokens_citados.issubset(frozenset(_tokens(_normalizar_nome(nl))))
    ]
    if len(parciais) == 1:
        return parciais[0][0], None
    if not parciais:
        return None, DuvidaInterpretacaoOrdem(
            codigo='DESTINATARIO_NAO_ENCONTRADO',
            descricao=f'"{nome_citado}" não corresponde a nenhum destinatário do diagnóstico informado.',
            trecho_ordem=nome_citado,
        )
    nomes_legiveis = ', '.join(sorted(nl for _, nl in parciais))
    return None, DuvidaInterpretacaoOrdem(
        codigo='DESTINATARIO_AMBIGUO',
        descricao=(
            f'"{nome_citado}" corresponde a mais de um destinatário possível no diagnóstico '
            f'({nomes_legiveis}) -- escolha explícita necessária.'
        ),
        trecho_ordem=nome_citado,
    )


# ---------------------------------------------------------------------
# Resolução contra o diagnóstico (linhas -- mesmo formato de
# `selecao_envio_operador_v1._linhas_do_diagnostico`)
# ---------------------------------------------------------------------

def _resolver_cliente(linhas: Sequence[Mapping[str, Optional[str]]]) -> Tuple[Optional[str], Optional[DuvidaInterpretacaoOrdem]]:
    ids = sorted({l['cliente_id'] for l in linhas if l.get('colaborador_id')})
    if len(ids) == 1:
        return ids[0], None
    if not ids:
        return None, DuvidaInterpretacaoOrdem(
            codigo='DIAGNOSTICO_SEM_NECESSIDADE_DE_COLABORADOR',
            descricao='o diagnóstico informado não tem nenhuma necessidade associada a colaborador -- nada para interpretar.',
            trecho_ordem='',
        )
    return None, DuvidaInterpretacaoOrdem(
        codigo='CLIENTE_AMBIGUO_NO_DIAGNOSTICO',
        descricao=(
            f'o diagnóstico informado cobre mais de um cliente ({", ".join(ids)}) e esta versão do '
            f'intérprete só resolve diagnóstico de 1 cliente por vez -- rode a interpretação com o '
            f'diagnóstico de 1 cliente/competência, como as demais CLIs desta missão já fazem.'
        ),
        trecho_ordem='',
    )


def _competencias_do_cliente(linhas: Sequence[Mapping[str, Optional[str]]], cliente_id: str) -> List[str]:
    return sorted({l['competencia_id'] for l in linhas if l['cliente_id'] == cliente_id})


def _resolver_competencia(
    linhas: Sequence[Mapping[str, Optional[str]]],
    cliente_id: str,
    extraida: Optional[_CompetenciaExtraida],
) -> Tuple[Optional[str], Optional[DuvidaInterpretacaoOrdem]]:
    if extraida and extraida.competencia_id:
        return extraida.competencia_id, None

    competencias = _competencias_do_cliente(linhas, cliente_id)

    if extraida and extraida.mes_sem_ano:
        candidatas = sorted(
            c for c in competencias
            if re.match(r'^\d{4}-\d{2}$', c) and int(c.split('-')[1]) == extraida.mes_sem_ano
        )
        if len(candidatas) == 1:
            return candidatas[0], None
        return None, DuvidaInterpretacaoOrdem(
            codigo='COMPETENCIA_AMBIGUA_OU_NAO_ENCONTRADA',
            descricao=(
                f'a ordem cita o mês {extraida.mes_sem_ano:02d} sem ano e o diagnóstico tem '
                f'{len(candidatas)} competência(s) compatível(is) ({", ".join(candidatas) or "nenhuma"}) -- '
                f'não é possível inferir sem ambiguidade.'
            ),
            trecho_ordem='',
        )

    if len(competencias) == 1:
        return competencias[0], None
    return None, DuvidaInterpretacaoOrdem(
        codigo='COMPETENCIA_AUSENTE_E_NAO_INFERIVEL',
        descricao=(
            f'a ordem não cita competência e o diagnóstico tem {len(competencias)} competência(s) '
            f'disponível(is) -- não é possível inferir sem ambiguidade.'
        ),
        trecho_ordem='',
    )


def _candidatos_colaboradores(
    linhas: Sequence[Mapping[str, Optional[str]]],
    cliente_id: str,
    diretorio_nomes: Optional[Mapping[str, str]],
) -> List[Tuple[str, str]]:
    ids = sorted({l['colaborador_id'] for l in linhas if l['cliente_id'] == cliente_id and l.get('colaborador_id')})
    diretorio_nomes = diretorio_nomes or {}
    return [(cid, diretorio_nomes.get(cid, cid)) for cid in ids]


def _resolver_tipo_documental(
    linhas: Sequence[Mapping[str, Optional[str]]],
    cliente_id: str,
    competencia_id: str,
    colaborador_id: str,
    familia: str,
) -> Tuple[Optional[str], Optional[DuvidaInterpretacaoOrdem]]:
    linhas_colaborador = [
        l for l in linhas
        if l['cliente_id'] == cliente_id and l['competencia_id'] == competencia_id
        and l.get('colaborador_id') == colaborador_id
    ]
    candidatos = sorted({l['tipo_documental'] for l in linhas_colaborador if _tipo_documental_bate_na_familia(l['tipo_documental'], familia)})

    if len(candidatos) == 1:
        tipo = candidatos[0]
        linha = next(l for l in linhas_colaborador if l['tipo_documental'] == tipo)
        if linha['situacao'] != 'PRONTO':
            return None, DuvidaInterpretacaoOrdem(
                codigo='DOCUMENTO_NAO_PRONTO',
                descricao=(
                    f'"{tipo}" de {colaborador_id} em {competencia_id} existe no diagnóstico mas não está '
                    f'PRONTO (situação atual: {linha["situacao"]}).'
                ),
                trecho_ordem=tipo,
            )
        return tipo, None

    if not candidatos:
        return None, DuvidaInterpretacaoOrdem(
            codigo='DOCUMENTO_NAO_ENCONTRADO',
            descricao=(
                f'nenhum documento do tipo pedido na ordem foi encontrado no diagnóstico para '
                f'{colaborador_id} em {competencia_id}.'
            ),
            trecho_ordem=familia,
        )

    return None, DuvidaInterpretacaoOrdem(
        codigo='DOCUMENTO_AMBIGUO',
        descricao=(
            f'mais de um tipo documental do diagnóstico corresponde à palavra usada na ordem '
            f'({", ".join(candidatos)}) para {colaborador_id} em {competencia_id}.'
        ),
        trecho_ordem=familia,
    )


# ---------------------------------------------------------------------
# Núcleo público
# ---------------------------------------------------------------------

def interpretar_ordem_contra_linhas_diagnostico(
    ordem_texto: str,
    linhas: Sequence[Mapping[str, Optional[str]]],
    *,
    diretorio_nomes: Optional[Mapping[str, str]] = None,
) -> ResultadoInterpretacaoOrdem:
    """Função pura, determinística e IDEMPOTENTE: a mesma `ordem_texto`
    sobre as mesmas `linhas`/`diretorio_nomes` sempre produz o mesmo
    `ResultadoInterpretacaoOrdem` (todo conjunto usado para decisão é
    ordenado explicitamente, nunca depende de ordem de iteração de
    `set`/`dict`). `linhas` é o MESMO formato de `selecao_envio_
    operador_v1._linhas_do_diagnostico`/`selecao_envio_operador_cli.
    _linhas_do_diagnostico_json` (cliente_id/competencia_id/
    tipo_documental/colaborador_id/situacao) -- nunca uma leitura
    paralela do `DiagnosticoPrestacao`.

    NUNCA levanta exceção para dúvida de negócio -- só para entrada
    estruturalmente inválida (`ordem_texto` vazio). Qualquer dúvida
    real vira item de `ResultadoInterpretacaoOrdem.duvidas`, nunca uma
    seleção adivinhada."""
    if not isinstance(ordem_texto, str) or not ordem_texto.strip():
        raise InterpretacaoOrdemOperadorError('ordem_texto deve ser texto não vazio')

    linhas = tuple(linhas)
    texto_sa = _remover_acentos(ordem_texto)
    texto_sa_lower = texto_sa.lower()

    duvidas: List[DuvidaInterpretacaoOrdem] = []

    cliente_id, duvida_cliente = _resolver_cliente(linhas)
    if duvida_cliente:
        duvidas.append(duvida_cliente)

    familia_tipo = _localizar_familia_tipo_documental(texto_sa_lower)
    if familia_tipo is None:
        duvidas.append(DuvidaInterpretacaoOrdem(
            codigo='TIPO_DOCUMENTAL_NAO_IDENTIFICADO',
            descricao=(
                'a ordem não menciona nenhum tipo de documento reconhecido '
                '(ex.: holerite, folha de ponto, extrato, fgts, comprovante...).'
            ),
            trecho_ordem=ordem_texto,
        ))

    competencia_id = None
    if cliente_id is not None:
        competencia_extraida = _extrair_competencia_da_ordem(texto_sa_lower)
        competencia_id, duvida_competencia = _resolver_competencia(linhas, cliente_id, competencia_extraida)
        if duvida_competencia:
            duvidas.append(duvida_competencia)

    nomes_citados = _extrair_destinatarios(texto_sa)
    if not nomes_citados:
        duvidas.append(DuvidaInterpretacaoOrdem(
            codigo='DESTINATARIO_NAO_IDENTIFICADO',
            descricao='a ordem não identifica nenhum destinatário (esperado algo como "pro Fulano"/"para Beltrano").',
            trecho_ordem=ordem_texto,
        ))

    exigir_assinatura = _extrair_exigir_assinatura(texto_sa_lower)

    itens: List[ItemSelecaoEnvioOperador] = []
    if cliente_id is not None and nomes_citados:
        candidatos = _candidatos_colaboradores(linhas, cliente_id, diretorio_nomes)
        for nome_citado in nomes_citados:
            colaborador_id, duvida_nome = _resolver_destinatario(nome_citado, candidatos)
            if duvida_nome:
                duvidas.append(duvida_nome)
                continue
            if competencia_id is None or familia_tipo is None:
                # Já registrado acima (COMPETENCIA_*/TIPO_DOCUMENTAL_NAO_IDENTIFICADO) --
                # não tenta resolver documento sem os dois, para não produzir dúvida redundante.
                continue
            tipo_documental, duvida_tipo = _resolver_tipo_documental(
                linhas, cliente_id, competencia_id, colaborador_id, familia_tipo,
            )
            if duvida_tipo:
                duvidas.append(duvida_tipo)
                continue
            itens.append(ItemSelecaoEnvioOperador(
                cliente_id=cliente_id, competencia_id=competencia_id, colaborador_id=colaborador_id,
                tipos_documentais=(tipo_documental,),
                exigir_assinatura_digital_e_comprovante=exigir_assinatura,
            ))

    if duvidas:
        return ResultadoInterpretacaoOrdem(selecao=None, duvidas=tuple(duvidas))
    return ResultadoInterpretacaoOrdem(selecao=SelecaoEnvioOperador(itens=tuple(itens)), duvidas=())
