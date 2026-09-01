"""Handlers da Confirmação de Alocação -- framework-agnóstico (missão
"ENTRADA OPERACIONAL + POSTGRES PRÓPRIO V1", FASE 6). Nenhum import de
`flask` neste arquivo nem em nenhum outro deste subpacote.

Este é o "menor ponto de entrada humano real" da missão, no sentido em
que qualquer front-end/adapter web futuro chama exatamente estas 2
funções -- nunca `confirmacao.py`/`preview_confirmacao.py` diretamente,
para que a checagem de perfil (`exigir_perfil`) nunca possa ser
esquecida por acidente num novo ponto de entrada.

**Por que não existe ainda um Blueprint Flask/rota HTTP real:** este
projeto não tem, hoje, nenhum mecanismo de autenticação administrativa
(auditado nesta missão -- ver `../autorizacao.py`). Registrar uma rota
HTTP que altera histórico canônico sem uma autenticação real por trás
seria pior do que não ter rota nenhuma -- qualquer chamador poderia se
autodeclarar `Sujeito(perfil=Perfil.GESTOR)`. Por isso esta missão para
exatamente aqui: a camada de autorização e os handlers estão prontos e
testados, mas a construção real de `Sujeito` (a partir de uma sessão/
token validado de verdade) e o registro da rota em `app.py` ficam como
GATE explícito (ver ADR desta missão) -- mesmo padrão já em vigor para
`modulo01/api/handlers.py`, que também nunca foi wireado a uma rota
real."""
from __future__ import annotations

from ..autorizacao import Perfil, Sujeito, exigir_perfil
from ..confirmacao import SolicitacaoConfirmacaoAlocacao, aplicar_confirmacao_alocacao
from ..preview_confirmacao import PreviewConfirmacaoAlocacao, montar_preview

# Pré-visualização é leitura -- nunca altera histórico canônico --
# então aceita um perfil operacional além do gestor. Confirmar é
# escrita real -- só GESTOR (regra da missão: "a Confirmação de
# Alocação altera histórico canônico... auditar como restringir a
# operação a usuário administrativo").
PERMISSAO_PRE_VISUALIZAR = frozenset({Perfil.GESTOR, Perfil.OPERACIONAL})
PERMISSAO_CONFIRMAR = frozenset({Perfil.GESTOR})


def pre_visualizar_confirmacao(
    sujeito: Sujeito, repo, snapshot_airtable, solicitacao: SolicitacaoConfirmacaoAlocacao,
) -> PreviewConfirmacaoAlocacao:
    """Nunca escreve nada -- `exigir_perfil` primeiro, sempre, mesmo
    para uma operação só de leitura (nenhuma exceção implícita)."""
    exigir_perfil(sujeito, PERMISSAO_PRE_VISUALIZAR)
    return montar_preview(repo, snapshot_airtable, solicitacao)


def confirmar_alocacao(
    sujeito: Sujeito, repo, resolver, solicitacao: SolicitacaoConfirmacaoAlocacao,
) -> str:
    """Única porta de escrita real desta API -- `exigir_perfil` roda
    ANTES de qualquer leitura/escrita em `repo`/`resolver` (nunca depois
    de já ter tocado o banco)."""
    exigir_perfil(sujeito, PERMISSAO_CONFIRMAR)
    return aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
