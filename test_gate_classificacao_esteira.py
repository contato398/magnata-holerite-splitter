"""Teste de integração: gate controlado REGISTRO -> CLASSIFICACAO.

Cobre o ponto de integração real dentro de
`ServicoCriacaoLote._processar_um_arquivo` (servico_lote.py) que aplica
`politica_classificacao.decidir_transicao_classificacao` sobre a MESMA
`DecisaoRoteamentoDocumental` já calculada para o roteamento shadow —
nunca reclassifica, nunca chama `decidir_roteamento()` duas vezes.

Monkeypatch de `extrair_texto_seguro`/`decidir_roteamento_de_texto` (via
`servico_lote_mod` -- bridge de identificação de Holerite avulso, branch
fix/identificacao-holerite-avulso: `servico_lote.py` extrai o texto uma
única vez e decide via essas duas funções, nunca mais
`decidir_roteamento(bytes)` diretamente) torna estes testes
independentes do ambiente de extração de PDF (mesmo padrão já usado em
test_servico_lote_roteamento_shadow.py).
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
from magnata_os.documental.modulo01 import servico_lote as servico_lote_mod
from magnata_os.documental.modulo01.dominio_esteira import EtapaEsteira, SituacaoEsteira
from magnata_os.documental.modulo01.dtos_esteira import (
    MOTIVO_ERRO_TECNICO_GATE_CLASSIFICACAO,
    MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA,
    MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA_COM_BLOQUEIO,
    MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA_EM_REVISAO,
    MOTIVO_GATE_NAO_APLICAVEL,
)
from magnata_os.documental.modulo01.politica_classificacao import (
    CODIGO_BLOQUEIO_AMBIGUA,
    CODIGO_BLOQUEIO_PDF_INVALIDO,
    MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import (
    ServicoAvancoEsteira,
    calcular_proxima_acao,
)
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote

_Contexto = collections.namedtuple(
    '_Contexto', 'repo_docs repo_hist repo_lotes repo_estados servico_avanco servico_lote'
)


def _montar_servicos() -> _Contexto:
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco)

    return _Contexto(repo_docs, repo_hist, repo_lotes, repo_estados, servico_avanco, servico_lote)


def _decisao(estado: EstadoClassificacao, tipo: str = 'Holerite', motivo: MotivoRoteamento = None,
             escopo: EscopoDocumental = EscopoDocumental.COLABORADOR) -> DecisaoRoteamentoDocumental:
    motivo = motivo or {
        EstadoClassificacao.RESOLVIDA: MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
        EstadoClassificacao.AMBIGUA: MotivoRoteamento.CLASSIFICACAO_AMBIGUA,
        EstadoClassificacao.NAO_RECONHECIDA: MotivoRoteamento.TIPO_NAO_RECONHECIDO,
        EstadoClassificacao.INVALIDA: MotivoRoteamento.PDF_INVALIDO,
    }[estado]
    return DecisaoRoteamentoDocumental(
        tipo_documental=tipo,
        estado_classificacao=estado,
        escopo_documental=escopo,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=motivo,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='ALTA',
        evidencias_sanitizadas=('hit',),
        tipos_concorrentes=(),
    )


# ── 1/7. Documento novo RESOLVIDA -> CLASSIFICACAO/CONCLUIDO ──────────────────

class TestDocumentoNovoResolvida:
    def test_avanca_para_classificacao_concluido(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item = resumo.itens[0]
        assert item.sucesso is True
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
        assert estado.situacao == SituacaoEsteira.CONCLUIDO
        assert estado.motivo_bloqueio is None

    def test_exatamente_um_evento_de_avanco_para_classificacao(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite unico', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        eventos = ctx.repo_hist.listar_por_documento(documento_id)
        eventos_classificacao = [
            e for e in eventos
            if e.evento == 'ESTEIRA_ETAPA_AVANCADA' and e.detalhes.get('etapa_nova') == 'CLASSIFICACAO'
        ]
        assert len(eventos_classificacao) == 1
        # Achado da revisão arquitetural: NÃO usa o motivo do roteamento
        # (PROCESSADOR_AINDA_NAO_DISPONIVEL -- pertence à etapa
        # posterior, não à classificação em si).
        assert eventos_classificacao[0].detalhes['motivo_transicao'] != \
            MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL.value
        assert eventos_classificacao[0].detalhes['motivo_transicao'] == \
            MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA

    def test_resultado_gate_indica_promovida(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True  # ingestão nunca afetada pelo gate
        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate is not None
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is True
        assert resultado_gate.etapa_resultante == 'CLASSIFICACAO'
        assert resultado_gate.situacao_resultante == 'CONCLUIDO'
        assert resultado_gate.motivo == MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA


# ── 8. Duplicado: não gera segundo evento CLASSIFICACAO ───────────────────────

class TestDuplicadoNaoRepeteGate:
    def test_duplicado_nao_tenta_transicao_de_novo(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )
        conteudo = b'mesmo conteudo duas vezes'
        arquivos = [
            ArquivoEntradaLote(conteudo, 'a.pdf', 'application/pdf'),
            ArquivoEntradaLote(conteudo, 'b.pdf', 'application/pdf'),
        ]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)

        item_original, item_duplicado = resumo.itens
        assert item_original.duplicado is False
        assert item_duplicado.duplicado is True
        assert item_original.documento_id == item_duplicado.documento_id

        # Shadow ainda roda para o duplicado (observabilidade) --
        # requisito explícito: "shadow pode continuar sendo calculado
        # para observabilidade; não aplicar gate novamente".
        assert item_original.roteamento_shadow is not None
        assert item_duplicado.roteamento_shadow is not None

        # Só 1 evento de avanço para CLASSIFICACAO, nunca 2.
        eventos = ctx.repo_hist.listar_por_documento(item_original.documento_id)
        eventos_classificacao = [
            e for e in eventos
            if e.evento == 'ESTEIRA_ETAPA_AVANCADA' and e.detalhes.get('etapa_nova') == 'CLASSIFICACAO'
        ]
        assert len(eventos_classificacao) == 1

        # Original: gate tentado e promovido. Duplicado: gate NÃO
        # aplicável (nunca reaplica).
        assert item_original.resultado_gate_classificacao.tentado is True
        assert item_original.resultado_gate_classificacao.sucesso is True
        assert item_duplicado.resultado_gate_classificacao.tentado is False
        assert item_duplicado.resultado_gate_classificacao.motivo == MOTIVO_GATE_NAO_APLICAVEL

        estado = ctx.repo_estados.buscar_por_documento_id(item_original.documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO


# ── 9. AMBIGUA: evento de avanço + evento de bloqueio ─────────────────────────

class TestAmbiguaGeraDoisEventos:
    def test_avanco_e_bloqueio_registrados(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.AMBIGUA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo ambiguo', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        estado = ctx.repo_estados.buscar_por_documento_id(documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
        assert estado.situacao == SituacaoEsteira.BLOQUEADO
        assert estado.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_AMBIGUA
        assert estado.motivo_bloqueio.resolvivel_automaticamente is False

        eventos = ctx.repo_hist.listar_por_documento(documento_id)
        assert any(
            e.evento == 'ESTEIRA_ETAPA_AVANCADA' and e.detalhes.get('etapa_nova') == 'CLASSIFICACAO'
            for e in eventos
        )
        assert any(e.evento == 'ESTEIRA_BLOQUEIO_REGISTRADO' for e in eventos)

    def test_resultado_gate_indica_promovida_com_bloqueio_e_motivo_proprio(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.AMBIGUA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo ambiguo 3', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is True
        assert resultado_gate.situacao_resultante == 'BLOQUEADO'
        assert resultado_gate.motivo == MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA_COM_BLOQUEIO

        # AMBIGUA continua com motivo próprio (CLASSIFICACAO_AMBIGUA),
        # distinto do motivo genérico do gate.
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_AMBIGUA

    def test_avancar_etapa_fica_impedido_apos_bloqueio(self, monkeypatch):
        """BLOQUEADO impede avanço posterior até resolver_bloqueio() --
        comportamento já existente, preservado."""
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.AMBIGUA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo ambiguo 2', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        from magnata_os.documental.modulo01.dominio_esteira import AvancoBloqueadoPorPendencia
        with pytest.raises(AvancoBloqueadoPorPendencia):
            ctx.servico_avanco.avancar_etapa(
                documento_id, EtapaEsteira.SEPARACAO, 'corr-teste',
            )


# ── 10. NAO_RECONHECIDA: EM_REVISAO, sem hard-block ───────────────────────────

class TestNaoReconhecidaSemHardBlock:
    def test_em_revisao_sem_motivo_bloqueio(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.NAO_RECONHECIDA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo desconhecido', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        estado = ctx.repo_estados.buscar_por_documento_id(documento_id)
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
        assert estado.situacao == SituacaoEsteira.EM_REVISAO
        assert estado.motivo_bloqueio is None  # soft-flag, nunca hard-block

        # Avanço posterior NÃO é impedido (diferente de BLOQUEADO).
        novo_estado = ctx.servico_avanco.avancar_etapa(
            documento_id, EtapaEsteira.SEPARACAO, 'corr-teste',
        )
        assert novo_estado.etapa_atual == EtapaEsteira.SEPARACAO

    def test_resultado_gate_indica_promovida_em_revisao(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.NAO_RECONHECIDA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo desconhecido 2', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is True
        assert resultado_gate.situacao_resultante == 'EM_REVISAO'
        assert resultado_gate.motivo == MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA_EM_REVISAO
        # Continua distinguível de AMBIGUA/PDF_INVALIDO (motivos distintos).
        assert resultado_gate.motivo != MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA_COM_BLOQUEIO


class TestPdfInvalidoDistinguivel:
    def test_resultado_gate_indica_promovida_com_bloqueio(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.INVALIDA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo invalido', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is True
        assert resultado_gate.situacao_resultante == 'BLOQUEADO'
        assert resultado_gate.motivo == MOTIVO_GATE_CLASSIFICACAO_PROMOVIDA_COM_BLOQUEIO

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_PDF_INVALIDO
        assert estado.motivo_bloqueio.resolvivel_automaticamente is False
        # Distinguível de AMBIGUA por MotivoBloqueio.codigo, mesmo com o
        # mesmo motivo de gate genérico (PROMOVIDA_COM_BLOQUEIO).
        assert estado.motivo_bloqueio.codigo != CODIGO_BLOQUEIO_AMBIGUA


# ── 11. Erro técnico shadow: Documento continua em REGISTRO ───────────────────

class TestErroTecnicoShadowNaoAvanca:
    def test_documento_permanece_em_registro(self, monkeypatch):
        ctx = _montar_servicos()

        def _extrair_texto_quebrado(conteudo):
            raise RuntimeError('falha técnica simulada')

        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', _extrair_texto_quebrado)

        arquivos = [ArquivoEntradaLote(b'conteudo qualquer', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        assert item.sucesso is True
        assert item.roteamento_shadow.sucesso is False  # ERRO_TECNICO_SHADOW

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado.etapa_atual == EtapaEsteira.REGISTRO  # nunca avançou
        assert estado.situacao == SituacaoEsteira.CONCLUIDO  # como já estava

        eventos = ctx.repo_hist.listar_por_documento(item.documento_id)
        assert not any(
            e.evento == 'ESTEIRA_ETAPA_AVANCADA' and e.detalhes.get('etapa_nova') == 'CLASSIFICACAO'
            for e in eventos
        )

        # Gate não era aplicável -- shadow com erro técnico.
        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate is not None
        assert resultado_gate.tentado is False
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_GATE_NAO_APLICAVEL
        assert resultado_gate.etapa_resultante is None
        assert resultado_gate.situacao_resultante is None


# ── Falha REAL/SIMULADA do gate em si (distinta de "gate não aplicável") ──────

class TestFalhaDoGateEmSi:
    """Requisito explícito da revisão: quando decidir_roteamento()
    FUNCIONA e a classificação é RESOLVIDA, mas a PROMOÇÃO do gate em
    si falha (aplicar_resultado_classificacao levanta exceção), isso
    precisa ficar distinguível de "gate não aplicável" -- Documento
    continua registrado, ingestão continua sucesso=True, mas o
    resultado do gate informa explicitamente a falha, sem vazar a
    mensagem da exceção."""

    def test_falha_ao_aplicar_gate_nao_afeta_ingestao(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )

        def _aplicar_quebrado(self, documento_id, decisao_transicao, correlation_id):
            raise RuntimeError('falha simulada na promoção do gate — nunca deve vazar')

        monkeypatch.setattr(
            servico_lote_mod.ServicoAvancoEsteira, 'aplicar_resultado_classificacao', _aplicar_quebrado,
        )

        arquivos = [ArquivoEntradaLote(b'conteudo holerite com falha de gate', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        # Documento continua registrado; ingestão continua sucesso.
        assert item.sucesso is True
        assert item.documento_id is not None
        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        assert estado is not None
        assert estado.etapa_atual == EtapaEsteira.REGISTRO  # nunca avançou

        # Roteamento shadow continua correto (classificação funcionou).
        assert item.roteamento_shadow is not None
        assert item.roteamento_shadow.sucesso is True
        assert item.roteamento_shadow.tipo_documental == 'Holerite'

        # Resultado do gate informa a falha explicitamente.
        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate is not None
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_ERRO_TECNICO_GATE_CLASSIFICACAO
        assert resultado_gate.etapa_resultante is None
        assert resultado_gate.situacao_resultante is None

        # Mensagem da exceção NUNCA vaza.
        assert 'falha simulada' not in resultado_gate.motivo

    def test_ambigua_com_falha_em_registrar_bloqueio_permanece_bloqueado(self, monkeypatch):
        """Revisão final (mesmo achado e mesma correção já aplicados em
        aplicar_resultado_identificacao): quando a decisão de
        classificação exige bloqueio (AMBIGUA), a situação transitória
        passada a avancar_etapa já nasce BLOQUEADO -- se
        registrar_bloqueio falhar DEPOIS de avancar_etapa já ter
        persistido, o documento nunca fica em CLASSIFICACAO/AGUARDANDO
        (que pareceria "ainda não processado") nem em
        CLASSIFICACAO/CONCLUIDO -- permanece CLASSIFICACAO/BLOQUEADO,
        visivelmente pendente de revisão."""
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.AMBIGUA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )

        def _registrar_bloqueio_quebrado(self_avanco, documento_id, motivo, correlation_id):
            raise RuntimeError('falha técnica simulada em registrar_bloqueio — nunca deve vazar')

        monkeypatch.setattr(
            servico_lote_mod.ServicoAvancoEsteira, 'registrar_bloqueio', _registrar_bloqueio_quebrado,
        )

        arquivos = [ArquivoEntradaLote(b'conteudo ambiguo com falha de bloqueio', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        item = resumo.itens[0]

        # Ingestão nunca é afetada por falha secundária do gate.
        assert item.sucesso is True

        resultado_gate = item.resultado_gate_classificacao
        assert resultado_gate is not None
        assert resultado_gate.tentado is True
        assert resultado_gate.sucesso is False
        assert resultado_gate.motivo == MOTIVO_ERRO_TECNICO_GATE_CLASSIFICACAO

        estado = ctx.repo_estados.buscar_por_documento_id(item.documento_id)
        # avancar_etapa já persistiu com situacao=BLOQUEADO (nasceu
        # bloqueado) antes de registrar_bloqueio falhar -- motivo_bloqueio
        # pode estar None porque a segunda gravação falhou, mas a
        # situação NUNCA regride para AGUARDANDO nem avança para
        # CONCLUIDO, e o próximo avanço continua impedido.
        assert estado.etapa_atual == EtapaEsteira.CLASSIFICACAO
        assert estado.situacao == SituacaoEsteira.BLOQUEADO
        assert estado.situacao != SituacaoEsteira.CONCLUIDO
        assert estado.situacao != SituacaoEsteira.AGUARDANDO

        from magnata_os.documental.modulo01.dominio_esteira import AvancoBloqueadoPorPendencia
        with pytest.raises(AvancoBloqueadoPorPendencia):
            ctx.servico_avanco.avancar_etapa(item.documento_id, EtapaEsteira.SEPARACAO, 'corr-teste')

        # Mensagem da exceção nunca vaza para DTO nem evento.
        assert 'falha técnica simulada' not in resultado_gate.motivo
        eventos = ctx.repo_hist.listar_por_documento(item.documento_id)
        for evento in eventos:
            assert 'falha técnica simulada' not in str(evento.detalhes)


# ── 12. Nenhum texto/PII nos eventos ──────────────────────────────────────────

class TestEventosSanitizados:
    def test_evento_de_avanco_nao_contem_pii(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )
        arquivos = [ArquivoEntradaLote(b'CPF: 123.456.789-01 texto qualquer', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        eventos = ctx.repo_hist.listar_por_documento(documento_id)
        for evento in eventos:
            texto_evento = str(evento.detalhes).lower()
            assert '123.456.789' not in texto_evento
            assert 'cpf' not in texto_evento

    def test_evento_de_bloqueio_ambigua_nao_contem_pii(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.AMBIGUA, tipo='Outro', escopo=EscopoDocumental.DESCONHECIDO),
        )
        arquivos = [ArquivoEntradaLote(b'nome: Joao da Silva, CNPJ 12.345.678/0001-90', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        eventos = ctx.repo_hist.listar_por_documento(documento_id)
        for evento in eventos:
            texto_evento = str(evento.detalhes).lower()
            assert 'joao' not in texto_evento
            assert '12.345.678' not in texto_evento


# ── 13. Próxima ação em CLASSIFICACAO não pode dizer "fase futura" ────────────

class TestProximaAcaoAtualizada:
    def test_classificacao_concluido_nao_diz_fase_futura(self, monkeypatch):
        ctx = _montar_servicos()
        monkeypatch.setattr(servico_lote_mod, 'extrair_texto_seguro', lambda conteudo: 'texto fake')
        monkeypatch.setattr(
            servico_lote_mod, 'decidir_roteamento_de_texto',
            lambda texto: _decisao(EstadoClassificacao.RESOLVIDA),
        )
        arquivos = [ArquivoEntradaLote(b'conteudo holerite', 'x.pdf', 'application/pdf')]
        resumo = ctx.servico_lote.criar_lote('upload_manual', arquivos)
        documento_id = resumo.itens[0].documento_id

        estado = ctx.repo_estados.buscar_por_documento_id(documento_id)
        assert estado.proxima_acao is not None
        assert 'implementacao em fase futura' not in estado.proxima_acao.acao.lower()
        assert 'implementação em fase futura' not in estado.proxima_acao.acao.lower()
        assert 'classifica' in estado.proxima_acao.acao.lower()

    def test_calcular_proxima_acao_direto_para_classificacao_concluido(self):
        """Teste direto da função pura, sem passar pelo lote."""
        proxima = calcular_proxima_acao(EtapaEsteira.CLASSIFICACAO, SituacaoEsteira.CONCLUIDO)
        assert proxima is not None
        assert 'fase futura' not in proxima.acao.lower()

    def test_classificacao_bloqueada_continua_dizendo_resolver_bloqueio(self):
        """Só o caso CONCLUIDO foi ajustado -- BLOQUEADO/EM_REVISAO
        continuam com suas próprias mensagens já corretas (não regride)."""
        from magnata_os.documental.modulo01.dominio_esteira import MotivoBloqueio
        motivo = MotivoBloqueio('CLASSIFICACAO_AMBIGUA', 'ambiguidade', None, False)
        proxima = calcular_proxima_acao(EtapaEsteira.CLASSIFICACAO, SituacaoEsteira.BLOQUEADO, motivo)
        assert 'resolver bloqueio' in proxima.acao.lower()
