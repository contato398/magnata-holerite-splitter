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
-> trilha "quem fez".

**Gate arquitetural registrado, não mascarado (revisão independente do
PR #118, HEAD `2666320`):** a operação de domínio (`chamada()`) e a
gravação da auditoria são, hoje, 2 escritas em 2 repositórios/conexões
POTENCIALMENTE distintos (`repo` de `confirmar_alocacao` e
`repo_auditoria`) -- não há transação única cobrindo as duas. Se a
operação de domínio for aplicada com sucesso e a gravação da auditoria
falhar DEPOIS, a mudança canônica já está persistida sem uma linha de
auditoria correspondente. Isso é uma inconsistência real, mas
corrigi-la de verdade (uma transação cobrindo os 2 repositórios)
exigiria unificar a conexão de `repo`/`repo_auditoria` -- decisão
arquitetural própria (existe hoje 1 Postgres físico por trás de ambos
em produção, `magnata-os-db`, mas os adapters atuais não coordenam
transação entre si; e os testes SQLite usam arquivos `.sqlite3`
DIFERENTES de propósito, para isolar cada camada) -- fora do escopo
desta correção pontual de segurança de sessão. **Mitigação aplicada
aqui:** a falha de gravação da auditoria APÓS sucesso do domínio nunca
é silenciosa nem mascara o resultado -- ela vira
`FalhaAoRegistrarAuditoriaAposSucesso`, uma exceção nomeada e
encadeada (nunca um erro genérico, nunca engolida), para que quem
chamar saiba exatamente que a mudança canônica JÁ ocorreu mas a trilha
falhou. Simetricamente, se a operação de domínio falhar E a gravação
do evento de ERRO também falhar, a exceção de auditoria NUNCA substitui
a exceção de domínio original -- ela é só encadeada (`raise ... from
...`), o chamador sempre vê o erro de negócio real."""
from __future__ import annotations

from typing import Callable, Optional, TypeVar

from .eventos import RESULTADO_ERRO, RESULTADO_SUCESSO, OperacaoAuditada, registrar_operacao
from .identidade import Sujeito

_T = TypeVar('_T')


class FalhaAoRegistrarAuditoriaAposSucesso(Exception):
    """A operação de domínio foi aplicada com sucesso, mas a gravação
    do evento de auditoria correspondente falhou -- a mudança canônica
    JÁ ocorreu (nunca revertida por esta camada; ver gate arquitetural
    na docstring do módulo). Nunca levantada silenciosamente: sempre
    encadeada (`__cause__`) à exceção real de escrita da auditoria."""


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
    ou erro. Nunca engole a exceção original -- só observa: se
    `chamada()` falhar e a gravação do evento de ERRO TAMBÉM falhar, o
    chamador ainda vê a exceção de DOMÍNIO original (nunca substituída
    pela de auditoria, só encadeada); se `chamada()` tiver sucesso e a
    gravação do evento de SUCESSO falhar, isso vira
    `FalhaAoRegistrarAuditoriaAposSucesso` -- nunca mascarado como se
    nada tivesse acontecido (CLAUDE.md raiz §4, "falha nunca é
    silenciosa")."""
    try:
        resultado = chamada()
    except Exception as exc_original:
        try:
            registrar_operacao(repo_auditoria, OperacaoAuditada(
                sujeito=sujeito, operacao=operacao, resultado=RESULTADO_ERRO,
                referencia_agregado=referencia_agregado_de_erro, erro_codigo=type(exc_original).__name__,
            ))
        except Exception as exc_auditoria:
            # a falha de auditoria NUNCA substitui a falha de dominio
            # original -- so fica encadeada, para diagnostico.
            raise exc_original from exc_auditoria
        raise

    try:
        registrar_operacao(repo_auditoria, OperacaoAuditada(
            sujeito=sujeito, operacao=operacao, resultado=RESULTADO_SUCESSO,
            referencia_agregado=resultado if isinstance(resultado, str) else None,
        ))
    except Exception as exc_auditoria:
        raise FalhaAoRegistrarAuditoriaAposSucesso(
            f'operacao {operacao!r} foi aplicada com sucesso, mas a gravacao da trilha de '
            f'auditoria falhou: {type(exc_auditoria).__name__}'
        ) from exc_auditoria
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
