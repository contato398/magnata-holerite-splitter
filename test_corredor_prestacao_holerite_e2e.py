"""E2E do primeiro corredor automatizado da Prestação de Contas --
Holerite avulso primeiro (missão "CONSTRUIR O PRIMEIRO CORREDOR
AUTOMATIZADO E2E DA PRESTAÇÃO DE CONTAS").

Corredor provado ponta a ponta, sempre com fakes na fronteira (nenhum
acesso a Gmail/Airtable/Postgres reais):

    e-mail (fake) -> AdapterCapturaEmail -> ServicoCriacaoLote
    -> CLASSIFICACAO/CONCLUIDO -> IDENTIFICACAO/CONCLUIDO
    -> HoleriteConfirmadoDTO (competência OBSERVADA)
    -> ponte_prestacao_holerite (competência ESPERADA independente
       + FonteVinculosPrestacao) -> ItemInventarioPrestacao
    -> avaliar_prestacao_shadow -> PRONTO / FALTANDO

Reaproveita o composition root V1 (`construir_pipeline_modulo01`) e o
mesmo padrão de monkeypatch já provado em
test_magnata_os_documental_modulo01_email_captura.py::
test_holerite_elegivel_alcanca_identificacao_via_pipeline_completo --
`extrair_texto_seguro`/`decidir_roteamento_de_texto`/
`resolver_identificacao_holerite_de_texto`/`extrair_competencia_de_texto`
são pontos JÁ testados isoladamente em outros arquivos; aqui só
controlamos seu resultado para tornar o corredor determinístico, sem
depender de PDF real.
"""
from datetime import datetime, timezone

from magnata_os.classificacao.classificador_documental import EstadoClassificacao
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)
from magnata_os.classificacao.politica_requisitos_prestacao import (
    OverrideRequisitosPrestacao,
    PoliticaRequisitosPrestacao,
)
from magnata_os.classificacao.prestacao_readiness import (
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
from magnata_os.classificacao.prestacao_shadow import avaliar_prestacao_shadow
from magnata_os.classificacao.roteamento_documental import (
    AcaoRoteamento,
    DecisaoRoteamentoDocumental,
    EscopoDocumental,
    MotivoRoteamento,
)
from magnata_os.documental.importacao_lote.contratos import (
    CompetenciaExtraida,
    StatusExtracaoCompetencia,
    TipoDocumental,
)
from magnata_os.documental.modulo01 import servico_lote as servico_lote_mod
from magnata_os.documental.modulo01.adapters.email_captura import (
    AnexoEmailRecebido,
    MensagemEmailRecebida,
)
from magnata_os.documental.modulo01.composicao import construir_pipeline_modulo01
from magnata_os.documental.modulo01.ponte_prestacao_holerite import (
    confirmar_holerites_do_lote,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)


CLIENTE = ReferenciaCanonica("CLIENTE", "cliente-corredor-e2e")
COMPETENCIA_ESPERADA = (2026, 7)
COMPETENCIA_REF = ReferenciaCanonica("COMPETENCIA", "2026-07")
TIPOS_BASE = (
    "DCTFWeb - Declaração",
    "DCTFWeb - Recibo de Entrega",
    "Guia DCTFWeb/DARF",
    "FGTS",
    "extrato_cliente",
)


# ============================================================================
# Fakes de fronteira -- nenhum acesso real a e-mail, Airtable ou Postgres.
# ============================================================================

class FonteMensagensEmailFalsa:
    def __init__(self, mensagens=None):
        self._mensagens = list(mensagens or [])

    def buscar_novas_mensagens(self):
        return list(self._mensagens)


class _FonteCandidatosFuncionarioFake:
    def __init__(self, candidatos=None):
        self._candidatos = list(candidatos or [])

    def listar_funcionarios(self):
        return self._candidatos


class FonteVinculosPrestacaoFake:
    """Duplo de FonteVinculosPrestacao -- devolve sempre a mesma
    ResolucaoDimensao configurada (mesmo padrão de
    test_prestacao_shadow_e2e.py::FonteVinculosPrestacaoFake)."""

    def __init__(self, resolucao):
        self._resolucao = resolucao
        self.chamadas = []

    def resolver_clientes(self, origem, competencia):
        self.chamadas.append((origem, competencia))
        return self._resolucao


class FonteVinculosPrestacaoFalha:
    """Duplo que simula uma falha TÉCNICA da fonte de vínculos (ex.:
    Airtable indisponível) -- nunca uma ambiguidade de negócio."""

    def resolver_clientes(self, origem, competencia):
        raise ConnectionError("falha técnica simulada da fonte de vínculos")


class FonteInventarioCompostaFake:
    """Combina o inventário base (5 tipos fiscais fixos) com os itens de
    Holerite já confirmados pela ponte -- mesmo padrão de composição já
    usado em test_prestacao_shadow_e2e.py."""

    def __init__(self, itens_holerite=(), inventario_base=None):
        self._itens_holerite = tuple(itens_holerite)
        self._inventario_base = inventario_base if inventario_base is not None else _inventario_base()

    def listar(self, cliente, competencia):
        if cliente != CLIENTE or competencia != COMPETENCIA_REF:
            return ()
        return self._inventario_base + self._itens_holerite


def _inventario_base(tipos=TIPOS_BASE):
    return tuple(
        ItemInventarioPrestacao(
            documento_id=f"doc-fiscal-{indice}",
            tipo_documental=tipo,
            cliente=CLIENTE,
            competencia=COMPETENCIA_REF,
        )
        for indice, tipo in enumerate(tipos, start=1)
    )


def _resolucao_cliente_competencia():
    """ResultadoResolucaoSemantico de CLIENTE/COMPETENCIA já resolvidos --
    dimensão INDEPENDENTE da identificação de colaborador (que acontece
    dentro do pipeline do Módulo 01); mesmo papel de `_resolucao()` em
    test_prestacao_shadow_e2e.py."""
    regras = tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao,
            aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )
        for dimensao in (DimensaoResolucao.CLIENTE, DimensaoResolucao.COMPETENCIA)
    )
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id="corredor-holerite-e2e", version="1",
        escopo_documental="prestacao-contas", regras=regras,
    )
    resolucoes = tuple(
        ResolucaoDimensao(
            dimensao=dimensao,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(referencia,),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
        for dimensao, referencia in (
            (DimensaoResolucao.CLIENTE, CLIENTE),
            (DimensaoResolucao.COMPETENCIA, COMPETENCIA_REF),
        )
    )
    return ResultadoResolucaoSemantico(
        documento_id="corredor-holerite-e2e",
        resolver_id="resolver-corredor-e2e",
        resolver_version="1",
        politica_id="prestacao-readiness",
        politica_version="1",
        perfil=perfil,
        resolucoes=resolucoes,
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA,
        necessita_revisao_humana=False,
    )


def _politica_com_holerite_obrigatorio():
    return PoliticaRequisitosPrestacao(
        version="1",
        overrides=(
            OverrideRequisitosPrestacao(
                cliente=CLIENTE,
                competencia=COMPETENCIA_REF,
                requisitos_adicionais=(
                    RequisitoDocumentalPrestacao(TipoDocumental.HOLERITE.value),
                ),
            ),
        ),
    )


def _mensagem(anexos, message_id="msg-corredor"):
    return MensagemEmailRecebida(
        message_id=message_id,
        remetente="cliente@exemplo.com",
        assunto="Documentos",
        recebido_em=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        anexos=anexos,
    )


def _anexo(nome="holerite.pdf", conteudo=b"conteudo holerite"):
    return AnexoEmailRecebido(nome_original=nome, mime_type="application/pdf", conteudo=conteudo)


def _decisao_roteamento(tipo_documental="Holerite"):
    return DecisaoRoteamentoDocumental(
        tipo_documental=tipo_documental,
        estado_classificacao=EstadoClassificacao.RESOLVIDA,
        escopo_documental=EscopoDocumental.COLABORADOR,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='BAIXA',
        evidencias_sanitizadas=('hit',),
        tipos_concorrentes=(),
    )


def _processar_lote_holerite(
    monkeypatch,
    *,
    resolucao_identificacao,
    competencia_observada,
    tipo_documental="Holerite",
    anexos=None,
):
    """Atravessa o pipeline REAL do Módulo 01 (composition root), com
    classificação/identificação/competência observada controladas por
    monkeypatch nos pontos já testados isoladamente em outros arquivos
    (test_gate_classificacao_esteira.py, test_gate_identificacao_
    holerite_esteira.py, test_magnata_os_documental_modulo01_email_
    captura.py). Devolve o ResumoLote inteiro."""
    monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
    monkeypatch.setattr(
        servico_lote_mod, 'decidir_roteamento_de_texto',
        lambda texto: _decisao_roteamento(tipo_documental),
    )
    monkeypatch.setattr(
        servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
        lambda texto, candidatos: resolucao_identificacao,
    )
    monkeypatch.setattr(
        servico_lote_mod, 'extrair_competencia_de_texto',
        lambda texto: competencia_observada,
    )

    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=RepositorioDocumentosEmMemoria(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=RepositorioEstadosEsteiraEmMemoria(),
        fonte_mensagens=FonteMensagensEmailFalsa([
            _mensagem(anexos or [_anexo()]),
        ]),
        fonte_candidatos_funcionario=_FonteCandidatosFuncionarioFake(),
    )
    resumo = pipeline.adapter_captura_email.capturar_novas_mensagens()
    return resumo.resumos_lote[0]


_RESOLUCAO_COLABORADOR_UNICO = ResolucaoDimensao(
    dimensao=DimensaoResolucao.COLABORADOR,
    estado=EstadoResolucaoDimensao.RESOLVIDA,
    valores_confirmados=(ReferenciaCanonica('COLABORADOR', 'colab-001'),),
)
_COMPETENCIA_CONFIRMADA = CompetenciaExtraida(
    status=StatusExtracaoCompetencia.ENCONTRADA, ano_mes=(2026, 7), estrategia='mm_aaaa_numerico',
)
_RESOLUCAO_VINCULO_UNICO = ResolucaoDimensao(
    dimensao=DimensaoResolucao.CLIENTE,
    estado=EstadoResolucaoDimensao.RESOLVIDA,
    valores_confirmados=(CLIENTE,),
    confianca=ConfiancaResolucao(NivelConfianca.FORTE),
)


# ============================================================================
# CASO 1 -- caminho feliz: PRONTO
# ============================================================================

def test_caso1_holerite_valido_vinculo_unico_competencia_confirmada_resulta_pronto(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True
    assert item.holerite_confirmado is not None
    assert item.resultado_gate_identificacao.situacao_resultante == 'CONCLUIDO'

    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert len(itens_holerite) == 1
    assert itens_holerite[0].tipo_documental == TipoDocumental.HOLERITE.value
    assert itens_holerite[0].cliente == CLIENTE

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO
    assert resultado.tipos_faltantes == ()


# ============================================================================
# CASO 2 -- Holerite válido, mas falta outro tipo obrigatório -> FALTANDO
# ============================================================================

def test_caso2_holerite_valido_mas_outro_tipo_obrigatorio_ausente_resulta_faltando(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert len(itens_holerite) == 1

    # Inventário base incompleto -- falta "FGTS".
    inventario_incompleto = _inventario_base(tipos=(
        "DCTFWeb - Declaração", "DCTFWeb - Recibo de Entrega",
        "Guia DCTFWeb/DARF", "extrato_cliente",
    ))
    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite, inventario_incompleto),
        _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == ("FGTS",)


# ============================================================================
# CASO 3 -- colaborador ambíguo -> nunca confirma Holerite, revisão/bloqueio
# ============================================================================

def test_caso3_colaborador_ambiguo_nunca_confirma_holerite(monkeypatch):
    resolucao_ambigua = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COLABORADOR,
        estado=EstadoResolucaoDimensao.AMBIGUA,
    )
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=resolucao_ambigua,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True  # ingestão preservada
    assert item.holerite_confirmado is None  # nunca confirmado com colaborador ambíguo
    assert item.resultado_gate_identificacao.situacao_resultante == 'BLOQUEADO'

    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert itens_holerite == ()
    assert fonte_vinculos.chamadas == []  # nunca sequer tenta resolver cliente

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == (TipoDocumental.HOLERITE.value,)


# ============================================================================
# CASO 4 -- vínculo cliente ambíguo -> não associa arbitrariamente
# ============================================================================

def test_caso4_vinculo_cliente_ambiguo_nao_associa_arbitrariamente(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
    )
    assert resumo_lote.itens[0].holerite_confirmado is not None  # identificação em si foi resolvida

    cliente_alternativo = ReferenciaCanonica("CLIENTE", "cliente-alternativo")
    resolucao_vinculo_ambigua = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.AMBIGUA,
        candidatos=(CLIENTE, cliente_alternativo),
        confianca=ConfiancaResolucao(NivelConfianca.FRACA),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculo_ambigua)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert itens_holerite == ()  # readiness nunca recebe item indevido

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == (TipoDocumental.HOLERITE.value,)


# ============================================================================
# CASO 5 -- competência observada != esperada -> não entra confirmado
# ============================================================================

def test_caso5_competencia_observada_diferente_da_esperada_nao_confirma(monkeypatch):
    competencia_divergente = CompetenciaExtraida(
        status=StatusExtracaoCompetencia.ENCONTRADA, ano_mes=(2026, 8), estrategia='mm_aaaa_numerico',
    )
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=competencia_divergente,
    )
    assert resumo_lote.itens[0].holerite_confirmado is not None  # observada existe, só diverge da esperada

    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert itens_holerite == ()  # esperada=2026-07, observada=2026-08 -- nunca aceito
    assert fonte_vinculos.chamadas == []  # nunca chega a tentar resolver cliente

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == (TipoDocumental.HOLERITE.value,)


# ============================================================================
# CASO 6 -- competência esperada ausente -> não inventa, pendente explícito
# ============================================================================

def test_caso6_competencia_esperada_ausente_nao_inventa_fica_pendente(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
    )
    assert resumo_lote.itens[0].holerite_confirmado is not None  # observada existe e é válida

    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    # Nenhuma competência esperada configurada ainda para este ciclo --
    # `None` explícito, nunca a observada copiada como se fosse esperada.
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, None, fonte_vinculos)
    assert itens_holerite == ()
    assert fonte_vinculos.chamadas == []  # nunca sequer tenta resolver cliente sem competência esperada

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == (TipoDocumental.HOLERITE.value,)


# ============================================================================
# CASO 7 -- duplicado -> nunca duplica contribuição no inventário
# ============================================================================

def test_caso7_documento_duplicado_nunca_duplica_contribuicao(monkeypatch):
    conteudo_fixo = b"conteudo holerite fixo"
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
        anexos=[_anexo('holerite.pdf', conteudo_fixo), _anexo('holerite_copia.pdf', conteudo_fixo)],
    )
    assert resumo_lote.quantidade_sucesso == 1
    assert resumo_lote.quantidade_duplicados == 1
    original, duplicado = resumo_lote.itens
    assert original.holerite_confirmado is not None
    assert duplicado.duplicado is True
    assert duplicado.holerite_confirmado is None  # idempotência: nunca reaplica identificação

    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert len(itens_holerite) == 1  # nunca 2, mesmo com 2 itens no resumo


# ============================================================================
# CASO 8 -- outro tipo documental -> nunca passa pelo corredor de Holerite
# ============================================================================

def test_caso8_outro_tipo_documental_nunca_passa_pelo_corredor_holerite(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
        tipo_documental="Ficha de Registro",
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True
    assert item.resultado_gate_identificacao.tentado is False  # gate nem tentado, tipo não elegível
    assert item.holerite_confirmado is None

    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos)
    assert itens_holerite == ()


# ============================================================================
# CASO 9 -- falha técnica da fonte de vínculos -> ingestão preservada,
# erro sanitizado, nenhum falso PRONTO
# ============================================================================

def test_caso9_falha_tecnica_da_fonte_de_vinculos_nunca_gera_falso_pronto(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_CONFIRMADA,
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True  # ingestão preservada mesmo que a ponte falhe depois
    assert item.documento_id is not None
    assert item.erro is None

    fonte_vinculos_com_falha = FonteVinculosPrestacaoFalha()
    # confirmar_holerites_do_lote nunca propaga a exceção da fonte --
    # trata como "não confirma", nunca deixa a exceção subir.
    itens_holerite = confirmar_holerites_do_lote(resumo_lote, COMPETENCIA_ESPERADA, fonte_vinculos_com_falha)
    assert itens_holerite == ()

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO  # nunca PRONTO por falha de fonte
    assert resultado.tipos_faltantes == (TipoDocumental.HOLERITE.value,)
