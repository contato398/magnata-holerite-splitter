"""
Servico de entrada unica do Modulo 01 (Documental).

Ponto de entrada obrigatorio para qualquer documento novo: recebe
arquivo + origem + metadados opcionais, calcula hash, verifica
duplicidade e registra o Documento (RECEBIDO -> REGISTRADO) antes de
qualquer classificacao, OCR ou fatiamento -- que sao fases futuras, fora
de escopo aqui (ver MAGNATA_OS_DOCUMENTAL_MODULO01.md).

Principios aplicados (Manifesto):
  - Erros explicitos: falha nunca retorna nem registra sucesso.
  - Idempotencia: mesmo hash nunca cria um segundo Documento, mesmo sob
    chamadas concorrentes (atomicidade delegada ao repositorio, ver
    repositorio.RepositorioDocumentosEmMemoria.salvar_se_ausente_por_hash).
  - Auditoria: toda transicao de estado gera um EventoHistorico.
  - Consistencia: o Documento NUNCA e removido depois de criado. Se o
    registro do historico falhar, o Documento permanece persistido --
    nunca apagado, nunca "como se nao tivesse acontecido". Um
    EventoHistorico nunca aponta para um documento_id que deixou de
    existir, porque nada remove Documento nesta fase.
      - Falha ao registrar DOCUMENTO_RECEBIDO ou DOCUMENTO_REGISTRADO
        (falha no proprio registro do Documento): o Documento e marcado
        ERRO.
      - Falha ao registrar TENTATIVA_DUPLICADA (falha na AUDITORIA de
        um reenvio de conteudo ja registrado, nao no Documento em si):
        o Documento existente NAO e alterado de forma alguma -- nem
        status, nem atualizado_em, nem nenhum outro campo. Uma falha ao
        auditar uma duplicidade nunca degrada um Documento ja valido.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Optional

from .dominio import (
    Documento,
    EventoHistorico,
    StatusDocumento,
    gerar_correlation_id,
    gerar_documento_id,
    gerar_referencia_arquivo_provisoria,
    hash_valido,
    transicionar_status,
)
from .repositorio import RepositorioDocumentos, RepositorioHistorico


class ArquivoAusente(Exception):
    """Nenhum conteudo de arquivo foi fornecido para registrar entrada."""


class HashInvalido(Exception):
    """Uma string de hash SHA-256 mal formada foi usada numa consulta."""


class FalhaPersistencia(Exception):
    """Falha ao gravar Documento ou EventoHistorico. Nunca mascarada como
    sucesso -- quem chama precisa saber que a operacao nao completou. A
    causa original e sempre preservada via `raise ... from exc`."""


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


class ServicoEntradaDocumental:
    """Orquestra o registro de um documento novo. Nao faz OCR,
    classificacao, fatiamento nem vinculo -- so recebe e registra.

    AVISO (a partir da Fase 3): este e um servico de BAIXO NIVEL,
    mantido por compatibilidade com quem ja o chama diretamente
    (servico_entrada_persistente.py da Fase 2, testes, composicao
    interna de outros servicos). Integracoes NOVAS nao devem chamar
    este servico diretamente -- a porta oficial de entrada operacional
    e ServicoCriacaoLote.criar_lote() (servico_lote.py, Fase 3), que
    garante lote_id e EstadoEsteiraDocumento para todo Documento novo e
    isola falha/duplicidade por arquivo. Chamar este servico direto
    cria um Documento tecnicamente valido, mas sem nenhum
    acompanhamento operacional pela esteira (mesmo tratamento dado a
    documentos legados -- ver "Documentos legados" em
    MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md). Esta classe continua sem
    nenhuma dependencia de lote/esteira de proposito -- e o
    ServicoCriacaoLote que a compoe, nao o contrario."""

    def __init__(
        self,
        repositorio_documentos: RepositorioDocumentos,
        repositorio_historico: RepositorioHistorico,
        gerador_documento_id: Callable[[], str] = gerar_documento_id,
        gerador_referencia_arquivo: Callable[[str], str] = gerar_referencia_arquivo_provisoria,
        relogio: Callable[[], datetime] = _relogio_padrao,
    ) -> None:
        self._documentos = repositorio_documentos
        self._historico = repositorio_historico
        self._gerar_documento_id = gerador_documento_id
        self._gerar_referencia_arquivo = gerador_referencia_arquivo
        self._relogio = relogio

    def registrar_entrada(
        self,
        conteudo: bytes,
        nome_original: str,
        mime_type: str,
        origem: str,
        correlation_id: Optional[str] = None,
        lote_id: Optional[str] = None,
        metadados: Optional[dict] = None,
    ) -> Documento:
        """
        Registra a entrada de um documento novo. Idempotente por hash,
        inclusive sob concorrencia: a criacao (ou descoberta de que ja
        existe) e atomica no repositorio -- nunca cria um segundo
        Documento para o mesmo hash SHA-256, mesmo com chamadas
        simultaneas para o mesmo conteudo.

        Se o registro de QUALQUER evento no historico falhar, o
        Documento correspondente NAO e removido -- fica persistido, e
        um evento FALHA_REGISTRO_HISTORICO e registrado quando
        possivel. Falha em DOCUMENTO_RECEBIDO/DOCUMENTO_REGISTRADO marca
        o Documento como ERRO; falha em TENTATIVA_DUPLICADA (auditoria
        de um reenvio, nao do Documento em si) NUNCA altera o Documento
        existente. A excecao sempre propaga como FalhaPersistencia,
        preservando a causa original.
        """
        if not conteudo:
            raise ArquivoAusente(
                'Arquivo ausente ou vazio -- nao e possivel registrar entrada sem conteudo.'
            )

        correlation_id = correlation_id or gerar_correlation_id()
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        agora = self._relogio()

        def _fabricar_documento_recebido() -> Documento:
            return Documento(
                documento_id=self._gerar_documento_id(),
                arquivo_original=self._gerar_referencia_arquivo(hash_sha256),
                nome_original=nome_original,
                mime_type=mime_type,
                tamanho=len(conteudo),
                hash_sha256=hash_sha256,
                origem=origem,
                recebido_em=agora,
                lote_id=lote_id,
                status=StatusDocumento.RECEBIDO,
                correlation_id=correlation_id,
                criado_em=agora,
                atualizado_em=agora,
            )

        try:
            documento, criado_agora = self._documentos.salvar_se_ausente_por_hash(
                hash_sha256, _fabricar_documento_recebido,
            )
        except Exception as exc:
            raise FalhaPersistencia(
                f'Falha ao registrar documento (hash_sha256={hash_sha256}): {exc}'
            ) from exc

        if not criado_agora:
            try:
                self._historico.registrar(EventoHistorico(
                    documento_id=documento.documento_id,
                    evento='TENTATIVA_DUPLICADA',
                    status_anterior=documento.status,
                    status_novo=documento.status,
                    timestamp=agora,
                    correlation_id=correlation_id,
                    detalhes={
                        'hash_sha256': hash_sha256,
                        'nome_original_tentativa': nome_original,
                        'origem_tentativa': origem,
                        'metadados_tentativa': dict(metadados or {}),
                    },
                ))
            except Exception as exc:
                self._tratar_falha_auditoria_duplicada(documento, exc, correlation_id, agora)
            return documento

        # Documento novo. A partir daqui, qualquer falha de historico NAO
        # remove o Documento -- ele fica persistido, marcado ERRO.
        try:
            self._historico.registrar(EventoHistorico(
                documento_id=documento.documento_id,
                evento='DOCUMENTO_RECEBIDO',
                status_anterior=None,
                status_novo=StatusDocumento.RECEBIDO,
                timestamp=agora,
                correlation_id=correlation_id,
                detalhes={
                    'nome_original': nome_original,
                    'origem': origem,
                    'tamanho': documento.tamanho,
                    'metadados': dict(metadados or {}),
                },
            ))
        except Exception as exc:
            self._tratar_falha_historico(documento, 'DOCUMENTO_RECEBIDO', exc, correlation_id, agora)

        try:
            documento_registrado = transicionar_status(documento, StatusDocumento.REGISTRADO, agora)
            self._documentos.salvar(documento_registrado)
        except Exception as exc:
            raise FalhaPersistencia(
                f'Falha ao transicionar para REGISTRADO (documento_id={documento.documento_id}): {exc}'
            ) from exc

        try:
            self._historico.registrar(EventoHistorico(
                documento_id=documento_registrado.documento_id,
                evento='DOCUMENTO_REGISTRADO',
                status_anterior=StatusDocumento.RECEBIDO,
                status_novo=StatusDocumento.REGISTRADO,
                timestamp=agora,
                correlation_id=correlation_id,
                detalhes={},
            ))
        except Exception as exc:
            self._tratar_falha_historico(documento_registrado, 'DOCUMENTO_REGISTRADO', exc, correlation_id, agora)

        return documento_registrado

    def consultar_por_hash(self, hash_sha256: str) -> Optional[Documento]:
        """Consulta um Documento pelo hash, sem registrar nada. Valida o
        formato do hash antes de consultar -- nunca aceita uma string
        que nao seja SHA-256 valido em silencio."""
        if not hash_valido(hash_sha256):
            raise HashInvalido(f'hash_sha256 invalido: {hash_sha256!r}')
        return self._documentos.buscar_por_hash(hash_sha256.strip().lower())

    def _tratar_falha_historico(
        self, documento_afetado: Documento, evento_que_falhou: str,
        causa: Exception, correlation_id: str, agora: datetime,
    ) -> None:
        """
        Reacao padrao a uma falha em historico.registrar(): o Documento
        NUNCA e removido. Tenta marca-lo como ERRO (persistindo essa
        transicao) e, se possivel, registra um evento
        FALHA_REGISTRO_HISTORICO com a causa original. Sempre levanta
        FalhaPersistencia ao final, preservando a causa original -- este
        metodo nunca retorna normalmente.
        """
        documento_final = documento_afetado
        try:
            documento_em_erro = transicionar_status(documento_afetado, StatusDocumento.ERRO, agora)
            self._documentos.salvar(documento_em_erro)
            documento_final = documento_em_erro
        except Exception:
            # Nao foi possivel marcar ERRO (ex.: transicao invalida a
            # partir do status atual, ou o proprio repositorio de
            # documentos tambem esta falhando). O Documento permanece
            # como estava -- nunca removido, nunca perdido.
            pass

        try:
            self._historico.registrar(EventoHistorico(
                documento_id=documento_final.documento_id,
                evento='FALHA_REGISTRO_HISTORICO',
                status_anterior=documento_afetado.status,
                status_novo=documento_final.status,
                timestamp=agora,
                correlation_id=correlation_id,
                detalhes={
                    'evento_que_falhou': evento_que_falhou,
                    'causa': str(causa),
                },
            ))
        except Exception:
            # "Quando possivel": se o proprio historico esta
            # indisponivel, nao ha como registrar isso nele. Nao mascara
            # nem substitui o erro original -- so nao adiciona uma
            # segunda excecao por cima da primeira.
            pass

        raise FalhaPersistencia(
            f'Falha ao registrar {evento_que_falhou} (documento_id={documento_final.documento_id}): {causa}'
        ) from causa

    def _tratar_falha_auditoria_duplicada(
        self, documento_existente: Documento, causa: Exception,
        correlation_id: str, agora: datetime,
    ) -> None:
        """
        Reacao especifica a uma falha ao registrar TENTATIVA_DUPLICADA
        (falha na AUDITORIA de uma tentativa de reenvio de conteudo ja
        registrado -- nao uma falha no registro do proprio Documento).

        O Documento existente e o unico dado valido e ja confirmado
        desta operacao -- a falha e so em registrar que alguem tentou
        reenviar o mesmo conteudo. Por isso, ao contrario de
        _tratar_falha_historico:
          - o status do Documento existente NUNCA muda (nunca vai para
            ERRO por causa de uma falha de auditoria de duplicidade);
          - nenhum campo do Documento e tocado, incluindo
            atualizado_em -- self._documentos.salvar() nunca e chamado
            aqui.

        Ainda assim tenta registrar FALHA_REGISTRO_HISTORICO (best
        effort, deixando explicito no detalhe que a falha ocorreu numa
        tentativa duplicada) e sempre levanta FalhaPersistencia
        preservando a causa original -- este metodo nunca retorna
        normalmente.
        """
        try:
            self._historico.registrar(EventoHistorico(
                documento_id=documento_existente.documento_id,
                evento='FALHA_REGISTRO_HISTORICO',
                status_anterior=documento_existente.status,
                status_novo=documento_existente.status,
                timestamp=agora,
                correlation_id=correlation_id,
                detalhes={
                    'evento_que_falhou': 'TENTATIVA_DUPLICADA',
                    'contexto': 'falha_auditoria_de_duplicidade',
                    'causa': str(causa),
                },
            ))
        except Exception:
            # "Quando possivel": se o proprio historico esta
            # indisponivel, nao ha como registrar isso nele. Nao mascara
            # nem substitui o erro original.
            pass

        raise FalhaPersistencia(
            f'Falha ao registrar auditoria de tentativa duplicada '
            f'(documento_id={documento_existente.documento_id}): {causa}'
        ) from causa
