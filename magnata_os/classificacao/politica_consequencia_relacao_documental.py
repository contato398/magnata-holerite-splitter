"""Política DECLARATIVA de consequência de uma relação Documento↔
Documento já RESOLVIDA (missão "CORRIGIR METADADOS + MERGE PR #106 +
COSTURA AUTOMÁTICA DE RELAÇÃO DOCUMENTO↔DOCUMENTO NO CORREDOR V1", §7).

Evita `if tipo == beneficios` espalhado pelo orquestrador -- um
cadastro (tupla de regras), nunca um branch novo por família (mesmo
princípio de `perfil_aplicabilidade_documental._PERFIS_POR_TIPO`).
Reaproveita `TipoRelacaoDocumental` já existente
(`relacao_documental.py`), nunca um enum novo.

Cada regra nomeia os 2 PAPÉIS semânticos da relação -- nunca "tipo
A"/"tipo B" genéricos, porque a relação real é assimétrica: um lado
RELATA/SOLICITA (relatório, guia -- carrega composição/clientes já
resolvidos), o outro COMPROVA (comprovante -- tipicamente sem
colaborador/cliente individualizável na própria estrutura). Uma regra
declara o que o lado COMPROVANTE pode herdar do lado RELATANTE quando
a relação resolve -- nunca o inverso, nunca mais do que o declarado
aqui (§6: "não herdar dados indevidos" -- composição individual
continua vindo sempre do relatante, nunca inventada no comprovante)."""
from __future__ import annotations

import dataclasses
from typing import Dict, Optional, Tuple

from .contratos import ReferenciaCanonica
from .relacao_documental import TipoRelacaoDocumental


@dataclasses.dataclass(frozen=True)
class RegraConsequenciaRelacao:
    tipo_relatante: str
    tipo_comprovante: str
    tipo_relacao: TipoRelacaoDocumental
    pode_derivar_referencias_do_relatante: bool
    """Quando `True`, o lado COMPROVANTE (nunca o relatante) herda as
    `referencias_logicas` (clientes) já resolvidas do candidato
    vencedor -- nunca decompõe valor por colaborador, nunca inventa
    posto/competência divergente. Só o CONJUNTO já comprovado do outro
    lado, nunca um subconjunto escolhido nem um valor recalculado."""
    preserva_broadcast: bool
    """Quando `True`, a lista de clientes deste tipo continua vindo
    inteiramente da política de broadcast já canônica
    (`itens_para_clientes_broadcast`, injetada por quem orquestra) --
    a relação nunca decide clientes aqui, só fica registrada como
    evidência/auditoria (§9/§20-G da missão: "DCTF... broadcast
    preservado")."""
    motivo_registrado: str
    """Código sanitizado de auditoria -- nunca texto livre não
    documentado."""

    def __post_init__(self) -> None:
        if self.pode_derivar_referencias_do_relatante and self.preserva_broadcast:
            raise ValueError(
                'uma regra nunca pode, ao mesmo tempo, derivar referencias do relatante E preservar broadcast '
                '-- sao consequencias mutuamente exclusivas por desenho'
            )


# Cadastro declarativo -- ver docs/decisoes/costura-relacao-documental-
# corredor-v1.md para a auditoria/justificativa de cada regra. Nenhuma
# regra aqui é especulativa: cada uma tem um caso E2E correspondente
# (§23 da missão).
_REGRAS: Tuple[RegraConsequenciaRelacao, ...] = (
    RegraConsequenciaRelacao(
        tipo_relatante='Relatório de Benefícios', tipo_comprovante='Comprovante de Pagamento - VR/VA',
        tipo_relacao=TipoRelacaoDocumental.COMPROVA, pode_derivar_referencias_do_relatante=True,
        preserva_broadcast=False,
        motivo_registrado='comprovante_global_de_beneficios_herda_clientes_do_relatorio_relacionado',
    ),
    RegraConsequenciaRelacao(
        tipo_relatante='FGTS', tipo_comprovante='Comprovante de Pagamento - FGTS',
        tipo_relacao=TipoRelacaoDocumental.COMPROVA, pode_derivar_referencias_do_relatante=True,
        preserva_broadcast=False,
        motivo_registrado='comprovante_fgts_herda_cliente_da_guia_relacionada',
    ),
    RegraConsequenciaRelacao(
        tipo_relatante='Guia DCTFWeb/DARF', tipo_comprovante='Comprovante de Pagamento - DCTF/DARF',
        tipo_relacao=TipoRelacaoDocumental.COMPROVA, pode_derivar_referencias_do_relatante=False,
        preserva_broadcast=True,
        motivo_registrado='dctf_comprovante_mantem_broadcast_estrutural_relacao_so_evidencia',
    ),
)

_REGRAS_POR_TIPO_COMPROVANTE: Dict[str, RegraConsequenciaRelacao] = {
    regra.tipo_comprovante: regra for regra in _REGRAS
}


def regra_para_tipo_comprovante(tipo_documental: str) -> Optional[RegraConsequenciaRelacao]:
    """Consulta pura de tabela -- devolve a regra em que
    `tipo_documental` é o lado COMPROVANTE, ou `None` quando não há
    regra comprovada (nunca inventada -- mesmo princípio de
    `perfil_aplicabilidade_documental.perfil_para_tipo`: tipo sem regra
    é um gate real, nunca uma regra fabricada para preencher a
    lacuna)."""
    return _REGRAS_POR_TIPO_COMPROVANTE.get(tipo_documental)


def tipos_comprovante_com_regra_cadastrada() -> frozenset:
    """Observabilidade -- usado pela métrica de universo documental,
    nunca por lógica de decisão."""
    return frozenset(_REGRAS_POR_TIPO_COMPROVANTE)


def derivar_referencias_herdadas(
    relacao_resolvida: bool, referencias_do_relatante: Tuple[ReferenciaCanonica, ...],
) -> Tuple[ReferenciaCanonica, ...]:
    """Regra ÚNICA de herança (§6 da missão): o lado comprovante só
    herda quando a relação já está `RESOLVIDA`, e herda exatamente o
    conjunto já comprovado do relatante -- nunca um subconjunto
    escolhido, nunca um valor recalculado. Generalização de
    `produtores_evidencia_beneficios.derivar_clientes_logicos_do_
    comprovante_global` (que agora delega aqui -- fonte única de
    verdade, nunca uma segunda engine por família)."""
    if not relacao_resolvida:
        return ()
    return referencias_do_relatante
