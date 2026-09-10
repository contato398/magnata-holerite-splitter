"""Observador de assinatura: somente consulta, nunca cria/envia, idempotente
(nunca duplica histórico), CONCLUIDO só com assinatura+comprovante.
"""
from datetime import datetime, timezone

from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura
from magnata_os.orquestrador.observador_assinatura import observar_e_registrar_transicao

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class _PortaFake:
    def __init__(self, obrigacao=None):
        self._obrigacao = obrigacao
        self.chamadas = 0
        self.criou = False

    def consultar_por_correlacao(self, *, acao_execucao_id):
        self.chamadas += 1
        return self._obrigacao

    def criar_ou_recuperar(self, **kwargs):
        self.criou = True
        raise AssertionError('observador nunca deve criar obrigação')


class _RepoConclusaoFake:
    def __init__(self, estado_inicial=None):
        self._estado = estado_inicial
        self.registros = []

    def estado_mais_recente(self, acao_execucao_id):
        return self._estado

    def registrar_transicao(self, registro):
        self.registros.append(registro)
        self._estado = registro.estado


def test_sem_obrigacao_retorna_none_sem_registrar():
    porta = _PortaFake(obrigacao=None)
    repo = _RepoConclusaoFake()
    resultado = observar_e_registrar_transicao(
        porta_assinatura=porta, repositorio_conclusao=repo,
        acao_execucao_id='a' * 64, instante=AGORA,
    )
    assert resultado is None
    assert repo.registros == []
    assert porta.criou is False


def test_pendente_mapeia_para_aguardando_assinatura():
    porta = _PortaFake(obrigacao=ObrigacaoAssinatura(
        assinatura_id='rec1', link='https://x', status='Pendente', tem_comprovante=False,
    ))
    repo = _RepoConclusaoFake()
    resultado = observar_e_registrar_transicao(
        porta_assinatura=porta, repositorio_conclusao=repo,
        acao_execucao_id='a' * 64, instante=AGORA,
    )
    assert resultado == 'AGUARDANDO_ASSINATURA'
    assert len(repo.registros) == 1


def test_assinado_sem_comprovante_nao_e_concluido():
    porta = _PortaFake(obrigacao=ObrigacaoAssinatura(
        assinatura_id='rec1', link='https://x', status='Assinado', tem_comprovante=False,
    ))
    repo = _RepoConclusaoFake()
    resultado = observar_e_registrar_transicao(
        porta_assinatura=porta, repositorio_conclusao=repo,
        acao_execucao_id='a' * 64, instante=AGORA,
    )
    assert resultado == 'ASSINADO'


def test_concluido_exige_assinatura_e_comprovante_juntos():
    porta = _PortaFake(obrigacao=ObrigacaoAssinatura(
        assinatura_id='rec1', link='https://x', status='Assinado', tem_comprovante=True,
    ))
    repo = _RepoConclusaoFake()
    resultado = observar_e_registrar_transicao(
        porta_assinatura=porta, repositorio_conclusao=repo,
        acao_execucao_id='a' * 64, instante=AGORA,
    )
    assert resultado == 'CONCLUIDO'


def test_mesmo_estado_observado_duas_vezes_nunca_duplica_historico():
    porta = _PortaFake(obrigacao=ObrigacaoAssinatura(
        assinatura_id='rec1', link='https://x', status='Pendente', tem_comprovante=False,
    ))
    repo = _RepoConclusaoFake(estado_inicial='AGUARDANDO_ASSINATURA')
    observar_e_registrar_transicao(
        porta_assinatura=porta, repositorio_conclusao=repo,
        acao_execucao_id='a' * 64, instante=AGORA,
    )
    assert repo.registros == []  # já estava nesse estado, nada novo gravado


def test_mudanca_de_estado_registra_exatamente_uma_transicao():
    porta = _PortaFake(obrigacao=ObrigacaoAssinatura(
        assinatura_id='rec1', link='https://x', status='Assinado', tem_comprovante=True,
    ))
    repo = _RepoConclusaoFake(estado_inicial='ASSINADO')
    observar_e_registrar_transicao(
        porta_assinatura=porta, repositorio_conclusao=repo,
        acao_execucao_id='a' * 64, instante=AGORA,
    )
    assert len(repo.registros) == 1
    assert repo.registros[0].estado == 'CONCLUIDO'
