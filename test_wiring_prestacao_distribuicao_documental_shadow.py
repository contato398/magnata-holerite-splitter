"""Wiring Prestação de Contas -> Distribuição Documental Genérica V1.

Testa APENAS montagem/repasse deste elo -- as invariantes internas do
núcleo genérico (ordem dos efeitos, idempotência de token, replay,
malformação de link, etc.) já são provadas por
`test_wiring_distribuicao_documental_shadow.py` e não são duplicadas
aqui.
"""
import ast
import hashlib
from datetime import datetime, timezone

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
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.politica_preset_distribuicao_documental import (
    PresetDistribuicaoDocumentalDesconhecido,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    InconsistenciaOrdemDocumento,
    ItemDocumentoOrdem,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    ColaboradorAusenteNaNecessidade,
    ColaboradorDivergenteEntreDocumentos,
    materializar_prestacao_distribuicao_documental_shadow,
    montar_ordem_distribuicao_documental_de_prestacao,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------
# Fakes -- mesmos padrões já usados por test_wiring_distribuicao_
# documental_shadow.py, duplicados aqui deliberadamente para isolamento
# de teste (mesma convenção já usada no repo, ex.: cada arquivo `_real`
# define seus próprios `_kwargs()`/fakes).
# ---------------------------------------------------------------------

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
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


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
        self.ordem_chamadas: list = []

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id, funcionario_id, tipo_documento, arquivo_record_ids):
        self.ordem_chamadas.append('criar_ou_recuperar')
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
        self.ordem_chamadas.append('consultar_por_correlacao')
        return self._por_correlacao.get(acao_execucao_id)


def _preparar_documento(repositorio_documentos, armazenamento, *, documento_id, conteudo: bytes, nome_original='arquivo.pdf'):
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = Documento(
        documento_id=documento_id, arquivo_original='origem.pdf', nome_original=nome_original,
        mime_type='application/pdf', tamanho=len(conteudo), hash_sha256=hash_sha256, origem='teste',
        recebido_em=AGORA, lote_id=None, status=StatusDocumento.REGISTRADO,
        correlation_id='corr-1', criado_em=AGORA, atualizado_em=AGORA,
    )
    repositorio_documentos.salvar(documento)
    armazenamento.armazenar(hash_sha256, conteudo, documento.mime_type, documento.nome_original, documento.tamanho)
    return documento


def _colaborador(entidade_id='colab-1') -> ReferenciaCanonica:
    return ReferenciaCanonica('COLABORADOR', entidade_id)


def _necessidade(*, tipo_documental='HOLERITE', colaborador=None, cliente_id='cliente-1', competencia_id='2099-01'):
    return NecessidadeDocumentoPrestacao(
        cliente=ReferenciaCanonica('CLIENTE', cliente_id),
        competencia=ReferenciaCanonica('COMPETENCIA', competencia_id),
        tipo_documental=tipo_documental,
        motivo_exigencia='teste',
        colaborador=colaborador,
    )


def _resultado_aquisicao(documento, *, tipo_documental='HOLERITE', colaborador=None):
    return ResultadoAquisicaoPorNecessidade(
        necessidade=_necessidade(tipo_documental=tipo_documental, colaborador=colaborador),
        documento_id=documento.documento_id, hash_sha256=documento.hash_sha256,
    )


def _montar_dependencias():
    conexao = _Conexao()
    return {
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_autorizacoes': RepositorioAutorizacoesGateEmMemoria(),
        'repositorio_acoes': RepositorioAcoesExecucaoPlanoPostgres(conexao),
    }, conexao


# ---------------------------------------------------------------------
# Correlação colaborador/documento
# ---------------------------------------------------------------------

def test_correlacao_colaborador_preservada_ate_funcionario_id():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-holerite-1', conteudo=b'holerite-conteudo',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-42'))

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        mensagem_texto='Segue seu documento:',
    )

    assert ordem.funcionario_id == 'colab-42'
    assert ordem.documentos == (
        ItemDocumentoOrdem(documento_id='doc-holerite-1', hash_sha256=documento.hash_sha256),
    )


def test_colaborador_ausente_falha_fechado():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-sem-colaborador', conteudo=b'sem-colaborador',
    )
    resultado = _resultado_aquisicao(documento, colaborador=None)

    with pytest.raises(ColaboradorAusenteNaNecessidade):
        montar_ordem_distribuicao_documental_de_prestacao(
            resultados_aquisicao=(resultado,), destinatario='5511999999999',
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='FGTS',
            mensagem_texto='Segue seu documento:',
        )


def test_colaboradores_divergentes_falha_fechado():
    deps, _conexao = _montar_dependencias()
    doc_a = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-a', conteudo=b'conteudo-a',
    )
    doc_b = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-b', conteudo=b'conteudo-b',
    )
    resultado_a = _resultado_aquisicao(doc_a, tipo_documental='HOLERITE', colaborador=_colaborador('colab-1'))
    resultado_b = _resultado_aquisicao(doc_b, tipo_documental='FOLHA_PONTO', colaborador=_colaborador('colab-2'))

    with pytest.raises(ColaboradorDivergenteEntreDocumentos):
        montar_ordem_distribuicao_documental_de_prestacao(
            resultados_aquisicao=(resultado_a, resultado_b), destinatario='5511999999999',
            preset_id='PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA', tipo_documento='HOLERITE_FOLHA_PONTO',
            mensagem_texto='Seus documentos:',
        )


# ---------------------------------------------------------------------
# Presets -- preset_id -> política, tipo_documento sempre opaco
# ---------------------------------------------------------------------

def test_preset_documento_unitario_sem_assinatura_repassa_politica_correta():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-1',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador())

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
        mensagem_texto='Segue:',
    )
    assert ordem.canal == 'WHATSAPP'
    assert ordem.exigir_assinatura is False
    assert ordem.exigir_comprovante is False
    assert ordem.politica_agrupamento == 'UNITARIO'


def test_preset_documento_unitario_com_assinatura_repassa_politica_correta():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-1',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador())

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA', tipo_documento='CONTRATO',
        mensagem_texto='Assine:',
    )
    assert ordem.exigir_assinatura is True
    assert ordem.exigir_comprovante is True
    assert ordem.politica_agrupamento == 'UNITARIO'


def test_preset_pacote_2_documentos_1_link_repassa_politica_correta():
    deps, _conexao = _montar_dependencias()
    doc_holerite = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-holerite', conteudo=b'holerite',
    )
    doc_ponto = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-ponto', conteudo=b'ponto',
    )
    colaborador = _colaborador('colab-9')
    resultado_holerite = _resultado_aquisicao(doc_holerite, tipo_documental='HOLERITE', colaborador=colaborador)
    resultado_ponto = _resultado_aquisicao(doc_ponto, tipo_documental='FOLHA_PONTO', colaborador=colaborador)

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado_holerite, resultado_ponto), destinatario='5511999999999',
        preset_id='PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA', tipo_documento='HOLERITE_FOLHA_PONTO',
        mensagem_texto='Seus documentos do mês:',
    )
    assert len(ordem.documentos) == 2
    assert ordem.funcionario_id == 'colab-9'
    assert ordem.exigir_assinatura is True
    assert ordem.exigir_comprovante is True
    assert ordem.politica_agrupamento == 'AGRUPADO_1_LINK'
    assert ordem.tipo_documento == 'HOLERITE_FOLHA_PONTO'


def test_preset_desconhecido_falha_fechado():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-1',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador())

    with pytest.raises(PresetDistribuicaoDocumentalDesconhecido):
        montar_ordem_distribuicao_documental_de_prestacao(
            resultados_aquisicao=(resultado,), destinatario='5511999999999',
            preset_id='PRESET_QUE_NAO_EXISTE', tipo_documento='HOLERITE',
            mensagem_texto='Segue:',
        )


@pytest.mark.parametrize('tipo_documento', ['EPI', 'NR01'])
def test_tipos_documentais_arbitrarios_usam_mesmo_preset_sem_alteracao_de_codigo(tipo_documento):
    """Prova de genericidade: nenhum `if tipo_documento` neste módulo --
    qualquer tipo novo funciona com o preset compatível."""
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id=f'doc-{tipo_documento}', conteudo=f'conteudo-{tipo_documento}'.encode(),
    )
    resultado = _resultado_aquisicao(documento, tipo_documental=tipo_documento, colaborador=_colaborador())

    ordem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento=tipo_documento,
        mensagem_texto='Segue:',
    )
    assert ordem.tipo_documento == tipo_documento
    assert ordem.politica_agrupamento == 'UNITARIO'


def test_mesmo_tipo_documento_usa_presets_diferentes():
    """`CONTRATO` pode ir sem ou com assinatura -- a decisão vem do
    preset escolhido pelo chamador, nunca de um mapeamento fixo por
    tipo_documento."""
    deps, _conexao = _montar_dependencias()
    doc_sem = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-contrato-sem', conteudo=b'contrato-sem-assinatura',
    )
    doc_com = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-contrato-com', conteudo=b'contrato-com-assinatura',
    )
    colaborador = _colaborador()

    ordem_sem = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(_resultado_aquisicao(doc_sem, tipo_documental='CONTRATO', colaborador=colaborador),),
        destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
        tipo_documento='CONTRATO', mensagem_texto='Segue:',
    )
    ordem_com = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=(_resultado_aquisicao(doc_com, tipo_documental='CONTRATO', colaborador=colaborador),),
        destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA',
        tipo_documento='CONTRATO', mensagem_texto='Assine:',
    )

    assert ordem_sem.tipo_documento == ordem_com.tipo_documento == 'CONTRATO'
    assert ordem_sem.exigir_assinatura is False
    assert ordem_com.exigir_assinatura is True


# ---------------------------------------------------------------------
# Integração com o núcleo -- monta e repassa, nunca duplica
# ---------------------------------------------------------------------

def test_e2e_n1_sem_assinatura_chega_pending_reutilizando_nucleo():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-e2e-sem-assinatura',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-e2e'))

    resultado_distribuicao = materializar_prestacao_distribuicao_documental_shadow(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
        mensagem_texto='Segue:', materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    assert resultado_distribuicao.funcionario_id == 'colab-e2e'
    assert resultado_distribuicao.assinatura_link is None
    assert resultado_distribuicao.acao_persistida.acao_execucao_id == resultado_distribuicao.acao_execucao_id


def test_e2e_n1_com_assinatura_chega_pending_com_link_reutilizando_nucleo():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-e2e-com-assinatura',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-e2e'))
    porta_assinatura = _PortaAssinaturaFake()

    resultado_distribuicao = materializar_prestacao_distribuicao_documental_shadow(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_COM_ASSINATURA', tipo_documento='CONTRATO',
        mensagem_texto='Assine:', materializador=_MaterializadorFake(),
        porta_assinatura=porta_assinatura,
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    assert resultado_distribuicao.assinatura_link is not None
    # autorização SEMPRE antes da obrigação -- invariante do núcleo,
    # reconfirmada aqui na integração real deste wiring.
    assert porta_assinatura.ordem_chamadas[0] == 'consultar_por_correlacao'
    assert 'criar_ou_recuperar' in porta_assinatura.ordem_chamadas


def test_e2e_n2_pacote_holerite_folha_ponto_chega_pending_com_link_unico():
    deps, _conexao = _montar_dependencias()
    doc_holerite = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-holerite', conteudo=b'holerite-e2e',
    )
    doc_ponto = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-ponto', conteudo=b'ponto-e2e',
    )
    colaborador = _colaborador('colab-e2e-n2')
    resultados = (
        _resultado_aquisicao(doc_holerite, tipo_documental='HOLERITE', colaborador=colaborador),
        _resultado_aquisicao(doc_ponto, tipo_documental='FOLHA_PONTO', colaborador=colaborador),
    )

    resultado_distribuicao = materializar_prestacao_distribuicao_documental_shadow(
        resultados_aquisicao=resultados, destinatario='5511999999999',
        preset_id='PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA', tipo_documento='HOLERITE_FOLHA_PONTO',
        mensagem_texto='Seus documentos do mês:', materializador=_MaterializadorFake(),
        porta_assinatura=_PortaAssinaturaFake(),
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    assert len(resultado_distribuicao.arquivo_record_ids) == 2
    assert resultado_distribuicao.assinatura_link is not None
    assert resultado_distribuicao.funcionario_id == 'colab-e2e-n2'


def test_replay_idempotente_mesmo_event_id_sem_duplicar():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-replay',
    )
    resultado = _resultado_aquisicao(documento, colaborador=_colaborador('colab-replay'))
    kwargs = dict(
        resultados_aquisicao=(resultado,), destinatario='5511999999999',
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
        mensagem_texto='Segue:', materializador=None, porta_assinatura=None,
        ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
        **deps,
    )

    primeiro = materializar_prestacao_distribuicao_documental_shadow(**kwargs)
    segundo = materializar_prestacao_distribuicao_documental_shadow(**kwargs)

    assert primeiro.event_id == segundo.event_id
    assert primeiro.acao_execucao_id == segundo.acao_execucao_id
    assert len(_conexao.linhas) == 1


def test_documento_hash_divergente_propaga_erro_do_nucleo_sem_mascarar():
    deps, _conexao = _montar_dependencias()
    documento = _preparar_documento(
        deps['repositorio_documentos'], deps['armazenamento'],
        documento_id='doc-1', conteudo=b'conteudo-real',
    )
    resultado_com_hash_errado = ResultadoAquisicaoPorNecessidade(
        necessidade=_necessidade(colaborador=_colaborador()),
        documento_id=documento.documento_id, hash_sha256='0' * 64,
    )

    with pytest.raises(InconsistenciaOrdemDocumento):
        materializar_prestacao_distribuicao_documental_shadow(
            resultados_aquisicao=(resultado_com_hash_errado,), destinatario='5511999999999',
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='COMUNICADO',
            mensagem_texto='Segue:', materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_v1', instante=AGORA,
            **deps,
        )


def test_zero_import_de_transporte_ou_evolution_neste_wiring():
    """Checagem estrutural via AST (mesma técnica de
    `test_wiring_distribuicao_documental_shadow.py::
    test_modulo_nunca_importa_nem_chama_transporte_real`) -- imune a
    aliasing (`import requests as r`) ou uso indireto via atributo, ao
    contrário de uma busca textual simples."""
    import magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow as modulo
    caminho = modulo.__file__
    with open(caminho, 'r', encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=caminho)
    proibidos = {
        'requests', 'boto3', 'psycopg',
        'transporte_real_habilitado', 'compor_porta_execucao',
        'ExecutorEvolutionLegado', 'executar_plano_disparo',
        'gerar_token_reservado_csprng',
    }
    nomes_encontrados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes_encontrados.update(alias.name.split('.')[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            nomes_encontrados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.Name):
            nomes_encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes_encontrados.add(no.attr)
    assert proibidos.isdisjoint(nomes_encontrados)
