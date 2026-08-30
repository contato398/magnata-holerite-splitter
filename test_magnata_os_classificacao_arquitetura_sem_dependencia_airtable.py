"""Teste arquitetural (missão "INTEGRAÇÃO REAL DO CONTEÚDO DOCUMENTAL AO
MOTOR SEMÂNTICO", Fase 21): nenhum módulo do corredor
CONTEÚDO->MOTOR->ESTEIRA construído nesta e nas missões anteriores
importa Airtable -- Airtable é bridge/fonte substituível, nunca cérebro
nem dependência estrutural do motor (CLAUDE.md §3, "Airtable é
legado/adapter temporário").

Verificação por AST (nunca por busca textual solta, que teria falsos
positivos em docstring/comentário) -- cada módulo listado é PARSEADO e
todo `import`/`from ... import` é inspecionado; nenhum nome de módulo
importado pode conter 'airtable'."""
import ast
import inspect

from magnata_os.classificacao import (
    automacao_por_confianca,
    ponte_conteudo_motor_semantico,
    reconciliacao_origem_conteudo,
)
from magnata_os.documental.modulo01 import politica_classificacao_semantica

_MODULOS_DO_CORREDOR_SEMANTICO = (
    ponte_conteudo_motor_semantico,
    reconciliacao_origem_conteudo,
    automacao_por_confianca,
    politica_classificacao_semantica,
)


def _nomes_de_modulos_importados(modulo) -> set:
    arvore = ast.parse(inspect.getsource(modulo))
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
    return nomes


def test_nenhum_modulo_do_corredor_semantico_importa_airtable():
    for modulo in _MODULOS_DO_CORREDOR_SEMANTICO:
        nomes = _nomes_de_modulos_importados(modulo)
        achados = {nome for nome in nomes if 'airtable' in nome.lower()}
        assert not achados, f'{modulo.__name__} importa airtable diretamente: {achados!r}'


def test_ponte_conteudo_motor_semantico_so_conhece_texto_nunca_fonte_de_dados():
    """A ponte só recebe `texto`/`conteudo_pdf` -- nenhum parâmetro ou
    import sugere Airtable, Gmail ou armazenamento específico; poderia
    ser alimentada por qualquer origem sem alteração aqui."""
    assinatura_texto = inspect.signature(ponte_conteudo_motor_semantico.resolver_tipo_documental_de_texto)
    assinatura_pdf = inspect.signature(ponte_conteudo_motor_semantico.resolver_tipo_documental_de_pdf)
    assert list(assinatura_texto.parameters) == ['texto']
    assert list(assinatura_pdf.parameters) == ['conteudo_pdf']


def test_politica_classificacao_semantica_aceita_tipo_origem_como_string_generica():
    """`tipo_origem` é uma `str` opcional genérica -- nunca um tipo
    específico de Airtable/registro; qualquer fonte (Gmail, upload
    manual, armazenamento) pode preencher o mesmo parâmetro."""
    assinatura = inspect.signature(politica_classificacao_semantica.decidir_transicao_classificacao_semantica)
    assert set(assinatura.parameters) == {'texto', 'tipo_origem', 'competencia_esperada'}
