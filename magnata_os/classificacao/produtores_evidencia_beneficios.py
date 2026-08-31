"""Produtor de RELATÓRIO/PEDIDO DE BENEFÍCIOS (Adendo substitutivo ao
PR #105 — regra canônica confirmada: VR e VA normalmente são
processados num MESMO relatório de pedido, por colaborador; o
comprovante de pagamento correspondente é um documento separado).

CORREÇÃO FINAL PRÉ-MERGE (2ª revisão): a versão anterior deste produtor
declarava a frase "Relatório/Pedido/Crédito de Benefícios" NECESSÁRIA E
SUFICIENTE, com força FORTE — isso violava a cláusula pétrea geral do
motor ("palavra/regex/rótulo é evidência, nunca identidade suficiente
sozinha"). Corrigido: NENHUMA evidência isolada resolve sozinha. O
título/rótulo agora é FRACA (nunca decide sozinho — Fase A do review:
"somente a frase, sem tabela/valores/beneficiários, NÃO pode resolver
automaticamente"). A resolução só ocorre por COMBINAÇÃO real de
evidências estruturais — nunca por depender de um título específico
(Fase B-D do review: um relatório sem "Relatório de Benefícios" no
texto, mas com linha(s) de valor por rubrica e/ou múltiplos
beneficiários e/ou total do pedido, deve poder resolver igual).

REGRA PÉTREA (§2/§6 do adendo original, preservada): um documento
físico pode conter DUAS categorias de benefício (VR e VA) ao mesmo
tempo — este produtor NUNCA força o motor a escolher exclusivamente
entre "VR" ou "VA" como `tipo_documental`. Existe UM tipo container
('Relatório de Benefícios'); rubrica VR/VA vira EVIDÊNCIA anexada à
MESMA hipótese, nunca um candidato concorrente.

REGRA PÉTREA (§5/§7/§9 do adendo original, preservada): o FORNECEDOR
(VR Benefícios, iFood Benefícios, ou qualquer futuro) é EVIDÊNCIA/
METADADO, nunca identidade do tipo documental — nenhuma classe/pipeline
por fornecedor é criada aqui. Um fornecedor DESCONHECIDO nunca impede a
classificação (a estrutura do documento é o que importa, nunca a lista
fechada de nomes) -- a lista de nomes conhecidos é só um sinal FRACO
adicional, nunca uma condição."""
from __future__ import annotations

import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca, ReferenciaCanonica
from .relacao_documental import DadosCorrelacaoDocumental, extrair_dados_correlacao_de_texto
from .resolucao_tipo_documental import HipoteseTipoDocumental

TIPO_RELATORIO_BENEFICIOS = 'Relatório de Benefícios'

# Título/rótulo -- NECESSÁRIO para nenhuma hipótese ser emitida sem
# nenhum sinal, mas NUNCA suficiente sozinho (sempre FRACA, como
# qualquer frase isolada do motor -- cláusula pétrea geral: "palavra ou
# frase isolada nunca são identidade suficiente").
_PADRAO_RELATORIO_BENEFICIOS = re.compile(
    r'Relat[óo]rio\s+de\s+Benef[íi]cios|Pedido\s+de\s+Benef[íi]cios|'
    r'Cr[ée]dito\s+de\s+Benef[íi]cios|Solicita[çc][ãa]o\s+de\s+Benef[íi]cios',
    re.IGNORECASE,
)
# Rubrica mencionada isoladamente (sem valor associado na mesma linha)
# -- sinal FRACO, reforça mas nunca decide.
_PADRAO_RUBRICA_VR = re.compile(r'Vale[-\s]?Refei[çc][ãa]o', re.IGNORECASE)
_PADRAO_RUBRICA_VA = re.compile(r'Vale[-\s]?Alimenta[çc][ãa]o', re.IGNORECASE)
# Linha de BENEFÍCIO COM VALOR -- rubrica + valor monetário na MESMA
# linha (até 40 caracteres de distância) -- padrão estrutural mais
# específico que a rubrica isolada: uma rubrica "amarrada" a um valor é
# o formato real de uma linha de relatório/pedido de benefícios, pouco
# provável de aparecer, por acidente, num comprovante bancário genérico
# (que tipicamente só mostra "Valor: R$ X" sem o nome da rubrica ao
# lado). MODERADA -- mas nunca sozinha o bastante para vencer uma
# hipótese concorrente também MODERADA (ex.: 'Comprovante de Pagamento
# - VR/VA', que qualquer menção solta de "vale-refeição" já alimenta);
# precisa combinar com OUTRA evidência MODERADA (total do pedido ou
# múltiplos beneficiários) para virar FORTE -- nunca por decreto, só
# pela regra de combinação já existente do motor (2+ MODERADA -> FORTE).
_PADRAO_LINHA_VALOR_RUBRICA = re.compile(
    r'(?:Vale[-\s]?Refei[çc][ãa]o|Vale[-\s]?Alimenta[çc][ãa]o)[^\n]{0,40}?R\$\s*[\d.,]+',
    re.IGNORECASE,
)
# Total do pedido/lote -- marcador deliberado e específico de um
# documento de LOTE (nunca presente num comprovante bancário
# individual) -- MODERADA.
_PADRAO_TOTAL_PEDIDO = re.compile(r'Total\s+do\s+Pedido|Valor\s+Total\s+d[oa]\s+Pedido', re.IGNORECASE)
# Fornecedor -- sinal FRACO, nunca decide sozinho e nunca é exigido
# (§5/§9: fornecedor desconhecido nunca impede classificação). Lista
# aberta por desenho -- adicionar um fornecedor novo é adicionar um
# nome à lista, nunca uma classe nova; um fornecedor FORA da lista
# simplesmente não contribui esta evidência específica, mas a
# resolução continua por estrutura.
_FORNECEDORES_CONHECIDOS = re.compile(
    r'iFood\s+Benef[íi]cios|VR\s+Benef[íi]cios|Alelo|Sodexo|Ticket', re.IGNORECASE,
)


def hipoteses_de_relatorio_beneficios(texto: str) -> Tuple[HipoteseTipoDocumental, ...]:
    """Nenhuma evidência isolada resolve sozinha -- a resolução final
    (RESOLVIDA/AMBIGUA/NAO_ENCONTRADA) é sempre decidida por
    `resolver_tipo_documental` (o mesmo motor único, nenhuma regra
    nova aqui), a partir da combinação de forças já suportada pelo
    motor (FRACA isolada -> insuficiente; 2+ MODERADA -> FORTE).

    Sem NENHUM sinal (nem título, nem rubrica, nem valor, nem
    fornecedor), nenhuma hipótese é emitida."""
    if not texto:
        return ()

    ocorrencias_valor_rubrica = _PADRAO_LINHA_VALOR_RUBRICA.findall(texto)
    tem_titulo = bool(_PADRAO_RELATORIO_BENEFICIOS.search(texto))
    tem_rubrica_vr_isolada = bool(_PADRAO_RUBRICA_VR.search(texto))
    tem_rubrica_va_isolada = bool(_PADRAO_RUBRICA_VA.search(texto))
    tem_total_pedido = bool(_PADRAO_TOTAL_PEDIDO.search(texto))
    fornecedor = _FORNECEDORES_CONHECIDOS.search(texto)

    if not (
        tem_titulo or tem_rubrica_vr_isolada or tem_rubrica_va_isolada
        or ocorrencias_valor_rubrica or tem_total_pedido or fornecedor
    ):
        return ()

    evidencias = []
    if tem_titulo:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_RELATORIO_PEDIDO_PALAVRA_CHAVE', fonte='produtor_evidencia_beneficios',
            referencia_fonte='relatorio_ou_pedido_de_beneficios', metodo='regex_relatorio_beneficios',
            forca=NivelConfianca.FRACA,
        ))
    if tem_rubrica_vr_isolada:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_CONTEM_RUBRICA_VR', fonte='produtor_evidencia_beneficios',
            referencia_fonte='rubrica_vale_refeicao', metodo='regex_rubrica_vr', forca=NivelConfianca.FRACA,
        ))
    if tem_rubrica_va_isolada:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_CONTEM_RUBRICA_VA', fonte='produtor_evidencia_beneficios',
            referencia_fonte='rubrica_vale_alimentacao', metodo='regex_rubrica_va', forca=NivelConfianca.FRACA,
        ))
    if ocorrencias_valor_rubrica:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_LINHA_VALOR_POR_RUBRICA', fonte='produtor_evidencia_beneficios',
            referencia_fonte='linha_de_beneficio_com_valor', metodo='regex_linha_valor_rubrica',
            forca=NivelConfianca.MODERADA,
        ))
    if len(ocorrencias_valor_rubrica) >= 2:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_MULTIPLOS_BENEFICIARIOS', fonte='produtor_evidencia_beneficios',
            referencia_fonte='multiplas_linhas_de_beneficio_com_valor', metodo='contagem_linha_valor_rubrica',
            forca=NivelConfianca.MODERADA,
        ))
    if tem_total_pedido:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_TOTAL_DO_PEDIDO', fonte='produtor_evidencia_beneficios',
            referencia_fonte='total_do_pedido', metodo='regex_total_pedido', forca=NivelConfianca.MODERADA,
        ))
    if fornecedor:
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='BENEFICIOS_FORNECEDOR_CONHECIDO', fonte='produtor_evidencia_beneficios',
            referencia_fonte='fornecedor_de_beneficios', metodo='regex_fornecedor_beneficios',
            forca=NivelConfianca.FRACA,
        ))
    return (HipoteseTipoDocumental(tipo_documental=TIPO_RELATORIO_BENEFICIOS, evidencias=tuple(evidencias)),)


def dados_correlacao_beneficios(texto: str) -> DadosCorrelacaoDocumental:
    """Extração dos campos comparáveis de RELAÇÃO (§6 da missão "MERGE
    PR #105 + EVIDÊNCIA RELACIONAL...") para Relatório de Benefícios OU
    seu Comprovante -- mesma função para os dois lados do par, já que o
    extrator (`relacao_documental.extrair_dados_correlacao_de_texto`) é
    genérico. O único detalhe específico de benefícios injetado aqui é
    a lista de fornecedores JÁ cadastrada (`_FORNECEDORES_CONHECIDOS`,
    reaproveitada -- nunca uma segunda lista paralela); o extrator em si
    nunca conhece o nome de nenhum fornecedor (§5/§9: zero dependência
    de fornecedor no core)."""
    return extrair_dados_correlacao_de_texto(texto, padrao_fornecedor=_FORNECEDORES_CONHECIDOS)


def derivar_clientes_logicos_do_comprovante_global(
    relacao_resolvida: bool, clientes_do_relatorio: Tuple[ReferenciaCanonica, ...],
) -> Tuple[ReferenciaCanonica, ...]:
    """§7/§8 da missão: um COMPROVANTE GLOBAL de benefícios (1 documento
    físico, 1 `documento_id`, nunca duplicado) só herda os clientes A/B/C
    do RELATÓRIO relacionado quando a relação COMPROVA já está
    `RESOLVIDA` (`relacao_resolvida=True`, decidido por
    `relacao_documental.resolver_relacao_documental_par/_dentre_
    candidatos` -- nunca reavaliado aqui) -- e SEMPRE o mesmo conjunto
    de clientes já resolvido para o relatório (nunca um subconjunto
    escolhido por este módulo, nunca um valor recalculado a partir do
    comprovante isoladamente: "o comprovante nunca decompõe
    individualmente, os valores sempre vêm do relatório").

    Sem relação resolvida: `()` -- NUNCA um cliente é atribuído por
    suposição (§6: "não inventar relação sem evidência"); o comprovante
    fica sem clientes lógicos até haver evidência suficiente (revisão
    humana a partir daí, via o mesmo roteamento de
    `automacao_por_confianca` para NAO_ENCONTRADA).

    Identidade física preservada: esta função NUNCA cria um novo
    `documento_id` nem duplica o arquivo -- só devolve o CONJUNTO de
    clientes que, em conjunto com o `documento_id` já existente do
    comprovante, formam N relações lógicas via o MESMO mecanismo já
    existente (`ItemInventarioPrestacao.identidade_logica`, §17 --
    nunca alterado por esta função)."""
    if not relacao_resolvida:
        return ()
    return clientes_do_relatorio
