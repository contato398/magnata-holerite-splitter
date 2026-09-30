"""Domínio puro: Cadastro de Colaborador PRÓPRIO do Magnata OS.

Contexto (ver `docs/decisoes/cadastro-colaborador-persistente-v1.md`):
quando um Kit de Admissão chega com um colaborador novo, o operador
quer que o Magnata OS já cadastre esse colaborador num registro
PRÓPRIO -- não Airtable, não Secullum -- para servir, entre outras
coisas, de fonte real do "diretório de nomes" que
`interpretar_ordem_operador_v1.py` já espera receber (hoje opcional e
vazio; este módulo só provê a fonte).

Reaproveita, sem duplicar, o que `gatilho_admissao.py` já define:
`DadosColaboradorKitAdmissao` (o que já dá para extrair de um Kit) e
`DeterminacaoLocalTrabalho` (a decisão humana pontual sobre onde o
colaborador vai trabalhar -- NUNCA lida/inferida automaticamente, ver
`docs/decisoes/local-trabalho-determinacao-humana-admissao-v1.md`).
Este módulo não reabre essa decisão: local de trabalho continua sendo
sempre determinação humana.

Domínio puro: nenhum import de Flask, driver de banco, boto3 ou
cliente Airtable -- só tipo Python (`dataclass`, `Enum`, `datetime`) e
os próprios contratos de `gatilho_admissao.py`.

Dimensões mantidas SEPARADAS (`/CLAUDE.md` §4, `magnata_os/CLAUDE.md`):
`situacao_cadastro` (o cadastro está completo ou pendente?) nunca é
fundida com `local_trabalho` (qual é o valor determinado?) -- são
perguntas diferentes, mesmo quando uma implica a outra por invariante
de domínio (ver `Colaborador.__post_init__`).

CRITÉRIO DE CORREÇÃO DE LOCAL DE TRABALHO JÁ DEFINIDO (item 6 da missão,
registrado aqui e em `docs/decisoes/cadastro-colaborador-persistente-v1.md`
§4 -- mesmo princípio de "arquivo original é imutável" (`/CLAUDE.md`
§4) adaptado a cadastro):

- Reprocessar o MESMO kit com o MESMO local de trabalho já persistido é
  idempotência (nunca um evento, nunca um erro) -- `aplicar_determinacao_
  local_trabalho` devolve o colaborador inalterado (só `atualizado_em`
  avança).
- Determinar um local de trabalho quando `local_trabalho` ainda é
  `None` (`situacao_cadastro == AGUARDANDO_LOCAL_TRABALHO`) é o caminho
  normal -- preenche e completa o cadastro.
- Tentar mudar um `local_trabalho` JÁ preenchido para um valor
  DIFERENTE, sem `motivo_correcao`, é RECUSADO
  (`LocalTrabalhoJaDefinidoError`) -- nunca uma sobrescrita silenciosa.
- A mesma mudança COM `motivo_correcao` (texto não vazio, autoria via
  `determinado_por`) é aceita e produz um `EventoCorrecaoLocalTrabalho`
  explícito -- o valor anterior nunca desaparece sem deixar rastro.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from magnata_os.rh_admissao.gatilho_admissao import (
    DadosColaboradorKitAdmissao,
    DeterminacaoLocalTrabalho,
)

EVENTO_CADASTRO_COLABORADOR_PENDENTE = 'cadastro_colaborador_pendente_local_trabalho'
EVENTO_CADASTRO_COLABORADOR_COMPLETO = 'cadastro_colaborador_completo'
EVENTO_CADASTRO_COLABORADOR_LOCAL_TRABALHO_CORRIGIDO = 'cadastro_colaborador_local_trabalho_corrigido'


class CadastroColaboradorError(ValueError):
    """Erro estrutural de domínio -- entrada inválida demais para
    compor/alterar um `Colaborador`."""


class LocalTrabalhoJaDefinidoError(CadastroColaboradorError):
    """Recusa de sobrescrever um `local_trabalho` já preenchido com um
    valor DIFERENTE sem `motivo_correcao` explícito -- nunca uma edição
    silenciosa (ver critério no cabeçalho deste módulo)."""


class SituacaoCadastroColaborador(str, enum.Enum):
    AGUARDANDO_LOCAL_TRABALHO = 'AGUARDANDO_LOCAL_TRABALHO'
    """Colaborador extraído do Kit, mas sem determinação humana de
    local de trabalho ainda -- `local_trabalho is None` sempre que esta
    situação vale (invariante reforçada em `Colaborador.__post_init__`).
    Mesmo vocabulário de `SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_
    TRABALHO` (gatilho_admissao.py) -- dimensão irmã, mas enum próprio:
    a situação do CADASTRO persistido não é a mesma coisa que a situação
    do PROCESSAMENTO do kit pela porta Secullum (um é sobre o registro,
    o outro sobre a intenção enviada a um sistema externo)."""
    CADASTRO_COMPLETO = 'CADASTRO_COMPLETO'
    """`local_trabalho` determinado e persistido -- sempre não-`None`
    quando esta situação vale."""


@dataclass(frozen=True)
class EventoCorrecaoLocalTrabalho:
    """Registro append-only (nunca editado/apagado) de UMA correção de
    `local_trabalho` já definido. Não é o *event store* oficial do
    Módulo 01 (`documentos`/`eventos_documentais`) -- é o rastro mínimo
    desta missão, hoje emitido via log estruturado
    (`EVENTO_CADASTRO_COLABORADOR_LOCAL_TRABALHO_CORRIGIDO`) pelo
    chamador (CLI de determinação manual). Promovê-lo a uma tabela
    própria é trabalho futuro, não decidido nem construído aqui (ver
    ADR §5)."""

    colaborador_id: str
    local_trabalho_anterior: str
    local_trabalho_novo: str
    motivo_correcao: str
    determinado_por: str
    determinado_em: datetime

    def __post_init__(self) -> None:
        for campo in ('colaborador_id', 'local_trabalho_anterior', 'local_trabalho_novo',
                      'motivo_correcao', 'determinado_por'):
            valor = getattr(self, campo)
            if not isinstance(valor, str) or not valor.strip():
                raise CadastroColaboradorError(f'EventoCorrecaoLocalTrabalho.{campo} é obrigatório')
        if self.local_trabalho_anterior == self.local_trabalho_novo:
            raise CadastroColaboradorError(
                'EventoCorrecaoLocalTrabalho exige valor novo diferente do anterior -- '
                'reprocessar o mesmo valor é idempotência, não correção')

    def como_evidencia(self) -> dict:
        """Só ids/valores de local de trabalho (nunca CPF/nome) --
        mesma disciplina de `ResultadoGatilhoAdmissao.como_evidencia()`."""
        return {
            'colaborador_id': self.colaborador_id,
            'local_trabalho_anterior': self.local_trabalho_anterior,
            'local_trabalho_novo': self.local_trabalho_novo,
            'motivo_correcao': self.motivo_correcao,
            'determinado_por': self.determinado_por,
            'determinado_em': self.determinado_em.isoformat(),
        }


@dataclass(frozen=True)
class Colaborador:
    """Registro persistente de um Colaborador no Cadastro PRÓPRIO do
    Magnata OS.

    `colaborador_id` é a MESMA chave de idempotência já usada por
    `RegistroGatilhoAdmissaoEmMemoria` (gatilho_admissao.py) -- um Kit
    de Admissão corresponde a um evento de admissão por colaborador;
    nenhum esquema de idempotência novo foi inventado aqui.

    Invariante de domínio (`situacao_cadastro` XOR `local_trabalho`,
    nunca os dois de um jeito inconsistente -- reforçada também no
    CHECK da migration, defesa em profundidade):
    - `AGUARDANDO_LOCAL_TRABALHO` <=> `local_trabalho is None`
    - `CADASTRO_COMPLETO` <=> `local_trabalho is not None`
    """

    colaborador_id: str
    cpf: str
    nome: str
    situacao_cadastro: SituacaoCadastroColaborador
    cargo: Optional[str] = None
    local_trabalho: Optional[str] = None
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.colaborador_id.strip():
            raise CadastroColaboradorError('colaborador_id é obrigatório')
        if not self.cpf.strip():
            raise CadastroColaboradorError('cpf é obrigatório')
        if not self.nome.strip():
            raise CadastroColaboradorError('nome é obrigatório')
        if not isinstance(self.situacao_cadastro, SituacaoCadastroColaborador):
            raise CadastroColaboradorError('situacao_cadastro deve ser SituacaoCadastroColaborador')
        if self.situacao_cadastro == SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO:
            if self.local_trabalho is not None:
                raise CadastroColaboradorError(
                    'AGUARDANDO_LOCAL_TRABALHO exige local_trabalho None -- nunca fundir as duas dimensões')
        else:
            if not self.local_trabalho or not self.local_trabalho.strip():
                raise CadastroColaboradorError(
                    'CADASTRO_COMPLETO exige local_trabalho preenchido -- nunca fundir as duas dimensões')

    def como_evidencia(self) -> dict:
        """Só ids/enums/local de trabalho -- NUNCA cpf/nome (mesma
        disciplina de `ResultadoGatilhoAdmissao.como_evidencia()`)."""
        return {
            'colaborador_id': self.colaborador_id,
            'situacao_cadastro': self.situacao_cadastro.value,
            'local_trabalho': self.local_trabalho,
            'cargo': self.cargo,
        }


def compor_colaborador_a_partir_do_kit(
    dados: DadosColaboradorKitAdmissao,
    determinacao: Optional[DeterminacaoLocalTrabalho],
    *,
    agora: datetime,
) -> Colaborador:
    """Traduz o que o gatilho já recebe (`DadosColaboradorKitAdmissao` +
    `DeterminacaoLocalTrabalho` opcional) para um `Colaborador` pronto
    para persistir -- mesma regra do gatilho: sem `determinacao`, o
    cadastro nasce pendente (`AGUARDANDO_LOCAL_TRABALHO`), nunca
    adivinha."""
    if determinacao is None:
        return Colaborador(
            colaborador_id=dados.colaborador_id,
            cpf=dados.cpf,
            nome=dados.nome,
            cargo=dados.cargo,
            situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
            local_trabalho=None,
            criado_em=agora,
            atualizado_em=agora,
        )
    return Colaborador(
        colaborador_id=dados.colaborador_id,
        cpf=dados.cpf,
        nome=dados.nome,
        cargo=dados.cargo,
        situacao_cadastro=SituacaoCadastroColaborador.CADASTRO_COMPLETO,
        local_trabalho=determinacao.grupo_escala_id,
        criado_em=agora,
        atualizado_em=determinacao.determinado_em,
    )


def aplicar_determinacao_local_trabalho(
    colaborador: Colaborador,
    determinacao: DeterminacaoLocalTrabalho,
    *,
    motivo_correcao: Optional[str] = None,
) -> "tuple[Colaborador, Optional[EventoCorrecaoLocalTrabalho]]":
    """Aplica uma determinação humana de local de trabalho a um
    `Colaborador` JÁ EXISTENTE (buscado do repositório) -- usada pelo
    canal de determinação manual (item 6). Nunca chamada pelo wiring
    automático do gatilho (que usa `compor_colaborador_a_partir_do_kit`
    para compor o registro do zero a cada kit).

    Devolve `(colaborador_atualizado, evento_ou_None)`:
    - `local_trabalho` ainda `None` -> completa o cadastro, sem evento.
    - `local_trabalho` já igual ao novo valor -> idempotência: mesmo
      colaborador, só `atualizado_em` avança, sem evento.
    - `local_trabalho` já definido e DIFERENTE, sem `motivo_correcao` ->
      `LocalTrabalhoJaDefinidoError` (nunca sobrescreve em silêncio).
    - `local_trabalho` já definido e DIFERENTE, COM `motivo_correcao` ->
      aplica e devolve o `EventoCorrecaoLocalTrabalho` correspondente.
    """
    novo_valor = determinacao.grupo_escala_id

    if colaborador.local_trabalho is None:
        atualizado = replace(
            colaborador,
            situacao_cadastro=SituacaoCadastroColaborador.CADASTRO_COMPLETO,
            local_trabalho=novo_valor,
            atualizado_em=determinacao.determinado_em,
        )
        return atualizado, None

    if colaborador.local_trabalho == novo_valor:
        atualizado = replace(colaborador, atualizado_em=determinacao.determinado_em)
        return atualizado, None

    if not motivo_correcao or not motivo_correcao.strip():
        raise LocalTrabalhoJaDefinidoError(
            f'colaborador_id={colaborador.colaborador_id} já tem local_trabalho='
            f'{colaborador.local_trabalho!r} definido -- mudar para {novo_valor!r} exige '
            f'motivo_correcao explícito (nunca sobrescrita silenciosa)'
        )

    evento = EventoCorrecaoLocalTrabalho(
        colaborador_id=colaborador.colaborador_id,
        local_trabalho_anterior=colaborador.local_trabalho,
        local_trabalho_novo=novo_valor,
        motivo_correcao=motivo_correcao,
        determinado_por=determinacao.determinado_por,
        determinado_em=determinacao.determinado_em,
    )
    atualizado = replace(
        colaborador,
        local_trabalho=novo_valor,
        atualizado_em=determinacao.determinado_em,
    )
    return atualizado, evento
