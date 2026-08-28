"""Classificador de tipo documental — puro, sem dependências de infraestrutura.

Fonte de verdade: app.py TIPO_DOC_REGRAS (linhas 503-599).
Reproduz 100% da lógica legada, mas com uma diferença deliberada de
segurança: o legado decide pelo primeiro tipo que casar, sem checar se
essa precedência é realmente conhecida. Este módulo TORNA EXPLÍCITA a
precedência histórica comprovada (`_PRECEDENCIA_HISTORICA` abaixo) e só
resolve automaticamente uma colisão entre tipos quando ela está nessa
lista. Qualquer colisão fora dela vira AMBIGUA + revisão humana — nunca
decidida por "quem vem primeiro na lista" sozinho.

Precedências históricas comprovadas (citadas em app.py, com data do
achado em produção quando disponível):
- Rescisão > Holerite (05/07/2026 — TRCT com "Valor Líquido")
- Rescisão > Contrato de Trabalho (rescisão sempre cita "contrato de trabalho")
- Rescisão > Contrato de Experiência (mesmo motivo)
- Extrato da Folha de Pagamento > Holerite (extrato cita "Total de
  Vencimentos"/"Valor Líquido" como agregado)
- DCTFWeb - Recibo de Entrega > DCTFWeb - Declaração (senão o \bDCTFWeb\b
  genérico sempre vence antes do recibo ser testado)
- Guia DCTFWeb/DARF > DCTFWeb - Declaração (mesmo motivo: guia é mais
  específica que a declaração genérica)
- FGTS > Holerite, EPI, Ficha de Registro de Empregado, Contrato de
  Experiência, Contrato de Trabalho, Férias (10/07/2026 — Guia Emitida
  FGTS Digital com glossário citando "Contrato de trabalho Verde e
  Amarelo" várias vezes)
- Termo de Prorrogação de Contrato de Experiência > Contrato de
  Experiência (o termo sempre cita "contrato de experiência" no corpo)
- Ficha de Registro de Empregado > Contrato de Trabalho (ficha cita
  número de CTPS, que também bate com \bCTPS\b de Contrato de Trabalho)

Padrões removidos (por comprovação de falso positivo em produção) —
NUNCA reintroduzidos:
- 'Líquido rescisão' e 'Férias Rescisão' de Rescisão (05/07/2026: são
  rubricas de linha dentro de holerites, não indicador de documento;
  causaram falso positivo em lote de 110 páginas de holerites reais)

Nenhum import de app.py (legado protegido).
Nenhuma dependência de Flask, Airtable, Postgres, boto3.
Puro: determinístico, sem I/O, sem PII.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class EstadoClassificacao(str, Enum):
    """Estados finais da classificação."""
    RESOLVIDA = "RESOLVIDA"              # Um único tipo casou, ou colisão coberta por precedência histórica comprovada
    AMBIGUA = "AMBIGUA"                  # Múltiplos tipos casaram sem precedência histórica conhecida entre eles
    NAO_RECONHECIDA = "NAO_RECONHECIDA"  # Nenhum padrão casou (fallback "Outro")
    INVALIDA = "INVALIDA"                # Entrada malformada (ex: não é string)


@dataclass(frozen=True)
class ResultadoClassificacaoDocumental:
    """Contrato imutável de resultado de classificação.

    Campos:
    - tipo_documental: resultado da classificação (string exata como em
      app.py); "Outro" quando NAO_RECONHECIDA ou AMBIGUA (neste último
      caso, nenhum tipo é escolhido sem confiança — ver `tipos_concorrentes`
      para os candidatos).
    - estado: semântica da confiança (RESOLVIDA/AMBIGUA/NAO_RECONHECIDA/INVALIDA).
    - quantidade_hits: número total de padrões que casaram (0+).
    - regras_matching: identificadores dos padrões que casaram — apenas
      códigos internos de regra, nunca texto do documento nem PII.
    - tipos_concorrentes: outros tipos cujos padrões também casaram no
      mesmo texto (sanitizado — só o nome do tipo, nunca a evidência bruta).
    - necessita_revisao_humana: True se deve ir para fila de revisão.
    - prioridade_revisao: sugestão de prioridade se necessita_revisao_humana.
    """
    tipo_documental: str
    estado: EstadoClassificacao
    quantidade_hits: int
    regras_matching: Tuple[str, ...] = ()
    tipos_concorrentes: Tuple[str, ...] = ()
    necessita_revisao_humana: bool = False
    prioridade_revisao: Optional[str] = None

    def __post_init__(self) -> None:
        """Validações estruturais."""
        if not isinstance(self.tipo_documental, str) or not self.tipo_documental.strip():
            raise ValueError("tipo_documental deve ser string não-vazia")
        if not isinstance(self.estado, EstadoClassificacao):
            raise ValueError("estado deve ser EstadoClassificacao")
        if self.quantidade_hits < 0:
            raise ValueError("quantidade_hits não pode ser negativa")

        # Validações de coerência
        if self.estado == EstadoClassificacao.RESOLVIDA:
            if self.quantidade_hits == 0:
                raise ValueError("RESOLVIDA exige quantidade_hits > 0")
        elif self.estado == EstadoClassificacao.NAO_RECONHECIDA:
            if self.quantidade_hits != 0:
                raise ValueError("NAO_RECONHECIDA exige quantidade_hits == 0")
            if self.tipo_documental != "Outro":
                raise ValueError("NAO_RECONHECIDA exige tipo_documental == 'Outro'")
        elif self.estado == EstadoClassificacao.AMBIGUA:
            if self.quantidade_hits == 0:
                raise ValueError("AMBIGUA exige quantidade_hits > 0")
            if not self.necessita_revisao_humana:
                raise ValueError("AMBIGUA exige necessita_revisao_humana=True")
            if len(self.tipos_concorrentes) < 2:
                raise ValueError(
                    "AMBIGUA exige ao menos 2 tipos concorrentes registrados")

        if self.necessita_revisao_humana and not self.prioridade_revisao:
            raise ValueError(
                "necessita_revisao_humana exige prioridade_revisao (ALTA/MEDIA/BAIXA)")
        if not self.necessita_revisao_humana and self.prioridade_revisao:
            raise ValueError(
                "prioridade_revisao só pode existir quando necessita_revisao_humana=True")


# Regras compiladas uma única vez — mesmos tipos, mesma ordem e mesmos
# regex de app.py TIPO_DOC_REGRAS. A ORDEM AQUI SÓ SERVE PARA DESEMPATE
# QUANDO A COLISÃO JÁ É CONHECIDA (ver _PRECEDENCIA_HISTORICA abaixo) —
# ela deixou de ser, sozinha, autorização para decidir uma colisão nova.
# Cada entrada: (tipo, [(identificador_pattern, regex_compilada), ...])
_REGRAS_COMPILADAS: list[tuple[str, list[tuple[str, re.Pattern]]]] = [
    # 1. Rescisão
    ("Rescisão", [
        ("termo_rescisao", re.compile(r'Termo\s+de\s+Rescis[ãa]o', re.IGNORECASE)),
        ("aviso_rescisao", re.compile(r'Aviso\s+de\s+Rescis[ãa]o', re.IGNORECASE)),
        ("trct", re.compile(r'\bTRCT\b', re.IGNORECASE)),
        ("rescisao_contrato_trabalho", re.compile(r'Rescis[ãa]o\s+(?:do\s+)?Contrato\s+de\s+Trabalho', re.IGNORECASE)),
        ("homologacao_rescisao", re.compile(r'Homologa[çc][ãa]o\s+(?:de\s+)?Rescis[ãa]o', re.IGNORECASE)),
        ("calculo_rescisao", re.compile(r'C[áa]lculo\s+de\s+Rescis[ãa]o', re.IGNORECASE)),
        ("motivo_demissao", re.compile(r'Motivo\s+demiss[ãa]o', re.IGNORECASE)),
        ("data_demissao_1", re.compile(r'Data\s+demiss[ãa]o', re.IGNORECASE)),
        ("data_demissao_2", re.compile(r'Data\s+de\s+demiss[ãa]o', re.IGNORECASE)),
    ]),

    # 2. Extrato da Folha de Pagamento
    ("Extrato da Folha de Pagamento", [
        ("extrato_folha_pagamento", re.compile(r'Extrato\s+(?:da\s+)?Folha\s+de\s+Pagamento', re.IGNORECASE)),
        ("extrato_mensal", re.compile(r'Extrato\s+Mensal\b', re.IGNORECASE)),
    ]),

    # 3. DCTFWeb - Recibo de Entrega
    ("DCTFWeb - Recibo de Entrega", [
        ("recibo_dctfweb_1", re.compile(r'Recibo\s+de\s+Entrega.{0,60}DCTFWeb', re.IGNORECASE)),
        ("recibo_dctfweb_2", re.compile(r'DCTFWeb.{0,60}Recibo\s+de\s+Entrega', re.IGNORECASE)),
    ]),

    # 4. Guia DCTFWeb/DARF
    ("Guia DCTFWeb/DARF", [
        ("guia_dctfweb_1", re.compile(r'Guia\s+(?:de\s+Recolhimento\s+)?(?:da\s+)?DCTFWeb\b', re.IGNORECASE)),
        ("dctfweb_darf_1", re.compile(r'DCTFWeb\s*[-–—:/]?\s*DARF\b', re.IGNORECASE)),
        ("darf_dctfweb", re.compile(r'DARF\s*[-–—:/]?(?:\s+da)?\s+DCTFWeb\b', re.IGNORECASE)),
    ]),

    # 5. DCTFWeb - Declaração (genérico, catch-all para DCTFWeb)
    ("DCTFWeb - Declaração", [
        ("dctfweb_generico", re.compile(r'\bDCTFWeb\b', re.IGNORECASE)),
    ]),

    # 6. FGTS
    ("FGTS", [
        ("fgts_digital", re.compile(r'FGTS\s+Digital', re.IGNORECASE)),
        ("guia_fgts", re.compile(r'Guia\s+do\s+FGTS', re.IGNORECASE)),
        ("gfd", re.compile(r'\bGFD\b', re.IGNORECASE)),
        ("detalhe_guia_emitida", re.compile(r'Detalhe\s+da\s+Guia\s+Emitida', re.IGNORECASE)),
        ("fgts_mensal_guia", re.compile(r'FGTS\s+Mensal\s+na\s+Guia', re.IGNORECASE)),
        ("qtd_trabalhadores_fgts", re.compile(r'Qtd\.?\s*Trabalhadores\s+FGTS', re.IGNORECASE)),
        ("total_fgts", re.compile(r'Total\s+FGTS\b', re.IGNORECASE)),
    ]),

    # 7. Holerite
    ("Holerite", [
        ("recibo_pagamento", re.compile(r'Recibo\s+de\s+Pagamento', re.IGNORECASE)),
        ("total_vencimentos", re.compile(r'Total\s+de\s+Vencimentos', re.IGNORECASE)),
        ("valor_liquido", re.compile(r'Valor\s+L[íi]quido', re.IGNORECASE)),
    ]),

    # 8. Folha de Ponto
    ("Folha de Ponto", [
        ("folha_ponto", re.compile(r'Folha\s+de\s+Ponto', re.IGNORECASE)),
        ("espelho_ponto", re.compile(r'Espelho\s+de\s+Ponto', re.IGNORECASE)),
        ("cartao_ponto", re.compile(r'Cart[ãa]o\s+(?:de\s+)?Ponto', re.IGNORECASE)),
        ("secullum", re.compile(r'Secullum', re.IGNORECASE)),
        ("ponto_web", re.compile(r'Ponto\s+Web', re.IGNORECASE)),
    ]),

    # 9. EPI
    ("EPI", [
        ("ficha_controle_epi", re.compile(r'Ficha\s+de\s+(?:Controle\s+de\s+)?EPI\b', re.IGNORECASE)),
        ("equipamento_protecao_individual", re.compile(r'Equipamento\s+de\s+Prote[çc][ãa]o\s+Individual', re.IGNORECASE)),
        ("ficha_epis", re.compile(r"Ficha\s+de\s+EPI['\"]?s", re.IGNORECASE)),
        ("epi_generico", re.compile(r'\bEPI\b', re.IGNORECASE)),
        ("recebi_equipamentos", re.compile(r'Recebi\s+(?:o|os|do|dos)\s+(?:seguintes\s+)?equipamentos?', re.IGNORECASE)),
    ]),

    # 10. Termo de Prorrogação de Contrato de Experiência
    ("Termo de Prorrogação de Contrato de Experiência", [
        ("prorrogacao_contrato_experiencia", re.compile(r'Prorroga[çc][ãa]o\s+(?:do\s+)?Contrato\s+de\s+Experi[êe]ncia', re.IGNORECASE)),
        ("termo_aditivo_prorrogacao", re.compile(r'Termo\s+(?:Aditivo\s+)?de\s+Prorroga[çc][ãa]o', re.IGNORECASE)),
    ]),

    # 11. Ficha de Registro de Empregado
    ("Ficha de Registro de Empregado", [
        ("ficha_registro_empregado_1", re.compile(r'Ficha\s+de\s+Registro\s+de\s+Empregados?', re.IGNORECASE)),
        ("registro_empregado_ficha", re.compile(r'Registro\s+de\s+Empregados?\b.{0,40}Ficha', re.IGNORECASE)),
        ("livro_registro_empregado", re.compile(r'Livro\s+(?:de\s+)?Registro\s+de\s+Empregados?', re.IGNORECASE)),
        ("registro_empregado_isolado", re.compile(r'Registro\s+de\s+Empregados?\b', re.IGNORECASE)),
        ("matricula_esocial", re.compile(r'Matr[íi]cula\s+eSocial', re.IGNORECASE)),
    ]),

    # 12. Contrato de Experiência
    ("Contrato de Experiência", [
        ("contrato_experiencia", re.compile(r'Contrato\s+de\s+Experi[êe]ncia', re.IGNORECASE)),
    ]),

    # 13. Contrato de Trabalho
    ("Contrato de Trabalho", [
        ("contrato_trabalho", re.compile(r'Contrato\s+de\s+Trabalho', re.IGNORECASE)),
        ("ctps", re.compile(r'\bCTPS\b', re.IGNORECASE)),
    ]),

    # 14. Férias
    ("Férias", [
        ("aviso_ferias", re.compile(r'Aviso\s+de\s+F[ée]rias', re.IGNORECASE)),
        ("recibo_ferias", re.compile(r'Recibo\s+de\s+F[ée]rias', re.IGNORECASE)),
        ("periodo_gozo", re.compile(r'Per[íi]odo\s+de\s+Gozo', re.IGNORECASE)),
    ]),

    # 15. Guia (fallback genérico para GPS, DARF sem DCTFWeb)
    ("Guia", [
        ("guia_recolhimento", re.compile(r'Guia\s+de\s+Recolhimento', re.IGNORECASE)),
        ("gps", re.compile(r'\bGPS\b', re.IGNORECASE)),
        ("darf_generico", re.compile(r'\bDARF\b', re.IGNORECASE)),
    ]),

    # 16. Boleto
    ("Boleto", [
        ("codigo_barras", re.compile(r'\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14}')),
        ("linha_digitavel", re.compile(r'Linha\s+Digit[áa]vel', re.IGNORECASE)),
    ]),

    # 17. Nota Fiscal
    ("Nota Fiscal", [
        ("nfse", re.compile(r'NFS-?e', re.IGNORECASE)),
        ("nota_fiscal_servico", re.compile(r'Nota\s+Fiscal\s+de\s+Servi[çc]o', re.IGNORECASE)),
        ("danfe", re.compile(r'DANFE', re.IGNORECASE)),
    ]),
]

_TIPOS_VALIDOS = frozenset(tipo for tipo, _ in _REGRAS_COMPILADAS)


def _construir_precedencia(mapa_bruto: dict[str, tuple[str, ...]]) -> dict[str, frozenset[str]]:
    """Valida e congela o mapa de precedência histórica.

    Garante, na importação do módulo, que todo tipo citado (vencedor ou
    perdedor) existe de fato em `_REGRAS_COMPILADAS` — erro de digitação
    aqui não pode passar em silêncio para produção.
    """
    resultado: dict[str, frozenset[str]] = {}
    for vencedor, perdedores in mapa_bruto.items():
        if vencedor not in _TIPOS_VALIDOS:
            raise ValueError(f"precedência histórica cita tipo inexistente: {vencedor!r}")
        for perdedor in perdedores:
            if perdedor not in _TIPOS_VALIDOS:
                raise ValueError(f"precedência histórica cita tipo inexistente: {perdedor!r}")
        resultado[vencedor] = frozenset(perdedores)
    return resultado


# Precedência histórica EXPLÍCITA e FECHADA — a única fonte de autorização
# para resolver automaticamente uma colisão entre dois tipos que casaram
# no mesmo texto. A ordem de `_REGRAS_COMPILADAS` NUNCA é, sozinha,
# suficiente para decidir uma colisão: só entra aqui o que já foi
# comprovado em produção ou está documentado explicitamente em app.py.
#
# Formato: tipo_vencedor -> conjunto de tipos que ele tem autorização
# para vencer quando ambos casarem no mesmo texto.
_PRECEDENCIA_HISTORICA: dict[str, frozenset[str]] = _construir_precedencia({
    # 05/07/2026 — TRCT genuíno contém "Valor Líquido" (discriminação de
    # verbas rescisórias) e cita "contrato de trabalho" no corpo.
    "Rescisão": (
        "Holerite",
        "Contrato de Trabalho",
        "Contrato de Experiência",
    ),
    # Extrato é relatório-resumo da folha; cita "Total de Vencimentos"/
    # "Valor Líquido" como agregado.
    "Extrato da Folha de Pagamento": (
        "Holerite",
    ),
    # Recibo de Entrega e Guia são documentos específicos do sistema
    # DCTFWeb; o padrão genérico \bDCTFWeb\b da Declaração sempre bate
    # também, então sem esta precedência o recibo/guia nunca seriam
    # distinguidos da declaração genérica.
    #
    # "DCTFWeb - Recibo de Entrega" > "Guia DCTFWeb/DARF": comprovado por
    # teste legado real (test_classificacao_guia_dctfweb_darf.py::
    # test_recibo_tem_precedencia_sobre_mencao_a_guia — texto "Recibo de
    # Entrega da DCTFWeb referente à Guia DCTFWeb" espera "DCTFWeb -
    # Recibo de Entrega", não "Guia DCTFWeb/DARF").
    "DCTFWeb - Recibo de Entrega": (
        "DCTFWeb - Declaração",
        "Guia DCTFWeb/DARF",
    ),
    # "Guia DCTFWeb/DARF" > "Guia" (genérica): app.py não tem comentário
    # explícito para este par, mas a ORDEM da lista (posição 4 antes da
    # 15) e o teste legado real comprovam a intenção — qualquer "Guia de
    # Recolhimento DCTFWeb"/"DARF...DCTFWeb" também bate no padrão
    # genérico de Guia (r'Guia\s+de\s+Recolhimento' ou \bDARF\b).
    # Comprovado por test_classificacao_guia_dctfweb_darf.py::
    # test_guia_dctfweb_e_identificada e ::
    # test_darf_sem_sinal_de_dctfweb_permanece_generico (este último
    # confirma que SEM sinal de DCTFWeb, DARF cai no tipo genérico —
    # logo COM sinal de DCTFWeb, a Guia específica tem precedência).
    "Guia DCTFWeb/DARF": (
        "DCTFWeb - Declaração",
        "Guia",
    ),
    # 10/07/2026 — Guia Emitida do FGTS Digital (98 trabalhadores) trouxe
    # glossário de categorias FGTS no rodapé citando "Contrato de
    # trabalho Verde e Amarelo" várias vezes.
    "FGTS": (
        "Holerite",
        "EPI",
        "Ficha de Registro de Empregado",
        "Contrato de Experiência",
        "Contrato de Trabalho",
        "Férias",
    ),
    # O termo de prorrogação sempre menciona "contrato de experiência"
    # no corpo do texto.
    "Termo de Prorrogação de Contrato de Experiência": (
        "Contrato de Experiência",
    ),
    # A ficha de registro cita o número da CTPS, que também bate com o
    # padrão \bCTPS\b de Contrato de Trabalho.
    "Ficha de Registro de Empregado": (
        "Contrato de Trabalho",
    ),
})


def _avaliar_todas_as_regras(texto: str) -> list[tuple[str, tuple[str, ...]]]:
    """Avalia TODOS os tipos (nunca para no primeiro match).

    Necessário para detectar colisão — o legado parava no primeiro tipo
    com hit e nunca sabia se um tipo posterior também teria casado.
    Retorna só os tipos com ao menos 1 hit, na ordem de
    `_REGRAS_COMPILADAS` (usada depois só para desempate quando a
    colisão é conhecida).
    """
    encontrados = []
    for tipo, padroes in _REGRAS_COMPILADAS:
        hits = tuple(identificador for identificador, regex in padroes if regex.search(texto))
        if hits:
            encontrados.append((tipo, hits))
    return encontrados


def classificar_documento(texto: str) -> ResultadoClassificacaoDocumental:
    """Classifica documento por tipo baseado em padrões regex.

    Diferença de segurança em relação a app.py: aqui TODOS os tipos são
    avaliados (não só até o primeiro match). Se mais de um tipo casar:

    - se a combinação exata está coberta por `_PRECEDENCIA_HISTORICA`
      (o candidato mais antigo na ordem legada tem autorização explícita
      para vencer todos os demais que casaram): RESOLVIDA, com o tipo
      vencedor do legado;
    - caso contrário (colisão nova, sem precedência comprovada): AMBIGUA,
      necessita_revisao_humana=True — nunca decidida por "quem vem
      primeiro na lista" sozinho.

    Args:
        texto: Conteúdo do documento a classificar (extraído de PDF, etc).

    Returns:
        ResultadoClassificacaoDocumental com tipo, estado e evidências
        sanitizadas (nunca texto bruto, nunca PII).

    Raises:
        Nunca — entrada inválida vira estado INVALIDA, não exceção.
    """
    if not isinstance(texto, str):
        return ResultadoClassificacaoDocumental(
            tipo_documental="Outro",
            estado=EstadoClassificacao.INVALIDA,
            quantidade_hits=0,
            necessita_revisao_humana=True,
            prioridade_revisao="MEDIA",
        )

    encontrados = _avaliar_todas_as_regras(texto)

    if not encontrados:
        return ResultadoClassificacaoDocumental(
            tipo_documental="Outro",
            estado=EstadoClassificacao.NAO_RECONHECIDA,
            quantidade_hits=0,
        )

    if len(encontrados) == 1:
        tipo, hits = encontrados[0]
        return ResultadoClassificacaoDocumental(
            tipo_documental=tipo,
            estado=EstadoClassificacao.RESOLVIDA,
            quantidade_hits=len(hits),
            regras_matching=hits,
        )

    # Múltiplos tipos casaram — candidato vencedor é o mais antigo na
    # ordem legada; só vence de fato se a precedência sobre TODOS os
    # demais tipos encontrados já é conhecida e comprovada.
    tipo_candidato, hits_candidato = encontrados[0]
    demais = encontrados[1:]
    tipos_demais = [tipo for tipo, _ in demais]

    autorizados_a_perder = _PRECEDENCIA_HISTORICA.get(tipo_candidato, frozenset())
    nao_cobertos = [tipo for tipo in tipos_demais if tipo not in autorizados_a_perder]

    if not nao_cobertos:
        # Colisão conhecida — precedência histórica comprovada resolve.
        return ResultadoClassificacaoDocumental(
            tipo_documental=tipo_candidato,
            estado=EstadoClassificacao.RESOLVIDA,
            quantidade_hits=len(hits_candidato),
            regras_matching=hits_candidato,
            tipos_concorrentes=tuple(tipos_demais),
        )

    # Colisão nova, sem precedência comprovada — nunca decide sozinho.
    todos_tipos = tuple(tipo for tipo, _ in encontrados)
    todas_regras = tuple(regra for _, hits in encontrados for regra in hits)
    return ResultadoClassificacaoDocumental(
        tipo_documental="Outro",
        estado=EstadoClassificacao.AMBIGUA,
        quantidade_hits=len(todas_regras),
        regras_matching=todas_regras,
        tipos_concorrentes=todos_tipos,
        necessita_revisao_humana=True,
        prioridade_revisao="ALTA",
    )
