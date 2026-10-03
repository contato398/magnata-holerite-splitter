"""Testa `construir_resolvedor_parametros_ordem_prestacao_fallback_
canal_v1` -- roteamento por canal (Plano A / Plano B) para
`ResolverParametrosOrdemPrestacao`, plugável em
`executar_prestacao_ate_distribuicao_documental_shadow` sem nenhuma
alteração no composition root nem no núcleo genérico.

2 blocos:
    1. Unidade pura do combinador (sem I/O, sem Prestação real) --
       roteamento, fallback, fail-closed e determinismo.
    2. Integração ponta a ponta reaproveitando os fakes/fixtures já
       existentes de `test_wiring_prestacao_ate_distribuicao_
       documental_shadow.py` (nunca reconstruídos) -- prova que o
       combinador, plugado no composition root real, roteia
       corretamente até PENDING, isola falha de 1 destinatário dos
       demais, e não duplica em replay.
"""
import ast
import hashlib

import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.orquestrador.resolver_parametros_ordem_prestacao_fallback_canal_v1 import (
    construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    ParametrosOrdemPrestacao,
)

from test_wiring_prestacao_ate_distribuicao_documental_shadow import (
    AGORA,
    _COMPETENCIA_AF,
    _contexto,
    _deps_nucleo,
    _documento_bruto,
    _executor_readonly_resolve_por_documento,
    modulo_composicao,
)
from unittest.mock import patch

from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (
    executar_prestacao_ate_distribuicao_documental_shadow,
)

_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-fallback-canal')
_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'colab-fallback-canal')

_PARAMETROS_WHATSAPP = ParametrosOrdemPrestacao(
    destinatario='5511999999999', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
    tipo_documento='HOLERITE', mensagem_texto='Segue seu holerite (WhatsApp):',
)
_PARAMETROS_EMAIL = ParametrosOrdemPrestacao(
    destinatario='colaborador-sintetico@exemplo.invalid', preset_id='DOCUMENTOS_SEM_ASSINATURA',
    tipo_documento='HOLERITE', mensagem_texto='Segue seu holerite (e-mail):',
)


# ---------------------------------------------------------------------
# 1. Unidade pura do combinador
# ---------------------------------------------------------------------

def test_plano_a_disponivel_e_usado_sem_chamar_plano_b():
    chamadas_b = []

    def plano_a(cliente, competencia, resultados_aquisicao):
        return _PARAMETROS_WHATSAPP

    def plano_b(cliente, competencia, resultados_aquisicao):
        chamadas_b.append(1)
        return _PARAMETROS_EMAIL

    resolver = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=plano_a, resolver_plano_b=plano_b,
    )
    resultado = resolver(_CLIENTE, _COMPETENCIA_AF, ())

    assert resultado == _PARAMETROS_WHATSAPP
    assert chamadas_b == []  # Plano B nunca chamado quando A resolve


def test_plano_a_indisponivel_cai_para_plano_b():
    def plano_a(cliente, competencia, resultados_aquisicao):
        return None  # WhatsApp indisponível para este colaborador

    def plano_b(cliente, competencia, resultados_aquisicao):
        return _PARAMETROS_EMAIL

    resolver = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=plano_a, resolver_plano_b=plano_b,
    )
    resultado = resolver(_CLIENTE, _COMPETENCIA_AF, ())

    assert resultado == _PARAMETROS_EMAIL


def test_nenhum_canal_disponivel_fail_closed_none():
    resolver = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=lambda *a: None, resolver_plano_b=lambda *a: None,
    )
    assert resolver(_CLIENTE, _COMPETENCIA_AF, ()) is None


def test_combinador_e_deterministico_mesma_entrada_mesma_saida():
    """Idempotência do combinador: pura função de dados já resolvidos,
    sem estado mutável -- chamar 2x com os mesmos argumentos devolve
    exatamente o mesmo resultado (não é o mesmo teste que a
    idempotência de gravação do núcleo, provada à parte)."""
    resolver = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=lambda *a: None, resolver_plano_b=lambda *a: _PARAMETROS_EMAIL,
    )
    primeiro = resolver(_CLIENTE, _COMPETENCIA_AF, ())
    segundo = resolver(_CLIENTE, _COMPETENCIA_AF, ())
    assert primeiro == segundo == _PARAMETROS_EMAIL


def test_argumentos_repassados_integralmente_aos_2_planos():
    """O combinador nunca reinterpreta cliente/competencia/resultados --
    só repassa, na ordem, para quem de fato resolve."""
    recebidos_a = []
    recebidos_b = []

    def plano_a(cliente, competencia, resultados_aquisicao):
        recebidos_a.append((cliente, competencia, resultados_aquisicao))
        return None

    def plano_b(cliente, competencia, resultados_aquisicao):
        recebidos_b.append((cliente, competencia, resultados_aquisicao))
        return _PARAMETROS_EMAIL

    resolver = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=plano_a, resolver_plano_b=plano_b,
    )
    sentinela_resultados = ('sentinela',)
    resolver(_CLIENTE, _COMPETENCIA_AF, sentinela_resultados)

    assert recebidos_a == [(_CLIENTE, _COMPETENCIA_AF, sentinela_resultados)]
    assert recebidos_b == [(_CLIENTE, _COMPETENCIA_AF, sentinela_resultados)]


def test_zero_import_de_transporte_neste_combinador_de_canal():
    """Checagem estrutural via AST (mesma técnica de
    `test_wiring_prestacao_distribuicao_documental_shadow.py::
    test_zero_import_de_transporte_ou_evolution_neste_wiring`) -- este
    módulo nunca importa WhatsApp/e-mail/transporte real, nem por
    aliasing nem por atributo."""
    import magnata_os.orquestrador.resolver_parametros_ordem_prestacao_fallback_canal_v1 as modulo
    with open(modulo.__file__, 'r', encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=modulo.__file__)
    proibidos = {
        'requests', 'boto3', 'psycopg', 'smtplib', 'imaplib',
        'transporte_real_habilitado', 'compor_porta_execucao',
        'ExecutorEvolutionLegado', 'executar_plano_disparo',
        'gerar_token_reservado_csprng', 'cryptography', 'Fernet',
    }
    nomes_encontrados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes_encontrados.update(alias.name.split('.')[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            nomes_encontrados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.Name):
            nomes_encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes_encontrados.add(no.attr)
    assert proibidos.isdisjoint(nomes_encontrados)


# ---------------------------------------------------------------------
# 2. Integração ponta a ponta -- reaproveita fixtures/fakes existentes
#    de test_wiring_prestacao_ate_distribuicao_documental_shadow.py.
# ---------------------------------------------------------------------

def test_integracao_plano_a_e_plano_b_roteiam_clientes_distintos_ate_pending():
    """2 clientes sintéticos, colaboradores distintos: cliente A só tem
    WhatsApp (Plano A); cliente B só tem e-mail (Plano B) -- ambos
    chegam a PENDING via o MESMO composition root
    (`executar_prestacao_ate_distribuicao_documental_shadow`), cada um
    roteado pelo canal correto, sem nenhuma alteração no núcleo nem no
    composition root."""
    cliente_a = ReferenciaCanonica('CLIENTE', 'cliente-fb-a')
    cliente_b = ReferenciaCanonica('CLIENTE', 'cliente-fb-b')
    colaborador_a = ReferenciaCanonica('COLABORADOR', 'colab-fb-a')
    colaborador_b = ReferenciaCanonica('COLABORADOR', 'colab-fb-b')

    conteudo_a = b'holerite-fb-a'
    hash_a = hashlib.sha256(conteudo_a).hexdigest()
    documento_a = _documento_bruto('doc-fb-a', hash_a)

    conteudo_b = b'holerite-fb-b'
    hash_b = hashlib.sha256(conteudo_b).hexdigest()
    documento_b = _documento_bruto('doc-fb-b', hash_b)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente_a, cliente_b),
        colaboradores_por_cliente={cliente_a: (colaborador_a,), cliente_b: (colaborador_b,)},
        candidatos_por_necessidade={
            (cliente_a, _COMPETENCIA_AF): (documento_a,),
            (cliente_b, _COMPETENCIA_AF): (documento_b,),
        },
        competencias_por_cliente={cliente_a: _COMPETENCIA_AF, cliente_b: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    # Só o colaborador A "tem" WhatsApp cadastrado (Plano A); só o
    # colaborador B "tem" e-mail cadastrado (Plano B) -- fakes
    # sintéticos, sem tocar em `contato_colaborador.py`/Airtable/rede.
    def plano_a(cliente, competencia, resultados_aquisicao):
        colaborador = resultados_aquisicao[0].necessidade.colaborador
        if colaborador == colaborador_a:
            return _PARAMETROS_WHATSAPP
        return None  # indisponível -- cai para Plano B

    def plano_b(cliente, competencia, resultados_aquisicao):
        colaborador = resultados_aquisicao[0].necessidade.colaborador
        if colaborador == colaborador_b:
            return _PARAMETROS_EMAIL
        return None

    resolver_fallback = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=plano_a, resolver_plano_b=plano_b,
    )

    fake_executor = _executor_readonly_resolve_por_documento({
        'doc-fb-a': (cliente_a, _COMPETENCIA_AF, colaborador_a),
        'doc-fb-b': (cliente_b, _COMPETENCIA_AF, colaborador_b),
    })
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento_a)
        deps['repositorio_documentos'].salvar(documento_b)
        deps['armazenamento'].armazenar(hash_a, conteudo_a, 'application/pdf', 'doc.pdf', len(conteudo_a))
        deps['armazenamento'].armazenar(hash_b, conteudo_b, 'application/pdf', 'doc.pdf', len(conteudo_b))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_fallback,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_fallback_canal_v1', instante=AGORA,
            **deps,
        )

    assert len(resultados) == 2
    funcionarios = {resultado.funcionario_id for resultado in resultados}
    assert funcionarios == {'colab-fb-a', 'colab-fb-b'}


def test_integracao_nenhum_canal_disponivel_isola_cliente_sem_travar_os_demais():
    """Cliente sem WhatsApp NEM e-mail (Plano A e B indisponíveis) vira
    zero Ordem para ele -- fail-closed, pendência humana (Plano C) --
    mas NÃO impede o cliente vizinho, que tem WhatsApp, de chegar a
    PENDING normalmente. Prova a exigência da missão: "falha de um
    destinatário não trava os demais"."""
    cliente_ok = ReferenciaCanonica('CLIENTE', 'cliente-fb-ok')
    cliente_sem_canal = ReferenciaCanonica('CLIENTE', 'cliente-fb-sem-canal')
    colaborador_ok = ReferenciaCanonica('COLABORADOR', 'colab-fb-ok')
    colaborador_sem_canal = ReferenciaCanonica('COLABORADOR', 'colab-fb-sem-canal')

    conteudo_ok = b'holerite-fb-ok'
    hash_ok = hashlib.sha256(conteudo_ok).hexdigest()
    documento_ok = _documento_bruto('doc-fb-ok', hash_ok)

    conteudo_sem = b'holerite-fb-sem-canal'
    hash_sem = hashlib.sha256(conteudo_sem).hexdigest()
    documento_sem = _documento_bruto('doc-fb-sem-canal', hash_sem)

    deps, _conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente_ok, cliente_sem_canal),
        colaboradores_por_cliente={
            cliente_ok: (colaborador_ok,), cliente_sem_canal: (colaborador_sem_canal,),
        },
        candidatos_por_necessidade={
            (cliente_ok, _COMPETENCIA_AF): (documento_ok,),
            (cliente_sem_canal, _COMPETENCIA_AF): (documento_sem,),
        },
        competencias_por_cliente={cliente_ok: _COMPETENCIA_AF, cliente_sem_canal: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    def plano_a(cliente, competencia, resultados_aquisicao):
        colaborador = resultados_aquisicao[0].necessidade.colaborador
        return _PARAMETROS_WHATSAPP if colaborador == colaborador_ok else None

    def plano_b(cliente, competencia, resultados_aquisicao):
        return None  # ninguém tem e-mail cadastrado neste cenário

    resolver_fallback = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=plano_a, resolver_plano_b=plano_b,
    )

    fake_executor = _executor_readonly_resolve_por_documento({
        'doc-fb-ok': (cliente_ok, _COMPETENCIA_AF, colaborador_ok),
        'doc-fb-sem-canal': (cliente_sem_canal, _COMPETENCIA_AF, colaborador_sem_canal),
    })
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento_ok)
        deps['repositorio_documentos'].salvar(documento_sem)
        deps['armazenamento'].armazenar(hash_ok, conteudo_ok, 'application/pdf', 'doc.pdf', len(conteudo_ok))
        deps['armazenamento'].armazenar(hash_sem, conteudo_sem, 'application/pdf', 'doc.pdf', len(conteudo_sem))
        resultados = executar_prestacao_ate_distribuicao_documental_shadow(
            contexto=contexto, resolver_parametros_ordem=resolver_fallback,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_fallback_canal_v1', instante=AGORA,
            **deps,
        )

    assert len(resultados) == 1
    assert resultados[0].funcionario_id == 'colab-fb-ok'


def test_integracao_replay_nao_duplica_acao_com_fallback_canal():
    """Idempotência ponta a ponta: rodar o composition root 2x com o
    mesmo resolvedor de fallback nunca duplica a ação PENDING (mesma
    invariante já provada para o resolvedor único por
    `test_wiring_prestacao_ate_distribuicao_documental_shadow.py::
    test_replay_nao_duplica_acao`, agora com o combinador plugado)."""
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-fb-replay')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-fb-replay')
    conteudo = b'holerite-fb-replay'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = _documento_bruto('doc-fb-replay', hash_sha256)

    deps, conexao = _deps_nucleo()
    contexto = _contexto(
        clientes=(cliente,), colaboradores_por_cliente={cliente: (colaborador,)},
        candidatos_por_necessidade={(cliente, _COMPETENCIA_AF): (documento,)},
        competencias_por_cliente={cliente: _COMPETENCIA_AF},
        repositorio_documentos=deps['repositorio_documentos'], armazenamento_arquivos=deps['armazenamento'],
    )

    resolver_fallback = construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
        resolver_plano_a=lambda *a: None,  # WhatsApp indisponível -- sempre cai para e-mail
        resolver_plano_b=lambda *a: _PARAMETROS_EMAIL,
    )

    fake_executor = _executor_readonly_resolve_por_documento({
        'doc-fb-replay': (cliente, _COMPETENCIA_AF, colaborador),
    })
    with patch.object(modulo_composicao, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo_composicao, 'executar_documento_readonly', fake_executor):
        deps['repositorio_documentos'].salvar(documento)
        deps['armazenamento'].armazenar(hash_sha256, conteudo, 'application/pdf', 'doc.pdf', len(conteudo))
        kwargs = dict(
            contexto=contexto, resolver_parametros_ordem=resolver_fallback,
            materializador=None, porta_assinatura=None,
            ator_referencia='ator:teste', proveniencia='teste_fallback_canal_v1', instante=AGORA,
            **deps,
        )
        primeiro = executar_prestacao_ate_distribuicao_documental_shadow(**kwargs)
        segundo = executar_prestacao_ate_distribuicao_documental_shadow(**kwargs)

    assert len(primeiro) == 1 and len(segundo) == 1
    assert primeiro[0].event_id == segundo[0].event_id
    assert primeiro[0].acao_execucao_id == segundo[0].acao_execucao_id
    # Gate J1b: todas as ações do plano são persistidas (texto + documento).
    assert len(conexao.linhas) == 2
