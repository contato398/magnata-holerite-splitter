"""Composição até `PENDING` com autorização humana REAL -- Etapa
Pré-Canário Seguro da V1 WhatsApp.

Fecha o caminho:
    OrdemDistribuicaoDocumental (já produzida pelo corredor real da
    Prestação, PR #183, ou por qualquer outro chamador -- este módulo
    nunca sabe de onde a Ordem veio)
    -> Evento Canônico -> Grande Orquestrador -> WAITING_GATE (núcleo
       genérico, `wiring_distribuicao_documental_shadow.
       registrar_evento_canonico_ordem_distribuicao_documental_shadow`,
       intocado)
    -> Preview (`montar_preview_comunicacao`, intocado)
    -> autorização humana REAL (`autorizacao_operador_real_v1.
       autorizar_preview_operador_real`, nunca shadow)
    -> PlanoDisparo -> Envelope -> ação PENDING persistida
       (`montar_plano_disparo`/`armazenar_acao_e_envelope_v1`/
       `criar_registro_acao_plano`, todos intocados)
    -> PARADA.

Escopo estrito desta V1 (Marco A / Pré-Canário): só o ramo SEM
assinatura (`ordem.exigir_assinatura=False`), exatamente 1 documento
(`politica_agrupamento='UNITARIO'`) -- mesma restrição que `_montar_
ramo_sem_assinatura` já impõe em `wiring_distribuicao_documental_
shadow.py`. Nunca compõe o ramo com assinatura (fora de escopo desta
etapa, ver Ultraplan Corretivo: Marco A não depende da migration 0006
justamente por nunca tocar esse ramo).

Por que uma composição nova em vez de parametrizar `materializar_
distribuicao_documental_shadow`: aquele módulo é usado por múltiplos
chamadores já validados (canário genérico #179, Prestação #181);
injetar ali um segundo caminho de autorização, mesmo como parâmetro
opcional com default preservando compatibilidade, ampliaria o raio de
mudança de um arquivo crítico e amplamente testado sem necessidade
comprovada para esta etapa (que é, por definição, uma única composição
root nova e isolada -- mesmo padrão já usado por `executar_prestacao_
contato_ate_pending_shadow_v1.py`, `executar_canario_v1.py`,
`distribuir_documento_v1.py`). O pequeno trecho de resolução de
documento + montagem de preview/plano é reproduzido aqui (não
importado como privado) por clareza -- é a MESMA lógica de `_montar_
ramo_sem_assinatura`, nunca uma reinterpretação dela; qualquer
mudança de contrato lá (`ItemComunicacao`/`ConteudoItem`/
`montar_plano_disparo`) precisa ser espelhada aqui, e os testes deste
módulo travam esse espelhamento.

Nunca importa `porta_execucao`/`transporte_real_habilitado`/
`ExecutorEvolutionLegado`/`ciclo_producao_v1` -- termina estritamente
em PENDING, mesma garantia estrutural do núcleo genérico."""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Tuple

from magnata_os.autenticacao.identidade import Sujeito
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentos

from .autorizacao_gate import RepositorioAutorizacoesGate
from .autorizacao_operador_real_v1 import autorizar_preview_operador_real
from .envelope_execucao_autorizada import armazenar_acao_e_envelope_v1
from .plano_comunicacao import ConteudoItem, montar_plano_disparo
from .politica_comunicacao import ItemComunicacao, montar_preview_comunicacao
from .repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
    criar_registro_acao_plano,
)
from .wiring_distribuicao_documental_shadow import (
    DistribuicaoDocumentalError,
    DocumentoAusenteNaOrdem,
    InconsistenciaOrdemDocumento,
    OrdemDistribuicaoDocumental,
    ResultadoDistribuicaoDocumentalShadow,
    derivar_identidade_ordem_distribuicao,
)

__all__ = [
    'DocumentoUnitarioObrigatorio',
    'materializar_documento_pre_canario_operador_real_v1',
]


class DocumentoUnitarioObrigatorio(DistribuicaoDocumentalError):
    """Esta composição só aceita `politica_agrupamento='UNITARIO'` com
    exatamente 1 documento -- fail-closed antes de qualquer I/O, mesma
    disciplina de `_validar_e_mapear_politica_agrupamento`."""


def _resolver_unico_documento(
    ordem: OrdemDistribuicaoDocumental,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
) -> Tuple[Documento, bytes]:
    (item,) = ordem.documentos
    documento = repositorio_documentos.buscar_por_id(item.documento_id)
    if documento is None:
        raise DocumentoAusenteNaOrdem(
            f'documento_id não encontrado no repositório canônico: {item.documento_id}'
        )
    if documento.hash_sha256 != item.hash_sha256:
        raise InconsistenciaOrdemDocumento(
            f'hash declarado na Ordem ({item.hash_sha256}) != hash do Documento canônico '
            f'({documento.hash_sha256}) para documento_id={item.documento_id}'
        )
    with armazenamento.abrir_leitura(documento.hash_sha256) as arquivo:
        conteudo_bytes = arquivo.read()
    return documento, conteudo_bytes


def materializar_documento_pre_canario_operador_real_v1(
    *,
    ordem: OrdemDistribuicaoDocumental,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    sujeito: Sujeito,
    instante: datetime,
) -> ResultadoDistribuicaoDocumentalShadow:
    """Composição completa até `PENDING`, com autorização humana REAL.

    Pré-condição: o evento canônico da Ordem já deve estar registrado
    em `execucoes` (`WAITING_GATE`) -- responsabilidade do chamador,
    via `wiring_distribuicao_documental_shadow.registrar_evento_
    canonico_ordem_distribuicao_documental_shadow`, nunca duplicada
    aqui (mesmo padrão de `materializar_distribuicao_documental_shadow`,
    que também não registra o evento canônico sozinha)."""
    if ordem.exigir_assinatura:
        raise DistribuicaoDocumentalError(
            'esta composição é exclusiva do ramo sem assinatura (Marco A/Pré-Canário); '
            'exigir_assinatura=True está fora de escopo desta etapa'
        )
    if (len(ordem.documentos), ordem.politica_agrupamento) != (1, 'UNITARIO'):
        raise DocumentoUnitarioObrigatorio(
            f'{len(ordem.documentos)} documento(s) com politica_agrupamento='
            f'{ordem.politica_agrupamento!r} -- esta composição só aceita 1 documento UNITARIO'
        )

    event_id = derivar_identidade_ordem_distribuicao(ordem)
    documento, conteudo_bytes = _resolver_unico_documento(ordem, repositorio_documentos, armazenamento)

    item_preview = ItemComunicacao(
        tipo='documento', nome=documento.nome_original, conteudo_sha256=documento.hash_sha256,
    )
    preview = montar_preview_comunicacao(
        destinatarios=(ordem.destinatario,), texto=ordem.mensagem_texto,
        itens=(item_preview,), assinatura=False, comprovante=ordem.exigir_comprovante,
        preferencia='separado',
    )

    autorizacao = autorizar_preview_operador_real(
        repositorio_autorizacoes=repositorio_autorizacoes, preview=preview,
        event_id=event_id, sujeito=sujeito, instante=instante,
    )

    conteudo_item = ConteudoItem(tipo='documento', nome=documento.nome_original, conteudo=conteudo_bytes)
    plano = montar_plano_disparo(
        preview=preview, texto=ordem.mensagem_texto, conteudos=(conteudo_item,),
        preview_id_autorizado=autorizacao.preview_id, autorizacao_explicita=True,
    )

    # Herdado do núcleo genérico (PR #184, `materializar_distribuicao_
    # documental_shadow`): TODAS as ações do plano são persistidas, cada
    # uma com o próprio Envelope -- nunca só `plano.acoes[0]`. No ramo
    # sem assinatura com preferência 'separado', o passo de texto vem
    # ANTES do passo de documento (`_composicao_separada`,
    # `politica_comunicacao.py`); pegar só `acoes[0]` persistia
    # exclusivamente a ação de TEXTO e o documento nunca chegava a
    # `PENDING` -- exatamente o defeito que #184 corrigiu no núcleo e
    # que esta composição herdava por espelhamento. Corrigido aqui
    # reproduzindo o mesmo laço, nunca um mecanismo de persistência
    # paralelo.
    registros = []
    for acao_do_plano in plano.acoes:
        registro = criar_registro_acao_plano(
            event_id=event_id, plano=plano, autorizacao=autorizacao, acao=acao_do_plano, criado_em=instante,
        )
        envelope_sha256_acao = armazenar_acao_e_envelope_v1(
            armazenamento=armazenamento, registro=registro, acao=acao_do_plano,
        )
        registros.append(dataclasses.replace(registro, envelope_sha256=envelope_sha256_acao))
    acoes_persistidas = repositorio_acoes.materializar_registros(
        registros=tuple(registros), autorizacao=autorizacao,
    )
    acao_persistida = acoes_persistidas[0]

    return ResultadoDistribuicaoDocumentalShadow(
        event_id=event_id,
        autorizacao_id=autorizacao.autorizacao_id,
        acao_execucao_id=acao_persistida.acao_execucao_id,
        arquivo_record_ids=(),
        documento_ids=(documento.documento_id,),
        funcionario_id=ordem.funcionario_id,
        assinatura_link=None,
        envelope_sha256=acao_persistida.envelope_sha256,
        acao_persistida=acao_persistida,
        acoes_persistidas=tuple(acoes_persistidas),
    )
    # STOP -- porta_execucao/transporte_real_habilitado/ExecutorEvolutionLegado/
    # ciclo_producao_v1 nunca importados nem chamados neste módulo.
