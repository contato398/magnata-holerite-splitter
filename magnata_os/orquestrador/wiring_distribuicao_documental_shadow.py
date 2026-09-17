"""Wiring canônico Distribuição Documental Genérica -> Assinatura (opcional)
-> Comunicação WhatsApp, V1 shadow.

Prova a composição ponta a ponta para QUALQUER `Documento` canônico do
Módulo 01 (holerite, folha de ponto, contrato, EPI, NR, rescisão,
comprovante, etc.):

    OrdemDistribuicaoDocumental
        -> resolver Documento(s) canônico(s) + bytes
        -> (se exigir_assinatura) materializar arquivo(s) no legado
           -> obrigação de assinatura (token/link resolvidos com
              idempotência de replay, nunca antes da autorização)
        -> preview EXATO -> autorização -> PlanoDisparo
        -> Envelope Executável -> ação PENDING persistida

sempre parando ANTES de qualquer transporte real (Evolution) ou serviço
real (Airtable/Render) -- mesmo espírito de `wiring_assinatura_comunicacao_
shadow.py`, generalizado para qualquer tipo documental.

Disciplina de agnosticismo (mandatória): este módulo NUNCA testa
`tipo_documento` contra um valor específico (HOLERITE, FOLHA_PONTO,
HOLERITE_FOLHA_PONTO, EPI, NR, contrato, rescisão, ...). `tipo_documento`
é sempre um dado opaco repassado adiante -- quem sabe que o motor legado
só agrupa 2 documentos sob HOLERITE_FOLHA_PONTO é exclusivamente
`adapters/obrigacao_assinatura_legado_http.py` (ver
`TIPO_DOCUMENTO_PACOTE_LEGADO_2` lá). Holerite+Ponto é só um preset de
`preset_id`/`politica_agrupamento`, nunca um `if` neste módulo.

Nunca acopla a `PacotePrestacaoCliente`/Prestação de Contas -- a Ordem
nasce diretamente de quem a construir (CLI, futuro endpoint, futuro
corredor), nunca da fonte de candidatos de Prestação.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime
from typing import Optional, Sequence, Tuple

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.materializador_arquivo import (
    MaterializadorArquivoLegado,
)
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentos

from .autorizacao_gate import RegistroAutorizacaoGate, RepositorioAutorizacoesGate
from .envelope_execucao_autorizada import armazenar_acao_e_envelope_v1
from .obrigacao_assinatura import ObrigacaoAssinatura, PortaObrigacaoAssinatura
from .plano_comunicacao import ConteudoItem, PlanoDisparo, montar_plano_disparo
from .politica_comunicacao import ItemComunicacao, PreviewComunicacao, montar_preview_comunicacao
from .repositorio_acoes_execucao_plano_postgres import (
    RegistroAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
    criar_registro_acao_plano,
)
from .wiring_assinatura_comunicacao_shadow import (
    autorizar_preview_assinatura_shadow,
    gerar_token_reservado_csprng,
)

__all__ = [
    'DistribuicaoDocumentalError',
    'DocumentoAusenteNaOrdem',
    'InconsistenciaOrdemDocumento',
    'PoliticaAgrupamentoNaoSuportada',
    'LinkObrigacaoAssinaturaMalformado',
    'ItemDocumentoOrdem',
    'OrdemDistribuicaoDocumental',
    'ResultadoDistribuicaoDocumentalShadow',
    'derivar_identidade_ordem_distribuicao',
    'materializar_distribuicao_documental_shadow',
]


class DistribuicaoDocumentalError(ValueError):
    """Erro fail-closed da composição de distribuição documental."""


class DocumentoAusenteNaOrdem(DistribuicaoDocumentalError):
    """`RepositorioDocumentos.buscar_por_id` não encontrou o
    `documento_id` declarado na Ordem -- bloqueia a operação inteira,
    nunca ignorado silenciosamente."""


class InconsistenciaOrdemDocumento(DistribuicaoDocumentalError):
    """O `hash_sha256` declarado na Ordem não bate com o `Documento`
    canônico resolvido -- a Ordem nunca é uma segunda fonte de verdade
    sobre o conteúdo, só uma referência a validar contra o Documental."""


class PoliticaAgrupamentoNaoSuportada(DistribuicaoDocumentalError):
    """Combinação (quantidade de documentos, politica_agrupamento,
    exigir_assinatura) fora da tabela de combinações permitidas nesta
    V1 -- fail-closed ANTES de qualquer materialização/obrigação/
    persistência. Nunca aceita silenciosamente uma política
    desconhecida."""


class LinkObrigacaoAssinaturaMalformado(DistribuicaoDocumentalError):
    """`ObrigacaoAssinatura.link` devolvido por `consultar_por_correlacao`
    não termina num token no MESMO formato canônico exigido pelo motor
    legado para `token_reservado` (`_validar_reserva_assinatura` em
    app.py: Base64 URL-safe de 32 bytes, 43 caracteres, sem padding).
    Nunca aceito silenciosamente -- um link vazio, malformado ou de
    domínio/path arbitrário nunca produz uma obrigação recuperada por
    adivinhação; a operação inteira é bloqueada."""


@dataclasses.dataclass(frozen=True)
class ItemDocumentoOrdem:
    """Referência a um documento dentro da Ordem, na posição em que foi
    declarado -- a posição participa da identidade da Ordem (ver
    `_serializar_ordem_canonica`)."""

    documento_id: str
    hash_sha256: str


@dataclasses.dataclass(frozen=True)
class OrdemDistribuicaoDocumental:
    """Contrato explícito e imutável da intenção de distribuição
    documental. Não carrega bytes nem resultado de materialização --
    é o dado completo que determina a identidade determinística da
    Ordem (`event_id`) e governa toda a composição.

    `tipo_documento` é dado/política da Ordem, repassado opaco através
    de toda a composição -- nunca gatilho de `if` no núcleo genérico.
    """

    documentos: Tuple[ItemDocumentoOrdem, ...]
    funcionario_id: str
    destinatario: str
    canal: str
    preset_id: str
    tipo_documento: str
    exigir_assinatura: bool
    exigir_comprovante: bool
    politica_agrupamento: str
    mensagem_texto: str

    def __post_init__(self) -> None:
        if not self.documentos:
            raise DistribuicaoDocumentalError('OrdemDistribuicaoDocumental exige ao menos 1 documento')
        for campo in ('funcionario_id', 'destinatario', 'canal', 'preset_id',
                      'tipo_documento', 'politica_agrupamento'):
            if not isinstance(getattr(self, campo), str) or not getattr(self, campo).strip():
                raise DistribuicaoDocumentalError(f'{campo} deve ser texto não vazio')
        if not isinstance(self.exigir_assinatura, bool) or not isinstance(self.exigir_comprovante, bool):
            raise DistribuicaoDocumentalError('exigir_assinatura e exigir_comprovante devem ser booleanos explícitos')


@dataclasses.dataclass(frozen=True)
class ResultadoDistribuicaoDocumentalShadow:
    """Retorno opaco da composição -- nunca contém dado pessoal em
    claro. `assinatura_link`/`arquivo_record_ids` são `None`/vazio no
    ramo sem assinatura."""

    event_id: str
    autorizacao_id: str
    acao_execucao_id: str
    arquivo_record_ids: Tuple[str, ...]
    documento_ids: Tuple[str, ...]
    funcionario_id: str
    assinatura_link: Optional[str]
    envelope_sha256: str
    acao_persistida: RegistroAcaoExecucaoPlano


# ---------------------------------------------------------------------------
# Identidade determinística da Ordem (nunca timestamp/UUID)
# ---------------------------------------------------------------------------

def _serializar_ordem_canonica(ordem: OrdemDistribuicaoDocumental) -> bytes:
    payload = {
        'documentos': [(d.documento_id, d.hash_sha256) for d in ordem.documentos],
        'funcionario_id': ordem.funcionario_id,
        'destinatario': ordem.destinatario,
        'canal': ordem.canal,
        'preset_id': ordem.preset_id,
        'tipo_documento': ordem.tipo_documento,
        'exigir_assinatura': ordem.exigir_assinatura,
        'exigir_comprovante': ordem.exigir_comprovante,
        'politica_agrupamento': ordem.politica_agrupamento,
        'mensagem_texto': ordem.mensagem_texto,
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def derivar_identidade_ordem_distribuicao(ordem: OrdemDistribuicaoDocumental) -> str:
    """`event_id` determinístico da Ordem inteira -- nunca timestamp/
    UUID. Mesma Ordem lógica (todos os 10 campos idênticos, incluindo
    posição dos documentos) sempre produz o mesmo `event_id`; qualquer
    campo semanticamente diferente produz um `event_id` diferente.

    Deliberadamente NÃO deriva `preview_id`: `preview_id` é
    exclusivamente o produzido por `montar_preview_comunicacao` sobre o
    texto/composição EXATOS apresentados ao humano (link de assinatura
    incluído, quando houver) -- nunca um segundo conceito de
    "preview_id da Ordem"."""
    return 'evt_' + hashlib.sha256(b'event|' + _serializar_ordem_canonica(ordem)).hexdigest()


def _derivar_acao_execucao_id_assinatura(event_id: str) -> str:
    """Identidade ÚNICA da ação de assinatura desta Ordem -- usada tanto
    como `acao_execucao_id` real da ação persistida quanto como
    correlação da obrigação de assinatura. Depende só de `event_id`
    (já é hash completo da Ordem canônica) -- válido apenas porque esta
    composição garante exatamente 1 ação por Ordem quando
    `exigir_assinatura=True`."""
    return hashlib.sha256(f'{event_id}|assinatura_unica'.encode('utf-8')).hexdigest()


_RE_TOKEN_RESERVADO = re.compile(r'^[A-Za-z0-9_-]{43}$')
"""Mesmo formato exigido por `_validar_reserva_assinatura` (app.py) e
produzido por `gerar_token_reservado_csprng` -- reutilizado aqui (nunca
redefinido) para validar o token extraído de `ObrigacaoAssinatura.link`
no replay, fail-closed."""


def _extrair_token_do_link(link: str) -> str:
    """Extrai o token do último segmento de path de `link` (convenção
    já usada pelo motor legado: `{RECIBO_BASE_URL}/assinatura/{token}`)
    e VALIDA seu FORMATO antes de devolvê-lo -- nunca aceita link vazio,
    terminando em `/`, ou sem segmento no formato Base64 URL-safe de 43
    caracteres. Fail-closed quanto a formato: qualquer divergência
    bloqueia a operação inteira em vez de produzir um token errado
    silenciosamente.

    Limite conhecido e aceito nesta correção (não resolvido aqui,
    registrado como risco residual): esta validação verifica só o
    FORMATO do último segmento, não a rota/domínio que o precede -- um
    link de rota arbitrária cujo último segmento aparente ser um token
    válido passaria. Fechar essa lacuna por completo exigiria expor o
    token explicitamente em `ObrigacaoAssinatura`/`PortaObrigacaoAssinatura`
    (o adapter já tem o valor cru antes de montar `link`), em vez de
    inferi-lo por parsing reverso de URL -- mudança de contrato maior,
    fora do escopo desta correção pontual."""
    token = (link or '').rsplit('/', 1)[-1]
    if not _RE_TOKEN_RESERVADO.match(token):
        raise LinkObrigacaoAssinaturaMalformado(
            f'link de obrigação de assinatura não contém token no formato esperado: {link!r}'
        )
    return token


# ---------------------------------------------------------------------------
# Política de agrupamento -- combinações V1 permitidas, genérico por
# quantidade/política, NUNCA por tipo_documento específico.
# ---------------------------------------------------------------------------

_POLITICAS_V1_PERMITIDAS: dict = {
    (1, 'UNITARIO'): 'separado',
    (2, 'AGRUPADO_1_LINK'): 'separado',
}


def _validar_e_mapear_politica_agrupamento(ordem: OrdemDistribuicaoDocumental) -> str:
    """Fail-closed ANTES de qualquer I/O: valida a combinação
    (quantidade de documentos, politica_agrupamento) contra a tabela
    V1, e a restrição adicional de que agrupar sob 1 link só faz
    sentido quando há assinatura. NUNCA referencia um `tipo_documento`
    específico -- qual `tipo_documento` o motor legado de fato sabe
    entregar para N=2 é decisão exclusiva do adapter de compatibilidade
    (`adapters/obrigacao_assinatura_legado_http.py`), nunca deste
    núcleo. Reutiliza `PreferenciaComposicao` já existente -- nenhum
    motor de agrupamento novo."""
    chave = (len(ordem.documentos), ordem.politica_agrupamento)
    if chave not in _POLITICAS_V1_PERMITIDAS:
        raise PoliticaAgrupamentoNaoSuportada(
            f'{len(ordem.documentos)} documento(s) com politica_agrupamento='
            f'{ordem.politica_agrupamento!r} não é uma combinação suportada nesta V1'
        )
    if chave == (2, 'AGRUPADO_1_LINK') and not ordem.exigir_assinatura:
        raise PoliticaAgrupamentoNaoSuportada(
            'AGRUPADO_1_LINK com 2 documentos exige exigir_assinatura=True -- '
            '1 link só faz sentido para o fluxo de assinatura'
        )
    return _POLITICAS_V1_PERMITIDAS[chave]


# ---------------------------------------------------------------------------
# Resolução documental
# ---------------------------------------------------------------------------

def _resolver_documento_da_ordem(
    item: ItemDocumentoOrdem, repositorio_documentos: RepositorioDocumentos,
) -> Documento:
    documento = repositorio_documentos.buscar_por_id(item.documento_id)
    if documento is None:
        raise DocumentoAusenteNaOrdem(f'documento_id não encontrado no repositório canônico: {item.documento_id}')
    if documento.hash_sha256 != item.hash_sha256:
        raise InconsistenciaOrdemDocumento(
            f'hash declarado na Ordem ({item.hash_sha256}) != hash do Documento canônico '
            f'({documento.hash_sha256}) para documento_id={item.documento_id}'
        )
    return documento


def _resolver_documentos_e_bytes(
    ordem: OrdemDistribuicaoDocumental,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
) -> Tuple[Tuple[Documento, bytes], ...]:
    resolvidos = []
    for item in ordem.documentos:
        documento = _resolver_documento_da_ordem(item, repositorio_documentos)
        with armazenamento.abrir_leitura(documento.hash_sha256) as arquivo:
            conteudo_bytes = arquivo.read()
        resolvidos.append((documento, conteudo_bytes))
    return tuple(resolvidos)


# ---------------------------------------------------------------------------
# Composição principal
# ---------------------------------------------------------------------------

def materializar_distribuicao_documental_shadow(
    *,
    ordem: OrdemDistribuicaoDocumental,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
    materializador: Optional[MaterializadorArquivoLegado],
    porta_assinatura: Optional[PortaObrigacaoAssinatura],
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
) -> ResultadoDistribuicaoDocumentalShadow:
    """Composição completa até a persistência da ação PENDING, sem
    transporte: resolve documento(s) -> (se exigir_assinatura)
    materializa no legado e resolve obrigação/link idempotentemente,
    SEMPRE depois da autorização do preview exato -> PlanoDisparo ->
    Envelope -> ação persistida.

    `materializador`/`porta_assinatura` podem ser `None` quando
    `ordem.exigir_assinatura=False` (nenhuma materialização em
    TABLE_ARQUIVOS é necessária para enviar um documento sem exigir
    assinatura -- o mesmo padrão já usado pelas rotas legadas
    `whatsapp_enviar_documento`/`whatsapp_enviar_texto`, que despacham
    mídia sem depender do motor de assinatura)."""
    preferencia = _validar_e_mapear_politica_agrupamento(ordem)  # fail-closed antes de qualquer outra checagem
    if ordem.exigir_assinatura and (materializador is None or porta_assinatura is None):
        raise DistribuicaoDocumentalError(
            'exigir_assinatura=True exige materializador e porta_assinatura não-nulos'
        )

    event_id = derivar_identidade_ordem_distribuicao(ordem)
    documentos_resolvidos = _resolver_documentos_e_bytes(ordem, repositorio_documentos, armazenamento)
    documento_ids = tuple(doc.documento_id for doc, _ in documentos_resolvidos)

    if ordem.exigir_assinatura:
        preview, autorizacao, plano, acao, obrigacao, acao_execucao_id, arquivo_record_ids = (
            _montar_ramo_com_assinatura(
                ordem=ordem, event_id=event_id, preferencia=preferencia,
                documentos_resolvidos=documentos_resolvidos,
                materializador=materializador, porta_assinatura=porta_assinatura,
                repositorio_autorizacoes=repositorio_autorizacoes,
                ator_referencia=ator_referencia, proveniencia=proveniencia, instante=instante,
            )
        )
        assinatura_link = obrigacao.link
    else:
        preview, autorizacao, plano, acao = _montar_ramo_sem_assinatura(
            ordem=ordem, event_id=event_id, preferencia=preferencia,
            documentos_resolvidos=documentos_resolvidos,
            repositorio_autorizacoes=repositorio_autorizacoes,
            ator_referencia=ator_referencia, proveniencia=proveniencia, instante=instante,
        )
        arquivo_record_ids = ()
        assinatura_link = None
        acao_execucao_id = None  # definido abaixo pela fórmula genérica

    registro = criar_registro_acao_plano(
        event_id=event_id, plano=plano, autorizacao=autorizacao, acao=acao, criado_em=instante,
    )
    if acao_execucao_id is not None:
        # Ramo com assinatura: substitui pelo id único derivado da Ordem
        # (ver `_derivar_acao_execucao_id_assinatura`) -- o MESMO id já
        # usado para correlacionar a obrigação, nunca dois ids
        # concorrentes para a mesma ação.
        registro = dataclasses.replace(registro, acao_execucao_id=acao_execucao_id)
    else:
        acao_execucao_id = registro.acao_execucao_id

    envelope_sha256 = armazenar_acao_e_envelope_v1(armazenamento=armazenamento, registro=registro, acao=acao)
    registro_com_envelope = dataclasses.replace(registro, envelope_sha256=envelope_sha256)
    (acao_persistida,) = repositorio_acoes.materializar_registros(
        registros=(registro_com_envelope,), autorizacao=autorizacao,
    )

    return ResultadoDistribuicaoDocumentalShadow(
        event_id=event_id,
        autorizacao_id=autorizacao.autorizacao_id,
        acao_execucao_id=acao_execucao_id,
        arquivo_record_ids=arquivo_record_ids,
        documento_ids=documento_ids,
        funcionario_id=ordem.funcionario_id,
        assinatura_link=assinatura_link,
        envelope_sha256=envelope_sha256,
        acao_persistida=acao_persistida,
    )
    # STOP -- porta_execucao/transporte_real_habilitado nunca importados
    # nem chamados neste módulo.


def _montar_ramo_com_assinatura(
    *,
    ordem: OrdemDistribuicaoDocumental,
    event_id: str,
    preferencia: str,
    documentos_resolvidos: Tuple[Tuple[Documento, bytes], ...],
    materializador: MaterializadorArquivoLegado,
    porta_assinatura: PortaObrigacaoAssinatura,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
):
    """Ordem obrigatória dos efeitos (fail-closed -- nunca cria
    obrigação antes da autorização do preview exato):

    materializar arquivos -> derivar A -> consultar obrigação por A
    (read-only) -> resolver link (recuperado ou token novo só em
    memória) -> montar preview EXATO -> autorizar -> SÓ ENTÃO criar/
    recuperar obrigação sob A -> montar PlanoDisparo.

    Até 2 tentativas: se `criar_ou_recuperar` falhar porque outro
    processo já criou a obrigação sob o mesmo `A` entre a consulta e
    esta chamada (corrida real -- nunca esperada no CLI manual desta
    V1, mas fail-closed mesmo assim), a 2ª tentativa refaz a consulta
    (que agora encontra a obrigação do vencedor), reconstrói o preview/
    autorização com o LINK REAL do vencedor, e nunca assume que o link
    especulativo desta chamada é o correto."""
    arquivo_record_ids = tuple(
        materializador.materializar(
            documento=documento, conteudo_bytes=conteudo_bytes, funcionario_id=ordem.funcionario_id,
        ).arquivo_record_id
        for documento, conteudo_bytes in documentos_resolvidos
    )

    A = _derivar_acao_execucao_id_assinatura(event_id)

    for tentativa in range(2):
        obrigacao_existente = porta_assinatura.consultar_por_correlacao(acao_execucao_id=A)  # READ-ONLY

        if obrigacao_existente is not None:
            token_pendente = None
            link = f'/assinatura/{_extrair_token_do_link(obrigacao_existente.link)}'
        else:
            token_pendente = gerar_token_reservado_csprng()  # CSPRNG, só em memória -- nenhuma escrita ainda
            link = f'/assinatura/{token_pendente}'

        texto_exato = f'{ordem.mensagem_texto.strip()} {link}'.strip()
        preview = montar_preview_comunicacao(
            destinatarios=(ordem.destinatario,), texto=texto_exato, itens=(),
            assinatura=True, comprovante=ordem.exigir_comprovante, preferencia=preferencia,
        )

        autorizacao = autorizar_preview_assinatura_shadow(  # AUTORIZAÇÃO DO PREVIEW EXATO -- sempre antes da obrigação
            repositorio_autorizacoes=repositorio_autorizacoes, preview=preview,
            event_id=event_id, ator_referencia=ator_referencia, proveniencia=proveniencia, instante=instante,
        )

        if obrigacao_existente is not None:
            obrigacao = obrigacao_existente
            break

        try:
            obrigacao = porta_assinatura.criar_ou_recuperar(  # ÚNICA escrita de obrigação, só agora
                token_reservado=token_pendente, acao_execucao_id=A,
                funcionario_id=ordem.funcionario_id, tipo_documento=ordem.tipo_documento,
                arquivo_record_ids=arquivo_record_ids,
            )
            break
        except Exception:
            if tentativa == 1:
                raise
            # Corrida real: outro processo criou a obrigação sob o
            # mesmo A entre a consulta e esta escrita. Refaz do início
            # (nova consulta encontrará o vencedor) -- nunca reaproveita
            # o preview/autorização desta tentativa perdida.
            continue

    plano = montar_plano_disparo(
        preview=preview, texto=texto_exato, conteudos=(),
        preview_id_autorizado=autorizacao.preview_id, autorizacao_explicita=True,
    )
    acao = plano.acoes[0]
    return preview, autorizacao, plano, acao, obrigacao, A, arquivo_record_ids


def _montar_ramo_sem_assinatura(
    *,
    ordem: OrdemDistribuicaoDocumental,
    event_id: str,
    preferencia: str,
    documentos_resolvidos: Tuple[Tuple[Documento, bytes], ...],
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
):
    """Sem obrigação/token/link -- documento(s) despachado(s) como
    mídia comum, mesmo padrão das rotas legadas que já enviam WhatsApp
    sem depender do motor de assinatura. Nesta V1, a tabela de
    políticas (`_POLITICAS_V1_PERMITIDAS`) só admite N=1 sem
    assinatura (N=2/AGRUPADO_1_LINK exige exigir_assinatura=True)."""
    (documento, conteudo_bytes), = documentos_resolvidos
    item_preview = ItemComunicacao(
        tipo='documento', nome=documento.nome_original,
        conteudo_sha256=documento.hash_sha256,
    )
    preview = montar_preview_comunicacao(
        destinatarios=(ordem.destinatario,), texto=ordem.mensagem_texto,
        itens=(item_preview,), assinatura=False, comprovante=ordem.exigir_comprovante,
        preferencia=preferencia,
    )
    autorizacao = autorizar_preview_assinatura_shadow(
        repositorio_autorizacoes=repositorio_autorizacoes, preview=preview,
        event_id=event_id, ator_referencia=ator_referencia, proveniencia=proveniencia, instante=instante,
    )
    conteudo_item = ConteudoItem(tipo='documento', nome=documento.nome_original, conteudo=conteudo_bytes)
    plano = montar_plano_disparo(
        preview=preview, texto=ordem.mensagem_texto, conteudos=(conteudo_item,),
        preview_id_autorizado=autorizacao.preview_id, autorizacao_explicita=True,
    )
    acao = plano.acoes[0]
    return preview, autorizacao, plano, acao
