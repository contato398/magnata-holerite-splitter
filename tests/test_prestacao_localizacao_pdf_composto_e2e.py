"""Incidente real reproduzido de ponta a ponta, sem transporte:

um PDF de 12 páginas (um holerite por página, 12 colaboradores) chega
por e-mail e fica armazenado como UM Documento. Não há inventário para
ele e o nome do arquivo não diz nada. A Prestação precisa do holerite
de cada colaborador.

    necessidade -> localização (fonte por conteúdo) -> PDF composto
    -> separação por CPF -> Documento derivado (só as páginas daquela
    pessoa) -> corredor -> readiness PRONTO -> Ordem -> Evento
    canônico -> Preview -> Autorização -> ação PENDING

O corredor é substituído na fronteira (mesma convenção de
`test_integracao_prestacao_contato_ate_pending.py`), mas o fake lê o
TEXTO REAL do PDF que recebe e só resolve quando há exatamente 1 CPF:
é o que prova que cada derivado contém só as páginas certas. Todo o
resto é real: extração por página, separação, fatiamento, registro
idempotente, localização, elegibilidade, readiness e o núcleo do
Orquestrador até PENDING. Dados 100% sintéticos.
"""
import logging
from datetime import datetime, timezone
from unittest.mock import patch

from cryptography.fernet import Fernet

from _pdf_sintetico import cpf_sintetico, pdf_com_paginas
import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo_composicao
from magnata_os.central.localizacao import FonteNomeada
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import ContextoComposicaoPrestacao
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao, Cardinalidade, ConfiancaResolucao, DimensaoResolucao,
    EstadoResolucaoDimensao, EstadoResultadoSemantico, NivelConfianca,
    PerfilAplicabilidadeResolucao, ReferenciaCanonica, RegraAplicabilidadeDimensao,
    ResolucaoDimensao, ResultadoResolucaoSemantico,
)
from magnata_os.classificacao.fonte_candidatos_por_conteudo import FonteCandidatosPorConteudo
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
from magnata_os.classificacao.orquestrador_corredor_readonly import ResultadoExecucaoCorredorPrestacao
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao, RequisitoDocumentalPrestacao
from magnata_os.classificacao.resolucao_documento_prestacao import (
    EstadoCorredorDocumentoPrestacao,
    ResultadoProcessamentoDocumentoPrestacao,
)
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP, RegistroContatoColaborador, RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato, cifrar_valor_contato,
)
from magnata_os.documental.derivacao_documental import ORIGEM_DERIVADO_SEPARACAO
from magnata_os.documental.extracao_texto import extrair_texto_pdf_por_pagina
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.importacao_lote.dominio import extrair_cpfs_distintos_de_texto, normalizar_cpf
from magnata_os.documental.modulo01.adaptador_entrada_duravel import AdaptadorEntradaDuravel
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano, RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.resolver_parametros_ordem_prestacao_contato_v1 import (
    construir_resolvedor_parametros_ordem_prestacao_contato_v1,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    executar_prestacao_ate_distribuicao_documental_shadow,
)


AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-09")
CLIENTE = ReferenciaCanonica("CLIENTE", "cliente-sintetico")
CHAVE_FERNET = Fernet.generate_key()
CHAVE_HMAC = b"segredo-hmac-teste"
N = 12


def cpf(i):
    return cpf_sintetico(90000000000 + i)


def colab(i):
    return f"colab-{i:02d}"


PAGINAS = [f"RECIBO DE PAGAMENTO\nColaborador sintetico {i}\nCPF {cpf(i)}\nCompetencia 09/2026" for i in range(1, N + 1)]


# ---- fakes de Prestação (mesmo padrão dos testes de integração existentes) ----

class _RepositorioExecucoesPrestacao:
    def __init__(self):
        self._execucoes = {}

    def criar(self, execucao):
        self._execucoes[execucao.execucao_prestacao_id] = execucao
        return execucao

    def buscar_por_id(self, execucao_prestacao_id):
        return self._execucoes.get(execucao_prestacao_id)

    def atualizar_estado(self, *, execucao_prestacao_id, novo_estado, concluido_em=None, **kwargs):
        import dataclasses
        execucao = dataclasses.replace(self._execucoes[execucao_prestacao_id], estado=novo_estado)
        self._execucoes[execucao_prestacao_id] = execucao
        return execucao


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteClientes:
    def listar_ativos(self, contexto=None):
        return (CLIENTE,)


class _FonteColaboradoresEsperados:
    def __init__(self, ids):
        self._colaboradores = tuple(ReferenciaCanonica("COLABORADOR", i) for i in ids)

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._colaboradores


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao
        self._ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if "INSERT INTO magnata_orquestrador.acoes_execucao_plano" in sql and "RETURNING acao_execucao_id" in sql:
            valores = params[:-4]
            if valores[0] in self.conexao.linhas:
                self._ultimo = None
            else:
                self.conexao.linhas[valores[0]] = valores
                self._ultimo = (valores[0],)
        elif sql.strip().startswith("SELECT") and "acoes_execucao_plano" in sql:
            self._ultimo = self.conexao.linhas.get(params[0])
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo


class _Conexao:
    def __init__(self):
        self.linhas = {}

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass


def _resolucao(documento_id, colaborador, competencia=COMPETENCIA):
    def regra(d):
        return RegraAplicabilidadeDimensao(dimensao=d, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA, cardinalidade=Cardinalidade(1, 1))

    def dim(d, v):
        return ResolucaoDimensao(dimensao=d, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(v,), confianca=ConfiancaResolucao(NivelConfianca.FORTE))

    return ResultadoResolucaoSemantico(
        documento_id=documento_id, resolver_id="resolver-teste", resolver_version="1",
        politica_id="prestacao", politica_version="1",
        perfil=PerfilAplicabilidadeResolucao(
            perfil_id="prestacao-teste", version="1", escopo_documental="prestacao-contas",
            regras=tuple(regra(d) for d in (DimensaoResolucao.CLIENTE, DimensaoResolucao.COMPETENCIA, DimensaoResolucao.COLABORADOR, DimensaoResolucao.TIPO_DOCUMENTAL)),
        ),
        resolucoes=(
            dim(DimensaoResolucao.CLIENTE, CLIENTE), dim(DimensaoResolucao.COMPETENCIA, competencia),
            dim(DimensaoResolucao.COLABORADOR, colaborador),
            dim(DimensaoResolucao.TIPO_DOCUMENTAL, ReferenciaCanonica("TIPO_DOCUMENTAL", TIPO_HOLERITE)),
        ),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA, necessita_revisao_humana=False,
    )


def _corredor_que_le_o_texto_real(chamadas, competencia=COMPETENCIA):
    """Resolve só quando o texto recebido tem exatamente 1 CPF conhecido --
    com 2+ pessoas no mesmo texto, devolve conflito (como o corredor real)."""
    colaborador_por_cpf = {normalizar_cpf(cpf(i)): colab(i) for i in range(1, N + 1)}

    def _fake(contexto_corredor, sink):
        texto = "\n".join(contexto_corredor.paginas)
        cpfs = extrair_cpfs_distintos_de_texto(texto)
        chamadas.append((contexto_corredor.documento_id, len(cpfs)))
        if len(cpfs) != 1 or cpfs[0] not in colaborador_por_cpf:
            return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=ResultadoProcessamentoDocumentoPrestacao(
                documento_id=contexto_corredor.documento_id, estado=EstadoCorredorDocumentoPrestacao.TIPO_CONFLITO,
                motivo="multiplos_colaboradores_no_mesmo_texto",
            )),)
        colaborador = ReferenciaCanonica("COLABORADOR", colaborador_por_cpf[cpfs[0]])
        sink.adicionar(ItemInventarioPrestacao(
            documento_id=contexto_corredor.documento_id, tipo_documental=TIPO_HOLERITE,
            cliente=CLIENTE, competencia=competencia, colaborador=colaborador,
        ))
        return (ResultadoExecucaoCorredorPrestacao(resultado_corredor=ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto_corredor.documento_id, estado=EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU,
            tipo_documental=TIPO_HOLERITE, resolucao_semantica=_resolucao(contexto_corredor.documento_id, colaborador, competencia),
        )),)

    return _fake


def _cenario(*, esperados, com_separacao=True, paginas=None):
    documentos, historico, armazenamento = (
        RepositorioDocumentosEmMemoria(), RepositorioHistoricoEmMemoria(), ArmazenamentoArquivosEmMemoria(),
    )
    entrada = AdaptadorEntradaDuravel(documentos, historico, armazenamento)
    composto = entrada.registrar_entrada(
        pdf_com_paginas(paginas or PAGINAS), "digitalizacao_0042.pdf", "application/pdf", "email", lote_id="lote-email-1",
    )
    candidatos = tuple(CandidatoFuncionario(colab(i), cpf(i), f"sintetico {i}") for i in range(1, N + 2))
    contexto = ContextoComposicaoPrestacao(
        competencia_base="2026-09",
        fonte_clientes=_FonteClientes(),
        fonte_requisitos=_FonteRequisitosVazia(),
        repositorio_execucoes=_RepositorioExecucoesPrestacao(),
        requisitos_base=(RequisitoDocumentalPrestacao(TIPO_HOLERITE),),
        competencias_por_cliente={CLIENTE: COMPETENCIA},
        fonte_colaboradores_esperados=_FonteColaboradoresEsperados(esperados),
        tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
        repositorio_documentos=documentos,
        armazenamento_arquivos=armazenamento,
        candidatos_colaborador=candidatos,
        fontes_localizacao=(
            FonteNomeada("conteudo", FonteCandidatosPorConteudo(documentos, armazenamento, candidatos)),
        ),
        entrada_documentos_derivados=entrada if com_separacao else None,
    )
    contatos = RepositorioContatoColaboradorEmMemoria()
    for i in range(1, N + 2):
        contatos.criar_ou_confirmar(RegistroContatoColaborador(
            colaborador_id=colab(i), canal=CANAL_WHATSAPP,
            valor_cifrado=cifrar_valor_contato(CHAVE_FERNET, f"1199990{i:04d}"),
            hash_auxiliar=calcular_hash_auxiliar_contato(CHAVE_HMAC, f"1199990{i:04d}"),
            versao_chave="v1", origem="teste", criado_em=AGORA, atualizado_em=AGORA,
        ))
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=contatos, chave_fernet=CHAVE_FERNET,
        preset_id="DOCUMENTO_UNITARIO_SEM_ASSINATURA", tipo_documento="HOLERITE",
        montar_mensagem_texto=lambda cliente, competencia: "Segue seu documento",
    )
    conexao = _Conexao()
    deps = {
        "repositorio_documentos": documentos, "armazenamento": armazenamento,
        "repositorio_execucoes": RepositorioExecucoesEmMemoria(),
        "repositorio_autorizacoes": RepositorioAutorizacoesGateEmMemoria(),
        "repositorio_acoes": RepositorioAcoesExecucaoPlanoPostgres(conexao),
    }
    return contexto, resolver, deps, conexao, composto, historico


def _executar(contexto, resolver, deps, chamadas):
    with patch.object(modulo_composicao, "executar_documento_readonly", _corredor_que_le_o_texto_real(chamadas)):
        return executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver, materializador=None, porta_assinatura=None,
            ator_referencia="ator:teste", proveniencia="teste_pdf_composto", instante=AGORA, **deps,
        )


def test_documento_dentro_de_pdf_de_12_paginas_e_encontrado_separado_e_chega_a_pending():
    contexto, resolver, deps, conexao, composto, _ = _cenario(esperados=[colab(i) for i in range(1, N + 1)])
    chamadas = []

    resultados = _executar(contexto, resolver, deps, chamadas)

    assert len(resultados) == N
    por_colaborador = {r.funcionario_id: r for r in resultados}
    assert set(por_colaborador) == {colab(i) for i in range(1, N + 1)}
    assert all(r.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING for r in resultados)

    # o documento enviado ao colab-07 é o derivado, só com a página 7
    documentos = deps["repositorio_documentos"]
    derivados = [d for d in documentos.listar_todos() if d.origem == ORIGEM_DERIVADO_SEPARACAO]
    assert len(derivados) == N
    derivado_07 = next(
        d for d in derivados
        if cpf(7) in "".join(extrair_texto_pdf_por_pagina(deps["armazenamento"].abrir_leitura(d.hash_sha256).read()))
    )
    with deps["armazenamento"].abrir_leitura(derivado_07.hash_sha256) as arquivo:
        paginas = extrair_texto_pdf_por_pagina(arquivo.read())
    assert len(paginas) == 1
    assert cpf(6) not in paginas[0] and cpf(8) not in paginas[0]

    # o corredor nunca recebeu o PDF inteiro, só partes com 1 CPF
    assert all(qtd == 1 for _, qtd in chamadas)
    assert composto.documento_id not in {doc_id for doc_id, _ in chamadas}
    # original preservado
    assert documentos.buscar_por_id(composto.documento_id).hash_sha256 == composto.hash_sha256


def test_sem_separacao_o_mesmo_pdf_nao_atende_ninguem_comportamento_anterior():
    contexto, resolver, deps, conexao, composto, _ = _cenario(
        esperados=[colab(i) for i in range(1, N + 1)], com_separacao=False,
    )
    chamadas = []

    resultados = _executar(contexto, resolver, deps, chamadas)

    assert resultados == ()
    assert conexao.linhas == {}
    assert {qtd for _, qtd in chamadas} == {N}


def test_replay_nao_duplica_derivados_nem_acoes():
    contexto, resolver, deps, conexao, _, _ = _cenario(esperados=[colab(3)])
    _executar(contexto, resolver, deps, [])
    linhas_primeira = dict(conexao.linhas)
    total_documentos = len(deps["repositorio_documentos"].listar_todos())

    _executar(contexto, resolver, deps, [])

    assert conexao.linhas == linhas_primeira
    assert len(deps["repositorio_documentos"].listar_todos()) == total_documentos


def test_colaborador_fora_do_pdf_fica_sem_documento_com_rastro_da_busca(caplog):
    contexto, resolver, deps, conexao, _, _ = _cenario(esperados=[colab(3), colab(13)])

    with caplog.at_level(logging.INFO, logger=modulo_composicao.__name__):
        resultados = _executar(contexto, resolver, deps, [])

    # pacote do cliente fica incompleto: nenhuma ordem sai pela metade
    assert resultados == ()
    eventos = [r for r in caplog.records if getattr(r, "evento", None) == modulo_composicao.EVENTO_LOCALIZACAO_SEM_DOCUMENTO]
    assert [(e.colaborador, e.decisao) for e in eventos] == [(colab(13), "NAO_LOCALIZADO")]
    detalhes = eventos[0].consultas[0]["detalhes"]
    assert detalhes["documentos_analisados"] >= 1
    assert detalhes["documentos_encontrados"] == 0
    assert cpf(13) not in caplog.text


# ---- diagnóstico por necessidade (somente leitura) ----

def _diagnosticar(contexto, competencia=COMPETENCIA):
    with patch.object(modulo_composicao, "executar_documento_readonly", _corredor_que_le_o_texto_real([], competencia)):
        return modulo_composicao.diagnosticar_prestacao(contexto)


def _situacoes(diagnostico):
    return {
        d.necessidade.colaborador.entidade_id: d.situacao.value
        for cliente in diagnostico.clientes for d in cliente.necessidades
    }


def test_diagnostico_aponta_pronto_e_ausente_e_nao_libera_ordem_pela_metade():
    contexto, *_ = _cenario(esperados=[colab(3), colab(13)])

    diagnostico = _diagnosticar(contexto)

    assert _situacoes(diagnostico) == {colab(3): "PRONTO", colab(13): "AUSENTE"}
    assert diagnostico.clientes[0].ordem_pronta is False
    ausente = next(d for d in diagnostico.clientes[0].necessidades if d.situacao.value == "AUSENTE")
    assert ausente.localizacao["decisao"] == "NAO_LOCALIZADO"
    assert ausente.localizacao["consultas"][0]["detalhes"]["documentos_analisados"] >= 1
    texto = repr(diagnostico.como_dict())
    assert cpf(3) not in texto and normalizar_cpf(cpf(3)) not in texto
    assert "Colaborador sintetico" not in texto and "sintetico 3" not in texto  # nome de pessoa nunca


def test_diagnostico_com_todos_presentes_libera_ordem():
    contexto, *_ = _cenario(esperados=[colab(i) for i in range(1, N + 1)])

    diagnostico = _diagnosticar(contexto)

    assert set(_situacoes(diagnostico).values()) == {"PRONTO"}
    assert diagnostico.clientes[0].ordem_pronta is True


def test_diagnostico_sem_separacao_mostra_em_revisao_em_vez_de_vazio():
    contexto, *_ = _cenario(esperados=[colab(5)], com_separacao=False)

    assert _situacoes(_diagnosticar(contexto)) == {colab(5): "EM_REVISAO"}


def test_diagnostico_competencia_errada_e_encontrado_nao_elegivel():
    contexto, *_ = _cenario(esperados=[colab(5)])

    diagnostico = _diagnosticar(contexto, competencia=ReferenciaCanonica("COMPETENCIA", "2026-08"))

    assert _situacoes(diagnostico) == {colab(5): "ENCONTRADO_NAO_ELEGIVEL"}


def test_diagnostico_fonte_quebrada_e_fonte_indisponivel_e_sem_fonte():
    import dataclasses

    class _Quebrada:
        def candidatos_para(self, necessidade):
            raise TimeoutError("fora do ar")

    contexto, *_ = _cenario(esperados=[colab(5)])
    quebrado = dataclasses.replace(contexto, fontes_localizacao=(FonteNomeada("interna", _Quebrada()),))
    sem_fonte = dataclasses.replace(contexto, fontes_localizacao=())

    assert _situacoes(_diagnosticar(quebrado)) == {colab(5): "FONTE_INDISPONIVEL"}
    assert _situacoes(_diagnosticar(sem_fonte)) == {colab(5): "SEM_FONTE"}


# ---- regressões da revisão adversarial ----

def _texto_de(deps, documento_id):
    documento = deps["repositorio_documentos"].buscar_por_id(documento_id)
    with deps["armazenamento"].abrir_leitura(documento.hash_sha256) as arquivo:
        return "\n".join(extrair_texto_pdf_por_pagina(arquivo.read()))


def test_pagina_sem_cpf_ou_com_cpf_sem_formatacao_nunca_entra_na_parte_de_outra_pessoa():
    """Resumo geral da folha (sem CPF) e holerite de outra pessoa com CPF
    sem formatação vinham grudados na parte do colaborador anterior por
    carry-forward -- e seriam enviados a ele."""
    paginas = [
        f"RECIBO\nColaborador sintetico 1\nCPF {cpf(1)}",
        f"RECIBO\nColaborador sintetico 2\nCPF {normalizar_cpf(cpf(2))}",  # sem formatação
        "RESUMO GERAL DA FOLHA\nColaborador sintetico 1 1000,00\nColaborador sintetico 2 2000,00",
        f"RECIBO\nColaborador sintetico 3\nCPF {cpf(3)}\noutro CPF {cpf(4)}",  # 2 CPFs
        f"RECIBO\nColaborador sintetico 5\nCPF {cpf(5)}",
    ]
    contexto, resolver, deps, conexao, _, _ = _cenario(esperados=[colab(1)], paginas=paginas)
    chamadas = []

    resultados = _executar(contexto, resolver, deps, chamadas)

    assert [r.funcionario_id for r in resultados] == [colab(1)]
    texto = _texto_de(deps, chamadas[0][0])
    assert cpf(1) in texto
    assert "RESUMO GERAL" not in texto
    assert normalizar_cpf(cpf(2)) not in texto and "sintetico 2" not in texto
    derivados = [d for d in deps["repositorio_documentos"].listar_todos() if d.origem == ORIGEM_DERIVADO_SEPARACAO]
    # só colab-1 e colab-5 viram partes; página com 2 CPFs fica sem grupo
    assert len(derivados) == 2


def test_rodar_de_novo_nao_acumula_eventos_no_historico():
    contexto, resolver, deps, _, _, historico = _cenario(esperados=[colab(i) for i in range(1, N + 1)])
    _executar(contexto, resolver, deps, [])
    eventos_primeira = len(historico.listar_todos())

    _executar(contexto, resolver, deps, [])

    assert len(historico.listar_todos()) == eventos_primeira
    assert not [e for e in historico.listar_todos() if e.evento == "TENTATIVA_DUPLICADA"]


def test_diagnostico_nao_grava_nada_nos_repositorios_reais():
    contexto, resolver, deps, conexao, _, historico = _cenario(esperados=[colab(i) for i in range(1, N + 1)])
    documentos_antes = len(deps["repositorio_documentos"].listar_todos())
    eventos_antes = len(historico.listar_todos())

    diagnostico = _diagnosticar(contexto)

    assert set(_situacoes(diagnostico).values()) == {"PRONTO"}
    assert len(deps["repositorio_documentos"].listar_todos()) == documentos_antes
    assert len(historico.listar_todos()) == eventos_antes
    assert conexao.linhas == {}


def test_diagnostico_depois_do_ciclo_reaproveita_derivados_reais():
    contexto, resolver, deps, _, _, historico = _cenario(esperados=[colab(2)])
    _executar(contexto, resolver, deps, [])
    eventos = len(historico.listar_todos())

    diagnostico = _diagnosticar(contexto)

    elegiveis = diagnostico.clientes[0].necessidades[0].documentos_elegiveis
    assert len(elegiveis) == 1 and deps["repositorio_documentos"].buscar_por_id(elegiveis[0]) is not None
    assert len(historico.listar_todos()) == eventos
