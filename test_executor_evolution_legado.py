"""ExecutorEvolutionLegado: ponte fina PortaExecucaoAcao -> PortaTransporteWhatsapp.

Cobre: execução exata da AcaoEnvio (sem reotimizar/reinterpretar), extração
de ID externo, e a regra mais rigorosa de 2xx sem ID -> ENVIO_EXTERNO_INCERTO
(nunca SUCCEEDED), sem alterar o comportamento do transporte legado em si.
"""
import pytest

from magnata_os.orquestrador.adapters.executor_evolution_legado import ExecutorEvolutionLegado
from magnata_os.orquestrador.classificador_falha import FalhaEnvioIncerto
from magnata_os.orquestrador.executor_persistente_fake import ResultadoExecucaoPorta
from magnata_os.orquestrador.plano_comunicacao import AcaoEnvio
from magnata_os.orquestrador.transporte_comunicacao import TransporteComunicacaoError


class _TransporteFake:
    def __init__(self, texto=None, video=None, documento=None):
        self._texto = texto if texto is not None else {'key': {'id': 'T1'}}
        self._video = video if video is not None else {'key': {'id': 'V1'}}
        self._documento = documento if documento is not None else {'key': {'id': 'D1'}}
        self.chamadas = []

    def enviar_texto(self, *, numero, texto):
        self.chamadas.append(('texto', numero, texto))
        return self._texto

    def enviar_video(self, *, numero, conteudo, nome_arquivo, legenda=''):
        self.chamadas.append(('video', numero, conteudo, nome_arquivo, legenda))
        return self._video

    def enviar_documento(self, *, numero, conteudo, nome_arquivo, legenda=''):
        self.chamadas.append(('documento', numero, conteudo, nome_arquivo, legenda))
        return self._documento


def test_executa_acao_de_texto_exatamente_como_autorizada():
    transporte = _TransporteFake()
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(destinatario='5511999999999', ordem=1, tipo='texto', texto='mensagem exata')

    resultado = executor.executar(acao)

    assert transporte.chamadas == [('texto', '5511999999999', 'mensagem exata')]
    assert isinstance(resultado, ResultadoExecucaoPorta)
    assert resultado.resultado_referencia == 'T1'


def test_nao_reotimiza_nem_altera_legenda_de_video():
    transporte = _TransporteFake()
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(
        destinatario='5511999999999', ordem=1, tipo='video',
        conteudo=b'bytes-video', nome='v.mp4', legenda='legenda exata autorizada',
    )

    executor.executar(acao)

    assert transporte.chamadas == [
        ('video', '5511999999999', b'bytes-video', 'v.mp4', 'legenda exata autorizada'),
    ]


def test_documento_repassa_conteudo_e_nome_sem_alteracao():
    transporte = _TransporteFake()
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(
        destinatario='5511999999999', ordem=2, tipo='documento',
        conteudo=b'%PDF-1.4', nome='doc.pdf',
    )

    resultado = executor.executar(acao)

    assert transporte.chamadas == [('documento', '5511999999999', b'%PDF-1.4', 'doc.pdf', '')]
    assert resultado.resultado_referencia == 'D1'


def test_2xx_sem_id_externo_nunca_vira_sucesso_regra_mais_rigorosa():
    transporte = _TransporteFake(texto={'status': 'ok'})  # sem key.id nem id
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(destinatario='5511999999999', ordem=1, tipo='texto', texto='oi')

    with pytest.raises(FalhaEnvioIncerto):
        executor.executar(acao)


def test_2xx_com_id_em_id_plano_tambem_e_aceito():
    transporte = _TransporteFake(texto={'id': 'PLANO1'})
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(destinatario='5511999999999', ordem=1, tipo='texto', texto='oi')

    resultado = executor.executar(acao)

    assert resultado.resultado_referencia == 'PLANO1'


def test_evidencia_nunca_contem_texto_nem_destinatario_em_claro():
    transporte = _TransporteFake()
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(
        destinatario='5511999999999', ordem=1, tipo='texto',
        texto='mensagem sensivel que nunca deve ir para a evidencia',
    )

    resultado = executor.executar(acao)

    assert b'5511999999999' not in resultado.evidencia
    assert b'mensagem sensivel' not in resultado.evidencia


def test_tipo_nao_executavel_propaga_erro_de_transporte_sem_reinterpretar():
    transporte = _TransporteFake()
    executor = ExecutorEvolutionLegado(transporte=transporte)
    acao = AcaoEnvio(destinatario='5511999999999', ordem=1, tipo='imagem')

    with pytest.raises(TransporteComunicacaoError):
        executor.executar(acao)


def test_falha_do_transporte_propaga_sem_reclassificar():
    class _TransporteQueFalha:
        def enviar_texto(self, *, numero, texto):
            raise FalhaEnvioIncerto('já classificado pelo adapter de transporte')

    executor = ExecutorEvolutionLegado(transporte=_TransporteQueFalha())
    acao = AcaoEnvio(destinatario='5511999999999', ordem=1, tipo='texto', texto='oi')

    with pytest.raises(FalhaEnvioIncerto):
        executor.executar(acao)
