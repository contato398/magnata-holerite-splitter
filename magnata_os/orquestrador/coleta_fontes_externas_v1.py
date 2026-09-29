"""Coleta de fontes externas ANTES da localização (aquisição multifonte).

Não cria captura nova: cada coletor reutiliza uma entrada que já existe
(e-mail: `AdapterCapturaEmail` do pipeline do Módulo 01, Gmail somente
leitura, idempotente por hash). O que chega vira `Documento` interno e
passa a ser encontrado pela busca por conteúdo -- a localização nunca
depende de a fonte externa estar de pé no momento da busca.

Falha isolada: um coletor que falha (credencial, rede, timeout) é
registrado com o tipo do erro e os demais seguem. Quem consome o
resultado trata a busca como INCOMPLETA: nenhum documento é dado como
AUSENTE e nenhuma Ordem sai (o documento -- ou uma versão corrigida --
pode estar justamente na fonte que falhou).

Ativar a coleta real de e-mail é gate humano (docs/decisoes/
fase1-gmail-readonly-inerte.md, "Fase 2").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ResultadoColeta:
    fonte: str
    status: str  # 'OK' | 'FALHOU'
    documentos_novos: int = 0
    documentos_repetidos: int = 0
    erro_tipo: Optional[str] = None

    def como_dict(self):
        return {
            'fonte': self.fonte, 'status': self.status, 'documentos_novos': self.documentos_novos,
            'documentos_repetidos': self.documentos_repetidos, 'erro_tipo': self.erro_tipo,
        }


def coletar(coletores: Sequence[Tuple[str, Callable[[], object]]]) -> Tuple[ResultadoColeta, ...]:
    resultados = []
    for nome, coletor in coletores:
        try:
            resumo = coletor()
        except Exception as exc:  # isolada e registrada; nunca derruba as demais
            resultados.append(ResultadoColeta(nome, 'FALHOU', erro_tipo=type(exc).__name__))
            continue
        novos, repetidos = _contar(resumo)
        resultados.append(ResultadoColeta(nome, 'OK', novos, repetidos))
    return tuple(resultados)


def _contar(resumo: object) -> Tuple[int, int]:
    """Aceita `ResumoCapturaEmail` (lotes com `quantidade_sucesso`/
    `quantidade_duplicados`); outros coletores devolvem o mesmo formato."""
    lotes = getattr(resumo, 'resumos_lote', ()) or ()
    return (
        sum(getattr(lote, 'quantidade_sucesso', 0) for lote in lotes),
        sum(getattr(lote, 'quantidade_duplicados', 0) for lote in lotes),
    )


def compor_coletor_email(dependencias, fonte_mensagens) -> Callable[[], object]:
    """Pipeline do Módulo 01 já existente, sobre os MESMOS repositórios e
    armazenamento da Prestação (idempotência por hash compartilhada)."""
    from magnata_os.documental.modulo01.composicao import construir_pipeline_modulo01

    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=dependencias.repositorio_documentos,
        repositorio_historico=dependencias.repositorio_historico,
        repositorio_lotes=dependencias.repositorio_lotes,
        repositorio_estados_esteira=dependencias.repositorio_estados_esteira,
        fonte_mensagens=fonte_mensagens,
        armazenamento_arquivos=dependencias.armazenamento,
    )
    return pipeline.adapter_captura_email.capturar_novas_mensagens


def compor_fonte_gmail(label: str, caminho_token: str):
    """Gmail somente leitura (escopo `gmail.readonly`), adapter existente."""
    from magnata_os.documental.modulo01.adapters.email_gmail_readonly import (
        ClienteGmailReadOnly,
        carregar_credenciais_gmail_readonly,
    )

    return ClienteGmailReadOnly(label, carregar_credenciais_gmail_readonly(caminho_token))
