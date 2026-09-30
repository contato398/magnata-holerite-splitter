"""Configuração de segredo da cifra de CPF do Cadastro de Colaborador
PRÓPRIO (`rh_admissao_colaboradores.cpf_cifrado`, migration 0002).

Mesmo padrão institucional já em uso por
`magnata_os/documental/alocacao/configuracao_contato_colaborador.py`
(segredo lido de variável de ambiente, NUNCA hardcoded, NUNCA gerado
on-the-fly quando ausente -- falha explícita e nomeada,
`SegredoCpfColaboradorAusente`, nunca um registro persistido/lido sem
cifra) e a MESMA derivação de chave Fernet (SHA-256 do segredo humano +
`base64.urlsafe_b64encode`, 32 bytes -- formato exigido por
`cryptography.fernet.Fernet`).

**Reproduzida aqui, não importada** de `documental/alocacao/`: os dois
módulos pertencem a contextos desacoplados (`/CLAUDE.md` §3, "módulos
desacoplados -- um módulo não importa o interno de outro"); a própria
`configuracao_contato_colaborador.py` já registra a mesma decisão ao
não generalizar a classe de `configuracao_identidade_colaborador.py`.
Ver `docs/decisoes/cadastro-colaborador-persistente-v1.md` §6.

**Sem versionamento de chave nesta V1** (diferença deliberada em
relação a `configuracao_contato_colaborador.py`): o CPF cifrado aqui
nunca é usado para deduplicação/comparação entre colaboradores (cada
`colaborador_id` já é a chave primária/idempotência do cadastro) --
não há, hoje, nenhum fluxo de bootstrap em lote que precise cifrar sob
uma versão nova antes de promovê-la. Uma única variável de ambiente
(chave atual) é suficiente para o requisito desta missão (cifrar em
repouso); adicionar rotação de chave sem um caso de uso real seria
complexidade não pedida. Decisão registrada, não uma omissão -- ver
ADR §6.

Nenhuma dependência de Postgres/Airtable/Flask aqui -- só
`hashlib`/`base64` da stdlib."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
from typing import Mapping, Optional

_VARIAVEL_CHAVE_FERNET = 'MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE'


class SegredoCpfColaboradorAusente(Exception):
    """A variável de ambiente da chave de cifra do CPF não está
    configurada -- toda leitura/escrita real de `cpf` exige essa
    variável; nunca uma chave gerada on-the-fly, nunca um fallback
    silencioso para texto puro (fail-closed -- ver
    `adapters/repositorio_colaboradores_postgres.py`)."""


def _derivar_chave_fernet_de_segredo(segredo: str) -> bytes:
    """Mesma derivação de
    `configuracao_contato_colaborador._derivar_chave_fernet_de_segredo`
    (reproduzida, não importada -- ver docstring do módulo):
    determinística -- o MESMO segredo sempre produz a MESMA chave
    Fernet, então rotação (fora de escopo aqui) funcionaria trocando o
    segredo na variável de ambiente, sem estado adicional."""
    digest = hashlib.sha256(segredo.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


@dataclasses.dataclass(frozen=True)
class ConfiguracaoSegredoCpfColaborador:
    """Snapshot imutável do ambiente no momento da leitura -- nunca
    cacheado além do escopo de quem chamou
    `carregar_configuracao_segredo_cpf`, para que uma rotação de
    variável de ambiente entre execuções seja sempre respeitada."""

    ambiente: Mapping[str, str]

    def obter_chave_fernet(self) -> bytes:
        """Chave Fernet (bytes, pronta para `Fernet(chave)`) -- fail
        closed: levanta `SegredoCpfColaboradorAusente` (nunca devolve
        uma chave inventada, nunca loga o segredo bruto) quando a
        variável de ambiente não está configurada."""
        valor = self.ambiente.get(_VARIAVEL_CHAVE_FERNET)
        if not valor:
            raise SegredoCpfColaboradorAusente(
                f'{_VARIAVEL_CHAVE_FERNET} nao configurada -- cifra de CPF do '
                f'Cadastro de Colaborador exige essa variavel de ambiente '
                f'(fail-closed: nunca grava/le CPF sem cifra).'
            )
        return _derivar_chave_fernet_de_segredo(valor)


def carregar_configuracao_segredo_cpf(
    ambiente: Optional[Mapping[str, str]] = None,
) -> ConfiguracaoSegredoCpfColaborador:
    """Ponto de entrada único desta configuração. `ambiente=None` (o
    caso real) lê `os.environ` no momento da chamada -- nunca cacheado
    em import time, para que testes possam injetar um mapeamento
    completamente isolado sem tocar o ambiente real do processo."""
    import os

    return ConfiguracaoSegredoCpfColaborador(
        ambiente=ambiente if ambiente is not None else os.environ,
    )
