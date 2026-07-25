"""
Servico de criacao de lote (Modulo 01, Fase 3).

Ponto de entrada oficial para qualquer entrada NOVA de documentos a
partir desta fase: agrupa N arquivos recebidos juntos (mesma origem,
mesmo correlation_id) num LoteDocumental, delega a cada arquivo
individualmente ao ServicoEntradaDocumental (Fase 1, reaproveitado sem
alteracao) e cria o EstadoEsteiraDocumento inicial de cada um via
ServicoAvancoEsteira (Fase 3).

Principios aplicados:
  - Nenhuma entrada nova criada por este servico fica sem lote_id --
    "cada entrada nova deve possuir lote" e garantido aqui, no unico
    lugar que fabrica lote_id (ver gerar_lote_id, dominio_esteira.py).
    ServicoEntradaDocumental (Fase 1) continua aceitando lote_id=None
    para nao quebrar nenhum chamador existente -- a garantia e de
    CONVENCAO desta fase em diante, nao de um novo parametro obrigatorio
    que quebraria a Fase 1/2 ja mergeadas (ver "Documentos legados" em
    MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md).
  - Duplicidade nunca aborta o lote -- um arquivo cujo conteudo ja foi
    registrado antes (neste lote ou em qualquer lote anterior) e
    marcado `duplicado=True` no resumo, sem interromper o processamento
    dos demais arquivos.
  - Erro isolado nunca aborta o lote -- uma excecao ao processar UM
    arquivo (ex.: arquivo vazio, falha de persistencia) e capturada,
    registrada no item correspondente do resumo, e o loop continua para
    o proximo arquivo.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

from .dominio_esteira import EtapaEsteira, LoteDocumental, SituacaoEsteira, gerar_correlation_id_lote, gerar_lote_id
from .dtos_esteira import ItemResumoLote, ResumoLote
from .repositorio_esteira import RepositorioLotes
from .servico_avanco_esteira import ServicoAvancoEsteira
from .servico_entrada import ServicoEntradaDocumental


@dataclasses.dataclass(frozen=True)
class ArquivoEntradaLote:
    """Um arquivo dentro de uma solicitacao de criacao de lote."""

    conteudo: bytes
    nome_original: str
    mime_type: str
    metadados: Optional[dict] = None


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


class ServicoCriacaoLote:
    """Orquestra a criacao de um LoteDocumental e o registro de cada
    arquivo nele, isolando falha e duplicidade por arquivo."""

    def __init__(
        self,
        repositorio_lotes: RepositorioLotes,
        servico_entrada: ServicoEntradaDocumental,
        servico_avanco_esteira: ServicoAvancoEsteira,
        gerador_lote_id: Callable[[], str] = gerar_lote_id,
        relogio: Callable[[], datetime] = _relogio_padrao,
    ) -> None:
        self._lotes = repositorio_lotes
        self._servico_entrada = servico_entrada
        self._servico_avanco = servico_avanco_esteira
        self._gerar_lote_id = gerador_lote_id
        self._relogio = relogio

    def criar_lote(
        self,
        origem: str,
        arquivos: Sequence[ArquivoEntradaLote],
        correlation_id: Optional[str] = None,
        metadados: Optional[dict] = None,
    ) -> ResumoLote:
        """
        Cria um lote com os arquivos informados. Cada arquivo e
        processado isoladamente: uma falha ou uma duplicidade em um
        arquivo nunca impede o processamento dos demais nem aborta o
        lote como um todo. Retorna um ResumoLote completo, sempre --
        mesmo que todos os arquivos tenham falhado (nesse caso,
        situacao=ERRO).
        """
        correlation_id = correlation_id or gerar_correlation_id_lote()
        agora = self._relogio()
        lote_id = self._gerar_lote_id()

        lote = LoteDocumental(
            lote_id=lote_id,
            origem=origem,
            recebido_em=agora,
            quantidade_arquivos=len(arquivos),
            situacao=SituacaoEsteira.EM_PROCESSAMENTO,
            correlation_id=correlation_id,
            criado_em=agora,
            atualizado_em=agora,
            metadados=metadados or {},
        )
        self._lotes.salvar(lote)

        itens: List[ItemResumoLote] = []
        for arquivo in arquivos:
            itens.append(self._processar_um_arquivo(lote_id, origem, correlation_id, arquivo))

        quantidade_sucesso = sum(1 for i in itens if i.sucesso and not i.duplicado)
        quantidade_duplicados = sum(1 for i in itens if i.sucesso and i.duplicado)
        quantidade_erro = sum(1 for i in itens if not i.sucesso)

        if quantidade_erro == 0:
            situacao_final = SituacaoEsteira.CONCLUIDO
        elif quantidade_erro == len(itens):
            situacao_final = SituacaoEsteira.ERRO
        else:
            situacao_final = SituacaoEsteira.EM_REVISAO  # sucesso parcial -- precisa de olhar humano

        agora_final = self._relogio()
        lote_final = dataclasses.replace(lote, situacao=situacao_final, atualizado_em=agora_final)
        self._lotes.salvar(lote_final)

        return ResumoLote(
            lote_id=lote_id,
            origem=origem,
            correlation_id=correlation_id,
            quantidade_arquivos=len(arquivos),
            quantidade_sucesso=quantidade_sucesso,
            quantidade_duplicados=quantidade_duplicados,
            quantidade_erro=quantidade_erro,
            situacao=situacao_final,
            criado_em=agora,
            itens=tuple(itens),
        )

    def _processar_um_arquivo(
        self, lote_id: str, origem: str, correlation_id: str, arquivo: ArquivoEntradaLote,
    ) -> ItemResumoLote:
        try:
            documento = self._servico_entrada.registrar_entrada(
                arquivo.conteudo, arquivo.nome_original, arquivo.mime_type, origem,
                correlation_id=correlation_id, lote_id=lote_id, metadados=arquivo.metadados,
            )
        except Exception as exc:
            return ItemResumoLote(
                nome_original=arquivo.nome_original, documento_id=None,
                sucesso=False, duplicado=False, erro=str(exc),
            )

        try:
            _estado, criado_agora = self._servico_avanco.criar_estado_inicial(
                documento.documento_id, lote_id, correlation_id,
            )
            if criado_agora:
                # Documento novo na esteira: ServicoEntradaDocumental (Fase 1)
                # ja persistiu o Documento com status REGISTRADO nesta mesma
                # chamada -- a etapa REGISTRO ja esta, de fato, concluida.
                self._servico_avanco.avancar_etapa(
                    documento.documento_id, EtapaEsteira.REGISTRO, correlation_id,
                    situacao_nova_etapa=SituacaoEsteira.CONCLUIDO,
                )
        except Exception as exc:
            return ItemResumoLote(
                nome_original=arquivo.nome_original, documento_id=documento.documento_id,
                sucesso=False, duplicado=False, erro=str(exc),
            )

        return ItemResumoLote(
            nome_original=arquivo.nome_original, documento_id=documento.documento_id,
            sucesso=True, duplicado=not criado_agora, erro=None,
        )
