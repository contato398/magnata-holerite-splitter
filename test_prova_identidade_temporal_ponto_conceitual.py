"""Prova de viabilidade CONCEITUAL, isolada e sintética (missão
"IDENTIDADE TEMPORAL DO PDF DE FOLHA/CARTÃO DE PONTO V1" — fase de
auditoria/proposta, ver `docs/decisoes/identidade-temporal-ponto-
auditoria-v1.md`).

NÃO é código de produção, não é importado por nenhum módulo real, não
se conecta a Airtable/Postgres/rede. Demonstra só que o PIPELINE
CONCEITUAL é viável em memória:

    PDF sintético (texto)
    -> extração pura de período (mesma regex-padrão de
       app.py::_PERIODO_CARTAO_PONTO_RE, REIMPLEMENTADA aqui — nunca
       importada de app.py, legado protegido)
    -> resolução de competência (fechamento do período)
    -> objeto canônico em memória (equivalente a
       `resolucao_documental_temporal`, proposto, NÃO IMPLEMENTADO)
    -> resolução de colaborador -> cliente via alocação histórica
       SINTÉTICA (dict em memória, consultada por DATA — nunca pelo
       cadastro atual)

Nenhuma informação de competência é escrita em nenhum lugar — tudo
fica em memória, dentro do teste."""
import ast
import dataclasses
import datetime
import hashlib
import inspect
import re
from typing import Optional

# Reaproveitamento REAL confirmado (revisão independente): a cardinalidade
# múltipla de cliente (transferência de posto dentro do período do
# documento) já tem representação pronta em ResolucaoDimensao
# (magnata_os/classificacao/contratos.py) -- nunca uma modelagem nova.
# Importar aqui não viola o isolamento da prova: é módulo de domínio puro
# já existente do próprio Magnata OS, nunca Airtable/requests/app.py.
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)

# ---------------------------------------------------------------------------
# 1) Extração pura de período (prova) -- mesma forma de
#    "Período: dd/mm/aaaa até dd/mm/aaaa" já validada contra PDF real em
#    app.py::_PERIODO_CARTAO_PONTO_RE. Reimplementada aqui SÓ para a
#    prova -- nunca importa app.py.
# ---------------------------------------------------------------------------
_PADRAO_PERIODO = re.compile(
    r'Per[íi]odo:\s*(\d{2})/(\d{2})/(\d{4})\s*at[ée]\s*(\d{2})/(\d{2})/(\d{4})',
    re.IGNORECASE,
)


def extrair_periodo_do_texto(texto: str) -> Optional[tuple]:
    """Devolve (data_inicio, data_fim) como `datetime.date`, ou `None`
    se o período não estiver declarado explicitamente no texto -- nunca
    infere de nome de arquivo/data de upload."""
    m = _PADRAO_PERIODO.search(texto or '')
    if not m:
        return None
    d1, m1, a1, d2, m2, a2 = m.groups()
    try:
        inicio = datetime.date(int(a1), int(m1), int(d1))
        fim = datetime.date(int(a2), int(m2), int(d2))
    except ValueError:
        return None
    if fim < inicio:
        return None
    return inicio, fim


def competencia_do_periodo(periodo_fim: datetime.date) -> str:
    """Competência = mês/ano do FECHAMENTO do período (mesma convenção
    já adotada para ciclos deslocados). Formato canônico 'AAAA-MM'."""
    return f'{periodo_fim.year:04d}-{periodo_fim.month:02d}'


# ---------------------------------------------------------------------------
# 2) Objeto canônico em memória -- equivalente ILUSTRATIVO da tabela
#    proposta `resolucao_documental_temporal` (NÃO implementada, NÃO é
#    um modelo de produção real).
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class _ResolucaoDocumentalTemporalConceitual:
    documento_id: str
    tipo_documental: str
    colaborador_id: Optional[str]
    periodo_inicio: Optional[datetime.date]
    periodo_fim: Optional[datetime.date]
    competencia: Optional[str]
    estado_resolucao: str


def resolver_documento_conceitual(
    conteudo_pdf: bytes, texto_extraido: str, colaborador_id: str,
) -> _ResolucaoDocumentalTemporalConceitual:
    documento_id = hashlib.sha256(conteudo_pdf).hexdigest()
    periodo = extrair_periodo_do_texto(texto_extraido)
    if periodo is None:
        return _ResolucaoDocumentalTemporalConceitual(
            documento_id=documento_id, tipo_documental='Folha de Ponto',
            colaborador_id=colaborador_id, periodo_inicio=None, periodo_fim=None,
            competencia=None, estado_resolucao='NAO_ENCONTRADA',
        )
    inicio, fim = periodo
    return _ResolucaoDocumentalTemporalConceitual(
        documento_id=documento_id, tipo_documental='Folha de Ponto',
        colaborador_id=colaborador_id, periodo_inicio=inicio, periodo_fim=fim,
        competencia=competencia_do_periodo(fim), estado_resolucao='RESOLVIDA',
    )


# ---------------------------------------------------------------------------
# 3) Vínculo histórico SINTÉTICO -- simula a consulta que, com um
#    Postgres real, seria feita contra `alocacao` (vigente_de/
#    vigente_ate) -- por DATA, nunca pelo cadastro atual.
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class _AlocacaoSintetica:
    colaborador_id: str
    cliente_id: str
    vigente_de: datetime.date
    vigente_ate: Optional[datetime.date]


def resolver_clientes_por_periodo_documental(
    alocacoes, colaborador_id: str, periodo_inicio: datetime.date, periodo_fim: datetime.date,
) -> ResolucaoDimensao:
    """Resolve cliente(s) por INTERSEÇÃO temporal entre o período do
    documento e as alocações do colaborador -- nunca por um único ponto
    no tempo (um PDF cobre um INTERVALO de dias; o colaborador pode ter
    tido mais de uma alocação válida dentro dele -- transferência de
    posto no meio do ciclo). Reaproveita `ResolucaoDimensao`
    (`classificacao/contratos.py`) já existente: `valores_confirmados`
    já é uma tupla, já suporta N clientes legítimos sem modelagem nova
    -- MESMO mecanismo já usado para "vínculo múltiplo genuíno" de
    Holerite (`adaptador_inventario_prestacao.py::
    itens_para_multiplos_clientes_do_vinculo`)."""
    clientes = []
    for a in alocacoes:
        if a.colaborador_id != colaborador_id:
            continue
        fim_efetivo = a.vigente_ate  # None = vigente sem fim (nunca tratado como "ate agora" aqui: intersecao so precisa saber que cobre ate o fim do periodo ou alem)
        intersecta = a.vigente_de <= periodo_fim and (fim_efetivo is None or fim_efetivo >= periodo_inicio)
        if intersecta:
            cliente = ReferenciaCanonica('CLIENTE', a.cliente_id)
            if cliente not in clientes:
                clientes.append(cliente)

    if not clientes:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
        )
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=tuple(clientes),
    )


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def test_extrai_periodo_explicito_do_pdf_sintetico():
    texto = 'CARTAO DE PONTO\nFuncionario: Fulano\nPeríodo: 29/05/2026 até 28/06/2026\n...'
    periodo = extrair_periodo_do_texto(texto)
    assert periodo == (datetime.date(2026, 5, 29), datetime.date(2026, 6, 28))


def test_sem_periodo_declarado_nunca_infere_de_outro_lugar():
    assert extrair_periodo_do_texto('CARTAO DE PONTO sem periodo nenhum') is None
    assert extrair_periodo_do_texto('') is None


def test_periodo_invertido_e_rejeitado():
    texto = 'Período: 28/06/2026 até 29/05/2026'
    assert extrair_periodo_do_texto(texto) is None


def test_competencia_e_o_fechamento_do_periodo():
    assert competencia_do_periodo(datetime.date(2026, 6, 28)) == '2026-06'
    assert competencia_do_periodo(datetime.date(2027, 1, 5)) == '2027-01'


def test_pipeline_completo_documento_resolvido():
    conteudo = b'%PDF-1.7 conteudo sintetico do cartao de ponto'
    texto = 'CARTAO DE PONTO\nPeríodo: 29/05/2026 até 28/06/2026\n29/05/26 - Sex - C1 08:00 12:00 13:00 17:00'
    resolucao = resolver_documento_conceitual(conteudo, texto, colaborador_id='func-sintetico-1')

    assert resolucao.documento_id == hashlib.sha256(conteudo).hexdigest()
    assert resolucao.estado_resolucao == 'RESOLVIDA'
    assert resolucao.competencia == '2026-06'
    assert resolucao.periodo_inicio == datetime.date(2026, 5, 29)
    assert resolucao.periodo_fim == datetime.date(2026, 6, 28)


def test_documento_sem_periodo_fica_nao_encontrada_nunca_inventa():
    conteudo = b'%PDF-1.7 sem periodo'
    resolucao = resolver_documento_conceitual(conteudo, 'texto sem periodo', colaborador_id='func-x')
    assert resolucao.estado_resolucao == 'NAO_ENCONTRADA'
    assert resolucao.competencia is None
    assert resolucao.periodo_inicio is None


def test_resolucao_de_cliente_usa_alocacao_vigente_no_periodo_do_documento_nunca_cadastro_atual():
    alocacoes = (
        _AlocacaoSintetica('func-1', 'cliente-A', datetime.date(2026, 1, 1), datetime.date(2026, 5, 31)),
        _AlocacaoSintetica('func-1', 'cliente-B', datetime.date(2026, 6, 1), None),  # transferencia, vigente agora
    )
    # Documento cujo periodo cai INTEIRAMENTE ANTES da transferencia -- deve
    # resolver só cliente-A, mesmo que o cadastro "atual" (alocacao
    # vigente=None) já seja cliente-B.
    resolucao_antiga = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-1', datetime.date(2026, 4, 1), datetime.date(2026, 4, 30),
    )
    resolucao_nova = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-1', datetime.date(2026, 6, 5), datetime.date(2026, 6, 30),
    )
    assert resolucao_antiga.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_antiga.valores_confirmados == (ReferenciaCanonica('CLIENTE', 'cliente-A'),)
    assert resolucao_nova.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_nova.valores_confirmados == (ReferenciaCanonica('CLIENTE', 'cliente-B'),)


def test_transferencia_de_posto_dentro_do_periodo_documental_preserva_as_duas_alocacoes():
    """Caso adversarial confirmado pela revisão: ciclo 29/05/2026 a
    28/06/2026, Cliente A vigente até 10/06/2026, Cliente B vigente a
    partir de 11/06/2026 -- as duas alocações intersectam o MESMO
    documento. Nenhuma pode ser descartada; nenhuma escolhida
    arbitrariamente; nenhuma reduzida silenciosamente a uma só."""
    alocacoes = (
        _AlocacaoSintetica('func-transferido', 'cliente-A', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10)),
        _AlocacaoSintetica('func-transferido', 'cliente-B', datetime.date(2026, 6, 11), None),
    )
    resolucao = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-transferido', datetime.date(2026, 5, 29), datetime.date(2026, 6, 28),
    )
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert set(resolucao.valores_confirmados) == {
        ReferenciaCanonica('CLIENTE', 'cliente-A'), ReferenciaCanonica('CLIENTE', 'cliente-B'),
    }
    assert len(resolucao.valores_confirmados) == 2  # nenhuma das duas foi descartada


def test_transferencia_intraperiodo_e_deterministica():
    alocacoes = (
        _AlocacaoSintetica('func-transferido', 'cliente-A', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10)),
        _AlocacaoSintetica('func-transferido', 'cliente-B', datetime.date(2026, 6, 11), None),
    )
    primeira = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-transferido', datetime.date(2026, 5, 29), datetime.date(2026, 6, 28),
    )
    segunda = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-transferido', datetime.date(2026, 5, 29), datetime.date(2026, 6, 28),
    )
    assert primeira == segunda


def test_colaborador_sem_alocacao_no_periodo_nunca_inventa_cliente_fica_nao_encontrada():
    alocacoes = (
        _AlocacaoSintetica('func-1', 'cliente-A', datetime.date(2026, 6, 1), None),
    )
    sem_alocacao_alguma = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-2', datetime.date(2026, 6, 1), datetime.date(2026, 6, 30),
    )
    periodo_antes_de_qualquer_alocacao = resolver_clientes_por_periodo_documental(
        alocacoes, 'func-1', datetime.date(2026, 1, 1), datetime.date(2026, 1, 31),
    )
    assert sem_alocacao_alguma.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert sem_alocacao_alguma.valores_confirmados == ()
    assert periodo_antes_de_qualquer_alocacao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_pipeline_ponta_a_ponta_documento_mais_alocacao():
    """Prova completa: PDF -> período -> competência -> objeto canônico
    -> colaborador -> cliente(s) via alocação histórica por interseção
    de período -- tudo em memória, nenhuma escrita em Airtable/Postgres."""
    conteudo = b'%PDF-1.7 cartao ponto sintetico junho'
    texto = 'CARTAO DE PONTO\nPeríodo: 29/05/2026 até 28/06/2026'
    resolucao = resolver_documento_conceitual(conteudo, texto, colaborador_id='func-sintetico-2')

    alocacoes = (
        _AlocacaoSintetica('func-sintetico-2', 'cliente-sintetico-Z', datetime.date(2026, 1, 1), None),
    )
    resolucao_cliente = resolver_clientes_por_periodo_documental(
        alocacoes, resolucao.colaborador_id, resolucao.periodo_inicio, resolucao.periodo_fim,
    )

    assert resolucao.estado_resolucao == 'RESOLVIDA'
    assert resolucao.competencia == '2026-06'
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_cliente.valores_confirmados == (ReferenciaCanonica('CLIENTE', 'cliente-sintetico-Z'),)


def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def test_prova_nunca_importa_airtable_requests_ou_app_py():
    """Confirma, por AST, que este arquivo de prova é 100% isolado --
    nenhum import de rede/Airtable/legado protegido."""
    import sys
    modulo_atual = sys.modules[__name__]
    codigo_fonte = inspect.getsource(modulo_atual)
    arvore = ast.parse(codigo_fonte)
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            nomes = [no.module] if isinstance(no, ast.ImportFrom) else [a.name for a in no.names]
            for nome in nomes:
                if not nome:
                    continue
                proibido = nome.lower() in ('requests',) or 'airtable' in nome.lower() or nome == 'app'
                assert not proibido, f'import proibido na prova isolada: {nome!r}'
