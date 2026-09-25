"""Autorização humana REAL (nunca sintética) de um preview do Grande
Orquestrador -- Etapa Pré-Canário Seguro da V1 WhatsApp.

Função IRMÃ de `wiring_assinatura_comunicacao_shadow.autorizar_preview_
assinatura_shadow` -- nunca uma extração parametrizada dela. As duas
compartilham o MESMO contrato de saída (`RegistroAutorizacaoGate`,
`autorizacao_gate.py`, intocado) e o mesmo padrão de idempotência
(`registrar_se_novo`), mas nunca a mesma função: a shadow é sempre
chamada por composição automática (nenhuma decisão humana real por
trás dela); esta função só pode ser chamada com um `Sujeito`
autenticado de verdade (`magnata_os.autenticacao`), nunca com uma
string de `ator_referencia` arbitrária. Mantê-las como funções
distintas (em vez de uma só com um parâmetro `real: bool`) evita que um
erro de configuração transforme uma autorização sintética em produção
por engano -- a diferença fica no NOME da função chamada, nunca num
argumento que pode ser esquecido/invertido.

Nunca decide autonomia/perfil/domínio -- é capacidade genérica do
Orquestrador, nunca específica de WhatsApp ou de Prestação (qualquer
domínio/canal futuro pode reutilizá-la sem modificação)."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import FrozenSet

from magnata_os.autenticacao.identidade import Perfil, Sujeito, exigir_perfil

from .autorizacao_gate import DecisaoGate, RegistroAutorizacaoGate, RepositorioAutorizacoesGate
from .politica_comunicacao import PreviewComunicacao

PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1 = 'autorizacao_operador_real_v1'
"""Nunca `..._shadow_v1` -- distinguível por consulta direta no
repositório de autorizações, sem depender de nenhum outro sinal."""

PERFIS_AUTORIZACAO_ENVIO_PADRAO: FrozenSet[Perfil] = frozenset({Perfil.GESTOR, Perfil.OPERACIONAL})
"""Perfis mínimos autorizados a liberar um envio real -- `AUDITOR` fica
de fora de propósito (perfil de leitura, nunca de decisão de negócio)."""


class AutorizacaoOperadorRealError(ValueError):
    """Falha ao autorizar preview com identidade humana real -- nunca
    mascarada como sucesso."""


def autorizar_preview_operador_real(
    *,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    preview: PreviewComunicacao,
    event_id: str,
    sujeito: Sujeito,
    instante: datetime,
    perfis_permitidos: FrozenSet[Perfil] = PERFIS_AUTORIZACAO_ENVIO_PADRAO,
) -> RegistroAutorizacaoGate:
    """Registra a autorização REAL do preview exato (append-only,
    idempotente por `autorizacao_id` determinístico) -- mudar texto/
    destinatário/composição depois disso invalida a autorização (hash
    diferente, `preview_id` diferente), exatamente como a shadow.

    Fail-closed em duas frentes que a shadow nunca precisa checar:
    1. `exigir_perfil` -- levanta `PermissaoNegada` se o perfil do
       sujeito não estiver entre os permitidos;
    2. `sujeito.email` ausente -- nunca autoriza com identidade
       anônima/não verificada (um `Sujeito` construído só com `perfil`,
       sem passar pela fronteira real de autenticação, é rejeitado
       aqui, mesmo que o perfil seja válido).

    SEMPRE devolve o registro efetivamente persistido (`buscar`), nunca
    o objeto construído localmente -- achado de Ultrareview adversarial:
    se dois operadores diferentes autorizarem o MESMO `event_id`/
    `preview_id` (corrida real ou nova tentativa após timeout aparente),
    `registrar_se_novo` mantém o PRIMEIRO fato e descarta o segundo sem
    sobrescrever; devolver o objeto local do chamador perdedor faria o
    restante da composição (`criar_registro_acao_plano`, envelope)
    gravar um `ator_referencia`/`autorizacao_id` que nunca corresponde
    ao que está de fato em `autorizacoes_gate` -- corrompendo a trilha
    de auditoria de quem realmente autorizou o envio. Mesmo padrão já
    usado por `autorizacao_gate.registrar_decisao_gate_shadow`."""
    exigir_perfil(sujeito, perfis_permitidos)
    if not sujeito.email:
        raise AutorizacaoOperadorRealError(
            'sujeito.email é obrigatório para autorização real -- '
            'nunca autorizar com identidade anônima/não verificada'
        )
    ator_referencia = sujeito.email

    autorizacao = RegistroAutorizacaoGate(
        autorizacao_id=hashlib.sha256(
            f'{event_id}|{preview.preview_id}|{ator_referencia}'.encode('utf-8')
        ).hexdigest(),
        event_id=event_id,
        preview_id=preview.preview_id,
        decisao=DecisaoGate.AUTORIZADO,
        ator_referencia=ator_referencia,
        registrado_em=instante,
        proveniencia=PROVENIENCIA_AUTORIZACAO_OPERADOR_REAL_V1,
    )
    repositorio_autorizacoes.registrar_se_novo(autorizacao)
    return repositorio_autorizacoes.buscar(event_id, preview.preview_id) or autorizacao
