"""Adapter concreto de `PortaExecucaoAcao` sobre `PortaTransporteWhatsapp`.

Ponte fina entre o executor persistente (`executor_persistente_fake.py`) e
o transporte já injetado (`TransporteEvolutionLegado` ou qualquer outro
implementador de `PortaTransporteWhatsapp`). Executa exatamente a
`AcaoEnvio` já verificada pelo Envelope -- nunca reconstrói preview,
reotimiza composição, reinterpreta autorização nem altera texto/legenda.

Interpretação MAIS RIGOROSA que o legado direto: uma resposta 2xx sem ID
externo confirmável é tratada aqui como `ENVIO_EXTERNO_INCERTO`, nunca
como sucesso -- diferente do comportamento das rotas `/whatsapp/enviar-*`
existentes, que continuam aceitando 2xx sem ID como sucesso (não
alterado, preservado integralmente). A regra mais rigorosa vale só para
este wiring novo, durável, onde `SUCCEEDED` precisa significar "temos
evidência externa confirmável", nunca "recebemos 2xx".
"""
from __future__ import annotations

import dataclasses
import json

from ..classificador_falha import FalhaEnvioIncerto
from ..executor_persistente_fake import PortaExecucaoAcao, ResultadoExecucaoPorta
from ..plano_comunicacao import AcaoEnvio
from ..transporte_comunicacao import PortaTransporteWhatsapp, TransporteComunicacaoError


def _extrair_id_externo(resposta: object) -> str | None:
    """Mesma extração já usada pelas rotas `/whatsapp/enviar-*` legadas
    (`resultado.get('key', {}).get('id') ou resultado.get('id')`) --
    reaproveitada aqui, não reimplementada com regra diferente."""
    if not isinstance(resposta, dict):
        return None
    identificador = resposta.get('key', {}).get('id') if isinstance(resposta.get('key'), dict) else None
    if not identificador:
        identificador = resposta.get('id')
    return identificador or None


@dataclasses.dataclass(frozen=True)
class ExecutorEvolutionLegado:
    """Implementa `PortaExecucaoAcao` despachando para um
    `PortaTransporteWhatsapp` já configurado (injetado)."""

    transporte: PortaTransporteWhatsapp

    def executar(self, acao: AcaoEnvio) -> ResultadoExecucaoPorta:
        try:
            if acao.tipo == 'texto':
                resposta = self.transporte.enviar_texto(
                    numero=acao.destinatario, texto=acao.texto,
                )
            elif acao.tipo == 'video':
                resposta = self.transporte.enviar_video(
                    numero=acao.destinatario, conteudo=acao.conteudo,
                    nome_arquivo=acao.nome, legenda=acao.legenda,
                )
            elif acao.tipo == 'documento':
                resposta = self.transporte.enviar_documento(
                    numero=acao.destinatario, conteudo=acao.conteudo,
                    nome_arquivo=acao.nome, legenda=acao.legenda,
                )
            else:
                # Protegido pelo preflight de transporte_comunicacao; defesa
                # em profundidade -- nunca reinterpreta um tipo desconhecido.
                raise TransporteComunicacaoError(f'tipo não executável: {acao.tipo}')
        except TransporteComunicacaoError:
            raise
        # As exceções do vocabulário do Orquestrador (FalhaTransitoria,
        # FalhaEnvioIncerto, ValueError de 4xx) já saem classificadas do
        # adapter de transporte -- este método só propaga, nunca reclassifica.

        identificador = _extrair_id_externo(resposta)
        if not identificador:
            # Regra mais rigorosa desta missão (Seção 14): 2xx sem ID
            # externo confirmável nunca vira SUCCEEDED aqui, mesmo que o
            # transporte legado não tenha levantado exceção. Nunca
            # descarta a evidência: o corpo da resposta (sem PII, é
            # metadado de protocolo) vai junto na mensagem da exceção.
            raise FalhaEnvioIncerto(
                'resposta 2xx sem ID externo confirmável: '
                f'{json.dumps(resposta, ensure_ascii=True, default=str)[:500]}'
            )

        return ResultadoExecucaoPorta(
            resultado_referencia=str(identificador),
            evidencia=json.dumps(
                {'id_externo': str(identificador)}, ensure_ascii=True,
            ).encode('utf-8'),
        )
