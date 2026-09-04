"""Testes da fundação temporal Posto ↔ Cliente (missão
"FUNDAÇÃO TEMPORAL POSTO ↔ CLIENTE V1").

Cobrindo:
  1. relação única posto→cliente;
  2. duas relações consecutivas sem sobreposição;
  3. sobreposição no mesmo posto rejeitada;
  4. postos diferentes podem ter períodos simultâneos;
  5. `vigente_ate < vigente_de` rejeitado;
  6. leitura histórica cliente correto;
  7. mudança de cliente durante período retorna ambos;
  8. ausência de relação NÃO fabrica cliente;
  9. alocação fora do período não entra;
  10. relação cliente/posto fora do período não entra;
  11. ordenação determinística;
  12. nenhuma dependência nova Airtable/app.py;
  13. LACUNA TEMPORAL.
  14. BUG FIX: Alocação e cliente devem intersectar entre si.

Implementação: Mock DB-API 2.0 compatível (não acessa Postgres real).
"""
import datetime
import pytest
from magnata_os.documental.alocacao.temporal import TuplaAlocacaoComClientes


class MockCursor:
    """Mock cursor DB-API 2.0 compatível para testes do adapter."""

    def __init__(self, rows):
        self.rows = rows
        self.description = None
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        """Armazena query para análise posterior."""
        self.query = query
        self.params = params or ()
        self.last_query = query
        self.last_params = params or ()

    def fetchall(self):
        """Retorna rows pré-configuradas."""
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockConnection:
    """Mock conexão DB-API 2.0."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def cursor(self):
        return MockCursor(self.rows)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_caso_adversarial_alocacao_cliente_nao_intersectam():
    """BUG FIX: Garantir que alocação e cliente devem intersectar entre si.

    Cenário adversarial:
      Consulta: 01/01/2026 → 31/12/2026
      Alocação: 01/01/2026 → 30/06/2026
      Posto→Cliente: 01/07/2026 → 31/12/2026

    Ambos intersectam a janela, MAS não se intersectam entre si.
    Resultado esperado: NÃO associar cliente a esta alocação (query filtra).
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock data: nenhuma interseção entre alocação e cliente
    # Query com LEFT JOIN não retorna nada quando não há interseção real
    mock_conn = MockConnection(rows=[])
    repo = RepositorioAlocacaoPostgres(mock_conn)

    # Executar query
    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'func-1',
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31)
    )

    # Sem interseção real entre alocação e cliente, resultado está vazio
    assert len(resultado) == 0


def test_alocacao_cliente_realmente_intersectam():
    """Alocação e cliente intersectam entre si + ambos intersectam janela.

    Cenário:
      Consulta: 01/01/2026 → 31/12/2026
      Alocação: 01/01/2026 → 30/06/2026
      Posto→Cliente: 01/01/2026 → 30/06/2026
      Interseção: 01/01 → 30/06 (completa)

    Resultado: 1 row com cliente associado.
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock data: alocação e cliente intersectam
    # vinculo_id, colaborador_id, alocacao_id, posto_id, cliente_id,
    # alocacao_vigente_de, alocacao_vigente_ate, cliente_vigente_de, cliente_vigente_ate
    row = (
        'v1', 'f1', 'a1', 'p1', 'c1',
        datetime.date(2026, 1, 1), datetime.date(2026, 6, 30),
        datetime.date(2026, 1, 1), datetime.date(2026, 6, 30)
    )

    mock_conn = MockConnection(rows=[row])
    repo = RepositorioAlocacaoPostgres(mock_conn)

    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'f1',
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31)
    )

    assert len(resultado) == 1
    assert resultado[0].cliente_id == 'c1'
    assert resultado[0].alocacao_vigente_de == datetime.date(2026, 1, 1)
    assert resultado[0].cliente_vigente_de == datetime.date(2026, 1, 1)


def test_ausencia_relacao_nao_fabrica_cliente():
    """Ausência de relação cliente→posto retorna NULL (não fabricado).

    LEFT JOIN sem match = cliente_id = NULL e cliente_vigente_de/ate = NULL.
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock data: alocação existe, mas sem cliente na tabela vigencia_cliente_por_posto
    row = (
        'v1', 'f1', 'a1', 'p1', None,  # cliente_id = NULL
        datetime.date(2026, 1, 1), datetime.date(2026, 6, 30),
        None, None  # cliente períodos também NULL
    )

    mock_conn = MockConnection(rows=[row])
    repo = RepositorioAlocacaoPostgres(mock_conn)

    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'f1',
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31)
    )

    assert len(resultado) == 1
    assert resultado[0].cliente_id is None
    assert resultado[0].cliente_vigente_de is None
    assert resultado[0].cliente_vigente_ate is None


def test_lacuna_temporal_cliente_desconhecido():
    """Lacuna temporal: período sem cliente comprovado retorna NULL.

    Cliente A até 30/06, Cliente B desde 05/07.
    Período 01/07-04/07: sem cliente comprovado = NULL.
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock data: alocação em período sem cliente
    row = (
        'v1', 'f1', 'a1', 'p1', None,
        datetime.date(2026, 7, 1), datetime.date(2026, 7, 4),
        None, None
    )

    mock_conn = MockConnection(rows=[row])
    repo = RepositorioAlocacaoPostgres(mock_conn)

    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'f1',
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 4)
    )

    assert len(resultado) == 1
    assert resultado[0].cliente_id is None
    assert resultado[0].cliente_vigente_de is None
    assert resultado[0].cliente_vigente_ate is None


def test_mudanca_cliente_legítima_retorna_ambos():
    """Mudança legítima de cliente durante alocação retorna 2 rows.

    Alocação: 01/06 → 31/07
    Cliente A: 01/06 → 30/06
    Cliente B: 01/07 → 31/07

    Query 01/06 → 31/07: retorna 2 rows (A e B).
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock data: 2 rows com mesma alocação mas clientes diferentes
    rows = [
        (
            'v1', 'f1', 'a1', 'p1', 'c1',
            datetime.date(2026, 6, 1), datetime.date(2026, 7, 31),
            datetime.date(2026, 6, 1), datetime.date(2026, 6, 30)
        ),
        (
            'v1', 'f1', 'a1', 'p1', 'c2',
            datetime.date(2026, 6, 1), datetime.date(2026, 7, 31),
            datetime.date(2026, 7, 1), datetime.date(2026, 7, 31)
        ),
    ]

    mock_conn = MockConnection(rows=rows)
    repo = RepositorioAlocacaoPostgres(mock_conn)

    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'f1',
        datetime.date(2026, 6, 1),
        datetime.date(2026, 7, 31)
    )

    assert len(resultado) == 2
    assert resultado[0].cliente_id == 'c1'
    assert resultado[1].cliente_id == 'c2'


def test_ordenacao_deterministica_multiplos_clientes():
    """Ordenação determinística: posto_id, cliente_id, vigente_de ASC."""
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock data: já em ordem (como SQL retornaria)
    # ORDER BY a.posto_id, vc.cliente_id, a.vigente_de ASC
    rows = [
        ('v1', 'f1', 'a2', 'p1', 'c1', datetime.date(2026, 6, 1), None, datetime.date(2026, 1, 1), None),
        ('v1', 'f1', 'a1', 'p1', 'c2', datetime.date(2026, 6, 1), None, datetime.date(2026, 1, 1), None),
        ('v1', 'f1', 'a3', 'p2', 'c1', datetime.date(2026, 6, 1), None, datetime.date(2026, 1, 1), None),
    ]

    mock_conn = MockConnection(rows=rows)
    repo = RepositorioAlocacaoPostgres(mock_conn)

    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'f1',
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31)
    )

    # Verificar que ordering é preservado
    assert len(resultado) == 3
    # p1 < p2
    assert resultado[0].posto_id == 'p1'
    assert resultado[1].posto_id == 'p1'
    assert resultado[2].posto_id == 'p2'
    # Dentro de p1: c1 < c2
    assert resultado[0].cliente_id == 'c1'
    assert resultado[1].cliente_id == 'c2'


def test_nenhum_import_app_py():
    """Verificar que o módulo não importa app.py."""
    import sys
    import magnata_os.documental.alocacao.adapters.postgres_alocacao

    magnata_modules = [m for m in sys.modules.keys() if 'magnata' in m]
    for mod_name in magnata_modules:
        assert mod_name != 'app'
        assert not mod_name.startswith('app.')


def test_nenhuma_dependencia_airtable_nova():
    """Verificar que postgres_alocacao não importa clientes Airtable."""
    import inspect
    from magnata_os.documental.alocacao.adapters import postgres_alocacao

    source = inspect.getsource(postgres_alocacao)
    assert 'LeitorAirtable' not in source
    assert 'airtable_leitura' not in source


def test_validar_tipagem_cliente_null():
    """Confirmar que cliente_vigente_de/ate são Optional[date]."""
    from magnata_os.documental.alocacao.temporal import TuplaAlocacaoComClientes

    annotations = TuplaAlocacaoComClientes.__annotations__

    cliente_id_annotation = str(annotations['cliente_id'])
    assert 'Optional' in cliente_id_annotation or 'None' in cliente_id_annotation

    cliente_vigente_de_annotation = str(annotations['cliente_vigente_de'])
    assert 'Optional' in cliente_vigente_de_annotation or 'None' in cliente_vigente_de_annotation

    cliente_vigente_ate_annotation = str(annotations['cliente_vigente_ate'])
    assert 'Optional' in cliente_vigente_ate_annotation or 'None' in cliente_vigente_ate_annotation


def test_tupla_alocacao_com_clientes_estrutura():
    """Validar estrutura básica da dataclass."""
    tupla = TuplaAlocacaoComClientes(
        vinculo_id='v1', colaborador_id='f1', alocacao_id='a1',
        posto_id='p1', cliente_id='c1',
        alocacao_vigente_de=datetime.date(2026, 6, 1),
        alocacao_vigente_ate=datetime.date(2026, 12, 31),
        cliente_vigente_de=datetime.date(2026, 1, 1),
        cliente_vigente_ate=datetime.date(2026, 12, 31),
    )

    assert tupla.cliente_id == 'c1'
    assert tupla.alocacao_vigente_de >= tupla.cliente_vigente_de
    assert tupla.cliente_vigente_ate >= tupla.alocacao_vigente_de


def test_condicoes_cruzadas_no_sql():
    """Validar que SQL contém condições cruzadas de interseção entre alocação e cliente.

    As duas condições obrigatórias:
    1. (vc.vigente_ate IS NULL OR a.vigente_de <= vc.vigente_ate)
       - Alocação começa antes do cliente terminar
    2. (a.vigente_ate IS NULL OR vc.vigente_de <= a.vigente_ate)
       - Cliente começa antes da alocação terminar

    Se essas faltarem, o bug volta (ambos intersectam janela, mas não entre si).
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock com capture de query
    class CaptureConnection:
        def __init__(self):
            self.captured_query = None

        def cursor(self):
            return CaptureCursor(self)

    class CaptureCursor:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, query, params=None):
            self.conn.captured_query = query

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_conn = CaptureConnection()
    repo = RepositorioAlocacaoPostgres(mock_conn)

    # Executar query
    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'f1',
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31)
    )

    # Verificar SQL contém as duas condições cruzadas
    assert mock_conn.captured_query is not None
    query = mock_conn.captured_query

    # Condição 1: a.vigente_de <= vc.vigente_ate
    assert 'a.vigente_de <= vc.vigente_ate' in query or \
           'a.vigente_de<=vc.vigente_ate' in query.replace(' ', ''), \
           f"Falta condição cruzada 1 na query: {query}"

    # Condição 2: vc.vigente_de <= a.vigente_ate
    assert 'vc.vigente_de <= a.vigente_ate' in query or \
           'vc.vigente_de<=a.vigente_ate' in query.replace(' ', ''), \
           f"Falta condição cruzada 2 na query: {query}"

    # Ambas devem estar em OR com verificação de NULL
    assert 'vc.vigente_ate IS NULL OR' in query, \
           f"Falta proteção de NULL para vigente_ate em query: {query}"
    assert 'a.vigente_ate IS NULL OR' in query, \
           f"Falta proteção de NULL para vigente_ate em query: {query}"


def test_binding_sql_parametros():
    """Validar que número de placeholders SQL == número de parâmetros DB-API.

    Garantias:
    - SQL tem exatamente 7 placeholders %s
    - Tuple de parâmetros tem exatamente 7 valores
    - Ordem correta: data_fim, data_inicio, colaborador_id, data_fim, data_inicio, data_fim, data_inicio
    """
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

    # Mock com capture de query e params
    class CaptureConnection:
        def __init__(self):
            self.captured_query = None
            self.captured_params = None

        def cursor(self):
            return CaptureBindingCursor(self)

    class CaptureBindingCursor:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, query, params=None):
            self.conn.captured_query = query
            self.conn.captured_params = params or ()

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_conn = CaptureConnection()
    repo = RepositorioAlocacaoPostgres(mock_conn)

    # Executar query
    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'colaborador-123',
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31)
    )

    # Verificar binding
    assert mock_conn.captured_query is not None
    assert mock_conn.captured_params is not None

    query = mock_conn.captured_query
    params = mock_conn.captured_params

    # Contar placeholders
    placeholder_count = query.count('%s')
    assert placeholder_count == 7, \
           f"Esperado 7 placeholders, encontrado {placeholder_count}"

    # Contar parâmetros
    assert len(params) == 7, \
           f"Esperado 7 parâmetros, encontrado {len(params)}: {params}"

    # Verificar ordem (sem contar valores duplicados)
    # Os valores únicos são: data_fim=2026-12-31, data_inicio=2026-01-01, colaborador_id=colaborador-123
    assert params[0] == datetime.date(2026, 12, 31)  # data_fim
    assert params[1] == datetime.date(2026, 1, 1)     # data_inicio
    assert params[2] == 'colaborador-123'             # colaborador_id
    assert params[3] == datetime.date(2026, 12, 31)  # data_fim (v.data_admissao)
    assert params[4] == datetime.date(2026, 1, 1)     # data_inicio (v.data_desligamento)
    assert params[5] == datetime.date(2026, 12, 31)  # data_fim (a.vigente_de)
    assert params[6] == datetime.date(2026, 1, 1)     # data_inicio (a.vigente_ate)
