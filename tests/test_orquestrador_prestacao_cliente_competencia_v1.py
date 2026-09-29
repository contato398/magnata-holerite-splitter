"""J4 -- "Prestação do cliente X, competência Y" composta pelas fontes reais
(adapters Airtable somente leitura REAIS sobre um leitor fake; Postgres
e S3 substituídos pelas implementações em memória equivalentes).

O corredor semântico é substituído na fronteira pelo mesmo fake dos
testes de PDF composto (lê o texto real do PDF recebido). Todo o resto
é o código de produção: adapters de clientes, colaboradores esperados,
vínculos, requisitos canônicos, política de competência, localização
por conteúdo, separação de PDF composto, diagnóstico e o núcleo do
Orquestrador até PENDING.
"""
from unittest.mock import patch

import pytest

from _pdf_sintetico import pdf_com_paginas
from test_prestacao_localizacao_pdf_composto_e2e import (
    AGORA, CHAVE_FERNET, CHAVE_HMAC, CLIENTE, _Conexao, _corredor_que_le_o_texto_real, colab, cpf,
)
import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo_composicao
from magnata_os.classificacao.competencia_esperada_prestacao import REFERENCIA_CLIENTE_SKY_TATUI
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP, RegistroContatoColaborador, RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato, cifrar_valor_contato,
)
from magnata_os.documental.importacao_lote.adapters.airtable_clientes_prestacao import F_CLI_STATUS
from magnata_os.documental.importacao_lote.adapters.airtable_colaboradores_esperados_prestacao import F_FUNC_STATUS
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import TABLE_CLIENTES, TABLE_FUNC
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS, F_LOCAL_CLIENTE, TABLE_LOCAIS,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoCliente, CandidatoFuncionario
from magnata_os.documental.modulo01.adaptador_entrada_duravel import AdaptadorEntradaDuravel
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria
from magnata_os.documental.modulo01.repositorio_esteira import RepositorioLotesEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.composicao_prestacao_real_v1 import (
    ClienteNaoAtivo, DependenciasPrestacaoReal, FonteClienteUnico, montar_contexto_prestacao,
)
from magnata_os.orquestrador.executar_prestacao_contato_ate_pending_shadow_v1 import (
    executar_prestacao_contato_ate_pending_shadow_v1,
)
from magnata_os.orquestrador.prestacao_cliente_competencia_v1 import (
    _parse_args, executar_prestacao_cliente_competencia,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import RepositorioAcoesExecucaoPlanoPostgres
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria

N = 3
OUTRO_CLIENTE = "cliente-inativo"
CNPJ_CLIENTE = "11.111.111/0001-11"
CNPJ_OUTRO = "22.222.222/0001-22"
TIPOS_CLIENTE = (
    "DCTFWeb - Declaração", "DCTFWeb - Recibo de Entrega", "Extrato da Folha de Pagamento",
    "FGTS", "Guia DCTFWeb/DARF",
)


class _LeitorAirtableFake:
    """Mesma superfície somente leitura de `LeitorAirtableSomenteLeitura`;
    tabelas mínimas: Clientes (status), Locais (-> cliente), Funcionários
    (-> locais, status, CPF). Dados sintéticos."""

    def __init__(self, colaboradores=N):
        self.tabelas = {
            TABLE_CLIENTES: [
                {"id": CLIENTE.entidade_id, "fields": {F_CLI_STATUS: "Ativo"}},
                {"id": OUTRO_CLIENTE, "fields": {F_CLI_STATUS: "Inativo"}},
            ],
            TABLE_LOCAIS: [{"id": "local-1", "fields": {F_LOCAL_CLIENTE: [CLIENTE.entidade_id]}}],
            TABLE_FUNC: [
                {"id": colab(i), "fields": {F_FUNC_LOCAIS: ["local-1"], F_FUNC_STATUS: "Ativo"}}
                for i in range(1, colaboradores + 1)
            ],
        }
        self.colaboradores = colaboradores

    def listar_registros(self, table_id, fields=None, filter_by_formula=None, **kwargs):
        registros = self.tabelas.get(table_id, [])
        if filter_by_formula:
            registros = [r for r in registros if r["id"] in filter_by_formula]
        return registros

    def listar_funcionarios(self):
        self.chamadas_funcionarios = getattr(self, "chamadas_funcionarios", 0) + 1
        return [CandidatoFuncionario(colab(i), cpf(i), f"sintetico {i}") for i in range(1, self.colaboradores + 1)]

    def listar_clientes(self):
        self.chamadas_clientes = getattr(self, "chamadas_clientes", 0) + 1
        return [
            CandidatoCliente(CLIENTE.entidade_id, CNPJ_CLIENTE, "cliente sintetico"),
            CandidatoCliente(OUTRO_CLIENTE, CNPJ_OUTRO, "outro sintetico"),
        ]


class _UnidadePostoHistoricaVazia:
    def resolver_unidade_posto(self, colaborador, competencia):
        raise AssertionError("o corredor fake não resolve unidade/posto")


class _RepositorioExecucoesPrestacao:
    def __init__(self):
        self.execucoes = {}

    def criar(self, execucao):
        self.execucoes[execucao.execucao_prestacao_id] = execucao
        return execucao

    def buscar_por_id(self, execucao_prestacao_id):
        return self.execucoes.get(execucao_prestacao_id)


def _documentos_do_cliente(cnpj=CNPJ_CLIENTE, tipos=TIPOS_CLIENTE):
    """Um PDF por documento institucional, com nome de arquivo inútil."""
    return [[f"TIPO: {tipo}\nEmpresa CNPJ {cnpj}\nCompetencia 09/2026"] for tipo in tipos]


def _dependencias(paginas, colaboradores=N, documentos_cliente=None):
    documentos, historico, armazenamento = (
        RepositorioDocumentosEmMemoria(), RepositorioHistoricoEmMemoria(), ArmazenamentoArquivosEmMemoria(),
    )
    entrada = AdaptadorEntradaDuravel(documentos, historico, armazenamento)
    entrada.registrar_entrada(pdf_com_paginas(paginas), "scan_0001.pdf", "application/pdf", "email")
    for i, paginas_cliente in enumerate(_documentos_do_cliente() if documentos_cliente is None else documentos_cliente):
        entrada.registrar_entrada(pdf_com_paginas(paginas_cliente), f"scan_{i + 2:04d}.pdf", "application/pdf", "email")
    return DependenciasPrestacaoReal(
        leitor_airtable=_LeitorAirtableFake(colaboradores),
        repositorio_documentos=documentos, repositorio_historico=historico,
        repositorio_lotes=RepositorioLotesEmMemoria(),
        repositorio_execucoes_prestacao=_RepositorioExecucoesPrestacao(),
        armazenamento=armazenamento, fonte_unidade_posto_historica=_UnidadePostoHistoricaVazia(),
    )


PAGINAS = [f"RECIBO DE PAGAMENTO\nColaborador sintetico {i}\nCPF {cpf(i)}" for i in range(1, N + 1)]


def _executar_ate_pending(deps):
    contatos = RepositorioContatoColaboradorEmMemoria()
    for i in range(1, N + 1):
        contatos.criar_ou_confirmar(RegistroContatoColaborador(
            colaborador_id=colab(i), canal=CANAL_WHATSAPP,
            valor_cifrado=cifrar_valor_contato(CHAVE_FERNET, f"1199990{i:04d}"),
            hash_auxiliar=calcular_hash_auxiliar_contato(CHAVE_HMAC, f"1199990{i:04d}"),
            versao_chave="v1", origem="teste", criado_em=AGORA, atualizado_em=AGORA,
        ))
    conexao = _Conexao()

    def _executar(*, contexto, instante):
        return executar_prestacao_contato_ate_pending_shadow_v1(
            contexto=contexto, repositorio_contato=contatos, chave_fernet=CHAVE_FERNET,
            preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", tipo_documento="PRESTACAO_CONTAS",
            montar_mensagem_texto=lambda cliente, competencia: "Segue seu documento",
            repositorio_documentos=deps.repositorio_documentos, armazenamento=deps.armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_execucoes=RepositorioExecucoesEmMemoria(),
            repositorio_autorizacoes=RepositorioAutorizacoesGateEmMemoria(),
            repositorio_acoes=RepositorioAcoesExecucaoPlanoPostgres(conexao),
            ator_referencia="ator:teste", proveniencia="teste_j4", instante=instante,
        )

    return _executar, conexao


def _corredor_com_documentos_de_cliente():
    """Documentos com CPF: o mesmo fake dos testes de PDF composto.
    Documentos institucionais: lê TIPO e CNPJ do texto real; resolve só
    quando há exatamente 1 CNPJ conhecido e 1 tipo."""
    import re

    from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
    from magnata_os.classificacao.resolucao_documento_prestacao import (
        EstadoCorredorDocumentoPrestacao, ResultadoProcessamentoDocumentoPrestacao,
    )
    from magnata_os.classificacao.orquestrador_corredor_readonly import ResultadoExecucaoCorredorPrestacao
    from test_prestacao_localizacao_pdf_composto_e2e import COMPETENCIA, _resolucao

    por_cpf = _corredor_que_le_o_texto_real([])
    clientes_por_cnpj = {CNPJ_CLIENTE: CLIENTE, CNPJ_OUTRO: ReferenciaCanonica("CLIENTE", OUTRO_CLIENTE)}

    def _fake(contexto_corredor, sink):
        texto = "\n".join(contexto_corredor.paginas)
        cnpjs = set(re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto))
        tipos = re.findall(r"TIPO: (.+)", texto)
        if not cnpjs:
            return por_cpf(contexto_corredor, sink)
        if len(cnpjs) != 1 or len(set(tipos)) != 1 or next(iter(cnpjs)) not in clientes_por_cnpj:
            return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=ResultadoProcessamentoDocumentoPrestacao(
                documento_id=contexto_corredor.documento_id, estado=EstadoCorredorDocumentoPrestacao.TIPO_CONFLITO,
            )),)
        cliente, tipo = clientes_por_cnpj[next(iter(cnpjs))], tipos[0].strip()
        sink.adicionar(ItemInventarioPrestacao(
            documento_id=contexto_corredor.documento_id, tipo_documental=tipo, cliente=cliente, competencia=COMPETENCIA,
        ))
        resolucao = _resolucao_institucional(contexto_corredor.documento_id, cliente, tipo)
        return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto_corredor.documento_id, estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
            tipo_documental=tipo, resolucao_semantica=resolucao,
        )),)

    return _fake


def _resolucao_institucional(documento_id, cliente, tipo):
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao, Cardinalidade, ConfiancaResolucao, DimensaoResolucao, EstadoResolucaoDimensao,
        EstadoResultadoSemantico, NivelConfianca, PerfilAplicabilidadeResolucao, RegraAplicabilidadeDimensao,
        ResolucaoDimensao, ResultadoResolucaoSemantico,
    )
    from test_prestacao_localizacao_pdf_composto_e2e import COMPETENCIA

    def regra(d):
        return RegraAplicabilidadeDimensao(dimensao=d, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA, cardinalidade=Cardinalidade(1, 1))

    def dim(d, v):
        return ResolucaoDimensao(dimensao=d, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(v,),
                                 confianca=ConfiancaResolucao(NivelConfianca.FORTE))

    dimensoes = (DimensaoResolucao.CLIENTE, DimensaoResolucao.COMPETENCIA, DimensaoResolucao.TIPO_DOCUMENTAL)
    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id="resolver-teste", resolver_version="1",
        politica_id="prestacao", politica_version="1",
        perfil=PerfilAplicabilidadeResolucao(perfil_id="institucional-teste", version="1",
                                             escopo_documental="prestacao-contas", regras=tuple(regra(d) for d in dimensoes)),
        resolucoes=(dim(DimensaoResolucao.CLIENTE, cliente), dim(DimensaoResolucao.COMPETENCIA, COMPETENCIA),
                    dim(DimensaoResolucao.TIPO_DOCUMENTAL, ReferenciaCanonica("TIPO_DOCUMENTAL", tipo))),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA, necessita_revisao_humana=False,
    )


def _com_corredor_fake():
    return patch.object(modulo_composicao, "executar_documento_readonly", _corredor_com_documentos_de_cliente())


def test_contexto_usa_fontes_reais_restritas_a_um_cliente():
    deps = _dependencias(PAGINAS)

    contexto = montar_contexto_prestacao(cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps)

    assert isinstance(contexto.fonte_clientes, FonteClienteUnico)
    assert contexto.fonte_clientes.listar_ativos() == (CLIENTE,)
    assert contexto.competencias_por_cliente == {CLIENTE: ReferenciaCanonica("COMPETENCIA", "2026-09")}
    assert [f.nome for f in contexto.fontes_localizacao] == ["conteudo"]
    assert contexto.fontes_localizacao[0].data_versao is not None  # e-mail mais recente vale
    assert contexto.entrada_documentos_derivados is not None
    assert len(contexto.candidatos_colaborador) == N


def test_cliente_inativo_ou_competencia_invalida_falham_fechado():
    deps = _dependencias(PAGINAS)
    with pytest.raises(ClienteNaoAtivo):
        montar_contexto_prestacao(cliente_id=OUTRO_CLIENTE, competencia_base="2026-09", dependencias=deps)
    with pytest.raises(ValueError):
        montar_contexto_prestacao(cliente_id=CLIENTE.entidade_id, competencia_base="09/2026", dependencias=deps)
    with pytest.raises(ValueError):
        montar_contexto_prestacao(cliente_id=CLIENTE.entidade_id, competencia_base="2026-13", dependencias=deps)


def test_competencia_esperada_segue_a_politica_do_cliente():
    deps = _dependencias(PAGINAS)
    deps.leitor_airtable.tabelas[TABLE_CLIENTES].append(
        {"id": REFERENCIA_CLIENTE_SKY_TATUI.entidade_id, "fields": {F_CLI_STATUS: "Ativo"}},
    )

    contexto = montar_contexto_prestacao(
        cliente_id=REFERENCIA_CLIENTE_SKY_TATUI.entidade_id, competencia_base="2026-07", dependencias=deps,
    )

    assert contexto.competencias_por_cliente == {
        REFERENCIA_CLIENTE_SKY_TATUI: ReferenciaCanonica("COMPETENCIA", "2026-06"),
    }


def test_diagnostico_do_cliente_encontra_os_documentos_dentro_do_pdf_composto_sem_gravar_nada():
    deps = _dependencias(PAGINAS)
    documentos_antes = len(deps.repositorio_documentos.listar_todos())

    with _com_corredor_fake():
        relatorio = executar_prestacao_cliente_competencia(
            cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps,
        )

    assert relatorio["modo"] == "diagnostico"
    cliente = relatorio["clientes"][0]
    assert cliente["ordem_pronta"] is True
    assert {(n["tipo_documental"], n["colaborador"]): n["situacao"] for n in cliente["necessidades"]} == {
        **{("Holerite", colab(i)): "PRONTO" for i in range(1, N + 1)},
        **{(tipo, None): "PRONTO" for tipo in TIPOS_CLIENTE},
    }
    assert len(deps.repositorio_documentos.listar_todos()) == documentos_antes
    # cache por execução: nada de uma chamada à API por página
    assert deps.leitor_airtable.chamadas_clientes == 1 and deps.leitor_airtable.chamadas_funcionarios == 1


def test_ate_pending_gera_uma_ordem_por_colaborador_sem_transporte():
    deps = _dependencias(PAGINAS)
    executar, conexao = _executar_ate_pending(deps)

    with _com_corredor_fake():
        relatorio = executar_prestacao_cliente_competencia(
            cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps,
            ate_pending=True, executar_ate_pending=executar, instante=AGORA,
        )

    assert sorted(o["funcionario_id"] for o in relatorio["ordens"]) == [colab(i) for i in range(1, N + 1)]
    assert {o["estado_acao"] for o in relatorio["ordens"]} == {"PENDING"}
    assert conexao.linhas


def test_pacote_incompleto_nao_gera_ordem_e_diz_o_que_falta():
    deps = _dependencias(PAGINAS, colaboradores=N + 1)  # colab-04 esperado, fora do PDF
    executar, conexao = _executar_ate_pending(deps)

    with _com_corredor_fake():
        relatorio = executar_prestacao_cliente_competencia(
            cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps,
            ate_pending=True, executar_ate_pending=executar, instante=AGORA,
        )

    assert relatorio["ordens"] == [] and relatorio["ordens_motivo"] == "pacote_nao_pronto"
    assert conexao.linhas == {}
    ausentes = [n["colaborador"] for n in relatorio["clientes"][0]["necessidades"] if n["situacao"] == "AUSENTE"]
    assert ausentes == [colab(N + 1)]


def test_linha_de_comando_exige_preset_e_mensagem_para_ir_ate_pending():
    assert _parse_args(["--cliente", "rec1", "--competencia", "2026-09"]).ate_pending is False
    with pytest.raises(SystemExit):
        _parse_args(["--cliente", "rec1", "--competencia", "2026-09", "--ate-pending"])


def test_documento_institucional_de_outro_cliente_nunca_atende_este_cliente():
    documentos = _documentos_do_cliente(tipos=TIPOS_CLIENTE[:-1]) + _documentos_do_cliente(
        cnpj=CNPJ_OUTRO, tipos=TIPOS_CLIENTE[-1:],
    )
    deps = _dependencias(PAGINAS, documentos_cliente=documentos)

    with _com_corredor_fake():
        relatorio = executar_prestacao_cliente_competencia(
            cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps,
        )

    situacoes = {n["tipo_documental"]: n["situacao"] for n in relatorio["clientes"][0]["necessidades"] if n["colaborador"] is None}
    assert situacoes[TIPOS_CLIENTE[-1]] == "AUSENTE"
    assert relatorio["clientes"][0]["ordem_pronta"] is False


def test_documento_institucional_nunca_vira_ordem_de_colaborador():
    deps = _dependencias(PAGINAS)
    executar, _ = _executar_ate_pending(deps)

    with _com_corredor_fake():
        relatorio = executar_prestacao_cliente_competencia(
            cliente_id=CLIENTE.entidade_id, competencia_base="2026-09", dependencias=deps,
            ate_pending=True, executar_ate_pending=executar, instante=AGORA,
        )

    assert sorted(o["funcionario_id"] for o in relatorio["ordens"]) == [colab(i) for i in range(1, N + 1)]
