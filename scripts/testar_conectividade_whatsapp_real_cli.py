"""CLI one-shot de teste de conectividade do transporte WhatsApp real
(Evolution) -- missão "TESTE DE CONECTIVIDADE WHATSAPP REAL V1".

Envia EXATAMENTE 1 mensagem de texto para 1 número, só para confirmar
que o canal físico funciona (credencial certa, número certo, mensagem
chega). Nenhum documento, nenhuma assinatura, nenhum `event_id`/
`preview_id`, nenhum outro destinatário -- deliberadamente mais simples
que `executar_canario_v1.py` (que opera sobre um par de pipeline de
eventos real), porque este script não tem nenhum evento/ação por trás.

NUNCA referenciado por cron/scheduler/`render.yaml` -- só é invocável
manualmente, por um humano, na linha de comando. NUNCA importa
`app.py`. NUNCA altera `autorizacao_transporte_real.py` -- só consome
`transporte_real_habilitado`, exatamente como já é consumida em
`ciclo_producao_v1.compor_porta_execucao`.

Mantém as MESMAS 3 barreiras do canário nominal (`executar_canario_v1.
AUTORIZACAO_ESTRUTURAL_CANARIO_V1`), sem bypass:

  REAL = AUTORIZACAO_ESTRUTURAL_TESTE_CONECTIVIDADE_V1 is True
         AND ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO == "1" (exato)
         AND NOT ORQUESTRADOR_DRY_RUN (veto)

Barreira 1 (estrutural, própria deste script, literal no código,
revisável só via PR) nunca é lida de variável de ambiente. Barreiras 2
e 3 continuam decididas exclusivamente dentro de
`transporte_real_habilitado` (`autorizacao_transporte_real.py`,
INTOCADO) -- este script nunca reimplementa essa lógica.

Uso (depois que um humano exportar `ORQUESTRADOR_TRANSPORTE_REAL_
AUTORIZADO=1` manualmente -- nunca a partir deste script):

    python -m scripts.testar_conectividade_whatsapp_real_cli \\
        --numero +5511999998888

    python -m scripts.testar_conectividade_whatsapp_real_cli \\
        --numero +5511999998888 \\
        --texto "Teste de conectividade Magnata OS — ignore esta mensagem"

Validação de número: fail-closed. Formato claramente inválido (poucos
dígitos, caracteres não numéricos além de um `+` opcional no início)
recusa ANTES de qualquer composição de transporte ou tentativa de
rede -- nunca "tenta mesmo assim".

Log/saída: o número completo NUNCA aparece em texto puro -- só
mascarado (mostra só os 2 últimos dígitos, mesmo princípio de
`app.py:_mascarar_cpf`). A confirmação de sucesso mostra o ID externo
retornado pela Evolution (evidência), nunca o número.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from typing import Optional

from magnata_os.orquestrador.autorizacao_transporte_real import (
    transporte_real_habilitado,
)
from magnata_os.orquestrador.composicao_transporte_evolution_legado import (
    compor_transporte_evolution_real,
)

_logger = logging.getLogger(__name__)

TEXTO_PADRAO = 'Teste de conectividade Magnata OS — ignore esta mensagem'

# Barreira 1 (estrutural) DESTE script -- literal, código revisado em
# PR, nunca lida de ambiente. Mesmo padrão de
# `executar_canario_v1.AUTORIZACAO_ESTRUTURAL_CANARIO_V1`: continua
# sujeita integralmente às barreiras 2
# (ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO) e 3 (veto dry-run) dentro
# de `transporte_real_habilitado` -- nunca as substitui.
AUTORIZACAO_ESTRUTURAL_TESTE_CONECTIVIDADE_V1 = True

# Formato plausível de telefone com DDI: `+` opcional seguido de 8 a 15
# dígitos (E.164 permite até 15 dígitos no total, excluindo o `+`).
# Fail-closed: qualquer outro caractere (espaço, letra, parênteses,
# hífen) recusa -- nunca normaliza ou "tenta adivinhar" o formato.
_PADRAO_NUMERO_PLAUSIVEL = re.compile(r'^\+?\d{8,15}$')


class NumeroInvalidoError(ValueError):
    """Formato de número claramente inválido -- fail-closed, nunca
    tenta enviar "mesmo assim"."""


class TransporteRealNaoHabilitadoError(RuntimeError):
    """`transporte_real_habilitado` retornou False -- barreira 2
    ausente ou barreira 3 (dry-run) vetando. Nunca uma tentativa de
    composição ou envio acontece depois desta exceção."""


def validar_numero(numero: str) -> str:
    """Valida o formato de `numero` -- fail-closed. Levanta
    `NumeroInvalidoError` para qualquer formato claramente inválido,
    nunca tenta normalizar ou adivinhar."""
    if not numero or not _PADRAO_NUMERO_PLAUSIVEL.match(numero):
        raise NumeroInvalidoError(
            f'formato de número inválido (esperado: + opcional e 8 a 15 dígitos): {mascarar_numero(numero)}'
        )
    return numero


def mascarar_numero(numero: Optional[str]) -> str:
    """Blindagem LGPD para log/exibição: nunca imprimir o número
    completo em texto puro. Mantém só os 2 últimos dígitos -- mesmo
    princípio de `app.py:_mascarar_cpf`. Entrada vazia/inválida nunca é
    ecoada como está -- volta um placeholder igualmente seguro."""
    digitos = re.sub(r'\D', '', numero or '')
    if len(digitos) < 2:
        return '*' * max(len(digitos), 4)
    return '*' * (len(digitos) - 2) + digitos[-2:]


def executar_teste_conectividade(
    *,
    numero: str,
    texto: str,
    autorizar_transporte_real: bool = AUTORIZACAO_ESTRUTURAL_TESTE_CONECTIVIDADE_V1,
    compor_transporte=None,
) -> str:
    """Núcleo testável (sem parsing de CLI). Valida o número, checa as
    3 barreiras via `transporte_real_habilitado` e, só se habilitado,
    compõe o transporte real e chama `enviar_texto` exatamente 1 vez.

    `compor_transporte` é injetável só para teste (nunca chamada
    HTTP real em teste) -- em produção é sempre
    `compor_transporte_evolution_real`, a mesma composição canônica já
    usada pelo canário nominal.

    Retorna o identificador externo (evidência) da Evolution.
    """
    numero_validado = validar_numero(numero)

    if compor_transporte is None:
        # Lookup pelo nome do módulo (não um default vinculado em
        # tempo de definição) -- permite que testes substituam
        # `compor_transporte_evolution_real` via patch.object(módulo,
        # ...) sem precisar passar `compor_transporte` explicitamente.
        compor_transporte = compor_transporte_evolution_real

    if not transporte_real_habilitado(autorizar_transporte_real=autorizar_transporte_real):
        raise TransporteRealNaoHabilitadoError(
            'transporte real não habilitado -- falta '
            'ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO="1" e/ou ORQUESTRADOR_DRY_RUN '
            'está vetando. Nenhuma tentativa de composição/envio foi feita.'
        )

    transporte = compor_transporte()
    resposta = transporte.enviar_texto(numero=numero_validado, texto=texto)

    identificador = None
    if isinstance(resposta, dict):
        chave = resposta.get('key')
        if isinstance(chave, dict):
            identificador = chave.get('id')
        if not identificador:
            identificador = resposta.get('id')

    _logger.info(
        '[TESTE_CONECTIVIDADE_WHATSAPP] enviado numero=%s id_externo=%s',
        mascarar_numero(numero_validado), identificador,
    )
    return str(identificador) if identificador else ''


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description=(
            'Envia EXATAMENTE 1 mensagem de texto real via WhatsApp (Evolution) '
            'para 1 número, só para testar conectividade do transporte real. '
            'Nunca aceita lista de números, nunca itera.'
        ),
    )
    parser.add_argument('--numero', required=True, help='número de destino, com DDI (ex.: +5511999998888)')
    parser.add_argument('--texto', default=TEXTO_PADRAO, help='texto da mensagem (default: mensagem de teste padrão)')
    args = parser.parse_args(argv)

    try:
        identificador = executar_teste_conectividade(numero=args.numero, texto=args.texto)
    except NumeroInvalidoError as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        return 1
    except TransporteRealNaoHabilitadoError as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        return 1

    print('Mensagem de teste de conectividade enviada.')
    print(f'id_externo={identificador or "(ausente na resposta)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
