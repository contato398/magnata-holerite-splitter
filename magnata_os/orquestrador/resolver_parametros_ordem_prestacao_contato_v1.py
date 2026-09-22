"""Implementação real de `ResolverParametrosOrdemPrestacao`
(`wiring_prestacao_distribuicao_documental_shadow.py`) usando o Contato
Canônico de Colaborador V1 (`magnata_os.documental.alocacao.
contato_colaborador`) -- primeira implementação real deste ponto de
extensão; até aqui só existiam fakes de teste com telefone hardcoded
(`test_wiring_prestacao_ate_distribuicao_documental_shadow.py`).

Direção de dependência: `orquestrador` -> `documental.alocacao` --
mesmo sentido já usado por este módulo em relação a
`documental.modulo01` (`RepositorioDocumentos`, `ArmazenamentoArquivos`,
`MaterializadorArquivoLegado`), nunca o inverso.

Responsabilidade ESTRITA deste módulo:
    - resolver `colaborador_id` a partir do MESMO
      `ResultadoAquisicaoPorNecessidade` já usado por
      `montar_ordem_distribuicao_documental_de_prestacao` (reaproveitado,
      nunca reconstruído -- `necessidade.colaborador.entidade_id`);
    - delegar a resolução do contato a `resolver_contato_colaborador_
      para_ordem` (núcleo do domínio, único ponto autorizado a
      decifrar);
    - montar `ParametrosOrdemPrestacao` (contrato existente, assinatura
      intocada) ou `None` (fail-closed).

Nunca:
    - consulta Airtable (nenhum import de cliente Airtable neste
      módulo -- ver `test_resolver_parametros_ordem_prestacao_contato_
      v1.py::test_modulo_nao_importa_airtable_nem_app`);
    - decide qual `preset_id`/`tipo_documento`/`mensagem_texto` usar a
      partir de heurística de tipo documental -- esses valores são
      SEMPRE parâmetros explícitos de quem constrói o resolvedor
      (`construir_resolvedor_parametros_ordem_prestacao_contato_v1`),
      mesma disciplina de `politica_preset_distribuicao_documental.py`;
    - dispara transporte real (nenhum import de módulo de transporte
      -- Evolution, WhatsApp real -- neste módulo)."""
from __future__ import annotations

from typing import Callable, Tuple

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ResultadoAquisicaoPorNecessidade,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RepositorioContatoColaborador,
    resolver_contato_colaborador_para_ordem,
)

from .wiring_prestacao_distribuicao_documental_shadow import (
    ParametrosOrdemPrestacao,
    ResolverParametrosOrdemPrestacao,
)

MensagemTextoPrestacao = Callable[[ReferenciaCanonica, ReferenciaCanonica], str]
"""Callback do chamador para o texto da mensagem -- mesma disciplina
de `destinatario`/`preset_id`/`tipo_documento`: nunca inferido aqui,
sempre decisão explícita de quem monta o resolvedor."""


def construir_resolvedor_parametros_ordem_prestacao_contato_v1(
    *,
    repositorio_contato: RepositorioContatoColaborador,
    chave_fernet: bytes,
    preset_id: str,
    tipo_documento: str,
    montar_mensagem_texto: MensagemTextoPrestacao,
    canal: str = CANAL_WHATSAPP,
) -> ResolverParametrosOrdemPrestacao:
    """Fábrica: fecha sobre as dependências reais (repositório, chave,
    política operacional já decidida pelo chamador) e devolve uma
    função com a MESMA assinatura de `ResolverParametrosOrdemPrestacao`
    -- `executar_prestacao_ate_distribuicao_documental_shadow` nunca
    precisa saber que a implementação usa Contato Canônico de
    Colaborador por baixo.

    Fail-closed, sempre devolvendo `None` (nunca levanta) quando:
    - não há `resultados_aquisicao` (nada a resolver);
    - `necessidade.colaborador` é `None` (ausente -- mesmo critério já
      aplicado por `montar_ordem_distribuicao_documental_de_prestacao`,
      verificado aqui ANTES para nunca chegar a montar uma Ordem sem
      destinatário resolvido);
    - `resolver_contato_colaborador_para_ordem` devolve `None`
      (contato ausente, inválido, ou descriptografia falhou -- ver
      docstring daquela função para os 3 casos)."""

    def _resolver(
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
        resultados_aquisicao: Tuple[ResultadoAquisicaoPorNecessidade, ...],
    ):
        if not resultados_aquisicao:
            return None

        colaborador = resultados_aquisicao[0].necessidade.colaborador
        if colaborador is None:
            return None

        destinatario = resolver_contato_colaborador_para_ordem(
            repositorio_contato, colaborador.entidade_id, canal, chave_fernet,
        )
        if destinatario is None:
            return None

        return ParametrosOrdemPrestacao(
            destinatario=destinatario,
            preset_id=preset_id,
            tipo_documento=tipo_documento,
            mensagem_texto=montar_mensagem_texto(cliente, competencia),
        )

    return _resolver
