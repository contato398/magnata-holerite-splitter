"""Testes de `resolucao_master_documental.py` (Fase D da missão
"CAPACIDADES TRANSVERSAIS DO MOTOR DOCUMENTAL")."""
import ast
import inspect

from magnata_os.classificacao import resolucao_master_documental as modulo
from magnata_os.classificacao.evidencia_estrutural_documental import (
    EvidenciaEstruturalDocumento,
)
from magnata_os.classificacao.resolucao_master_documental import (
    EstadoGranularidadeDocumento,
    detectar_granularidade_documento,
)


def test_multiplos_cnpjs_e_potencialmente_master():
    evidencia = EvidenciaEstruturalDocumento(
        total_paginas=5, quantidade_cnpjs_distintos=2, quantidade_cpfs_distintos=0,
    )
    decisao = detectar_granularidade_documento(evidencia)
    assert decisao.estado == EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER
    assert decisao.evidencias


def test_multiplos_cpfs_e_potencialmente_master():
    evidencia = EvidenciaEstruturalDocumento(
        total_paginas=5, quantidade_cnpjs_distintos=0, quantidade_cpfs_distintos=3,
    )
    decisao = detectar_granularidade_documento(evidencia)
    assert decisao.estado == EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER


def test_entidade_unica_e_unitario():
    evidencia = EvidenciaEstruturalDocumento(
        total_paginas=2, quantidade_cnpjs_distintos=1, quantidade_cpfs_distintos=0,
    )
    decisao = detectar_granularidade_documento(evidencia)
    assert decisao.estado == EstadoGranularidadeDocumento.UNITARIO


def test_documento_sem_nenhuma_entidade_e_inconclusivo():
    evidencia = EvidenciaEstruturalDocumento(
        total_paginas=1, quantidade_cnpjs_distintos=0, quantidade_cpfs_distintos=0,
    )
    decisao = detectar_granularidade_documento(evidencia)
    assert decisao.estado == EstadoGranularidadeDocumento.INCONCLUSIVO


def test_inconclusivo_nunca_forca_unitario_por_padrao():
    """Ausência de evidência é INCONCLUSIVO, nunca UNITARIO -- nunca
    mascarar falta de sinal como confiança (/CLAUDE.md §4, "falha nunca
    é silenciosa")."""
    evidencia = EvidenciaEstruturalDocumento(0, 0, 0)
    decisao = detectar_granularidade_documento(evidencia)
    assert decisao.estado != EstadoGranularidadeDocumento.UNITARIO


def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def _termos_em_codigo_executavel(modulo) -> set:
    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and _e_docstring(no)
    }
    identificadores, literais = set(), set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Name, ast.arg)):
            identificadores.add(no.id if isinstance(no, ast.Name) else no.arg)
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identificadores.add(no.name)
        elif isinstance(no, ast.Attribute):
            identificadores.add(no.attr)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            if id(no) not in nos_de_docstring:
                literais.add(no.value)
    return {s.lower() for s in identificadores | literais}


def test_detector_de_master_e_estruturalmente_generico():
    """Nunca conhece nenhum tipo documental por nome (nem em código
    executável nem em identificador) -- só sabe interpretar contagem de
    entidades, igual à prova de generalidade já usada em
    `resolucao_tipo_documental.py`."""
    codigo_executavel = _termos_em_codigo_executavel(modulo)
    termos_proibidos = (
        'holerite', 'extrato', 'fgts', 'dctfweb', 'darf', 'folha de ponto',
        'nota fiscal', 'boleto', 'cliente', 'colaborador', 'filename', 'nome_arquivo',
    )
    for termo in termos_proibidos:
        achados = {s for s in codigo_executavel if termo in s}
        assert not achados, f'termo proibido em código executável: {termo!r} em {achados!r}'


def test_nenhuma_funcao_do_modulo_aceita_filename():
    for nome, obj in inspect.getmembers(modulo, inspect.isfunction):
        parametros = inspect.signature(obj).parameters
        assert 'filename' not in parametros and 'nome_arquivo' not in parametros, nome
