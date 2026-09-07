"""Configuração de segredo da Identidade Canônica de Colaborador V1.

Mesmo padrão institucional já auditado e em uso em
`magnata_os/autenticacao/adapters/sessao.py::configurar_sessao_segura`:
segredo lido de variável de ambiente, NUNCA hardcoded, NUNCA um valor
gerado on-the-fly quando ausente -- falha explícita e nomeada
(`SegredoIdentidadeColaboradorAusente`), nunca uma sessão/identidade
"funcionando" silenciosamente com um segredo fraco ou inventado.

**Versionamento de chave é obrigatório** (decisão do ULTRAPLAN
aprovado): HMAC determinístico com uma única chave fixa não pode ser
rotacionado sem invalidar todos os hashes já persistidos. O desenho
aqui separa deliberadamente duas perguntas:

  1. "Qual é a chave da versão X?" -- `obter_chave_para_versao`, nunca
     amarrada a qual versão está "atual". Usada pelo BOOTSTRAP durante
     uma rotação: roda com a chave da versão NOVA (ainda não
     promovida) para popular a tabela sob a nova versão, antes de
     qualquer promoção.
  2. "Qual versão devo usar AGORA para uma consulta nova?" --
     `versao_atual`. Só muda quando alguém promove a rotação (passo
     operacional, fora deste código -- trocar a variável de ambiente
     `MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL`).

Isso implementa exatamente a exigência "rotação: backfill da nova
versão antes de promover CURRENT" sem precisar de nenhum estado
mutável em código: backfill usa (1) com a versão alvo explícita;
promoção é só mudar a variável de ambiente lida por (2).

Nenhuma dependência de Postgres/Airtable/Flask aqui -- só `os.environ`
(ou um mapeamento injetado, para teste)."""
from __future__ import annotations

import dataclasses
from typing import Mapping, Optional

_PREFIXO_VARIAVEL_CHAVE = 'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_CHAVE_'
_VARIAVEL_VERSAO_ATUAL = 'MAGNATA_IDENTIDADE_COLABORADOR_HMAC_VERSAO_ATUAL'


class SegredoIdentidadeColaboradorAusente(Exception):
    """A variável de ambiente da chave (ou da versão atual) não está
    configurada -- resolução/bootstrap reais exigem essas variáveis;
    nunca um segredo gerado on-the-fly nem uma versão inventada."""


@dataclasses.dataclass(frozen=True)
class ConfiguracaoSegredoIdentidadeColaborador:
    """Snapshot imutável do ambiente no momento da leitura -- nunca
    cacheado além do escopo de quem chamou `carregar_configuracao_
    segredo`, para que uma rotação de variável de ambiente entre
    execuções seja sempre respeitada."""

    ambiente: Mapping[str, str]

    def obter_chave_para_versao(self, versao: str) -> bytes:
        """Chave (bytes, para uso direto em `hmac.new`) da versão
        pedida -- NUNCA depende de qual versão está "atual". Usada pelo
        bootstrap para popular a tabela sob uma versão nova, antes de
        promovê-la."""
        if not (versao or '').strip():
            raise ValueError('versao deve ser texto nao vazio')
        nome_variavel = f'{_PREFIXO_VARIAVEL_CHAVE}{versao.upper()}'
        valor = self.ambiente.get(nome_variavel)
        if not valor:
            raise SegredoIdentidadeColaboradorAusente(
                f'{nome_variavel} nao configurada -- Identidade Canônica de '
                f'Colaborador exige essa variavel de ambiente para a versao '
                f'{versao!r}.'
            )
        return valor.encode('utf-8')

    def versao_atual(self) -> str:
        """Qual versão de chave deve ser usada AGORA para uma nova
        consulta/derivação -- nunca lida indiretamente de outro lugar.
        Promover uma rotação é só mudar esta variável de ambiente,
        depois que o backfill sob a versão nova já foi confirmado."""
        valor = self.ambiente.get(_VARIAVEL_VERSAO_ATUAL)
        if not valor or not valor.strip():
            raise SegredoIdentidadeColaboradorAusente(
                f'{_VARIAVEL_VERSAO_ATUAL} nao configurada -- Identidade '
                f'Canônica de Colaborador exige uma versao atual explicita.'
            )
        return valor.strip()

    def obter_chave_atual(self) -> bytes:
        """Atalho para o caso comum: chave da versão atualmente
        promovida. Equivalente a
        `obter_chave_para_versao(self.versao_atual())`."""
        return self.obter_chave_para_versao(self.versao_atual())


def carregar_configuracao_segredo(
    ambiente: Optional[Mapping[str, str]] = None,
) -> ConfiguracaoSegredoIdentidadeColaborador:
    """Ponto de entrada único desta configuração. `ambiente=None` (o
    caso real) lê `os.environ` no momento da chamada -- nunca cacheado
    em import time, para que testes possam injetar um mapeamento
    completamente isolado sem tocar o ambiente real do processo."""
    import os

    return ConfiguracaoSegredoIdentidadeColaborador(
        ambiente=ambiente if ambiente is not None else os.environ,
    )
