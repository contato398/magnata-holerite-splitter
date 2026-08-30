"""Runner READ-ONLY do primeiro CICLO PILOTO real da Prestação de
Contas (missão "FECHAMENTO DA BASE CANÔNICA + PREPARAÇÃO DO PRIMEIRO
CICLO PILOTO REAL READ-ONLY", 2026-08-30).

Este módulo NUNCA cria uma peça nova de negócio -- só ORQUESTRA, na
ordem abaixo, peças já existentes e já testadas isoladamente (mesmo
espírito de `ciclo_prestacao.py`, um nível acima):

  1. competência BASE entra uma vez, na borda (`ContextoCicloPrestacao`,
     fornecida por quem chama -- nunca lida do relógio aqui);
  2. lista clientes ativos (`FonteClientesPrestacao.listar_ativos`);
  3. carrega requisitos canônicos (`CadastroRequisitosPrestacao`,
     tipicamente `CADASTRO_REQUISITOS_PRESTACAO_V2`, via
     `FonteRequisitosPrestacaoCanonica`);
  4. os overrides condicionais por cliente já vêm embutidos no cadastro
     (passo 3) -- nenhum campo extra é inventado aqui;
  5. consome o inventário já calculado (`FonteInventarioPrestacao`);
  6/7. calcula a competência EFETIVA por cliente (SKY, etc.) e aplica o
     readiness -- ambos já feitos por `executar_ciclo_prestacao`
     (`competencias_por_cliente` é parâmetro explícito, calculado fora
     deste módulo, na borda, nunca aqui);
  8. calcula pacote lógico + necessidades faltantes
     (`executar_ciclo_prestacao`, reaproveitado sem alteração);
  9/10. traduz o resultado para a saída SANITIZADA do modo dry-run.

ZERO escrita, ZERO envio, ZERO mutação de Airtable, ZERO chamada de rede
neste módulo -- todas as fontes injetadas (`FonteClientesPrestacao`,
`FonteRequisitosPrestacao`, `FonteInventarioPrestacao`,
`FonteColaboradoresEsperadosPrestacao`) já são Protocols read-only
existentes; este runner nunca instancia um adapter concreto sozinho.

MODO DRY-RUN -- restrição de segurança OBRIGATÓRIA (nunca relaxada):
a saída sanitizada carrega SOMENTE `CLIENTE_ID` / `COMPETENCIA_EFETIVA`
/ `ESTADO` / `PRESENTES` / `FALTANTES` / `NAO_CONFIGURADOS` /
`EM_REVISAO`. NUNCA CPF, NUNCA nome de colaborador/cliente, NUNCA texto
de PDF, NUNCA token/segredo, NUNCA payload bruto do Airtable --
`cliente_id`/tipos_documentais já são identificadores/vocabulário
sanitizados por construção em todo o motor (`ReferenciaCanonica.
entidade_id`, nunca CPF/nome; `tipo_documental`, vocabulário fixo do
motor, nunca texto livre de documento)."""
from __future__ import annotations

import dataclasses
from typing import Mapping, Optional, Tuple

from .ciclo_prestacao import ResultadoCicloPrestacao, executar_ciclo_prestacao
from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica, ResultadoResolucaoSemantico
from .fonte_clientes_prestacao import FonteClientesPrestacao
from .fonte_colaboradores_esperados_prestacao import FonteColaboradoresEsperadosPrestacao
from .fonte_requisitos_prestacao import FonteRequisitosPrestacao
from .inventario_prestacao import FonteInventarioPrestacao
from .pacote_prestacao import EstadoPacotePrestacao
from .prestacao_readiness import RequisitoDocumentalPrestacao


@dataclasses.dataclass(frozen=True)
class LinhaDryRunCicloPiloto:
    """1 linha de saída SANITIZADA do ciclo piloto -- os ÚNICOS campos
    permitidos são os declarados abaixo (ver restrição de segurança no
    docstring do módulo). Nunca adicionar um campo novo aqui sem
    reavaliar explicitamente se ele pode carregar CPF/nome/texto de
    PDF/token/payload -- a lista de campos é a própria garantia de
    sanitização, não um detalhe de implementação."""

    cliente_id: str
    competencia_efetiva: str
    estado: str
    presentes: Tuple[str, ...]
    faltantes: Tuple[str, ...]
    nao_configurados: Tuple[str, ...]
    em_revisao: bool


def _formatar_competencia(competencia: ReferenciaCanonica) -> str:
    return competencia.entidade_id


def gerar_linhas_dry_run(resultado: ResultadoCicloPrestacao) -> Tuple[LinhaDryRunCicloPiloto, ...]:
    """Traduz um `ResultadoCicloPrestacao` JÁ CALCULADO (nunca recalcula
    nada aqui -- puro, sem I/O) para a saída sanitizada do dry-run."""
    linhas = []
    for resultado_cliente in resultado.resultados_por_cliente:
        pacote = resultado_cliente.pacote
        presentes = tuple(sorted({item.tipo_documental for item in pacote.itens_incluidos}))
        linhas.append(LinhaDryRunCicloPiloto(
            cliente_id=resultado_cliente.cliente.entidade_id,
            competencia_efetiva=_formatar_competencia(resultado_cliente.competencia),
            estado=pacote.estado.value,
            presentes=presentes,
            faltantes=pacote.tipos_faltantes,
            nao_configurados=resultado_cliente.requisitos_nao_configurados,
            em_revisao=pacote.estado == EstadoPacotePrestacao.EM_REVISAO,
        ))
    return tuple(linhas)


def executar_ciclo_piloto_readonly(
    contexto: ContextoCicloPrestacao,
    fonte_clientes: FonteClientesPrestacao,
    fonte_requisitos: FonteRequisitosPrestacao,
    fonte_inventario: FonteInventarioPrestacao,
    requisitos_base: Tuple[RequisitoDocumentalPrestacao, ...],
    resolucoes_ancora: Mapping[ReferenciaCanonica, ResultadoResolucaoSemantico],
    competencias_por_cliente: Mapping[ReferenciaCanonica, ReferenciaCanonica],
    tipos_condicionais_para_auditoria: Tuple[str, ...] = (),
    fonte_colaboradores_esperados: Optional[FonteColaboradoresEsperadosPrestacao] = None,
) -> Tuple[LinhaDryRunCicloPiloto, ...]:
    """Executa 1 ciclo piloto ponta-a-ponta e devolve SÓ a saída
    sanitizada do dry-run -- nunca o `ResultadoCicloPrestacao` bruto
    (que carrega `ItemInventarioPrestacao`/`ResolucaoDimensao`
    completos, não pensados para impressão/observabilidade externa).
    Quem precisar do resultado completo (para persistência interna
    futura, nunca para imprimir) chama `executar_ciclo_prestacao`
    diretamente -- este runner é especificamente a fachada SEGURA para
    saída externa (log, terminal, relatório).

    Mesma assinatura de `executar_ciclo_prestacao` -- este módulo nunca
    duplica a orquestração, só adiciona a tradução sanitizada por cima."""
    resultado = executar_ciclo_prestacao(
        contexto=contexto,
        fonte_clientes=fonte_clientes,
        fonte_requisitos=fonte_requisitos,
        fonte_inventario=fonte_inventario,
        requisitos_base=requisitos_base,
        resolucoes_ancora=resolucoes_ancora,
        competencias_por_cliente=competencias_por_cliente,
        tipos_condicionais_para_auditoria=tipos_condicionais_para_auditoria,
        fonte_colaboradores_esperados=fonte_colaboradores_esperados,
    )
    return gerar_linhas_dry_run(resultado)
