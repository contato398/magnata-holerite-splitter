"""Testes de contrato puro para as funções de parse/decisão/mapeamento de
campos de `src/sync_new_employees.py` — sem rede, sem Airtable, sem
Secullum real. Achado da auditoria "Testes, CI e observabilidade"
(2026-10-03): este módulo (ingestão de colaboradores a partir do header
do holerite, estruturação no Airtable, mapeamento de cargo para a
Secullum) tinha 24% de cobertura.

Decisão de arquitetura de teste (coordenador, 2026-10-03): fixture
sintética derivada das próprias estruturas que o código já faz parse
(texto de header de holerite, dict de registro do Airtable), nunca
chamada real ao Airtable/Secullum. Os pontos de fronteira de rede
(`buscar_funcionario_por_cpf`) são substituídos por dublê via
`monkeypatch.setattr`, nunca mockando `requests` diretamente — mesmo
padrão já usado em outros testes do repositório.
"""
import pytest

import src.sync_new_employees as sync_mod
from src.sync_new_employees import (
    GRUPO_ESCALA_A,
    STATUS_PENDENTE,
    _horario_para_cargo,
    _normalizar_cargo,
    _so_digitos,
    criar_ou_completar_funcionario,
    extrair_dados_holerite,
    sincronizar_lista_cpfs,
)


# ── _so_digitos / _normalizar_cargo ───────────────────────────────────────

def test_so_digitos():
    assert _so_digitos('123.456.789-01') == '12345678901'
    assert _so_digitos(None) == ''


def test_normalizar_cargo_remove_acento_e_colapsa_espaco():
    assert _normalizar_cargo('Serviços  Gerais') == 'SERVICOS GERAIS'
    assert _normalizar_cargo(None) == ''


# ── _horario_para_cargo ────────────────────────────────────────────────────

def test_horario_para_cargo_delega_para_ingestao_secullum():
    from src.ingestao_secullum import horario_para_cargo as horario_ingestao
    assert _horario_para_cargo('Auxiliar de Limpeza') == horario_ingestao('Auxiliar de Limpeza')


def test_horario_para_cargo_cai_no_padrao_se_delegacao_falhar(monkeypatch):
    import src.ingestao_secullum as ingestao_mod

    def _explode(cargo):
        raise RuntimeError('falha sintética')

    monkeypatch.setattr(ingestao_mod, 'horario_para_cargo', _explode)
    assert _horario_para_cargo('Qualquer Cargo') == sync_mod.SECULLUM_HORARIO_NUMERO_PADRAO


# ── extrair_dados_holerite ─────────────────────────────────────────────────

_HEADER_HOLERITE = (
    '347 DAVI LEME DOS SANTOS 517410 1 1\n'
    'CONTROLADOR DE ACESSO Admissão: 04/05/2026\n'
    'CPF: 123.456.789-01\n'
)


def test_extrair_dados_holerite_header_completo():
    dados = extrair_dados_holerite(_HEADER_HOLERITE)
    assert dados['nome'] == 'DAVI LEME DOS SANTOS'
    assert dados['cargo'] == 'CONTROLADOR DE ACESSO'
    assert dados['admissao'] == '04/05/2026'
    assert dados['cpf'] == '123.456.789-01'
    assert dados['pis'] is None  # modelo atual nunca imprime PIS -- não é falha de regex


def test_extrair_dados_holerite_texto_vazio_retorna_todas_chaves_none():
    dados = extrair_dados_holerite('')
    assert dados == {'nome': None, 'cargo': None, 'admissao': None, 'cpf': None, 'pis': None}


def test_extrair_dados_holerite_pis_quando_presente():
    texto = _HEADER_HOLERITE + 'PIS: 123.45678.90-1\n'
    dados = extrair_dados_holerite(texto)
    assert dados['pis'] == '123.45678.90-1'


def test_extrair_dados_holerite_so_cpf_sem_cabecalho_de_nome():
    dados = extrair_dados_holerite('CPF: 123.456.789-01\n')
    assert dados['cpf'] == '123.456.789-01'
    assert dados['nome'] is None
    assert dados['cargo'] is None


# ── criar_ou_completar_funcionario (dry_run -- decisão/mapeamento, sem rede) ──

def _dados(nome='DAVI LEME DOS SANTOS', cargo='CONTROLADOR DE ACESSO',
           admissao='04/05/2026', cpf='123.456.789-01', pis=None):
    return {'nome': nome, 'cargo': cargo, 'admissao': admissao, 'cpf': cpf, 'pis': pis}


def test_criar_ou_completar_funcionario_sem_cpf_eh_erro():
    resultado = criar_ou_completar_funcionario(_dados(cpf=None), dry_run=True)
    assert resultado == {'status': 'erro', 'motivo': 'CPF não extraído do holerite'}


def test_criar_ou_completar_funcionario_novo_mapeia_campos_e_converte_data(monkeypatch):
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf', lambda cpf: None)
    resultado = criar_ou_completar_funcionario(_dados(), dry_run=True)
    assert resultado['status'] == 'novo_dry_run'
    campos = resultado['campos']
    assert campos[sync_mod.F_FUNC_CPF] == '123.456.789-01'
    assert campos[sync_mod.F_FUNC_STATUS_SYNC] == STATUS_PENDENTE
    assert campos[sync_mod.F_FUNC_NOME] == 'DAVI LEME DOS SANTOS'
    assert campos[sync_mod.F_FUNC_CARGO] == 'CONTROLADOR DE ACESSO'
    # DD/MM/AAAA (holerite) -> AAAA-MM-DD (Airtable)
    assert campos[sync_mod.F_FUNC_ADMISSAO] == '2026-05-04'
    assert sync_mod.F_FUNC_PIS not in campos  # PIS ausente não entra como campo vazio


def test_criar_ou_completar_funcionario_existente_sem_campo_vazio_nao_altera_nada(monkeypatch):
    existente = {'id': 'rec1', 'fields': {'Cargo': 'JA PREENCHIDO', 'Data de Admissão': '2020-01-01', 'PIS': '123'}}
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf', lambda cpf: existente)
    resultado = criar_ou_completar_funcionario(_dados(), dry_run=True)
    assert resultado == {'status': 'existente_completo', 'id': 'rec1'}


def test_criar_ou_completar_funcionario_existente_completa_so_o_que_falta(monkeypatch):
    # Cargo já preenchido (nunca sobrescrever); Admissão e PIS vazios -- completar.
    existente = {'id': 'rec1', 'fields': {'Cargo': 'JA PREENCHIDO'}}
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf', lambda cpf: existente)
    resultado = criar_ou_completar_funcionario(_dados(pis='12345678901'), dry_run=True)
    assert resultado['status'] == 'existente_a_completar'
    campos = resultado['campos']
    assert sync_mod.F_FUNC_CARGO not in campos  # nunca sobrescreve dado já preenchido
    assert campos[sync_mod.F_FUNC_ADMISSAO] == '2026-05-04'
    assert campos[sync_mod.F_FUNC_PIS] == '12345678901'


# ── sincronizar_lista_cpfs (dry_run -- mapeamento de cargo p/ Secullum) ──────

def _registro_airtable(cpf='12345678901', nome='DAVI LEME DOS SANTOS',
                        cargo='Controlador de Acesso', pis=None,
                        admissao=None, created_time='2026-01-15T10:00:00.000Z'):
    fields = {'Nome Completo': nome, 'Cargo': cargo, 'Código': '347'}
    if pis:
        fields['PIS'] = pis
    if admissao:
        fields['Data de Admissão'] = admissao
    return {'id': 'rec1', 'createdTime': created_time, 'fields': fields}


def test_sincronizar_lista_cpfs_cpf_nao_encontrado(monkeypatch):
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf', lambda cpf: None)
    resultado = sincronizar_lista_cpfs(['00000000000'], dry_run=True)
    assert resultado == [{'cpf': '00000000000', 'erro': 'CPF não encontrado no Airtable'}]


def test_sincronizar_lista_cpfs_cargo_sem_mapeamento_conhecido(monkeypatch):
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf',
                         lambda cpf: _registro_airtable(cargo='Cargo Desconhecido'))
    resultado = sincronizar_lista_cpfs(['12345678901'], dry_run=True)
    assert len(resultado) == 1
    assert 'sem mapeamento conhecido' in resultado[0]['erro']


def test_sincronizar_lista_cpfs_dry_run_mapeia_cargo_e_horario(monkeypatch):
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf',
                         lambda cpf: _registro_airtable(admissao='2020-01-01'))
    resultado = sincronizar_lista_cpfs(['12345678901'], dry_run=True)
    assert len(resultado) == 1
    r = resultado[0]
    assert r['status'] == 'dry_run'
    assert r['funcao_descricao'] == 'CONTROLADOR DE ACESSO'
    assert r['departamento_descricao'] == 'CONTROLADOR DE ACESSO'
    assert r['admissao'] == '2020-01-01'
    assert r['admissao_e_proxy'] is False


def test_sincronizar_lista_cpfs_sem_admissao_usa_created_time_como_proxy(monkeypatch):
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf',
                         lambda cpf: _registro_airtable(admissao=None, created_time='2026-01-15T10:00:00.000Z'))
    resultado = sincronizar_lista_cpfs(['12345678901'], dry_run=True)
    r = resultado[0]
    assert r['admissao'] == '2026-01-15'
    assert r['admissao_e_proxy'] is True


def test_sincronizar_lista_cpfs_cargo_normalizado_bate_com_mapa_apesar_de_acento_e_caixa(monkeypatch):
    # "Serviços Gerais" (Airtable, com acento/caixa mista) deve bater com a
    # chave normalizada 'SERVICOS GERAIS' do _MAPA_CARGO_SECULLUM.
    monkeypatch.setattr(sync_mod, 'buscar_funcionario_por_cpf',
                         lambda cpf: _registro_airtable(cargo='Serviços Gerais', admissao='2020-01-01'))
    resultado = sincronizar_lista_cpfs(['12345678901'], dry_run=True)
    assert resultado[0]['funcao_descricao'] == 'SERVIÇOS GERAIS'
