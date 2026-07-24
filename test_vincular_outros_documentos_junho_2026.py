"""
Testes do comando TEMPORARIO de vinculacao
(scripts/vincular_outros_documentos_junho_2026.py).

Nenhum destes testes acessa o Airtable real -- requests.get/patch,
_at_throttle e input sao mockados. O comando em si nunca e executado
contra producao a partir daqui, e o modo 'aplicar' nunca e chamado com
dados reais.
"""
import requests
from unittest.mock import patch, Mock

import pytest

from scripts import vincular_outros_documentos_junho_2026 as vod


@pytest.fixture(autouse=True)
def _sem_throttle_real():
    """_at_throttle() dorme no mundo real (rate limit do Airtable) -- nos
    testes isso so soma segundos sem nenhum valor. Mockado em todos os
    testes deste arquivo."""
    with patch('scripts.vincular_outros_documentos_junho_2026._at_throttle'):
        yield


def _resp(status_code=200, fields=None, record_id=None):
    m = Mock()
    m.status_code = status_code
    m.ok = 200 <= status_code < 300
    body = {'fields': fields or {}}
    if record_id is not None:
        body['id'] = record_id
    m.json = lambda: body
    m.text = ''
    if m.ok:
        m.raise_for_status = Mock()
    else:
        m.raise_for_status = Mock(side_effect=requests.exceptions.HTTPError(str(status_code)))
    return m


def _campos_envio_com_ids_string(ids, data=vod.DATA_ENVIADO_ESPERADA):
    """Formato alternativo do campo de link: lista de IDs string, sem
    objeto {'id','name'} -- o formato real que motivou a correcao."""
    return {
        vod.CAMPO_FUNC_ENVIO: list(ids),
        vod.CAMPO_ENVIADO_EM: f'{data}T00:00:00.000Z',
    }


def _campos_od_vazio(nome):
    return {vod.F_OD_DOCUMENTO: f'Assiduidade Junho 2026 - {nome}', vod.F_OD_ENVIO: []}


def _campos_envio_ok(nome, data=vod.DATA_ENVIADO_ESPERADA):
    return {
        vod.CAMPO_FUNC_ENVIO: [{'id': 'recFuncX', 'name': nome}],
        vod.CAMPO_ENVIADO_EM: f'{data}T00:00:00.000Z',
    }


def _nomes_sinteticos():
    return {rid: f'COLABORADOR {i}' for i, rid in enumerate(vod.PARES_APROVADOS)}


def _mock_get_lote_ok(nomes_por_record_id):
    """side_effect para requests.get cobrindo os 39 pares, todos validos."""
    def _fake(url, **kwargs):
        for record_id, envio_id in vod.PARES_APROVADOS.items():
            nome = nomes_por_record_id[record_id]
            if url.endswith(f'/{vod.TABLE_OUTROS_DOCS}/{record_id}'):
                return _resp(200, _campos_od_vazio(nome))
            if url.endswith(f'/{vod.TABLE_ENVIOS}/{envio_id}'):
                return _resp(200, _campos_envio_ok(nome))
        raise AssertionError(f'GET inesperado: {url}')
    return _fake


# --------------------------------------------------------------- allowlist --

def test_allowlist_tem_exatamente_39_pares():
    assert len(vod.PARES_APROVADOS) == 39


def test_nao_importa_funcao_de_anexacao():
    """Estruturalmente, este comando nao pode chamar
    _aplicar_outros_documentos_no_envio -- nao foi importada."""
    assert not hasattr(vod, '_aplicar_outros_documentos_no_envio')


# -------------------------------------------------------- validar_par --

def test_validar_par_ok():
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, _campos_envio_ok('FULANO DE TAL')),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'ok'


def test_validar_par_ja_vinculado():
    campos_od = {vod.F_OD_DOCUMENTO: 'Assiduidade Junho 2026 - FULANO',
                 vod.F_OD_ENVIO: [{'id': 'recEnvio1'}]}
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [_resp(200, campos_od), _resp(200, _campos_envio_ok('FULANO'))]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'ja_vinculado'


def test_validar_par_vinculo_divergente_ja_existe():
    campos_od = {vod.F_OD_DOCUMENTO: 'Assiduidade Junho 2026 - FULANO',
                 vod.F_OD_ENVIO: [{'id': 'recOUTROENVIO'}]}
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [_resp(200, campos_od)]  # nem chega a buscar o Envio esperado
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'vinculo_diferente_ja_existe'


def test_validar_par_registro_origem_nao_encontrado():
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [_resp(404)]
        resultado = vod.validar_par('recOD_inexistente', 'recEnvio1')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'registro_origem_nao_encontrado'


def test_validar_par_envio_destino_nao_encontrado():
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [_resp(200, _campos_od_vazio('FULANO')), _resp(404)]
        resultado = vod.validar_par('recOD1', 'recEnvio_inexistente')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'envio_destino_nao_encontrado'


def test_validar_par_funcionario_incompativel():
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, _campos_envio_ok('OUTRA PESSOA COMPLETAMENTE DIFERENTE')),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'funcionario_incompativel'


def test_validar_par_funcionario_lista_ids_string_compativel():
    """Funcionario(s) Vinculado(s) como lista de IDs string (formato real
    retornado pela API em leitura de registro unico) -- deve buscar o
    registro do Funcionario e comparar pelo Nome Completo."""
    campos_envio = _campos_envio_com_ids_string(['recFunc1'])
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, campos_envio),
            _resp(200, {'Nome Completo': 'FULANO DE TAL'}, record_id='recFunc1'),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'ok'


def test_validar_par_funcionario_lista_ids_string_incompativel():
    campos_envio = _campos_envio_com_ids_string(['recFunc1'])
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, campos_envio),
            _resp(200, {'Nome Completo': 'PESSOA COMPLETAMENTE DIFERENTE'}, record_id='recFunc1'),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'funcionario_incompativel'


def test_validar_par_funcionario_objeto_id_name_compativel():
    """Formato antigo {'id':..., 'name':...} -- precisa continuar
    funcionando depois da correcao (regressao)."""
    campos_envio = _campos_envio_ok('FULANO DE TAL')
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, campos_envio),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'ok'


def test_validar_par_funcionario_campo_vazio():
    campos_envio = _campos_envio_com_ids_string([])
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, campos_envio),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'funcionario_incompativel'


def test_validar_par_data_enviado_em_diferente():
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get') as mock_get:
        mock_get.side_effect = [
            _resp(200, _campos_od_vazio('FULANO DE TAL')),
            _resp(200, _campos_envio_ok('FULANO DE TAL', data='2026-07-10')),
        ]
        resultado = vod.validar_par('recOD1', 'recEnvio1')
    assert resultado['status'] == 'divergente'
    assert resultado['motivo'] == 'data_enviado_em_diferente'


# ------------------------------------------------------------- dry-run --

def test_dry_run_nunca_escreve():
    nomes = _nomes_sinteticos()
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_mock_get_lote_ok(nomes)), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch') as mock_patch:
        resultados = vod.cmd_dry_run('corr123')

    mock_patch.assert_not_called()
    assert len(resultados) == 39
    assert all(v['status'] == 'ok' for v in resultados.values())


# ------------------------------------------------------------- aplicar --

def test_aplicar_dos_39_com_confirmacao_faz_exatamente_39_patches():
    nomes = _nomes_sinteticos()
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_mock_get_lote_ok(nomes)), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch',
               return_value=_resp(200, {})) as mock_patch:
        resultado = vod.cmd_aplicar('corr123', confirmar_input=lambda _: 'CONFIRMAR')

    assert mock_patch.call_count == 39
    assert len(resultado['aplicados']) == 39
    assert resultado['erros'] == []

    # cada PATCH so mexe em F_OD_ENVIO -- nunca em Arquivos
    for chamada in mock_patch.call_args_list:
        campos = chamada.kwargs['json']['fields']
        assert set(campos.keys()) == {vod.F_OD_ENVIO}
        assert 'Arquivos' not in campos


def test_aplicar_confirmacao_incorreta_nao_escreve():
    nomes = _nomes_sinteticos()
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_mock_get_lote_ok(nomes)), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch') as mock_patch:
        resultado = vod.cmd_aplicar('corr123', confirmar_input=lambda _: 'confirmar')  # minusculo

    assert resultado == 'cancelado'
    mock_patch.assert_not_called()


def test_aplicar_bloqueia_tudo_se_houver_qualquer_divergencia():
    nomes = _nomes_sinteticos()
    algum_record_id = next(iter(vod.PARES_APROVADOS))

    def _get_com_uma_divergencia(url, **kwargs):
        for record_id, envio_id in vod.PARES_APROVADOS.items():
            nome = nomes[record_id]
            if url.endswith(f'/{vod.TABLE_OUTROS_DOCS}/{record_id}'):
                return _resp(200, _campos_od_vazio(nome))
            if url.endswith(f'/{vod.TABLE_ENVIOS}/{envio_id}'):
                if record_id == algum_record_id:
                    # funcionario incompativel so neste par
                    return _resp(200, _campos_envio_ok('PESSOA ERRADA'))
                return _resp(200, _campos_envio_ok(nome))
        raise AssertionError(f'GET inesperado: {url}')

    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_get_com_uma_divergencia), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch') as mock_patch:
        resultado = vod.cmd_aplicar('corr123', confirmar_input=lambda _: 'CONFIRMAR')

    assert resultado == 'bloqueado'
    mock_patch.assert_not_called()  # nem os 38 pares OK sao aplicados


def test_aplicar_ja_vinculados_nao_geram_patch_e_nao_bloqueiam():
    nomes = _nomes_sinteticos()
    ja_vinculado_id, ja_vinculado_envio = next(iter(vod.PARES_APROVADOS.items()))

    def _get_com_um_ja_vinculado(url, **kwargs):
        for record_id, envio_id in vod.PARES_APROVADOS.items():
            nome = nomes[record_id]
            if url.endswith(f'/{vod.TABLE_OUTROS_DOCS}/{record_id}'):
                if record_id == ja_vinculado_id:
                    campos = {vod.F_OD_DOCUMENTO: f'Assiduidade Junho 2026 - {nome}',
                              vod.F_OD_ENVIO: [{'id': ja_vinculado_envio}]}
                    return _resp(200, campos)
                return _resp(200, _campos_od_vazio(nome))
            if url.endswith(f'/{vod.TABLE_ENVIOS}/{envio_id}'):
                return _resp(200, _campos_envio_ok(nome))
        raise AssertionError(f'GET inesperado: {url}')

    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_get_com_um_ja_vinculado), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch',
               return_value=_resp(200, {})) as mock_patch:
        resultado = vod.cmd_aplicar('corr123', confirmar_input=lambda _: 'CONFIRMAR')

    assert mock_patch.call_count == 38  # 39 - 1 ja vinculado
    assert len(resultado['aplicados']) == 38
    assert resultado['ja_vinculados'] == [ja_vinculado_id]


def test_aplicar_falha_parcial_de_api():
    nomes = _nomes_sinteticos()
    falha_id = next(iter(vod.PARES_APROVADOS))

    def _patch_com_uma_falha(url, **kwargs):
        if f'/{vod.TABLE_OUTROS_DOCS}/{falha_id}' in url:
            return _resp(500, {})
        return _resp(200, {})

    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_mock_get_lote_ok(nomes)), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch',
               side_effect=_patch_com_uma_falha) as mock_patch:
        resultado = vod.cmd_aplicar('corr123', confirmar_input=lambda _: 'CONFIRMAR')

    assert mock_patch.call_count == 39  # tenta todos, mesmo apos a falha
    assert len(resultado['aplicados']) == 38
    assert len(resultado['erros']) == 1
    assert resultado['erros'][0]['record_id'] == falha_id


# ------------------------------------------------------------ auditoria --

def test_snapshot_pre_patch_registra_campos_obrigatorios():
    nomes = _nomes_sinteticos()
    with patch('scripts.vincular_outros_documentos_junho_2026.requests.get',
               side_effect=_mock_get_lote_ok(nomes)), \
         patch('scripts.vincular_outros_documentos_junho_2026.requests.patch',
               return_value=_resp(200, {})), \
         patch('scripts.vincular_outros_documentos_junho_2026.logger') as mock_logger:
        vod.cmd_aplicar('corr-snapshot', confirmar_input=lambda _: 'CONFIRMAR')

    linhas_snapshot = [
        ' '.join(str(a) for a in chamada.args)
        for chamada in mock_logger.info.call_args_list
        if 'snapshot_pre_patch' in ' '.join(str(a) for a in chamada.args)
    ]
    assert len(linhas_snapshot) == 39
    primeira = linhas_snapshot[0]
    for campo in ('record_id', 'valor_anterior_F_OD_ENVIO', 'valor_novo_F_OD_ENVIO',
                  'timestamp', 'correlation_id', 'corr-snapshot'):
        assert campo in primeira
