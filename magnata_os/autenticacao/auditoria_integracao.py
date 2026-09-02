"""Integração genérica da trilha de auditoria com QUALQUER operação de
domínio já existente -- missão "AUTENTICAÇÃO ADMINISTRATIVA
COMPARTILHADA V1", FASE 6/7 ("aproveitar a identidade autenticada para
resolver o segundo gate do PR #117").

**Composição, nunca modificação.** `magnata_os/documental/alocacao/
api/handlers.py::confirmar_alocacao` continua com a MESMA assinatura de
sempre -- nenhum parâmetro novo, nenhum teste existente quebra.
`executar_com_auditoria` é um wrapper genérico (não sabe nada de
alocação); `confirmar_alocacao_com_auditoria` é a composição específica
que fecha o loop pedido: identidade autenticada -> operação de domínio
-> trilha "quem fez"."""
from __future__ import annotations

from typing import Callable, Optional, TypeVar

from .eventos import RESULTADO_ERRO, RESULTADO_SUCESSO, OperacaoAuditada, registrar_operacao
from .identidade import Sujeito

_T = TypeVar('_T')


def executar_com_auditoria(
    repo_auditoria,
    sujeito: Sujeito,
    operacao: str,
    chamada: Callable[[], _T],
    *,
    referencia_agregado_de_erro: Optional[str] = None,
) -> _T:
    """Executa `chamada()` (fechada sobre seus próprios argumentos --
    `lambda: confirmar_alocacao(sujeito, repo, resolver, solicitacao)`,
    por exemplo) e SEMPRE grava exatamente 1 linha de auditoria, sucesso
    ou erro, antes de devolver/repropagar. Nunca engole a exceção
    original -- só observa (a auditoria em si nunca deve ser a razão de
    uma operação de negócio falhar de um jeito diferente do que já
    falharia sem ela; se `registrar_operacao` falhar, essa falha
    propaga por cima, nunca mascarada -- CLAUDE.md raiz §4, "falha
    nunca é silenciosa")."""
    try:
        resultado = chamada()
    except Exception as exc:
        registrar_operacao(repo_auditoria, OperacaoAuditada(
            sujeito=sujeito, operacao=operacao, resultado=RESULTADO_ERRO,
            referencia_agregado=referencia_agregado_de_erro, erro_codigo=type(exc).__name__,
        ))
        raise
    registrar_operacao(repo_auditoria, OperacaoAuditada(
        sujeito=sujeito, operacao=operacao, resultado=RESULTADO_SUCESSO,
        referencia_agregado=resultado if isinstance(resultado, str) else None,
    ))
    return resultado


def confirmar_alocacao_com_auditoria(sujeito: Sujeito, repo, resolver, solicitacao, repo_auditoria) -> str:
    """Composição concreta para `documental/alocacao/api/handlers.py::
    confirmar_alocacao` -- import local (nunca no topo do arquivo) para
    que este pacote (`autenticacao/`, infraestrutura compartilhada)
    nunca dependa de `documental/alocacao` na direção errada quando
    `confirmar_alocacao_com_auditoria` não é usada."""
    from magnata_os.documental.alocacao.api.handlers import confirmar_alocacao

    return executar_com_auditoria(
        repo_auditoria, sujeito, 'confirmar_alocacao', lambda: confirmar_alocacao(sujeito, repo, resolver, solicitacao),
        referencia_agregado_de_erro=solicitacao.colaborador_id,
    )
