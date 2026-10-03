"""Testa a integração REAL da seleção/curadoria do operador com o ponto
onde a Ordem é composta -- `filtrar_trios_por_selecao_operador` e
`executar_prestacao_selecionada_ate_distribuicao_documental_shadow`
(`wiring_prestacao_distribuicao_documental_shadow.py`).

Reaproveita, via `patch.object`, os MESMOS fakes leves já usados por
`test_wiring_prestacao_distribuicao_documental_shadow.py` para os
`ResultadoAquisicaoPorNecessidade`/dependências do núcleo -- não duplica
o corredor/readiness pesado de `test_wiring_prestacao_ate_distribuicao_
documental_shadow.py`, porque `resultados_aquisicao_prontos_por_
colaborador` é substituído diretamente por um fake determinístico (o
comportamento DELE já é provado à exaustão naquele outro arquivo).
Dados 100% sintéticos.
"""
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ResultadoAquisicaoPorNecessidade,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
from magnata_os.documental.modulo01.materializador_arquivo import ResultadoMaterializacao
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.adapters.postgres_conclusao_obrigacao_assinatura import (
    RepositorioConclusaoObrigacaoAssinaturaEmMemoria,
)
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.selecao_envio_operador_v1 import (
    ItemSelecaoEnvioOperador,
    SelecaoApontaParaNecessidadeInexistente,
    SelecaoApontaParaNecessidadeNaoPronta,
    SelecaoEnvioOperador,
)
import magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow as modulo_wiring
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    ParametrosOrdemPrestacao,
    PresetDaOrdemDivergeDaSelecaoOperador,
    executar_prestacao_selecionada_ate_distribuicao_documental_shadow,
    filtrar_trios_por_selecao_operador,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-1')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-09')


class _MaterializadorFake:
    def __init__(self):
        self._por_chave = {}

    def materializar(self, *, documento, conteudo_bytes, funcionario_id):
        chave = (documento.hash_sha256, funcionario_id)
        if chave not in self._por_chave:
            self._por_chave[chave] = ResultadoMaterializacao(
                arquivo_record_id=f'recARQ{len(self._por_chave) + 1}',
                documento_id=documento.documento_id, funcionario_id=funcionario_id,
                hash_sha256=documento.hash_sha256, reutilizado=False,
            )
        return self._por_chave[chave]


class _PortaAssinaturaFake:
    def __init__(self):
        self._por_correlacao: dict = {}

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id, funcionario_id, tipo_documento, arquivo_record_ids):
        existente = self._por_correlacao.get(acao_execucao_id)
        if existente is not None:
            return existente
        obrigacao = ObrigacaoAssinatura(
            assinatura_id=f'rec-obg-{len(self._por_correlacao) + 1}',
            link=f'https://exemplo.invalid/assinatura/{token_reservado}',
            status='Pendente', tem_comprovante=False,
        )
        self._por_correlacao[acao_execucao_id] = obrigacao
        return obrigacao

    def consultar_por_correlacao(self, *, acao_execucao_id):
        return self._por_correlacao.get(acao_execucao_id)


def _colaborador(entidade_id):
    return ReferenciaCanonica('COLABORADOR', entidade_id)


def _necessidade(*, tipo_documental, colaborador):
    return NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental=tipo_documental,
        motivo_exigencia='teste', colaborador=colaborador,
    )


def _preparar_documento(repositorio_documentos, armazenamento, *, documento_id, conteudo: bytes):
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = Documento(
        documento_id=documento_id, arquivo_original='origem.pdf', nome_original=f'{documento_id}.pdf',
        mime_type='application/pdf', tamanho=len(conteudo), hash_sha256=hash_sha256, origem='teste',
        recebido_em=AGORA, lote_id=None, status=StatusDocumento.REGISTRADO,
        correlation_id=f'corr-{documento_id}', criado_em=AGORA, atualizado_em=AGORA,
    )
    repositorio_documentos.salvar(documento)
    armazenamento.armazenar(hash_sha256, conteudo, documento.mime_type, documento.nome_original, documento.tamanho)
    return documento


def _resultado_aquisicao(documento, *, tipo_documental, colaborador):
    return ResultadoAquisicaoPorNecessidade(
        necessidade=_necessidade(tipo_documental=tipo_documental, colaborador=colaborador),
        documento_id=documento.documento_id, hash_sha256=documento.hash_sha256,
    )


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao
        self._ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((sql, params))
        if 'INSERT INTO magnata_orquestrador.acoes_execucao_plano' in sql and 'RETURNING acao_execucao_id' in sql:
            colunas_valores = params[:-4]
            acao_execucao_id = colunas_valores[0]
            if acao_execucao_id in self.conexao.linhas:
                self._ultimo = None
            else:
                self.conexao.linhas[acao_execucao_id] = colunas_valores
                self._ultimo = (acao_execucao_id,)
        elif sql.strip().startswith('SELECT') and 'acoes_execucao_plano' in sql:
            acao_execucao_id = params[0]
            self._ultimo = self.conexao.linhas.get(acao_execucao_id)
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo


class _Conexao:
    def __init__(self):
        self.executados = []
        self.linhas = {}
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1


def _deps():
    conexao = _Conexao()
    return {
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_execucoes': RepositorioExecucoesEmMemoria(),
        'repositorio_autorizacoes': RepositorioAutorizacoesGateEmMemoria(),
        'repositorio_acoes': RepositorioAcoesExecucaoPlanoPostgres(conexao),
        'repositorio_conclusao': RepositorioConclusaoObrigacaoAssinaturaEmMemoria(),
    }, conexao


def _resolver_sem_assinatura(cliente, competencia, resultados_aquisicao):
    return ParametrosOrdemPrestacao(
        destinatario='5511999999999', preset_id='DOCUMENTOS_SEM_ASSINATURA',
        tipo_documento='COMUNICADO', mensagem_texto='Segue:',
    )


def _resolver_com_assinatura(cliente, competencia, resultados_aquisicao):
    return ParametrosOrdemPrestacao(
        destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA',
        tipo_documento='CONTRATO', mensagem_texto='Assine:',
    )


def _resolver_por_colaborador(mapa: dict):
    """mapa: colaborador_id -> ParametrosOrdemPrestacao"""
    def _fake(cliente, competencia, resultados_aquisicao):
        colaborador = resultados_aquisicao[0].necessidade.colaborador
        return mapa[colaborador.entidade_id]
    return _fake


# ---------------------------------------------------------------------
# filtrar_trios_por_selecao_operador
# ---------------------------------------------------------------------

def test_filtro_seleciona_so_o_colaborador_escolhido_resto_fica_diagnosticado_fora():
    doc_a = _preparar_documento(RepositorioDocumentosEmMemoria(), ArmazenamentoArquivosEmMemoria(), documento_id='a', conteudo=b'a')
    resultado_1 = _resultado_aquisicao(doc_a, tipo_documental='HOLERITE', colaborador=_colaborador('colab-1'))
    resultado_2 = _resultado_aquisicao(doc_a, tipo_documental='HOLERITE', colaborador=_colaborador('colab-2'))
    trios = (
        (_CLIENTE, _COMPETENCIA, (resultado_1,)),
        (_CLIENTE, _COMPETENCIA, (resultado_2,)),
    )
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    filtrados = filtrar_trios_por_selecao_operador(trios, selecao)
    assert len(filtrados) == 1
    assert filtrados[0][3].colaborador_id == 'colab-1'


def test_filtro_n_documentos_para_1_destinatario():
    doc_holerite = _preparar_documento(RepositorioDocumentosEmMemoria(), ArmazenamentoArquivosEmMemoria(), documento_id='h', conteudo=b'h')
    doc_ponto = _preparar_documento(RepositorioDocumentosEmMemoria(), ArmazenamentoArquivosEmMemoria(), documento_id='p', conteudo=b'p')
    colaborador = _colaborador('colab-1')
    trio = (_CLIENTE, _COMPETENCIA, (
        _resultado_aquisicao(doc_holerite, tipo_documental='HOLERITE', colaborador=colaborador),
        _resultado_aquisicao(doc_ponto, tipo_documental='FOLHA_PONTO', colaborador=colaborador),
    ))
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('HOLERITE', 'FOLHA_PONTO'), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    filtrados = filtrar_trios_por_selecao_operador((trio,), selecao)
    assert len(filtrados) == 1
    assert len(filtrados[0][2]) == 2


def test_filtro_selecao_vazia_devolve_vazio():
    doc = _preparar_documento(RepositorioDocumentosEmMemoria(), ArmazenamentoArquivosEmMemoria(), documento_id='a', conteudo=b'a')
    resultado = _resultado_aquisicao(doc, tipo_documental='HOLERITE', colaborador=_colaborador('colab-1'))
    trios = ((_CLIENTE, _COMPETENCIA, (resultado,)),)
    assert filtrar_trios_por_selecao_operador(trios, SelecaoEnvioOperador(itens=())) == ()


def test_filtro_selecao_apontando_para_algo_nao_pronto_e_rejeitada():
    """Trio ausente dos resultados prontos representa exatamente "não
    está PRONTO" -- a seleção aponta para um colaborador que não
    aparece nos trios já elegíveis desta execução."""
    trios = ()
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    with pytest.raises(SelecaoApontaParaNecessidadeInexistente):
        filtrar_trios_por_selecao_operador(trios, selecao)


# ---------------------------------------------------------------------
# executar_prestacao_selecionada_ate_distribuicao_documental_shadow
# ---------------------------------------------------------------------

def test_sem_selecao_nenhuma_ordem_e_criada_padrao_seguro():
    deps, _conexao = _deps()
    resultados = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
        contexto=object(), selecao_operador=SelecaoEnvioOperador(itens=()),
        resolver_parametros_ordem=_resolver_sem_assinatura,
        materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
        **deps,
    )
    assert resultados == ()


def test_selecao_1_documento_1_destinatario_sem_assinatura_chega_a_pending():
    deps, _conexao = _deps()
    doc = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-1', conteudo=b'holerite')
    resultado = _resultado_aquisicao(doc, tipo_documental='HOLERITE', colaborador=_colaborador('colab-1'))
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    with patch.object(modulo_wiring, 'resultados_aquisicao_prontos_por_colaborador',
                       lambda contexto: ((_CLIENTE, _COMPETENCIA, (resultado,)),)):
        resultados = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
            contexto=object(), selecao_operador=selecao, resolver_parametros_ordem=_resolver_sem_assinatura,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
            **deps,
        )
    assert len(resultados) == 1
    assert resultados[0].assinatura_link is None
    assert resultados[0].funcionario_id == 'colab-1'


def test_selecao_1_documento_1_destinatario_com_assinatura_chega_a_pending_com_link():
    deps, _conexao = _deps()
    doc = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-1', conteudo=b'contrato')
    resultado = _resultado_aquisicao(doc, tipo_documental='CONTRATO', colaborador=_colaborador('colab-1'))
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('CONTRATO',), exigir_assinatura_digital_e_comprovante=True,
        ),
    ))
    with patch.object(modulo_wiring, 'resultados_aquisicao_prontos_por_colaborador',
                       lambda contexto: ((_CLIENTE, _COMPETENCIA, (resultado,)),)):
        resultados = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
            contexto=object(), selecao_operador=selecao, resolver_parametros_ordem=_resolver_com_assinatura,
            materializador=_MaterializadorFake(), porta_assinatura=_PortaAssinaturaFake(),
            ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
            **deps,
        )
    assert len(resultados) == 1
    assert resultados[0].assinatura_link is not None


def test_selecao_1_documento_para_n_destinatarios_produz_n_ordens():
    deps, _conexao = _deps()
    doc = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-comunicado', conteudo=b'comunicado')
    resultado_1 = _resultado_aquisicao(doc, tipo_documental='COMUNICADO', colaborador=_colaborador('colab-1'))
    resultado_2 = _resultado_aquisicao(doc, tipo_documental='COMUNICADO', colaborador=_colaborador('colab-2'))
    resultado_3 = _resultado_aquisicao(doc, tipo_documental='COMUNICADO', colaborador=_colaborador('colab-nao-selecionado'))
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('COMUNICADO',), exigir_assinatura_digital_e_comprovante=False,
        ),
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-2',
            tipos_documentais=('COMUNICADO',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    with patch.object(modulo_wiring, 'resultados_aquisicao_prontos_por_colaborador', lambda contexto: (
        (_CLIENTE, _COMPETENCIA, (resultado_1,)),
        (_CLIENTE, _COMPETENCIA, (resultado_2,)),
        (_CLIENTE, _COMPETENCIA, (resultado_3,)),  # NÃO selecionado -- fica diagnosticado, nunca vira Ordem
    )):
        resultados = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
            contexto=object(), selecao_operador=selecao, resolver_parametros_ordem=_resolver_sem_assinatura,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
            **deps,
        )
    assert {r.funcionario_id for r in resultados} == {'colab-1', 'colab-2'}
    assert len(resultados) == 2


def test_selecao_apontando_para_algo_nao_pronto_e_rejeitada_na_composicao():
    deps, _conexao = _deps()
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-inexistente',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    with patch.object(modulo_wiring, 'resultados_aquisicao_prontos_por_colaborador', lambda contexto: ()):
        with pytest.raises(SelecaoApontaParaNecessidadeInexistente):
            executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
                contexto=object(), selecao_operador=selecao, resolver_parametros_ordem=_resolver_sem_assinatura,
                materializador=None, porta_assinatura=None,
                ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
                **deps,
            )


def test_preset_divergente_da_selecao_e_isolado_por_colaborador_e_nao_derruba_os_demais():
    """Operador pediu exigir_assinatura_digital_e_comprovante=True para
    colab-1, mas o resolvedor devolve um preset SEM assinatura --
    fail-closed, isolado (mesma disciplina de erro de domínio de 1
    colaborador nunca contaminar os demais)."""
    deps, _conexao = _deps()
    doc = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-1', conteudo=b'x')
    doc2 = _preparar_documento(RepositorioDocumentosEmMemoria(), ArmazenamentoArquivosEmMemoria(), documento_id='doc-2', conteudo=b'y')
    resultado_1 = _resultado_aquisicao(doc, tipo_documental='CONTRATO', colaborador=_colaborador('colab-1'))
    resultado_2 = _resultado_aquisicao(doc2, tipo_documental='COMUNICADO', colaborador=_colaborador('colab-2'))
    deps['repositorio_documentos'].salvar(doc2)
    deps['armazenamento'].armazenar(doc2.hash_sha256, b'y', doc2.mime_type, doc2.nome_original, doc2.tamanho)

    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('CONTRATO',), exigir_assinatura_digital_e_comprovante=True,
        ),
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-2',
            tipos_documentais=('COMUNICADO',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    resolver = _resolver_por_colaborador({
        'colab-1': ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTOS_SEM_ASSINATURA',  # DIVERGE do pedido (True)
            tipo_documento='CONTRATO', mensagem_texto='Assine:',
        ),
        'colab-2': ParametrosOrdemPrestacao(
            destinatario='5511999999999', preset_id='DOCUMENTOS_SEM_ASSINATURA',
            tipo_documento='COMUNICADO', mensagem_texto='Segue:',
        ),
    })
    with patch.object(modulo_wiring, 'resultados_aquisicao_prontos_por_colaborador', lambda contexto: (
        (_CLIENTE, _COMPETENCIA, (resultado_1,)),
        (_CLIENTE, _COMPETENCIA, (resultado_2,)),
    )):
        resultados = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
            contexto=object(), selecao_operador=selecao, resolver_parametros_ordem=resolver,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
            **deps,
        )
    # colab-1 falhou (isolado, não propagou); colab-2 chegou normalmente a PENDING.
    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-2'


def test_idempotencia_executar_2_vezes_mesma_selecao_mesmo_event_id():
    deps, _conexao = _deps()
    doc = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-1', conteudo=b'holerite-idem')
    resultado = _resultado_aquisicao(doc, tipo_documental='HOLERITE', colaborador=_colaborador('colab-1'))
    selecao = SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=False,
        ),
    ))
    kwargs = dict(
        contexto=object(), selecao_operador=selecao, resolver_parametros_ordem=_resolver_sem_assinatura,
        materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_selecao_v1', instante=AGORA,
        **deps,
    )
    with patch.object(modulo_wiring, 'resultados_aquisicao_prontos_por_colaborador',
                       lambda contexto: ((_CLIENTE, _COMPETENCIA, (resultado,)),)):
        primeiro = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(**kwargs)
        segundo = executar_prestacao_selecionada_ate_distribuicao_documental_shadow(**kwargs)
    assert len(primeiro) == 1 and len(segundo) == 1
    assert primeiro[0].event_id == segundo[0].event_id
    assert primeiro[0].acao_execucao_id == segundo[0].acao_execucao_id
