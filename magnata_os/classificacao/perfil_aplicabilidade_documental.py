"""Cadastro DECLARATIVO de perfil de aplicabilidade por tipo documental
já RESOLVIDO (missão "CORREDOR AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fase 2/3:
"o maior bloqueio registrado pelo PR #104 foi a ausência de uma
estrutura que diga quais dimensões devem ser resolvidas para cada
tipo").

REGRA CRÍTICA (Fase 2 da missão): este cadastro só pode ser consultado
DEPOIS que TIPO_DOCUMENTAL já foi resolvido pelo motor semântico
(`ponte_conteudo_motor_semantico.resolver_tipo_documental_de_texto`).
NUNCA o inverso — o perfil nunca infere tipo, nunca reforça
classificação, nunca resolve documento pela origem, nunca substitui
evidência. `perfil_para_tipo` é uma função PURA de tabela: recebe um
`tipo_documental` (string) JÁ RESOLVIDO, devolve o `Perfil
AplicabilidadeResolucao` (contrato já existente, `contratos.py` —
nenhum contrato novo criado, Fase 3 da missão: "provar se perfil já
existe" — ele já existia, só faltava o CADASTRO tipo→perfil) ou `None`
quando o tipo não tem perfil cadastrado ainda (Fase 16: "não criar
valores falsos apenas para preencher dimensões" — tipo sem perfil é um
GATE real, nunca um perfil inventado).

Fase 6 (Não criar um IF gigante por documento): cadastro DECLARATIVO
(dict), nunca um `if tipo == X: ... elif tipo == Y: ...` — adicionar uma
família nova é adicionar uma entrada no dict, nunca um branch novo em
código de decisão.

TAXONOMIA DE GRANULARIDADE (Adendo substitutivo ao PR #105, §13) — todo
tipo cadastrado cai numa destas 3 formas (as 2 restantes da lista do
adendo — MASTER_MULTIENTIDADE e SEM_PERFIL — não são um "perfil": a
primeira é uma decisão ORTOGONAL tomada ANTES deste cadastro, pela
separação (`resolucao_documento_prestacao.processar_documento_com_
separacao_se_necessaria`, que fatia o texto e reentra cada filho no
MESMO motor — cada filho então cai numa das 3 formas abaixo,
normalmente); a segunda é simplesmente a ausência de entrada no dict —
nunca um valor cadastrado):
  - `_perfil_granularidade_colaborador`: documento pertence a 1
    colaborador; cliente é DERIVADO do vínculo do colaborador.
  - `_perfil_granularidade_cliente`: documento pertence a 1 cliente
    diretamente (nunca via vínculo de colaborador); cliente vem de
    `cliente_direto` (origem já resolvida) ou de separação por cliente.
  - `_perfil_broadcast`: documento é estruturalmente global à
    competência; nunca ausência de produtor de CLIENTE fingindo ser
    broadcast (Adendo §13: "ausência de produtor de CLIENTE NUNCA
    significa broadcast") — só usado quando a aplicabilidade GLOBAL já
    foi estruturalmente comprovada para a família (hoje: só DCTF, ver
    §12 do adendo). FGTS deixou de usar esta forma nesta correção (ver
    "Correção FGTS" abaixo).

CORREÇÃO FGTS (Adendo substitutivo ao PR #105, §10): FGTS (Guia e
Comprovante) NÃO é broadcast estrutural — foi um erro de modelagem do
PR #105 original, corrigido aqui antes do merge. FGTS agora usa
`_perfil_granularidade_cliente`: precisa de `cliente_direto` (origem já
resolvida) ou de separação por cliente (`estrategia_por_cnpj_cliente`,
já existente, reentra cada filho no motor); sem cliente resolvido, o
documento fica `NAO_AVALIADA`/revisão — NUNCA se espalha para todos os
clientes.

GUIA GENÉRICA (Adendo substitutivo ao PR #105, §11): removida do
cadastro. 'Guia' (fallback GPS/DARF sem finalidade determinada) não tem
finalidade suficiente para nenhuma granularidade — permanece
`PERFIL_NAO_CADASTRADO` até que a finalidade real seja resolvida (FGTS,
DCTF/DARF, ou outra). Nunca um pacote automático global para um tipo
ainda inconclusivo.

VINCULO (Adendo substitutivo ao PR #105, §14; a missão "EVIDÊNCIA
RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS" tentou
promover esta dimensão a OBRIGATORIA, mas o "ADENDO PRÉ-MERGE AO PR
#106 — CORREÇÃO DA SEMÂNTICA DE VÍNCULO HISTÓRICO" reverteu isso: a
resolução usada para a promoção fabricava a identidade do vínculo por
espelhamento de CLIENTE — nunca uma evidência real. VINCULO permanece
`NAO_APLICAVEL` em TODO perfil até existir uma fonte REAL
(`vinculo_unidade_prestacao.FonteVinculoPrestacao`) — o Protocol e o
resolvedor já existem e estão testados isoladamente, prontos para
quando essa fonte real existir; §4 do adendo: "melhor manter fora do
gate operacional do que inventar uma resolução falsa"). CLIENTE
continua resolvido normalmente pelo mecanismo já existente
(`vinculos_prestacao.FonteVinculosPrestacao`) — esta reversão não afeta
CLIENTE nem o corredor.

UNIDADE_POSTO: PROMOVIDA a **OBRIGATORIA** (cardinalidade múltipla,
nunca escolhida arbitrariamente quando o colaborador tem mais de um
posto na competência) **somente para Holerite** — o único caso com
regra semântica comprovada nesta missão (Fase 5 original: "Holerite:
unidade_posto quando fonte/vínculo permitir"; teste E2E A desta missão
exige a cadeia completa colaborador→vínculo→posto→cliente→pacote para
Holerite). Para as DEMAIS famílias de granularidade colaborador
(Ponto, Comprovantes, Relatório de Benefícios), permanece
`NAO_APLICAVEL` — decisão registrada, não escondida: nenhuma regra de
negócio comprovada exige posto para essas famílias nesta missão (§15:
"não obrigar unidade/posto para família onde ela realmente não
importa"); promover globalmente exigiria `fonte_unidade_posto`
configurada em TODO chamador dessas famílias sem nenhuma prova de que
isso é semanticamente necessário — mais seguro promover só onde há
prova, e estender depois com prova nova."""
from __future__ import annotations

from typing import Dict, Optional

from .contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    PerfilAplicabilidadeResolucao,
    RegraAplicabilidadeDimensao,
)

_OBRIGATORIA_UNICA = Cardinalidade(1, 1)
_OBRIGATORIA_MULTIPLA = Cardinalidade(1, None)
_NAO_APLICAVEL = Cardinalidade(0, 0)


def _regra(dimensao: DimensaoResolucao, aplicabilidade: AplicabilidadeDimensao, cardinalidade: Cardinalidade):
    return RegraAplicabilidadeDimensao(dimensao=dimensao, aplicabilidade=aplicabilidade, cardinalidade=cardinalidade)


def _tipo_obrigatorio():
    return _regra(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA)


# VINCULO: NAO_APLICAVEL em todo perfil -- revertido pelo adendo
# pré-merge ao PR #106 (ver docstring do módulo). Nenhuma fonte real
# existe ainda; nunca fabricar resolução só para preencher o gate.
_VINCULO_NAO_APLICAVEL = _regra(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL)


def _perfil_granularidade_colaborador(
    perfil_id: str, unidade_posto_obrigatoria: bool = False,
) -> PerfilAplicabilidadeResolucao:
    """Família cujo documento pertence a UM colaborador, cujo cliente é
    DERIVADO do vínculo do colaborador (Fase 5: "Holerite: conteúdo->
    colaborador->vínculo->cliente(s)", "Ponto: colaborador... cliente
    derivado do vínculo", "Comprovante Salário: colaborador... cliente
    por vínculo"). CLIENTE aceita cardinalidade multipla (1..N) --
    Adendo de Regra de Negócio (Holerite): um colaborador genuinamente
    vinculado a mais de um cliente na competência gera 1 item por
    cliente (`itens_para_multiplos_clientes_do_vinculo`, já existente).

    VINCULO: NAO_APLICAVEL -- ver docstring do módulo, "VINCULO"
    (revertido pelo adendo pré-merge ao PR #106: nenhuma fonte real
    existe ainda).

    `unidade_posto_obrigatoria`: só `True` para Holerite nesta missão
    (ver docstring do módulo) -- as demais famílias continuam
    NAO_APLICAVEL até haver regra semântica comprovada exigindo posto."""
    regra_unidade_posto = (
        _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_MULTIPLA)
        if unidade_posto_obrigatoria
        else _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL)
    )
    return PerfilAplicabilidadeResolucao(
        perfil_id=perfil_id, version='1', escopo_documental='granularidade_colaborador',
        regras=(
            _tipo_obrigatorio(),
            _regra(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_MULTIPLA),
            regra_unidade_posto,
            _VINCULO_NAO_APLICAVEL,
        ),
    )


def _perfil_granularidade_cliente(perfil_id: str) -> PerfilAplicabilidadeResolucao:
    """Família cujo documento pertence diretamente a UM cliente, sem
    colaborador (Fase 5: "Extrato: cliente/competência"). CLIENTE aqui
    é resolvido por uma fonte de origem específica (ex.: Airtable), não
    por vínculo de colaborador -- este perfil não impõe COMO, só QUE
    dimensão é obrigatória."""
    return PerfilAplicabilidadeResolucao(
        perfil_id=perfil_id, version='1', escopo_documental='granularidade_cliente',
        regras=(
            _tipo_obrigatorio(),
            _regra(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL),
            _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL),
            _VINCULO_NAO_APLICAVEL,
        ),
    )


def _perfil_broadcast(perfil_id: str) -> PerfilAplicabilidadeResolucao:
    """Família estruturalmente global (Fase 5/10: "DCTF: broadcast
    quando estruturalmente aplicável") -- CLIENTE é NAO_APLICAVEL AQUI
    (o perfil não resolve cliente nenhum); a lista real de clientes para
    os quais este documento se aplica é INJETADA por quem orquestra
    (`itens_para_clientes_broadcast`, já existente) -- nunca decidida
    por este cadastro."""
    return PerfilAplicabilidadeResolucao(
        perfil_id=perfil_id, version='1', escopo_documental='broadcast_estrutural',
        regras=(
            _tipo_obrigatorio(),
            _regra(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL),
            _regra(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL),
            _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL),
            _VINCULO_NAO_APLICAVEL,
        ),
    )


# Cadastro declarativo tipo_documental -> perfil (Fase 6: nunca um `if`
# gigante). Tipos cobertos nesta missão -- ver docs/decisoes/
# corredor-autonomo-pos-classificacao-v1.md, "Universo documental" para
# a matriz completa (inclusive os tipos SEM perfil ainda, honestamente
# marcados como tal, nunca escondidos).
_PERFIS_POR_TIPO: Dict[str, PerfilAplicabilidadeResolucao] = {
    'Holerite': _perfil_granularidade_colaborador('perfil-holerite', unidade_posto_obrigatoria=True),
    'Folha de Ponto': _perfil_granularidade_colaborador('perfil-folha-de-ponto'),
    'Comprovante de Pagamento - Salário': _perfil_granularidade_colaborador('perfil-comprovante-salario'),
    'Comprovante de Pagamento - VR/VA': _perfil_granularidade_colaborador('perfil-comprovante-vr-va'),
    'Comprovante de Pagamento - Assiduidade': _perfil_granularidade_colaborador('perfil-comprovante-assiduidade'),
    'Comprovante de Pagamento - Diárias': _perfil_granularidade_colaborador('perfil-comprovante-diarias'),
    'Comprovante de Pagamento - Horas Extras': _perfil_granularidade_colaborador('perfil-comprovante-horas-extras'),
    # Relatório/pedido de benefícios (Adendo substitutivo ao PR #105,
    # §1/§3): pertence a colaborador, cliente derivado do vínculo --
    # mesma forma de Holerite/Ponto. VR e VA no MESMO relatório nunca
    # forçam tipo_documental distinto (ver produtores_evidencia_
    # beneficios.py) -- a granularidade por colaborador é o que separa
    # as parcelas, nunca uma dimensão nova de "categoria de benefício".
    'Relatório de Benefícios': _perfil_granularidade_colaborador('perfil-relatorio-beneficios'),
    'Extrato da Folha de Pagamento': _perfil_granularidade_cliente('perfil-extrato'),
    'Guia DCTFWeb/DARF': _perfil_broadcast('perfil-guia-dctfweb-darf'),
    'DCTFWeb - Declaração': _perfil_broadcast('perfil-dctfweb-declaracao'),
    'DCTFWeb - Recibo de Entrega': _perfil_broadcast('perfil-dctfweb-recibo'),
    # FGTS: corrigido de broadcast para granularidade cliente (Adendo
    # substitutivo ao PR #105, §10) -- nunca se espalha para clientes
    # não comprovados; exige cliente_direto (origem) ou separação por
    # cliente.
    'FGTS': _perfil_granularidade_cliente('perfil-fgts-guia'),
    'Comprovante de Pagamento - FGTS': _perfil_granularidade_cliente('perfil-comprovante-fgts'),
    'Comprovante de Pagamento - DCTF/DARF': _perfil_broadcast('perfil-comprovante-dctf-darf'),
    # 'Guia' (fallback genérico GPS/DARF sem finalidade determinada) foi
    # REMOVIDA do cadastro nesta correção (Adendo substitutivo ao PR
    # #105, §11) -- finalidade insuficiente para qualquer granularidade;
    # permanece PERFIL_NAO_CADASTRADO até resolver para FGTS/DCTF/outra.
}


def perfil_para_tipo(tipo_documental: str) -> Optional[PerfilAplicabilidadeResolucao]:
    """Consulta pura de tabela -- `None` quando o tipo não tem perfil
    cadastrado (gate real: Fase 26, "subsistema grande desconectado da
    missão"/"regra de negócio nova não comprovada" -- nunca um perfil
    inventado para preencher a lacuna)."""
    return _PERFIS_POR_TIPO.get(tipo_documental)


def tipos_com_perfil_cadastrado() -> frozenset:
    """Observabilidade: quais tipos já têm perfil -- usado pela métrica
    de universo documental (Fase 16), nunca por lógica de decisão."""
    return frozenset(_PERFIS_POR_TIPO)
