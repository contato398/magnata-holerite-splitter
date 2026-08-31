"""Teste arquitetural (missão "INTEGRAÇÃO REAL DO CONTEÚDO DOCUMENTAL AO
MOTOR SEMÂNTICO", Fase 21; estendido pela missão "CORREDOR AUTÔNOMO
PÓS-CLASSIFICAÇÃO V1", Fase 27): nenhum módulo do corredor
CONTEÚDO->MOTOR->PERFIL->IDENTIFICAÇÃO->VALIDAÇÃO->INVENTÁRIO->
READINESS->PACOTE construído nesta e nas missões anteriores importa
Airtable -- Airtable é bridge/fonte substituível, nunca cérebro nem
dependência estrutural do motor (CLAUDE.md §3, "Airtable é
legado/adapter temporário").

Verificação por AST (nunca por busca textual solta, que teria falsos
positivos em docstring/comentário) -- cada módulo listado é PARSEADO e
todo `import`/`from ... import` é inspecionado; nenhum nome de módulo
importado pode conter 'airtable'."""
import ast
import inspect

from magnata_os.classificacao import (
    automacao_por_confianca,
    identificacao_documental,
    inventario_prestacao_memoria,
    perfil_aplicabilidade_documental,
    ponte_conteudo_motor_semantico,
    reconciliacao_origem_conteudo,
    resolucao_documento_prestacao,
)
from magnata_os.documental.modulo01 import politica_classificacao_semantica

_MODULOS_DO_CORREDOR_SEMANTICO = (
    ponte_conteudo_motor_semantico,
    reconciliacao_origem_conteudo,
    automacao_por_confianca,
    politica_classificacao_semantica,
    identificacao_documental,
    perfil_aplicabilidade_documental,
    resolucao_documento_prestacao,
    inventario_prestacao_memoria,
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


def test_resolver_documento_prestacao_so_recebe_fontes_via_protocol_injetado():
    """Fase 27: `fonte_vinculos` é tipado contra `FonteVinculosPrestacao`
    (Protocol, `vinculos_prestacao.py`) -- não um cliente Airtable
    concreto. Provado por substituição: um objeto Python puro qualquer
    (duck-typed contra o Protocol) resolve o mesmo corredor até
    RESOLVIDO_E_AVANCOU sem o módulo saber que não é Airtable."""
    from magnata_os.classificacao.contratos import (
        DimensaoResolucao,
        EstadoResolucaoDimensao,
        ReferenciaCanonica,
        ResolucaoDimensao,
    )
    from magnata_os.classificacao.resolucao_documento_prestacao import (
        ContextoResolucaoDocumentoPrestacao,
        EstadoCorredorDocumentoPrestacao,
        processar_documento_prestacao,
    )
    from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

    class _FonteVinculosPuroPython:
        """Nunca importa Airtable, boto3, psycopg2 nem qualquer driver
        -- só implementa o Protocol via duck typing."""

        def resolver_clientes(self, origem, competencia):
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(ReferenciaCanonica('CLIENTE', 'cli-qualquer'),),
            )

    class _FonteUnidadePostoPuroPython:
        """Mesmo princípio para a dimensão UNIDADE_POSTO (missão
        "EVIDÊNCIA RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO
        REAIS") -- nunca Airtable, só o Protocol via duck typing."""

        def resolver_unidade_posto(self, colaborador, competencia):
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(ReferenciaCanonica('UNIDADE_POSTO', 'posto-qualquer'),),
            )

    contexto = ContextoResolucaoDocumentoPrestacao(
        documento_id='doc-arquitetura', hash_sha256='a' * 64, competencia_esperada=(2026, 7),
        candidatos_colaborador=[CandidatoFuncionario(func_id='f1', cpf='11122233344', nome_normalizado='X')],
        fonte_vinculos=_FonteVinculosPuroPython(), fonte_unidade_posto=_FonteUnidadePostoPuroPython(),
    )
    resultado = processar_documento_prestacao(
        'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44', contexto,
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
