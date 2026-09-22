"""Testes de `resolver_parametros_ordem_prestacao_contato_v1.py` --
primeira implementação REAL de `ResolverParametrosOrdemPrestacao`
(antes só fakes de teste com telefone hardcoded existiam). Cobre:
contato válido, ausente, inválido, múltiplo/conflitante, replay,
telefone alterado -> nova Ordem/event_id, ausência de qualquer chamada
Airtable durante a resolução, e zero transporte real."""
from cryptography.fernet import Fernet

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ResultadoAquisicaoPorNecessidade,
)
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RepositorioContatoColaboradorEmMemoria,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
    RegistroContatoColaborador,
)
from magnata_os.orquestrador.resolver_parametros_ordem_prestacao_contato_v1 import (
    construir_resolvedor_parametros_ordem_prestacao_contato_v1,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    derivar_identidade_ordem_distribuicao,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    montar_ordem_distribuicao_documental_de_prestacao,
)

from datetime import datetime, timezone

AGORA = datetime(2026, 9, 21, tzinfo=timezone.utc)
_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-1')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-09')
_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'colab-1')
_CHAVE_FERNET = Fernet.generate_key()
_CHAVE_HMAC = b'segredo-hmac-resolver-teste'


def _resultado_aquisicao(colaborador=_COLABORADOR, documento_id='doc-1', hash_sha256='hash-doc-1'):
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental='HOLERITE',
        motivo_exigencia='teste', colaborador=colaborador,
    )
    return ResultadoAquisicaoPorNecessidade(
        necessidade=necessidade, documento_id=documento_id, hash_sha256=hash_sha256,
    )


def _registrar_contato(repo, colaborador_id, numero, canal=CANAL_WHATSAPP, versao='v1'):
    registro = RegistroContatoColaborador(
        colaborador_id=colaborador_id, canal=canal,
        valor_cifrado=cifrar_valor_contato(_CHAVE_FERNET, numero),
        hash_auxiliar=calcular_hash_auxiliar_contato(_CHAVE_HMAC, numero),
        versao_chave=versao, origem='teste', criado_em=AGORA, atualizado_em=AGORA,
    )
    repo.criar_ou_confirmar(registro)


def _mensagem_texto(cliente, competencia):
    return f'Segue seu documento -- {cliente.entidade_id}/{competencia.entidade_id}'


# ---------------------------------------------------------------------
# Contato válido.
# ---------------------------------------------------------------------

def test_contato_valido_produz_parametros_ordem():
    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )

    parametros = resolver(_CLIENTE, _COMPETENCIA, (_resultado_aquisicao(),))

    assert parametros is not None
    assert parametros.destinatario == '5511999998888'
    assert parametros.preset_id == 'DOCUMENTO_UNITARIO_SEM_ASSINATURA'
    assert parametros.tipo_documento == 'HOLERITE'
    assert 'cliente-1' in parametros.mensagem_texto


# ---------------------------------------------------------------------
# Contato ausente / inválido / colaborador ausente / sem resultados.
# ---------------------------------------------------------------------

def test_contato_ausente_devolve_none_fail_closed():
    repo = RepositorioContatoColaboradorEmMemoria()  # vazio
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    assert resolver(_CLIENTE, _COMPETENCIA, (_resultado_aquisicao(),)) is None


def test_contato_invalido_chave_errada_devolve_none_fail_closed():
    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    chave_errada = Fernet.generate_key()
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=chave_errada,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    assert resolver(_CLIENTE, _COMPETENCIA, (_resultado_aquisicao(),)) is None


def test_colaborador_ausente_na_necessidade_devolve_none_fail_closed():
    repo = RepositorioContatoColaboradorEmMemoria()
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    assert resolver(_CLIENTE, _COMPETENCIA, (_resultado_aquisicao(colaborador=None),)) is None


def test_sem_resultados_aquisicao_devolve_none_fail_closed():
    repo = RepositorioContatoColaboradorEmMemoria()
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    assert resolver(_CLIENTE, _COMPETENCIA, ()) is None


# ---------------------------------------------------------------------
# Múltiplo/conflitante -- via ConflitoContatoColaborador na escrita
# (o resolvedor, em leitura, nunca vê mais de 1 registro por
# construção da chave primária; o teste prova que a tentativa de gerar
# ambiguidade já falha antes, na escrita).
# ---------------------------------------------------------------------

def test_tentativa_de_registrar_contato_conflitante_nunca_produz_ambiguidade_na_leitura():
    from magnata_os.documental.alocacao.contato_colaborador import ConflitoContatoColaborador
    import pytest

    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    with pytest.raises(ConflitoContatoColaborador):
        _registrar_contato(repo, 'colab-1', '5511988887777')

    # O resolvedor continua enxergando só o valor ORIGINAL -- nunca
    # múltiplo, nunca o conflitante.
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    parametros = resolver(_CLIENTE, _COMPETENCIA, (_resultado_aquisicao(),))
    assert parametros.destinatario == '5511999998888'


# ---------------------------------------------------------------------
# Replay -- chamadas repetidas são determinísticas.
# ---------------------------------------------------------------------

def test_replay_e_deterministico_mesmos_parametros():
    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    resultado_aquisicao = (_resultado_aquisicao(),)
    p1 = resolver(_CLIENTE, _COMPETENCIA, resultado_aquisicao)
    p2 = resolver(_CLIENTE, _COMPETENCIA, resultado_aquisicao)
    assert p1 == p2


# ---------------------------------------------------------------------
# Telefone alterado gera nova Ordem/event_id.
# ---------------------------------------------------------------------

def test_telefone_alterado_entre_colaboradores_diferentes_gera_event_id_diferente():
    """Simula 2 colaboradores diferentes com telefones diferentes (o
    cenário real de "telefone mudou" é coberto a nível de repositório
    por `ConflitoContatoColaborador` -- nunca aplicado silenciosamente;
    aqui provamos a CONSEQUÊNCIA na Ordem: destinatario diferente ->
    Ordem diferente -> event_id diferente, nunca considerado replay da
    mesma Ordem)."""
    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    _registrar_contato(repo, 'colab-2', '5511988887777')
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )

    resultado_colab1 = (_resultado_aquisicao(colaborador=_COLABORADOR, documento_id='doc-1', hash_sha256='h1'),)
    resultado_colab2 = (_resultado_aquisicao(
        colaborador=ReferenciaCanonica('COLABORADOR', 'colab-2'), documento_id='doc-1', hash_sha256='h1',
    ),)

    params1 = resolver(_CLIENTE, _COMPETENCIA, resultado_colab1)
    params2 = resolver(_CLIENTE, _COMPETENCIA, resultado_colab2)
    assert params1.destinatario != params2.destinatario

    ordem1 = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultado_colab1, destinatario=params1.destinatario,
        preset_id=params1.preset_id, tipo_documento=params1.tipo_documento,
        mensagem_texto=params1.mensagem_texto,
    )
    ordem2 = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultado_colab2, destinatario=params2.destinatario,
        preset_id=params2.preset_id, tipo_documento=params2.tipo_documento,
        mensagem_texto=params2.mensagem_texto,
    )
    event_id_1 = derivar_identidade_ordem_distribuicao(ordem1)
    event_id_2 = derivar_identidade_ordem_distribuicao(ordem2)
    assert event_id_1 != event_id_2


def test_mesmo_destinatario_produz_mesmo_event_id_replay_nao_duplica():
    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    resultado = (_resultado_aquisicao(),)
    params = resolver(_CLIENTE, _COMPETENCIA, resultado)

    ordem_1a_vez = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultado, destinatario=params.destinatario,
        preset_id=params.preset_id, tipo_documento=params.tipo_documento,
        mensagem_texto=params.mensagem_texto,
    )
    ordem_2a_vez = montar_ordem_distribuicao_documental_de_prestacao(
        resultados_aquisicao=resultado, destinatario=params.destinatario,
        preset_id=params.preset_id, tipo_documento=params.tipo_documento,
        mensagem_texto=params.mensagem_texto,
    )
    assert derivar_identidade_ordem_distribuicao(ordem_1a_vez) == derivar_identidade_ordem_distribuicao(ordem_2a_vez)


# ---------------------------------------------------------------------
# Airtable indisponível não impede leitura do Postgres / nenhuma
# chamada Airtable durante resolução / zero transporte real.
# ---------------------------------------------------------------------

def test_resolucao_funciona_sem_qualquer_objeto_airtable_construido():
    """Prova por construção: em nenhum momento desta cadeia (repositório
    em memória, que na V1 real seria o Postgres) um cliente/objeto
    Airtable é instanciado, importado ou passado -- resolução depende
    só do repositório interno, nunca de rede externa em runtime."""
    repo = RepositorioContatoColaboradorEmMemoria()
    _registrar_contato(repo, 'colab-1', '5511999998888')
    resolver = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repo, chave_fernet=_CHAVE_FERNET,
        preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA', tipo_documento='HOLERITE',
        montar_mensagem_texto=_mensagem_texto,
    )
    # Nenhum parâmetro de rede/Airtable existe na assinatura de
    # `construir_resolvedor_parametros_ordem_prestacao_contato_v1` nem
    # de `resolver_contato_colaborador_para_ordem` -- estruturalmente
    # impossível de chamar Airtable a partir daqui.
    assert resolver(_CLIENTE, _COMPETENCIA, (_resultado_aquisicao(),)) is not None


def test_modulo_resolvedor_nunca_importa_airtable_nem_app():
    import ast
    import inspect

    import magnata_os.orquestrador.resolver_parametros_ordem_prestacao_contato_v1 as modulo
    arvore = ast.parse(inspect.getsource(modulo))
    modulos_importados = {
        node.module for node in ast.walk(arvore) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name for node in ast.walk(arvore) if isinstance(node, ast.Import) for alias in node.names
    }
    proibidos = [m for m in modulos_importados if m and ('airtable' in m.lower() or m == 'app' or m.startswith('app.'))]
    assert proibidos == []


def test_modulo_resolvedor_nunca_importa_transporte_evolution_whatsapp_real():
    """Zero transporte real: o resolvedor monta parâmetros e para --
    nunca importa nada capaz de disparar uma mensagem de verdade."""
    import ast
    import inspect

    import magnata_os.orquestrador.resolver_parametros_ordem_prestacao_contato_v1 as modulo
    arvore = ast.parse(inspect.getsource(modulo))
    nomes_importados = {
        alias.asname or alias.name
        for node in ast.walk(arvore)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    proibidos = {'ExecutorEvolutionLegado', 'TransporteEvolutionLegado', 'compor_transporte_evolution_real'}
    assert not (nomes_importados & proibidos)
