"""E2E Postgres real/efêmero: `executar_prestacao_contato_ate_pending_shadow_v1`
-- a composição nova que liga a aquisição da Prestação ao resolvedor
real do Contato Canônico do Colaborador. Nunca executa transporte.

Roda somente com ``MAGNATA_TEST_POSTGRES_REAL``. Aplica as migrations
canônicas do Orquestrador 0001-0004 (mesmo padrão de
`test_wiring_distribuicao_documental_shadow_real.py`/`test_wiring_
prestacao_distribuicao_documental_shadow.py::test_e2e_postgres_real_
ponte_execucoes_ate_pending_sem_seed_manual`) MAIS a migration 0004 de
`magnata_os/documental/alocacao/migrations/` (`contato_colaborador_
observado`) -- as duas "0004" são migrations DIFERENTES, em diretórios
diferentes, aplicadas na MESMA base efêmera deste teste. Nunca executa
rollback, DELETE ou DROP.

Real: `RepositorioAutorizacoesGatePostgres`, `RepositorioExecucoesPostgres`,
`RepositorioAcoesExecucaoPlanoPostgres` (Orquestrador) e
`RepositorioContatoColaboradorPostgres` (Contato Canônico) -- as 4
únicas dependências desta composição que de fato persistem. Fake/em
memória: `ContextoComposicaoPrestacao` inteiro (aquisição/readiness da
Prestação) -- composição real de Fonte* Airtable é gap separado e
futuro (ver ADR/auditoria), fora de escopo aqui; este teste prova
persistência real do Orquestrador + Contato Canônico, não integração
Airtable. Ramo sem assinatura: `materializador`/`porta_assinatura` são
`None`, nenhuma chamada Airtable/HTTP acontece.
"""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from cryptography.fernet import Fernet

import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo_composicao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
from magnata_os.classificacao.orquestrador_corredor_readonly import (
    ResultadoExecucaoCorredorPrestacao,
)
from magnata_os.classificacao.prestacao_readiness import (
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
from magnata_os.classificacao.resolucao_documento_prestacao import (
    EstadoCorredorDocumentoPrestacao,
    ResultadoProcessamentoDocumentoPrestacao,
)
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RegistroContatoColaborador,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
)
from magnata_os.documental.alocacao.adapters.postgres_contato_colaborador import (
    RepositorioContatoColaboradorPostgres,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_autorizacoes_gate_postgres import (
    RepositorioAutorizacoesGatePostgres,
)
from magnata_os.orquestrador.repositorio_execucoes_postgres import RepositorioExecucoesPostgres
from magnata_os.orquestrador.executar_prestacao_contato_ate_pending_shadow_v1 import (
    executar_prestacao_contato_ate_pending_shadow_v1,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

_RAIZ_MIGRATIONS_ORQUESTRADOR = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
_MIGRATIONS_ORQUESTRADOR = tuple(
    (_RAIZ_MIGRATIONS_ORQUESTRADOR / nome).read_text(encoding='utf-8')
    for nome in (
        '0001_repositorio_execucoes.sql', '0002_autorizacoes_gate.sql',
        '0003_acoes_execucao_plano.sql', '0004_envelope_execucao_autorizada.sql',
    )
)
_MIGRATION_CONTATO_COLABORADOR = (
    Path(__file__).parent / 'magnata_os' / 'documental' / 'alocacao' / 'migrations'
    / '0004_criar_contato_colaborador_observado.sql'
).read_text(encoding='utf-8')

_AGORA = datetime(2099, 3, 1, 12, 0, tzinfo=timezone.utc)
_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-composicao-v1-real-teste'


def _aplicar_migrations_se_ausentes(conn):
    with conn.cursor() as cursor:
        for nome_tabela, migration in zip(
            ('execucoes', 'autorizacoes_gate', 'acoes_execucao_plano'), _MIGRATIONS_ORQUESTRADOR[:3],
        ):
            cursor.execute("SELECT to_regclass(%s)", (f'magnata_orquestrador.{nome_tabela}',))
            if cursor.fetchone()[0] is None:
                cursor.execute(migration)
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='magnata_orquestrador' "
            "AND table_name='acoes_execucao_plano' AND column_name='envelope_sha256'"
        )
        if cursor.fetchone() is None:
            cursor.execute(_MIGRATIONS_ORQUESTRADOR[3])
        cursor.execute("SELECT to_regclass('contato_colaborador_observado')")
        if cursor.fetchone()[0] is None:
            cursor.execute(_MIGRATION_CONTATO_COLABORADOR)
    conn.commit()


# ---------------------------------------------------------------------
# Fakes de Prestação (aquisição/readiness) -- mesmo padrão de
# test_executar_prestacao_contato_ate_pending_shadow_v1.py.
# ---------------------------------------------------------------------

class _RepositorioExecucoesPrestacaoMemoria:
    def __init__(self):
        self._execucoes = {}

    def criar(self, execucao):
        self._execucoes[execucao.execucao_prestacao_id] = execucao
        return execucao

    def buscar_por_id(self, execucao_prestacao_id):
        return self._execucoes.get(execucao_prestacao_id)

    def atualizar_estado(self, *, execucao_prestacao_id, novo_estado, concluido_em=None, **kwargs):
        import dataclasses
        execucao = self._execucoes[execucao_prestacao_id]
        execucao = dataclasses.replace(execucao, estado=novo_estado)
        self._execucoes[execucao_prestacao_id] = execucao
        return execucao


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteClientes:
    def __init__(self, *clientes):
        self._clientes = clientes

    def listar_ativos(self, contexto=None):
        return self._clientes


class _FonteColaboradoresEsperados:
    def __init__(self, mapa: dict):
        self._mapa = mapa

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._mapa.get(cliente, ())


class _FonteCandidatosPorNecessidade:
    def __init__(self, mapa: dict):
        self._mapa = mapa

    def candidatos_para(self, necessidade):
        return self._mapa.get((necessidade.cliente, necessidade.competencia), ())


def _documento_bruto(documento_id, hash_sha256):
    return Documento(
        documento_id=documento_id, arquivo_original=f'{documento_id}.pdf',
        nome_original=f'{documento_id}.pdf', mime_type='application/pdf', tamanho=10,
        hash_sha256=hash_sha256, origem='teste', recebido_em=_AGORA, lote_id=None,
        status='RECEBIDO', correlation_id=f'corr-{documento_id}', criado_em=_AGORA, atualizado_em=_AGORA,
    )


def _resolucao_ancora_holerite(documento_id, *, cliente, competencia, colaborador):
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao, Cardinalidade, ConfiancaResolucao, DimensaoResolucao,
        EstadoResolucaoDimensao, EstadoResultadoSemantico, NivelConfianca,
        PerfilAplicabilidadeResolucao, RegraAplicabilidadeDimensao, ResolucaoDimensao,
        ResultadoResolucaoSemantico,
    )

    def _regra(dimensao):
        return RegraAplicabilidadeDimensao(
            dimensao=dimensao, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )

    def _dim(dimensao, valor):
        return ResolucaoDimensao(
            dimensao=dimensao, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(valor,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )

    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='prestacao-composicao-v1-real-teste', version='1', escopo_documental='prestacao-contas',
        regras=(_regra(DimensaoResolucao.CLIENTE), _regra(DimensaoResolucao.COMPETENCIA)),
    )
    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id='resolver-composicao-v1-real-teste', resolver_version='1',
        politica_id='prestacao-composicao-v1-real', politica_version='1', perfil=perfil,
        resolucoes=(_dim(DimensaoResolucao.CLIENTE, cliente), _dim(DimensaoResolucao.COMPETENCIA, competencia)),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA, necessita_revisao_humana=False,
    )


def _executor_readonly_resolve_holerite(cliente, competencia, colaborador):
    def _fake(contexto_corredor, sink):
        sink.adicionar(ItemInventarioPrestacao(
            documento_id=contexto_corredor.documento_id, tipo_documental=TIPO_HOLERITE,
            cliente=cliente, competencia=competencia, colaborador=colaborador,
        ))
        resultado_processamento = ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto_corredor.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
            tipo_documental=TIPO_HOLERITE,
            resolucao_semantica=_resolucao_ancora_holerite(
                contexto_corredor.documento_id, cliente=cliente, competencia=competencia, colaborador=colaborador,
            ),
        )
        return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=resultado_processamento),)
    return _fake


def _mensagem_texto(cliente, competencia):
    return f'Segue seu documento -- {cliente.entidade_id}/{competencia.entidade_id}'


def test_e2e_postgres_real_prestacao_contato_ate_pending():
    """Prova a cadeia completa contra Postgres real/efêmero: pacote
    PRONTO (fake) -> contato REAL persistido em `contato_colaborador_
    observado` -> resolvedor real -> Ordem -> Evento canônico
    (`execucoes`, real) -> WAITING_GATE -> Preview -> autorização
    shadow (`autorizacoes_gate`, real) -> Plano -> Envelope -> AÇÃO
    PENDING (`acoes_execucao_plano`, real). Replay não duplica nenhuma
    das 4 tabelas."""
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-e2e-real-composicao-v1')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-e2e-real-composicao-v1')
    competencia = ReferenciaCanonica('COMPETENCIA', '2099-03')
    conteudo = b'holerite-e2e-real-composicao-v1'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('documento-e2e-real-composicao-v1', hash_sha256)

    try:
        _aplicar_migrations_se_ausentes(conn)

        repositorio_contato = RepositorioContatoColaboradorPostgres(conn)
        repositorio_contato.criar_ou_confirmar(RegistroContatoColaborador(
            colaborador_id='colab-e2e-real-composicao-v1', canal=CANAL_WHATSAPP,
            valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, '5511999998888'),
            hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, '5511999998888'),
            versao_chave='v1', origem='teste_e2e_real', criado_em=_AGORA, atualizado_em=_AGORA,
        ))

        repositorio_documentos = RepositorioDocumentosEmMemoria()
        armazenamento = ArmazenamentoArquivosEmMemoria()
        contexto = ContextoComposicaoPrestacao(
            competencia_base='2099-03',
            fonte_clientes=_FonteClientes(cliente),
            fonte_requisitos=_FonteRequisitosVazia(),
            repositorio_execucoes=_RepositorioExecucoesPrestacaoMemoria(),
            requisitos_base=(RequisitoDocumentalPrestacao(TIPO_HOLERITE),),
            competencias_por_cliente={cliente: competencia},
            fonte_colaboradores_esperados=_FonteColaboradoresEsperados({cliente: (colaborador,)}),
            fonte_candidatos_por_necessidade=_FonteCandidatosPorNecessidade(
                {(cliente, competencia): (documento,)},
            ),
            tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
            repositorio_documentos=repositorio_documentos,
            armazenamento_arquivos=armazenamento,
        )

        fake_executor = _executor_readonly_resolve_holerite(cliente, competencia, colaborador)
        kwargs = dict(
            contexto=contexto, repositorio_contato=repositorio_contato, chave_fernet=_CHAVE_FERNET,
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
            montar_mensagem_texto=_mensagem_texto,
            repositorio_documentos=repositorio_documentos, armazenamento=armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_execucoes=RepositorioExecucoesPostgres(conn),
            repositorio_autorizacoes=RepositorioAutorizacoesGatePostgres(conn),
            repositorio_acoes=RepositorioAcoesExecucaoPlanoPostgres(conn),
            ator_referencia='ator:e2e:real:composicao:v1', proveniencia='e2e_real_composicao_v1',
            instante=_AGORA,
        )

        with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
             patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
            repositorio_documentos.salvar(documento)
            armazenamento.armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
            primeiro = executar_prestacao_contato_ate_pending_shadow_v1(**kwargs)
            segundo = executar_prestacao_contato_ate_pending_shadow_v1(**kwargs)

        assert len(primeiro) == 1 and len(segundo) == 1
        assert primeiro[0].event_id == segundo[0].event_id
        assert primeiro[0].acao_persistida.acao_execucao_id == segundo[0].acao_persistida.acao_execucao_id
        assert primeiro[0].acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM magnata_orquestrador.acoes_execucao_plano WHERE acao_execucao_id = %s',
                (primeiro[0].acao_persistida.acao_execucao_id,),
            )
            (quantidade,) = cursor.fetchone()
        assert quantidade == 1  # replay nao duplicou a acao persistida

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM contato_colaborador_observado WHERE colaborador_id = %s',
                ('colab-e2e-real-composicao-v1',),
            )
            (quantidade_contatos,) = cursor.fetchone()
        assert quantidade_contatos == 1  # nunca duplica o contato persistido
    finally:
        conn.close()
