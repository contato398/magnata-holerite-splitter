"""Composição Prestação -> Orquestrador com persistência real das ações,
sempre sem transporte. Cobre a extensão aditiva de
``wiring_prestacao_orquestrador_postgres_shadow``: persistência, idempotência
e ausência estrutural de qualquer import/chamada de transporte.
"""
import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.orquestrador.autorizacao_gate import (
    RepositorioAutorizacoesGateEmMemoria,
)
from magnata_os.orquestrador.plano_comunicacao import ConteudoItem
from magnata_os.orquestrador.politica_comunicacao import (
    ItemComunicacao,
    hash_conteudo_comunicacao,
    montar_preview_comunicacao,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_prestacao_orquestrador_postgres_shadow import (
    materializar_prestacao_orquestrador_persistente_shadow,
)

_INSTANTE = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
_TEXTO = 'Comunicação sintética para validação da persistência do executor.'
_MIDIA = b'midia-persistencia-totalmente-sintetica-v1'
_DESTINATARIO = 'destinatario:sintetico:persistencia:001'


def _pacote():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-sintetico-persistencia-001')
    competencia = ReferenciaCanonica('COMPETENCIA', '2099-01')
    return PacotePrestacaoCliente(
        cliente=cliente,
        competencia=competencia,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(ItemInventarioPrestacao(
            documento_id='documento-sintetico-persistencia-001',
            tipo_documental='DOCUMENTO_SINTETICO',
            cliente=cliente,
            competencia=competencia,
        ),),
        tipos_obrigatorios=('DOCUMENTO_SINTETICO',),
    )


def _item(conteudo=_MIDIA):
    return ItemComunicacao(
        'documento', 'arquivo-sintetico-persistencia.bin',
        hash_conteudo_comunicacao(conteudo),
    )


def _preview_id():
    return montar_preview_comunicacao(
        destinatarios=(_DESTINATARIO,), texto=_TEXTO, itens=(_item(),),
        assinatura=False, comprovante=True,
    ).preview_id


class _RepositorioAcoesFalso:
    """Espelha a interface de ``RepositorioAcoesExecucaoPlanoPostgres`` usada
    pelo wiring, delegando a lógica real de identidade/idempotência ao mesmo
    ``criar_registro_acao_plano`` que o adapter real usa -- não reimplementa
    a regra, só troca o transporte SQL por um dicionário em memória.
    """

    def __init__(self):
        self._por_id = {}

    def materializar_registros(self, *, registros, autorizacao):
        persistidos = []
        for registro in registros:
            existente = self._por_id.get(registro.acao_execucao_id)
            if existente is None:
                self._por_id[registro.acao_execucao_id] = registro
                persistidos.append(registro)
            else:
                persistidos.append(existente)
        return tuple(persistidos)


def _executar(
    repo_exec=None, repo_auth=None, repo_acoes=None, armazenamento=None,
    **overrides,
):
    repo_exec = repo_exec or RepositorioExecucoesEmMemoria()
    repo_auth = repo_auth or RepositorioAutorizacoesGateEmMemoria()
    repo_acoes = repo_acoes or _RepositorioAcoesFalso()
    armazenamento = armazenamento or ArmazenamentoArquivosEmMemoria()
    kwargs = dict(
        pacote=_pacote(),
        repositorio_execucoes=repo_exec,
        repositorio_autorizacoes=repo_auth,
        repositorio_acoes=repo_acoes,
        armazenamento=armazenamento,
        destinatarios=(_DESTINATARIO,),
        texto=_TEXTO,
        itens=(_item(),),
        conteudos=(ConteudoItem('documento', 'arquivo-sintetico-persistencia.bin', _MIDIA),),
        assinatura=False,
        comprovante=True,
        preview_id_autorizado=_preview_id(),
        ator_referencia='ator:sintetico:persistencia:001',
        proveniencia_autorizacao='persistencia_shadow_sintetico',
        instante=_INSTANTE,
    )
    kwargs.update(overrides)
    return (
        materializar_prestacao_orquestrador_persistente_shadow(**kwargs),
        repo_exec, repo_auth, repo_acoes,
    )


def test_plano_autorizado_persiste_uma_acao_por_notificacao():
    resultado, _, _, _ = _executar()

    assert len(resultado.acoes) == resultado.plano.plano.total_notificacoes == 1
    acao = resultado.acoes[0]
    assert acao.event_id == resultado.intencao.execucao.event_id
    assert acao.preview_id == resultado.autorizacao.preview_id
    assert acao.autorizacao_id == resultado.autorizacao.autorizacao_id
    assert acao.estado == EstadoAcaoExecucaoPlano.PENDING
    assert acao.attempt == 0


def test_reaplicacao_do_mesmo_evento_e_idempotente_na_persistencia():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    repo_acoes = _RepositorioAcoesFalso()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    primeiro, _, _, _ = _executar(
        repo_exec, repo_auth, repo_acoes, armazenamento,
    )
    segundo, _, _, _ = _executar(
        repo_exec, repo_auth, repo_acoes, armazenamento,
    )

    assert len(primeiro.acoes) == len(segundo.acoes) == 1
    assert primeiro.acoes[0].acao_execucao_id == segundo.acoes[0].acao_execucao_id
    assert len(repo_acoes._por_id) == 1
    assert primeiro.acoes[0].envelope_sha256 is not None
    assert armazenamento.existe(primeiro.acoes[0].envelope_sha256)


def test_acoes_persistidas_nao_contem_destinatario_texto_ou_midia_em_claro():
    resultado, _, _, _ = _executar()
    acao = resultado.acoes[0]

    for campo in dataclass_fields_texto(acao):
        assert _DESTINATARIO not in campo
        assert _TEXTO not in campo
        assert _MIDIA.decode(errors='ignore') not in campo


def test_blob_e_gravado_antes_do_banco_e_falha_de_db_deixa_so_orfao():
    armazenamento = ArmazenamentoArquivosEmMemoria()

    class _RepositorioFalha:
        def materializar_registros(self, *, registros, autorizacao):
            assert all(
                armazenamento.existe(registro.envelope_sha256)
                for registro in registros
            )
            raise RuntimeError('falha sintetica de banco')

    with pytest.raises(RuntimeError, match='falha sintetica'):
        _executar(
            repo_acoes=_RepositorioFalha(), armazenamento=armazenamento,
        )
    assert len(armazenamento._objetos) == 2  # mídia + envelope órfãos


def dataclass_fields_texto(registro):
    import dataclasses
    return [
        str(valor) for valor in dataclasses.astuple(registro)
        if isinstance(valor, str)
    ]


def test_modulo_continua_estruturalmente_sem_transporte():
    fonte = Path(
        'magnata_os/orquestrador/wiring_prestacao_orquestrador_postgres_shadow.py'
    ).read_text(encoding='utf-8')

    arvore = ast.parse(fonte)
    imports = {
        alias.name
        for no in ast.walk(arvore)
        if isinstance(no, (ast.Import, ast.ImportFrom))
        for alias in no.names
    }

    assert 'executar_plano_disparo' not in imports
    assert not any('transporte' in nome.lower() for nome in imports)
    assert not any('evolution' in nome.lower() for nome in imports)
    assert '/whatsapp/enviar-' not in fonte

    # Ausência de CHAMADA (não de menção em docstring/comentário) ao trio
    # claim/checkpoint: esta fase só materializa, nunca reivindica nem
    # finaliza -- isso fica para uma fase futura, com hard gate próprio.
    chamadas = {
        no.func.attr for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert 'reivindicar_proxima' not in chamadas
    assert 'marcar_sucesso' not in chamadas
    assert 'marcar_falha' not in chamadas
