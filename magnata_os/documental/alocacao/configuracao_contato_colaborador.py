"""Configuração de segredo do Contato Canônico de Colaborador V1.

Mesmo padrão institucional de
`configuracao_identidade_colaborador.py` (segredo lido de variável de
ambiente, NUNCA hardcoded, NUNCA gerado on-the-fly quando ausente --
falha explícita e nomeada, nunca um contato "funcionando" com uma
chave inventada) e versionamento de chave obrigatório (rotação:
backfill sob versão nova antes de promover CURRENT).

**Não é a mesma classe** de `ConfiguracaoSegredoIdentidadeColaborador`
-- REUTILIZA o padrão, não o código, porque o formato de chave difere:
HMAC (identidade) aceita qualquer segredo em bytes; Fernet (contato)
exige uma chave de exatamente 32 bytes, codificada em base64 urlsafe.
Generalizar a classe existente para os dois formatos tocaria um módulo
já aprovado e mesclado por outra missão (Identidade Canônica de
Colaborador V1) fora do escopo desta -- decisão registrada aqui, não
escondida.

**Duas chaves por versão, nunca uma só** (higiene de separação de
chave: cifrar e autenticar/deduplicar nunca compartilham segredo):
`obter_chave_fernet_para_versao` (cifra/decifra o valor) e
`obter_chave_hmac_para_versao` (hash auxiliar de deduplicação/conflito,
nunca recupera o valor)."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
from typing import Mapping, Optional

_PREFIXO_VARIAVEL_CHAVE_FERNET = 'MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_'
_PREFIXO_VARIAVEL_CHAVE_HMAC = 'MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_'
_VARIAVEL_VERSAO_ATUAL = 'MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL'


class SegredoContatoColaboradorAusente(Exception):
    """A variável de ambiente da chave (Fernet ou HMAC) ou da versão
    atual não está configurada -- resolução/bootstrap reais exigem
    essas variáveis; nunca um segredo gerado on-the-fly nem uma versão
    inventada."""


def _derivar_chave_fernet_de_segredo(segredo: str) -> bytes:
    """Fernet exige uma chave de exatamente 32 bytes, urlsafe-base64.
    Um segredo humano (variável de ambiente, comprimento livre) é
    determinístico e uniformemente derivado via SHA-256 (32 bytes) +
    `base64.urlsafe_b64encode` -- nunca o segredo bruto usado
    diretamente como chave Fernet (formato incompatível na maioria dos
    casos). Determinístico: o MESMO segredo sempre produz a MESMA chave
    Fernet, então rotação funciona trocando o segredo na variável de
    ambiente, sem estado adicional."""
    digest = hashlib.sha256(segredo.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


@dataclasses.dataclass(frozen=True)
class ConfiguracaoSegredoContatoColaborador:
    """Snapshot imutável do ambiente no momento da leitura -- nunca
    cacheado além do escopo de quem chamou `carregar_configuracao_
    segredo_contato`, para que uma rotação de variável de ambiente
    entre execuções seja sempre respeitada."""

    ambiente: Mapping[str, str]

    def obter_chave_fernet_para_versao(self, versao: str) -> bytes:
        """Chave Fernet (bytes, pronta para `Fernet(chave)`) da versão
        pedida -- NUNCA depende de qual versão está "atual". Usada pelo
        bootstrap/resolução para popular ou ler sob uma versão
        explícita."""
        if not (versao or '').strip():
            raise ValueError('versao deve ser texto nao vazio')
        nome_variavel = f'{_PREFIXO_VARIAVEL_CHAVE_FERNET}{versao.upper()}'
        valor = self.ambiente.get(nome_variavel)
        if not valor:
            raise SegredoContatoColaboradorAusente(
                f'{nome_variavel} nao configurada -- Contato Canonico de '
                f'Colaborador exige essa variavel de ambiente para a versao '
                f'{versao!r}.'
            )
        return _derivar_chave_fernet_de_segredo(valor)

    def obter_chave_hmac_para_versao(self, versao: str) -> bytes:
        """Chave HMAC (bytes, uso direto em `hmac.new`) da versão
        pedida -- separada da chave Fernet (ver docstring do módulo)."""
        if not (versao or '').strip():
            raise ValueError('versao deve ser texto nao vazio')
        nome_variavel = f'{_PREFIXO_VARIAVEL_CHAVE_HMAC}{versao.upper()}'
        valor = self.ambiente.get(nome_variavel)
        if not valor:
            raise SegredoContatoColaboradorAusente(
                f'{nome_variavel} nao configurada -- Contato Canonico de '
                f'Colaborador exige essa variavel de ambiente para a versao '
                f'{versao!r}.'
            )
        return valor.encode('utf-8')

    def versao_atual(self) -> str:
        """Qual versão de chave deve ser usada AGORA para uma escrita/
        leitura nova -- nunca lida indiretamente de outro lugar."""
        valor = self.ambiente.get(_VARIAVEL_VERSAO_ATUAL)
        if not valor or not valor.strip():
            raise SegredoContatoColaboradorAusente(
                f'{_VARIAVEL_VERSAO_ATUAL} nao configurada -- Contato '
                f'Canonico de Colaborador exige uma versao atual explicita.'
            )
        return valor.strip()

    def obter_chave_fernet_atual(self) -> bytes:
        return self.obter_chave_fernet_para_versao(self.versao_atual())

    def obter_chave_hmac_atual(self) -> bytes:
        return self.obter_chave_hmac_para_versao(self.versao_atual())


def carregar_configuracao_segredo_contato(
    ambiente: Optional[Mapping[str, str]] = None,
) -> ConfiguracaoSegredoContatoColaborador:
    """Ponto de entrada único desta configuração. `ambiente=None` (o
    caso real) lê `os.environ` no momento da chamada -- nunca cacheado
    em import time, para que testes possam injetar um mapeamento
    completamente isolado sem tocar o ambiente real do processo."""
    import os

    return ConfiguracaoSegredoContatoColaborador(
        ambiente=ambiente if ambiente is not None else os.environ,
    )
