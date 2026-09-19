"""Presets operacionais V1 da Distribuição Documental Genérica.

Mapeia `preset_id` (escolhido explicitamente por quem constrói a
`OrdemDistribuicaoDocumental`) para a política operacional completa --
canal, exigência de assinatura/comprovante e política de agrupamento.

Disciplina de agnosticismo (mesma do núcleo,
`wiring_distribuicao_documental_shadow.py`): esta tabela é indexada
EXCLUSIVAMENTE por `preset_id`, NUNCA por `tipo_documento`. Um
`tipo_documento` novo (EPI, NR01, CONTRATO, COMUNICADO, etc.) usa
qualquer preset compatível sem qualquer alteração de código aqui --
`tipo_documento` continua dado opaco da Ordem, repassado só até o
adapter legado (`adapters/obrigacao_assinatura_legado_http.py`,
`TIPO_DOCUMENTO_PACOTE_LEGADO_2`), único lugar autorizado a testá-lo.

`PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA` é uma política operacional
de N=2/1 link -- não é específica de Holerite/Ponto. A limitação de que
o motor legado hoje só sabe agrupar 2 documentos sob
`tipo_documento='HOLERITE_FOLHA_PONTO'` permanece exclusivamente no
adapter; um N=2 de outro `tipo_documento` usando este mesmo preset
continua fail-closed no adapter (`QuantidadeArquivosNaoSuportadaPeloLegado`),
nunca aqui.
"""
from __future__ import annotations

import dataclasses

__all__ = [
    'PresetDistribuicaoDocumentalDesconhecido',
    'PoliticaPresetDistribuicaoDocumental',
    'resolver_preset',
]


class PresetDistribuicaoDocumentalDesconhecido(ValueError):
    """`preset_id` não corresponde a nenhum preset V1 conhecido --
    fail-closed antes de qualquer I/O, nunca uma política inferida ou
    adivinhada a partir de `tipo_documento`."""


@dataclasses.dataclass(frozen=True)
class PoliticaPresetDistribuicaoDocumental:
    canal: str
    exigir_assinatura: bool
    exigir_comprovante: bool
    politica_agrupamento: str


_PRESETS_V1: dict = {
    'DOCUMENTO_UNITARIO_SEM_ASSINATURA': PoliticaPresetDistribuicaoDocumental(
        canal='WHATSAPP', exigir_assinatura=False, exigir_comprovante=False,
        politica_agrupamento='UNITARIO',
    ),
    'DOCUMENTO_UNITARIO_COM_ASSINATURA': PoliticaPresetDistribuicaoDocumental(
        canal='WHATSAPP', exigir_assinatura=True, exigir_comprovante=True,
        politica_agrupamento='UNITARIO',
    ),
    'PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA': PoliticaPresetDistribuicaoDocumental(
        canal='WHATSAPP', exigir_assinatura=True, exigir_comprovante=True,
        politica_agrupamento='AGRUPADO_1_LINK',
    ),
}


def resolver_preset(preset_id: str) -> PoliticaPresetDistribuicaoDocumental:
    """Fail-closed: `preset_id` desconhecido nunca infere uma política
    default -- levanta imediatamente, antes de qualquer resolução de
    documento/materialização/autorização."""
    try:
        return _PRESETS_V1[preset_id]
    except KeyError:
        raise PresetDistribuicaoDocumentalDesconhecido(
            f'preset_id desconhecido nesta V1: {preset_id!r}'
        ) from None
