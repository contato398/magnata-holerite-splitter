"""Painel operacional — Prestação de Contas — V1 (somente leitura).

Dá visibilidade humana ao resultado de `diagnosticar_prestacao`
(`composicao_ciclo_persistente_prestacao.py`) sem exigir olhar log ou
JSON cru. Referência: PR #195 ("painel próprio como interface
operacional futura", ainda não implementado até aqui).

Escopo desta V1 — **decisão explícita**, registrada em
`docs/decisoes/painel-operacional-prestacao-v1.md`: nenhuma rota
Flask, nenhuma infraestrutura nova. Uma função pura que recebe o
`.como_dict()` já produzido por `DiagnosticoPrestacao` (contrato que o
próprio módulo de diagnóstico já documenta como "consumível pelo
futuro painel") e devolve Markdown legível. Zero escrita, zero ação,
zero botão — só leitura e formatação. Reaproveitável tanto por uma
rota Flask futura (`return Response(renderizar(...), mimetype='text/
markdown')`) quanto por uma CLI (`scripts/painel_diagnostico_
prestacao_cli.py`, incluído nesta mesma mudança) sem qualquer
acoplamento a Flask, Airtable ou banco.

Nenhuma linha aqui importa `flask`, driver de banco, cliente S3 ou
cliente do Airtable — só tipos Python puro, seguindo a mesma disciplina
de pureza de domínio do restante de `magnata_os/` (`magnata_os/
CLAUDE.md`).

Nenhum dado pessoal (CPF, nome de colaborador, nome de arquivo) chega
aqui — o próprio contrato de entrada (`DiagnosticoPrestacao.como_dict`)
já garante isso na origem: só ids opacos, hashes e nomes de fonte.
"""

from __future__ import annotations

from typing import Mapping, Sequence


# Legenda das situações de necessidade -- mesmo vocabulário e mesmo
# significado dos docstrings de `SituacaoNecessidade`
# (`composicao_ciclo_persistente_prestacao.py`). Mantida como texto
# estático, não como import do Enum, porque o contrato de entrada desta
# função é o dict (`como_dict()`), não o dataclass -- ver docstring do
# módulo. `test_painel_diagnostico_prestacao.py` cobre que esta lista
# permanece em sincronia com o Enum real.
_LEGENDA_SITUACAO_NECESSIDADE: Mapping[str, str] = {
    'PRONTO': 'há documento elegível (confere cliente, competência, colaborador e tipo).',
    'CONFLITO': 'mais de um documento elegível e distinto para a mesma necessidade -- exige decisão humana.',
    'ENCONTRADO_NAO_ELEGIVEL': 'documento achado e resolvido, mas de outro colaborador/mês/cliente/tipo.',
    'EM_REVISAO': 'documento achado, mas o corredor não conseguiu resolvê-lo com segurança.',
    'ERRO_DE_LEITURA': 'candidato achado, mas o arquivo não pôde ser lido (blob ausente, falha de leitura, PDF sem texto e sem OCR).',
    'AUSENTE': 'nenhum documento nas fontes consultadas.',
    'FONTE_INDISPONIVEL': 'alguma fonte falhou -- ausência não pode ser afirmada.',
    'SEM_FONTE': 'nenhuma fonte de localização configurada.',
}

# Situações em que vale a pena expandir o rastro de localização (as
# demais -- PRONTO e CONFLITO sem ambiguidade de fonte -- já contam a
# história pelos documentos elegíveis/avaliados).
_SITUACOES_QUE_EXIGEM_RASTRO = frozenset({
    'ENCONTRADO_NAO_ELEGIVEL', 'EM_REVISAO', 'ERRO_DE_LEITURA',
    'AUSENTE', 'FONTE_INDISPONIVEL',
})

_MARCADOR_SITUACAO: Mapping[str, str] = {
    'PRONTO': '✅',
    'CONFLITO': '⚠️',
    'ENCONTRADO_NAO_ELEGIVEL': '⚠️',
    'EM_REVISAO': '🟡',
    'ERRO_DE_LEITURA': '🟡',
    'AUSENTE': '⬜',
    'FONTE_INDISPONIVEL': '🟥',
    'SEM_FONTE': '🟥',
}


def renderizar_diagnostico_prestacao_markdown(diagnostico: Mapping[str, object]) -> str:
    """Recebe `DiagnosticoPrestacao.como_dict()` e devolve um relatório
    Markdown legível por humano. Função pura -- nenhuma leitura de
    arquivo, banco ou rede; nenhum efeito colateral."""
    competencia_base = diagnostico.get('competencia_base', '?')
    clientes = list(diagnostico.get('clientes', []) or [])

    linhas = [
        f'# Painel de Diagnóstico -- Prestação de Contas -- {competencia_base}',
        '',
        '_Somente leitura -- reflete o que o ciclo real de Prestação faria,'
        ' sem criar Ordem, autorizar ou enviar nada._',
        '',
    ]
    linhas.append(_resumo_geral(clientes))
    linhas.append('')

    if not clientes:
        linhas.append('_Nenhum cliente na composição desta competência._')
        return '\n'.join(linhas)

    for cliente in clientes:
        linhas.append(_renderizar_cliente(cliente))
        linhas.append('')

    linhas.append(_renderizar_legenda())
    return '\n'.join(linhas)


def _resumo_geral(clientes: Sequence[Mapping[str, object]]) -> str:
    total = len(clientes)
    prontos = sum(1 for c in clientes if c.get('ordem_pronta'))
    bloqueados = total - prontos
    return (
        f'**Resumo:** {total} cliente(s) nesta competência -- '
        f'{prontos} com Ordem pronta, {bloqueados} bloqueado(s)/pendente(s).'
    )


def _renderizar_cliente(cliente: Mapping[str, object]) -> str:
    cliente_id = cliente.get('cliente', '?')
    competencia = cliente.get('competencia', '?')
    estado_pacote = cliente.get('estado_pacote', '?')
    ordem_pronta = bool(cliente.get('ordem_pronta'))
    necessidades = list(cliente.get('necessidades', []) or [])

    marcador = '✅' if ordem_pronta else '⛔'
    linhas = [
        f'## {marcador} Cliente `{cliente_id}` -- competência `{competencia}`',
        '',
        f'- Estado do pacote: **{estado_pacote}**',
        f'- Ordem pronta para sair: **{"SIM" if ordem_pronta else "NÃO"}**',
        f'- Necessidades avaliadas: {len(necessidades)}',
        '',
    ]

    if not necessidades:
        linhas.append('_Nenhuma necessidade documental identificada para este cliente._')
        return '\n'.join(linhas)

    linhas.append('| Tipo documental | Colaborador | Situação | Avaliados | Elegíveis |')
    linhas.append('|---|---|---|---|---|')
    for necessidade in necessidades:
        situacao = str(necessidade.get('situacao', '?'))
        marcador_situacao = _MARCADOR_SITUACAO.get(situacao, '?')
        colaborador = necessidade.get('colaborador') or '_(nível cliente)_'
        avaliados = len(necessidade.get('documentos_avaliados', []) or [])
        elegiveis = len(necessidade.get('documentos_elegiveis', []) or [])
        linhas.append(
            f'| `{necessidade.get("tipo_documental", "?")}` | `{colaborador}` | '
            f'{marcador_situacao} {situacao} | {avaliados} | {elegiveis} |'
        )

    rastros = [
        _renderizar_rastro_necessidade(n) for n in necessidades
        if str(n.get('situacao')) in _SITUACOES_QUE_EXIGEM_RASTRO
    ]
    rastros = [r for r in rastros if r]
    if rastros:
        linhas.append('')
        linhas.append('### Rastro de localização (necessidades sem PRONTO)')
        linhas.extend(rastros)

    return '\n'.join(linhas)


def _renderizar_rastro_necessidade(necessidade: Mapping[str, object]) -> str:
    localizacao = necessidade.get('localizacao')
    tipo = necessidade.get('tipo_documental', '?')
    colaborador = necessidade.get('colaborador') or '(nível cliente)'
    situacao = necessidade.get('situacao', '?')

    cabecalho = f'- **{tipo}** / `{colaborador}` ({situacao})'
    if localizacao is None:
        return cabecalho + ': sem consulta de localização registrada.'

    decisao = localizacao.get('decisao', '?')
    motivo = localizacao.get('motivo', '')
    fonte_selecionada = localizacao.get('fonte_selecionada')
    partes = [f'{cabecalho}: decisão de localização `{decisao}` -- {motivo}']

    consultas = localizacao.get('consultas', []) or []
    if consultas:
        for consulta in consultas:
            fonte = consulta.get('fonte', '?')
            status = consulta.get('status', '?')
            erro_tipo = consulta.get('erro_tipo')
            qtd = len(consulta.get('documento_ids', []) or [])
            extra = f' (erro: {erro_tipo})' if erro_tipo else ''
            partes.append(f'  - fonte `{fonte}`: {status}, {qtd} candidato(s){extra}')

    if fonte_selecionada:
        partes.append(f'  - fonte selecionada: `{fonte_selecionada}`')

    return '\n'.join(partes)


def _renderizar_legenda() -> str:
    linhas = ['---', '', '### Legenda -- situação da necessidade', '']
    for situacao, descricao in _LEGENDA_SITUACAO_NECESSIDADE.items():
        marcador = _MARCADOR_SITUACAO.get(situacao, '?')
        linhas.append(f'- {marcador} **{situacao}**: {descricao}')
    return '\n'.join(linhas)


def renderizar_diagnostico_prestacao_objeto(diagnostico: object) -> str:
    """Conveniência para quem já tem o dataclass `DiagnosticoPrestacao`
    em mãos (uso in-process, sem serializar para JSON antes) -- chama
    `.como_dict()` e delega para `renderizar_diagnostico_prestacao_
    markdown`. Nenhuma lógica de renderização própria."""
    return renderizar_diagnostico_prestacao_markdown(diagnostico.como_dict())
