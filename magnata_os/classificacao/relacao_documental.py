"""Capacidade GENÉRICA de relação semântica Documento↔Documento (missão
"MERGE PR #105 + EVIDÊNCIA RELACIONAL DOCUMENTO↔DOCUMENTO +
VÍNCULO/UNIDADE_POSTO REAIS + FECHAMENTO DO UNIVERSO DOCUMENTAL V1",
§5-§9).

Auditoria prévia (§1 da missão) confirmou: `dominio_versionamento.py`
(importacao_lote) já modela relação entre VERSÕES do MESMO documento
lógico (supersessão) -- um conceito DIFERENTE, nunca confundido aqui.
Nenhum outro módulo do repositório modela relação semântica entre DOIS
DOCUMENTOS DISTINTOS (ex.: um relatório de benefícios e o comprovante
de pagamento correspondente). Este módulo preenche essa lacuna --
UMA VEZ, de forma reutilizável (§9: "a mesma infra precisa suportar
FGTS guia↔comprovante, DCTF guia↔comprovante, benefício pedido↔
comprovante, documento↔assinatura, master↔filhos -- sem criar um motor
por família").

NUNCA criados aqui (proibição explícita da missão): `RelacaoComprovante
Ifood`, `RelacaoVrBeneficios`, `RelacaoFgtsEspecial` ou qualquer classe
por família/fornecedor. Regras específicas de EXTRAÇÃO de campo (o que
conta como "identificador de pedido" num Relatório de Benefícios vs.
numa Guia FGTS) podem viver no módulo da família correspondente -- mas
o CONTRATO de relação e o RESOLVEDOR são só este, sempre.

REGRA DE COMBINAÇÃO (§6, cláusula pétrea explícita da missão: "valor
total sozinho NÃO basta, data sozinha NÃO basta, fornecedor sozinho
NÃO basta -- combinar evidências"): nenhum tipo de evidência isolado
decide uma relação sozinho. A força combinada segue a MESMA regra já
estabelecida em `resolucao_tipo_documental._forca_combinada` (réplica
documentada aqui porque aquela função é privada do módulo de tipo
documental -- a REGRA é a mesma, nunca uma segunda decisão paralela):
  - qualquer evidência FORTE -> força combinada FORTE;
  - 2+ evidências MODERADA (nenhuma FORTE) -> FORTE;
  - exatamente 1 MODERADA -> MODERADA;
  - 2+ FRACA (nenhuma FORTE/MODERADA) -> MODERADA;
  - exatamente 1 FRACA -> FRACA;
  - nenhuma evidência -> INDETERMINADA.
Uma relação só é `RESOLVIDA` quando a força combinada chega a FORTE.

Estados (§ "Documento↔Documento — capacidade genérica" da missão:
"estados espelhando RESOLVIDA/AMBIGUA/NAO_ENCONTRADA/CONFLITO/
ERRO_TECNICO") -- reaproveita `EstadoResolucaoDimensao`, já existente,
em vez de um enum novo (cláusula pétrea repetida em toda esta missão:
"não criar enum se contrato existente já representa a incerteza"). Só
os 5 estados citados pela missão são produzidos por este módulo
(NAO_AVALIADA/NAO_APLICAVEL/INVALIDA seguem fora do escopo desta
capacidade -- quem orquestra decide se avalia ou não)."""
from __future__ import annotations

import dataclasses
import enum
from typing import Optional, Pattern, Tuple

from magnata_os.documental.importacao_lote.contratos import StatusExtracaoCompetencia
from magnata_os.documental.importacao_lote.dominio import extrair_competencia_de_texto

from .contratos import ConfiancaResolucao, EstadoResolucaoDimensao, NivelConfianca


class TipoRelacaoDocumental(str, enum.Enum):
    """Semânticas de relação REALMENTE usáveis dado o que existe hoje de
    evidência (§5: "só se os contratos existentes permitirem" -- nenhuma
    aqui é decorativa, cada uma tem pelo menos um uso concreto nesta
    mesma missão ou documentado como aplicação futura em §9/§11)."""

    COMPROVA = 'COMPROVA'
    """Documento B comprova o pagamento/execução do que Documento A
    solicita/relata (ex.: comprovante bancário COMPROVA um relatório de
    benefícios ou uma guia FGTS)."""
    PERTENCE_AO_LOTE = 'PERTENCE_AO_LOTE'
    """Documento A e Documento B foram ingeridos como parte do mesmo
    lote/remessa -- evidência de contexto, nunca por si só suficiente."""
    DERIVADO_DE = 'DERIVADO_DE'
    """Documento B foi extraído/separado de Documento A (ex.: um filho
    de granularidade colaborador extraído de um master) -- aplicação
    futura documentada; não usado por este mission-scope diretamente
    (a separação já tem seu próprio mecanismo, `separacao_documental.py`
    -- esta semântica existe para o caso em que a proveniência precisa
    ser registrada como RELAÇÃO, não só como resultado de separação)."""
    FILHO_DE = 'FILHO_DE'
    """Documento A é a página/seção-mãe estrutural de Documento B."""
    REFERENCIA = 'REFERENCIA'
    """Documento A cita/referencia Documento B explicitamente, sem
    implicar comprovação ou derivação (relação mais fraca)."""
    SUBSTITUI = 'SUBSTITUI'
    """Aplicação futura documentada (§9): reservado para o caso em que
    a semântica de substituição precisar ser expressa como uma RELAÇÃO
    entre dois documentos lógicos distintos -- distinto da supersessão
    de VERSÃO do MESMO documento lógico, que já é resolvida por
    `dominio_versionamento.py` e nunca duplicada aqui."""
    COMPLEMENTA = 'COMPLEMENTA'
    """Documento B complementa Documento A sem comprovar nem substituir
    (ex.: um anexo informativo). Aplicação futura documentada."""


_ESTADOS_PRODUZIDOS = frozenset({
    EstadoResolucaoDimensao.RESOLVIDA, EstadoResolucaoDimensao.AMBIGUA,
    EstadoResolucaoDimensao.NAO_ENCONTRADA, EstadoResolucaoDimensao.CONFLITO,
})


@dataclasses.dataclass(frozen=True)
class EvidenciaRelacaoDocumental:
    """Uma evidência ISOLADA de relação entre dois documentos -- nunca,
    sozinha (mesmo se `forca=FORTE`), suficiente para `RESOLVIDA`: o
    resolvedor sempre recombina (ver regra de combinação acima). Uma
    evidência com `contraditoria=True` é um sinal de CONFLITO real
    (ex.: identificador de pedido explícito DIVERGENTE entre os dois
    documentos) -- qualquer evidência contraditória, sozinha, já basta
    para marcar a relação como `CONFLITO`, nunca absorvida
    silenciosamente por outras evidências favoráveis."""

    tipo_evidencia: str
    forca: NivelConfianca
    motivo_sanitizado: Optional[str] = None
    contraditoria: bool = False

    def __post_init__(self) -> None:
        if not self.tipo_evidencia or not self.tipo_evidencia.strip():
            raise ValueError('tipo_evidencia deve ser texto nao vazio')


@dataclasses.dataclass(frozen=True)
class ResolucaoRelacaoDocumental:
    """Resultado da resolução de relação entre `documento_a_id` e
    (quando resolvida/ambígua) um ou mais `documento_b_id` candidatos.
    Nunca carrega texto bruto, CPF ou qualquer PII -- só IDs de
    documento já sanitizados (§25 da missão)."""

    documento_a_id: str
    tipo_relacao: TipoRelacaoDocumental
    estado: EstadoResolucaoDimensao
    documento_b_id: Optional[str] = None
    candidatos_documento_b_id: Tuple[str, ...] = ()
    evidencias: Tuple[EvidenciaRelacaoDocumental, ...] = ()
    confianca: ConfiancaResolucao = dataclasses.field(
        default_factory=lambda: ConfiancaResolucao(NivelConfianca.INDETERMINADA)
    )
    motivos: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.estado not in _ESTADOS_PRODUZIDOS:
            raise ValueError(f'estado {self.estado!r} nao e produzido por relacao_documental')
        if self.estado == EstadoResolucaoDimensao.RESOLVIDA and not self.documento_b_id:
            raise ValueError('RESOLVIDA exige documento_b_id')
        if self.estado == EstadoResolucaoDimensao.AMBIGUA and len(self.candidatos_documento_b_id) < 2:
            raise ValueError('AMBIGUA exige 2+ candidatos_documento_b_id')


def _forca_combinada(evidencias: Tuple[EvidenciaRelacaoDocumental, ...]) -> NivelConfianca:
    """Mesma regra de `resolucao_tipo_documental._forca_combinada` --
    ver docstring do módulo, "REGRA DE COMBINAÇÃO"."""
    forcas = [evidencia.forca for evidencia in evidencias]
    if NivelConfianca.FORTE in forcas:
        return NivelConfianca.FORTE
    quantidade_moderada = forcas.count(NivelConfianca.MODERADA)
    quantidade_fraca = forcas.count(NivelConfianca.FRACA)
    if quantidade_moderada >= 2:
        return NivelConfianca.FORTE
    if quantidade_moderada == 1:
        return NivelConfianca.MODERADA
    if quantidade_fraca >= 2:
        return NivelConfianca.MODERADA
    if quantidade_fraca == 1:
        return NivelConfianca.FRACA
    return NivelConfianca.INDETERMINADA


def resolver_relacao_documental_par(
    documento_a_id: str,
    documento_b_id: str,
    tipo_relacao: TipoRelacaoDocumental,
    evidencias: Tuple[EvidenciaRelacaoDocumental, ...],
) -> ResolucaoRelacaoDocumental:
    """Resolve a relação entre UM par já determinado de documentos --
    uso direto quando não há candidatos concorrentes (ex.: só existe um
    comprovante candidato para aquele relatório)."""
    if not documento_a_id or not documento_a_id.strip():
        raise ValueError('documento_a_id deve ser texto nao vazio')
    if not documento_b_id or not documento_b_id.strip():
        raise ValueError('documento_b_id deve ser texto nao vazio')

    if any(evidencia.contraditoria for evidencia in evidencias):
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.CONFLITO, documento_b_id=documento_b_id, evidencias=evidencias,
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
            motivos=('evidencia_contraditoria_de_relacao_documental',),
        )

    if not evidencias:
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            motivos=('nenhuma_evidencia_de_relacao_documental_encontrada',),
        )

    forca = _forca_combinada(evidencias)
    if forca == NivelConfianca.FORTE:
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.RESOLVIDA, documento_b_id=documento_b_id, evidencias=evidencias,
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
    return ResolucaoRelacaoDocumental(
        documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
        estado=EstadoResolucaoDimensao.NAO_ENCONTRADA, evidencias=evidencias,
        confianca=ConfiancaResolucao(forca),
        motivos=('evidencia_insuficiente_para_relacao_documental',),
    )


def resolver_relacao_documental_dentre_candidatos(
    documento_a_id: str,
    tipo_relacao: TipoRelacaoDocumental,
    candidatos: Tuple[Tuple[str, Tuple[EvidenciaRelacaoDocumental, ...]], ...],
) -> ResolucaoRelacaoDocumental:
    """Resolve a relação de `documento_a_id` dentre N candidatos a
    `documento_b_id` (ex.: um relatório de benefícios com vários
    comprovantes possíveis). Nunca escolhe por decreto: só `RESOLVIDA`
    quando exatamente 1 candidato atinge força combinada FORTE; 2+
    empatados em FORTE -> `AMBIGUA` (nunca um escolhido arbitrariamente,
    mesmo princípio de cardinalidade de `vinculo_unidade_prestacao`)."""
    if not documento_a_id or not documento_a_id.strip():
        raise ValueError('documento_a_id deve ser texto nao vazio')
    if not candidatos:
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            motivos=('nenhum_candidato_de_relacao_documental_informado',),
        )

    todas_evidencias: Tuple[EvidenciaRelacaoDocumental, ...] = tuple(
        evidencia for _, evidencias_candidato in candidatos for evidencia in evidencias_candidato
    )
    if any(evidencia.contraditoria for evidencia in todas_evidencias):
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.CONFLITO, evidencias=todas_evidencias,
            candidatos_documento_b_id=tuple(documento_b_id for documento_b_id, _ in candidatos),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
            motivos=('evidencia_contraditoria_de_relacao_documental',),
        )

    fortes = tuple(
        documento_b_id for documento_b_id, evidencias_candidato in candidatos
        if _forca_combinada(evidencias_candidato) == NivelConfianca.FORTE
    )
    if len(fortes) == 1:
        evidencias_vencedoras = next(ev for doc_id, ev in candidatos if doc_id == fortes[0])
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.RESOLVIDA, documento_b_id=fortes[0], evidencias=evidencias_vencedoras,
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
    if len(fortes) >= 2:
        return ResolucaoRelacaoDocumental(
            documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
            estado=EstadoResolucaoDimensao.AMBIGUA, candidatos_documento_b_id=fortes, evidencias=todas_evidencias,
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
            motivos=('multiplos_candidatos_empatados_em_relacao_documental',),
        )
    return ResolucaoRelacaoDocumental(
        documento_a_id=documento_a_id, tipo_relacao=tipo_relacao,
        estado=EstadoResolucaoDimensao.NAO_ENCONTRADA, evidencias=todas_evidencias,
        candidatos_documento_b_id=tuple(documento_b_id for documento_b_id, _ in candidatos),
        motivos=('nenhum_candidato_atinge_evidencia_suficiente_para_relacao_documental',),
    )


@dataclasses.dataclass(frozen=True)
class DadosCorrelacaoDocumental:
    """Campos JÁ EXTRAÍDOS de um documento, usados para produzir
    evidência de relação com outro. Este dataclass é GENÉRICO -- nunca
    `DadosCorrelacaoBeneficios`/`DadosCorrelacaoFgts` (§5/§9: mesmo
    contrato para toda família). Todo campo é opcional -- a ausência de
    um campo nunca impede a avaliação dos demais (§6)."""

    identificador_pedido: Optional[str] = None
    valor_total: Optional[str] = None
    competencia: Optional[Tuple[int, int]] = None
    origem: Optional[str] = None
    data: Optional[str] = None
    fornecedor: Optional[str] = None
    lote_ingestao_id: Optional[str] = None


def produzir_evidencias_correlacao(
    a: DadosCorrelacaoDocumental, b: DadosCorrelacaoDocumental,
) -> Tuple[EvidenciaRelacaoDocumental, ...]:
    """Compara campos JÁ EXTRAÍDOS de dois documentos e produz
    evidências -- NUNCA decide sozinha (cabe ao resolvedor combinar).
    Nenhum campo isolado emite `FORTE` (§6: "valor total sozinho NÃO
    basta, data sozinha NÃO basta, fornecedor sozinho NÃO basta") --
    mesmo um identificador de pedido/lote IGUAL é `MODERADA`, exigindo
    combinação com pelo menos mais um campo para virar `FORTE` via a
    regra de combinação (2+ MODERADA -> FORTE). Um identificador
    DIVERGENTE (ambos presentes, valores diferentes) é sinal de
    CONFLITO real -- essa evidência sozinha já é suficiente para não
    deixar a relação passar como resolvida silenciosamente."""
    evidencias = []

    if a.identificador_pedido and b.identificador_pedido:
        if a.identificador_pedido == b.identificador_pedido:
            evidencias.append(EvidenciaRelacaoDocumental(
                tipo_evidencia='MESMO_IDENTIFICADOR_PEDIDO_LOTE', forca=NivelConfianca.MODERADA,
                motivo_sanitizado='identificador_de_pedido_ou_lote_coincide',
            ))
        else:
            evidencias.append(EvidenciaRelacaoDocumental(
                tipo_evidencia='IDENTIFICADOR_PEDIDO_LOTE_DIVERGENTE', forca=NivelConfianca.FORTE,
                motivo_sanitizado='identificador_de_pedido_ou_lote_diverge', contraditoria=True,
            ))

    if a.valor_total and b.valor_total and a.valor_total == b.valor_total:
        evidencias.append(EvidenciaRelacaoDocumental(
            tipo_evidencia='MESMO_VALOR_TOTAL', forca=NivelConfianca.MODERADA,
            motivo_sanitizado='valor_total_coincide',
        ))

    if a.competencia and b.competencia and a.competencia == b.competencia:
        evidencias.append(EvidenciaRelacaoDocumental(
            tipo_evidencia='MESMA_COMPETENCIA', forca=NivelConfianca.MODERADA,
            motivo_sanitizado='competencia_coincide',
        ))

    if a.origem and b.origem and a.origem == b.origem:
        evidencias.append(EvidenciaRelacaoDocumental(
            tipo_evidencia='MESMA_ORIGEM_REMESSA', forca=NivelConfianca.MODERADA,
            motivo_sanitizado='origem_ou_remessa_coincide',
        ))

    if a.lote_ingestao_id and b.lote_ingestao_id and a.lote_ingestao_id == b.lote_ingestao_id:
        evidencias.append(EvidenciaRelacaoDocumental(
            tipo_evidencia='MESMO_LOTE_INGESTAO', forca=NivelConfianca.MODERADA,
            motivo_sanitizado='lote_de_ingestao_coincide',
        ))

    if a.data and b.data and a.data == b.data:
        evidencias.append(EvidenciaRelacaoDocumental(
            tipo_evidencia='PROXIMIDADE_TEMPORAL', forca=NivelConfianca.FRACA,
            motivo_sanitizado='data_coincide',
        ))

    if a.fornecedor and b.fornecedor and a.fornecedor == b.fornecedor:
        evidencias.append(EvidenciaRelacaoDocumental(
            tipo_evidencia='MESMO_FORNECEDOR', forca=NivelConfianca.FRACA,
            motivo_sanitizado='fornecedor_coincide',
        ))

    return tuple(evidencias)


_PADRAO_IDENTIFICADOR_PEDIDO = None
_PADRAO_VALOR_TOTAL = None
_PADRAO_DATA = None


def _padroes_extracao():
    """Compilados sob demanda (nunca no import) para manter este módulo
    livre de custo de import quando a extração de texto não é usada
    (ex.: quem só quer o resolvedor puro para dados já estruturados)."""
    global _PADRAO_IDENTIFICADOR_PEDIDO, _PADRAO_VALOR_TOTAL, _PADRAO_DATA
    import re

    if _PADRAO_IDENTIFICADOR_PEDIDO is None:
        _PADRAO_IDENTIFICADOR_PEDIDO = re.compile(
            r'(?:Pedido|Lote|Refer[êe]ncia)\s*n?[ºo°]?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/.]{2,29})',
            re.IGNORECASE,
        )
        _PADRAO_VALOR_TOTAL = re.compile(
            r'(?:Valor\s+Total|Total\s+d[oa]\s+(?:Pedido|Lote)|Total\s+Geral)\s*[:\-]?\s*R\$\s*([\d.,]+)',
            re.IGNORECASE,
        )
        _PADRAO_DATA = re.compile(r'Data\s*[:\-]?\s*(\d{2}/\d{2}/\d{2,4})', re.IGNORECASE)
    return _PADRAO_IDENTIFICADOR_PEDIDO, _PADRAO_VALOR_TOTAL, _PADRAO_DATA


def extrair_dados_correlacao_de_texto(
    texto: str, padrao_fornecedor: Optional[Pattern] = None,
) -> DadosCorrelacaoDocumental:
    """Extração GENÉRICA (nunca por fornecedor/família) dos campos
    comparáveis de `DadosCorrelacaoDocumental` a partir de texto bruto.
    `padrao_fornecedor` é injetado por quem chama (ex.: a lista de
    fornecedores de benefícios já cadastrada em
    `produtores_evidencia_beneficios._FORNECEDORES_CONHECIDOS`) -- este
    módulo nunca conhece nomes de fornecedor específicos (§5/§9:
    "zero dependência de fornecedor no core"). Reaproveita
    `extrair_competencia_de_texto` já existente (`dominio.py`) -- nunca
    uma segunda extração de competência paralela."""
    identificador_re, valor_re, data_re = _padroes_extracao()

    identificador_match = identificador_re.search(texto)
    valor_match = valor_re.search(texto)
    data_match = data_re.search(texto)
    fornecedor_match = padrao_fornecedor.search(texto) if padrao_fornecedor else None

    competencia_extraida = extrair_competencia_de_texto(texto)
    competencia = (
        competencia_extraida.ano_mes
        if competencia_extraida.status == StatusExtracaoCompetencia.ENCONTRADA else None
    )

    return DadosCorrelacaoDocumental(
        identificador_pedido=identificador_match.group(1) if identificador_match else None,
        valor_total=valor_match.group(1) if valor_match else None,
        competencia=competencia,
        data=data_match.group(1) if data_match else None,
        fornecedor=fornecedor_match.group(0).strip().lower() if fornecedor_match else None,
    )
