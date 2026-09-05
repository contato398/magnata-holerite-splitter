"""Orquestrador READ-ONLY de um ciclo da Prestação de Contas (missão
"POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fases 9-12).

Substitui o cenário artificial "clientes A/B/C injetados manualmente"
por uma execução que obtém clientes e requisitos de FONTES canônicas
substituíveis (`FonteClientesPrestacao`, `FonteRequisitosPrestacao`),
alimentando o corredor já existente (separação → resolução → inventário
→ readiness → pacote, PRs #93-#97) sem nenhum `if` por nome de cliente.

`executar_ciclo_prestacao`:
  1. recebe `ContextoCicloPrestacao` (competência ENTRA UMA VEZ, na
     borda — nunca lida do relógio aqui);
  2. lista clientes ativos (`FonteClientesPrestacao.listar_ativos`);
  3. para cada cliente, monta a `PoliticaRequisitosPrestacao` efetiva
     (base + registros normalizados de `FonteRequisitosPrestacao`);
  4. consome o inventário já calculado (`FonteInventarioPrestacao`);
  5. calcula readiness + pacote lógico (reaproveita `avaliar_e_montar_
     pacote`, `pacote_prestacao.py`, sem alteração);
  6. produz `NecessidadeDocumentoPrestacao` para cada tipo faltante
     (Fase 12 — nunca "documento não existe", sempre "não localizado
     no inventário consultado").

SEM busca externa, SEM envio, SEM efeito colateral — cada passo já
existia isoladamente; este módulo só ORQUESTRA."""
from __future__ import annotations

import dataclasses
from typing import Mapping, Optional, Tuple

from .cardinalidade_colaborador_por_tipo import avaliar_obrigatoriedade_por_tipo_documental
from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica, ResultadoResolucaoSemantico
from .fonte_clientes_prestacao import FonteClientesPrestacao
from .fonte_colaboradores_esperados_prestacao import FonteColaboradoresEsperadosPrestacao
from .fonte_requisitos_prestacao import FonteRequisitosPrestacao
from .holerite_obrigatorio_prestacao import TIPO_HOLERITE, avaliar_obrigatoriedade_holerite
from .inventario_prestacao import FonteInventarioPrestacao
from .normalizacao_requisitos_prestacao import normalizar_requisitos
from .pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
    avaliar_e_montar_pacote,
    combinar_pacote_com_holerite,
    combinar_pacote_com_obrigatoriedade_documental,
)
from .politica_requisitos_prestacao import OverrideRequisitosPrestacao, PoliticaRequisitosPrestacao
from .prestacao_readiness import RequisitoDocumentalPrestacao


@dataclasses.dataclass(frozen=True)
class NecessidadeDocumentoPrestacao:
    """Saída estruturada de 1 tipo faltante -- entrada da FUTURA busca
    complementar (Gmail/Airtable/armazenamento), nunca implementada
    aqui. Nunca declara ausência global -- só "não localizado NA FONTE
    DE INVENTÁRIO consultada" (cláusula pétrea #9)."""

    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    tipo_documental: str
    motivo_exigencia: str
    fontes_ainda_nao_consultadas: Tuple[str, ...] = ()
    colaborador: Optional[ReferenciaCanonica] = None
    """Adendo de Regra de Negócio (Holerite): identidade SANITIZADA
    (`ReferenciaCanonica('COLABORADOR', id)`, nunca CPF/nome) do
    colaborador cujo Holerite está faltando -- `None` para necessidades
    de tipos sem granularidade colaborador (FGTS, Extrato, DCTFWeb)."""

    def __post_init__(self) -> None:
        if not self.tipo_documental.strip():
            raise ValueError('tipo_documental deve ser texto nao vazio')
        if not self.motivo_exigencia.strip():
            raise ValueError('motivo_exigencia deve ser texto nao vazio')
        if self.colaborador is not None and self.colaborador.tipo_entidade != 'COLABORADOR':
            raise ValueError('colaborador deve ser referencia canonica de COLABORADOR')


@dataclasses.dataclass(frozen=True)
class ResultadoClientePrestacao:
    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    pacote: PacotePrestacaoCliente
    necessidades: Tuple[NecessidadeDocumentoPrestacao, ...] = ()
    requisitos_nao_configurados: Tuple[str, ...] = ()
    """Fase 13 (missão "CADASTRO CANÔNICO REAL DE REQUISITOS DA
    PRESTAÇÃO"): tipos que existem no universo canônico mas NÃO têm
    regra de obrigatoriedade configurada para este cliente -- NUNCA
    aparecem em `pacote.tipos_faltantes` (documento faltando é uma
    coisa; regra ainda não configurada é outra, cláusula pétrea desta
    missão: "não permitir que ambos apareçam como tipos_faltantes")."""


@dataclasses.dataclass(frozen=True)
class ResultadoCicloPrestacao:
    contexto: ContextoCicloPrestacao
    resultados_por_cliente: Tuple[ResultadoClientePrestacao, ...]

    def _clientes_no_estado(self, estado: EstadoPacotePrestacao) -> Tuple[ReferenciaCanonica, ...]:
        return tuple(
            resultado.cliente for resultado in self.resultados_por_cliente
            if resultado.pacote.estado == estado
        )

    @property
    def prontos(self) -> Tuple[ReferenciaCanonica, ...]:
        return self._clientes_no_estado(EstadoPacotePrestacao.PRONTO)

    @property
    def incompletos(self) -> Tuple[ReferenciaCanonica, ...]:
        return self._clientes_no_estado(EstadoPacotePrestacao.INCOMPLETO)

    @property
    def em_revisao(self) -> Tuple[ReferenciaCanonica, ...]:
        return self._clientes_no_estado(EstadoPacotePrestacao.EM_REVISAO)

    @property
    def bloqueados(self) -> Tuple[ReferenciaCanonica, ...]:
        return self._clientes_no_estado(EstadoPacotePrestacao.BLOQUEADO)


def _politica_efetiva_para_cliente(
    cliente: ReferenciaCanonica,
    contexto: ContextoCicloPrestacao,
    requisitos_base: Tuple[RequisitoDocumentalPrestacao, ...],
    fonte_requisitos: FonteRequisitosPrestacao,
) -> Tuple[PoliticaRequisitosPrestacao, Tuple]:
    """Monta a política efetiva de 1 cliente: base fixa (igual para
    todos, definida por quem orquestra) + registros brutos da fonte,
    NORMALIZADOS (Fase 7 -- nunca aceitos crus). Devolve também os
    resultados de normalização (incl. rejeitados) para quem chama
    decidir o que fazer com tipo desconhecido/quantidade inválida."""
    registros = fonte_requisitos.registros_para(cliente, contexto)
    validos, resultados_normalizacao = normalizar_requisitos(registros)
    # OverrideRequisitosPrestacao exige competencia -- usamos a
    # competência BASE do contexto; deslocamentos por tipo (SKY, etc.)
    # continuam responsabilidade de PoliticaCompetenciaPrestacao,
    # nunca desta política de REQUISITOS.
    ano, mes = contexto.competencia_base
    competencia_base = ReferenciaCanonica('COMPETENCIA', f'{ano:04d}-{mes:02d}')
    overrides = (
        (OverrideRequisitosPrestacao(cliente=cliente, competencia=competencia_base, requisitos_adicionais=validos),)
        if validos else ()
    )
    politica = PoliticaRequisitosPrestacao(
        version='ciclo-prestacao-v1', requisitos_base=requisitos_base, overrides=overrides,
    )
    return politica, resultados_normalizacao


def executar_ciclo_prestacao(
    contexto: ContextoCicloPrestacao,
    fonte_clientes: FonteClientesPrestacao,
    fonte_requisitos: FonteRequisitosPrestacao,
    fonte_inventario: FonteInventarioPrestacao,
    requisitos_base: Tuple[RequisitoDocumentalPrestacao, ...],
    resolucoes_ancora: Mapping[ReferenciaCanonica, ResultadoResolucaoSemantico],
    competencias_por_cliente: Mapping[ReferenciaCanonica, ReferenciaCanonica],
    tipos_condicionais_para_auditoria: Tuple[str, ...] = (),
    fonte_colaboradores_esperados: Optional[FonteColaboradoresEsperadosPrestacao] = None,
    tipos_obrigatorios_por_colaborador: Tuple[str, ...] = (TIPO_HOLERITE,),
) -> ResultadoCicloPrestacao:
    """Executa 1 ciclo, ponta-a-ponta, sem efeito colateral.

    `resolucoes_ancora`: para cada cliente, o `ResultadoResolucaoSemantico`
    que ancora a leitura de CLIENTE/COMPETENCIA no readiness (mesmo
    papel que já tinha em `avaliar_e_montar_pacote` -- este orquestrador
    nunca recalcula resolução semântica, só a repassa).
    `competencias_por_cliente`: competência EFETIVA já resolvida por
    cliente (via `PoliticaCompetenciaPrestacao`, ex.: SKY = base - 1
    mês) -- calculada fora deste módulo, na borda, nunca aqui (cláusula
    pétrea Fase 9: "competência entra uma vez na borda").
    `tipos_condicionais_para_auditoria`: tipos "de interesse" (ex.:
    `REQUISITOS_DIVERGENTES_ENTRE_FONTES`) cujo estado de configuração
    (Fase 13) é reportado por cliente em `ResultadoClientePrestacao.
    requisitos_nao_configurados` -- só populado quando `fonte_requisitos`
    implementa `requisitos_nao_configurados_para` (extensão OPCIONAL,
    duck-typed, nunca parte obrigatória do Protocol `FonteRequisitosPrestacao`
    do PR #98 -- uma fonte sem essa extensão simplesmente não relata
    esta informação, nunca quebra).
    `fonte_colaboradores_esperados`: quando informada, tipos em
    `tipos_obrigatorios_por_colaborador` são avaliados por CARDINALIDADE
    colaborador para TODO cliente, nunca só pela presença agregada do
    tipo no inventário -- "TIPOS OBRIGATÓRIOS SÃO EXIGIDOS EM TODA
    PRESTAÇÃO DE CONTAS" (Adendo de Regra de Negócio, generalizado de
    Holerite para suportar Folha de Ponto e outros). `None` (default)
    preserva o comportamento anterior (tipos avaliados só pela contagem
    plana, se estiverem na política efetiva do cliente).
    `tipos_obrigatorios_por_colaborador`: tuple de tipos_documental que
    devem ser avaliados por cardinalidade colaborador quando
    `fonte_colaboradores_esperados` é fornecida. Default = (TIPO_HOLERITE,)
    para compatibilidade. Pode incluir 'Folha de Ponto' ou outros tipos
    que tenham granularidade colaborador."""
    resultados = []
    for cliente in fonte_clientes.listar_ativos(contexto):
        competencia = competencias_por_cliente.get(cliente)
        resolucao_ancora = resolucoes_ancora.get(cliente)
        if competencia is None or resolucao_ancora is None:
            # Cliente ativo, mas sem contexto suficiente para avaliar
            # este ciclo -- nunca inventa competência/resolução; fica
            # de fora do resultado deste ciclo (NECESSITA REVISÃO fora
            # de banda, não um pacote fictício).
            continue

        politica, _resultados_normalizacao = _politica_efetiva_para_cliente(
            cliente, contexto, requisitos_base, fonte_requisitos)
        pacote = avaliar_e_montar_pacote(cliente, competencia, resolucao_ancora, fonte_inventario, politica)

        # Avalia cardinalidade por colaborador para TODOS os tipos obrigatórios
        # (não só Holerite). Compatibilidade: se `fonte_colaboradores_esperados`
        # é None, comportamento anterior preservado (contagem plana).
        resultado_holerite = None
        resultados_obrigatoriedade = {}
        if fonte_colaboradores_esperados is not None:
            colaboradores_esperados = fonte_colaboradores_esperados.colaboradores_esperados_para(cliente, contexto)
            for tipo_obrigatorio in tipos_obrigatorios_por_colaborador:
                resultado = avaliar_obrigatoriedade_por_tipo_documental(
                    cliente, competencia, tipo_obrigatorio, colaboradores_esperados, pacote.itens_incluidos
                )
                resultados_obrigatoriedade[tipo_obrigatorio] = resultado
                # Compatibilidade Holerite: manter campo `resultado_holerite` preenchido
                if tipo_obrigatorio == TIPO_HOLERITE:
                    resultado_holerite = avaliar_obrigatoriedade_holerite(
                        cliente, competencia, colaboradores_esperados, pacote.itens_incluidos
                    )
                # Combina pacote com obrigatoriedade de cada tipo
                pacote = combinar_pacote_com_obrigatoriedade_documental(pacote, resultado)

        # Tipos faltantes por cardinalidade: exclui tipos já processados
        # por-colaborador quando fonte de colaboradores foi informada
        tipos_excluir_necessidade_generica = (
            set(tipos_obrigatorios_por_colaborador) if fonte_colaboradores_esperados is not None else set()
        )
        tipos_para_necessidade_generica = (
            tuple(tipo for tipo in pacote.tipos_faltantes if tipo not in tipos_excluir_necessidade_generica)
        )
        necessidades = tuple(
            NecessidadeDocumentoPrestacao(
                cliente=cliente, competencia=competencia, tipo_documental=tipo,
                motivo_exigencia='requisito_documental_da_politica_efetiva',
                fontes_ainda_nao_consultadas=('gmail', 'airtable', 'armazenamento_documental'),
            )
            for tipo in tipos_para_necessidade_generica
        )
        # Gera necessidades por-colaborador para cada tipo com cardinalidade
        for tipo_obrigatorio, resultado_obrigatoriedade in resultados_obrigatoriedade.items():
            if resultado_obrigatoriedade.colaboradores_faltantes:
                necessidades = necessidades + tuple(
                    NecessidadeDocumentoPrestacao(
                        cliente=cliente, competencia=competencia, tipo_documental=tipo_obrigatorio,
                        motivo_exigencia=f'{tipo_obrigatorio.lower()}_obrigatorio_por_colaborador_esperado',
                        fontes_ainda_nao_consultadas=('gmail', 'airtable', 'armazenamento_documental'),
                        colaborador=colaborador_faltante,
                    )
                    for colaborador_faltante in resultado_obrigatoriedade.colaboradores_faltantes
                )

        # Compatibilidade: preencher campo `holerite` no pacote se foi avaliado
        # (consumidores existentes podem inspecionar este campo)
        if resultado_holerite is not None:
            pacote = dataclasses.replace(pacote, holerite=resultado_holerite)

        requisitos_nao_configurados = ()
        if tipos_condicionais_para_auditoria:
            obter_nao_configurados = getattr(fonte_requisitos, 'requisitos_nao_configurados_para', None)
            if obter_nao_configurados is not None:
                requisitos_nao_configurados = obter_nao_configurados(
                    cliente, contexto, tipos_condicionais_para_auditoria)

        resultados.append(ResultadoClientePrestacao(
            cliente=cliente, competencia=competencia, pacote=pacote, necessidades=necessidades,
            requisitos_nao_configurados=requisitos_nao_configurados,
        ))

    return ResultadoCicloPrestacao(contexto=contexto, resultados_por_cliente=tuple(resultados))
