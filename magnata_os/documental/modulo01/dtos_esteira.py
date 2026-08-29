"""
DTOs de saida da esteira operacional (Modulo 01, Fase 3).

Camada de apresentacao/consulta, deliberadamente separada das entidades
de dominio (dominio_esteira.py): quem consome estes DTOs (relatorios,
futura API, futura interface web) nunca depende diretamente da forma
interna de LoteDocumental/EstadoEsteiraDocumento -- se o dominio evoluir
internamente, o contrato externo so muda quando as funcoes de conversao
aqui mudarem, de proposito.

Nenhuma funcao aqui faz I/O -- so transforma dados ja carregados.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Mapping, Optional, Tuple

from magnata_os.classificacao.roteamento_documental import DecisaoRoteamentoDocumental

from .dominio import Documento
from .dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    MotivoBloqueio,
    ProximaAcao,
    SituacaoEsteira,
    TipoProximaAcao,
)


@dataclasses.dataclass(frozen=True)
class MotivoBloqueioDTO:
    codigo: str
    descricao: str
    detalhe_tecnico: Optional[str]
    resolvivel_automaticamente: bool


@dataclasses.dataclass(frozen=True)
class ProximaAcaoDTO:
    acao: str
    tipo: TipoProximaAcao
    prazo: Optional[datetime]
    responsavel: Optional[str]


@dataclasses.dataclass(frozen=True)
class ItemEsteiraDocumento:
    """Resposta completa a "onde este documento esta, como esta, por
    que parou, qual a proxima acao, ha quanto tempo" -- o principio
    obrigatorio desta fase (ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md).

    `rastreado_pela_esteira=False` e a resposta explicita para
    documentos legados (sem EstadoEsteiraDocumento, tipicamente criados
    antes da Fase 3) -- os campos de esteira ficam None em vez de
    inventar um estado que nunca existiu de verdade."""

    documento_id: str
    lote_id: Optional[str]
    rastreado_pela_esteira: bool
    etapa_atual: Optional[EtapaEsteira]
    situacao: Optional[SituacaoEsteira]
    motivo_bloqueio: Optional[MotivoBloqueioDTO]
    proxima_acao: Optional[ProximaAcaoDTO]
    entrou_na_etapa_em: Optional[datetime]
    tempo_na_etapa_segundos: Optional[float]
    atualizado_em: Optional[datetime]


@dataclasses.dataclass(frozen=True)
class RoteamentoShadowDTO:
    """Resultado OBSERVÁVEL (não persistido) do roteamento documental
    shadow (magnata_os/classificacao/roteamento_documental.py) para UM
    item de lote. Contrato de apresentação/consulta, mesma disciplina
    de separação já usada neste arquivo para EstadoEsteiraDocumento —
    quem consome `ItemResumoLote.roteamento_shadow` nunca depende
    diretamente da forma interna de `DecisaoRoteamentoDocumental`; se
    esse contrato evoluir, só a função de conversão (`roteamento_shadow_
    para_dto`, abaixo) muda.

    `executado=False` é reservado para uma evolução futura em que o
    roteamento shadow simplesmente não foi tentado neste ponto — NUNCA
    confundir com `executado=True, sucesso=False`, que significa
    "tentou, mas `decidir_roteamento()` levantou um erro técnico
    inesperado" (ver `roteamento_shadow_erro_tecnico`). Quando
    `executado=False`, os demais campos de classificação ficam vazios/
    None e `motivo` continua obrigatório (código sanitizado do porquê
    não foi executado).

    NUNCA carrega texto bruto do PDF, CPF, CNPJ, nome de colaborador,
    assunto/remetente de e-mail ou qualquer payload — só os campos de
    classificação sanitizados já produzidos por `DecisaoRoteamentoDocumental`
    mais a proveniência técnica mínima (documento_id, hash_sha256,
    origem_message_id) para correlação.
    """

    executado: bool
    sucesso: bool
    tipo_documental: Optional[str]
    estado_classificacao: Optional[str]
    escopo_documental: Optional[str]
    acao_recomendada: Optional[str]
    motivo: str
    necessita_revisao_humana: bool
    prioridade_revisao: Optional[str]
    tipos_concorrentes: Tuple[str, ...]
    documento_id: str
    hash_sha256: str
    origem_message_id: Optional[str]

    def __post_init__(self) -> None:
        if not self.executado:
            if self.sucesso:
                raise ValueError("executado=False exige sucesso=False")
            campos_detalhe = (
                self.tipo_documental, self.estado_classificacao,
                self.escopo_documental, self.acao_recomendada,
            )
            if any(campo is not None for campo in campos_detalhe):
                raise ValueError(
                    "executado=False não pode carregar campos de classificação preenchidos")


@dataclasses.dataclass(frozen=True)
class ItemResumoLote:
    """Resultado do processamento de UM arquivo dentro de um lote.

    `roteamento_shadow` é `None` quando o Documento nunca chegou a
    existir (falha na própria ingestão — ver `ServicoCriacaoLote.
    _processar_um_arquivo`) ou quando a criação/avanço do estado inicial
    da esteira falhou antes do ponto de integração do shadow. Quando o
    Documento existe (sucesso OU duplicado), `roteamento_shadow` é
    sempre preenchido — ver `_processar_um_arquivo` para o ponto exato."""

    nome_original: str
    documento_id: Optional[str]
    sucesso: bool
    duplicado: bool
    erro: Optional[str]
    roteamento_shadow: Optional[RoteamentoShadowDTO] = None


@dataclasses.dataclass(frozen=True)
class ResumoLote:
    lote_id: str
    origem: str
    correlation_id: str
    quantidade_arquivos: int
    quantidade_sucesso: int
    quantidade_duplicados: int
    quantidade_erro: int
    situacao: SituacaoEsteira
    criado_em: datetime
    itens: Tuple[ItemResumoLote, ...]


@dataclasses.dataclass(frozen=True)
class ResumoEsteira:
    """Visao agregada da esteira inteira -- para paineis/relatorios."""

    total_documentos_rastreados: int
    por_etapa: Mapping[EtapaEsteira, int]
    por_situacao: Mapping[SituacaoEsteira, int]
    total_bloqueados: int
    total_com_acao_humana_pendente: int


def motivo_bloqueio_para_dto(motivo: Optional[MotivoBloqueio]) -> Optional[MotivoBloqueioDTO]:
    if motivo is None:
        return None
    return MotivoBloqueioDTO(
        codigo=motivo.codigo,
        descricao=motivo.descricao,
        detalhe_tecnico=motivo.detalhe_tecnico,
        resolvivel_automaticamente=motivo.resolvivel_automaticamente,
    )


def proxima_acao_para_dto(proxima_acao: Optional[ProximaAcao]) -> Optional[ProximaAcaoDTO]:
    if proxima_acao is None:
        return None
    return ProximaAcaoDTO(
        acao=proxima_acao.acao,
        tipo=proxima_acao.tipo,
        prazo=proxima_acao.prazo,
        responsavel=proxima_acao.responsavel,
    )


# Código sanitizado fixo — nunca a mensagem real da exceção (poderia
# conter fragmento de texto do PDF ou outro dado sensível). Usado só por
# `roteamento_shadow_erro_tecnico` abaixo.
MOTIVO_ERRO_TECNICO_SHADOW = 'ERRO_TECNICO_SHADOW'


def roteamento_shadow_para_dto(
    decisao: DecisaoRoteamentoDocumental,
    documento_id: str,
    hash_sha256: str,
    origem_message_id: Optional[str],
) -> RoteamentoShadowDTO:
    """Converte uma `DecisaoRoteamentoDocumental` (classificacao/
    roteamento_documental.py) no DTO shadow observável. Repassa só
    campos já sanitizados pela decisão de origem — nunca adiciona texto
    bruto, CPF, CNPJ ou qualquer PII nova; a proveniência (documento_id/
    hash_sha256/origem_message_id) vem de fora, do chamador que já tem
    o Documento em mãos (nunca extraída de novo do conteúdo do PDF)."""
    return RoteamentoShadowDTO(
        executado=True,
        sucesso=True,
        tipo_documental=decisao.tipo_documental,
        estado_classificacao=decisao.estado_classificacao.value,
        escopo_documental=decisao.escopo_documental.value,
        acao_recomendada=decisao.acao_recomendada.value,
        motivo=decisao.motivo.value,
        necessita_revisao_humana=decisao.necessita_revisao_humana,
        prioridade_revisao=decisao.prioridade_revisao,
        tipos_concorrentes=decisao.tipos_concorrentes,
        documento_id=documento_id,
        hash_sha256=hash_sha256,
        origem_message_id=origem_message_id,
    )


def roteamento_shadow_erro_tecnico(
    documento_id: str,
    hash_sha256: str,
    origem_message_id: Optional[str],
) -> RoteamentoShadowDTO:
    """DTO para quando `decidir_roteamento()` levanta uma exceção
    inesperada (falha SECUNDÁRIA — nunca desfaz o Documento já
    persistido nem aborta o lote; ver `ServicoCriacaoLote.
    _processar_um_arquivo`). NUNCA expõe `str(exc)` — só o código
    sanitizado fixo `MOTIVO_ERRO_TECNICO_SHADOW`, para que uma mensagem
    de exceção que por acaso contenha fragmento do PDF nunca vaze para
    este DTO observável."""
    return RoteamentoShadowDTO(
        executado=True,
        sucesso=False,
        tipo_documental=None,
        estado_classificacao=None,
        escopo_documental=None,
        acao_recomendada=None,
        motivo=MOTIVO_ERRO_TECNICO_SHADOW,
        necessita_revisao_humana=True,
        prioridade_revisao='ALTA',
        tipos_concorrentes=(),
        documento_id=documento_id,
        hash_sha256=hash_sha256,
        origem_message_id=origem_message_id,
    )


def montar_item_esteira(
    documento: Documento,
    estado: Optional[EstadoEsteiraDocumento],
    agora: datetime,
) -> ItemEsteiraDocumento:
    """
    Constroi a resposta completa de rastreamento para um documento.
    `estado is None` e o caso de compatibilidade com documento legado
    (ver dominio_esteira.py, docstring de EstadoEsteiraDocumento) --
    nunca levanta excecao, sempre responde algo, com
    rastreado_pela_esteira=False deixando isso explicito para quem
    consome o DTO.
    """
    if estado is None:
        return ItemEsteiraDocumento(
            documento_id=documento.documento_id,
            lote_id=documento.lote_id,
            rastreado_pela_esteira=False,
            etapa_atual=None,
            situacao=None,
            motivo_bloqueio=None,
            proxima_acao=None,
            entrou_na_etapa_em=None,
            tempo_na_etapa_segundos=None,
            atualizado_em=None,
        )

    tempo_na_etapa_segundos = (agora - estado.entrou_na_etapa_em).total_seconds()
    return ItemEsteiraDocumento(
        documento_id=estado.documento_id,
        lote_id=estado.lote_id,
        rastreado_pela_esteira=True,
        etapa_atual=estado.etapa_atual,
        situacao=estado.situacao,
        motivo_bloqueio=motivo_bloqueio_para_dto(estado.motivo_bloqueio),
        proxima_acao=proxima_acao_para_dto(estado.proxima_acao),
        entrou_na_etapa_em=estado.entrou_na_etapa_em,
        tempo_na_etapa_segundos=tempo_na_etapa_segundos,
        atualizado_em=estado.atualizado_em,
    )
