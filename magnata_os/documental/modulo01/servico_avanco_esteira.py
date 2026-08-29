"""
Servico de avanco da esteira operacional (Modulo 01, Fase 3).

Responsavel por TODA mutacao de EstadoEsteiraDocumento: criar o estado
inicial de um documento na esteira, avancar de etapa (validando a
maquina de estados de dominio_esteira.py), registrar bloqueio e
registrar resolucao de bloqueio. Nunca muta StatusDocumento nem toca em
RepositorioDocumentos -- essa e a fronteira que mantem o principio
central desta fase (ver dominio_esteira.py).

Toda transicao de etapa/bloqueio/resolucao gera um EventoHistorico
(evento='ESTEIRA_*') no MESMO RepositorioHistorico da Fase 1 -- reuso
deliberado da infraestrutura de auditoria ja construida, em vez de criar
uma segunda tabela de eventos so para a esteira (ver "Historico da
esteira" em MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md). status_anterior e
status_novo desses eventos sao sempre None: eles nunca representam uma
transicao de StatusDocumento, so de EtapaEsteira/SituacaoEsteira.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from .dominio import EventoHistorico
from .dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    MotivoBloqueio,
    ProximaAcao,
    SituacaoEsteira,
    TipoProximaAcao,
    AvancoBloqueadoPorPendencia,
    MotivoSaltoObrigatorio,
    eh_salto_de_etapa,
    validar_transicao_etapa,
)
from .politica_classificacao import DecisaoTransicaoClassificacao
from .politica_identificacao_holerite import DecisaoTransicaoIdentificacao
from .repositorio import RepositorioHistorico
from .repositorio_esteira import RepositorioEstadosEsteira


class EstadoEsteiraInexistente(Exception):
    """Nenhum EstadoEsteiraDocumento encontrado para o documento_id
    informado -- so ocorre se o chamador tentar avancar/bloquear a
    esteira de um documento que nunca entrou nela (ex.: documento legado
    sem estado, ou documento_id inexistente)."""


class NenhumBloqueioAtivo(Exception):
    """Tentativa de resolver bloqueio de um documento cuja situacao
    atual nao e BLOQUEADO."""


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


# Etapas cuja proxima acao e considerada AUTOMATICA: ENTRADA e REGISTRO
# sao sempre executadas pela propria plataforma via
# ServicoEntradaDocumental (Fase 1) + ServicoCriacaoLote (Fase 3), sem
# nenhuma intervencao humana. As etapas seguintes (CLASSIFICACAO em
# diante) ainda nao tem nenhuma automacao implementada nesta fase --
# ver "Nao implementar ainda" em MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md
# -- entao a proxima acao para elas e HUMANA ate uma fase futura
# automatiza-las.
_ETAPAS_AUTOMATIZADAS = frozenset({EtapaEsteira.ENTRADA, EtapaEsteira.REGISTRO})

_DESCRICAO_PROXIMA_ACAO = {
    EtapaEsteira.ENTRADA: 'Confirmar recebimento e avancar automaticamente para REGISTRO',
    EtapaEsteira.REGISTRO: 'Avancar para CLASSIFICACAO (implementacao em fase futura)',
    EtapaEsteira.CLASSIFICACAO: 'Classificar o documento (implementacao em fase futura)',
    EtapaEsteira.SEPARACAO: 'Separar/fatiar o documento (implementacao em fase futura)',
    EtapaEsteira.IDENTIFICACAO: 'Identificar funcionario/cliente vinculado (implementacao em fase futura)',
    EtapaEsteira.VALIDACAO: 'Validar dados extraidos (implementacao em fase futura)',
    EtapaEsteira.MONTAGEM_PACOTE: 'Montar pacote de envio (implementacao em fase futura)',
    EtapaEsteira.DISTRIBUICAO: 'Distribuir/enviar pacote (implementacao em fase futura)',
    EtapaEsteira.CONFIRMACAO: 'Confirmar entrega (implementacao em fase futura)',
    EtapaEsteira.AUDITORIA: 'Nenhuma -- etapa terminal da esteira',
}


def calcular_proxima_acao(
    etapa_atual: EtapaEsteira,
    situacao: SituacaoEsteira,
    motivo_bloqueio: Optional[MotivoBloqueio] = None,
) -> Optional[ProximaAcao]:
    """
    Calcula a proxima acao esperada a partir da etapa e situacao atuais.
    Nunca acessa repositorio -- funcao pura, testavel isoladamente.

    Regras, em ordem de prioridade:
      1. BLOQUEADO -- a proxima acao e sempre resolver o bloqueio;
         AUTOMATICA se o motivo for resolvivel_automaticamente, HUMANA
         caso contrario.
      2. EM_REVISAO -- proxima acao e sempre HUMANA (revisao manual),
         independente da etapa.
      3. AUDITORIA + CONCLUIDO -- etapa terminal, nao ha proxima acao
         (retorna None).
      4. Caso geral -- descricao fixa por etapa; AUTOMATICA para
         ENTRADA/REGISTRO, HUMANA para as demais (ver
         _ETAPAS_AUTOMATIZADAS).
    """
    if situacao == SituacaoEsteira.BLOQUEADO:
        if motivo_bloqueio is None:
            return ProximaAcao(
                acao='Resolver bloqueio (motivo nao informado)',
                tipo=TipoProximaAcao.HUMANA,
                prazo=None,
                responsavel=None,
            )
        tipo = (
            TipoProximaAcao.AUTOMATICA
            if motivo_bloqueio.resolvivel_automaticamente
            else TipoProximaAcao.HUMANA
        )
        return ProximaAcao(
            acao=f'Resolver bloqueio: {motivo_bloqueio.descricao}',
            tipo=tipo,
            prazo=None,
            responsavel=None,
        )

    if situacao == SituacaoEsteira.EM_REVISAO:
        return ProximaAcao(
            acao=f'Revisar documento manualmente na etapa {etapa_atual.value}',
            tipo=TipoProximaAcao.HUMANA,
            prazo=None,
            responsavel=None,
        )

    if etapa_atual == EtapaEsteira.AUDITORIA and situacao == SituacaoEsteira.CONCLUIDO:
        return None

    if etapa_atual == EtapaEsteira.CLASSIFICACAO and situacao == SituacaoEsteira.CONCLUIDO:
        # Achado da auditoria read-only prévia, corrigido aqui: a
        # descrição genérica de _DESCRICAO_PROXIMA_ACAO[CLASSIFICACAO]
        # ("implementacao em fase futura") ficaria enganosa para um
        # documento cuja classificação JÁ ocorreu (via roteamento shadow
        # + politica_classificacao.decidir_transicao_classificacao,
        # caso RESOLVIDA -- ver servico_lote.py). Ajuste mínimo e
        # específico só para esta combinação exata etapa+situação --
        # NUNCA marca a etapa como automática de forma geral (não altera
        # _ETAPAS_AUTOMATIZADAS) nem afirma que o PROCESSAMENTO
        # posterior (fatiamento, vínculo, distribuição) é automático.
        return ProximaAcao(
            acao=(
                'Classificação concluída -- próxima etapa do fluxo '
                'documental ainda não implementada'
            ),
            tipo=TipoProximaAcao.HUMANA,
            prazo=None,
            responsavel=None,
        )

    if etapa_atual == EtapaEsteira.IDENTIFICACAO and situacao == SituacaoEsteira.CONCLUIDO:
        # Mesmo ajuste, mesmo motivo, que o já existente para
        # CLASSIFICACAO+CONCLUIDO acima: a descrição genérica de
        # _DESCRICAO_PROXIMA_ACAO[IDENTIFICACAO] ficaria enganosa para um
        # documento cuja identificação de colaborador JÁ ocorreu (via
        # politica_identificacao_holerite.decidir_transicao_identificacao,
        # caso RESOLVIDA -- ver servico_lote.py). Texto deliberadamente
        # não afirma que a etapa seguinte (VALIDACAO) já é automática --
        # só que a identificação em si terminou. NUNCA marca a etapa
        # como automática de forma geral (não altera
        # _ETAPAS_AUTOMATIZADAS).
        return ProximaAcao(
            acao='Identificação concluída -- validação documental pendente',
            tipo=TipoProximaAcao.HUMANA,
            prazo=None,
            responsavel=None,
        )

    tipo = TipoProximaAcao.AUTOMATICA if etapa_atual in _ETAPAS_AUTOMATIZADAS else TipoProximaAcao.HUMANA
    return ProximaAcao(acao=_DESCRICAO_PROXIMA_ACAO[etapa_atual], tipo=tipo, prazo=None, responsavel=None)


class ServicoAvancoEsteira:
    """Orquestra toda mutacao de EstadoEsteiraDocumento."""

    def __init__(
        self,
        repositorio_estados: RepositorioEstadosEsteira,
        repositorio_historico: RepositorioHistorico,
        relogio: Callable[[], datetime] = _relogio_padrao,
    ) -> None:
        self._estados = repositorio_estados
        self._historico = repositorio_historico
        self._relogio = relogio

    def criar_estado_inicial(
        self,
        documento_id: str,
        lote_id: Optional[str],
        correlation_id: str,
        etapa_inicial: EtapaEsteira = EtapaEsteira.ENTRADA,
        situacao_inicial: SituacaoEsteira = SituacaoEsteira.CONCLUIDO,
    ) -> Tuple[EstadoEsteiraDocumento, bool]:
        """
        Cria o primeiro EstadoEsteiraDocumento de um documento, se ainda
        nao existir um. Atomico via
        RepositorioEstadosEsteira.criar_se_ausente -- sob chamadas
        concorrentes para o mesmo documento_id (ex.: duas tentativas de
        lote com o mesmo conteudo, uma delas simultanea), exatamente uma
        cria o estado; a outra recebe o estado ja existente de volta
        (criado=False), sinal de que este documento e uma duplicidade
        (do mesmo lote ou de um lote anterior -- ver servico_lote.py).
        Retorna (estado, criado).
        """
        agora = self._relogio()

        def _fabricar() -> EstadoEsteiraDocumento:
            return EstadoEsteiraDocumento(
                documento_id=documento_id,
                lote_id=lote_id,
                etapa_atual=etapa_inicial,
                situacao=situacao_inicial,
                motivo_bloqueio=None,
                proxima_acao=calcular_proxima_acao(etapa_inicial, situacao_inicial),
                entrou_na_etapa_em=agora,
                atualizado_em=agora,
                correlation_id=correlation_id,
            )

        estado, criado = self._estados.criar_se_ausente(documento_id, _fabricar)
        if criado:
            self._registrar_evento(
                documento_id, 'ESTEIRA_ESTADO_INICIAL_CRIADO', correlation_id, agora,
                detalhes={'etapa_inicial': etapa_inicial.value, 'situacao_inicial': situacao_inicial.value,
                          'lote_id': lote_id},
            )
        return estado, criado

    def avancar_etapa(
        self,
        documento_id: str,
        nova_etapa: EtapaEsteira,
        correlation_id: str,
        situacao_nova_etapa: SituacaoEsteira = SituacaoEsteira.AGUARDANDO,
        motivo_transicao: Optional[str] = None,
    ) -> EstadoEsteiraDocumento:
        """
        Avanca o documento para `nova_etapa`. Valida a transicao contra
        a politica TRANSICOES_ETAPA_PERMITIDAS (dominio_esteira.py --
        um grafo explicito, nao mais uma sequencia linear obrigatoria)
        e impede qualquer avanco enquanto situacao == BLOQUEADO (levanta
        AvancoBloqueadoPorPendencia) -- o bloqueio precisa ser resolvido
        primeiro via resolver_bloqueio().

        Quando a transicao PULA uma ou mais etapas intermediarias da
        ordem canonica (ver eh_salto_de_etapa -- ex.:
        CLASSIFICACAO -> VALIDACAO, ou CLASSIFICACAO -> AUDITORIA para
        duplicidade/descarte controlado), `motivo_transicao` e
        OBRIGATORIO -- levanta MotivoSaltoObrigatorio se ausente ou
        vazio. Para uma transicao "passo a passo" comum (destino e a
        proxima etapa imediata da ordem canonica), `motivo_transicao` e
        opcional. Em qualquer caso, `motivo_transicao` (quando
        informado) e sempre registrado no evento de auditoria.

        Registra saida da etapa anterior e entrada na nova via um unico
        evento ESTEIRA_* no historico (Fase 1).
        """
        estado_atual = self._buscar_estado_ou_levantar(documento_id)

        if estado_atual.situacao == SituacaoEsteira.BLOQUEADO:
            raise AvancoBloqueadoPorPendencia(
                f'documento_id={documento_id} possui bloqueio ativo '
                f'(codigo={estado_atual.motivo_bloqueio.codigo if estado_atual.motivo_bloqueio else "?"}) '
                f'-- resolva o bloqueio antes de avancar de etapa.'
            )

        validar_transicao_etapa(estado_atual.etapa_atual, nova_etapa)

        eh_salto = eh_salto_de_etapa(estado_atual.etapa_atual, nova_etapa)
        if eh_salto and not (motivo_transicao and motivo_transicao.strip()):
            raise MotivoSaltoObrigatorio(
                f'Transicao {estado_atual.etapa_atual.value} -> {nova_etapa.value} pula etapa(s) '
                f'intermediaria(s) da ordem canonica -- motivo_transicao e obrigatorio para '
                f'justificar o salto (documento_id={documento_id}).'
            )

        agora = self._relogio()
        novo_estado = EstadoEsteiraDocumento(
            documento_id=estado_atual.documento_id,
            lote_id=estado_atual.lote_id,
            etapa_atual=nova_etapa,
            situacao=situacao_nova_etapa,
            motivo_bloqueio=None,
            proxima_acao=calcular_proxima_acao(nova_etapa, situacao_nova_etapa),
            entrou_na_etapa_em=agora,
            atualizado_em=agora,
            correlation_id=correlation_id,
        )
        self._estados.salvar(novo_estado)
        self._registrar_evento(
            documento_id, 'ESTEIRA_ETAPA_AVANCADA', correlation_id, agora,
            detalhes={
                'etapa_anterior': estado_atual.etapa_atual.value,
                'etapa_nova': nova_etapa.value,
                'situacao_nova': situacao_nova_etapa.value,
                'eh_salto': eh_salto,
                'motivo_transicao': motivo_transicao,
            },
        )
        return novo_estado

    def aplicar_resultado_classificacao(
        self,
        documento_id: str,
        decisao_transicao: DecisaoTransicaoClassificacao,
        correlation_id: str,
    ) -> Optional[EstadoEsteiraDocumento]:
        """Aplica o resultado de `politica_classificacao.
        decidir_transicao_classificacao` -- avança REGISTRO->CLASSIFICACAO
        e, quando necessário, registra bloqueio, reutilizando 100% da
        mecânica já existente (`avancar_etapa`/`registrar_bloqueio`
        acima). NÃO reimplementa transição, persistência nem evento --
        só compõe as duas chamadas já existentes conforme a decisão pura
        recebida.

        Retorna `None` sem fazer nada se `decisao_transicao.deve_avancar`
        for `False` (ex.: shadow com erro técnico ou não executado --
        nada estruturado para registrar; ver `politica_classificacao.py`
        e `servico_lote.py`).

        Falha após bloqueio parcial (mesmo achado e mesma correção já
        aplicados em `aplicar_resultado_identificacao`, ver esse
        método): quando `deve_bloquear=True`, a situação transitória
        passada a `avancar_etapa` já é `BLOQUEADO` (nunca `AGUARDANDO`)
        -- se `registrar_bloqueio` (chamado em seguida) falhar por
        qualquer motivo, o estado já persistido por `avancar_etapa`
        fica `CLASSIFICACAO/BLOQUEADO` (só com `motivo_bloqueio=None`
        temporariamente), nunca `CLASSIFICACAO/AGUARDANDO` -- que
        `calcular_proxima_acao` traduziria erroneamente como "ainda não
        implementado", escondendo um documento que na verdade precisa
        de revisão humana. `avancar_etapa` já bloqueia novo avanço
        quando `situacao == BLOQUEADO` (`AvancoBloqueadoPorPendencia`) e
        `calcular_proxima_acao` já trata `BLOQUEADO` com
        `motivo_bloqueio=None` como "Resolver bloqueio (motivo não
        informado)" -- nenhum estado novo foi inventado, só a ordem dos
        dois valores possíveis foi invertida para a mais segura. A
        situação FINAL do documento continua sendo sempre a que
        `registrar_bloqueio` produz (com o motivo estruturado correto),
        nunca a transitória.
        """
        if not decisao_transicao.deve_avancar:
            return None

        situacao_transitoria = (
            SituacaoEsteira.BLOQUEADO if decisao_transicao.deve_bloquear
            else decisao_transicao.situacao_classificacao
        )
        novo_estado = self.avancar_etapa(
            documento_id, EtapaEsteira.CLASSIFICACAO, correlation_id,
            situacao_nova_etapa=situacao_transitoria,
            motivo_transicao=decisao_transicao.motivo_transicao,
        )

        if decisao_transicao.deve_bloquear:
            novo_estado = self.registrar_bloqueio(
                documento_id, decisao_transicao.motivo_bloqueio, correlation_id,
            )

        return novo_estado

    def aplicar_resultado_identificacao(
        self,
        documento_id: str,
        decisao_transicao: DecisaoTransicaoIdentificacao,
        correlation_id: str,
    ) -> Optional[EstadoEsteiraDocumento]:
        """Aplica o resultado de `politica_identificacao_holerite.
        decidir_transicao_identificacao` -- avança
        CLASSIFICACAO->IDENTIFICACAO e, quando necessário, registra
        bloqueio, reutilizando 100% da mecânica já existente
        (`avancar_etapa`/`registrar_bloqueio` acima). NÃO reimplementa
        transição, persistência nem evento -- só compõe as duas
        chamadas já existentes conforme a decisão pura recebida. Mesmo
        formato de `aplicar_resultado_classificacao` acima.

        CLASSIFICACAO -> IDENTIFICACAO pula SEPARACAO na ordem canônica
        (`eh_salto_de_etapa`, dominio_esteira.py) -- por isso
        `motivo_transicao` é OBRIGATÓRIO nesta transição, e todo motivo
        produzido por `decidir_transicao_identificacao` já é uma string
        não vazia (ver politica_identificacao_holerite.py), nunca None
        nem vazio quando `deve_avancar=True`.

        Retorna `None` sem fazer nada se `decisao_transicao.deve_avancar`
        for `False` (ex.: identificação não elegível/não aplicável --
        nada estruturado para registrar; ver servico_lote.py).

        Falha após bloqueio parcial (achado da revisão final): quando
        `deve_bloquear=True`, a situação transitória passada a
        `avancar_etapa` já é `BLOQUEADO` (nunca `AGUARDANDO`) -- se
        `registrar_bloqueio` (chamado em seguida) falhar por qualquer
        motivo, o estado já persistido por `avancar_etapa` fica
        `IDENTIFICACAO/BLOQUEADO` (só com `motivo_bloqueio=None`
        temporariamente), nunca `IDENTIFICACAO/AGUARDANDO` -- que
        `calcular_proxima_acao` traduziria erroneamente como "ainda não
        implementado", escondendo um documento que na verdade precisa
        de revisão humana. `avancar_etapa` já bloqueia novo avanço
        quando `situacao == BLOQUEADO` (`AvancoBloqueadoPorPendencia`) e
        `calcular_proxima_acao` já trata `BLOQUEADO` com
        `motivo_bloqueio=None` como "Resolver bloqueio (motivo não
        informado)" -- nenhum estado novo foi inventado, só a ordem dos
        dois valores possíveis foi invertida para a mais segura.
        """
        if not decisao_transicao.deve_avancar:
            return None

        situacao_transitoria = (
            SituacaoEsteira.BLOQUEADO if decisao_transicao.deve_bloquear
            else decisao_transicao.situacao_identificacao
        )
        novo_estado = self.avancar_etapa(
            documento_id, EtapaEsteira.IDENTIFICACAO, correlation_id,
            situacao_nova_etapa=situacao_transitoria,
            motivo_transicao=decisao_transicao.motivo_transicao,
        )

        if decisao_transicao.deve_bloquear:
            novo_estado = self.registrar_bloqueio(
                documento_id, decisao_transicao.motivo_bloqueio, correlation_id,
            )

        return novo_estado

    def registrar_bloqueio(
        self, documento_id: str, motivo: MotivoBloqueio, correlation_id: str,
    ) -> EstadoEsteiraDocumento:
        """Marca o documento como BLOQUEADO na etapa atual (a etapa NAO
        muda -- bloqueio e sempre dentro da etapa corrente), com o
        motivo estruturado informado. Qualquer avanco de etapa fica
        impedido ate resolver_bloqueio()."""
        estado_atual = self._buscar_estado_ou_levantar(documento_id)
        agora = self._relogio()
        novo_estado = EstadoEsteiraDocumento(
            documento_id=estado_atual.documento_id,
            lote_id=estado_atual.lote_id,
            etapa_atual=estado_atual.etapa_atual,
            situacao=SituacaoEsteira.BLOQUEADO,
            motivo_bloqueio=motivo,
            proxima_acao=calcular_proxima_acao(estado_atual.etapa_atual, SituacaoEsteira.BLOQUEADO, motivo),
            entrou_na_etapa_em=estado_atual.entrou_na_etapa_em,
            atualizado_em=agora,
            correlation_id=correlation_id,
        )
        self._estados.salvar(novo_estado)
        self._registrar_evento(
            documento_id, 'ESTEIRA_BLOQUEIO_REGISTRADO', correlation_id, agora,
            detalhes={
                'etapa': estado_atual.etapa_atual.value,
                'motivo_codigo': motivo.codigo,
                'motivo_descricao': motivo.descricao,
                'motivo_detalhe_tecnico': motivo.detalhe_tecnico,
                'resolvivel_automaticamente': motivo.resolvivel_automaticamente,
            },
        )
        return novo_estado

    def resolver_bloqueio(
        self,
        documento_id: str,
        correlation_id: str,
        situacao_pos_resolucao: SituacaoEsteira = SituacaoEsteira.AGUARDANDO,
    ) -> EstadoEsteiraDocumento:
        """Limpa o bloqueio ativo (motivo_bloqueio=None) e devolve o
        documento a `situacao_pos_resolucao` na MESMA etapa -- resolver
        um bloqueio nunca avanca etapa por si so; um avancar_etapa()
        separado e sempre necessario depois, se for o caso. Levanta
        NenhumBloqueioAtivo se a situacao atual nao for BLOQUEADO."""
        estado_atual = self._buscar_estado_ou_levantar(documento_id)
        if estado_atual.situacao != SituacaoEsteira.BLOQUEADO:
            raise NenhumBloqueioAtivo(
                f'documento_id={documento_id} nao possui bloqueio ativo '
                f'(situacao atual={estado_atual.situacao.value}).'
            )

        agora = self._relogio()
        motivo_resolvido = estado_atual.motivo_bloqueio
        novo_estado = EstadoEsteiraDocumento(
            documento_id=estado_atual.documento_id,
            lote_id=estado_atual.lote_id,
            etapa_atual=estado_atual.etapa_atual,
            situacao=situacao_pos_resolucao,
            motivo_bloqueio=None,
            proxima_acao=calcular_proxima_acao(estado_atual.etapa_atual, situacao_pos_resolucao),
            entrou_na_etapa_em=estado_atual.entrou_na_etapa_em,
            atualizado_em=agora,
            correlation_id=correlation_id,
        )
        self._estados.salvar(novo_estado)
        self._registrar_evento(
            documento_id, 'ESTEIRA_BLOQUEIO_RESOLVIDO', correlation_id, agora,
            detalhes={
                'etapa': estado_atual.etapa_atual.value,
                'motivo_codigo_resolvido': motivo_resolvido.codigo if motivo_resolvido else None,
                'situacao_pos_resolucao': situacao_pos_resolucao.value,
            },
        )
        return novo_estado

    def _buscar_estado_ou_levantar(self, documento_id: str) -> EstadoEsteiraDocumento:
        estado = self._estados.buscar_por_documento_id(documento_id)
        if estado is None:
            raise EstadoEsteiraInexistente(
                f'Nenhum EstadoEsteiraDocumento para documento_id={documento_id} -- documento nunca '
                f'entrou na esteira (pode ser um documento legado, anterior a Fase 3).'
            )
        return estado

    def _registrar_evento(
        self, documento_id: str, evento: str, correlation_id: str, quando: datetime, detalhes: dict,
    ) -> None:
        """Best-effort: uma falha ao registrar o evento de auditoria da
        esteira NAO desfaz a mutacao de EstadoEsteiraDocumento ja salva
        (mesma filosofia de "Documento nunca e removido" da Fase 1 --
        aqui aplicada ao estado da esteira). Se o historico estiver
        indisponivel, a mutacao principal ja aconteceu e permanece
        valida; so a trilha de auditoria fica incompleta para este
        evento."""
        try:
            self._historico.registrar(EventoHistorico(
                documento_id=documento_id,
                evento=evento,
                status_anterior=None,
                status_novo=None,
                timestamp=quando,
                correlation_id=correlation_id,
                detalhes=detalhes,
            ))
        except Exception:
            pass
