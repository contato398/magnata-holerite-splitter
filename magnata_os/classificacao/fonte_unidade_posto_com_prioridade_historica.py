"""Composição PURA de 2 fontes de UNIDADE_POSTO já existentes (missão
"IMPLEMENTAÇÃO ESTRUTURAL DA ENTIDADE alocacao COM VIGÊNCIA HISTÓRICA",
Fase 5: "Airtable pode continuar bridge para dados atuais, mas não como
verdade histórica quando existir alocação persistida").

NUNCA reimplementa nenhuma das 2 fontes -- só decide a ORDEM de
consulta, mesmo espírito de `fonte_inventario_composta.
FonteInventarioPrestacaoComposta` (agrega sem conhecer a origem
concreta de cada fonte). Ambas as fontes precisam implementar o MESMO
Protocol já existente (`vinculo_unidade_prestacao.FonteUnidadePostoPrestacao`)
-- nenhum contrato novo.

Prioridade: `fonte_historica` (tipicamente `RepositorioAlocacaoPostgres`/
`RepositorioAlocacaoSQLite`, `magnata_os/documental/alocacao/`) primeiro
-- quando ela resolve com evidência real de vigência, essa resposta
NUNCA é sobrescrita pelo snapshot corrente do Airtable, mesmo que
divergente. `fonte_corrente` (tipicamente
`FonteUnidadePostoPrestacaoAirtableShadow`) só é consultada quando a
histórica não tem registro (`NAO_ENCONTRADA`) -- nunca quando a
histórica resolve com QUALQUER outro estado (`AMBIGUA`/`CONFLITO`/etc.
também não caem para o fallback, por design: um estado diferente de
NAO_ENCONTRADA já é uma resposta definitiva da fonte histórica, nunca
"tentar a sorte" com outra fonte)."""
from __future__ import annotations

from .contratos import EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao
from .vinculo_unidade_prestacao import FonteUnidadePostoPrestacao


class FonteUnidadePostoPrestacaoComPrioridadeHistorica:
    """Implementa `FonteUnidadePostoPrestacao` combinando uma fonte
    histórica (autoritativa quando tem dado) com uma fonte corrente
    (bridge, só usada na ausência de histórico)."""

    def __init__(
        self,
        fonte_historica: FonteUnidadePostoPrestacao,
        fonte_corrente: FonteUnidadePostoPrestacao,
    ) -> None:
        self._fonte_historica = fonte_historica
        self._fonte_corrente = fonte_corrente

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        resultado_historico = self._fonte_historica.resolver_unidade_posto(colaborador, competencia)
        if resultado_historico.estado != EstadoResolucaoDimensao.NAO_ENCONTRADA:
            return resultado_historico
        return self._fonte_corrente.resolver_unidade_posto(colaborador, competencia)
