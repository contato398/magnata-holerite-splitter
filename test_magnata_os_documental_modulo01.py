"""
Testes do Modulo 01 (Documental) -- fundacao da esteira documental
central.

Tudo em memoria, sem I/O real -- nenhum destes testes acessa Airtable,
rede ou disco.
"""
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.dominio import StatusDocumento
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


def _relogio_fixo(sequencia):
    """Devolve um relogio de teste que avanca 1 segundo a cada chamada,
    a partir de uma lista de datetimes pre-definida (para testar ordem)."""
    it = iter(sequencia)
    return lambda: next(it)


def _servico(relogio=None):
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    kwargs = {}
    if relogio is not None:
        kwargs['relogio'] = relogio
    servico = ServicoEntradaDocumental(repo_docs, repo_hist, **kwargs)
    return servico, repo_docs, repo_hist


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
    assert tentativa == original  # nao foi criada uma segunda instancia com dado diferente
    assert len(repo_docs._por_id) == 1  # so 1 Documento persistido no total

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
        assert repetido == primeiro  # sempre devolve exatamente o mesmo, nunca sobrescreve

    assert len(repo_docs._por_id) == 1
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

    assert repo_docs._por_id == {}
    assert repo_hist._eventos == []


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


def test_falha_de_persistencia_propaga_erro_e_nao_registra_historico_falso():
    class RepositorioQueFalha:
        def buscar_por_hash(self, hash_sha256):
            return None

        def buscar_por_id(self, documento_id):
            return None

        def salvar(self, documento):
            raise RuntimeError('Airtable indisponivel (simulado)')

    repo_docs_falho = RepositorioQueFalha()
    repo_hist = RepositorioHistoricoEmMemoria()
    servico = ServicoEntradaDocumental(repo_docs_falho, repo_hist)

    with pytest.raises(FalhaPersistencia):
        servico.registrar_entrada(b'conteudo qualquer', 'x.pdf', 'application/pdf', 'upload_manual')

    # nenhum evento de sucesso foi registrado -- a falha nao foi mascarada
    assert repo_hist._eventos == []


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
    assert documento.correlation_id  # nao vazio
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
