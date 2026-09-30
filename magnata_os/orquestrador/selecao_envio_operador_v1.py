"""Camada de seleção/curadoria humana -- entre `diagnosticar_prestacao`
(o que está PRONTO, `magnata_os.classificacao.composicao_ciclo_
persistente_prestacao.DiagnosticoPrestacao`) e a composição da Ordem/
distribuição (`wiring_prestacao_distribuicao_documental_shadow.py`,
intocado por este módulo).

Necessidade de negócio (registrada aqui por completo -- não só na
conversa, conforme `/CLAUDE.md` §2): hoje TODA necessidade PRONTA de um
cliente/competência vira Ordem automaticamente (`resultados_aquisicao_
prontos_por_colaborador` + `executar_prestacao_ate_distribuicao_
documental_shadow`), sem nenhuma seleção humana no meio. O operador
quer autonomia total para escolher quais documentos enviar, para quantos
colaboradores, com qual combinação de documentos por colaborador (1 ou
N documentos, 1 ou N destinatários), e se aquele envio específico exige
assinatura digital + comprovante ou não. Este módulo é só o contrato de
dados e a validação PURA dessa seleção -- nunca chama I/O, nunca compõe
Ordem, nunca decide sozinho o preset/política de agrupamento (isso
continua com `politica_preset_distribuicao_documental.resolver_preset`,
vocabulário já existente, nunca duplicado aqui).

Vocabulário reaproveitado, nunca um paralelo novo: `exigir_assinatura`/
`exigir_comprovante` já existem, sempre juntos, em todo preset de
`politica_preset_distribuicao_documental._PRESETS_V1` -- por isso a
seleção do operador usa 1 único campo booleano combinado,
`exigir_assinatura_digital_e_comprovante`, em vez de reintroduzir os 2
campos separados como se fossem uma decisão nova.

Granularidade da seleção: 1 `ItemSelecaoEnvioOperador` = 1 colaborador
(destinatário) + N tipos documentais (`tipo_documental`, o mesmo
vocabulário de `NecessidadeDocumentoPrestacao`) que compõem o pacote
dele. "1 documento para N destinatários" é expresso como N itens (1 por
colaborador), cada um citando o mesmo `tipo_documental` -- nunca um
construto de destinatário múltiplo dentro de 1 item, porque
`OrdemDistribuicaoDocumental` (núcleo genérico) já é, por contrato, de
destinatário único."""
from __future__ import annotations

import dataclasses
from typing import Mapping, Optional, Tuple

__all__ = [
    'SelecaoEnvioOperadorError',
    'ItemSelecaoInvalido',
    'SelecaoApontaParaClienteCompetenciaInexistente',
    'SelecaoApontaParaNecessidadeInexistente',
    'SelecaoApontaParaNecessidadeNaoPronta',
    'ItemSelecaoEnvioOperador',
    'SelecaoEnvioOperador',
    'ItemSelecaoValidada',
    'validar_selecao_contra_diagnostico',
    'validar_selecao_contra_linhas_diagnostico',
]


class SelecaoEnvioOperadorError(ValueError):
    """Erro fail-closed da seleção/curadoria do operador -- nunca
    silencioso, nunca uma tentativa de adivinhar a intenção real."""


class ItemSelecaoInvalido(SelecaoEnvioOperadorError):
    """`ItemSelecaoEnvioOperador`/`SelecaoEnvioOperador` mal formado --
    levantado no próprio `__post_init__`, antes de qualquer validação
    contra o diagnóstico."""


class SelecaoApontaParaClienteCompetenciaInexistente(SelecaoEnvioOperadorError):
    """O par (cliente_id, competencia_id) do item não existe no
    `DiagnosticoPrestacao` informado."""


class SelecaoApontaParaNecessidadeInexistente(SelecaoEnvioOperadorError):
    """O `tipo_documental` pedido não existe, para aquele colaborador,
    dentro do cliente/competência do item -- cobre tanto "colaborador
    não existe no diagnóstico" quanto "documento/tipo não existe para
    esse colaborador"."""


class SelecaoApontaParaNecessidadeNaoPronta(SelecaoEnvioOperadorError):
    """A necessidade existe no diagnóstico, mas `situacao !=
    SituacaoNecessidade.PRONTO` -- nunca vira Ordem a partir de um
    documento que ainda não está pronto para distribuição."""


@dataclasses.dataclass(frozen=True)
class ItemSelecaoEnvioOperador:
    """1 pacote de envio decidido pelo operador: para 1 colaborador
    (`colaborador_id`) de 1 cliente/competência, quais tipos documentais
    entram no pacote (1 = documento único, N = pacote agrupado) e se
    esse envio específico exige assinatura digital + comprovante."""

    cliente_id: str
    competencia_id: str
    colaborador_id: str
    tipos_documentais: Tuple[str, ...]
    exigir_assinatura_digital_e_comprovante: bool

    def __post_init__(self) -> None:
        for campo in ('cliente_id', 'competencia_id', 'colaborador_id'):
            valor = getattr(self, campo)
            if not isinstance(valor, str) or not valor.strip():
                raise ItemSelecaoInvalido(f'{campo} deve ser texto não vazio')
        if not isinstance(self.tipos_documentais, tuple) or not self.tipos_documentais:
            raise ItemSelecaoInvalido('tipos_documentais exige ao menos 1 tipo documental')
        for tipo in self.tipos_documentais:
            if not isinstance(tipo, str) or not tipo.strip():
                raise ItemSelecaoInvalido('tipos_documentais só aceita texto não vazio')
        if len(set(self.tipos_documentais)) != len(self.tipos_documentais):
            raise ItemSelecaoInvalido(
                f'tipos_documentais não pode repetir tipo dentro do mesmo item: {self.tipos_documentais!r}'
            )
        if not isinstance(self.exigir_assinatura_digital_e_comprovante, bool):
            raise ItemSelecaoInvalido('exigir_assinatura_digital_e_comprovante deve ser booleano explícito')


@dataclasses.dataclass(frozen=True)
class SelecaoEnvioOperador:
    """A seleção completa do operador para 1 rodada de curadoria. Uma
    seleção sem itens (`itens=()`) é uma seleção EXPLICITAMENTE vazia --
    o chamador a jusante (`executar_prestacao_selecionada_ate_
    distribuicao_documental_shadow`) trata isso como "zero Ordem", nunca
    como "seleção ausente = manda tudo"."""

    itens: Tuple[ItemSelecaoEnvioOperador, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.itens, tuple):
            raise ItemSelecaoInvalido('itens deve ser uma tupla de ItemSelecaoEnvioOperador')
        for item in self.itens:
            if not isinstance(item, ItemSelecaoEnvioOperador):
                raise ItemSelecaoInvalido(f'item de seleção inválido: {item!r}')
        chaves_vistas = set()
        for item in self.itens:
            chave = (item.cliente_id, item.competencia_id, item.colaborador_id)
            if chave in chaves_vistas:
                raise ItemSelecaoInvalido(
                    f'colaborador {item.colaborador_id!r} repetido em mais de 1 item para '
                    f'cliente={item.cliente_id!r} competencia={item.competencia_id!r} -- '
                    f'combine os tipos documentais num único item para esse colaborador'
                )
            chaves_vistas.add(chave)


@dataclasses.dataclass(frozen=True)
class ItemSelecaoValidada:
    """Saída de `validar_selecao_contra_diagnostico` -- o mesmo item do
    operador, confirmado contra o diagnóstico: cada tipo documental
    citado existe, é do colaborador certo e está `PRONTO`."""

    item: ItemSelecaoEnvioOperador

    @property
    def cliente_id(self) -> str:
        return self.item.cliente_id

    @property
    def competencia_id(self) -> str:
        return self.item.competencia_id

    @property
    def colaborador_id(self) -> str:
        return self.item.colaborador_id

    @property
    def tipos_documentais(self) -> Tuple[str, ...]:
        return self.item.tipos_documentais

    @property
    def exigir_assinatura_digital_e_comprovante(self) -> bool:
        return self.item.exigir_assinatura_digital_e_comprovante


def _linhas_do_diagnostico(diagnostico) -> Tuple[Mapping[str, Optional[str]], ...]:
    """Extrai do `DiagnosticoPrestacao` (dataclasses reais) exatamente
    as mesmas colunas que `DiagnosticoPrestacao.como_dict()` exporia
    para o futuro painel -- só ids/situação, nunca CPF/nome. Usado como
    a ÚNICA fonte de verdade da validação, para que a mesma regra valha
    tanto para o diagnóstico em memória (testes/composição real) quanto
    para o diagnóstico já serializado em JSON (CLI, ver
    `validar_selecao_contra_linhas_diagnostico`)."""
    linhas = []
    for cliente in diagnostico.clientes:
        for diagnostico_necessidade in cliente.necessidades:
            necessidade = diagnostico_necessidade.necessidade
            linhas.append({
                'cliente_id': cliente.cliente.entidade_id,
                'competencia_id': cliente.competencia.entidade_id,
                'tipo_documental': necessidade.tipo_documental,
                'colaborador_id': necessidade.colaborador.entidade_id if necessidade.colaborador else None,
                'situacao': diagnostico_necessidade.situacao.value,
            })
    return tuple(linhas)


def validar_selecao_contra_linhas_diagnostico(
    linhas: Tuple[Mapping[str, Optional[str]], ...],
    selecao: SelecaoEnvioOperador,
) -> Tuple[ItemSelecaoValidada, ...]:
    """Núcleo puro da validação -- opera só sobre `linhas` no mesmo
    formato de `DiagnosticoPrestacao.como_dict()['clientes'][*][
    'necessidades'][*]` (cliente_id/competencia_id/tipo_documental/
    colaborador_id/situacao). Nunca faz I/O; rejeita explicitamente
    (nunca silencioso) qualquer item que aponte para algo que não existe
    ou não está `PRONTO`. Reutilizado tanto por `validar_selecao_
    contra_diagnostico` (dataclasses em memória) quanto pela CLI
    (diagnóstico já em JSON) -- 1 única regra, nunca 2 implementações
    divergentes."""
    indice: dict = {}
    for linha in linhas:
        if linha['colaborador_id'] is None:
            continue  # necessidade de nível cliente -- fora do escopo desta seleção por colaborador
        chave = (linha['cliente_id'], linha['competencia_id'], linha['colaborador_id'], linha['tipo_documental'])
        indice[chave] = linha['situacao']

    validados = []
    for item in selecao.itens:
        for tipo in item.tipos_documentais:
            chave = (item.cliente_id, item.competencia_id, item.colaborador_id, tipo)
            situacao = indice.get(chave)
            if situacao is None:
                raise SelecaoApontaParaNecessidadeInexistente(
                    f'nenhuma necessidade PRONTA nem em outra situação encontrada no diagnóstico para '
                    f'cliente={item.cliente_id!r} competencia={item.competencia_id!r} '
                    f'colaborador={item.colaborador_id!r} tipo_documental={tipo!r}'
                )
            if situacao != 'PRONTO':
                raise SelecaoApontaParaNecessidadeNaoPronta(
                    f'necessidade cliente={item.cliente_id!r} competencia={item.competencia_id!r} '
                    f'colaborador={item.colaborador_id!r} tipo_documental={tipo!r} não está PRONTO '
                    f'(situação atual: {situacao!r})'
                )
        validados.append(ItemSelecaoValidada(item=item))
    return tuple(validados)


def validar_selecao_contra_diagnostico(diagnostico, selecao: SelecaoEnvioOperador) -> Tuple[ItemSelecaoValidada, ...]:
    """Função pura (mission item 2): recebe o `DiagnosticoPrestacao` já
    existente + a `SelecaoEnvioOperador` do operador e devolve só os
    itens selecionados que estão de fato prontos para virar Ordem --
    fail-closed em qualquer seleção que aponte para uma necessidade que
    não está `PRONTO`, ou um documento/colaborador que não existe no
    diagnóstico. Seleção vazia (`selecao.itens == ()`) devolve tupla
    vazia -- nunca um erro, é o modo seguro por padrão."""
    return validar_selecao_contra_linhas_diagnostico(_linhas_do_diagnostico(diagnostico), selecao)
