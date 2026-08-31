"""Produtor de RELATÓRIO/PEDIDO DE BENEFÍCIOS (Adendo substitutivo ao
PR #105 — regra canônica confirmada: VR e VA normalmente são
processados num MESMO relatório de pedido, por colaborador; o
comprovante de pagamento correspondente é um documento separado).

REGRA PÉTREA (§2 do adendo): um documento físico pode conter DUAS
categorias de benefício (VR e VA) ao mesmo tempo — este produtor NUNCA
força o motor a escolher exclusivamente entre "VR" ou "VA" como
`tipo_documental`. Existe UM tipo container ('Relatório de Benefícios')
para o relatório/pedido; a presença de rubrica VR/VA vira EVIDÊNCIA
informativa anexada à MESMA hipótese, nunca um candidato concorrente.

REGRA PÉTREA (§7/§9): o FORNECEDOR (VR Benefícios, iFood Benefícios, ou
qualquer futuro) é EVIDÊNCIA/METADADO, nunca identidade do tipo
documental — nenhuma classe/pipeline por fornecedor é criada aqui; o
nome do fornecedor, quando presente, é só mais um sinal FRACO que nunca
decide sozinho (mesma disciplina já usada para "nome do arquivo é só
sinal", cláusula pétrea geral do motor)."""
from __future__ import annotations

import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental

TIPO_RELATORIO_BENEFICIOS = 'Relatório de Benefícios'

_PADRAO_RELATORIO_BENEFICIOS = re.compile(
    r'Relat[óo]rio\s+de\s+Benef[íi]cios|Pedido\s+de\s+Benef[íi]cios|'
    r'Cr[ée]dito\s+de\s+Benef[íi]cios|Solicita[çc][ãa]o\s+de\s+Benef[íi]cios',
    re.IGNORECASE,
)
_PADRAO_RUBRICA_VR = re.compile(r'Vale[-\s]?Refei[çc][ãa]o', re.IGNORECASE)
_PADRAO_RUBRICA_VA = re.compile(r'Vale[-\s]?Alimenta[çc][ãa]o', re.IGNORECASE)
_PADRAO_TOTAL_PEDIDO = re.compile(r'Total\s+do\s+Pedido|Valor\s+Total\s+d[oa]\s+Pedido', re.IGNORECASE)
# Linha de beneficiário: CPF + valor monetário na MESMA linha -- mesmo
# padrão estrutural já provado para Ponto (linha repetida >= 2x vira
# evidência estrutural real, nunca 1 linha isolada).
_PADRAO_LINHA_BENEFICIARIO = re.compile(
    r'\d{3}\.\d{3}\.\d{3}-\d{2}.*R\$\s*[\d.,]+', re.MULTILINE,
)
# Fornecedor -- sinal FRACO, nunca decide sozinho (§7/§9: fornecedor é
# metadado, não identidade). Lista aberta por desenho -- adicionar um
# fornecedor novo é adicionar um nome à lista, nunca uma classe nova.
_FORNECEDORES_CONHECIDOS = re.compile(
    r'iFood\s+Benef[íi]cios|VR\s+Benef[íi]cios|Alelo|Sodexo|Ticket', re.IGNORECASE,
)


def hipoteses_de_relatorio_beneficios(texto: str) -> Tuple[HipoteseTipoDocumental, ...]:
    """A frase característica de relatório/pedido de benefícios é
    NECESSÁRIA (sem ela, nenhuma hipótese) e já SUFICIENTE sozinha —
    FORTE, não MODERADA: "Relatório/Pedido/Crédito de Benefícios" é uma
    frase deliberada e específica (baixíssimo falso-positivo), mais
    específica que a mera menção solta de "vale-refeição"/"vale-
    alimentação" em qualquer texto (que já alimenta, com força
    MODERADA, a hipótese SEPARADA 'Comprovante de Pagamento - VR/VA' em
    `finalidade_comprovante_pagamento.py` -- correta para um comprovante
    bancário avulso, mas nunca deve vencer um relatório/pedido já
    identificado pela própria frase). Sem essa força FORTE aqui, um
    relatório com rubricas VR/VA no corpo ficaria empatado em MODERADA
    contra essa outra hipótese e viraria AMBIGUA -- exatamente o que a
    regra pétrea do adendo (§2) proíbe: nunca forçar uma escolha
    inconclusiva quando o próprio relatório já se identifica.

    Rubrica VR/VA, total do pedido, linhas de beneficiário e fornecedor
    conhecido são evidências ADICIONAIS anexadas à MESMA hipótese --
    nunca candidatos concorrentes 'VR'/'VA'/'iFood'."""
    if not texto or not _PADRAO_RELATORIO_BENEFICIOS.search(texto):
        return ()

    evidencias = [EvidenciaSanitizada(
        tipo_evidencia='BENEFICIOS_RELATORIO_PEDIDO_PALAVRA_CHAVE', fonte='produtor_evidencia_beneficios',
        referencia_fonte='relatorio_ou_pedido_de_beneficios', metodo='regex_relatorio_beneficios',
        forca=NivelConfianca.FORTE,
    )]
    if _PADRAO_RUBRICA_VR.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_CONTEM_RUBRICA_VR', fonte='produtor_evidencia_beneficios',
            referencia_fonte='rubrica_vale_refeicao', metodo='regex_rubrica_vr', forca=NivelConfianca.FRACA,
        ))
    if _PADRAO_RUBRICA_VA.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_CONTEM_RUBRICA_VA', fonte='produtor_evidencia_beneficios',
            referencia_fonte='rubrica_vale_alimentacao', metodo='regex_rubrica_va', forca=NivelConfianca.FRACA,
        ))
    if _PADRAO_TOTAL_PEDIDO.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_TOTAL_DO_PEDIDO', fonte='produtor_evidencia_beneficios',
            referencia_fonte='total_do_pedido', metodo='regex_total_pedido', forca=NivelConfianca.FRACA,
        ))
    if len(_PADRAO_LINHA_BENEFICIARIO.findall(texto)) >= 2:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_TABELA_BENEFICIARIOS', fonte='produtor_evidencia_beneficios',
            referencia_fonte='linhas_de_beneficiario_repetidas', metodo='regex_linha_beneficiario',
            forca=NivelConfianca.FRACA,
        ))
    fornecedor = _FORNECEDORES_CONHECIDOS.search(texto)
    if fornecedor:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_FORNECEDOR_CONHECIDO', fonte='produtor_evidencia_beneficios',
            referencia_fonte='fornecedor_de_beneficios', metodo='regex_fornecedor_beneficios',
            forca=NivelConfianca.FRACA,
        ))
    return (HipoteseTipoDocumental(tipo_documental=TIPO_RELATORIO_BENEFICIOS, evidencias=tuple(evidencias)),)
