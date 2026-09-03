"""Repositório de `ResolucaoDocumentalTemporalPonto` (missão "IDENTIDADE
TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1") — interface +
implementação em memória.

GATE DE ATOMICIDADE (obrigatório por esta missão): a resolução temporal
e o evento de auditoria correspondente (reaproveitando `EventoHistorico`/
`RepositorioHistorico`, já existentes — nenhuma tabela de evento nova)
são persistidos como UMA operação — `salvar_com_evento`. Se o registro
do evento falhar, a resolução é DESFEITA (nunca fica um estado de
domínio novo sem o evento de auditoria correspondente) — diferente,
DELIBERADAMENTE, do padrão de compensação de `ServicoEntradaDocumental`
(`servico_entrada.py`), que preserva o Documento mesmo se o Historico
falhar (decisão documentada e válida para aquele caso, mas
explicitamente insuficiente para o gate desta missão — ver
`docs/decisoes/identidade-temporal-ponto-auditoria-v1.md`, seção
"Atomicidade / auditoria"). Aqui: tudo comita, ou tudo é revertido.

GATE DE REPROCESSAMENTO (revisão independente pós-PR #127):
`salvar_com_evento` NUNCA sobrescreve silenciosamente uma resolução já
persistida. Toda chamada é classificada por
`classificar_transicao_resolucao` (`classificacao/resolucao_temporal_
ponto.py`, função pura, única fonte desta decisão) em NOVA/EQUIVALENTE/
ATUALIZACAO/CONFLITO — ver docstrings daquele módulo para a semântica
completa de cada uma. `fabricar_evento` recebe a transição e os dois
valores (anterior/novo) para poder registrar um evento de auditoria
completo — nunca um evento genérico que esconda o que mudou.

Nenhuma dependência de Airtable/Flask/driver de banco neste módulo —
mesma disciplina de `repositorio.py` (Modulo 01)."""
from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional, Protocol

from .dominio import EventoHistorico
from .repositorio import RepositorioHistorico
from magnata_os.classificacao.resolucao_temporal_ponto import (
    ResolucaoDocumentalTemporalPonto,
    TransicaoResolucaoTemporal,
    classificar_transicao_resolucao,
    resolucao_a_persistir_para_transicao,
)

FabricanteEvento = Callable[
    [TransicaoResolucaoTemporal, Optional[ResolucaoDocumentalTemporalPonto], ResolucaoDocumentalTemporalPonto],
    EventoHistorico,
]


class FalhaAuditoriaResolucaoTemporal(Exception):
    """O evento de auditoria falhou ao ser registrado — a resolução
    correspondente foi revertida (nunca persiste sozinha)."""


class RepositorioResolucaoTemporal(Protocol):
    """Contrato que qualquer adapter (memória, Postgres) precisa
    cumprir. `salvar_com_evento` é a ÚNICA forma de escrita — não existe
    um `salvar` isolado sem evento, de propósito (o gate de atomicidade
    não pode ser contornado por quem chama). `fabricar_evento` recebe
    `(transicao, anterior, novo)` — ver `TransicaoResolucaoTemporal`
    para o vocabulário completo."""

    def buscar_por_documento_id(self, documento_id: str) -> Optional[ResolucaoDocumentalTemporalPonto]: ...

    def salvar_com_evento(
        self,
        resolucao: ResolucaoDocumentalTemporalPonto,
        fabricar_evento: FabricanteEvento,
    ) -> TransicaoResolucaoTemporal: ...

    def listar_todos(self) -> List[ResolucaoDocumentalTemporalPonto]: ...


class RepositorioResolucaoTemporalEmMemoria:
    """Implementação em memória — para testes e para esta fase de
    fundação (nenhum Postgres real conectado nesta missão). Protegida
    por lock único: `salvar_com_evento` é atômica — classificação da
    transição, escrita da resolução e registro do evento acontecem sob
    a MESMA seção crítica, com rollback explícito se o evento falhar."""

    def __init__(self, repositorio_historico: RepositorioHistorico) -> None:
        self._por_documento_id: Dict[str, ResolucaoDocumentalTemporalPonto] = {}
        self._repositorio_historico = repositorio_historico
        self._lock = threading.Lock()

    def buscar_por_documento_id(self, documento_id: str) -> Optional[ResolucaoDocumentalTemporalPonto]:
        with self._lock:
            return self._por_documento_id.get(documento_id)

    def salvar_com_evento(
        self,
        resolucao: ResolucaoDocumentalTemporalPonto,
        fabricar_evento: FabricanteEvento,
    ) -> TransicaoResolucaoTemporal:
        with self._lock:
            anterior = self._por_documento_id.get(resolucao.documento_id)
            transicao = classificar_transicao_resolucao(anterior, resolucao)

            if transicao == TransicaoResolucaoTemporal.EQUIVALENTE:
                # Idempotência real: reprocessar o MESMO resultado nunca
                # escreve nada nem gera evento -- nenhum ruído de
                # auditoria para uma repetição exata.
                return transicao

            resolucao_a_persistir = resolucao_a_persistir_para_transicao(transicao, resolucao)
            self._por_documento_id[resolucao.documento_id] = resolucao_a_persistir
            try:
                evento = fabricar_evento(transicao, anterior, resolucao)
                self._repositorio_historico.registrar(evento)
            except Exception as exc:
                # Rollback explícito, na MESMA seção crítica: nunca deixa
                # a resolução nova visível sem o evento de auditoria
                # correspondente -- restaura o estado anterior (ou
                # remove, se não havia nenhum).
                if anterior is None:
                    del self._por_documento_id[resolucao.documento_id]
                else:
                    self._por_documento_id[resolucao.documento_id] = anterior
                raise FalhaAuditoriaResolucaoTemporal(
                    f'Falha ao registrar evento de auditoria para documento_id='
                    f'{resolucao.documento_id!r} -- resolução revertida.'
                ) from exc
            return transicao

    def listar_todos(self) -> List[ResolucaoDocumentalTemporalPonto]:
        with self._lock:
            return list(self._por_documento_id.values())
