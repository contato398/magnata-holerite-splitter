"""Wiring Prestação de Contas -> Distribuição Documental Genérica, V1 shadow.

Elo fino entre `magnata_os.classificacao` (que sabe de Prestação,
necessidade, cliente/competência/colaborador) e o núcleo genérico
`wiring_distribuicao_documental_shadow.py` (que nunca conhece
Prestação -- ver docstring de lá, linhas 29-31). A direção de
dependência é sempre `orquestrador -> classificacao`, nunca o
inverso -- mesmo padrão já usado por `wiring_prestacao_comunicacao_
shadow.py`/`wiring_prestacao_orquestrador_postgres_shadow.py`.

Responsabilidade ESTRITA deste módulo:
    - receber `ResultadoAquisicaoPorNecessidade` já produzidos por
      `adquirir_por_necessidades` (reaproveitados, nunca reconstruídos);
    - preservar `necessidade.colaborador` como `funcionario_id` da Ordem;
    - receber `destinatario` já resolvido (responsabilidade do
      chamador -- este módulo NUNCA resolve telefone, nunca conhece
      Evolution, nunca importa nada de `app.py`);
    - receber `preset_id` e resolver a política operacional via
      `politica_preset_distribuicao_documental.resolver_preset`
      (`preset_id -> política`, nunca `tipo_documento -> política`);
    - montar `ItemDocumentoOrdem`/`OrdemDistribuicaoDocumental`;
    - chamar `materializar_distribuicao_documental_shadow` (núcleo,
      intocado por este módulo).

Nunca:
    - resolve telefone/WhatsApp;
    - gera token;
    - decide `politica_agrupamento`/`exigir_assinatura` a partir de
      `tipo_documento` ou da quantidade de documentos -- essas decisões
      já vêm prontas do preset escolhido pelo chamador;
    - duplica a lógica de resolução/materialização/autorização do
      núcleo genérico;
    - dispara transporte real.

Escopo desta V1: `destinatario` é dependência explícita do chamador.
A composição da fonte real de contato (hoje só existente, de forma
crua, em `app.py`/Airtable -- arquivo protegido, não tocado aqui)
permanece requisito de uma etapa posterior, antes do canário
operacional real (ver ADR correspondente).

DELTA FINAL A-F (Ultraplan "Cliente+Competência -> PENDING"):
`executar_prestacao_ate_distribuicao_documental_shadow` fecha o gap
upstream que faltava -- reutiliza `resultados_aquisicao_prontos_por_
cliente` (Prestação, já faz descoberta+aquisição+readiness reutilizando
`executar_ciclo_prestacao_persistente`'s própria composição interna,
via extração) para obter, por cliente/competência com `pacote.estado ==
PRONTO`, os `ResultadoAquisicaoPorNecessidade` prontos -- e delega a
`materializar_prestacao_distribuicao_documental_shadow` (já existente
acima) só para quem o chamador souber resolver `destinatario`/
`preset_id`/`tipo_documento`/`mensagem_texto` (via `resolver_parametros_
ordem`, nunca inferidos aqui). Cliente sem readiness OU sem parâmetros
resolvidos -- zero Ordem para ele, isolado, nunca contamina os demais.
Não cria `ExecucaoPrestacao`/`execucao_id` novo -- é leitura + gate +
delegação, nada mais.

PONTE ORDEM -> EVENTO CANÔNICO: a função que registra o evento canônico
antes da autorização (`registrar_evento_canonico_ordem_distribuicao_
documental_shadow`) foi EXTRAÍDA para o núcleo genérico
(`wiring_distribuicao_documental_shadow.py`) -- nunca teve dependência
real de Prestação (só `OrdemDistribuicaoDocumental` + `Repositorio
Execucoes`), e mantê-la aqui impediria chamadores genéricos (ex.
`distribuir_documento_v1.py`) de reutilizá-la sem um import
semanticamente estranho. Este módulo apenas reexporta os mesmos nomes
(`EventoCanonicoNaoAguardaGate`, `montar_evento_canonico_ordem_
distribuicao_documental`, `registrar_evento_canonico_ordem_
distribuicao_documental_shadow`) por compatibilidade -- nenhum código
duplicado, nenhuma segunda ponte.
`materializar_prestacao_distribuicao_documental_shadow` continua
chamando essa ponte ANTES de delegar ao núcleo -- nenhum TipoEvento
novo, nenhum motor novo, nenhuma tabela nova, nenhum SQL manual de seed.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime
from typing import Callable, Optional, Tuple

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
    ResultadoAquisicaoPorNecessidade,
    resultados_aquisicao_prontos_por_colaborador,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos
from magnata_os.documental.modulo01.materializador_arquivo import MaterializadorArquivoLegado
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentos

from .autorizacao_gate import RepositorioAutorizacoesGate
from .obrigacao_assinatura import PortaObrigacaoAssinatura
from .politica_preset_distribuicao_documental import resolver_preset
from .repositorio_acoes_execucao_plano_postgres import RepositorioAcoesExecucaoPlanoPostgres
from .repositorio_execucoes import RepositorioExecucoes
from .wiring_distribuicao_documental_shadow import (
    DistribuicaoDocumentalError,
    EventoCanonicoNaoAguardaGate,
    ItemDocumentoOrdem,
    OrdemDistribuicaoDocumental,
    ResultadoDistribuicaoDocumentalShadow,
    materializar_distribuicao_documental_shadow,
    montar_evento_canonico_ordem_distribuicao_documental,
    registrar_evento_canonico_ordem_distribuicao_documental_shadow,
)

_logger = logging.getLogger(__name__)

EVENTO_CLIENTE_FALHOU_DISTRIBUICAO_DOCUMENTAL = 'cliente_falhou_distribuicao_documental'
"""Nome de evento ESTÁVEL para observabilidade (mesma disciplina de
`composicao_ciclo_persistente_prestacao.py`, `EVENTO_CORREDOR_FALHOU`)
-- nunca `str(exc)` cru, nunca dado pessoal, só identificadores
sanitizados (`cliente`/`competencia` já são `entidade_id` opacos)."""

__all__ = [
    'PrestacaoDistribuicaoDocumentalError',
    'ColaboradorAusenteNaNecessidade',
    'ColaboradorDivergenteEntreDocumentos',
    'EventoCanonicoNaoAguardaGate',
    'montar_ordem_distribuicao_documental_de_prestacao',
    'montar_evento_canonico_ordem_distribuicao_documental',
    'registrar_evento_canonico_ordem_distribuicao_documental_shadow',
    'materializar_prestacao_distribuicao_documental_shadow',
    'ParametrosOrdemPrestacao',
    'ResolverParametrosOrdemPrestacao',
    'executar_prestacao_ate_distribuicao_documental_shadow',
]


class PrestacaoDistribuicaoDocumentalError(ValueError):
    """Erro fail-closed da composição Prestação -> Distribuição
    Documental."""


class ColaboradorAusenteNaNecessidade(PrestacaoDistribuicaoDocumentalError):
    """`necessidade.colaborador` é `None` -- esta composição exige
    granularidade por colaborador (nunca infere um `funcionario_id` a
    partir de heurística/nome)."""


class ColaboradorDivergenteEntreDocumentos(PrestacaoDistribuicaoDocumentalError):
    """Os `ResultadoAquisicaoPorNecessidade` informados pertencem a
    colaboradores diferentes -- uma única Ordem nunca mistura
    documentos de mais de 1 colaborador."""


def montar_ordem_distribuicao_documental_de_prestacao(
    *,
    resultados_aquisicao: Tuple[ResultadoAquisicaoPorNecessidade, ...],
    destinatario: str,
    preset_id: str,
    tipo_documento: str,
    mensagem_texto: str,
) -> OrdemDistribuicaoDocumental:
    """Monta a Ordem sem nenhum I/O -- pura composição de dados já
    resolvidos por `adquirir_por_necessidades` (reaproveitado, nunca
    reconstruído) e pelo preset escolhido pelo chamador.

    `tipo_documento` é sempre parâmetro explícito do chamador, nunca
    derivado por este módulo a partir de `necessidade.tipo_documental`
    -- para N=2 (ex.: pacote Holerite+Ponto) o valor correto
    (`HOLERITE_FOLHA_PONTO`) não é literalmente o `tipo_documental` de
    nenhuma das 2 necessidades isoladas, e decidir isso aqui
    reintroduziria conhecimento de tipo documental fora do adapter
    legado -- exatamente o acoplamento que esta composição deve evitar."""
    if not resultados_aquisicao:
        raise PrestacaoDistribuicaoDocumentalError(
            'ao menos 1 ResultadoAquisicaoPorNecessidade é obrigatório'
        )

    colaboradores_vistos: set = set()
    itens = []
    for resultado in resultados_aquisicao:
        colaborador = resultado.necessidade.colaborador
        if colaborador is None:
            raise ColaboradorAusenteNaNecessidade(
                f'necessidade sem colaborador associado (documento_id='
                f'{resultado.documento_id!r}) -- esta composição exige '
                f'granularidade por colaborador'
            )
        colaboradores_vistos.add(colaborador.entidade_id)
        itens.append(ItemDocumentoOrdem(
            documento_id=resultado.documento_id, hash_sha256=resultado.hash_sha256,
        ))

    if len(colaboradores_vistos) > 1:
        raise ColaboradorDivergenteEntreDocumentos(
            f'documentos pertencem a colaboradores diferentes: '
            f'{sorted(colaboradores_vistos)!r}'
        )
    (funcionario_id,) = colaboradores_vistos

    preset = resolver_preset(preset_id)

    return OrdemDistribuicaoDocumental(
        documentos=tuple(itens),
        funcionario_id=funcionario_id,
        destinatario=destinatario,
        canal=preset.canal,
        preset_id=preset_id,
        tipo_documento=tipo_documento,
        exigir_assinatura=preset.exigir_assinatura,
        exigir_comprovante=preset.exigir_comprovante,
        politica_agrupamento=preset.politica_agrupamento,
        mensagem_texto=mensagem_texto,
    )


def materializar_prestacao_distribuicao_documental_shadow(
    *,
    resultados_aquisicao: Tuple[ResultadoAquisicaoPorNecessidade, ...],
    destinatario: str,
    preset_id: str,
    tipo_documento: str,
    mensagem_texto: str,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
    materializador: Optional[MaterializadorArquivoLegado],
    porta_assinatura: Optional[PortaObrigacaoAssinatura],
    repositorio_execucoes: RepositorioExecucoes,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
) -> ResultadoDistribuicaoDocumentalShadow:
    """Monta a Ordem (`montar_ordem_distribuicao_documental_de_
    prestacao`), registra seu evento canônico em `execucoes` (`registrar_
    evento_canonico_ordem_distribuicao_documental_shadow` -- satisfaz a FK
    que `autorizacoes_gate` exige) e só então chama o núcleo genérico
    (`materializar_distribuicao_documental_shadow`, intocado) -- nenhuma
    lógica de resolução, materialização, preview, autorização ou
    persistência é duplicada aqui; este módulo só monta e repassa."""
    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultados_aquisicao, destinatario=destinatario,
        preset_id=preset_id, tipo_documento=tipo_documento, mensagem_texto=mensagem_texto,
    )
    registrar_evento_canonico_ordem_distribuicao_documental_shadow(
        ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=instante,
    )
    return materializar_distribuicao_documental_shadow(
        ordem=ordem,
        repositorio_documentos=repositorio_documentos,
        armazenamento=armazenamento,
        materializador=materializador,
        porta_assinatura=porta_assinatura,
        repositorio_autorizacoes=repositorio_autorizacoes,
        repositorio_acoes=repositorio_acoes,
        ator_referencia=ator_referencia,
        proveniencia=proveniencia,
        instante=instante,
    )


@dataclasses.dataclass(frozen=True)
class ParametrosOrdemPrestacao:
    """Dados que só o chamador sabe resolver -- nunca inferidos por
    este módulo (mesma disciplina de `montar_ordem_distribuicao_
    documental_de_prestacao`, reaproveitada aqui, não reimplementada)."""

    destinatario: str
    preset_id: str
    tipo_documento: str
    mensagem_texto: str

    def __post_init__(self) -> None:
        for campo in ('destinatario', 'preset_id', 'tipo_documento', 'mensagem_texto'):
            if not isinstance(getattr(self, campo), str) or not getattr(self, campo).strip():
                raise PrestacaoDistribuicaoDocumentalError(f'{campo} deve ser texto não vazio')


ResolverParametrosOrdemPrestacao = Callable[
    [ReferenciaCanonica, ReferenciaCanonica, Tuple[ResultadoAquisicaoPorNecessidade, ...]],
    Optional[ParametrosOrdemPrestacao],
]
"""Callback fornecido pelo chamador: dado (cliente, competência,
resultados_aquisicao prontos), devolve os parâmetros da Ordem ou
`None` -- `None` significa fail-closed para ESSE cliente/competência
(ex.: destinatário/preset não resolvido), nunca uma tentativa de
adivinhar. Nunca resolve telefone/preset internamente a este módulo --
é só o ponto de extensão onde o chamador injeta essa decisão."""


def executar_prestacao_ate_distribuicao_documental_shadow(
    *,
    contexto: ContextoComposicaoPrestacao,
    resolver_parametros_ordem: ResolverParametrosOrdemPrestacao,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
    materializador: Optional[MaterializadorArquivoLegado],
    porta_assinatura: Optional[PortaObrigacaoAssinatura],
    repositorio_execucoes: RepositorioExecucoes,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
) -> Tuple[ResultadoDistribuicaoDocumentalShadow, ...]:
    """Composition root do Delta Final A-F: fecha `CLIENTE+COMPETÊNCIA
    -> ... -> PENDING` reutilizando, em sequência, só componentes já
    existentes -- nenhum motor novo:

    `resultados_aquisicao_prontos_por_colaborador` (Prestação: descoberta
    -> aquisição -> readiness por cliente -> partição por colaborador,
    Gate J1b) -> gate de readiness (cliente sem `PRONTO` nunca chega
    aqui) -> `resolver_
    parametros_ordem` (decisão externa do chamador, fail-closed se
    `None`) -> `materializar_prestacao_distribuicao_documental_shadow`
    (elo G-P já staged, intocado) -> núcleo genérico -> PENDING.

    Isolamento por cliente (correção pós-Ultrareview deste Delta --
    achado MEDIUM): uma exceção de DOMÍNIO de 1 cliente
    (`PrestacaoDistribuicaoDocumentalError`/subclasses -- ex.:
    `ColaboradorAusenteNaNecessidade`, `ColaboradorDivergenteEntreDocumentos`,
    `PresetDistribuicaoDocumentalDesconhecido`, ou qualquer
    `DistribuicaoDocumentalError` do núcleo) é capturada e REGISTRADA
    (nunca silenciada -- `_logger.error` com evento estável), mas NÃO
    interrompe o processamento dos demais clientes: um dado ruim de 1
    cliente nunca impede que N-1 outros clientes prontos e íntegros
    cheguem a PENDING. Qualquer outra exceção (sistêmica -- ex. falha
    de conexão Postgres, bug de programação) continua propagando e
    interrompendo, como antes desta correção.

    Zero transporte: só chama `materializar_prestacao_distribuicao_
    documental_shadow`, que já para em PENDING.

    Gate J1b: itera `resultados_aquisicao_prontos_por_colaborador` (1
    trio por cliente+competência+colaborador) em vez do pacote do
    cliente inteiro -- cliente com N colaboradores prontos produz N
    Ordens de destinatário único, e o isolamento acima passa a valer
    por colaborador (erro de domínio de A nunca impede a Ordem de B).
    Documentos de nível cliente não entram em Ordem de colaborador."""
    resultados: list = []
    for cliente, competencia, resultados_aquisicao in resultados_aquisicao_prontos_por_colaborador(contexto):
        parametros = resolver_parametros_ordem(cliente, competencia, resultados_aquisicao)
        if parametros is None:
            continue  # fail-closed: sem parâmetros resolvidos, zero Ordem para este cliente/competência
        try:
            resultado = materializar_prestacao_distribuicao_documental_shadow(
                resultados_aquisicao=resultados_aquisicao,
                destinatario=parametros.destinatario,
                preset_id=parametros.preset_id,
                tipo_documento=parametros.tipo_documento,
                mensagem_texto=parametros.mensagem_texto,
                repositorio_documentos=repositorio_documentos,
                armazenamento=armazenamento,
                materializador=materializador,
                porta_assinatura=porta_assinatura,
                repositorio_execucoes=repositorio_execucoes,
                repositorio_autorizacoes=repositorio_autorizacoes,
                repositorio_acoes=repositorio_acoes,
                ator_referencia=ator_referencia,
                proveniencia=proveniencia,
                instante=instante,
            )
        except (PrestacaoDistribuicaoDocumentalError, DistribuicaoDocumentalError) as exc:
            colaborador = resultados_aquisicao[0].necessidade.colaborador
            colaborador_id = colaborador.entidade_id if colaborador is not None else None
            _logger.error(
                '%s cliente=%s competencia=%s colaborador=%s exception_type=%s',
                EVENTO_CLIENTE_FALHOU_DISTRIBUICAO_DOCUMENTAL,
                cliente.entidade_id, competencia.entidade_id, colaborador_id, type(exc).__name__,
                extra={
                    'evento': EVENTO_CLIENTE_FALHOU_DISTRIBUICAO_DOCUMENTAL,
                    'cliente': cliente.entidade_id, 'competencia': competencia.entidade_id,
                    'colaborador': colaborador_id,
                    'exception_type': type(exc).__name__,
                },
            )
            continue  # isolamento: erro de domínio de 1 cliente nunca contamina os demais
        resultados.append(resultado)
    return tuple(resultados)
