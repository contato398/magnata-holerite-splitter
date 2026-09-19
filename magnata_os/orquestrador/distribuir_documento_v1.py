"""CLI -- adapter de borda para o serviço genérico de Distribuição
Documental (`wiring_distribuicao_documental_shadow.py`).

Responsabilidade estrita, nunca mais que isto:
    1. ler inputs (argv/env);
    2. construir a `OrdemDistribuicaoDocumental`;
    3. compor as dependências reais (Postgres, S3, adapter HTTP legado);
    4. chamar `materializar_distribuicao_documental_shadow`;
    5. mostrar o resultado.

Nenhuma regra de negócio vive aqui -- quantidade de documentos
suportada, política de agrupamento, ordem dos efeitos da assinatura,
idempotência: tudo isso é do serviço genérico. Qualquer outro domínio
(Prestação, RH, um futuro endpoint HTTP) pode chamar
`materializar_distribuicao_documental_shadow` diretamente, sem importar
este módulo.

Mesmo nível de maturidade operacional de `executar_canario_v1.py`:
script manual, nunca chamado pelo Cron Job (`ciclo_producao_v1.py`).
Nunca dispara transporte real (não importa `porta_execucao`,
`transporte_real_habilitado`, nem qualquer adapter de Evolution).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from magnata_os.documental.modulo01.repositorio import RepositorioDocumentos

from .autorizacao_gate import RepositorioAutorizacoesGate
from .obrigacao_assinatura import PortaObrigacaoAssinatura
from .wiring_distribuicao_documental_shadow import (
    ItemDocumentoOrdem,
    OrdemDistribuicaoDocumental,
    ResultadoDistribuicaoDocumentalShadow,
    materializar_distribuicao_documental_shadow,
)


def montar_ordem_distribuicao_documental(
    *,
    documentos: tuple,
    funcionario_id: str,
    destinatario: str,
    canal: str,
    preset_id: str,
    tipo_documento: str,
    exigir_assinatura: bool,
    exigir_comprovante: bool,
    politica_agrupamento: str,
    mensagem_texto: str,
) -> OrdemDistribuicaoDocumental:
    """Só constrói o contrato -- nenhuma validação de negócio além da
    que `OrdemDistribuicaoDocumental.__post_init__` já faz."""
    itens = tuple(
        ItemDocumentoOrdem(documento_id=documento_id, hash_sha256=hash_sha256)
        for documento_id, hash_sha256 in documentos
    )
    return OrdemDistribuicaoDocumental(
        documentos=itens,
        funcionario_id=funcionario_id,
        destinatario=destinatario,
        canal=canal,
        preset_id=preset_id,
        tipo_documento=tipo_documento,
        exigir_assinatura=exigir_assinatura,
        exigir_comprovante=exigir_comprovante,
        politica_agrupamento=politica_agrupamento,
        mensagem_texto=mensagem_texto,
    )


# ---------------------------------------------------------------------
# Composição de dependências a partir do ambiente -- só esta seção lê
# variável de ambiente/importa driver real, mesmo padrão de
# `ciclo_producao_v1._compor_*_a_partir_do_ambiente`. Falha de
# configuração é sempre RuntimeError explícito, nunca default
# silencioso.
# ---------------------------------------------------------------------

def _compor_repositorio_documentos_a_partir_do_ambiente() -> RepositorioDocumentos:
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import (
        RepositorioDocumentosPostgres,
    )
    return RepositorioDocumentosPostgres(abrir_conexao())


def _compor_armazenamento_a_partir_do_ambiente():
    from .ciclo_producao_v1 import _compor_armazenamento_a_partir_do_ambiente as _compor
    return _compor()


def _compor_materializador_a_partir_do_ambiente():
    from magnata_os.documental.modulo01.adapters.materializador_arquivo_legado import (
        MaterializadorArquivoLegadoAirtable,
    )
    api_key = (os.environ.get('AIRTABLE_API_KEY') or '').strip()
    if not api_key:
        raise RuntimeError('AIRTABLE_API_KEY não configurada -- materializador nunca infere credencial (fail-closed).')
    return MaterializadorArquivoLegadoAirtable(api_key_provider=lambda: api_key)


def _compor_obrigacao_assinatura_a_partir_do_ambiente() -> PortaObrigacaoAssinatura:
    from .ciclo_producao_v1 import _compor_obrigacao_assinatura_a_partir_do_ambiente as _compor
    return _compor()


def _compor_repositorio_autorizacoes_a_partir_do_ambiente() -> RepositorioAutorizacoesGate:
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    from .repositorio_autorizacoes_gate_postgres import RepositorioAutorizacoesGatePostgres
    return RepositorioAutorizacoesGatePostgres(abrir_conexao())


def _compor_repositorio_acoes_a_partir_do_ambiente():
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    from .repositorio_acoes_execucao_plano_postgres import RepositorioAcoesExecucaoPlanoPostgres
    return RepositorioAcoesExecucaoPlanoPostgres(abrir_conexao())


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documento', action='append', required=True,
                         help='documento_id:hash_sha256 -- repetível para N>1')
    parser.add_argument('--funcionario-id', required=True)
    parser.add_argument('--destinatario', required=True)
    parser.add_argument('--canal', default='whatsapp')
    parser.add_argument('--preset-id', required=True)
    parser.add_argument('--tipo-documento', required=True)
    parser.add_argument('--exigir-assinatura', action='store_true')
    parser.add_argument('--exigir-comprovante', action='store_true')
    parser.add_argument('--politica-agrupamento', required=True)
    parser.add_argument('--mensagem-texto', required=True)
    parser.add_argument('--ator-referencia', required=True)
    parser.add_argument('--proveniencia', default='distribuir_documento_v1_cli')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    documentos = tuple(
        tuple(par.split(':', 1)) for par in args.documento
    )
    ordem = montar_ordem_distribuicao_documental(
        documentos=documentos,
        funcionario_id=args.funcionario_id,
        destinatario=args.destinatario,
        canal=args.canal,
        preset_id=args.preset_id,
        tipo_documento=args.tipo_documento,
        exigir_assinatura=args.exigir_assinatura,
        exigir_comprovante=args.exigir_comprovante,
        politica_agrupamento=args.politica_agrupamento,
        mensagem_texto=args.mensagem_texto,
    )

    materializador = _compor_materializador_a_partir_do_ambiente() if ordem.exigir_assinatura else None
    porta_assinatura = _compor_obrigacao_assinatura_a_partir_do_ambiente() if ordem.exigir_assinatura else None

    resultado: ResultadoDistribuicaoDocumentalShadow = materializar_distribuicao_documental_shadow(
        ordem=ordem,
        repositorio_documentos=_compor_repositorio_documentos_a_partir_do_ambiente(),
        armazenamento=_compor_armazenamento_a_partir_do_ambiente(),
        materializador=materializador,
        porta_assinatura=porta_assinatura,
        repositorio_autorizacoes=_compor_repositorio_autorizacoes_a_partir_do_ambiente(),
        repositorio_acoes=_compor_repositorio_acoes_a_partir_do_ambiente(),
        ator_referencia=args.ator_referencia,
        proveniencia=args.proveniencia,
        instante=datetime.now(timezone.utc),
    )

    print(json.dumps({
        'event_id': resultado.event_id,
        'autorizacao_id': resultado.autorizacao_id,
        'acao_execucao_id': resultado.acao_execucao_id,
        'arquivo_record_ids': list(resultado.arquivo_record_ids),
        'documento_ids': list(resultado.documento_ids),
        'assinatura_link': resultado.assinatura_link,
        'envelope_sha256': resultado.envelope_sha256,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
