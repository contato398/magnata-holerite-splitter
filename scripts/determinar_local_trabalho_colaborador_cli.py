"""CLI: canal de determinação manual do local de trabalho (item 6 da
missão "CADASTRO DE COLABORADOR PERSISTENTE V1").

Uso:

    python -m scripts.determinar_local_trabalho_colaborador_cli \\
        --colaborador-id recXXXXXXXXXXXXXX \\
        --local-trabalho "Escala A - Dias Pares" \\
        --determinado-por "operador.rh@magnataservicos.com.br"

Correção de um `local_trabalho` JÁ definido (exige `--motivo-correcao`
explícito -- nunca sobrescrita silenciosa, ver
`dominio_cadastro_colaborador.aplicar_determinacao_local_trabalho`):

    python -m scripts.determinar_local_trabalho_colaborador_cli \\
        --colaborador-id recXXXXXXXXXXXXXX \\
        --local-trabalho "Escala B - Dias Ímpares" \\
        --determinado-por "operador.rh@magnataservicos.com.br" \\
        --motivo-correcao "Colaborador transferido de posto em 2026-10-01"

Responsabilidade ESTRITA desta CLI: validar `colaborador_id` existente
E pendente/já cadastrado, montar `DeterminacaoLocalTrabalho`, chamar
`dominio_cadastro_colaborador.aplicar_determinacao_local_trabalho` e
persistir o resultado via `RepositorioColaboradoresPostgres` -- nada
além disso. Reaproveita
`magnata_os.documental.modulo01.adapters.conexao` (`abrir_conexao`)
para abrir a conexão Postgres -- mesma exceção deliberada já registrada
em `magnata_os/documental/alocacao/fabrica_repositorio_alocacao.py`
(reduzir a superfície de código que lê `DATABASE_URL`/segredo de
conexão, em vez de duplicar essa lógica sensível em mais um lugar).

Comportamento de erro (colaborador inexistente / já com local de
trabalho definido e divergente sem `--motivo-correcao`): mensagem clara
em stderr, saída != 0, NENHUMA escrita -- nunca uma tentativa de
adivinhar ou seguir em frente.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from magnata_os.documental.modulo01.adapters.conexao import (
    ConfiguracaoBancoAusente,
    FalhaConexaoBanco,
    abrir_conexao,
)
from magnata_os.rh_admissao.adapters.repositorio_colaboradores_postgres import (
    RepositorioColaboradoresPostgres,
)
from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    CadastroColaboradorError,
    LocalTrabalhoJaDefinidoError,
    aplicar_determinacao_local_trabalho,
)
from magnata_os.rh_admissao.gatilho_admissao import DeterminacaoLocalTrabalho

_logger = logging.getLogger(__name__)


def determinar_local_trabalho(
    repositorio_colaboradores,
    *,
    colaborador_id: str,
    local_trabalho: str,
    determinado_por: str,
    motivo_correcao: str | None = None,
    agora=None,
):
    """Núcleo testável (sem I/O de processo) -- a função `main` abaixo
    só faz parsing de argumentos/conexão e chama esta função."""
    colaborador = repositorio_colaboradores.buscar_por_id(colaborador_id)
    if colaborador is None:
        raise CadastroColaboradorError(
            f'colaborador_id={colaborador_id!r} não está cadastrado -- '
            'nada a determinar (o cadastro nasce do gatilho de admissão, não desta CLI)'
        )

    determinacao = DeterminacaoLocalTrabalho(
        grupo_escala_id=local_trabalho,
        determinado_por=determinado_por,
        determinado_em=agora or datetime.now(timezone.utc),
    )
    atualizado, evento = aplicar_determinacao_local_trabalho(
        colaborador, determinacao, motivo_correcao=motivo_correcao,
    )
    persistido = repositorio_colaboradores.salvar(atualizado)
    if evento is not None:
        # Histórico append-only real (item 2 da correção do PR #215) --
        # o log estruturado abaixo continua existindo (não é removido),
        # mas deixa de ser a ÚNICA fonte de verdade: o evento agora
        # também é gravado numa tabela que nunca é editada/apagada
        # (`rh_admissao_historico_correcao_local_trabalho`, migration
        # 0003). Gravado DEPOIS de `salvar` persistir o novo
        # `local_trabalho` -- ver limitação declarada no ADR §6 (duas
        # escritas em transações separadas, não atômicas entre si).
        repositorio_colaboradores.registrar_evento_correcao_local_trabalho(evento)
        _logger.info(
            'cadastro_colaborador_local_trabalho_corrigido colaborador_id=%s',
            colaborador_id,
            extra={'evento': 'cadastro_colaborador_local_trabalho_corrigido', **evento.como_evidencia()},
        )
    return persistido, evento


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Determina (ou corrige) o local de trabalho de um colaborador já cadastrado.',
    )
    parser.add_argument('--colaborador-id', required=True)
    parser.add_argument('--local-trabalho', required=True, help='grupo_escala_id determinado pelo humano')
    parser.add_argument('--determinado-por', required=True, help='identificador do operador (nunca dado do colaborador)')
    parser.add_argument(
        '--motivo-correcao', default=None,
        help='obrigatório só quando o colaborador já tem local_trabalho definido e DIFERENTE do novo valor',
    )
    args = parser.parse_args(argv)

    try:
        conexao = abrir_conexao()
    except ConfiguracaoBancoAusente as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        return 1
    except FalhaConexaoBanco as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        return 1

    repositorio = RepositorioColaboradoresPostgres(conexao)
    try:
        persistido, evento = determinar_local_trabalho(
            repositorio,
            colaborador_id=args.colaborador_id,
            local_trabalho=args.local_trabalho,
            determinado_por=args.determinado_por,
            motivo_correcao=args.motivo_correcao,
        )
    except LocalTrabalhoJaDefinidoError as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        print('Use --motivo-correcao para confirmar uma correção explícita.', file=sys.stderr)
        return 1
    except CadastroColaboradorError as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        return 1

    if evento is not None:
        print(f'Local de trabalho CORRIGIDO para colaborador_id={persistido.colaborador_id}.')
    else:
        print(f'Local de trabalho determinado para colaborador_id={persistido.colaborador_id}.')
    print(f'situacao_cadastro={persistido.situacao_cadastro.value}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
