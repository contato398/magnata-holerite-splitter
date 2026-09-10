"""Contrato puro de PortaObrigacaoAssinatura / ObrigacaoAssinatura.

Garante que o domínio permanece testável com um fake simples, sem
Airtable, Flask, requests nem HTTP -- e que o dataclass de retorno nunca
carrega campos sensíveis por acidente (CPF, nome de campo Airtable,
credencial).
"""
import dataclasses

from magnata_os.orquestrador.obrigacao_assinatura import (
    ObrigacaoAssinatura,
    PortaObrigacaoAssinatura,
)


class _AdapterFake:
    """Implementação mínima só para provar o contrato, sem I/O nenhum."""

    def __init__(self):
        self._obrigacoes = {}

    def criar_ou_recuperar(self, *, token_reservado, acao_execucao_id,
                            funcionario_id, tipo_documento, arquivo_record_id):
        existente = self._obrigacoes.get(acao_execucao_id)
        if existente is not None:
            return existente
        obrigacao = ObrigacaoAssinatura(
            assinatura_id=f'fake-{acao_execucao_id[:8]}',
            link=f'https://exemplo.invalid/assinatura/{token_reservado}',
            status='Pendente',
            tem_comprovante=False,
        )
        self._obrigacoes[acao_execucao_id] = obrigacao
        return obrigacao

    def consultar_por_correlacao(self, *, acao_execucao_id):
        return self._obrigacoes.get(acao_execucao_id)


def test_fake_satisfaz_o_protocol_estruturalmente():
    adapter: PortaObrigacaoAssinatura = _AdapterFake()
    assert hasattr(adapter, 'criar_ou_recuperar')
    assert hasattr(adapter, 'consultar_por_correlacao')


def test_consultar_por_correlacao_antes_de_criar_retorna_none_sem_criar():
    adapter = _AdapterFake()
    assert adapter.consultar_por_correlacao(acao_execucao_id='a' * 64) is None
    assert adapter._obrigacoes == {}  # nada foi criado por uma consulta


def test_criar_ou_recuperar_e_idempotente_pela_mesma_correlacao():
    adapter = _AdapterFake()
    primeira = adapter.criar_ou_recuperar(
        token_reservado='tok', acao_execucao_id='a' * 64,
        funcionario_id='rec1', tipo_documento='COMUNICADO',
        arquivo_record_id='recArq',
    )
    segunda = adapter.criar_ou_recuperar(
        token_reservado='tok', acao_execucao_id='a' * 64,
        funcionario_id='rec1', tipo_documento='COMUNICADO',
        arquivo_record_id='recArq',
    )
    assert primeira == segunda


def test_consultar_por_correlacao_depois_de_criar_encontra_sem_recriar():
    adapter = _AdapterFake()
    criada = adapter.criar_ou_recuperar(
        token_reservado='tok', acao_execucao_id='a' * 64,
        funcionario_id='rec1', tipo_documento='COMUNICADO',
        arquivo_record_id='recArq',
    )
    consultada = adapter.consultar_por_correlacao(acao_execucao_id='a' * 64)
    assert consultada == criada


def test_obrigacao_assinatura_so_tem_campos_opacos_nao_sensiveis():
    campos = {f.name for f in dataclasses.fields(ObrigacaoAssinatura)}
    proibidos = {'cpf', 'nome', 'nome_completo', 'credencial', 'api_key',
                 'field_id', 'table_id', 'anexo_url', 'attachment'}
    assert campos.isdisjoint(proibidos)
    assert campos == {
        'assinatura_id', 'link', 'status', 'tem_comprovante', 'evidencia_opaca',
    }


def test_obrigacao_assinatura_e_imutavel():
    obrigacao = ObrigacaoAssinatura(
        assinatura_id='x', link='https://exemplo.invalid', status='Pendente',
        tem_comprovante=False,
    )
    try:
        obrigacao.status = 'Assinado'
        assert False, 'deveria ser frozen'
    except dataclasses.FrozenInstanceError:
        pass
