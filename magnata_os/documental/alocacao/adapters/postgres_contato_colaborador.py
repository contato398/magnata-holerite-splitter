"""Adapter PostgreSQL para `contato_colaborador.py` (Contato Canônico
de Colaborador V1).

Escrito contra a interface padronizada DB-API 2.0 (PEP 249), mesmo
padrão de `postgres_identidade_colaborador.py` -- nunca importa
psycopg2/psycopg diretamente; qualquer conexão compatível serve (real
ou duplo de teste). A tabela esperada é criada pela migration
`migrations/0004_criar_contato_colaborador_observado.sql` -- NÃO
aplicada por este módulo, e não aplicada em nenhum banco real por esta
missão.

GATE DE IDEMPOTÊNCIA/CONFLITO: `criar_ou_confirmar` insere sob a chave
primária composta (`colaborador_id`, `canal`); uma violação de chave
primária com `hash_auxiliar` DIFERENTE do que já existe é traduzida
para `ConflitoContatoColaborador` -- nunca um `UPDATE`/sobrescrita
silenciosa. Reprocessar o MESMO par (colaborador_id, canal) com o MESMO
`hash_auxiliar` -- reexecução idempotente do mesmo bootstrap -- devolve
a linha já existente sem erro.

`valor_cifrado` viaja como `bytes` (coluna BYTEA) -- este adapter nunca
decifra nada; decifragem só acontece em
`contato_colaborador.decifrar_valor_contato`, chamada só por
`resolver_contato_colaborador_para_ordem`, nunca aqui."""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..contato_colaborador import ConflitoContatoColaborador, RegistroContatoColaborador

_COLUNAS = (
    'colaborador_id', 'canal', 'valor_cifrado', 'hash_auxiliar',
    'versao_chave', 'origem', 'criado_em', 'atualizado_em',
)


def _e_violacao_de_integridade(exc: Exception) -> bool:
    """Mesma detecção duck-typed já usada em
    `postgres_identidade_colaborador.py`/`postgres_repositorio.py` --
    nunca duplicar a lógica em código, só a assinatura mínima aqui
    evita import cruzado desnecessário entre adapters irmãos."""
    for classe in type(exc).__mro__:
        if classe.__name__ == 'IntegrityError':
            return True
    return False


def _linha_para_registro(linha) -> RegistroContatoColaborador:
    (
        colaborador_id, canal, valor_cifrado, hash_auxiliar,
        versao_chave, origem, criado_em, atualizado_em,
    ) = linha
    return RegistroContatoColaborador(
        colaborador_id=colaborador_id, canal=canal,
        valor_cifrado=bytes(valor_cifrado), hash_auxiliar=hash_auxiliar,
        versao_chave=versao_chave, origem=origem,
        criado_em=criado_em, atualizado_em=atualizado_em,
    )


class RepositorioContatoColaboradorPostgres:
    """Implementa `RepositorioContatoColaborador` (`contato_colaborador.
    py`) contra Postgres real."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_colaborador(
        self, colaborador_id: str, canal: str,
    ) -> Optional[RegistroContatoColaborador]:
        colunas = ', '.join(_COLUNAS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM contato_colaborador_observado '
                f'WHERE colaborador_id = %s AND canal = %s',
                (colaborador_id, canal),
            )
            linha = cur.fetchone()
        return _linha_para_registro(linha) if linha else None

    def criar_ou_confirmar(
        self, registro: RegistroContatoColaborador,
    ) -> Tuple[RegistroContatoColaborador, bool]:
        """Tenta inserir; se a chave primária já existir, relê a linha
        existente e decide: MESMO `hash_auxiliar` -> devolve existente
        (idempotente); `hash_auxiliar` DIFERENTE ->
        `ConflitoContatoColaborador`, nunca um UPDATE."""
        existente = self.buscar_por_colaborador(registro.colaborador_id, registro.canal)
        if existente is not None:
            if existente.hash_auxiliar != registro.hash_auxiliar:
                raise ConflitoContatoColaborador(
                    registro.colaborador_id, registro.canal,
                    existente.hash_auxiliar, registro.hash_auxiliar,
                )
            return existente, False

        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO contato_colaborador_observado ({', '.join(_COLUNAS)})
                    VALUES ({', '.join(['%s'] * len(_COLUNAS))})
                    """,
                    (
                        registro.colaborador_id, registro.canal, registro.valor_cifrado,
                        registro.hash_auxiliar, registro.versao_chave, registro.origem,
                        registro.criado_em, registro.atualizado_em,
                    ),
                )
            self._conexao.commit()
            return registro, True
        except Exception as exc:
            self._conexao.rollback()
            if _e_violacao_de_integridade(exc):
                # Corrida: outra transação inseriu a MESMA chave entre o
                # SELECT acima e este INSERT -- relê e aplica a mesma
                # decisão de conflito/idempotência, nunca assume sucesso.
                existente_apos_corrida = self.buscar_por_colaborador(
                    registro.colaborador_id, registro.canal,
                )
                if existente_apos_corrida is not None:
                    if existente_apos_corrida.hash_auxiliar != registro.hash_auxiliar:
                        raise ConflitoContatoColaborador(
                            registro.colaborador_id, registro.canal,
                            existente_apos_corrida.hash_auxiliar, registro.hash_auxiliar,
                        ) from exc
                    return existente_apos_corrida, False
            raise

    def listar_todos(self) -> List[RegistroContatoColaborador]:
        colunas = ', '.join(_COLUNAS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM contato_colaborador_observado ORDER BY criado_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_registro(l) for l in linhas]
