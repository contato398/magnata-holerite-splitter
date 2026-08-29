"""Decisão de roteamento documental — pura, sem efeitos, sem I/O externo.

Liga bytes de PDF avulso (ainda na janela transiente de ingestão, antes
de serem descartados — ver auditoria da ponte Documento→ResultadoItem)
ao classificador canônico e produz uma DECISÃO ESTRUTURADA sobre o que o
Magnata OS deveria fazer com o documento. Nunca executa o processamento
em si, nunca escreve Airtable, nunca envia nada, nunca persiste.

Fluxo:
    bytes PDF -> extrair_texto_pdf() -> classificar_documento() -> DecisaoRoteamentoDocumental

Reaproveita integralmente, sem duplicar:
    - `extrair_texto_pdf` (magnata_os/documental/extracao_texto.py) —
      função neutra promovida de importacao_lote/orquestrador.py
      (_extrair_texto_pdf), mesma extração usada por processar_holerite/
      processar_extrato. Nenhuma dependência de módulo privado de outro
      pacote.
    - `classificar_documento` (classificador_documental.py) — classificação
      canônica dos 17 tipos + fallback "Outro", com precedência histórica
      explícita e AMBIGUA para colisão nova (ver esse módulo).

POR QUE A AÇÃO NUNCA É PROCESSAR_AUTOMATICAMENTE NESTA FASE:
Os únicos processadores reais do core novo (`processar_holerite`,
`processar_extrato`, orquestrador.py) exigem `ItemManifestoHolerite`/
`ItemManifestoExtrato` — tipos moldados para o fluxo ZIP/manifesto
(Macro 5/6A: `source_service_number`, `nome_manifesto`, `pagina`, etc.),
nunca bytes avulsos de um Documento único vindo por e-mail. Auditoria
confirmada: nenhum dos 17 tipos tem hoje um processador comprovadamente
compatível com ENTRADA AVULSA. Por isso `_TIPOS_COM_PROCESSADOR_AVULSO_
COMPATIVEL` começa VAZIO de propósito.

QUANDO UM TIPO É RESOLVIDO MAS NÃO TEM PROCESSADOR AVULSO (achado da
revisão desta microetapa — comportamento do legado confirmado em
`app.py`, `_processar_documento_sem_automacao`, docstring: "Handler
genérico para tipos de documento sem processamento automático
implementado ainda... marca o item como 'Revisão Manual' + cria uma
Pendência apontando o Arquivo/PDF original, para que um humano trate o
documento — em vez de o item ficar invisível indefinidamente"):
    A AÇÃO É SEMPRE REVISAR_HUMANO, nunca um terceiro estado "limbo".
    Isso é DIFERENTE de AMBIGUA (colisão de tipos sem precedência) e de
    NAO_RECONHECIDA (nenhum tipo casou) — a classificação continua
    RESOLVIDA, o tipo e o escopo continuam corretos, só a AÇÃO reflete
    que ainda não há automação segura. A distinção fica explícita no
    campo `motivo` (MotivoRoteamento), nunca inferida cruzando outros
    campos.

CLASSIFICAÇÃO DE ESCOPO POR TIPO (auditoria confirmada em legado + core;
corrigida nesta revisão com evidência adicional de `PROCESSADORES_
DOCUMENTO`/`CAPACIDADES_DOCUMENTO`, app.py):
  A. COLABORADOR — documento pessoal do trabalhador (Holerite, Rescisão,
     Folha de Ponto, EPI, Termo de Prorrogação, Ficha de Registro,
     Contrato de Experiência, Contrato de Trabalho, Férias). [9 tipos]
  B. CLIENTE — legado fatia por cliente (`_processar_doc_cliente_master`;
     `CAPACIDADES_DOCUMENTO['FGTS'] = ('Por cliente (CNPJ/Nome)', ...)`),
     mas a partir de um PDF MESTRE multi-cliente, nunca de um Documento
     avulso 1:1 (Extrato da Folha de Pagamento, FGTS). [2 tipos]
  C. COMPETENCIA_GLOBAL — comprovante fiscal da empresa, sem vínculo a
     colaborador/cliente específico; confirmado por
     `CAPACIDADES_DOCUMENTO['DCTFWeb - Recibo de Entrega'] =
     ('Broadcast (mesmo documento p/ todos os clientes ativos)', ...)`
     e idem para 'DCTFWeb - Declaração'. "Guia DCTFWeb/DARF" acompanha o
     mesmo grupo documental DCTFWeb (mesma natureza de comprovante
     fiscal da empresa), embora não tenha entrada própria em
     CAPACIDADES_DOCUMENTO (registrado, não escondido — ver riscos no
     relatório da microetapa). [3 tipos: DCTFWeb - Recibo de Entrega,
     DCTFWeb - Declaração, Guia DCTFWeb/DARF]
  D. GENERICO — SEM rota automática comprovada. Evidência legada direta
     e explícita: `PROCESSADORES_DOCUMENTO['Guia'] =
     _processar_documento_sem_automacao` (idem 'Boleto', 'Nota Fiscal')
     — o próprio dispatch table do legado trata esses três exatamente
     como "sem automação", nunca como broadcast/competência. Corrigido
     nesta revisão: "Guia" (genérica) estava classificada erradamente
     como COMPETENCIA_GLOBAL numa versão anterior deste módulo; a
     evidência de `PROCESSADORES_DOCUMENTO` prova que não há essa
     semântica comprovada — só "Guia DCTFWeb/DARF" (grupo C acima) tem
     natureza de comprovante fiscal da empresa. [3 tipos: Guia, Boleto,
     Nota Fiscal]
  "Outro" (fallback do classificador) e qualquer colisão AMBIGUA nunca
  recebem escopo específico — sempre DESCONHECIDO.

  Total: 9 + 2 + 3 + 3 = 17.

Nenhum import de app.py. Nenhuma dependência de Flask, Airtable,
Postgres, boto3. Puro: determinístico, sem I/O externo, sem PII.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from magnata_os.documental.extracao_texto import extrair_texto_pdf

from .classificador_documental import (
    EstadoClassificacao,
    ResultadoClassificacaoDocumental,
    classificar_documento,
)


class EscopoDocumental(str, Enum):
    COLABORADOR = "COLABORADOR"
    CLIENTE = "CLIENTE"
    COMPETENCIA_GLOBAL = "COMPETENCIA_GLOBAL"
    GENERICO = "GENERICO"
    DESCONHECIDO = "DESCONHECIDO"


class AcaoRoteamento(str, Enum):
    PROCESSAR_AUTOMATICAMENTE = "PROCESSAR_AUTOMATICAMENTE"
    REVISAR_HUMANO = "REVISAR_HUMANO"


class MotivoRoteamento(str, Enum):
    """Código sanitizado — nunca texto livre nem trecho do documento.
    Distingue explicitamente os 4 caminhos que levam a REVISAR_HUMANO
    (ou o único que leva a PROCESSAR_AUTOMATICAMENTE), sem exigir que
    quem consome a decisão cruze `estado_classificacao` + `acao_recomendada`
    para saber qual é qual."""
    TIPO_RESOLVIDO_COM_PROCESSADOR = "TIPO_RESOLVIDO_COM_PROCESSADOR"
    PROCESSADOR_AINDA_NAO_DISPONIVEL = "PROCESSADOR_AINDA_NAO_DISPONIVEL"
    CLASSIFICACAO_AMBIGUA = "CLASSIFICACAO_AMBIGUA"
    TIPO_NAO_RECONHECIDO = "TIPO_NAO_RECONHECIDO"
    PDF_INVALIDO = "PDF_INVALIDO"


@dataclass(frozen=True)
class DecisaoRoteamentoDocumental:
    """Contrato imutável de decisão de roteamento.

    Campos:
    - tipo_documental: mesmo vocabulário de classificador_documental.py
      (um dos 17 nomes de app.py, ou "Outro").
    - estado_classificacao: estado do classificador canônico, repassado
      sem alteração.
    - escopo_documental: natureza operacional do documento (ver
      EscopoDocumental) — DESCONHECIDO quando a classificação não é
      RESOLVIDA, ou quando o tipo resolvido não tem escopo comprovado.
    - acao_recomendada: PROCESSAR_AUTOMATICAMENTE ou REVISAR_HUMANO.
      Nunca existe um terceiro estado "sem ação" — um tipo reconhecido
      mas sem processador avulso comprovado é, ele mesmo, um motivo de
      revisão humana (mesmo comportamento do legado:
      `_processar_documento_sem_automacao` sempre cria Pendência +
      "Revisão Manual", nunca deixa o item invisível).
    - motivo: código sanitizado (MotivoRoteamento) que explica a ação —
      distingue "resolvido sem processador" de AMBIGUA, NAO_RECONHECIDA
      e PDF_INVALIDO sem exigir inferência de quem consome a decisão.
    - processador_disponivel: True somente se existir, comprovadamente,
      um processador do core compatível com ENTRADA AVULSA para este
      tipo — nunca inferido pela existência de um processador que exige
      outro formato de entrada (ex.: manifesto ZIP).
    - necessita_revisao_humana / prioridade_revisao: mesma semântica do
      classificador canônico.
    - evidencias_sanitizadas: identificadores de regra que casaram —
      repassados de `regras_matching`, nunca texto bruto nem PII.
    - tipos_concorrentes: repassado de `tipos_concorrentes`, mesma
      sanitização.
    """
    tipo_documental: str
    estado_classificacao: EstadoClassificacao
    escopo_documental: EscopoDocumental
    acao_recomendada: AcaoRoteamento
    motivo: MotivoRoteamento
    processador_disponivel: bool
    necessita_revisao_humana: bool
    prioridade_revisao: Optional[str] = None
    evidencias_sanitizadas: Tuple[str, ...] = ()
    tipos_concorrentes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.tipo_documental, str) or not self.tipo_documental.strip():
            raise ValueError("tipo_documental deve ser string não-vazia")
        if not isinstance(self.estado_classificacao, EstadoClassificacao):
            raise ValueError("estado_classificacao deve ser EstadoClassificacao")
        if not isinstance(self.escopo_documental, EscopoDocumental):
            raise ValueError("escopo_documental deve ser EscopoDocumental")
        if not isinstance(self.acao_recomendada, AcaoRoteamento):
            raise ValueError("acao_recomendada deve ser AcaoRoteamento")
        if not isinstance(self.motivo, MotivoRoteamento):
            raise ValueError("motivo deve ser MotivoRoteamento")

        if self.acao_recomendada == AcaoRoteamento.PROCESSAR_AUTOMATICAMENTE:
            if not self.processador_disponivel:
                raise ValueError(
                    "PROCESSAR_AUTOMATICAMENTE exige processador_disponivel=True "
                    "— nunca marcado só porque o tipo foi reconhecido")
            if self.necessita_revisao_humana:
                raise ValueError(
                    "PROCESSAR_AUTOMATICAMENTE é incompatível com necessita_revisao_humana=True")
            if self.motivo != MotivoRoteamento.TIPO_RESOLVIDO_COM_PROCESSADOR:
                raise ValueError(
                    "PROCESSAR_AUTOMATICAMENTE exige motivo=TIPO_RESOLVIDO_COM_PROCESSADOR")

        if self.acao_recomendada == AcaoRoteamento.REVISAR_HUMANO:
            if not self.necessita_revisao_humana:
                raise ValueError("REVISAR_HUMANO exige necessita_revisao_humana=True")
            if self.processador_disponivel:
                raise ValueError(
                    "REVISAR_HUMANO é incompatível com processador_disponivel=True")
            if self.motivo == MotivoRoteamento.TIPO_RESOLVIDO_COM_PROCESSADOR:
                raise ValueError(
                    "REVISAR_HUMANO não pode ter motivo=TIPO_RESOLVIDO_COM_PROCESSADOR")

        # Coerência motivo <-> estado_classificacao — nunca dissociados.
        if self.motivo == MotivoRoteamento.CLASSIFICACAO_AMBIGUA and \
                self.estado_classificacao != EstadoClassificacao.AMBIGUA:
            raise ValueError("motivo=CLASSIFICACAO_AMBIGUA exige estado_classificacao=AMBIGUA")
        if self.motivo == MotivoRoteamento.TIPO_NAO_RECONHECIDO and \
                self.estado_classificacao != EstadoClassificacao.NAO_RECONHECIDA:
            raise ValueError("motivo=TIPO_NAO_RECONHECIDO exige estado_classificacao=NAO_RECONHECIDA")
        if self.motivo == MotivoRoteamento.PDF_INVALIDO and \
                self.estado_classificacao != EstadoClassificacao.INVALIDA:
            raise ValueError("motivo=PDF_INVALIDO exige estado_classificacao=INVALIDA")
        if self.motivo == MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL and \
                self.estado_classificacao != EstadoClassificacao.RESOLVIDA:
            raise ValueError(
                "motivo=PROCESSADOR_AINDA_NAO_DISPONIVEL exige estado_classificacao=RESOLVIDA")

        if self.necessita_revisao_humana and not self.prioridade_revisao:
            raise ValueError(
                "necessita_revisao_humana exige prioridade_revisao (ALTA/MEDIA/BAIXA)")
        if not self.necessita_revisao_humana and self.prioridade_revisao:
            raise ValueError(
                "prioridade_revisao só pode existir quando necessita_revisao_humana=True")


# Escopo operacional confirmado por auditoria (legado app.py + core novo)
# — ver docstring do módulo para a fonte de cada classificação. Fechado
# de propósito: um tipo do classificador que não estiver aqui cai no
# fallback DESCONHECIDO em _traduzir_para_decisao, nunca um escopo
# inventado.
_ESCOPO_POR_TIPO: dict[str, EscopoDocumental] = {
    # A. Individual / colaborador.
    "Holerite": EscopoDocumental.COLABORADOR,
    "Rescisão": EscopoDocumental.COLABORADOR,
    "Folha de Ponto": EscopoDocumental.COLABORADOR,
    "EPI": EscopoDocumental.COLABORADOR,
    "Termo de Prorrogação de Contrato de Experiência": EscopoDocumental.COLABORADOR,
    "Ficha de Registro de Empregado": EscopoDocumental.COLABORADOR,
    "Contrato de Experiência": EscopoDocumental.COLABORADOR,
    "Contrato de Trabalho": EscopoDocumental.COLABORADOR,
    "Férias": EscopoDocumental.COLABORADOR,
    # B. Cliente / posto — fatiamento de PDF mestre multi-cliente no
    # legado, não Documento avulso 1:1 (fora de escopo desta microetapa).
    "Extrato da Folha de Pagamento": EscopoDocumental.CLIENTE,
    "FGTS": EscopoDocumental.CLIENTE,
    # C. Global / broadcast por competência — confirmado por
    # CAPACIDADES_DOCUMENTO (app.py) para os dois primeiros; "Guia
    # DCTFWeb/DARF" acompanha o mesmo grupo documental (ver docstring).
    "DCTFWeb - Recibo de Entrega": EscopoDocumental.COMPETENCIA_GLOBAL,
    "DCTFWeb - Declaração": EscopoDocumental.COMPETENCIA_GLOBAL,
    "Guia DCTFWeb/DARF": EscopoDocumental.COMPETENCIA_GLOBAL,
    # D. Genérico — evidência legada DIRETA: PROCESSADORES_DOCUMENTO
    # (app.py) mapeia estes três para _processar_documento_sem_automacao,
    # nunca para uma rota broadcast/competência.
    "Guia": EscopoDocumental.GENERICO,
    "Boleto": EscopoDocumental.GENERICO,
    "Nota Fiscal": EscopoDocumental.GENERICO,
}

# Tipos com processador do core comprovadamente compatível com ENTRADA
# AVULSA (bytes de 1 PDF, sem manifesto ZIP). VAZIO DE PROPÓSITO nesta
# microetapa — ver docstring do módulo. Adicionar um tipo aqui só depois
# de um adapter de entrada avulsa existir E ser coberto por teste de
# integração; nunca por analogia com um processador que exige outro
# formato de entrada.
_TIPOS_COM_PROCESSADOR_AVULSO_COMPATIVEL: frozenset[str] = frozenset()


def extrair_texto_seguro(conteudo_pdf: bytes) -> Optional[str]:
    """Extrai texto do PDF reaproveitando `extrair_texto_pdf`
    (magnata_os/documental/extracao_texto.py) — mesma extração usada por
    processar_holerite/processar_extrato, nenhuma segunda implementação.
    PDF corrompido ou sem texto extraível (ex.: PDF escaneado sem OCR)
    retorna None — nunca lança, nunca vira string vazia tratada como
    classificável (mesma distinção do legado entre "PDF ilegível" e
    "Documento não reconhecido": app.py, rota /email/webhook, `if not
    texto.strip()`).

    Público (auditoria read-only prévia — bridge de identificação de
    Holerite avulso, branch fix/identificacao-holerite-avulso): permite
    que um chamador que precise do MESMO texto para mais de uma
    finalidade (classificação + identificação de colaborador — ver
    `decidir_roteamento_de_texto` abaixo e `servico_lote.py`) extraia o
    PDF uma única vez, nunca duas."""
    if not conteudo_pdf:
        return None
    try:
        texto = extrair_texto_pdf(conteudo_pdf)
    except Exception:
        return None
    if not texto or not texto.strip():
        return None
    return texto


def _decisao_revisao(
    tipo_documental: str,
    estado: EstadoClassificacao,
    motivo: MotivoRoteamento,
    prioridade: str,
    evidencias: Tuple[str, ...] = (),
    concorrentes: Tuple[str, ...] = (),
) -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental=tipo_documental,
        estado_classificacao=estado,
        escopo_documental=EscopoDocumental.DESCONHECIDO,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=motivo,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao=prioridade,
        evidencias_sanitizadas=evidencias,
        tipos_concorrentes=concorrentes,
    )


def _traduzir_para_decisao(resultado: ResultadoClassificacaoDocumental) -> DecisaoRoteamentoDocumental:
    """Traduz o resultado do classificador canônico numa decisão de
    roteamento. Regras de segurança (nunca decisão silenciosa):
      - AMBIGUA -> REVISAR_HUMANO, motivo=CLASSIFICACAO_AMBIGUA.
      - NAO_RECONHECIDA -> REVISAR_HUMANO, motivo=TIPO_NAO_RECONHECIDO.
      - RESOLVIDA sem processador avulso comprovado -> REVISAR_HUMANO,
        motivo=PROCESSADOR_AINDA_NAO_DISPONIVEL (tipo/escopo continuam
        corretos — não é uma anomalia, é reconhecimento explícito de
        trabalho futuro, mesmo espírito do
        `_processar_documento_sem_automacao` do legado).
      - RESOLVIDA com processador avulso comprovado -> PROCESSAR_AUTOMATICAMENTE
        (nenhum tipo se qualifica hoje).
    """
    if resultado.estado == EstadoClassificacao.AMBIGUA:
        return _decisao_revisao(
            resultado.tipo_documental, resultado.estado,
            MotivoRoteamento.CLASSIFICACAO_AMBIGUA,
            resultado.prioridade_revisao or "ALTA",
            resultado.regras_matching, resultado.tipos_concorrentes,
        )

    if resultado.estado == EstadoClassificacao.NAO_RECONHECIDA:
        return _decisao_revisao(
            "Outro", resultado.estado, MotivoRoteamento.TIPO_NAO_RECONHECIDO, "MEDIA")

    # RESOLVIDA
    escopo = _ESCOPO_POR_TIPO.get(resultado.tipo_documental, EscopoDocumental.DESCONHECIDO)
    tem_processador = resultado.tipo_documental in _TIPOS_COM_PROCESSADOR_AVULSO_COMPATIVEL

    if tem_processador:
        return DecisaoRoteamentoDocumental(
            tipo_documental=resultado.tipo_documental,
            estado_classificacao=resultado.estado,
            escopo_documental=escopo,
            acao_recomendada=AcaoRoteamento.PROCESSAR_AUTOMATICAMENTE,
            motivo=MotivoRoteamento.TIPO_RESOLVIDO_COM_PROCESSADOR,
            processador_disponivel=True,
            necessita_revisao_humana=False,
            prioridade_revisao=None,
            evidencias_sanitizadas=resultado.regras_matching,
            tipos_concorrentes=resultado.tipos_concorrentes,
        )

    # Tipo reconhecido, sem processador avulso comprovado — legado nunca
    # deixa isso invisível: vira revisão humana explícita (Pendência +
    # "Revisão Manual"), preservando tipo/escopo corretos.
    return DecisaoRoteamentoDocumental(
        tipo_documental=resultado.tipo_documental,
        estado_classificacao=resultado.estado,
        escopo_documental=escopo,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao="BAIXA",
        evidencias_sanitizadas=resultado.regras_matching,
        tipos_concorrentes=resultado.tipos_concorrentes,
    )


def decidir_roteamento_de_texto(texto: Optional[str]) -> DecisaoRoteamentoDocumental:
    """Metade B (texto -> decisão) de `decidir_roteamento`, extraída
    como função pública própria (auditoria read-only prévia — bridge de
    identificação de Holerite avulso, branch
    fix/identificacao-holerite-avulso): permite que um chamador que já
    extraiu o texto uma única vez (via `extrair_texto_seguro`, acima —
    ex.: `servico_lote.py`, para reaproveitar o MESMO texto também na
    identificação de colaborador) obtenha a decisão de classificação sem
    extrair o PDF uma segunda vez.

    `texto is None` reproduz EXATAMENTE a mesma decisão de PDF_INVALIDO
    que `decidir_roteamento` já produzia para PDF vazio/ilegível —
    nenhuma mudança de comportamento em relação ao que existia antes
    desta extração.

    Pura e sem efeitos — não processa, não escreve, não envia, não
    persiste nada.
    """
    if texto is None:
        return _decisao_revisao(
            "Outro", EstadoClassificacao.INVALIDA, MotivoRoteamento.PDF_INVALIDO, "ALTA")

    resultado = classificar_documento(texto)
    return _traduzir_para_decisao(resultado)


def decidir_roteamento(conteudo_pdf: bytes) -> DecisaoRoteamentoDocumental:
    """Ponte shadow completa: bytes de PDF avulso -> decisão de
    roteamento. Pura e sem efeitos — não processa, não escreve, não
    envia, não persiste nada.

    Args:
        conteudo_pdf: bytes do PDF, disponíveis só na janela transiente
            de ingestão (ver auditoria — Documento persistido não
            guarda bytes hoje).

    Returns:
        DecisaoRoteamentoDocumental — nunca lança por PDF inválido/
        ilegível (vira REVISAR_HUMANO com estado INVALIDA e
        motivo=PDF_INVALIDO).

    Wrapper compatível (auditoria read-only prévia): extrai o texto via
    `extrair_texto_seguro` e delega a decisão a
    `decidir_roteamento_de_texto` — comportamento externo idêntico ao
    que existia antes desta extração; nenhum chamador precisa mudar.
    """
    texto = extrair_texto_seguro(conteudo_pdf)
    return decidir_roteamento_de_texto(texto)
