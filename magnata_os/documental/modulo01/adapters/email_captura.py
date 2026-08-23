"""
Adapter de captura de e-mail (Modulo 01, proposta pos-Fase 4).

Fonte de entrada para o e-mail que hoje chega via Gmail Apps Script e
alimenta `/email/webhook` em `app.py` (legado). Este adapter NAO se
conecta a nenhuma caixa de e-mail real -- fala contra
`FonteMensagensEmail`, uma interface minima que qualquer cliente real
(Gmail API, IMAP) precisa cumprir. Nenhum driver de e-mail e importado
aqui; quem instanciar `AdapterCapturaEmail` em producao passa um cliente
real que implemente `FonteMensagensEmail`; testes passam um duplo de
teste com a mesma interface (ver
test_magnata_os_documental_modulo01_email_captura.py).

Este adapter, quando ligado a uma fonte real, deve rodar EM PARALELO ao
`/email/webhook` legado -- nao o substitui, nao desliga o Gmail Apps
Script, nao toca em `app.py`. Ver
docs/decisoes/plano-consolidacao-ingestao-distribuicao.md.

O que este adapter explicitamente NAO faz: conectar a uma caixa de
e-mail real; OCR; classificacao de tipo documental; vinculo a
colaborador/cliente; envio (e-mail/WhatsApp); qualquer escrita real no
Airtable -- tudo isso continua fora de escopo do Modulo 01 (ver
MAGNATA_OS_DOCUMENTAL_MODULO01.md).

Idempotencia: este adapter NAO deduplica por `message_id`. A
deduplicacao real e por hash de conteudo de cada anexo, ja garantida por
`ServicoEntradaDocumental` (via `ServicoCriacaoLote`) -- reprocessar a
mesma mensagem (ex.: apos reiniciar a fonte, ou por reenvio) nunca cria
um segundo `Documento` para o mesmo anexo; o `ItemResumoLote`
correspondente vem com `duplicado=True`.

Erro por anexo: um anexo invalido (ex.: vazio) vira um `ItemResumoLote`
com `sucesso=False` e `erro` preenchido -- nunca trava os demais anexos
da mesma mensagem nem as demais mensagens da mesma chamada (comportamento
de `ServicoCriacaoLote`, testado em
`test_erro_parcial_um_anexo_falha_outro_da_mesma_mensagem_sucede`).

Erro na propria busca: `buscar_novas_mensagens()` NAO tem retry nem
tratamento de excecao aqui -- uma falha de rede/API na fonte real
propaga sem ser engolida (fail-loud deliberado, nao ausencia de
cuidado). Quem instanciar este adapter com uma fonte real e responsavel
por decidir a politica de retry/backoff do lado de fora (ex.: no
agendador/cron que chama `capturar_novas_mensagens()`) -- ver
`test_falha_na_busca_de_mensagens_propaga_sem_ser_engolida`.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import List, Protocol, Sequence, Tuple

from ..dtos_esteira import ResumoLote
from ..servico_lote import ArquivoEntradaLote, ServicoCriacaoLote

ORIGEM_EMAIL = 'email'


@dataclasses.dataclass(frozen=True)
class AnexoEmailRecebido:
    """Um anexo ja extraido de uma mensagem de e-mail -- bytes em mao,
    sem nenhuma dependencia de biblioteca de e-mail daqui em diante."""

    nome_original: str
    mime_type: str
    conteudo: bytes


@dataclasses.dataclass(frozen=True)
class MensagemEmailRecebida:
    """Uma mensagem de e-mail ja lida por uma fonte real (Gmail API,
    IMAP, etc.), reduzida ao que este adapter precisa. `message_id` e o
    identificador estavel da mensagem na fonte -- usado so para
    metadados/rastreabilidade aqui; a idempotencia de fato e por hash de
    conteudo de cada anexo (ver docstring do modulo), nunca por
    `message_id`."""

    message_id: str
    remetente: str
    assunto: str
    recebido_em: datetime
    anexos: Sequence[AnexoEmailRecebido]


class FonteMensagensEmail(Protocol):
    """Contrato minimo que qualquer cliente real de e-mail (Gmail API,
    IMAP) precisa cumprir para alimentar este adapter. Nenhum driver
    real e importado neste modulo -- quem instanciar
    `AdapterCapturaEmail` em producao passa a implementacao real; testes
    passam um duplo de teste com a mesma interface."""

    def buscar_novas_mensagens(self) -> Sequence[MensagemEmailRecebida]: ...


@dataclasses.dataclass(frozen=True)
class ResumoCapturaEmail:
    """Resultado de uma execucao de captura -- uma por chamada a
    `capturar_novas_mensagens()`, nunca mutado depois de criado."""

    mensagens_processadas: int
    # message_id de cada mensagem sem nenhum anexo -- nunca descartada em
    # silencio, mesmo que nao vire lote nenhum.
    mensagens_sem_anexo: Tuple[str, ...]
    resumos_lote: Tuple[ResumoLote, ...]


class AdapterCapturaEmail:
    """Le mensagens novas de `FonteMensagensEmail` e registra cada uma
    como um lote (`ServicoCriacaoLote.criar_lote`, a porta oficial de
    entrada -- ver aviso em servico_entrada.py), com origem='email'. Uma
    mensagem de e-mail vira um lote; cada anexo da mensagem vira um
    arquivo do lote. Mensagem sem nenhum anexo NUNCA vira um lote vazio
    silencioso -- e contabilizada em `mensagens_sem_anexo` e pulada,
    nunca escondida do resumo."""

    def __init__(
        self,
        fonte_mensagens: FonteMensagensEmail,
        servico_lote: ServicoCriacaoLote,
    ) -> None:
        self._fonte = fonte_mensagens
        self._servico_lote = servico_lote

    def capturar_novas_mensagens(self) -> ResumoCapturaEmail:
        """
        Busca mensagens novas na fonte e registra um lote por mensagem
        com pelo menos um anexo. Uma falha ao criar o lote de UMA
        mensagem nunca e mascarada aqui -- `ServicoCriacaoLote.criar_lote`
        ja garante que cada arquivo é isolado e que o `ResumoLote`
        retornado reflete erro por item, nunca aborta as demais
        mensagens desta chamada.
        """
        mensagens = self._fonte.buscar_novas_mensagens()

        mensagens_sem_anexo: List[str] = []
        resumos_lote: List[ResumoLote] = []

        for mensagem in mensagens:
            if not mensagem.anexos:
                mensagens_sem_anexo.append(mensagem.message_id)
                continue

            arquivos = [
                ArquivoEntradaLote(
                    conteudo=anexo.conteudo,
                    nome_original=anexo.nome_original,
                    mime_type=anexo.mime_type,
                    metadados={
                        'origem_message_id': mensagem.message_id,
                        'origem_remetente': mensagem.remetente,
                    },
                )
                for anexo in mensagem.anexos
            ]

            resumo = self._servico_lote.criar_lote(
                origem=ORIGEM_EMAIL,
                arquivos=arquivos,
                metadados={
                    'message_id': mensagem.message_id,
                    'remetente': mensagem.remetente,
                    'assunto': mensagem.assunto,
                    'recebido_em_origem': mensagem.recebido_em.isoformat(),
                },
            )
            resumos_lote.append(resumo)

        return ResumoCapturaEmail(
            mensagens_processadas=len(mensagens),
            mensagens_sem_anexo=tuple(mensagens_sem_anexo),
            resumos_lote=tuple(resumos_lote),
        )
