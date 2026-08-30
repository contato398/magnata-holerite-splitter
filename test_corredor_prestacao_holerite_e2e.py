"""E2E do primeiro corredor automatizado da Prestação de Contas --
Holerite avulso primeiro (missões "CONSTRUIR O PRIMEIRO CORREDOR
AUTOMATIZADO E2E DA PRESTAÇÃO DE CONTAS" e "DEFINIR E IMPLEMENTAR A
FONTE AUTOMÁTICA DE COMPETÊNCIA ESPERADA").

Corredor provado ponta a ponta, sempre com fakes na fronteira (nenhum
acesso a Gmail/Airtable/Postgres reais):

    e-mail (fake) -> AdapterCapturaEmail -> ServicoCriacaoLote
    -> CLASSIFICACAO/CONCLUIDO -> IDENTIFICACAO/CONCLUIDO
    -> HoleriteConfirmadoDTO (competência OBSERVADA)
    -> ponte_prestacao_holerite:
         1. competência observada precisa ter valor único;
         2. resolve CLIENTE via FonteVinculosPrestacao, usando a
            OBSERVADA como referência temporal do vínculo;
         3. resolve a competência ESPERADA para aquele cliente via
            PoliticaCompetenciaPrestacao (base do ciclo + eventual
            deslocamento por cliente -- NUNCA copiada do documento);
         4. valida observada contra esperada.
    -> ItemInventarioPrestacao -> avaliar_prestacao_shadow
    -> PRONTO / FALTANDO

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

import pytest

from magnata_os.classificacao.classificador_documental import EstadoClassificacao
from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
    DeslocamentoCompetenciaCliente,
    PoliticaCompetenciaPrestacao,
)
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
    confirmar_holerite_para_inventario,
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
CLIENTE_DESLOCADO = ReferenciaCanonica("CLIENTE", "cliente-corredor-e2e-deslocado")
COMPETENCIA_BASE = (2026, 7)
COMPETENCIA_REF = ReferenciaCanonica("COMPETENCIA", "2026-07")
COMPETENCIA_DESLOCADA_REF = ReferenciaCanonica("COMPETENCIA", "2026-06")
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


class FonteVinculosPrestacaoPorCliente:
    """Duplo que devolve uma resolução DIFERENTE por colaborador -- usada
    para o cenário de múltiplos clientes no mesmo lote (cada colaborador
    resolve para o cliente configurado para ele)."""

    def __init__(self, resolucao_por_entidade_colaborador):
        self._por_colaborador = dict(resolucao_por_entidade_colaborador)
        self.chamadas = []

    def resolver_clientes(self, origem, competencia):
        self.chamadas.append((origem, competencia))
        return self._por_colaborador[origem.entidade_id]


class FonteVinculosPrestacaoFalha:
    """Duplo que simula uma falha TÉCNICA da fonte de vínculos (ex.:
    Airtable indisponível) -- nunca uma ambiguidade de negócio."""

    def resolver_clientes(self, origem, competencia):
        raise ConnectionError("falha técnica simulada da fonte de vínculos")


class FonteInventarioCompostaFake:
    """Combina o inventário base (5 tipos fiscais fixos) com os itens de
    Holerite já confirmados pela ponte -- mesmo padrão de composição já
    usado em test_prestacao_shadow_e2e.py."""

    def __init__(self, itens_holerite=(), inventario_base=None, cliente=CLIENTE, competencia=COMPETENCIA_REF):
        self._itens_holerite = tuple(itens_holerite)
        self._inventario_base = (
            inventario_base if inventario_base is not None
            else _inventario_base(cliente=cliente, competencia=competencia)
        )
        self._cliente = cliente
        self._competencia = competencia

    def listar(self, cliente, competencia):
        if cliente != self._cliente or competencia != self._competencia:
            return ()
        return self._inventario_base + tuple(
            item for item in self._itens_holerite
            if item.cliente == cliente and item.competencia == competencia
        )


def _inventario_base(tipos=TIPOS_BASE, cliente=CLIENTE, competencia=COMPETENCIA_REF):
    return tuple(
        ItemInventarioPrestacao(
            documento_id=f"doc-fiscal-{cliente.entidade_id}-{indice}",
            tipo_documental=tipo,
            cliente=cliente,
            competencia=competencia,
        )
        for indice, tipo in enumerate(tipos, start=1)
    )


def _resolucao_cliente_competencia(cliente=CLIENTE, competencia=COMPETENCIA_REF):
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
            (DimensaoResolucao.CLIENTE, cliente),
            (DimensaoResolucao.COMPETENCIA, competencia),
        )
    )
    return ResultadoResolucaoSemantico(
        documento_id=f"corredor-holerite-e2e:{cliente.entidade_id}",
        resolver_id="resolver-corredor-e2e",
        resolver_version="1",
        politica_id="prestacao-readiness",
        politica_version="1",
        perfil=perfil,
        resolucoes=resolucoes,
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA,
        necessita_revisao_humana=False,
    )


def _politica_requisitos_com_holerite_obrigatorio(cliente=CLIENTE, competencia=COMPETENCIA_REF):
    return PoliticaRequisitosPrestacao(
        version="1",
        overrides=(
            OverrideRequisitosPrestacao(
                cliente=cliente,
                competencia=competencia,
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


def _resolucao_colaborador(entidade_id):
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.COLABORADOR,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('COLABORADOR', entidade_id),),
    )


def _competencia_extraida(ano_mes, estrategia='mm_aaaa_numerico'):
    return CompetenciaExtraida(
        status=StatusExtracaoCompetencia.ENCONTRADA, ano_mes=ano_mes, estrategia=estrategia,
    )


_RESOLUCAO_COLABORADOR_UNICO = _resolucao_colaborador('colab-001')
_COMPETENCIA_JULHO = _competencia_extraida((2026, 7))
_COMPETENCIA_JUNHO = _competencia_extraida((2026, 6))
_RESOLUCAO_VINCULO_UNICO = ResolucaoDimensao(
    dimensao=DimensaoResolucao.CLIENTE,
    estado=EstadoResolucaoDimensao.RESOLVIDA,
    valores_confirmados=(CLIENTE,),
    confianca=ConfiancaResolucao(NivelConfianca.FORTE),
)


def _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos):
    return confirmar_holerites_do_lote(resumo_lote, contexto, politica_competencia, fonte_vinculos)


# ============================================================================
# CASO 1 -- ciclo normal + cliente normal -> PRONTO
# ============================================================================

def test_caso1_ciclo_normal_cliente_normal_resulta_pronto(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True
    assert item.holerite_confirmado is not None

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')  # sem deslocamentos
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)

    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert len(itens_holerite) == 1
    assert itens_holerite[0].tipo_documental == TipoDocumental.HOLERITE.value
    assert itens_holerite[0].cliente == CLIENTE
    assert itens_holerite[0].competencia == COMPETENCIA_REF

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_requisitos_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO
    assert resultado.tipos_faltantes == ()


# ============================================================================
# CASO 2 -- cliente com deslocamento comprovado -> aceito na competência deslocada
# ============================================================================

def test_caso2_cliente_com_deslocamento_aceita_competencia_diferente_da_base(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JUNHO,  # o colaborador deste cliente é deslocado p/ junho
    )
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)  # base = julho
    politica_competencia = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(DeslocamentoCompetenciaCliente(CLIENTE_DESLOCADO, (2026, 6)),),
    )
    resolucao_vinculo_deslocado = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(CLIENTE_DESLOCADO,),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculo_deslocado)

    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert len(itens_holerite) == 1
    assert itens_holerite[0].cliente == CLIENTE_DESLOCADO
    assert itens_holerite[0].competencia == COMPETENCIA_DESLOCADA_REF

    resultado = avaliar_prestacao_shadow(
        CLIENTE_DESLOCADO, COMPETENCIA_DESLOCADA_REF,
        _resolucao_cliente_competencia(CLIENTE_DESLOCADO, COMPETENCIA_DESLOCADA_REF),
        FonteInventarioCompostaFake(
            itens_holerite,
            inventario_base=_inventario_base(cliente=CLIENTE_DESLOCADO, competencia=COMPETENCIA_DESLOCADA_REF),
            cliente=CLIENTE_DESLOCADO, competencia=COMPETENCIA_DESLOCADA_REF,
        ),
        _politica_requisitos_com_holerite_obrigatorio(CLIENTE_DESLOCADO, COMPETENCIA_DESLOCADA_REF),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO


# ============================================================================
# CASO 3 -- Holerite com competência do ciclo geral p/ cliente que exige
# deslocada -> rejeitado
# ============================================================================

def test_caso3_competencia_do_ciclo_geral_rejeitada_para_cliente_deslocado(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,  # competência do ciclo geral, nao a deslocada
    )
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(DeslocamentoCompetenciaCliente(CLIENTE_DESLOCADO, (2026, 6)),),
    )
    resolucao_vinculo_deslocado = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(CLIENTE_DESLOCADO,),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculo_deslocado)

    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()  # julho != junho (esperada deste cliente) -- nunca aceito


# ============================================================================
# Exceção REAL do SKY Tatuí (missão "ATIVAR REGRA DE COMPETÊNCIA DO SKY
# TATUÍ") -- usa a referência canônica confirmada e a política real
# exportada (POLITICA_COMPETENCIA_PRESTACAO_V1), nunca uma cópia
# sintética da regra.
# ============================================================================

def test_sky_com_holerite_junho_e_ciclo_base_julho_e_aceito(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JUNHO,  # SKY = base - 1 mes = junho, quando base = julho
    )
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)  # julho/2026
    resolucao_vinculo_sky = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(REFERENCIA_CLIENTE_SKY_TATUI,),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculo_sky)

    itens_holerite = _confirmar(
        resumo_lote, contexto, POLITICA_COMPETENCIA_PRESTACAO_V1, fonte_vinculos)
    assert len(itens_holerite) == 1
    assert itens_holerite[0].cliente == REFERENCIA_CLIENTE_SKY_TATUI
    assert itens_holerite[0].competencia == COMPETENCIA_DESLOCADA_REF  # 2026-06


def test_sky_com_holerite_julho_e_ciclo_base_julho_e_rejeitado(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,  # SKY exige junho quando base = julho -- julho diverge
    )
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    resolucao_vinculo_sky = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(REFERENCIA_CLIENTE_SKY_TATUI,),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculo_sky)

    itens_holerite = _confirmar(
        resumo_lote, contexto, POLITICA_COMPETENCIA_PRESTACAO_V1, fonte_vinculos)
    assert itens_holerite == ()  # julho != junho (esperada real do SKY) -- nunca aceito


# ============================================================================
# CASO 4 -- contexto de ciclo ausente -> não inventa competência
# ============================================================================

def test_caso4_contexto_ausente_nao_inventa_competencia(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)

    itens_holerite = _confirmar(resumo_lote, None, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()
    # o vinculo E' resolvido (usa a observada como referencia temporal) --
    # so a competencia esperada fica ausente, nunca inventada.
    assert fonte_vinculos.chamadas == [
        (ReferenciaCanonica('COLABORADOR', 'colab-001'), COMPETENCIA_REF),
    ]


# ============================================================================
# CASO 5 -- cliente não resolvido -> não calcula competência arbitrariamente
# ============================================================================

def test_caso5_cliente_nao_resolvido_nunca_calcula_competencia(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    cliente_alternativo = ReferenciaCanonica("CLIENTE", "cliente-alternativo")
    resolucao_vinculo_ambigua = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.AMBIGUA,
        candidatos=(CLIENTE, cliente_alternativo),
        confianca=ConfiancaResolucao(NivelConfianca.FRACA),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculo_ambigua)

    class _PoliticaEspiao(PoliticaCompetenciaPrestacao):
        chamadas = []

        def competencia_esperada_para(self, contexto, cliente, tipo_documental):
            _PoliticaEspiao.chamadas.append((cliente, tipo_documental))
            return super().competencia_esperada_para(contexto, cliente, tipo_documental)

    politica_competencia = _PoliticaEspiao(version='1')
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)

    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()
    assert _PoliticaEspiao.chamadas == []  # nunca sequer tenta resolver competencia p/ cliente ambiguo


# ============================================================================
# CASO 6 -- regra de cliente ambígua/conflitante -> nunca confirma
# ============================================================================

def test_caso6_politica_conflitante_nao_pode_nem_ser_construida():
    """Uma política com dois deslocamentos conflitantes para o mesmo
    cliente/tipo nunca chega a existir para ser consultada -- fail-fast
    na construção, nunca uma escolha arbitrária em tempo de resolução."""
    with pytest.raises(ValueError):
        PoliticaCompetenciaPrestacao(
            version='1',
            deslocamentos=(
                DeslocamentoCompetenciaCliente(CLIENTE, (2026, 6), 'holerite'),
                DeslocamentoCompetenciaCliente(CLIENTE, (2026, 5), 'holerite'),
            ),
        )


# ============================================================================
# CASO 7 -- competência observada divergente da esperada -> não entra
# ============================================================================

def test_caso7_competencia_observada_divergente_nao_entra_no_inventario(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_competencia_extraida((2026, 8)),  # nem julho (base) nem qualquer deslocamento
    )
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)

    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()


# ============================================================================
# CASO 8 -- regra default inexistente -> fail-safe, nunca mês atual implícito
# ============================================================================

def test_caso8_sem_contexto_e_sem_deslocamento_e_fail_safe_nunca_mes_atual(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')  # sem deslocamentos
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)

    # Nenhum contexto de ciclo, nenhum deslocamento -- resultado precisa
    # ser "nao confirmavel", nunca uma adivinhacao pelo mes atual do
    # relogio (o modulo nem importa datetime -- ver
    # test_magnata_os_classificacao_competencia_esperada_prestacao.py).
    itens_holerite = _confirmar(resumo_lote, None, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()


# ============================================================================
# CASO 9 -- múltiplos Holerites, clientes diferentes, mesmo ciclo -> cada
# um recebe sua competência esperada correta
# ============================================================================

def test_caso9_multiplos_clientes_no_mesmo_lote_cada_um_com_sua_competencia(monkeypatch):
    monkeypatch.setattr(
        servico_lote_mod, 'decidir_roteamento_de_texto',
        lambda texto: _decisao_roteamento('Holerite'),
    )

    # Cada arquivo (nome/conteudo distintos) e' identificado como um
    # colaborador diferente e traz a competencia observada compativel
    # com o cliente ao qual pertence.
    resolucoes_por_texto = {
        'texto-colab-normal': _resolucao_colaborador('colab-normal'),
        'texto-colab-deslocado': _resolucao_colaborador('colab-deslocado'),
    }
    competencias_por_texto = {
        'texto-colab-normal': _COMPETENCIA_JULHO,
        'texto-colab-deslocado': _COMPETENCIA_JUNHO,
    }

    def _texto_por_conteudo(conteudo):
        return conteudo.decode('utf-8')

    monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', _texto_por_conteudo)
    monkeypatch.setattr(
        servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
        lambda texto, candidatos: resolucoes_por_texto[texto],
    )
    monkeypatch.setattr(
        servico_lote_mod, 'extrair_competencia_de_texto',
        lambda texto: competencias_por_texto[texto],
    )

    pipeline = construir_pipeline_modulo01(
        repositorio_documentos=RepositorioDocumentosEmMemoria(),
        repositorio_historico=RepositorioHistoricoEmMemoria(),
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_estados_esteira=RepositorioEstadosEsteiraEmMemoria(),
        fonte_mensagens=FonteMensagensEmailFalsa([
            _mensagem(anexos=[
                _anexo('holerite_normal.pdf', b'texto-colab-normal'),
                _anexo('holerite_deslocado.pdf', b'texto-colab-deslocado'),
            ]),
        ]),
        fonte_candidatos_funcionario=_FonteCandidatosFuncionarioFake(),
    )
    resumo = pipeline.adapter_captura_email.capturar_novas_mensagens()
    resumo_lote = resumo.resumos_lote[0]
    assert resumo_lote.quantidade_sucesso == 2

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(DeslocamentoCompetenciaCliente(CLIENTE_DESLOCADO, (2026, 6)),),
    )
    fonte_vinculos = FonteVinculosPrestacaoPorCliente({
        'colab-normal': ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(CLIENTE,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        ),
        'colab-deslocado': ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(CLIENTE_DESLOCADO,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        ),
    })

    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert len(itens_holerite) == 2
    por_cliente = {item.cliente: item for item in itens_holerite}
    assert por_cliente[CLIENTE].competencia == COMPETENCIA_REF
    assert por_cliente[CLIENTE_DESLOCADO].competencia == COMPETENCIA_DESLOCADA_REF


# ============================================================================
# Casos herdados do PR #90 -- upstream do gate de identificação (o
# reordenamento cliente-antes-de-competência não muda estes: o item
# nunca chega a ter holerite_confirmado quando a identificação/tipo em
# si já falha antes da ponte).
# ============================================================================

def test_colaborador_ambiguo_nunca_confirma_holerite(monkeypatch):
    resolucao_ambigua = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COLABORADOR,
        estado=EstadoResolucaoDimensao.AMBIGUA,
    )
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=resolucao_ambigua,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True  # ingestão preservada
    assert item.holerite_confirmado is None
    assert item.resultado_gate_identificacao.situacao_resultante == 'BLOQUEADO'

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()
    assert fonte_vinculos.chamadas == []  # nunca sequer tenta resolver cliente


def test_documento_duplicado_nunca_duplica_contribuicao(monkeypatch):
    conteudo_fixo = b"conteudo holerite fixo"
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
        anexos=[_anexo('holerite.pdf', conteudo_fixo), _anexo('holerite_copia.pdf', conteudo_fixo)],
    )
    assert resumo_lote.quantidade_sucesso == 1
    assert resumo_lote.quantidade_duplicados == 1
    original, duplicado = resumo_lote.itens
    assert original.holerite_confirmado is not None
    assert duplicado.holerite_confirmado is None  # idempotência: nunca reaplica identificação

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert len(itens_holerite) == 1  # nunca 2, mesmo com 2 itens no resumo


def test_outro_tipo_documental_nunca_passa_pelo_corredor_holerite(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
        tipo_documental="Ficha de Registro",
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True
    assert item.resultado_gate_identificacao.tentado is False
    assert item.holerite_confirmado is None

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert itens_holerite == ()


def test_falha_tecnica_da_fonte_de_vinculos_nunca_gera_falso_pronto(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    item = resumo_lote.itens[0]
    assert item.sucesso is True  # ingestão preservada mesmo que a ponte falhe depois
    assert item.documento_id is not None
    assert item.erro is None

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos_com_falha = FonteVinculosPrestacaoFalha()
    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos_com_falha)
    assert itens_holerite == ()

    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite), _politica_requisitos_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == (TipoDocumental.HOLERITE.value,)


def test_holerite_valido_mas_outro_tipo_obrigatorio_ausente_resulta_faltando(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)
    itens_holerite = _confirmar(resumo_lote, contexto, politica_competencia, fonte_vinculos)
    assert len(itens_holerite) == 1

    inventario_incompleto = _inventario_base(tipos=(
        "DCTFWeb - Declaração", "DCTFWeb - Recibo de Entrega",
        "Guia DCTFWeb/DARF", "extrato_cliente",
    ))
    resultado = avaliar_prestacao_shadow(
        CLIENTE, COMPETENCIA_REF, _resolucao_cliente_competencia(),
        FonteInventarioCompostaFake(itens_holerite, inventario_incompleto),
        _politica_requisitos_com_holerite_obrigatorio(),
    )
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == ("FGTS",)


# ============================================================================
# Confirmação de assinatura -- confirmar_holerite_para_inventario direto
# (item único, sem passar pelo lote), garantindo que a API pública da
# ponte permanece exercitável isoladamente.
# ============================================================================

def test_confirmar_holerite_para_inventario_isolado_caminho_feliz(monkeypatch):
    resumo_lote = _processar_lote_holerite(
        monkeypatch,
        resolucao_identificacao=_RESOLUCAO_COLABORADOR_UNICO,
        competencia_observada=_COMPETENCIA_JULHO,
    )
    holerite_confirmado = resumo_lote.itens[0].holerite_confirmado
    assert holerite_confirmado is not None

    contexto = ContextoCicloPrestacao(competencia_base=COMPETENCIA_BASE)
    politica_competencia = PoliticaCompetenciaPrestacao(version='1')
    fonte_vinculos = FonteVinculosPrestacaoFake(_RESOLUCAO_VINCULO_UNICO)

    item = confirmar_holerite_para_inventario(
        holerite_confirmado, contexto, politica_competencia, fonte_vinculos,
    )
    assert item is not None
    assert item.cliente == CLIENTE
    assert item.competencia == COMPETENCIA_REF
