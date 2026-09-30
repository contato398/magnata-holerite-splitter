"""Adapter PostgreSQL do Cadastro de Colaborador (`RepositorioColaboradores`).

Implementa, sobre as tabelas `rh_admissao_colaboradores` (migrations
`0001_criar_tabela_colaboradores.sql` + `0002_cifrar_cpf_colaboradores.sql`)
e `rh_admissao_historico_correcao_local_trabalho`
(`0003_criar_historico_correcao_local_trabalho.sql` -- NENHUMA aplicada
por este módulo), o contrato `RepositorioColaboradores`
(`magnata_os/rh_admissao/repositorio_colaboradores.py`).

DB-API 2.0 (PEP 249), mesmo padrão de
`documental/modulo01/adapters/postgres_repositorio.py` e
`documental/alocacao/adapters/postgres_alocacao.py`: nunca importa
psycopg/psycopg2 por nome; qualquer conexão compatível serve.

Idempotência: `salvar` é um `INSERT ... ON CONFLICT (colaborador_id) DO
UPDATE` -- a mesma chave (`colaborador_id`) já usada por
`gatilho_admissao.RegistroGatilhoAdmissaoEmMemoria`. Este adapter NUNCA
decide se uma mudança de `local_trabalho` já definido é legítima --
essa regra pertence ao domínio
(`dominio_cadastro_colaborador.aplicar_determinacao_local_trabalho`);
o adapter só grava o que o chamador já validou. Uma chamada = uma
transação: sucesso grava tudo, qualquer exceção reverte (`rollback()`),
nunca sucesso parcial silencioso.

CIFRA DE CPF (item 1 do plano de correção do PR #215; ver
`docs/decisoes/cadastro-colaborador-persistente-v1.md` §6): `cpf` NUNCA
trafega em texto puro para/do banco. Este adapter é o ÚNICO lugar do
Cadastro de Colaborador que cifra/decifra (`Colaborador.cpf`, no
domínio, continua um `str` puro -- o domínio nunca sabe que existe
cifra, mesma disciplina de `contato_colaborador.py` em relação a
`ResolverParametrosOrdemPrestacao`). Fernet (AES-128-CBC + HMAC
autenticado, biblioteca `cryptography`), mesmo mecanismo já aprovado
para telefone (`documental/alocacao/contato_colaborador.py`), chave
derivada de `configuracao_cpf_colaborador.py` (variável de ambiente,
nunca hardcoded, nunca logada). Ausência da variável de ambiente é
FAIL-CLOSED: `SegredoCpfColaboradorAusente` propaga sem ser capturada
por este módulo -- nenhuma escrita/leitura acontece sem cifra.

HISTÓRICO APPEND-ONLY DE CORREÇÃO DE LOCAL DE TRABALHO (item 2 do plano
de correção): `registrar_evento_correcao_local_trabalho` grava um
`INSERT` em `rh_admissao_historico_correcao_local_trabalho` -- nunca um
`UPDATE`/`DELETE` (a migration 0003 também bloqueia isso a nível de
banco, mesmo padrão de `eventos_documentais`/migration 0003 do Módulo
01). `listar_historico_correcao_local_trabalho` só lê.
"""
from __future__ import annotations

from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

from magnata_os.rh_admissao.configuracao_cpf_colaborador import (
    ConfiguracaoSegredoCpfColaborador,
    carregar_configuracao_segredo_cpf,
)
from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    Colaborador,
    EventoCorrecaoLocalTrabalho,
    SituacaoCadastroColaborador,
)

_TABELA = 'rh_admissao_colaboradores'
_TABELA_HISTORICO = 'rh_admissao_historico_correcao_local_trabalho'

_COLUNAS = (
    'colaborador_id', 'cpf_cifrado', 'nome', 'cargo', 'local_trabalho',
    'situacao_cadastro', 'criado_em', 'atualizado_em',
)

_COLUNAS_HISTORICO = (
    'colaborador_id', 'local_trabalho_anterior', 'local_trabalho_novo',
    'motivo_correcao', 'determinado_por', 'determinado_em',
)


class CpfColaboradorDescriptografiaFalhou(Exception):
    """`cpf_cifrado` não pôde ser decifrado com a chave informada --
    chave errada ou token corrompido. Nunca propaga a exceção crua da
    biblioteca de criptografia (que pode incluir o token bruto) -- só
    este tipo. Fail-closed: quem captura esta exceção nunca deve
    inferir o CPF, só tratar como leitura indisponível."""


def _cifrar_cpf(chave_fernet: bytes, cpf: str) -> bytes:
    if not chave_fernet:
        raise ValueError('chave_fernet nao pode ser vazia')
    if not (cpf or '').strip():
        raise ValueError('cpf nao pode ser vazio')
    return Fernet(chave_fernet).encrypt(cpf.encode('utf-8'))


def _decifrar_cpf(chave_fernet: bytes, cpf_cifrado) -> str:
    if not chave_fernet:
        raise ValueError('chave_fernet nao pode ser vazia')
    try:
        return Fernet(chave_fernet).decrypt(bytes(cpf_cifrado)).decode('utf-8')
    except InvalidToken as exc:
        raise CpfColaboradorDescriptografiaFalhou(
            'nao foi possivel decifrar o cpf com a chave informada'
        ) from exc


def _linha_para_colaborador(linha, chave_fernet: bytes) -> Colaborador:
    (colaborador_id, cpf_cifrado, nome, cargo, local_trabalho,
     situacao_cadastro, criado_em, atualizado_em) = linha
    return Colaborador(
        colaborador_id=colaborador_id,
        cpf=_decifrar_cpf(chave_fernet, cpf_cifrado),
        nome=nome,
        cargo=cargo,
        local_trabalho=local_trabalho,
        situacao_cadastro=SituacaoCadastroColaborador(situacao_cadastro),
        criado_em=criado_em,
        atualizado_em=atualizado_em,
    )


def _linha_para_evento_correcao(linha) -> EventoCorrecaoLocalTrabalho:
    (colaborador_id, local_trabalho_anterior, local_trabalho_novo,
     motivo_correcao, determinado_por, determinado_em) = linha
    return EventoCorrecaoLocalTrabalho(
        colaborador_id=colaborador_id,
        local_trabalho_anterior=local_trabalho_anterior,
        local_trabalho_novo=local_trabalho_novo,
        motivo_correcao=motivo_correcao,
        determinado_por=determinado_por,
        determinado_em=determinado_em,
    )


class RepositorioColaboradoresPostgres:
    def __init__(
        self,
        conexao,
        *,
        configuracao_segredo_cpf: Optional[ConfiguracaoSegredoCpfColaborador] = None,
    ) -> None:
        self._conexao = conexao
        # Injetável para teste (chave determinística sem variável de
        # ambiente real); em produção, sempre `carregar_configuracao_
        # segredo_cpf()` (lê `os.environ` no momento de cada operação,
        # nunca cacheada em import time -- ver docstring do módulo de
        # configuração).
        self._configuracao_segredo_cpf = configuracao_segredo_cpf or carregar_configuracao_segredo_cpf()

    def _chave_fernet(self) -> bytes:
        """Fail-closed: `SegredoCpfColaboradorAusente` (ver
        `configuracao_cpf_colaborador.py`) propaga sem ser capturada
        aqui -- nenhuma operação de `cpf` prossegue sem a chave."""
        return self._configuracao_segredo_cpf.obter_chave_fernet()

    def salvar(self, colaborador: Colaborador) -> Colaborador:
        chave = self._chave_fernet()
        cpf_cifrado = _cifrar_cpf(chave, colaborador.cpf)
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA} ({", ".join(_COLUNAS)}) '
                    'VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now()), COALESCE(%s, now())) '
                    'ON CONFLICT (colaborador_id) DO UPDATE SET '
                    'cpf_cifrado = EXCLUDED.cpf_cifrado, nome = EXCLUDED.nome, cargo = EXCLUDED.cargo, '
                    'local_trabalho = EXCLUDED.local_trabalho, '
                    'situacao_cadastro = EXCLUDED.situacao_cadastro, '
                    'atualizado_em = EXCLUDED.atualizado_em '
                    f'RETURNING {", ".join(_COLUNAS)}',
                    (
                        colaborador.colaborador_id, cpf_cifrado, colaborador.nome,
                        colaborador.cargo, colaborador.local_trabalho,
                        colaborador.situacao_cadastro.value,
                        colaborador.criado_em, colaborador.atualizado_em,
                    ),
                )
                linha = cursor.fetchone()
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return _linha_para_colaborador(linha, chave)

    def buscar_por_id(self, colaborador_id: str) -> Optional[Colaborador]:
        chave = self._chave_fernet()
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {", ".join(_COLUNAS)} FROM {_TABELA} WHERE colaborador_id = %s',
                (colaborador_id,),
            )
            linha = cursor.fetchone()
        return _linha_para_colaborador(linha, chave) if linha is not None else None

    def listar(self) -> Tuple[Colaborador, ...]:
        chave = self._chave_fernet()
        with self._conexao.cursor() as cursor:
            cursor.execute(f'SELECT {", ".join(_COLUNAS)} FROM {_TABELA} ORDER BY colaborador_id')
            linhas = cursor.fetchall()
        return tuple(_linha_para_colaborador(linha, chave) for linha in linhas)

    def registrar_evento_correcao_local_trabalho(
        self, evento: EventoCorrecaoLocalTrabalho,
    ) -> EventoCorrecaoLocalTrabalho:
        """`INSERT` puro em `rh_admissao_historico_correcao_local_trabalho`
        -- nunca um `UPDATE`/`DELETE` (append-only, ver docstring do
        módulo e migration 0003). Nunca cifra nada (local de trabalho e
        motivo não são dado pessoal sensível na mesma categoria do CPF
        -- mesma disciplina de `EventoCorrecaoLocalTrabalho.
        como_evidencia`, que já nunca inclui CPF/nome)."""
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_HISTORICO} ({", ".join(_COLUNAS_HISTORICO)}) '
                    f'VALUES ({", ".join(["%s"] * len(_COLUNAS_HISTORICO))})',
                    (
                        evento.colaborador_id, evento.local_trabalho_anterior,
                        evento.local_trabalho_novo, evento.motivo_correcao,
                        evento.determinado_por, evento.determinado_em,
                    ),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return evento

    def listar_historico_correcao_local_trabalho(
        self, colaborador_id: str,
    ) -> Tuple[EventoCorrecaoLocalTrabalho, ...]:
        """Só leitura, ordenada por ordem de registro (`evento_id`) --
        nunca por `determinado_em` (que é entrada do chamador, não
        controlada pelo banco; ordenar pela chave append-only garante a
        ordem real de gravação mesmo com relógios divergentes)."""
        colunas = ', '.join(_COLUNAS_HISTORICO)
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {colunas} FROM {_TABELA_HISTORICO} '
                'WHERE colaborador_id = %s ORDER BY evento_id ASC',
                (colaborador_id,),
            )
            linhas = cursor.fetchall()
        return tuple(_linha_para_evento_correcao(linha) for linha in linhas)
