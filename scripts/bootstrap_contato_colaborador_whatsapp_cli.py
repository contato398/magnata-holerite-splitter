"""Bootstrap REAL do Contato Canônico de Colaborador V1 (WhatsApp) a
partir do Airtable (Funcionários -> Postgres, `contato_colaborador_
observado`, migration 0004).

    python scripts/bootstrap_contato_colaborador_whatsapp_cli.py

Fecha a lacuna registrada em
`/mnt/project-files/magnata-os/origem-dados-holerite.md` ("plano do
bootstrap de contato"): a tabela `contato_colaborador_observado`
existe, está testada, mas nunca foi populada com dado real -- não
havia composition root nenhum que a alimentasse fora de teste. Este
CLI é só isso: lê `Funcionários.WhatsApp` do Airtable (via
`LeitorAirtableSomenteLeitura.listar_funcionarios_contato`, adapter
somente-GET já existente) e grava, cifrado (Fernet) + hash auxiliar
(HMAC), em Postgres, via `executar_bootstrap_contato_colaborador_
whatsapp` (`bootstrap_contato_colaborador_airtable.py`, núcleo já
existente e testado, reaproveitado sem alteração).

Nunca:
    - lê outro campo de `Funcionários` além de `WhatsApp` (mais o id do
      próprio registro);
    - escreve em qualquer tabela além de `contato_colaborador_
      observado`;
    - envia WhatsApp, chama Evolution, ou toca `app.py`;
    - sobrescreve um contato já registrado com hash diferente -- isso é
      sempre um `ConflitoBootstrapContatoColaborador` reportado no
      resumo, nunca uma escrita automática (ver `contato_colaborador.
      ConflitoContatoColaborador`).
    - imprime telefone em claro -- só o `ResultadoBootstrapContato
      Colaborador` (contagens e hashes opacos em disputa).

Disparo SEMPRE manual -- este script nunca é referenciado por
cron/scheduler/render.yaml (CLAUDE.md §9/§12-I). Rodar contra
Airtable/Postgres reais é gate humano (CLAUDE.md §6, requisitos a-f) --
este módulo não decide isso; ele só executa quando chamado, com as
credenciais já presentes no ambiente.

Variáveis de ambiente exigidas (nenhum default silencioso -- falta de
qualquer uma é `RuntimeError` explícito antes de qualquer leitura/
escrita real):
    DATABASE_URL
    AIRTABLE_API_KEY
    MAGNATA_CONTATO_COLABORADOR_FERNET_CHAVE_<VERSAO>
    MAGNATA_CONTATO_COLABORADOR_HMAC_CHAVE_<VERSAO>
    MAGNATA_CONTATO_COLABORADOR_VERSAO_ATUAL
(ver `magnata_os/documental/alocacao/configuracao_contato_colaborador.py`)

Como desfazer uma execução: `DELETE FROM contato_colaborador_observado
WHERE origem = 'bootstrap_airtable_funcionarios_contato'` (toda linha
desta execução tem essa `origem` -- ver assinatura padrão de
`executar_bootstrap_contato_colaborador_whatsapp`; o comando exato é
produzido por `montar_plano_rollback_bootstrap`, única fonte, para
nunca divergir do texto impresso pelo `--dry-run`), ou a migration de
rollback já existente (`0004_criar_contato_colaborador_observado_
rollback.sql`) para desfazer o schema inteiro.

**`--dry-run`**: produz o relatório de reconciliação (contagem de
origem, de destino antes, duplicidade na própria origem, inválidos,
quantos seriam criados, quantos já existem de forma idempotente,
quantos ficariam bloqueados como possível atualização -- nunca
automática -- e o comando de rollback) SEM nenhuma escrita --
`simular_bootstrap_contato_colaborador_whatsapp` nunca chama
`criar_ou_confirmar`. Ainda abre conexões reais de leitura
(Airtable GET + Postgres SELECT) para que as contagens reflitam o
estado real -- só a escrita é que nunca acontece neste modo. Pensado
para ser o que se produz e se mostra ANTES de qualquer autorização de
fase (CLAUDE.md raiz §6, requisitos a-f) para rodar a escrita real.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.documental.alocacao.adapters.postgres_contato_colaborador import (  # noqa: E402
    RepositorioContatoColaboradorPostgres,
)
from magnata_os.documental.alocacao.configuracao_contato_colaborador import (  # noqa: E402
    SegredoContatoColaboradorAusente,
    carregar_configuracao_segredo_contato,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (  # noqa: E402
    LeitorAirtableSomenteLeitura,
)
from magnata_os.documental.importacao_lote.adapters.bootstrap_contato_colaborador_airtable import (  # noqa: E402
    executar_bootstrap_contato_colaborador_whatsapp,
    simular_bootstrap_contato_colaborador_whatsapp,
)
from magnata_os.documental.modulo01.adapters.conexao import (  # noqa: E402
    ConfiguracaoBancoAusente,
    FalhaConexaoBanco,
    abrir_conexao,
)


def _compor_leitor_airtable_a_partir_do_ambiente() -> LeitorAirtableSomenteLeitura:
    api_key = (os.environ.get('AIRTABLE_API_KEY') or '').strip()
    if not api_key:
        raise RuntimeError(
            'AIRTABLE_API_KEY não configurada -- o bootstrap nunca infere credencial (fail-closed).'
        )
    return LeitorAirtableSomenteLeitura(api_key)


def _compor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Bootstrap do Contato Canônico de Colaborador (WhatsApp) a partir do '
            'Airtable. Toda credencial vem do ambiente -- este script não aceita '
            'nenhum argumento além de --dry-run.'
        ),
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help=(
            'Produz o relatório de reconciliação (origem/destino, duplicidade, '
            'inválidos, inserts, atualizações bloqueadas, rollback) sem nenhuma '
            'escrita real.'
        ),
    )
    return parser


def main(argv=None) -> int:
    args = _compor_parser().parse_args(argv)

    try:
        configuracao_segredo = carregar_configuracao_segredo_contato()
        chave_fernet = configuracao_segredo.obter_chave_fernet_atual()
        chave_hmac = configuracao_segredo.obter_chave_hmac_atual()
        versao_chave = configuracao_segredo.versao_atual()
        leitor = _compor_leitor_airtable_a_partir_do_ambiente()
        conexao = abrir_conexao()
    except (SegredoContatoColaboradorAusente, ConfiguracaoBancoAusente, RuntimeError) as exc:
        print(f'CONFIGURACAO_AUSENTE: {exc}')
        return 2
    except FalhaConexaoBanco as exc:
        print(f'FALHA_CONEXAO: {exc}')
        return 2

    try:
        repositorio = RepositorioContatoColaboradorPostgres(conexao)
        if args.dry_run:
            resultado = simular_bootstrap_contato_colaborador_whatsapp(
                fonte_funcionarios=leitor,
                repositorio=repositorio,
                chave_hmac=chave_hmac,
            )
            bloqueado = bool(resultado.atualizacoes_bloqueadas)
        else:
            resultado = executar_bootstrap_contato_colaborador_whatsapp(
                fonte_funcionarios=leitor,
                repositorio=repositorio,
                chave_fernet=chave_fernet,
                chave_hmac=chave_hmac,
                versao_chave=versao_chave,
            )
            bloqueado = bool(resultado.conflitos)
    finally:
        conexao.close()

    print(json.dumps(dataclasses.asdict(resultado), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not bloqueado else 1


if __name__ == '__main__':
    raise SystemExit(main())
