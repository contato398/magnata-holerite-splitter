"""Teste de integração: gate controlado CLASSIFICACAO -> IDENTIFICACAO
para Holerite avulso (branch fix/identificacao-holerite-avulso).

Cobre o ponto de integração real dentro de
`ServicoCriacaoLote._processar_um_arquivo` (servico_lote.py): extração
de texto ÚNICA (extrair_texto_seguro), decisão de classificação
(decidir_roteamento_de_texto) reaproveitada tanto para o gate
REGISTRO->CLASSIFICACAO quanto para a elegibilidade do gate
CLASSIFICACAO->IDENTIFICACAO, e aplicação de
`politica_identificacao_holerite.decidir_transicao_identificacao` via
`ServicoAvancoEsteira.aplicar_resultado_identificacao`.

Monkeypatch de `extrair_texto_seguro`/`decidir_roteamento_de_texto`
(classificação, sempre Holerite RESOLVIDA nesta suíte) e de
`resolver_identificacao_holerite_de_texto` (resultado de identificação
controlado) torna estes testes independentes do ambiente de extração de
PDF e da lógica de CPF/nome (já cobertas separadamente em
test_politica_identificacao_holerite.py) — mesmo padrão já usado em
test_gate_classificacao_esteira.py.
"""
import collections

import pytest

from magnata_os.classificacao.classificador_documental import EstadoClassificacao
from magnata_os.classificacao.roteamento_documental import (
    AcaoRoteamento,
    DecisaoRoteamentoDocumental,
    EscopoDocumental,
    MotivoRoteamento,
)
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.modulo01 import servico_lote as servico_lote_mod
from magnata_os.documental.modulo01.dominio_esteira import EtapaEsteira, SituacaoEsteira
from magnata_os.documental.modulo01.dtos_esteira import (
    MOTIVO_ERRO_TECNICO_GATE_IDENTIFICACAO,
    MOTIVO_GATE_IDENTIFICACAO_NAO_APLICAVEL,
    MOTIVO_GATE_IDENTIFICACAO_PROMOVIDA,
    MOTIVO_GATE_IDENTIFICACAO_PROMOVIDA_COM_BLOQUEIO,
    MOTIVO_GATE_IDENTIFICACAO_PROMOVIDA_EM_REVISAO,
)
from magnata_os.documental.modulo01.politica_identificacao_holerite import (
    CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO,
    CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO,
    MestreSuspeitoIdentificacaoHolerite,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import ServicoAvancoEsteira
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote

_Contexto = collections.namedtuple(
    '_Contexto', 'repo_docs repo_hist repo_lotes repo_estados servico_avanco servico_lote fonte_candidatos'
)


class _FonteCandidatosFake:
    """Duplo de teste de FonteCandidatosFuncionario -- conta chamadas
    para provar que a leitura é feita no máximo 1 vez por lote (nunca
    por arquivo)."""

    def __init__(self, candidatos=None):
        self._candidatos = list(candidatos or [])
        self.chamadas = 0

    def listar_funcionarios(self):
        self.chamadas += 1
        return self._candidatos


def _montar_servicos(fonte_candidatos=None) -> _Contexto:
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    fonte = fonte_candidatos if fonte_candidatos is not None else _FonteCandidatosFake()
    servico_lote = ServicoCriacaoLote(
        repo_lotes, servico_entrada, servico_avanco, fonte_candidatos_funcionario=fonte,
    )

    return _Contexto(repo_docs, repo_hist, repo_lotes, repo_estados, servico_avanco, servico_lote, fonte)


def _decisao_holerite_resolvida() -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental='Holerite',
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


def _decisao_outro_tipo_resolvida(tipo: str) -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental=tipo,
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


def _forcar_classificacao_holerite_resolvida(monkeypatch: pytest.MonkeyPatch, texto: str = 'texto fake') -> None:
    monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: texto)
    monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento_de_texto', lambda t: _decisao_holerite_resolvida())


def _resolucao(estado: EstadoResolucaoDimensao, entidade_id: str | None = None) -> ResolucaoDimensao:
    valores = (ReferenciaCanonica('COLABORADOR', entidade_id),) if entidade_id else ()
    return ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=estado, valores_confirmados=valores)


def _eventos_identificacao(ctx: _Contexto, documento_id: str):
    eventos = ctx.repo_hist.listar_por_documento(documento_id)
    return [
        e for e in eventos
        if e.evento == 'ESTEIRA_ETAPA_AVANCADA' and e.detalhes.get('etapa_nova') == 'IDENTIFICACAO'
    ]


# ── 17/18. Holerite novo RESOLVIDO -> IDENTIFICACAO/CONCLUIDO, 1 evento ───────

class TestHoleriteResolvidoAvancaParaIdentificacaoConcluido:
    def test_avanca_para_identificacao_concluido(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO
        assert estado.motivo_bloqueio is None

        resultado_gate = item.resultado_gate_identificacao
        assert resultado_gate is not None
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is True
        assert resultado_gate.etapa_resultante == 'IDENTIFICACAO'
        assert resultado_gate.situacao_resultante == 'CONCLUIDO'
        assert resultado_gate.motivo == MOTIVO_GATE_IDENTIFICACAO_PROMOVIDA

    def test_exatamente_um_evento_de_avanco_para_identificacao(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite unico', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        eventos_identificacao = _eventos_identificacao(ctx, documento_id)
        assert len(eventos_identificacao) == 1


# ── 19. Duplicado não reaplica identificação ──────────────────────────────────

class TestDuplicadoNaoReaplicaIdentificacao:
    def test_duplicado_nao_tenta_identificacao_de_novo(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'),
        )
        conteudo = b'mesmo conteudo holerite duas vezes'
        arquivos = [
            ArquivoEntradaLote(conteudo, 'a.pdf', 'application/pdf'),
            ArquivoEntradaLote(conteudo, 'b.pdf', 'application/pdf'),
        ]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item_original, item_duplicado = resumo.itens

        assert item_original.resultado_gate_identificacao.tentado is True
        assert item_original.resultado_gate_identificacao.sucesso is True
        assert item_duplicado.resultado_gate_identificacao.tentado is False
        assert item_duplicado.resultado_gate_identificacao.motivo == MOTIVO_GATE_IDENTIFICACAO_NAO_APLICAVEL

        eventos_identificacao = _eventos_identificacao(ctx, item_original.documento_id)
        assert len(eventos_identificacao) == 1


# ── 20. Outro tipo documental nunca avança para IDENTIFICACAO ─────────────────

class TestOutroTipoDocumentalNaoAvancaParaIdentificacao:
    @pytest.mark.parametrize('tipo', ['Rescisão', 'Extrato da Folha de Pagamento', 'FGTS', 'Outro'])
    def test_tipo_nao_holerite_nao_tenta_identificacao(self, monkeypatch, tipo):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda t: _decisao_outro_tipo_resolvida(tipo),
        )

        def _nunca_deveria_ser_chamado(texto, candidatos):
            raise AssertionError(f'identificação nunca deveria ser tentada para tipo={tipo!r}')

        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto', _nunca_deveria_ser_chamado,
        )

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True
        resultado_gate = item.resultado_gate_identificacao
        assert resultado_gate.tentado is False
        assert resultado_gate.motivo == MOTIVO_GATE_IDENTIFICACAO_NAO_APLICAVEL

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO  # nunca avançou para IDENTIFICACAO


# ── 21/22/23. Tabela de decisão via a esteira real ────────────────────────────

class TestTabelaDeDecisaoNaEsteira:
    def test_ambigua_vira_identificacao_bloqueado(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.AMBIGUA),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite ambiguo', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.BLOQUEADO
        assert estado.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO
        assert estado.motivo_bloqueio.resolvivel_automaticamente is False
        assert item.resultado_gate_identificacao.motivo == MOTIVO_GATE_IDENTIFICACAO_PROMOVIDA_COM_BLOQUEIO

    def test_nao_encontrada_vira_identificacao_em_revisao(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.NAO_ENCONTRADA),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite nao encontrado', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.EM_REVISAO
        assert estado.motivo_bloqueio is None  # soft-flag, nunca hard-block
        assert item.resultado_gate_identificacao.motivo == MOTIVO_GATE_IDENTIFICACAO_PROMOVIDA_EM_REVISAO

    def test_mestre_suspeito_vira_identificacao_bloqueado(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: MestreSuspeitoIdentificacaoHolerite(quantidade_cpfs_distintos=2),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite mestre suspeito', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.BLOQUEADO
        assert estado.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_PDF_MESTRE_SUSPEITO
        assert estado.motivo_bloqueio.resolvivel_automaticamente is False
        assert estado.motivo_bloqueio.codigo != CODIGO_BLOQUEIO_COLABORADOR_AMBIGUO


# ── 24. Falha técnica da identificação não derruba ItemResumoLote.sucesso ─────

class TestFalhaTecnicaDaIdentificacao:
    def test_falha_na_identificacao_nao_afeta_ingestao_nem_classificacao(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)

        def _identificacao_quebrada(texto, candidatos):
            raise RuntimeError('falha técnica simulada na identificação — nunca deve vazar')

        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto', _identificacao_quebrada,
        )

        arquivos = [ArquivoEntradaLote(b'conteudo holerite com falha', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True  # ingestão nunca afetada
        assert item.roteamento_shadow.sucesso is True  # classificação funcionou
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO  # nunca avançou p/ IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO  # classificação permanece intacta

        resultado_gate = item.resultado_gate_identificacao
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_ERRO_TECNICO_GATE_IDENTIFICACAO
        assert 'falha técnica simulada' not in resultado_gate.motivo


# ── 25. Nenhum CPF/nome/texto aparece nos eventos/DTOs ────────────────────────

class TestSanitizacao:
    def test_nenhum_cpf_nome_ou_texto_bruto_nos_eventos_e_dtos(self, monkeypatch):
        """Usa o pipeline REAL de identificação (não mocka
        resolver_identificacao_holerite_de_texto) com um texto contendo
        CPF/nome de verdade, para provar de ponta a ponta que nada disso
        escapa para eventos ou DTOs."""
        ctx = _montar_servicos(fonte_candidatos=_FonteCandidatosFake([
            CandidatoFuncionario(func_id='func-sigiloso', cpf='123.456.789-01', nome_normalizado='FULANO SIGILOSO'),
        ]))
        texto_sensivel = (
            "Nome do Funcionário\n"
            "001 FULANO SIGILOSO 99999\n"
            "CPF: 123.456.789-01\n"
        )
        _forcar_classificacao_holerite_resolvida(monkeypatch, texto=texto_sensivel)

        arquivos = [ArquivoEntradaLote(b'conteudo holerite sensivel', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        # Confirma que a identificação de fato rodou e resolveu (senão o
        # teste não provaria nada sobre o caminho sensível).
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO

        proibidos = ['123.456.789-01', '12345678901', 'FULANO SIGILOSO', texto_sensivel]

        eventos = ctx.repo_hist.listar_por_documento(item.documento_id)
        for evento in eventos:
            texto_evento = str(evento.detalhes)
            for proibido in proibidos:
                assert proibido not in texto_evento

        import dataclasses
        bruto_item = str(dataclasses.asdict(item))
        for proibido in proibidos:
            assert proibido not in bruto_item


# ── 26. Próxima ação de IDENTIFICACAO/CONCLUIDO não diz "fase futura" ─────────

class TestProximaAcaoIdentificacaoConcluido:
    def test_nao_diz_fase_futura(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        estado = ctx.repo_estados.buscar_por_documento_id(documento_id)
        assert estado.proxima_acao is not None
        assert 'fase futura' not in estado.proxima_acao.acao.lower()
        assert 'identificaç' in estado.proxima_acao.acao.lower()
        # Não afirma que a etapa seguinte (VALIDACAO) já é automática.
        assert 'automátic' not in estado.proxima_acao.acao.lower()


# ── Extração única (item 4 da auditoria) ──────────────────────────────────────

class TestExtracaoUnica:
    def test_extrair_texto_seguro_chamado_uma_unica_vez_por_arquivo(self, monkeypatch):
        chamadas = []

        def _espiao(conteudo):
            chamadas.append(conteudo)
            return 'texto fake'

        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', _espiao)
        monkeypatch.setattr(servico_lote_mod, 'decidir_roteamento_de_texto', lambda t: _decisao_holerite_resolvida())
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'),
        )

        ctx = _montar_servicos()
        arquivos = [ArquivoEntradaLote(b'conteudo holerite unico', 'x.pdf', 'application/pdf')]
        ctx.servico_lote.criar_lote('upload_manual', arquivos)

        # 1 extração para a classificação/identificação -- nunca 2.
        assert len(chamadas) == 1

    def test_candidatos_funcionario_lidos_no_maximo_uma_vez_por_lote(self, monkeypatch):
        fonte = _FonteCandidatosFake()
        ctx = _montar_servicos(fonte_candidatos=fonte)
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.RESOLVIDA, 'func-1'),
        )

        arquivos = [
            ArquivoEntradaLote(f'holerite {i}'.encode(), f'{i}.pdf', 'application/pdf')
            for i in range(3)
        ]
        ctx.servico_lote.criar_lote('upload_manual', arquivos)

        assert fonte.chamadas == 1  # nunca 1 leitura por arquivo

    def test_fonte_nao_e_lida_quando_nenhum_holerite_elegivel(self, monkeypatch):
        fonte = _FonteCandidatosFake()
        ctx = _montar_servicos(fonte_candidatos=fonte)
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda t: _decisao_outro_tipo_resolvida('Rescisão'),
        )

        arquivos = [ArquivoEntradaLote(b'conteudo rescisao', 'x.pdf', 'application/pdf')]
        ctx.servico_lote.criar_lote('upload_manual', arquivos)

        assert fonte.chamadas == 0

    def test_sem_fonte_injetada_identificacao_nunca_e_tentada(self, monkeypatch):
        ctx = _montar_servicos(fonte_candidatos=None)
        # Sobrescreve explicitamente para simular "nenhuma fonte" --
        # _montar_servicos default já cobre isso, mas deixamos explícito
        # aqui para o teste ficar auto-descritivo.
        ctx.servico_lote._fonte_candidatos_funcionario = None
        _forcar_classificacao_holerite_resolvida(monkeypatch)

        def _nunca_deveria_ser_chamado(texto, candidatos):
            raise AssertionError('identificação nunca deveria ser tentada sem fonte de candidatos')

        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto', _nunca_deveria_ser_chamado,
        )

        arquivos = [ArquivoEntradaLote(b'conteudo holerite sem fonte', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True
        assert item.resultado_gate_identificacao.tentado is False
        assert item.resultado_gate_identificacao.motivo == MOTIVO_GATE_IDENTIFICACAO_NAO_APLICAVEL
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO
        assert len(_eventos_identificacao(ctx, item.documento_id)) == 0


# ── Revisão final: falha após bloqueio parcial ────────────────────────────────
# (achado: aplicar_resultado_identificacao usava situacao transitória
# AGUARDANDO antes de registrar_bloqueio -- se registrar_bloqueio falhasse
# no meio do caminho, o documento ficava em IDENTIFICACAO/AGUARDANDO,
# nunca visível como bloqueado. Corrigido: a situacao transitória já
# nasce BLOQUEADO.)

class TestFalhaAposBloqueioParcial:
    def _forcar_registrar_bloqueio_quebrado(self, monkeypatch):
        def _registrar_bloqueio_quebrado(self_avanco, documento_id, motivo, correlation_id):
            raise RuntimeError('falha técnica simulada em registrar_bloqueio — nunca deve vazar')

        monkeypatch.setattr(
            servico_lote_mod.ServicoAvancoEsteira, 'registrar_bloqueio', _registrar_bloqueio_quebrado,
        )

    def test_ambigua_com_falha_em_registrar_bloqueio(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: _resolucao(EstadoResolucaoDimensao.AMBIGUA),
        )
        self._forcar_registrar_bloqueio_quebrado(monkeypatch)

        arquivos = [ArquivoEntradaLote(b'conteudo holerite ambiguo falha', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        # Ingestão nunca é afetada por falha secundária do gate.
        assert item.sucesso is True

        resultado_gate = item.resultado_gate_identificacao
        assert resultado_gate is not None
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_ERRO_TECNICO_GATE_IDENTIFICACAO

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        # avancar_etapa já persistiu com situacao=BLOQUEADO (nasceu
        # bloqueado) antes de registrar_bloqueio falhar -- NUNCA
        # CONCLUIDO, nunca a situação transitória antiga (AGUARDANDO).
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.BLOQUEADO
        assert estado.situacao != SituacaoEsteira.CONCLUIDO
        assert estado.situacao != SituacaoEsteira.AGUARDANDO

        # Mensagem da exceção nunca vaza para DTO nem evento.
        assert 'falha técnica simulada' not in resultado_gate.motivo
        eventos = ctx.repo_hist.listar_por_documento(item.documento_id)
        for evento in eventos:
            assert 'falha técnica simulada' not in str(evento.detalhes)

    def test_mestre_suspeito_com_falha_em_registrar_bloqueio(self, monkeypatch):
        ctx = _montar_servicos()
        _forcar_classificacao_holerite_resolvida(monkeypatch)
        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto',
            lambda texto, candidatos: MestreSuspeitoIdentificacaoHolerite(quantidade_cpfs_distintos=2),
        )
        self._forcar_registrar_bloqueio_quebrado(monkeypatch)

        arquivos = [ArquivoEntradaLote(b'conteudo holerite mestre falha', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True

        resultado_gate = item.resultado_gate_identificacao
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_ERRO_TECNICO_GATE_IDENTIFICACAO

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.IDENTIFICACAO
        assert estado.situacao == SituacaoEsteira.BLOQUEADO
        assert estado.situacao != SituacaoEsteira.CONCLUIDO

        assert 'falha técnica simulada' not in resultado_gate.motivo
        eventos = ctx.repo_hist.listar_por_documento(item.documento_id)
        for evento in eventos:
            assert 'falha técnica simulada' not in str(evento.detalhes)


# ── Revisão final: fonte indisponível (listar_funcionarios lança) ────────────

class TestFonteIndisponivel:
    def test_listar_funcionarios_lanca_excecao(self, monkeypatch):
        class _FonteQuebrada:
            def listar_funcionarios(self):
                raise ConnectionError('Airtable indisponível — nunca deve vazar')

        ctx = _montar_servicos(fonte_candidatos=_FonteQuebrada())
        _forcar_classificacao_holerite_resolvida(monkeypatch)

        def _nunca_deveria_ser_chamado(texto, candidatos):
            raise AssertionError(
                'resolver_identificacao_holerite_de_texto nunca deveria ser '
                'chamado se a fonte de candidatos falhou ao listar')

        monkeypatch.setattr(
            servico_lote_mod, 'resolver_identificacao_holerite_de_texto', _nunca_deveria_ser_chamado,
        )

        arquivos = [ArquivoEntradaLote(b'conteudo holerite fonte quebrada', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        # Ingestão e classificação já realizada permanecem válidas.
        assert item.sucesso is True
        assert item.roteamento_shadow.sucesso is True

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        # Nenhum avanço parcial para IDENTIFICACAO -- falha ocorreu antes
        # de qualquer chamada a aplicar_resultado_identificacao.
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO

        resultado_gate = item.resultado_gate_identificacao
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_ERRO_TECNICO_GATE_IDENTIFICACAO

        assert 'Airtable indisponível' not in resultado_gate.motivo
        import dataclasses
        assert 'Airtable indisponível' not in str(dataclasses.asdict(item))
        eventos = ctx.repo_hist.listar_por_documento(item.documento_id)
        assert len(_eventos_identificacao(ctx, item.documento_id)) == 0
        for evento in eventos:
            assert 'Airtable indisponível' not in str(evento.detalhes)
