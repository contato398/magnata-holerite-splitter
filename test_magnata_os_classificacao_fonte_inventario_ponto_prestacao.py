"""Testes focados de `fonte_inventario_ponto_prestacao.py` (missão
"FONTE DE INVENTÁRIO DE FOLHA/CARTÃO DE PONTO V1"). Nenhum nome real/
CPF real -- só dados sintéticos equivalentes ao schema real."""
import ast
import datetime
import inspect

from magnata_os.classificacao import fonte_inventario_ponto_prestacao as modulo
from magnata_os.classificacao.ciclo_ponto_prestacao import (
    CicloPontoClienteOverride,
    PoliticaCicloPontoPrestacao,
)
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.fonte_inventario_ponto_prestacao import (
    FonteInventarioPontoPrestacao,
    RegistroPontoBruto,
)
from magnata_os.classificacao.produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO

_CLIENTE_ALVO = ReferenciaCanonica('CLIENTE', 'rec_cliente_alvo')
_CLIENTE_OUTRO = ReferenciaCanonica('CLIENTE', 'rec_cliente_outro')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-06')
_FUNC_ESPERADO = ReferenciaCanonica('FUNCIONARIO', 'rec_func_esperado')
_FUNC_OUTRO = ReferenciaCanonica('FUNCIONARIO', 'rec_func_outro')
_FUNC_SEM_VINCULO = ReferenciaCanonica('FUNCIONARIO', 'rec_func_sem_vinculo')


class _FonteRegistrosEmMemoria:
    def __init__(self, registros):
        self._registros = tuple(registros)

    def listar_no_intervalo(self, data_inicio, data_fim):
        return tuple(
            r for r in self._registros if data_inicio <= r.data <= data_fim
        )


class _FonteVinculosFixa:
    """Vínculo histórico fixo -- FUNCIONARIO -> CLIENTE, por competência.
    `_FUNC_SEM_VINCULO` nunca resolve (simula colaborador sem vínculo
    histórico suficiente para a competência pedida)."""

    def __init__(self, mapa):
        self._mapa = mapa

    def resolver_clientes(self, origem, competencia):
        cliente = self._mapa.get((origem, competencia))
        if cliente is None:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.CLIENTE,
                estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            )
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(cliente,),
        )


def _vinculos_padrao():
    return _FonteVinculosFixa({
        (_FUNC_ESPERADO, _COMPETENCIA): _CLIENTE_ALVO,
        (_FUNC_OUTRO, _COMPETENCIA): _CLIENTE_OUTRO,
    })


def test_folha_correta_colaborador_esperado_satisfaz_requisito():
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '12:00', '13:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    itens = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    assert len(itens) == 1
    item = itens[0]
    assert item.tipo_documental == TIPO_FOLHA_DE_PONTO
    assert item.cliente == _CLIENTE_ALVO
    assert item.competencia == _COMPETENCIA
    assert item.colaborador == ReferenciaCanonica('COLABORADOR', _FUNC_ESPERADO.entidade_id)


def test_colaborador_esperado_sem_folha_nao_produz_item():
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria([]), _vinculos_padrao())
    itens = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    assert itens == ()


def test_folha_de_outro_colaborador_nunca_satisfaz():
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_OUTRO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    itens = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    assert itens == ()
    itens_outro = fonte.listar(_CLIENTE_OUTRO, _COMPETENCIA)
    assert len(itens_outro) == 1
    assert itens_outro[0].colaborador == ReferenciaCanonica('COLABORADOR', _FUNC_OUTRO.entidade_id)


def test_folha_de_outra_competencia_periodo_nunca_satisfaz():
    """Registro FORA da janela do ciclo (mês civil de junho/2026) nunca
    conta -- mesmo sendo do colaborador certo."""
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 7, 5), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    assert fonte.listar(_CLIENTE_ALVO, _COMPETENCIA) == ()


def test_ciclo_28_a_28_inclui_dias_do_mes_anterior_e_exclui_fora_da_janela():
    """Caso adversarial sintético: competência junho/2026, ciclo de
    ponto 28/05/2026 a 28/06/2026 -- cliente SINTÉTICO com override,
    nunca SKY Tatuí."""
    cliente_ciclo_deslocado = ReferenciaCanonica('CLIENTE', 'rec_cliente_ciclo_deslocado')
    politica = PoliticaCicloPontoPrestacao(
        version='teste',
        overrides=(CicloPontoClienteOverride(cliente=cliente_ciclo_deslocado, dia_corte=28),),
    )
    vinculos = _FonteVinculosFixa({(_FUNC_ESPERADO, _COMPETENCIA): cliente_ciclo_deslocado})
    registros = [
        RegistroPontoBruto(  # dentro da janela (mês anterior, dia 28)
            documento_id='rec_dentro_1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 5, 28), batidas=('08:00', '17:00'),
        ),
        RegistroPontoBruto(  # fora da janela -- 1 dia antes do corte
            documento_id='rec_fora', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 5, 27), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(
        _FonteRegistrosEmMemoria(registros), vinculos, politica_ciclo=politica,
    )
    itens = fonte.listar(cliente_ciclo_deslocado, _COMPETENCIA)
    assert len(itens) == 1  # 1 item logico por colaborador, mesmo com so 1 dia valido na janela


def test_duplicidade_equivalente_nao_gera_falso_bloqueio():
    """2 cópias do MESMO dia com a MESMA assinatura de batida -- nunca
    vira conflito, nunca duplica o item lógico."""
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
        RegistroPontoBruto(
            documento_id='rec1_copia', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    itens = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    assert len(itens) == 1


def test_duplicidade_conflitante_nunca_produz_falso_completo():
    """2 registros do MESMO dia com assinaturas de batida DIFERENTES --
    dia inteiro descartado como evidência; se era o ÚNICO dia
    disponível, o colaborador fica sem item (nunca falso PRONTO)."""
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
        RegistroPontoBruto(
            documento_id='rec1_conflito', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('09:00', '18:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    assert fonte.listar(_CLIENTE_ALVO, _COMPETENCIA) == ()


def test_duplicidade_conflitante_com_outro_dia_valido_ainda_satisfaz():
    """Conflito isola só o DIA conflitante -- outro dia válido no mesmo
    ciclo ainda basta como evidência de presença."""
    registros = [
        RegistroPontoBruto(
            documento_id='rec_conflito_a', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
        RegistroPontoBruto(
            documento_id='rec_conflito_b', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('09:00', '18:00'),
        ),
        RegistroPontoBruto(
            documento_id='rec_dia_valido', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 11), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    itens = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    assert len(itens) == 1


def test_colaborador_sem_vinculo_historico_suficiente_nunca_vira_item():
    """Sem vínculo histórico resolvido, o item nunca é produzido -- a
    ausência (não um cliente inventado) é o que propaga para
    FALTANDO/INDETERMINADO na readiness a jusante, nunca uma alocação
    inventada aqui."""
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_SEM_VINCULO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    assert fonte.listar(_CLIENTE_ALVO, _COMPETENCIA) == ()


def test_registro_sem_marcacao_nunca_conta_como_presenca():
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=(), possui_marcacao=False,
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    assert fonte.listar(_CLIENTE_ALVO, _COMPETENCIA) == ()


def test_determinismo_mesma_entrada_mesmo_resultado():
    registros = [
        RegistroPontoBruto(
            documento_id='rec1', colaborador=_FUNC_ESPERADO,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
        RegistroPontoBruto(
            documento_id='rec2', colaborador=_FUNC_OUTRO,
            data=datetime.date(2026, 6, 11), batidas=('08:00', '17:00'),
        ),
    ]
    fonte = FonteInventarioPontoPrestacao(_FonteRegistrosEmMemoria(registros), _vinculos_padrao())
    primeira = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    segunda = fonte.listar(_CLIENTE_ALVO, _COMPETENCIA)
    assert primeira == segunda


def test_colaborador_invalido_rejeitado_na_construcao():
    import pytest
    with pytest.raises(ValueError):
        RegistroPontoBruto(
            documento_id='rec1',
            colaborador=ReferenciaCanonica('COLABORADOR', 'x'),  # deve ser FUNCIONARIO
            data=datetime.date(2026, 6, 10),
        )


def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def test_fonte_de_ponto_nunca_importa_airtable_nem_hardcoda_cliente():
    """Núcleo (`fonte_inventario_ponto_prestacao.py`) nunca depende de
    Airtable (nem por import nem por literal 'airtable'/'requests') e
    nunca cita cliente algum por nome (SKY ou qualquer outro) em código
    executável -- só nas fixtures dos testes."""
    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)

    for no in ast.walk(arvore):
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            nomes = [no.module] if isinstance(no, ast.ImportFrom) else [a.name for a in no.names]
            for nome in nomes:
                if nome and ('airtable' in nome.lower() or nome == 'requests'):
                    raise AssertionError(f'import proibido no nucleo: {nome!r}')

    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and _e_docstring(no)
    }
    literais = {
        no.value.lower() for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in nos_de_docstring
    }
    proibidos = ['sky', 'tatui']
    for termo in proibidos:
        achados = {s for s in literais if termo in s}
        assert not achados, f'termo proibido em literal de codigo: {termo!r} em {achados!r}'
