"""Aplicação IDEMPOTENTE dos eventos canônicos (missão "CAPTURA
AUTOMÁTICA DE VÍNCULO E ALOCAÇÃO V1") sobre um repositório real
(`RepositorioAlocacaoPostgres`/`RepositorioAlocacaoSQLite` -- ambos
expõem a mesma superfície mínima usada aqui: `registrar_vinculo`,
`vinculo_mais_recente_de`, `encerrar_vinculo`, `registrar_alocacao`,
`alocacao_mais_recente_de`, `encerrar_alocacao` -- duck-typed, nenhum
Protocol formal novo, mesma disciplina de `resolucao.py`).

Idempotência por IDENTIFICADOR REAL já existente -- nunca uma chave
paralela nova: para Vínculo, `(colaborador_id, aberto/fechado, data)`
já existente na própria tabela; para Alocação,
`(vinculo_trabalhista_id, posto_id, aberto/fechado, data)`. Reprocessar
o MESMO evento duas vezes nunca duplica linha nem fecha duas vezes --
a segunda chamada reconhece que já foi aplicado e devolve o mesmo id,
sem tocar o banco de novo.

Conflito temporal (evento diverge de um registro já existente) e
evento fora de ordem (pressupõe estado que não existe) NUNCA são
mascarados -- sempre levantam exceção explícita (`eventos.py`) para
quem orquestra decidir (retry, fila de exceção humana, etc.); esta
camada nunca decide sozinha "o que fazer" com um conflito, só o
detecta e recusa aplicar silenciosamente."""
from __future__ import annotations

import uuid

from .eventos import (
    AlocacaoEncerrada,
    AlocacaoIniciada,
    ConflitoTemporalEventoError,
    EventoForaDeOrdemError,
    VinculoEncerrado,
    VinculoIniciado,
)


def _novo_id(prefixo: str) -> str:
    return f'{prefixo}-{uuid.uuid4().hex}'


def aplicar_vinculo_iniciado(repo, evento: VinculoIniciado) -> str:
    """Idempotente -- devolve o `id` do vínculo (novo ou já existente)."""
    recente = repo.vinculo_mais_recente_de(evento.colaborador_id)
    if recente is not None and recente.data_desligamento is None:
        if recente.data_admissao == evento.data_efetiva:
            return recente.id  # mesmo evento, já aplicado -- no-op
        raise ConflitoTemporalEventoError(
            f'colaborador ja tem vinculo aberto desde {recente.data_admissao}; '
            f'evento pede nova admissao em {evento.data_efetiva}'
        )
    # Sem vínculo aberto (nunca existiu, ou já encerrado -- readmissão
    # legítima) -- cria um vínculo NOVO, nunca reaproveita o antigo. A
    # própria constraint EXCLUDE do banco protege contra sobreposição
    # com um vínculo encerrado cujo período intersecte a nova data
    # (proteção em profundidade -- nunca reimplementada aqui).
    vinculo_id = _novo_id('vinculo')
    repo.registrar_vinculo(vinculo_id, evento.colaborador_id, evento.data_efetiva)
    return vinculo_id


def aplicar_vinculo_encerrado(repo, evento: VinculoEncerrado) -> str:
    """Idempotente -- devolve o `id` do vínculo encerrado."""
    recente = repo.vinculo_mais_recente_de(evento.colaborador_id)
    if recente is None:
        raise EventoForaDeOrdemError(
            f'evento de encerramento sem nenhum vinculo previamente registrado '
            f'para este colaborador')
    if recente.data_desligamento is not None:
        if recente.data_desligamento == evento.data_efetiva:
            return recente.id  # já aplicado -- no-op
        raise ConflitoTemporalEventoError(
            f'vinculo ja encerrado em {recente.data_desligamento}; '
            f'evento pede encerramento em {evento.data_efetiva}'
        )
    if evento.data_efetiva < recente.data_admissao:
        raise ConflitoTemporalEventoError(
            f'data de encerramento {evento.data_efetiva} anterior a admissao {recente.data_admissao}'
        )
    repo.encerrar_vinculo(evento.colaborador_id, evento.data_efetiva)
    return recente.id


def aplicar_alocacao_iniciada(repo, evento: AlocacaoIniciada) -> str:
    """Idempotente -- exige vínculo já ABERTO para o colaborador (nunca
    infere um vínculo; se não existir ou já estiver encerrado, é evento
    fora de ordem -- ex.: alocação chegando antes da admissão, ou depois
    do desligamento)."""
    vinculo = repo.vinculo_mais_recente_de(evento.colaborador_id)
    if vinculo is None or vinculo.data_desligamento is not None:
        raise EventoForaDeOrdemError(
            f'colaborador sem vinculo aberto -- alocacao nao pode ser registrada '
            f'antes da admissao nem apos o desligamento')
    recente = repo.alocacao_mais_recente_de(vinculo.id, evento.posto_id)
    if recente is not None and recente.vigente_ate is None:
        if recente.vigente_de == evento.data_efetiva:
            return recente.id  # já aplicado -- no-op
        raise ConflitoTemporalEventoError(
            f'ja existe alocacao aberta neste posto desde {recente.vigente_de}; '
            f'evento pede novo inicio em {evento.data_efetiva}'
        )
    alocacao_id = _novo_id('alocacao')
    repo.registrar_alocacao(alocacao_id, vinculo.id, evento.posto_id, evento.data_efetiva)
    return alocacao_id


def aplicar_alocacao_encerrada(repo, evento: AlocacaoEncerrada) -> str:
    """Idempotente -- fecha só a alocação DAQUELE posto (rateio em
    outros postos do mesmo vínculo nunca é afetado)."""
    vinculo = repo.vinculo_mais_recente_de(evento.colaborador_id)
    if vinculo is None:
        raise EventoForaDeOrdemError('colaborador sem nenhum vinculo registrado')
    recente = repo.alocacao_mais_recente_de(vinculo.id, evento.posto_id)
    if recente is None:
        raise EventoForaDeOrdemError(
            f'evento de encerramento de alocacao sem alocacao previamente '
            f'registrada para este posto')
    if recente.vigente_ate is not None:
        if recente.vigente_ate == evento.data_efetiva:
            return recente.id  # já aplicado -- no-op
        raise ConflitoTemporalEventoError(
            f'alocacao ja encerrada em {recente.vigente_ate}; '
            f'evento pede encerramento em {evento.data_efetiva}'
        )
    if evento.data_efetiva < recente.vigente_de:
        raise ConflitoTemporalEventoError(
            f'data de encerramento {evento.data_efetiva} anterior ao inicio {recente.vigente_de}'
        )
    repo.encerrar_alocacao(vinculo.id, evento.posto_id, evento.data_efetiva)
    return recente.id


def aplicar_transferencia(
    repo, colaborador_id: str, posto_antigo: str, posto_novo: str,
    data_efetiva, origem_evidencia: str,
) -> str:
    """Composição de 2 primitivas -- NUNCA um evento de negócio à
    parte: fecha `posto_antigo` e abre `posto_novo` na MESMA data.
    Devolve o id da nova alocação.

    ATÔMICA (missão "REVISÃO OBRIGATÓRIA PR #114 -- ATOMICIDADE DA
    TRANSFERÊNCIA", achado real da revisão independente): as 2
    primitivas rodam dentro de `repo.transacao()`, tudo-ou-nada -- se
    `aplicar_alocacao_iniciada` (abrir B) falhar por qualquer motivo, o
    fechamento de A já feito na MESMA chamada é revertido junto, nunca
    deixando A fechada com B inexistente. Idempotência preservada:
    reprocessar a transferência inteira depois de uma falha (retry)
    funciona normalmente, porque cada primitiva continua checando o
    estado real antes de agir."""
    with repo.transacao():
        aplicar_alocacao_encerrada(
            repo, AlocacaoEncerrada(colaborador_id, posto_antigo, data_efetiva, origem_evidencia))
        return aplicar_alocacao_iniciada(
            repo, AlocacaoIniciada(colaborador_id, posto_novo, data_efetiva, origem_evidencia))
