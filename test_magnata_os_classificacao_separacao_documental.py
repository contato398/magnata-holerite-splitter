"""Testes de `separacao_documental.py` (Fase E) e prova de reentrada no
motor geral (Fase F) da missão "CAPACIDADES TRANSVERSAIS DO MOTOR
DOCUMENTAL". CNPJs sintéticos -- válidos só no formato, nunca reais."""
import pytest

from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.produtores_evidencia_documental import (
    hipoteses_textuais_de_classificacao,
)
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.separacao_documental import (
    GrupoSeparado,
    IdentificacaoPagina,
    SituacaoPaginaSeparacao,
    estrategia_por_cnpj_cliente,
    separar_por_carry_forward,
    texto_do_grupo,
)

_CNPJ_MAGNATA = '00111222000133'
_CNPJ_CLIENTE_A = '11222333000181'
_CNPJ_CLIENTE_B = '44555666000172'
_CNPJ_DESCONHECIDO = '99888777000160'

_INDICE = {
    _CNPJ_CLIENTE_A: ('rec_cliente_a', 'Cliente A'),
    _CNPJ_CLIENTE_B: ('rec_cliente_b', 'Cliente B'),
}


def _fmt(cnpj: str) -> str:
    return f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}'


# ============================================================================
# Fase E -- engine genérica
# ============================================================================

def test_engine_pura_agrupa_por_carry_forward():
    """Reproduz exatamente a regra de `construir_mapa_cliente`: página
    com entidade conhecida abre/atualiza seção; página sem marcador
    herda a seção corrente; CNPJ desconhecido quebra o carry-forward."""
    paginas = (
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_A)}',   # 0: abre Cliente A
        'pagina de detalhe sem identificacao',       # 1: herda Cliente A
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_B)}',   # 2: abre Cliente B
        'outra pagina de detalhe',                    # 3: herda Cliente B
        f'Tomador CNPJ {_fmt(_CNPJ_DESCONHECIDO)}',  # 4: quebra -- sem grupo
        'pagina apos tomador desconhecido',           # 5: ainda sem grupo (carry-forward quebrado)
    )
    estrategia = estrategia_por_cnpj_cliente(_INDICE, cnpj_excluido=_CNPJ_MAGNATA)
    resultado = separar_por_carry_forward(paginas, estrategia)

    assert resultado.total_paginas == 6
    assert len(resultado.grupos) == 2
    grupo_a, grupo_b = resultado.grupos
    assert grupo_a.entidade_id == 'rec_cliente_a'
    assert grupo_a.indices_paginas == (0, 1)
    assert grupo_b.entidade_id == 'rec_cliente_b'
    assert grupo_b.indices_paginas == (2, 3)
    assert resultado.indices_sem_grupo == (4, 5)


def test_cada_pagina_aparece_em_exatamente_um_lugar():
    paginas = (
        f'CNPJ {_fmt(_CNPJ_CLIENTE_A)}', 'detalhe', f'CNPJ {_fmt(_CNPJ_DESCONHECIDO)}', 'sem nada',
    )
    estrategia = estrategia_por_cnpj_cliente(_INDICE)
    resultado = separar_por_carry_forward(paginas, estrategia)
    todas = sorted(
        [i for grupo in resultado.grupos for i in grupo.indices_paginas] + list(resultado.indices_sem_grupo)
    )
    assert todas == [0, 1, 2, 3]


def test_documento_sem_nenhum_marcador_vai_inteiro_para_sem_grupo():
    paginas = ('pagina 1 sem cnpj', 'pagina 2 sem cnpj')
    estrategia = estrategia_por_cnpj_cliente(_INDICE)
    resultado = separar_por_carry_forward(paginas, estrategia)
    assert resultado.grupos == ()
    assert resultado.indices_sem_grupo == (0, 1)


def test_cnpj_do_proprio_empregador_e_ignorado():
    """CNPJ excluído nunca é tratado como tomador -- reproduz a exclusão
    do CNPJ da Magnata do legado."""
    paginas = (f'Empregador CNPJ {_fmt(_CNPJ_MAGNATA)}',)
    estrategia = estrategia_por_cnpj_cliente(_INDICE, cnpj_excluido=_CNPJ_MAGNATA)
    resultado = separar_por_carry_forward(paginas, estrategia)
    assert resultado.grupos == ()
    assert resultado.indices_sem_grupo == (0,)


def test_identificacao_pagina_exige_entidade_id_quando_conhecida():
    with pytest.raises(ValueError):
        IdentificacaoPagina(SituacaoPaginaSeparacao.ENTIDADE_CONHECIDA)


def test_identificacao_pagina_rejeita_entidade_fora_de_entidade_conhecida():
    with pytest.raises(ValueError):
        IdentificacaoPagina(SituacaoPaginaSeparacao.SEM_MARCADOR, entidade_id='x')


def test_texto_do_grupo_preserva_ordem_original():
    paginas = ('pagina zero', 'pagina um', 'pagina dois')
    grupo = GrupoSeparado(entidade_id='e1', nome='Entidade', indices_paginas=(2, 0))
    assert texto_do_grupo(paginas, grupo) == 'pagina dois\npagina zero'


# ============================================================================
# Fase F -- prova de reentrada: MASTER -> SEPARACAO -> FILHOS -> MESMO MOTOR
# ============================================================================

def _resolver_tipo(texto: str, quantidade_entidades_distintas=None):
    hipoteses = hipoteses_textuais_de_classificacao(classificar_documento(texto))
    return resolver_tipo_documental(hipoteses, quantidade_entidades_distintas=quantidade_entidades_distintas)


def test_filhos_separados_reentram_no_mesmo_motor_sem_pipeline_paralelo():
    """Documento master (Extrato Mensal de 2 clientes) -- separado, cada
    filho passa pelo MESMO `classificar_documento` +
    `hipoteses_textuais_de_classificacao` + `resolver_tipo_documental`
    já usados para qualquer outro documento (nenhuma função nova
    "para filhos")."""
    paginas = (
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_A)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
        'pagina de detalhe do cliente A',
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_B)}\nExtrato Mensal\nExtrato da Folha de Pagamento',
    )
    estrategia = estrategia_por_cnpj_cliente(_INDICE, cnpj_excluido=_CNPJ_MAGNATA)
    resultado_separacao = separar_por_carry_forward(paginas, estrategia)
    assert len(resultado_separacao.grupos) == 2

    for grupo in resultado_separacao.grupos:
        texto_filho = texto_do_grupo(paginas, grupo)
        # Cada filho, isolado, tem exatamente 1 CNPJ -- nunca conflita
        # mais depois de separado.
        resolucao_tipo = _resolver_tipo(texto_filho, quantidade_entidades_distintas=1)
        assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
        assert resolucao_tipo.valores_confirmados == (
            ReferenciaCanonica('TIPO_DOCUMENTAL', 'Extrato da Folha de Pagamento'),
        )


def test_documento_ainda_nao_separado_conflita_no_mesmo_motor():
    """Antes da separação, o documento completo (múltiplas entidades
    distintas) nunca resolve sozinho -- mesmo fail-safe genérico já
    provado na Fase 2E anterior, prova que master e filho passam pelo
    MESMO resolvedor, cada um em seu momento certo."""
    texto_completo = (
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_A)}\nExtrato Mensal\n'
        f'Tomador CNPJ {_fmt(_CNPJ_CLIENTE_B)}\nExtrato Mensal'
    )
    resolucao_tipo = _resolver_tipo(texto_completo, quantidade_entidades_distintas=2)
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.CONFLITO
