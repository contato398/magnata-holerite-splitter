"""Distribuição Documental Genérica V1: Ordem -> Preview -> Autorização
-> Obrigação (opcional) -> PlanoDisparo -> Envelope -> AcaoEnvio PENDING.

Sempre sem transporte real, sempre sem Airtable/Evolution real -- prova a
composição para QUALQUER Documento canônico (holerite, ponto, contrato,
EPI, NR, rescisão etc.), nunca um `if` por tipo_documento no núcleo.
"""
import ast
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
from magnata_os.documental.modulo01.materializador_arquivo import (
    AmbiguidadeMaterializacao,
    OwnerAusenteMaterializacao,
    ResultadoMaterializacao,
)
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    DocumentoAusenteNaOrdem,
    DistribuicaoDocumentalError,
    InconsistenciaOrdemDocumento,
    ItemDocumentoOrdem,
    LinkObrigacaoAssinaturaMalformado,
    OrdemDistribuicaoDocumental,
    PoliticaAgrupamentoNaoSuportada,
    derivar_identidade_ordem_distribuicao,
    materializar_distribuicao_documental_shadow,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------
# Fakes reutilizando implementações em memória já existentes onde
# possível (RepositorioDocumentosEmMemoria, ArmazenamentoArquivosEmMemoria,
# RepositorioAutorizacoesGateEmMemoria) -- só o que não existe é fake
# aqui: MaterializadorArquivoLegado e PortaObrigacaoAssinatura
# (dependem de Airtable/HTTP real fora de teste) e a conexão DB-API do
# repositório de ações (mesmo padrão já usado em
# test_wiring_assinatura_comunicacao_shadow.py, com estado persistente
# entre chamadas para exercitar o ON CONFLICT DO NOTHING de verdade).
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
            colunas_valores = params[:-4]  # últimos 4 params são o WHERE do gate (autorizacao_id/event_id/preview_id/decisao)
            acao_execucao_id = colunas_valores[0]
            if acao_execucao_id in self.conexao.linhas:
                self._ultimo = None  # ON CONFLICT DO NOTHING
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
    """Fake em memória de MaterializadorArquivoLegado -- idempotente por
    (documento.hash_sha256, funcionario_id), como o adapter real."""

    def __init__(self, falha: Exception = None):
        self.chamadas = 0
        self._por_chave = {}
        self._falha = falha

    def materializar(self, *, documento: Documento, conteudo_bytes: bytes, funcionario_id: str) -> ResultadoMaterializacao:
        self.chamadas += 1
        if self._falha is not None:
            raise self._falha
        chave = (documento.hash_sha256, funcionario_id)
        if chave in self._por_chave:
            return dataclasses_replace_reutilizado(self._por_chave[chave])
        resultado = ResultadoMaterializacao(
            arquivo_record_id=f'recARQ{len(self._por_chave) + 1}',
            documento_id=documento.documento_id, funcionario_id=funcionario_id,
            hash_sha256=documento.hash_sha256, reutilizado=False,
        )
        self._por_chave[chave] = resultado
        return resultado


def dataclasses_replace_reutilizado(resultado: ResultadoMaterializacao) -> ResultadoMaterializacao:
    import dataclasses
    return dataclasses.replace(resultado, reutilizado=True)


class _PortaAssinaturaFake:
    """Fake em memória, estado persistente entre chamadas -- prova
    idempotência de replay de verdade (não só "nunca deveria consultar",
    como o fake do outro arquivo de teste)."""

    def __init__(self):
        self._por_correlacao: dict = {}
        self.chamadas_criar = []
        self.ordem_chamadas: list = []

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id, funcionario_id, tipo_documento, arquivo_record_ids):
        self.ordem_chamadas.append('criar_ou_recuperar')
        self.chamadas_criar.append((token_reservado, acao_execucao_id, arquivo_record_ids, tipo_documento))
        existente = self._por_correlacao.get(acao_execucao_id)
        if existente is not None:
            token_existente = existente.link.rsplit('/', 1)[-1]
            if token_existente != token_reservado:
                # Mesmo comportamento do motor legado real:
                # `_resolver_obrigacao_reservada_existente` (app.py)
                # devolve 409 conflito_token_mesma_obrigacao quando o
                # token não bate com o já persistido sob a MESMA
                # correlação -- aqui simulado como exceção genérica,
                # igual ao que `ObrigacaoAssinaturaLegadoError` faria.
                raise RuntimeError('conflito_token_mesma_obrigacao (simulado)')
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


def _documento(documento_id='doc-1', hash_sha256='a' * 64, nome_original='arquivo.pdf', tamanho=100) -> Documento:
    return Documento(
        documento_id=documento_id, arquivo_original='origem.pdf', nome_original=nome_original,
        mime_type='application/pdf', tamanho=tamanho, hash_sha256=hash_sha256, origem='teste',
        recebido_em=AGORA, lote_id=None, status=StatusDocumento.REGISTRADO,
        correlation_id='corr-1', criado_em=AGORA, atualizado_em=AGORA,
    )


def _preparar_documento(repositorio_documentos, armazenamento, *, documento_id, conteudo: bytes, nome_original='arquivo.pdf'):
    import hashlib
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento(documento_id=documento_id, hash_sha256=hash_sha256, nome_original=nome_original, tamanho=len(conteudo))
    repositorio_documentos.salvar(documento)
    armazenamento.armazenar(hash_sha256, conteudo, documento.mime_type, documento.nome_original, documento.tamanho)
    return documento


def _montar_dependencias():
    return {
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_autorizacoes': RepositorioAutorizacoesGateEmMemoria(),
        'repositorio_acoes': RepositorioAcoesExecucaoPlanoPostgres(_Conexao()),
    }


def _ordem_generica(*, documentos, funcionario_id='recFUNC1', tipo_documento='CONTRATO',
                     exigir_assinatura=False, exigir_comprovante=False,
                     politica_agrupamento='UNITARIO', mensagem_texto='Segue seu documento:'):
    return OrdemDistribuicaoDocumental(
        documentos=documentos, funcionario_id=funcionario_id, destinatario='5511999999999',
        canal='whatsapp', preset_id='preset-teste', tipo_documento=tipo_documento,
        exigir_assinatura=exigir_assinatura, exigir_comprovante=exigir_comprovante,
        politica_agrupamento=politica_agrupamento, mensagem_texto=mensagem_texto,
    )


# ---------------------------------------------------------------------
# 1. N=1 com assinatura
# ---------------------------------------------------------------------

def test_n1_com_assinatura_fecha_ate_pending_com_link():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-holerite', conteudo=b'PDF-HOLERITE')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True, exigir_comprovante=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()
    resultado = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    assert resultado.assinatura_link is not None
    assert resultado.arquivo_record_ids == ('recARQ1',)
    assert materializador.chamadas == 1
    assert len(porta.chamadas_criar) == 1


# ---------------------------------------------------------------------
# 2. N=1 sem assinatura
# ---------------------------------------------------------------------

def test_n1_sem_assinatura_fecha_ate_pending_sem_obrigacao():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-comprovante', conteudo=b'PDF-COMPROVANTE')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='COMPROVANTE', exigir_assinatura=False,
    )
    resultado = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=None, porta_assinatura=None,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    assert resultado.assinatura_link is None
    assert resultado.arquivo_record_ids == ()


# ---------------------------------------------------------------------
# 3. N=2 legado Holerite+Ponto com 1 link
# ---------------------------------------------------------------------

def test_n2_holerite_folha_ponto_agrupado_1_link():
    deps = _montar_dependencias()
    doc_holerite = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                        documento_id='doc-holerite', conteudo=b'PDF-HOLERITE')
    doc_ponto = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-ponto', conteudo=b'PDF-PONTO')
    ordem = _ordem_generica(
        documentos=(
            ItemDocumentoOrdem(doc_holerite.documento_id, doc_holerite.hash_sha256),
            ItemDocumentoOrdem(doc_ponto.documento_id, doc_ponto.hash_sha256),
        ),
        tipo_documento='HOLERITE_FOLHA_PONTO', exigir_assinatura=True, exigir_comprovante=True,
        politica_agrupamento='AGRUPADO_1_LINK',
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()
    resultado = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    assert len(resultado.arquivo_record_ids) == 2
    assert resultado.assinatura_link is not None
    assert len(porta.chamadas_criar) == 1  # 1 link só, cobrindo os 2 documentos


# ---------------------------------------------------------------------
# 4/5. Documento genérico não-Holerite (contrato/EPI/NR) -- mesmo núcleo
# ---------------------------------------------------------------------

@pytest.mark.parametrize('tipo_documento,exigir_assinatura', [
    ('CONTRATO_EXPERIENCIA', True),
    ('FICHA_EPI', False),
    ('NR01', True),
])
def test_tipos_documentais_diversos_usam_o_mesmo_nucleo_sem_codigo_especial(tipo_documento, exigir_assinatura):
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id=f'doc-{tipo_documento}', conteudo=f'PDF-{tipo_documento}'.encode())
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento=tipo_documento, exigir_assinatura=exigir_assinatura,
    )
    materializador = _MaterializadorFake() if exigir_assinatura else None
    porta = _PortaAssinaturaFake() if exigir_assinatura else None
    resultado = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    assert resultado.acao_execucao_id


# ---------------------------------------------------------------------
# 6/7. Replay 3x -- 1 token, 1 obrigação, 1 link, 1 ação, 1 envelope
# ---------------------------------------------------------------------

def test_replay_3x_com_assinatura_produz_identidade_unica():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-replay', conteudo=b'PDF-REPLAY')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True, exigir_comprovante=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()

    resultados = [
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=materializador, porta_assinatura=porta,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )
        for _ in range(3)
    ]

    event_ids = {r.event_id for r in resultados}
    acao_ids = {r.acao_execucao_id for r in resultados}
    links = {r.assinatura_link for r in resultados}
    assert len(event_ids) == 1
    assert len(acao_ids) == 1
    assert len(links) == 1
    assert len(porta.chamadas_criar) == 1  # token/obrigação criados só na 1a execução
    assert len(deps['repositorio_acoes']._conexao.linhas) == 1  # 1 única linha em acoes_execucao_plano


def test_replay_normal_consulta_por_A_e_nunca_gera_segundo_token(monkeypatch):
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-token-unico', conteudo=b'PDF-TOKEN')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()

    chamadas_token = []
    import magnata_os.orquestrador.wiring_distribuicao_documental_shadow as mod
    original = mod.gerar_token_reservado_csprng

    def _contador():
        chamadas_token.append(1)
        return original()

    monkeypatch.setattr(mod, 'gerar_token_reservado_csprng', _contador)

    for _ in range(3):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=materializador, porta_assinatura=porta,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )
    assert len(chamadas_token) == 1


# ---------------------------------------------------------------------
# 8. Nenhuma obrigação antes da autorização
# ---------------------------------------------------------------------

def test_criar_ou_recuperar_nunca_antes_da_autorizacao(monkeypatch):
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-ordem-efeitos', conteudo=b'PDF-ORDEM')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()

    ordem_de_chamadas = []
    import magnata_os.orquestrador.wiring_distribuicao_documental_shadow as mod
    original_autorizar = mod.autorizar_preview_assinatura_shadow

    def _autorizar_rastreado(**kwargs):
        ordem_de_chamadas.append('autorizar_preview')
        return original_autorizar(**kwargs)

    monkeypatch.setattr(mod, 'autorizar_preview_assinatura_shadow', _autorizar_rastreado)
    original_criar = porta.criar_ou_recuperar

    def _criar_rastreado(**kwargs):
        ordem_de_chamadas.append('criar_ou_recuperar')
        return original_criar(**kwargs)

    porta.criar_ou_recuperar = _criar_rastreado

    materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    assert ordem_de_chamadas.index('autorizar_preview') < ordem_de_chamadas.index('criar_ou_recuperar')


# ---------------------------------------------------------------------
# 9. Falha entre autorização e obrigação -> replay gera novo preview
# ---------------------------------------------------------------------

def test_falha_apos_autorizacao_antes_da_obrigacao_exige_nova_autorizacao(monkeypatch):
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-falha-parcial', conteudo=b'PDF-FALHA')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()

    import magnata_os.orquestrador.wiring_distribuicao_documental_shadow as mod
    original = porta.criar_ou_recuperar

    def _falha(**kwargs):
        raise RuntimeError('falha simulada entre autorizacao e obrigacao')

    porta.criar_ou_recuperar = _falha
    with pytest.raises(RuntimeError):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=materializador, porta_assinatura=porta,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )
    autorizacoes_apos_falha = len(deps['repositorio_autorizacoes']._dados)

    porta.criar_ou_recuperar = original
    resultado = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    autorizacoes_apos_replay = len(deps['repositorio_autorizacoes']._dados)
    assert autorizacoes_apos_replay > autorizacoes_apos_falha  # nova autorização, preview novo (token novo)
    assert resultado.assinatura_link is not None


# ---------------------------------------------------------------------
# 10/11. Documento ausente / hash divergente
# ---------------------------------------------------------------------

def test_documento_ausente_no_repositorio_falha_fechado():
    deps = _montar_dependencias()
    ordem = _ordem_generica(documentos=(ItemDocumentoOrdem('doc-inexistente', 'a' * 64),))
    with pytest.raises(DocumentoAusenteNaOrdem):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=None, porta_assinatura=None,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )


def test_hash_divergente_entre_ordem_e_documento_canonico_falha_fechado():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-hash-divergente', conteudo=b'PDF-X')
    ordem = _ordem_generica(documentos=(ItemDocumentoOrdem(documento.documento_id, 'f' * 64),))
    with pytest.raises(InconsistenciaOrdemDocumento):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=None, porta_assinatura=None,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )


# ---------------------------------------------------------------------
# 12. Ownership divergente/ausente bloqueia a operação inteira
# ---------------------------------------------------------------------

def test_ownership_ausente_no_materializador_bloqueia_toda_a_operacao():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-owner-ausente', conteudo=b'PDF-OWNER')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake(falha=OwnerAusenteMaterializacao('owner ausente'))
    porta = _PortaAssinaturaFake()
    with pytest.raises(OwnerAusenteMaterializacao):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=materializador, porta_assinatura=porta,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )
    assert len(porta.chamadas_criar) == 0  # nunca chega a criar obrigação


# ---------------------------------------------------------------------
# 13. Política de agrupamento inválida
# ---------------------------------------------------------------------

def test_politica_agrupamento_fora_da_tabela_v1_falha_antes_de_qualquer_io():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-politica-invalida', conteudo=b'PDF-POL')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        politica_agrupamento='POLITICA_INEXISTENTE',
    )
    with pytest.raises(PoliticaAgrupamentoNaoSuportada):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=None, porta_assinatura=None,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )


def test_agrupado_1_link_sem_exigir_assinatura_falha():
    deps = _montar_dependencias()
    doc1 = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-a', conteudo=b'A')
    doc2 = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-b', conteudo=b'B')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(doc1.documento_id, doc1.hash_sha256), ItemDocumentoOrdem(doc2.documento_id, doc2.hash_sha256)),
        politica_agrupamento='AGRUPADO_1_LINK', exigir_assinatura=False,
    )
    with pytest.raises(PoliticaAgrupamentoNaoSuportada):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=None, porta_assinatura=None,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )


# ---------------------------------------------------------------------
# 14. N>=3 rejeitado nesta V1
# ---------------------------------------------------------------------

def test_tres_documentos_rejeitado_nesta_v1():
    deps = _montar_dependencias()
    docs = [
        _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id=f'doc-{i}', conteudo=f'C{i}'.encode())
        for i in range(3)
    ]
    ordem = _ordem_generica(
        documentos=tuple(ItemDocumentoOrdem(d.documento_id, d.hash_sha256) for d in docs),
        politica_agrupamento='AGRUPADO_1_LINK', exigir_assinatura=True,
    )
    with pytest.raises(PoliticaAgrupamentoNaoSuportada):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=None, porta_assinatura=None,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )


def test_n2_fora_do_pacote_holerite_ponto_falha_no_adapter_nao_no_nucleo():
    """O núcleo (este módulo) permite a COMBINAÇÃO (2, AGRUPADO_1_LINK,
    exigir_assinatura=True) -- é o ADAPTER legado quem rejeita
    tipo_documento != HOLERITE_FOLHA_PONTO (ver
    adapters/obrigacao_assinatura_legado_http.py). Prova a separação de
    responsabilidade exigida: HOLERITE_FOLHA_PONTO nunca aparece neste
    módulo."""
    from unittest.mock import Mock, patch

    from magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http import (
        AdapterObrigacaoAssinaturaLegadoHttp,
        QuantidadeArquivosNaoSuportadaPeloLegado,
    )
    deps = _montar_dependencias()
    doc1 = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-a2', conteudo=b'A2')
    doc2 = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'], documento_id='doc-b2', conteudo=b'B2')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(doc1.documento_id, doc1.hash_sha256), ItemDocumentoOrdem(doc2.documento_id, doc2.hash_sha256)),
        tipo_documento='EPI', politica_agrupamento='AGRUPADO_1_LINK', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    adapter_real = AdapterObrigacaoAssinaturaLegadoHttp(base_url='https://exemplo.invalid', api_key='dummy')
    resposta_get = Mock(status_code=200)
    resposta_get.json.return_value = {'existe': False}
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.get',
               return_value=resposta_get):
        with pytest.raises(QuantidadeArquivosNaoSuportadaPeloLegado):
            materializar_distribuicao_documental_shadow(
                ordem=ordem, materializador=materializador, porta_assinatura=adapter_real,
                ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
            )


# ---------------------------------------------------------------------
# 15. Zero transporte real -- verificação estrutural (AST)
# ---------------------------------------------------------------------

def test_modulo_nunca_importa_nem_chama_transporte_real():
    caminho = 'magnata_os/orquestrador/wiring_distribuicao_documental_shadow.py'
    with open(caminho, 'r', encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=caminho)
    proibidos = {'transporte_real_habilitado', 'compor_porta_execucao', 'ExecutorEvolutionLegado',
                 'executar_plano_disparo'}
    nomes_encontrados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            nomes_encontrados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.Name):
            nomes_encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes_encontrados.add(no.attr)
    assert proibidos.isdisjoint(nomes_encontrados)


# ---------------------------------------------------------------------
# 16. Bug do link -- extração de token fail-closed (achado HIGH da
# Ultrareview: rsplit sozinho nunca lançava exceção para link vazio/
# malformado/arbitrário; agora validado contra o mesmo formato de
# `_validar_reserva_assinatura`, reutilizado via `_RE_TOKEN_RESERVADO`).
# ---------------------------------------------------------------------

@pytest.mark.parametrize('link_malformado', [
    '',
    'https://exemplo.invalid/assinatura/',
    'sem-barra-nenhuma',
    'https://exemplo.invalid/assinatura/token-curto-demais',
])
def test_link_malformado_ou_arbitrario_falha_fechado(link_malformado):
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-link-malformado', conteudo=b'PDF-LINK-RUIM')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()
    # Pré-popula a obrigação "existente" com um link malformado/arbitrário,
    # simulando um backend comprometido ou uma implementação futura de
    # PortaObrigacaoAssinatura que devolva algo fora do formato esperado.
    import magnata_os.orquestrador.wiring_distribuicao_documental_shadow as mod
    event_id = derivar_identidade_ordem_distribuicao(ordem)
    A_esperado = mod._derivar_acao_execucao_id_assinatura(event_id)
    porta._por_correlacao[A_esperado] = ObrigacaoAssinatura(
        assinatura_id='rec-malformado', link=link_malformado, status='Pendente', tem_comprovante=False,
    )
    with pytest.raises(LinkObrigacaoAssinaturaMalformado):
        materializar_distribuicao_documental_shadow(
            ordem=ordem, materializador=materializador, porta_assinatura=porta,
            ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
        )
    assert len(porta.chamadas_criar) == 0  # nunca chega a chamar criar_ou_recuperar com dado malformado


def test_token_extraido_valido_e_aceito_normalmente():
    """Contraprova: um link no formato canônico real (RECIBO_BASE_URL +
    token de 43 caracteres) é aceito sem erro."""
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-link-valido', conteudo=b'PDF-LINK-BOM')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()
    r1 = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    r2 = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    assert r1.assinatura_link == r2.assinatura_link


# ---------------------------------------------------------------------
# 17. Corrida real entre 2 processos -- autocura via retry (achado
# MEDIUM da Ultrareview): outro processo cria a obrigação sob o MESMO
# A, com token diferente, entre a consulta e a nossa escrita.
# ---------------------------------------------------------------------

def test_corrida_real_entre_dois_processos_autocura_via_retry():
    deps = _montar_dependencias()
    documento = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-corrida', conteudo=b'PDF-CORRIDA')
    ordem = _ordem_generica(
        documentos=(ItemDocumentoOrdem(documento.documento_id, documento.hash_sha256),),
        tipo_documento='HOLERITE', exigir_assinatura=True,
    )
    materializador = _MaterializadorFake()
    porta = _PortaAssinaturaFake()

    import magnata_os.orquestrador.wiring_distribuicao_documental_shadow as mod
    event_id = mod.derivar_identidade_ordem_distribuicao(ordem)
    A = mod._derivar_acao_execucao_id_assinatura(event_id)

    consulta_original = porta.consultar_por_correlacao
    chamadas = {'n': 0}

    def consulta_com_corrida(*, acao_execucao_id):
        chamadas['n'] += 1
        resultado = consulta_original(acao_execucao_id=acao_execucao_id)
        if chamadas['n'] == 1 and acao_execucao_id == A and resultado is None:
            # Simula outro processo criando a obrigação (com token
            # PRÓPRIO, diferente do que esta chamada vai gerar) bem
            # entre esta consulta e a nossa tentativa de criar_ou_recuperar.
            porta._por_correlacao[A] = ObrigacaoAssinatura(
                assinatura_id='rec-vencedor', link='https://exemplo.invalid/assinatura/' + ('V' * 43),
                status='Pendente', tem_comprovante=False,
            )
        return resultado

    porta.consultar_por_correlacao = consulta_com_corrida

    resultado = materializar_distribuicao_documental_shadow(
        ordem=ordem, materializador=materializador, porta_assinatura=porta,
        ator_referencia='rh:teste', proveniencia='teste:sintetico', instante=AGORA, **deps,
    )
    # Autocurado: usa o link do VENCEDOR da corrida, nunca o próprio
    # token gerado (e descartado) na tentativa perdida.
    assert resultado.assinatura_link.endswith('V' * 43)
    assert len(porta.chamadas_criar) == 1  # a tentativa perdida contou; a 2a nem chega a chamar criar_ou_recuperar


# ---------------------------------------------------------------------
# 18. Ordem dos documentos participa da identidade (achado MEDIUM/LOW)
# ---------------------------------------------------------------------

def test_ordem_dos_documentos_participa_da_identidade():
    deps = _montar_dependencias()
    doc_holerite = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                        documento_id='doc-holerite-ordem', conteudo=b'PDF-HOLERITE-ORDEM')
    doc_ponto = _preparar_documento(deps['repositorio_documentos'], deps['armazenamento'],
                                     documento_id='doc-ponto-ordem', conteudo=b'PDF-PONTO-ORDEM')
    ordem_1 = _ordem_generica(
        documentos=(ItemDocumentoOrdem(doc_holerite.documento_id, doc_holerite.hash_sha256),
                    ItemDocumentoOrdem(doc_ponto.documento_id, doc_ponto.hash_sha256)),
        tipo_documento='HOLERITE_FOLHA_PONTO', exigir_assinatura=True,
        politica_agrupamento='AGRUPADO_1_LINK',
    )
    ordem_2 = _ordem_generica(
        documentos=(ItemDocumentoOrdem(doc_ponto.documento_id, doc_ponto.hash_sha256),
                    ItemDocumentoOrdem(doc_holerite.documento_id, doc_holerite.hash_sha256)),
        tipo_documento='HOLERITE_FOLHA_PONTO', exigir_assinatura=True,
        politica_agrupamento='AGRUPADO_1_LINK',
    )
    assert derivar_identidade_ordem_distribuicao(ordem_1) != derivar_identidade_ordem_distribuicao(ordem_2)
