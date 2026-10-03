"""Gate fail-closed de duas barreiras independentes para preferir o
Contato Canônico de Colaborador V1 (`documental.alocacao.
contato_colaborador`) sobre o campo `WhatsApp` do Airtable, no fluxo de
Holerite avulso para colaborador (`app.py::_buscar_funcionario_nome_
whatsapp`, chamado por `_gerar_assinatura_core` e pelos fluxos de
reenvio).

Esta é a ÚNICA função autorizada a decidir se essa preferência pode ser
aplicada. Nenhum outro ponto do código deve reimplementar esta lógica --
mesmo desenho de `autorizacao_transporte_real.py`, mas sem a barreira de
veto por dry-run: esta decisão nunca dispara transporte real nem escreve
nada, só troca a FONTE de um número de telefone já resolvido de outra
forma (Airtable) por uma leitura adicional, read-only, do Postgres.

HABILITADO = autorizar_resolucao_contato_canonico is True
             AND ORQUESTRADOR_RESOLUCAO_CONTATO_CANONICO_HOLERITE_AVULSO_AUTORIZADA == "1" (exato)

Barreira 1 (estrutural): `autorizar_resolucao_contato_canonico` é
parâmetro de código, default literal `False` -- nunca lido de variável
de ambiente. Só uma mudança de código, revisada em PR, pode virar
`True`.

Barreira 2 (operacional positiva): a variável de ambiente exige o valor
exato `"1"` -- ausência, vazio, "0", "true", "yes", "01", " 1" ou
qualquer outro valor são tratados como NÃO autorizado. Mesma disciplina
estrita de `autorizacao_transporte_real.NOME_VARIAVEL_AUTORIZACAO_
OPERACIONAL`: esta variável só pode HABILITAR, então quanto mais estreito
o valor aceito, menor o risco de uma configuração ambígua ligar a
preferência por engano.

Sem terceira barreira de veto (diferente de `autorizacao_transporte_
real.py`): não existe aqui um equivalente a `ORQUESTRADOR_DRY_RUN` porque
esta decisão não tem efeito em produção real/transporte -- na pior
hipótese (bug na resolução canônica), o pior resultado possível é usar um
número errado/ausente, mesma classe de risco que já existe hoje com o
campo do Airtable desatualizado. Mitigado, não eliminado, por quem compõe
o resolvedor sempre cair em `None` (nunca levantar) e o chamador em
`app.py` sempre preservar o valor do Airtable como fallback quando a
resolução canônica devolve `None` -- ver diff proposto no pacote de
autorização (`pacote-autorizacao-app-py.md`, item 5)."""
from __future__ import annotations

import os

NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL = (
    'ORQUESTRADOR_RESOLUCAO_CONTATO_CANONICO_HOLERITE_AVULSO_AUTORIZADA'
)
_VALOR_AUTORIZADO_EXATO = '1'


def _autorizacao_operacional_explicita() -> bool:
    """Fail-closed: só o valor exato '1' habilita. Nunca aceita variantes
    (case, espaço, zero-padding) -- mesma disciplina de
    `autorizacao_transporte_real._autorizacao_operacional_explicita`."""
    valor = os.environ.get(NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL)
    return valor == _VALOR_AUTORIZADO_EXATO


def resolucao_contato_canonico_holerite_avulso_habilitada(
    *, autorizar_resolucao_contato_canonico: bool,
) -> bool:
    """Única função que decide se `_buscar_funcionario_nome_whatsapp`
    (`app.py`) pode preferir o Contato Canônico de Colaborador sobre o
    campo `WhatsApp` do Airtable.

    `autorizar_resolucao_contato_canonico` é sempre um argumento
    explícito do chamador (nunca lido de ambiente aqui) -- é a barreira
    estrutural."""
    if autorizar_resolucao_contato_canonico is not True:
        return False
    if not _autorizacao_operacional_explicita():
        return False
    return True
