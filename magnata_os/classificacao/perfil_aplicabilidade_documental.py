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

VINCULO: nenhuma entrada abaixo marca VINCULO como aplicável — decisão
registrada, não escondida (Fase 16): nenhum produtor de evidência
resolve a dimensão VINCULO isoladamente hoje (o que existe,
`vinculos_prestacao.FonteVinculosPrestacao`, resolve diretamente
CLIENTE a partir de COLABORADOR/UNIDADE_POSTO — o vínculo já
MATERIALIZADO em CLIENTE, nunca uma dimensão própria com evidência
independente). Marcar VINCULO como aplicável sem um produtor que a
resolva geraria NAO_AVALIADA permanente, nunca RESOLVIDA — pior que
declarar NAO_APLICAVEL honestamente."""
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


# VINCULO nunca aplicável em nenhum perfil desta missão -- ver docstring
# do módulo (nenhum produtor de evidência resolve esta dimensão
# isoladamente ainda).
_VINCULO_NAO_APLICAVEL = _regra(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL)


def _perfil_granularidade_colaborador(perfil_id: str) -> PerfilAplicabilidadeResolucao:
    """Família cujo documento pertence a UM colaborador, cujo cliente é
    DERIVADO do vínculo do colaborador (Fase 5: "Holerite: conteúdo->
    colaborador->vínculo->cliente(s)", "Ponto: colaborador... cliente
    derivado do vínculo", "Comprovante Salário: colaborador... cliente
    por vínculo"). CLIENTE aceita cardinalidade multipla (1..N) --
    Adendo de Regra de Negócio (Holerite): um colaborador genuinamente
    vinculado a mais de um cliente na competência gera 1 item por
    cliente (`itens_para_multiplos_clientes_do_vinculo`, já existente).

    UNIDADE_POSTO: NAO_APLICAVEL aqui, mesmo para Holerite (Fase 5 cita
    "quando fonte/vínculo permitir") -- decisão registrada, não
    escondida: nenhum produtor resolve esta dimensão isoladamente ainda
    (Fase 16), e `compor_resolucao_semantica` (já existente, nunca
    alterado aqui) trata QUALQUER dimensão NAO_AVALIADA -- inclusive
    uma marcada OPCIONAL sem produtor -- como impedimento a `RESOLVIDA`
    consolidado/`pronto_para_routing_logico`. Marcar OPCIONAL sem um
    produtor real bloquearia permanentemente o auto-avanço de toda a
    família -- mais seguro declarar NAO_APLICAVEL agora e promover para
    OPCIONAL/OBRIGATORIA quando um produtor real de UNIDADE_POSTO
    existir (próxima macro-missão candidata)."""
    return PerfilAplicabilidadeResolucao(
        perfil_id=perfil_id, version='1', escopo_documental='granularidade_colaborador',
        regras=(
            _tipo_obrigatorio(),
            _regra(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_UNICA),
            _regra(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, _OBRIGATORIA_MULTIPLA),
            _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, _NAO_APLICAVEL),
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
    'Holerite': _perfil_granularidade_colaborador('perfil-holerite'),
    'Folha de Ponto': _perfil_granularidade_colaborador('perfil-folha-de-ponto'),
    'Comprovante de Pagamento - Salário': _perfil_granularidade_colaborador('perfil-comprovante-salario'),
    'Comprovante de Pagamento - VR/VA': _perfil_granularidade_colaborador('perfil-comprovante-vr-va'),
    'Comprovante de Pagamento - Assiduidade': _perfil_granularidade_colaborador('perfil-comprovante-assiduidade'),
    'Comprovante de Pagamento - Diárias': _perfil_granularidade_colaborador('perfil-comprovante-diarias'),
    'Comprovante de Pagamento - Horas Extras': _perfil_granularidade_colaborador('perfil-comprovante-horas-extras'),
    'Extrato da Folha de Pagamento': _perfil_granularidade_cliente('perfil-extrato'),
    'Guia DCTFWeb/DARF': _perfil_broadcast('perfil-guia-dctfweb-darf'),
    'DCTFWeb - Declaração': _perfil_broadcast('perfil-dctfweb-declaracao'),
    'DCTFWeb - Recibo de Entrega': _perfil_broadcast('perfil-dctfweb-recibo'),
    'FGTS': _perfil_broadcast('perfil-fgts-guia'),
    'Guia': _perfil_broadcast('perfil-guia-generica'),
    'Comprovante de Pagamento - FGTS': _perfil_broadcast('perfil-comprovante-fgts'),
    'Comprovante de Pagamento - DCTF/DARF': _perfil_broadcast('perfil-comprovante-dctf-darf'),
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
