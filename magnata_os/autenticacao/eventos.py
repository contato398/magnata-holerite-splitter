"""Trilha "quem fez" -- puro, sem I/O (missão "AUTENTICAÇÃO
ADMINISTRATIVA COMPARTILHADA V1", FASE 6). Genérico -- qualquer módulo
autenticado pode registrar uma operação; nenhuma dependência de
`documental/alocacao` nem de nenhum outro módulo específico aqui.

**Nunca idempotente/deduplicado de propósito** -- ao contrário de
`documental/alocacao/eventos.py`/`captura.py` (onde reprocessar o MESMO
evento de negócio nunca deve duplicar o registro), cada TENTATIVA de
uma operação é, ela mesma, um fato auditável distinto: uma confirmação
repetida 3x gera 3 linhas de auditoria (mesmo que a 2ª/3ª sejam no-op
no domínio) -- colapsar isso esconderia informação de uma trilha cujo
propósito é justamente nunca esconder nada."""
from __future__ import annotations

import dataclasses
from typing import Optional

from .identidade import Sujeito

RESULTADO_SUCESSO = 'SUCESSO'
RESULTADO_ERRO = 'ERRO'
_RESULTADOS_VALIDOS = (RESULTADO_SUCESSO, RESULTADO_ERRO)


def _exigir_texto(valor: object, campo: str) -> None:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f'{campo} deve ser texto nao vazio')


@dataclasses.dataclass(frozen=True)
class OperacaoAuditada:
    """`sujeito.email` é obrigatório (é a própria prova de identidade
    verificada -- um `Sujeito` sem e-mail não pode gerar uma auditoria
    válida, mesmo que tenha `perfil`). `erro_codigo` é OBRIGATÓRIO
    quando `resultado=ERRO` e PROIBIDO quando `resultado=SUCESSO` --
    nunca os dois presentes, nunca os dois ausentes de forma
    inconsistente com o resultado."""

    sujeito: Sujeito
    operacao: str
    resultado: str
    referencia_agregado: Optional[str] = None
    erro_codigo: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.sujeito, Sujeito):
            raise ValueError('sujeito deve ser um Sujeito')
        _exigir_texto(self.sujeito.email, 'sujeito.email')
        _exigir_texto(self.operacao, 'operacao')
        if self.resultado not in _RESULTADOS_VALIDOS:
            raise ValueError(f'resultado deve ser um de {_RESULTADOS_VALIDOS}, recebido {self.resultado!r}')
        if self.resultado == RESULTADO_ERRO and not (self.erro_codigo and self.erro_codigo.strip()):
            raise ValueError('erro_codigo e obrigatorio quando resultado=ERRO')
        if self.resultado == RESULTADO_SUCESSO and self.erro_codigo:
            raise ValueError('erro_codigo so e valido quando resultado=ERRO')


def registrar_operacao(repo, evento: OperacaoAuditada) -> str:
    """Delega a `repo.inserir_operacao(...)` (duck-typed, mesma
    disciplina de `documental/alocacao/captura.py` para `repo`) --
    nunca decide idempotência, nunca reimplementa persistência."""
    import uuid
    operacao_id = f'auditoria-{uuid.uuid4().hex}'
    repo.inserir_operacao(
        operacao_id=operacao_id,
        sujeito_id=evento.sujeito.sujeito_id,
        email=evento.sujeito.email,
        perfil=evento.sujeito.perfil.value,
        operacao=evento.operacao,
        referencia_agregado=evento.referencia_agregado,
        resultado=evento.resultado,
        erro_codigo=evento.erro_codigo,
    )
    return operacao_id
