"""Wiring shadow ponta a ponta: token → preview → autorização → obrigação
→ PlanoDisparo → Envelope → persistência. Sempre sem transporte real,
sempre sem Airtable/Evolution real -- prova a composição, nunca envia.
"""
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.orquestrador.autorizacao_gate import RepositorioAutorizacoesGateEmMemoria
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.wiring_assinatura_comunicacao_shadow import (
    autorizar_preview_assinatura_shadow,
    gerar_token_reservado_csprng,
    materializar_assinatura_shadow,
    montar_intencao_assinatura_shadow,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((sql, params))
        self._ultimo = (sql, params)

    def fetchone(self):
        sql, params = self._ultimo
        # Simula o INSERT ... ON CONFLICT DO NOTHING RETURNING acao_execucao_id
        # de materializar_registros: devolve a identidade que foi de fato
        # inserida (primeiro parâmetro da linha), nunca um valor inventado.
        if 'RETURNING acao_execucao_id' in sql and params:
            return (params[0],)
        return None


class _Conexao:
    def __init__(self):
        self.executados = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _PortaAssinaturaFake:
    def __init__(self):
        self.chamadas_criar = []

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id,
                            funcionario_id, tipo_documento, arquivo_record_id):
        self.chamadas_criar.append((token_reservado, acao_execucao_id))
        return ObrigacaoAssinatura(
            assinatura_id='rec-fake-1',
            link=f'https://exemplo.invalid/assinatura/{token_reservado}',
            status='Pendente', tem_comprovante=False,
        )

    def consultar_por_correlacao(self, *, acao_execucao_id):
        raise AssertionError('wiring de criação nunca deve consultar')


def test_token_e_csprng_com_32_bytes_e_formato_canonico():
    import base64
    token = gerar_token_reservado_csprng()
    assert len(token) == 43
    decodificado = base64.urlsafe_b64decode(token + '=')
    assert len(decodificado) == 32
    # canônico: reencodar deve produzir exatamente a mesma string
    assert base64.urlsafe_b64encode(decodificado).rstrip(b'=').decode('ascii') == token


def test_dois_tokens_gerados_nunca_colidem():
    tokens = {gerar_token_reservado_csprng() for _ in range(200)}
    assert len(tokens) == 200


def test_token_vem_antes_do_preview_link_ja_embutido_no_texto():
    token = 'dummy'
    texto_exato, preview = montar_intencao_assinatura_shadow(
        destinatario='5511999999999', texto_sem_link='Segue seu holerite:',
        token_reservado=token,
    )
    assert token in texto_exato
    assert preview.texto_sha256  # hash já reflete o texto COM o link


def test_preview_sem_token_reservado_falha_explicitamente():
    from magnata_os.orquestrador.wiring_assinatura_comunicacao_shadow import (
        WiringAssinaturaComunicacaoError,
    )
    with pytest.raises(WiringAssinaturaComunicacaoError):
        montar_intencao_assinatura_shadow(
            destinatario='5511999999999', texto_sem_link='oi', token_reservado='',
        )


def test_composicao_completa_ate_persistencia_sem_transporte():
    token = gerar_token_reservado_csprng()
    texto_exato, preview = montar_intencao_assinatura_shadow(
        destinatario='5511999999999', texto_sem_link='Segue seu holerite:',
        token_reservado=token,
    )

    repo_autorizacoes = RepositorioAutorizacoesGateEmMemoria()
    autorizacao = autorizar_preview_assinatura_shadow(
        repositorio_autorizacoes=repo_autorizacoes, preview=preview,
        event_id='evento-assinatura-1', ator_referencia='rh:teste',
        proveniencia='teste:sintetico', instante=AGORA,
    )

    porta = _PortaAssinaturaFake()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conexao = _Conexao()
    repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    resultado = materializar_assinatura_shadow(
        porta_assinatura=porta, repositorio_acoes=repositorio_acoes,
        armazenamento=armazenamento, preview=preview, autorizacao=autorizacao,
        texto_exato=texto_exato, token_reservado=token,
        funcionario_id='recFUNC',
        tipo_documento='COMUNICADO', arquivo_record_id='recARQ',
        event_id='evento-assinatura-1', instante=AGORA,
    )

    assert resultado.obrigacao.assinatura_id == 'rec-fake-1'
    # a obrigação de assinatura foi criada com A MESMA correlação
    # (acao_execucao_id) que terminou persistida na ação de transporte --
    # é essa igualdade que permite ao observador reconciliar depois.
    assert porta.chamadas_criar == [(token, resultado.acao_persistida.acao_execucao_id)]
    assert resultado.acao_persistida.estado == EstadoAcaoExecucaoPlano.PENDING
    assert resultado.envelope_sha256
    # nunca importa transporte real nem infraestrutura de fornecedor --
    # só os imports de módulo, não a prosa dos comentários (que
    # legitimamente EXPLICA o que o wiring evita, citando "Evolution").
    import ast
    import magnata_os.orquestrador.wiring_assinatura_comunicacao_shadow as modulo
    arvore = ast.parse(open(modulo.__file__).read())
    nomes_importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes_importados.update(alias.name.split('.')[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes_importados.add(no.module.split('.')[0])
    assert nomes_importados.isdisjoint({'requests', 'flask', 'app'})
    assert 'transporte_comunicacao' not in nomes_importados
    assert 'transporte_evolution_legado' not in nomes_importados


def test_alterar_texto_depois_da_autorizacao_invalida_o_plano():
    from magnata_os.orquestrador.plano_comunicacao import PlanoComunicacaoError

    token = gerar_token_reservado_csprng()
    texto_exato, preview = montar_intencao_assinatura_shadow(
        destinatario='5511999999999', texto_sem_link='Segue seu holerite:',
        token_reservado=token,
    )
    repo_autorizacoes = RepositorioAutorizacoesGateEmMemoria()
    autorizacao = autorizar_preview_assinatura_shadow(
        repositorio_autorizacoes=repo_autorizacoes, preview=preview,
        event_id='evento-assinatura-1', ator_referencia='rh:teste',
        proveniencia='teste:sintetico', instante=AGORA,
    )

    from magnata_os.orquestrador.plano_comunicacao import montar_plano_disparo
    with pytest.raises(PlanoComunicacaoError):
        montar_plano_disparo(
            preview=preview, texto='texto diferente do autorizado',
            conteudos=(), preview_id_autorizado=autorizacao.preview_id,
            autorizacao_explicita=True,
        )
