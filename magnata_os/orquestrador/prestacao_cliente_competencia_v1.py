"""Prestação do cliente X -- competência Y (ponto de entrada J4).

    python -m magnata_os.orquestrador.prestacao_cliente_competencia_v1 \\
        --cliente recXXXXXXXX --competencia 2026-09

Por padrão só DIAGNOSTICA (somente leitura): para cada documento exigido
diz se está PRONTO, AUSENTE, EM_REVISAO, ENCONTRADO_NAO_ELEGIVEL,
CONFLITO, FONTE_INDISPONIVEL -- com onde procurou e o que encontrou -- e
se a Ordem pode sair. Não grava nada.

Com `--ate-pending`, segue pelo caminho JÁ EXISTENTE
(`executar_prestacao_contato_ate_pending_shadow_v1`): Ordem -> Evento ->
Preview -> Autorização (shadow) -> ações PENDING. Nunca executa
transporte: o executor do canal continua sendo o ciclo de produção, com
suas três barreiras. Preset e mensagem são decisão de negócio -- sempre
informados por quem roda (sem default).

Rodar contra o ambiente real (Postgres/S3/Airtable de produção) é gate
humano (CLAUDE.md §6/§12-I). Este módulo não decide isso.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import diagnosticar_prestacao

from .composicao_prestacao_real_v1 import (
    DependenciasPrestacaoReal,
    compor_dependencias_a_partir_do_ambiente,
    fechar_dependencias,
    montar_contexto_prestacao,
    parse_competencia,
)

PROVENIENCIA = 'prestacao_cliente_competencia_v1'
PRESETS_SEM_ASSINATURA = frozenset({'DOCUMENTO_UNITARIO_SEM_ASSINATURA', 'DOCUMENTOS_SEM_ASSINATURA'})


def executar_prestacao_cliente_competencia(
    *,
    cliente_id: str,
    competencia_base: str,
    dependencias: DependenciasPrestacaoReal,
    competencia_snapshot_airtable_comprovada=None,
    ate_pending: bool = False,
    executar_ate_pending: Optional[Callable[..., tuple]] = None,
    instante: Optional[datetime] = None,
) -> Mapping[str, object]:
    """Diagnóstico sempre; Ordens até PENDING só com `ate_pending` e só se
    o pacote do cliente estiver PRONTO (a mesma regra do caminho
    existente -- aqui só evitamos chamá-lo à toa). `executar_ate_pending`
    recebe o contexto e devolve os resultados do núcleo (injeção: em
    produção, `executar_prestacao_contato_ate_pending_shadow_v1` já
    composto com seus repositórios)."""
    contexto = montar_contexto_prestacao(
        cliente_id=cliente_id,
        competencia_base=competencia_base,
        dependencias=dependencias,
        competencia_snapshot_airtable_comprovada=competencia_snapshot_airtable_comprovada,
    )
    diagnostico = diagnosticar_prestacao(contexto)
    relatorio = {'modo': 'ate_pending' if ate_pending else 'diagnostico', **diagnostico.como_dict()}
    if not ate_pending:
        return relatorio

    if executar_ate_pending is None:
        raise ValueError('ate_pending exige executar_ate_pending composto')
    if not any(c.ordem_pronta for c in diagnostico.clientes):
        relatorio['ordens'] = []
        relatorio['ordens_motivo'] = 'pacote_nao_pronto'
        return relatorio

    resultados = executar_ate_pending(contexto=contexto, instante=instante or datetime.now(timezone.utc))
    relatorio['ordens'] = [
        {
            'funcionario_id': r.funcionario_id,
            'event_id': r.event_id,
            'estado_acao': r.acao_persistida.estado.value,
        }
        for r in resultados
    ]
    return relatorio


def _compor_executar_ate_pending_a_partir_do_ambiente(*, preset_id: str, mensagem: str, dependencias):
    """Reutiliza os compositores existentes do núcleo (repositórios do
    Orquestrador em Postgres, contato canônico cifrado). Sem assinatura
    e sem materializador legado: presets com assinatura exigem os
    compositores de assinatura, fora desta V1 -- fail-closed."""
    from .distribuir_documento_v1 import (
        _compor_repositorio_acoes_a_partir_do_ambiente,
        _compor_repositorio_autorizacoes_a_partir_do_ambiente,
        _compor_repositorio_execucoes_a_partir_do_ambiente,
    )
    from .executar_prestacao_contato_ate_pending_shadow_v1 import (
        compor_chave_fernet_contato_a_partir_do_ambiente,
        compor_repositorio_contato_a_partir_do_ambiente,
        executar_prestacao_contato_ate_pending_shadow_v1,
    )

    if preset_id not in PRESETS_SEM_ASSINATURA:
        raise RuntimeError(
            f'preset {preset_id!r} não suportado por esta V1 da linha de comando '
            f'(aceitos: {sorted(PRESETS_SEM_ASSINATURA)}; assinatura exige compositores próprios)'
        )
    repositorio_contato = compor_repositorio_contato_a_partir_do_ambiente()
    chave_fernet = compor_chave_fernet_contato_a_partir_do_ambiente()
    repositorio_execucoes = _compor_repositorio_execucoes_a_partir_do_ambiente()
    repositorio_autorizacoes = _compor_repositorio_autorizacoes_a_partir_do_ambiente()
    repositorio_acoes = _compor_repositorio_acoes_a_partir_do_ambiente()

    def _executar(*, contexto, instante):
        return executar_prestacao_contato_ate_pending_shadow_v1(
            contexto=contexto, repositorio_contato=repositorio_contato, chave_fernet=chave_fernet,
            preset_id=preset_id, tipo_documento='PRESTACAO_CONTAS',
            montar_mensagem_texto=lambda cliente, competencia: mensagem,
            repositorio_documentos=dependencias.repositorio_documentos,
            armazenamento=dependencias.armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_execucoes=repositorio_execucoes,
            repositorio_autorizacoes=repositorio_autorizacoes,
            repositorio_acoes=repositorio_acoes,
            ator_referencia=f'cli:{PROVENIENCIA}', proveniencia=PROVENIENCIA, instante=instante,
        )

    return _executar


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cliente', required=True, help='id do cliente (registro Airtable recXXX)')
    parser.add_argument('--competencia', required=True, help='competência-base AAAA-MM')
    parser.add_argument('--snapshot-airtable-comprovado', default=None,
                        help='AAAA-MM: SÓ se o vínculo Funcionário->Local de hoje vale para essa competência')
    parser.add_argument('--ate-pending', action='store_true', help='gerar Ordens até PENDING (sem transporte)')
    parser.add_argument('--preset', help='obrigatório com --ate-pending (decisão de negócio)')
    parser.add_argument('--mensagem', help='obrigatório com --ate-pending')
    args = parser.parse_args(argv)
    if args.ate_pending and not (args.preset and args.mensagem):
        parser.error('--ate-pending exige --preset e --mensagem')
    if args.ate_pending and args.preset not in PRESETS_SEM_ASSINATURA:
        parser.error(f'--preset deve ser um de {sorted(PRESETS_SEM_ASSINATURA)}')
    try:
        parse_competencia(args.competencia)
        if args.snapshot_airtable_comprovado:
            parse_competencia(args.snapshot_airtable_comprovado)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main(argv=None) -> int:
    args = _parse_args(argv)
    snapshot = parse_competencia(args.snapshot_airtable_comprovado) if args.snapshot_airtable_comprovado else None
    dependencias = compor_dependencias_a_partir_do_ambiente()
    try:
        executar = (
            _compor_executar_ate_pending_a_partir_do_ambiente(
                preset_id=args.preset, mensagem=args.mensagem, dependencias=dependencias,
            ) if args.ate_pending else None
        )
        relatorio = executar_prestacao_cliente_competencia(
            cliente_id=args.cliente, competencia_base=args.competencia, dependencias=dependencias,
            competencia_snapshot_airtable_comprovada=snapshot,
            ate_pending=args.ate_pending, executar_ate_pending=executar,
        )
    finally:
        fechar_dependencias(dependencias)
    print(json.dumps(relatorio, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
