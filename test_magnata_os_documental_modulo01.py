"""
Testes do Modulo 01 (Documental) -- fundacao da esteira documental
central.

Tudo em memoria, sem I/O real -- nenhum destes testes acessa Airtable,
rede ou disco. Nenhum teste acessa atributos privados dos repositorios
(_por_id, _id_por_hash, _eventos) -- so os contratos publicos.
"""
import threading
import types
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.dominio import (
    Documento,
    StatusDocumento,
    TransicaoStatusInvalida,
    transicionar_status,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.servico_entrada import (
    ArquivoAusente,
    FalhaPersistencia,
    HashInvalido,
    ServicoEntradaDocumental,
)


def _servico(relogio=None, gerador_referencia_arquivo=None):
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    kwargs = {}
    if relogio is not None:
        kwargs['relogio'] = relogio
    if gerador_referencia_arquivo is not None:
        kwargs['gerador_referencia_arquivo'] = gerador_referencia_arquivo
    servico = ServicoEntradaDocumental(repo_docs, repo_hist, **kwargs)
    return servico, repo_docs, repo_hist


def _documento_de_teste(status):
    agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Documento(
        documento_id='doc-teste-1',
        arquivo_original='pendente-armazenamento://abc',
        nome_original='teste.pdf',
        mime_type='application/pdf',
        tamanho=100,
        hash_sha256='a' * 64,
        origem='upload_manual',
        recebido_em=agora,
        lote_id=None,
        status=status,
        correlation_id='corr-teste',
        criado_em=agora,
        atualizado_em=agora,
    )


class _HistoricoComFalhaControlada:
    """Test double: falha na N-esima chamada a registrar(), sucede nas
    demais. Usado para testar rollback em pontos especificos."""

    def __init__(self, falhar_na_chamada):
        self._falhar_na_chamada = falhar_na_chamada
        self._chamadas = 0
        self._eventos = []

    def registrar(self, evento):
        self._chamadas += 1
        if self._chamadas == self._falhar_na_chamada:
            raise RuntimeError(f'falha simulada na chamada numero {self._chamadas}')
        self._eventos.append(evento)

    def listar_por_documento(self, documento_id):
        return [e for e in self._eventos if e.documento_id == documento_id]

    def listar_todos(self):
        return list(self._eventos)


# ------------------------------------------------------ primeiro registro --

def test_primeiro_registro_cria_documento_registrado():
    servico, repo_docs, _ = _servico()

    documento = servico.registrar_entrada(
        conteudo=b'%PDF-1.4 conteudo de teste',
        nome_original='holerite_teste.pdf',
        mime_type='application/pdf',
        origem='upload_manual',
    )

    assert documento.status == StatusDocumento.REGISTRADO
    assert documento.nome_original == 'holerite_teste.pdf'
    assert documento.mime_type == 'application/pdf'
    assert documento.origem == 'upload_manual'
    assert documento.tamanho == len(b'%PDF-1.4 conteudo de teste')
    assert len(documento.hash_sha256) == 64
    assert documento.documento_id
    assert repo_docs.buscar_por_id(documento.documento_id) == documento
    assert repo_docs.listar_todos() == [documento]


def test_documentos_com_conteudo_diferente_recebem_ids_diferentes():
    servico, _, _ = _servico()
    doc1 = servico.registrar_entrada(b'conteudo A', 'a.pdf', 'application/pdf', 'upload_manual')
    doc2 = servico.registrar_entrada(b'conteudo B', 'b.pdf', 'application/pdf', 'upload_manual')
    assert doc1.documento_id != doc2.documento_id
    assert doc1.hash_sha256 != doc2.hash_sha256


# --------------------------------------------------------- status inicial --

def test_status_iniciais_definidos_corretamente():
    esperados = {
        'RECEBIDO', 'REGISTRADO', 'DUPLICADO', 'AGUARDANDO_PROCESSAMENTO',
        'EM_PROCESSAMENTO', 'EM_REVISAO', 'ERRO',
    }
    valores_reais = {s.value for s in StatusDocumento}
    assert valores_reais == esperados


# --------------------------------------------------------- maquina de estados --

def test_transicao_valida_recebido_para_registrado():
    documento = _documento_de_teste(StatusDocumento.RECEBIDO)
    quando = datetime(2026, 2, 1, tzinfo=timezone.utc)
    novo = transicionar_status(documento, StatusDocumento.REGISTRADO, quando)
    assert novo.status == StatusDocumento.REGISTRADO
    assert novo.atualizado_em == quando
    assert documento.status == StatusDocumento.RECEBIDO  # original nunca mutado


def test_transicao_invalida_levanta_erro():
    documento = _documento_de_teste(StatusDocumento.REGISTRADO)
    with pytest.raises(TransicaoStatusInvalida):
        transicionar_status(documento, StatusDocumento.RECEBIDO, datetime.now(timezone.utc))


def test_transicao_para_o_mesmo_status_e_invalida():
    documento = _documento_de_teste(StatusDocumento.RECEBIDO)
    with pytest.raises(TransicaoStatusInvalida):
        transicionar_status(documento, StatusDocumento.RECEBIDO, datetime.now(timezone.utc))


def test_transicao_a_partir_de_estado_terminal_e_invalida():
    documento = _documento_de_teste(StatusDocumento.DUPLICADO)
    with pytest.raises(TransicaoStatusInvalida):
        transicionar_status(documento, StatusDocumento.REGISTRADO, datetime.now(timezone.utc))


# ------------------------------------------------------------ imutabilidade --

def test_evento_historico_detalhes_e_imutavel():
    servico, _, repo_hist = _servico()
    documento = servico.registrar_entrada(
        b'conteudo imutavel', 'a.pdf', 'application/pdf', 'upload_manual',
    )
    evento = repo_hist.listar_por_documento(documento.documento_id)[0]
    assert isinstance(evento.detalhes, types.MappingProxyType)
    with pytest.raises(TypeError):
        evento.detalhes['nome_original'] = 'alterado'


# ------------------------------------------------------ duplicidade/hash --

def test_duplicidade_por_hash_retorna_documento_existente():
    servico, repo_docs, repo_hist = _servico()

    original = servico.registrar_entrada(
        b'mesmo conteudo binario', 'original.pdf', 'application/pdf', 'upload_manual',
    )
    tentativa = servico.registrar_entrada(
        b'mesmo conteudo binario', 'nome_diferente.pdf', 'application/pdf', 'email_webhook',
    )

    assert tentativa.documento_id == original.documento_id
    assert tentativa == original
    assert repo_docs.listar_todos() == [original]  # so 1 Documento persistido no total

    eventos = repo_hist.listar_por_documento(original.documento_id)
    tipos_evento = [e.evento for e in eventos]
    assert tipos_evento.count('TENTATIVA_DUPLICADA') == 1
    evento_dup = next(e for e in eventos if e.evento == 'TENTATIVA_DUPLICADA')
    assert evento_dup.detalhes['nome_original_tentativa'] == 'nome_diferente.pdf'
    assert evento_dup.detalhes['origem_tentativa'] == 'email_webhook'


def test_idempotencia_multiplas_tentativas_preserva_documento_original():
    servico, repo_docs, _ = _servico()

    primeiro = servico.registrar_entrada(b'conteudo estavel', 'v1.pdf', 'application/pdf', 'upload_manual')
    for i in range(5):
        repetido = servico.registrar_entrada(
            b'conteudo estavel', f'v{i}.pdf', 'application/pdf', f'origem_{i}',
        )
        assert repetido == primeiro

    assert repo_docs.listar_todos() == [primeiro]
    assert repo_docs.buscar_por_id(primeiro.documento_id).nome_original == 'v1.pdf'


# -------------------------------------------------------------- historico --

def test_historico_registra_eventos_na_ordem_correta():
    momento = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    servico, _, repo_hist = _servico(relogio=lambda: momento)

    documento = servico.registrar_entrada(
        b'conteudo para historico', 'holerite.pdf', 'application/pdf', 'upload_manual',
        correlation_id='corr-fixo-123',
    )

    eventos = repo_hist.listar_por_documento(documento.documento_id)
    assert [e.evento for e in eventos] == ['DOCUMENTO_RECEBIDO', 'DOCUMENTO_REGISTRADO']

    recebido, registrado = eventos
    assert recebido.status_anterior is None
    assert recebido.status_novo == StatusDocumento.RECEBIDO
    assert registrado.status_anterior == StatusDocumento.RECEBIDO
    assert registrado.status_novo == StatusDocumento.REGISTRADO
    assert recebido.timestamp == momento
    assert registrado.timestamp == momento
    for e in eventos:
        assert e.correlation_id == 'corr-fixo-123'
        assert e.documento_id == documento.documento_id


# ----------------------------------------------------------------- erros --

def test_registrar_entrada_com_arquivo_ausente_levanta_erro():
    servico, repo_docs, repo_hist = _servico()

    with pytest.raises(ArquivoAusente):
        servico.registrar_entrada(b'', 'vazio.pdf', 'application/pdf', 'upload_manual')

    assert repo_docs.listar_todos() == []
    assert repo_hist.listar_todos() == []


def test_consultar_por_hash_invalido_levanta_erro():
    servico, _, _ = _servico()

    with pytest.raises(HashInvalido):
        servico.consultar_por_hash('isso-nao-e-um-sha256')

    with pytest.raises(HashInvalido):
        servico.consultar_por_hash('')


def test_consultar_por_hash_valido_nao_registrado_retorna_none():
    servico, _, _ = _servico()
    hash_valido_mas_desconhecido = 'a' * 64
    assert servico.consultar_por_hash(hash_valido_mas_desconhecido) is None


def test_falha_na_criacao_atomica_propaga_como_falha_persistencia():
    class RepositorioQueFalhaNaCriacao:
        def buscar_por_hash(self, hash_sha256):
            return None

        def buscar_por_id(self, documento_id):
            return None

        def salvar(self, documento):
            pass

        def salvar_se_ausente_por_hash(self, hash_sha256, fabricar_documento):
            raise RuntimeError('Airtable indisponivel (simulado)')

        def remover(self, documento_id):
            pass

        def listar_todos(self):
            return []

    repo_hist = RepositorioHistoricoEmMemoria()
    servico = ServicoEntradaDocumental(RepositorioQueFalhaNaCriacao(), repo_hist)

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo qualquer', 'x.pdf', 'application/pdf', 'upload_manual')

    assert repo_hist.listar_todos() == []


# -------------------------- falha de historico: 1o, 2o e 3o evento --------
# Comportamento oficial: o Documento NUNCA e removido quando o registro
# do historico falha. Ele permanece persistido, transicionado para ERRO,
# e um evento FALHA_REGISTRO_HISTORICO e registrado quando possivel --
# nunca fica um EventoHistorico apontando para um documento_id inexistente,
# porque nada remove Documento nesta fase.

def test_falha_no_primeiro_evento_historico_mantem_documento_marcado_erro():
    """1o evento = DOCUMENTO_RECEBIDO, na criacao de um Documento novo."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=1)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo falha 1', 'x.pdf', 'application/pdf', 'upload_manual')

    documentos = repo_docs.listar_todos()
    assert len(documentos) == 1  # documento preservado, nao removido
    assert documentos[0].status == StatusDocumento.ERRO

    eventos = repo_hist.listar_todos()
    assert [e.evento for e in eventos] == ['FALHA_REGISTRO_HISTORICO']
    assert eventos[0].documento_id == documentos[0].documento_id
    assert eventos[0].detalhes['evento_que_falhou'] == 'DOCUMENTO_RECEBIDO'
    assert 'falha simulada' in eventos[0].detalhes['causa']


def test_falha_no_segundo_evento_historico_mantem_documento_marcado_erro():
    """2o evento = DOCUMENTO_REGISTRADO, apos o 1o (DOCUMENTO_RECEBIDO) ja
    ter tido sucesso. O evento bem-sucedido permanece; o Documento e
    preservado e marcado ERRO."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=2)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo falha 2', 'y.pdf', 'application/pdf', 'upload_manual')

    documentos = repo_docs.listar_todos()
    assert len(documentos) == 1
    assert documentos[0].status == StatusDocumento.ERRO

    eventos = repo_hist.listar_todos()
    assert [e.evento for e in eventos] == ['DOCUMENTO_RECEBIDO', 'FALHA_REGISTRO_HISTORICO']
    assert eventos[1].detalhes['evento_que_falhou'] == 'DOCUMENTO_REGISTRADO'


# ------------- falha na auditoria de TENTATIVA_DUPLICADA (caso especial) --
# Ao contrario da falha em DOCUMENTO_RECEBIDO/DOCUMENTO_REGISTRADO, uma
# falha ao registrar TENTATIVA_DUPLICADA e falha em AUDITAR um reenvio,
# nao no Documento em si -- o Documento existente e valido e ja
# confirmado, e nunca deve ser degradado por causa disso.

def test_falha_em_tentativa_duplicada_documento_registrado_continua_registrado():
    """1: Documento REGISTRADO + falha em TENTATIVA_DUPLICADA -> continua
    REGISTRADO (nunca vai para ERRO)."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=3)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    original = servico.registrar_entrada(b'conteudo falha dup', 'z1.pdf', 'application/pdf', 'upload_manual')
    assert original.status == StatusDocumento.REGISTRADO

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo falha dup', 'z2.pdf', 'application/pdf', 'upload_manual')

    documentos = repo_docs.listar_todos()
    assert len(documentos) == 1  # nenhum documento novo criado, nenhum removido
    assert documentos[0].documento_id == original.documento_id
    assert documentos[0].status == StatusDocumento.REGISTRADO  # NAO foi para ERRO


def test_falha_em_tentativa_duplicada_nao_altera_nenhum_campo_do_documento():
    """2: campos do Documento permanecem inalterados, inclusive
    atualizado_em -- self._documentos.salvar() nunca e chamado neste
    caminho de falha."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=3)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    original = servico.registrar_entrada(b'conteudo falha dup campos', 'w1.pdf', 'application/pdf', 'upload_manual')

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(
            b'conteudo falha dup campos', 'w2.pdf', 'application/pdf', 'outra_origem_tentativa',
        )

    documento_apos = repo_docs.buscar_por_id(original.documento_id)
    assert documento_apos == original  # identico em todos os campos, inclusive atualizado_em


def test_falha_em_tentativa_duplicada_levanta_falha_persistencia():
    """3: FalhaPersistencia e levantada, com a causa original preservada."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=3)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    servico.registrar_entrada(b'conteudo falha dup excecao', 'v1.pdf', 'application/pdf', 'upload_manual')

    with pytest.raises(FalhaPersistencia) as exc_info:
        servico.registrar_entrada(b'conteudo falha dup excecao', 'v2.pdf', 'application/pdf', 'upload_manual')

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert 'falha simulada' in str(exc_info.value.__cause__)


def test_falha_em_tentativa_duplicada_registra_falha_registro_historico_com_contexto():
    """FALHA_REGISTRO_HISTORICO e registrado em best-effort, informando
    que a falha ocorreu numa tentativa duplicada."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=3)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    original = servico.registrar_entrada(b'conteudo falha dup evento', 'u1.pdf', 'application/pdf', 'upload_manual')

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo falha dup evento', 'u2.pdf', 'application/pdf', 'upload_manual')

    eventos = repo_hist.listar_todos()
    assert [e.evento for e in eventos] == [
        'DOCUMENTO_RECEBIDO', 'DOCUMENTO_REGISTRADO', 'FALHA_REGISTRO_HISTORICO',
    ]
    evento_falha = eventos[-1]
    assert evento_falha.documento_id == original.documento_id
    assert evento_falha.detalhes['evento_que_falhou'] == 'TENTATIVA_DUPLICADA'
    assert evento_falha.detalhes['contexto'] == 'falha_auditoria_de_duplicidade'
    assert evento_falha.status_anterior == StatusDocumento.REGISTRADO
    assert evento_falha.status_novo == StatusDocumento.REGISTRADO  # nao mudou


def test_falha_em_tentativa_duplicada_nao_gera_eventos_orfaos():
    """4: nao existem eventos orfaos apos falha na auditoria de duplicidade."""
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=3)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    servico.registrar_entrada(b'conteudo falha dup orfao', 't1.pdf', 'application/pdf', 'upload_manual')
    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo falha dup orfao', 't2.pdf', 'application/pdf', 'upload_manual')

    _assert_sem_eventos_orfaos(repo_docs, repo_hist)


def test_falha_de_historico_preserva_correlation_id_da_tentativa():
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=1)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(
            b'conteudo falha correlation', 'c.pdf', 'application/pdf', 'upload_manual',
            correlation_id='corr-da-falha-123',
        )

    eventos = repo_hist.listar_todos()
    assert eventos[0].correlation_id == 'corr-da-falha-123'


def _assert_sem_eventos_orfaos(repo_docs, repo_hist):
    ids_existentes = {d.documento_id for d in repo_docs.listar_todos()}
    for evento in repo_hist.listar_todos():
        assert evento.documento_id in ids_existentes, (
            f'evento {evento.evento} aponta para documento_id inexistente: {evento.documento_id}'
        )


def test_nenhum_evento_historico_aponta_para_documento_inexistente():
    """Confirma a invariante em 4 cenarios independentes (sucesso normal,
    falha no 1o, no 2o e no 3o evento de historico): todo
    EventoHistorico.documento_id corresponde a um Documento que de fato
    existe no repositorio -- nunca um evento orfao."""
    # sucesso normal
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico.registrar_entrada(b'conteudo orfao sucesso', 'a.pdf', 'application/pdf', 'upload_manual')
    _assert_sem_eventos_orfaos(repo_docs, repo_hist)

    # falha no 1o evento (DOCUMENTO_RECEBIDO)
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=1)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)
    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo orfao falha1', 'b.pdf', 'application/pdf', 'upload_manual')
    _assert_sem_eventos_orfaos(repo_docs, repo_hist)

    # falha no 2o evento (DOCUMENTO_REGISTRADO)
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=2)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)
    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo orfao falha2', 'c.pdf', 'application/pdf', 'upload_manual')
    _assert_sem_eventos_orfaos(repo_docs, repo_hist)

    # falha no 3o evento (TENTATIVA_DUPLICADA, apos 1o registro ok)
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = _HistoricoComFalhaControlada(falhar_na_chamada=3)
    servico = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico.registrar_entrada(b'conteudo orfao falha3', 'd1.pdf', 'application/pdf', 'upload_manual')
    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo orfao falha3', 'd2.pdf', 'application/pdf', 'upload_manual')
    _assert_sem_eventos_orfaos(repo_docs, repo_hist)


# ------------------------------------------------------------ correlation_id --

def test_correlation_id_fornecido_e_propagado():
    servico, _, repo_hist = _servico()
    documento = servico.registrar_entrada(
        b'conteudo com correlation', 'x.pdf', 'application/pdf', 'upload_manual',
        correlation_id='corr-explicito-abc',
    )
    assert documento.correlation_id == 'corr-explicito-abc'
    eventos = repo_hist.listar_por_documento(documento.documento_id)
    assert all(e.correlation_id == 'corr-explicito-abc' for e in eventos)


def test_correlation_id_gerado_automaticamente_quando_ausente():
    servico, _, _ = _servico()
    documento = servico.registrar_entrada(
        b'conteudo sem correlation explicito', 'y.pdf', 'application/pdf', 'upload_manual',
    )
    assert documento.correlation_id
    assert documento.correlation_id.startswith('doc')


def test_correlation_id_diferente_por_tentativa_duplicada():
    servico, _, repo_hist = _servico()
    original = servico.registrar_entrada(
        b'conteudo repetido', 'a.pdf', 'application/pdf', 'upload_manual',
        correlation_id='corr-original',
    )
    servico.registrar_entrada(
        b'conteudo repetido', 'a.pdf', 'application/pdf', 'upload_manual',
        correlation_id='corr-tentativa-2',
    )
    eventos = repo_hist.listar_por_documento(original.documento_id)
    correlations = [e.correlation_id for e in eventos]
    assert 'corr-original' in correlations
    assert 'corr-tentativa-2' in correlations


# ------------------------------------------------------ referencia de arquivo --

def test_gerador_referencia_arquivo_e_injetavel():
    chamadas = []

    def gerador_customizado(hash_sha256):
        chamadas.append(hash_sha256)
        return f'meu-storage://{hash_sha256}'

    servico, _, _ = _servico(gerador_referencia_arquivo=gerador_customizado)
    documento = servico.registrar_entrada(
        b'conteudo referencia', 'r.pdf', 'application/pdf', 'upload_manual',
    )

    assert documento.arquivo_original == f'meu-storage://{documento.hash_sha256}'
    assert chamadas == [documento.hash_sha256]


def test_referencia_arquivo_padrao_e_provisoria_baseada_no_hash():
    servico, _, _ = _servico()
    documento = servico.registrar_entrada(
        b'conteudo referencia padrao', 'p.pdf', 'application/pdf', 'upload_manual',
    )
    assert documento.arquivo_original == f'pendente-armazenamento://{documento.hash_sha256}'


# ----------------------------------------------------------------- concorrencia --

def test_concorrencia_multiplas_threads_mesmo_arquivo_cria_um_unico_documento():
    servico, repo_docs, repo_hist = _servico()
    conteudo = b'conteudo identico registrado por varias threads ao mesmo tempo'
    n_threads = 20
    barreira = threading.Barrier(n_threads)
    resultados = []
    erros = []
    lock_resultados = threading.Lock()

    def _tentar_registrar(indice):
        try:
            barreira.wait(timeout=5)
            doc = servico.registrar_entrada(
                conteudo, f'arquivo_{indice}.pdf', 'application/pdf', f'origem_{indice}',
            )
            with lock_resultados:
                resultados.append(doc)
        except Exception as exc:  # nao esperado -- registrado para diagnostico do teste
            with lock_resultados:
                erros.append(exc)

    threads = [threading.Thread(target=_tentar_registrar, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert erros == []
    assert len(resultados) == n_threads

    ids_unicos = {doc.documento_id for doc in resultados}
    assert len(ids_unicos) == 1  # um unico documento_id entre todas as chamadas

    todos_documentos = repo_docs.listar_todos()
    assert len(todos_documentos) == 1  # nenhuma estrutura orfa

    documento_id_final = next(iter(ids_unicos))
    eventos = repo_hist.listar_por_documento(documento_id_final)
    tipos = [e.evento for e in eventos]
    assert tipos.count('DOCUMENTO_RECEBIDO') == 1
    assert tipos.count('DOCUMENTO_REGISTRADO') == 1
    assert tipos.count('TENTATIVA_DUPLICADA') == n_threads - 1  # todas as demais registradas
