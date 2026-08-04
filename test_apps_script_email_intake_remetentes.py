"""
Guarda textual/estrutural para apps_script_email_intake.gs (fix/remetente-dp-email-intake).

Não há harness de execução real de Google Apps Script neste repositório
Python — este teste não executa o .gs, só verifica, por leitura de texto,
que a correção do remetente de DP e as garantias de segurança do
processamento administrativo por MESSAGE ID continuam presentes,
evitando regressão silenciosa.

Rodar: python test_apps_script_email_intake_remetentes.py
"""

import os

GS_PATH = os.path.join(os.path.dirname(__file__), 'apps_script_email_intake.gs')


def _ler_gs():
    with open(GS_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def _corpo_da_funcao(codigo, nome_funcao):
    """Extrai o corpo de uma função top-level pelo nome, via casamento de
    chaves balanceadas — mesma técnica usada no teste JS irmão."""
    marcador = 'function ' + nome_funcao + '('
    inicio = codigo.index(marcador)
    inicio_chave = codigo.index('{', inicio)
    profundidade = 0
    fim = None
    for i in range(inicio_chave, len(codigo)):
        if codigo[i] == '{':
            profundidade += 1
        elif codigo[i] == '}':
            profundidade -= 1
            if profundidade == 0:
                fim = i + 1
                break
    assert fim is not None, f'chaves desbalanceadas para {nome_funcao}'
    return codigo[inicio:fim]


def test_endereco_antigo_ausente():
    codigo = _ler_gs()
    assert 'dp.contabilidade1@hotmail.com' not in codigo, (
        'Endereço incorreto "dp.contabilidade1@hotmail.com" ainda presente no arquivo.'
    )
    print('OK: endereço antigo (dp.contabilidade1@hotmail.com) ausente')


def test_dp_correto_presente_em_remetentes_confiaveis():
    codigo = _ler_gs()
    bloco = _corpo_da_funcao if False else None  # REMETENTES_CONFIAVEIS não é função; ver abaixo
    inicio = codigo.index('var REMETENTES_CONFIAVEIS')
    fim = codigo.index('];', inicio)
    bloco = codigo[inicio:fim]
    assert 'dpessoal.contabilidade1@hotmail.com' in bloco, (
        'Endereço correto de DP ausente de REMETENTES_CONFIAVEIS.'
    )
    print('OK: dpessoal.contabilidade1@hotmail.com presente em REMETENTES_CONFIAVEIS')


def test_fiscal_preservado():
    codigo = _ler_gs()
    inicio = codigo.index('var REMETENTES_CONFIAVEIS')
    fim = codigo.index('];', inicio)
    bloco = codigo[inicio:fim]
    assert 'dpfiscal.contabilidade2@hotmail.com' in bloco, (
        'Endereço fiscal ausente de REMETENTES_CONFIAVEIS — não deveria ter sido tocado.'
    )
    print('OK: dpfiscal.contabilidade2@hotmail.com preservado em REMETENTES_CONFIAVEIS')


def test_funcoes_administrativas_nao_referenciadas_em_gatilho():
    codigo = _ler_gs()
    corpo_criar = _corpo_da_funcao(codigo, 'criarGatilhoHorario')
    for nome in ('executarProcessamentoAdministrativo', 'verificarMessageIdAdministrativo', 'processarMensagemPorId_'):
        assert nome not in corpo_criar, f'{nome} referenciada dentro de criarGatilhoHorario().'
    print('OK: nenhuma função administrativa referenciada em criarGatilhoHorario()')


def test_caminho_administrativo_sem_gmailapp_search():
    codigo = _ler_gs()
    for nome in ('processarMensagemPorId_', 'executarProcessamentoAdministrativo', 'verificarMessageIdAdministrativo'):
        corpo = _corpo_da_funcao(codigo, nome)
        assert 'GmailApp.search(' not in corpo, f'{nome} usa GmailApp.search — não deveria.'
    print('OK: caminho administrativo não usa GmailApp.search')


def test_processar_mensagem_por_id_sem_thread_getmessages():
    codigo = _ler_gs()
    corpo = _corpo_da_funcao(codigo, 'processarMensagemPorId_')
    assert 'thread.getMessages' not in corpo and '.getThread().getMessages' not in corpo, (
        'processarMensagemPorId_ não deveria enumerar mensagens da thread — só a função de diagnóstico pode.'
    )
    print('OK: processarMensagemPorId_ não chama getMessages() de thread')


def test_executor_administrativo_nunca_aplica_label():
    codigo = _ler_gs()
    for nome in ('executarProcessamentoAdministrativo', 'processarMensagemPorId_'):
        corpo = _corpo_da_funcao(codigo, nome)
        assert '.addLabel(' not in corpo, f'{nome} chama addLabel — caminho administrativo nunca deve rotular.'
    print('OK: caminho administrativo nunca chama addLabel')


def test_admin_apply_processed_label_ausente():
    codigo = _ler_gs()
    assert 'ADMIN_APPLY_PROCESSED_LABEL' not in codigo, (
        'ADMIN_APPLY_PROCESSED_LABEL não deveria existir nesta branch (decisão registrada no Ultraplan).'
    )
    print('OK: ADMIN_APPLY_PROCESSED_LABEL ausente do arquivo')


def test_defesa_explicita_dry_run_no_automatico():
    codigo = _ler_gs()
    corpo = _corpo_da_funcao(codigo, 'processarEmails')
    assert '!DRY_RUN && resultado.aplicarLabelPermitido' in corpo, (
        'Defesa explícita contra label em dry-run ausente de processarEmails().'
    )
    print('OK: defesa explícita "!DRY_RUN && resultado.aplicarLabelPermitido" presente em processarEmails()')


def test_lock_compartilhado_nas_duas_funcoes():
    codigo = _ler_gs()
    corpo_auto = _corpo_da_funcao(codigo, 'processarEmails')
    corpo_admin = _corpo_da_funcao(codigo, 'executarProcessamentoAdministrativo')
    assert 'LockService.getScriptLock()' in corpo_auto, 'processarEmails() não usa LockService.getScriptLock().'
    assert 'LockService.getScriptLock()' in corpo_admin, 'executarProcessamentoAdministrativo() não usa LockService.getScriptLock().'
    print('OK: processarEmails() e executarProcessamentoAdministrativo() usam o mesmo tipo de lock')


def test_executor_verifica_gatilho_ativo():
    codigo = _ler_gs()
    corpo = _corpo_da_funcao(codigo, 'executarProcessamentoAdministrativo')
    assert 'ScriptApp.getProjectTriggers()' in corpo, (
        'executarProcessamentoAdministrativo() não verifica gatilhos ativos.'
    )
    print('OK: executarProcessamentoAdministrativo() verifica gatilho ativo de processarEmails')


def test_verificador_nao_registrado_em_gatilho_e_sem_efeito_colateral():
    codigo = _ler_gs()
    corpo = _corpo_da_funcao(codigo, 'verificarMessageIdAdministrativo')
    assert 'addLabel' not in corpo
    assert 'UrlFetchApp.fetch' not in corpo
    assert 'setProperty' not in corpo
    assert 'ADMIN_EXECUTION_ENABLED' not in corpo
    print('OK: verificarMessageIdAdministrativo() é somente leitura (sem label, Render, escrita de property)')


if __name__ == '__main__':
    test_endereco_antigo_ausente()
    test_dp_correto_presente_em_remetentes_confiaveis()
    test_fiscal_preservado()
    test_funcoes_administrativas_nao_referenciadas_em_gatilho()
    test_caminho_administrativo_sem_gmailapp_search()
    test_processar_mensagem_por_id_sem_thread_getmessages()
    test_executor_administrativo_nunca_aplica_label()
    test_admin_apply_processed_label_ausente()
    test_defesa_explicita_dry_run_no_automatico()
    test_lock_compartilhado_nas_duas_funcoes()
    test_executor_verifica_gatilho_ativo()
    test_verificador_nao_registrado_em_gatilho_e_sem_efeito_colateral()
    print('\nTodos os testes passaram.')
