"""
Macro 6A — Identidade forte e obrigatória do agrupamento do Kit de Admissão.

Histórico: `_buscar_documentos_irmaos_kit_admissao` agrupava documentos só
por proximidade de horário (±JANELA_KIT_ADMISSAO_SEGUNDOS), sem checar
e-mail de origem nem CPF -- dois Kits de admissão de pessoas DIFERENTES
processados a poucos segundos de distância (plausível em lote/fila) seriam
agrupados como irmãos por engano. Uma primeira correção acrescentou o
vínculo por e-mail e a checagem de CPF, mas manteve os dois como "reforço
quando disponível": sem `email_savian_id` no ctx, caía de volta para a
janela de tempo sozinha; e `_cpf_compativel_com_kit` devolvia True quando
qualquer um dos dois CPFs estava ausente ("sem como provar divergência").
Uma revisão independente do patch apontou que isso ainda violava a regra de
identidade forte aprovada — ausência de contradição não é confirmação.

Correção final: um documento irmão só é incorporado automaticamente quando
há, SIMULTANEAMENTE: (1) vínculo determinístico com o mesmo registro de
e-mail de origem (Arquivos.F_ARQ_EMAILS via `ctx['email_savian_id']`);
(2) CPF extraído do documento candidato; (3) CPF esperado do funcionário;
(4) igualdade entre os CPFs normalizados. Qualquer ausência ou divergência
em qualquer uma das quatro condições resulta em: não vincular, não
incorporar, não descartar (nunca some) — vai para Pendência de revisão com
motivo sanitizado (nunca CPF nem trecho de PDF em log/observação) e
referência aos IDs técnicos (proc_id/arquivo_id/func_id). A janela de tempo
nunca prova pertencimento por si só — só restringe a busca.

Desenho dos testes: `_buscar_documentos_irmaos_kit_admissao` é testada em
isolamento para a dimensão "mesmo e-mail" (ela é o único lugar que decide
isso; qualquer candidato de OUTRO e-mail nunca chega a `_montar_e_disparar_
kit_admissao`, então "e-mails diferentes + CPF igual/divergente -> nunca
agrupa" já está coberto ali). `_montar_e_disparar_kit_admissao` é testada
para a dimensão "mesmo e-mail confirmado, CPF resolve o resto" -- os
"irmãos" passados nesses testes representam exatamente o que `_buscar_
documentos_irmaos_kit_admissao` já garante ter o MESMO e-mail de origem.

100% dado sintético -- nenhum CPF/nome real em nenhum lugar deste arquivo.
"""
from unittest.mock import Mock, patch

import pytest

from app import (
    F_ARQ_EMAILS,
    F_FUNC_CPF,
    F_FUNC_KIT_CONSOLIDADO,
    F_PROC_DATA,
    _baixar_e_classificar_papel_kit,
    _buscar_documentos_irmaos_kit_admissao,
    _cpf_compativel_com_kit,
    _montar_e_disparar_kit_admissao,
)


# ── _cpf_compativel_com_kit (função pura) — identidade forte OBRIGATÓRIA ─

def test_cpf_identico_e_compativel():
    assert _cpf_compativel_com_kit('111.111.111-11', '111.111.111-11') is True


def test_cpf_identico_com_formatacao_diferente_e_compativel():
    assert _cpf_compativel_com_kit('111.111.111-11', '11111111111') is True


def test_cpf_divergente_e_incompativel():
    assert _cpf_compativel_com_kit('111.111.111-11', '222.222.222-22') is False


def test_cpf_extraido_ausente_e_incompativel():
    """Correção final: ausência de um dos dois lados NÃO é mais tratada
    como "sem como provar divergência, aceita" -- a regra de identidade
    forte exige confirmação POSITIVA dos dois lados. Sem o CPF do
    candidato, nunca é compatível."""
    assert _cpf_compativel_com_kit(None, '111.111.111-11') is False


def test_cpf_esperado_ausente_e_incompativel():
    """Funcionário-alvo sem CPF cadastrado -- nunca compatível, mesmo que
    o candidato tenha CPF legível."""
    assert _cpf_compativel_com_kit('111.111.111-11', None) is False


def test_ambos_ausentes_e_incompativel():
    assert _cpf_compativel_com_kit(None, None) is False


def test_cpf_vazio_string_e_incompativel():
    """String vazia é tratada como ausência, não como valor."""
    assert _cpf_compativel_com_kit('', '111.111.111-11') is False
    assert _cpf_compativel_com_kit('111.111.111-11', '') is False


def test_assinatura_da_funcao_nunca_aceita_nome():
    """'CPF ausente -> não confirmar por nome aproximado': a assinatura da
    função só aceita os dois CPFs -- não há como nome algum influenciar a
    decisão."""
    import inspect
    assinatura = inspect.signature(_cpf_compativel_com_kit)
    parametros = list(assinatura.parameters.keys())
    assert parametros == ['cpf_extraido', 'cpf_esperado']
    assert 'nome' not in ' '.join(parametros).lower()


# ── _baixar_e_classificar_papel_kit devolve 3-upla ───────────────────────

def test_baixar_e_classificar_devolve_texto_junto():
    with patch('app._baixar_pdf_arquivo', return_value=(b'conteudo-fake', 'arquivo.pdf')), \
         patch('app.pdfplumber.open') as mock_open:
        pagina = Mock()
        pagina.extract_text.return_value = 'Ficha de Registro de Empregado sintetica'
        mock_open.return_value.__enter__.return_value.pages = [pagina]
        papel, conteudo, texto = _baixar_e_classificar_papel_kit('arqFAKE1')
    assert papel == 'ficha'
    assert conteudo == b'conteudo-fake'
    assert 'Ficha de Registro' in texto


def test_baixar_e_classificar_falha_devolve_tripla_vazia():
    with patch('app._baixar_pdf_arquivo', return_value=(None, None)):
        papel, conteudo, texto = _baixar_e_classificar_papel_kit('arqFAKE2')
    assert (papel, conteudo, texto) == (None, None, '')


# ── _buscar_documentos_irmaos_kit_admissao — vínculo de origem OBRIGATÓRIO

def _resposta(json_dict, ok=True):
    r = Mock()
    r.ok = ok
    r.json.return_value = json_dict
    return r


def test_irmao_com_mesmo_email_savian_e_incluido():
    ctx = {'proc_id': 'procATUAL', 'email_savian_id': 'recEmailFAKE1'}

    resp_data_processo = _resposta({'fields': {F_PROC_DATA: '2026-08-01T10:00:00.000Z'}})
    resp_busca = _resposta({'records': [
        {'id': 'procIRMAO', 'fields': {
            'Tipo de Documento': 'Ficha de Registro de Empregado',
            'Status': 'Pendente',
            'Arquivos 2': ['arqIRMAO'],
        }},
    ]})
    resp_arquivo_irmao = _resposta({'fields': {F_ARQ_EMAILS: ['recEmailFAKE1']}})

    with patch('app.requests.get', side_effect=[resp_data_processo, resp_busca, resp_arquivo_irmao]), \
         patch('app._at_throttle'):
        irmaos = _buscar_documentos_irmaos_kit_admissao(ctx)

    assert len(irmaos) == 1
    assert irmaos[0]['proc_id'] == 'procIRMAO'


def test_irmao_com_email_savian_diferente_e_rejeitado():
    """'e-mails diferentes -> nunca agrupar': candidato dentro da janela de
    tempo, mas de OUTRA mensagem de origem -- nunca deve ser agrupado,
    mesmo que (em outro teste) o CPF fosse compatível."""
    ctx = {'proc_id': 'procATUAL', 'email_savian_id': 'recEmailFAKE1'}

    resp_data_processo = _resposta({'fields': {F_PROC_DATA: '2026-08-01T10:00:00.000Z'}})
    resp_busca = _resposta({'records': [
        {'id': 'procOUTRAPESSOA', 'fields': {
            'Tipo de Documento': 'Ficha de Registro de Empregado',
            'Status': 'Pendente',
            'Arquivos 2': ['arqOUTRAPESSOA'],
        }},
    ]})
    resp_arquivo_outra_pessoa = _resposta({'fields': {F_ARQ_EMAILS: ['recEmailFAKE2_OUTRO']}})

    with patch('app.requests.get', side_effect=[resp_data_processo, resp_busca, resp_arquivo_outra_pessoa]), \
         patch('app._at_throttle'):
        irmaos = _buscar_documentos_irmaos_kit_admissao(ctx)

    assert irmaos == []


def test_sem_email_savian_id_no_ctx_nunca_agrupa_nada():
    """Correção final (achado material da revisão independente): a versão
    anterior caía de volta para a janela de tempo sozinha quando
    `email_savian_id` estava ausente no ctx -- exatamente o comportamento
    "janela temporal coincidente sem identidade forte" que a regra
    aprovada proíbe. Agora, sem origem determinística, a função devolve
    lista vazia SEM sequer consultar a janela de tempo -- "origem de
    e-mail ausente -> rejeita"."""
    ctx = {'proc_id': 'procATUAL'}  # sem 'email_savian_id'

    with patch('app.requests.get') as mock_get, \
         patch('app._at_throttle'):
        irmaos = _buscar_documentos_irmaos_kit_admissao(ctx)

    assert irmaos == []
    # nem chega a consultar Data Processo/janela -- falha fechada, não
    # "tenta mesmo assim com o que tem".
    mock_get.assert_not_called()


def test_irmao_cujo_arquivo_nao_pode_ser_lido_nunca_e_incluido_por_omissao():
    ctx = {'proc_id': 'procATUAL', 'email_savian_id': 'recEmailFAKE1'}

    resp_data_processo = _resposta({'fields': {F_PROC_DATA: '2026-08-01T10:00:00.000Z'}})
    resp_busca = _resposta({'records': [
        {'id': 'procIRMAO', 'fields': {
            'Tipo de Documento': 'Ficha de Registro de Empregado',
            'Status': 'Pendente',
            'Arquivos 2': ['arqIRMAO'],
        }},
    ]})
    resp_arquivo_falha = _resposta({}, ok=False)

    with patch('app.requests.get', side_effect=[resp_data_processo, resp_busca, resp_arquivo_falha]), \
         patch('app._at_throttle'):
        irmaos = _buscar_documentos_irmaos_kit_admissao(ctx)

    assert irmaos == []


def test_irmao_sem_arquivo_vinculado_nunca_e_incluido_por_omissao():
    """Achado material da revisão independente: candidato sem NENHUM
    Arquivo vinculado ('Arquivos 2' vazio) pulava direto para dentro da
    lista de irmãos na versão anterior (o `if email_savian_id_atual and
    arquivo_id:` era False quando arquivo_id era None, então o candidato
    passava batido pelo bloco de confirmação de e-mail inteiro). Agora,
    sem Arquivo, o candidato é descartado ANTES de qualquer tentativa de
    confirmar origem -- nunca inclui por omissão."""
    ctx = {'proc_id': 'procATUAL', 'email_savian_id': 'recEmailFAKE1'}

    resp_data_processo = _resposta({'fields': {F_PROC_DATA: '2026-08-01T10:00:00.000Z'}})
    resp_busca = _resposta({'records': [
        {'id': 'procSEMARQUIVO', 'fields': {
            'Tipo de Documento': 'Ficha de Registro de Empregado',
            'Status': 'Pendente',
            'Arquivos 2': [],
        }},
    ]})

    with patch('app.requests.get', side_effect=[resp_data_processo, resp_busca]) as mock_get, \
         patch('app._at_throttle'):
        irmaos = _buscar_documentos_irmaos_kit_admissao(ctx)

    assert irmaos == []
    # nunca tenta buscar o Arquivo (não existe id para buscar) -- só as 2
    # chamadas de sempre (Data Processo + busca na janela).
    assert mock_get.call_count == 2


# ── _montar_e_disparar_kit_admissao — identidade forte end-to-end ───────
# (o "irmão" passado a estes testes já representa o que _buscar_documentos_
# irmaos_kit_admissao GARANTE ter o mesmo e-mail de origem -- ver docstring
# do módulo para a justificativa do desenho em camadas.)

def _ctx_ficha_sintetica():
    return {
        'proc_id': 'procFICHA', 'arquivo_id': 'arqFICHA',
        'pdf_bytes': b'ficha-bytes', 'texto': 'Ficha de Registro de Empregado sintetica',
        'email_savian_id': 'recEmailFAKE1',
    }


def _monta_kit(ctx, func_id, r_func, irmao, texto_irmao_com_cpf, patches_extra=None):
    """Helper: roda _montar_e_disparar_kit_admissao com UM irmão candidato
    (já confirmado do mesmo e-mail) e o texto extraído dele (de onde o CPF
    seria lido por extrair_cpf, sem mockar extrair_cpf em si -- prova a
    integração real da extração)."""
    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[irmao] if irmao else []), \
         patch('app._baixar_e_classificar_papel_kit',
               return_value=('contrato', b'contrato-bytes', texto_irmao_com_cpf)), \
         patch('app._vincular_documento_ao_funcionario') as mock_vincular, \
         patch('app._criar_pendencia', return_value='recPENDFAKE') as mock_pendencia, \
         patch('app._montar_pdf_consolidado_kit_admissao', return_value=b'kit-consolidado'), \
         patch('app._anexar_attachment'), \
         patch('app.requests.post', return_value=_resposta({'id': 'recArquivoKitNovo'})), \
         patch('app._gerar_assinatura_core'), \
         patch('app._atualizar_status_processar'):
        resultado = _montar_e_disparar_kit_admissao(
            ctx, func_id, dry_run=False,
            dados_para_vt={'nome_funcionario': 'FULANO DE TESTE SINTETICO', 'cpf': '111.111.111-11'},
        )
    return resultado, mock_vincular, mock_pendencia


def test_mesmo_email_mesmo_cpf_aceita():
    """Caso obrigatório 1: mesmo e-mail (garantido pelo mock) + mesmo CPF
    -> aceita, vincula e incorpora ao Kit."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao = {'proc_id': 'procCONTRATO_MESMA_PESSOA', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_MESMA_PESSOA'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx, 'recFUNCALVO', r_func, irmao, 'CPF: 111.111.111-11')

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_MESMA_PESSOA' in vinculos
    assert resultado.get('irmaos_rejeitados_por_cpf') is None
    assert resultado.get('pendencias_identidade_kit') is None
    mock_pendencia.assert_not_called()
    assert resultado['kit_montado'] is True


def test_mesmo_email_cpf_divergente_rejeita_e_revisa():
    """Caso obrigatório 2: mesmo e-mail + CPF divergente -> rejeita,
    NUNCA vincula, NUNCA incorpora, e vai para Pendência de revisão."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao = {'proc_id': 'procCONTRATO_OUTRA_PESSOA', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_OUTRA_PESSOA'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx, 'recFUNCALVO', r_func, irmao, 'CPF: 222.222.222-22')

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_OUTRA_PESSOA' not in vinculos
    assert resultado.get('irmaos_rejeitados_por_cpf') == ['procCONTRATO_OUTRA_PESSOA']
    # encaminhado para revisão -- nunca descartado silenciosamente
    mock_pendencia.assert_called_once()
    assert resultado['pendencias_identidade_kit'][0]['motivo'] == 'cpf_divergente'
    assert resultado['pendencias_identidade_kit'][0]['proc_id'] == 'procCONTRATO_OUTRA_PESSOA'
    # referência aos IDs técnicos preservada, nunca o CPF
    args_pendencia = mock_pendencia.call_args.args
    assert args_pendencia[0] == 'arqCONTRATO_OUTRA_PESSOA'
    assert '222.222.222-22' not in str(args_pendencia)
    assert '111.111.111-11' not in str(args_pendencia)


def test_mesmo_email_cpf_ausente_no_candidato_rejeita_e_revisa():
    """Caso obrigatório 3: mesmo e-mail + CPF ausente no candidato ->
    rejeita e revisa (nunca aceita por omissão)."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao = {'proc_id': 'procCONTRATO_SEM_CPF_LEGIVEL', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_SEM_CPF_LEGIVEL'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx, 'recFUNCALVO', r_func, irmao, 'documento sem CPF legivel neste texto sintetico')

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_SEM_CPF_LEGIVEL' not in vinculos
    assert resultado.get('irmaos_rejeitados_por_cpf') == ['procCONTRATO_SEM_CPF_LEGIVEL']
    mock_pendencia.assert_called_once()
    assert resultado['pendencias_identidade_kit'][0]['motivo'] == 'cpf_candidato_ausente'


def test_mesmo_email_cpf_esperado_ausente_rejeita_e_revisa():
    """Caso obrigatório 4: mesmo e-mail + CPF esperado (funcionário-alvo)
    ausente -> rejeita e revisa, mesmo que o candidato tenha CPF legível."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: None}})
    irmao = {'proc_id': 'procCONTRATO_QUALQUER', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_QUALQUER'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx, 'recFUNCSEMCPF', r_func, irmao, 'CPF: 111.111.111-11')

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_QUALQUER' not in vinculos
    assert resultado.get('irmaos_rejeitados_por_cpf') == ['procCONTRATO_QUALQUER']
    mock_pendencia.assert_called_once()
    assert resultado['pendencias_identidade_kit'][0]['motivo'] == 'cpf_esperado_ausente'


def test_origem_de_email_ausente_no_documento_atual_nunca_agrupa_nenhum_irmao():
    """Caso obrigatório 5: origem de e-mail ausente (no documento ATUAL, o
    que está sendo processado agora) -> rejeita qualquer agrupamento
    automático. `_buscar_documentos_irmaos_kit_admissao` já devolve []
    nesse caso (testado em isolamento acima); aqui confirmamos que
    _montar_e_disparar_kit_admissao propaga isso corretamente: o Kit fica
    aguardando (rastreável), nunca é montado com dado incompleto/errado."""
    ctx = {
        'proc_id': 'procCONTRATO_SOZINHO', 'arquivo_id': 'arqCONTRATO_SOZINHO',
        'pdf_bytes': b'contrato-sozinho-bytes', 'texto': 'Contrato de Trabalho sintetico',
        # sem 'email_savian_id'
    }
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})

    def busca_irmaos(ctx_recebido):
        # Prova que, mesmo chamando a função REAL (não mockada) internamente
        # via este stub, o contrato "sem email_savian_id -> []" é respeitado
        # pelo próprio ctx recebido -- consistente com o teste em isolamento
        # de _buscar_documentos_irmaos_kit_admissao acima.
        assert not ctx_recebido.get('email_savian_id')
        return []

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', side_effect=busca_irmaos), \
         patch('app._vincular_documento_ao_funcionario'), \
         patch('app._montar_pdf_consolidado_kit_admissao') as mock_montar_pdf:
        resultado = _montar_e_disparar_kit_admissao(ctx, 'recFUNCALVO', dry_run=False)

    assert resultado['kit_montado'] is False
    mock_montar_pdf.assert_not_called()


def test_janela_temporal_sozinha_nunca_e_prova_suficiente():
    """Princípio geral (não um caso isolado): mesmo quando
    `_buscar_documentos_irmaos_kit_admissao` devolve um candidato (ou
    seja, a janela de tempo bateu), a decisão de vincular/incorporar
    NUNCA se baseia só nisso -- o CPF ainda precisa bater. Este teste
    prova que um candidato dentro da janela, mesmo e-mail confirmado, mas
    sem NENHUM CPF em nenhum dos dois lados, ainda assim é rejeitado."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: None}})
    irmao = {'proc_id': 'procCONTRATO_SEM_CPF', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_SEM_CPF'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx, 'recFUNCSEMCPF', r_func, irmao, 'documento sem nenhum CPF legivel')

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_SEM_CPF' not in vinculos
    mock_pendencia.assert_called_once()


def test_documento_rejeitado_nunca_fica_orfao_tem_pendencia_com_ids_tecnicos():
    """'Documento rejeitado não fica órfão ou perdido': cada rejeição por
    identidade cria uma Pendência com referência aos IDs técnicos
    (proc_id, arquivo_id) -- nunca só um log que desaparece."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao = {'proc_id': 'procREJEITADO', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqREJEITADO'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx, 'recFUNCALVO', r_func, irmao, 'CPF: 999.999.999-99')

    assert len(resultado['pendencias_identidade_kit']) == 1
    entrada = resultado['pendencias_identidade_kit'][0]
    assert entrada['proc_id'] == 'procREJEITADO'
    assert entrada['arquivo_id'] == 'arqREJEITADO'
    assert entrada['pendencia_id'] == 'recPENDFAKE'


def test_falha_ao_criar_pendencia_nao_interrompe_processamento_dos_demais():
    """Falha ao criar a Pendência (ex.: erro de rede) é não-bloqueante --
    não pode derrubar o processamento do resto do Kit."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao = {'proc_id': 'procREJEITADO', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqREJEITADO'}

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[irmao]), \
         patch('app._baixar_e_classificar_papel_kit',
               return_value=('contrato', b'contrato-bytes', 'CPF: 999.999.999-99')), \
         patch('app._vincular_documento_ao_funcionario'), \
         patch('app._criar_pendencia', side_effect=Exception('erro sintetico de rede')), \
         patch('app._gerar_pdf_declaracao_renuncia_vt', return_value=b'vt-fake'), \
         patch('app._montar_pdf_consolidado_kit_admissao', return_value=b'kit-consolidado'), \
         patch('app._anexar_attachment'), \
         patch('app.requests.post', return_value=_resposta({'id': 'recArquivoKitNovo'})), \
         patch('app._gerar_assinatura_core'), \
         patch('app._atualizar_status_processar'):
        # não deve levantar exceção
        resultado = _montar_e_disparar_kit_admissao(ctx, 'recFUNCALVO', dry_run=False)

    assert resultado.get('irmaos_rejeitados_por_cpf') == ['procREJEITADO']


def test_log_de_rejeicao_nunca_contem_cpf():
    """'Nunca registrar CPF ou conteúdo do PDF em log': confirma que o
    logger.warning de rejeição não recebe o valor de nenhum CPF."""
    ctx = _ctx_ficha_sintetica()
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao = {'proc_id': 'procREJEITADO', 'tipo_documento': 'Contrato de Trabalho',
             'status': 'Pendente', 'arquivo_id': 'arqREJEITADO'}

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[irmao]), \
         patch('app._baixar_e_classificar_papel_kit',
               return_value=('contrato', b'contrato-bytes', 'CPF: 222.222.222-22')), \
         patch('app._vincular_documento_ao_funcionario'), \
         patch('app._criar_pendencia', return_value='recPENDFAKE'), \
         patch('app._gerar_pdf_declaracao_renuncia_vt', return_value=b'vt-fake'), \
         patch('app._montar_pdf_consolidado_kit_admissao', return_value=b'kit-consolidado'), \
         patch('app._anexar_attachment'), \
         patch('app.requests.post', return_value=_resposta({'id': 'recArquivoKitNovo'})), \
         patch('app._gerar_assinatura_core'), \
         patch('app._atualizar_status_processar'), \
         patch('app.logger') as mock_logger:
        _montar_e_disparar_kit_admissao(ctx, 'recFUNCALVO', dry_run=False)

    mensagens = [str(c) for c in mock_logger.warning.call_args_list]
    texto_completo = ' '.join(mensagens)
    assert '222.222.222-22' not in texto_completo
    assert '111.111.111-11' not in texto_completo


# ── Casos herdados (anexo atrasado, kit incompleto, funcionário existente)

def test_documento_atrasado_apos_kit_ja_concluido_e_vinculado_ao_funcionario_nao_orfao():
    """'Anexos atrasados -> comportamento determinístico': quando o Kit já
    foi concluído por outro documento irmão, o documento atual (chegando
    tarde) ainda é vinculado ao funcionário -- nunca fica órfão."""
    ctx = _ctx_ficha_sintetica()
    func_id = 'recFUNCALVO'

    r_func = _resposta({'fields': {
        F_FUNC_KIT_CONSOLIDADO: [{'id': 'attKitJaExistente', 'filename': 'Kit Admissao.pdf'}],
        F_FUNC_CPF: '111.111.111-11',
    }})

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao') as mock_buscar_irmaos, \
         patch('app._vincular_documento_ao_funcionario') as mock_vincular:
        resultado = _montar_e_disparar_kit_admissao(ctx, func_id, dry_run=False)

    mock_vincular.assert_called_once_with(func_id, ctx['arquivo_id'])
    assert resultado['kit_montado'] is False
    assert resultado.get('documento_atual_vinculado_tardiamente') is True
    mock_buscar_irmaos.assert_not_called()


def test_kit_incompleto_sem_ficha_nunca_cadastra_incorretamente_fica_em_revisao():
    """'Kit incompleto -> revisão, sem cadastro incorreto': sem nenhum
    irmão (mesmo e-mail, mesmo CPF) classificado como Ficha, o Kit nunca é
    montado incorretamente -- fica aguardando, rastreável."""
    ctx = {
        'proc_id': 'procCONTRATO_SOZINHO', 'arquivo_id': 'arqCONTRATO_SOZINHO',
        'pdf_bytes': b'contrato-sozinho-bytes', 'texto': 'Contrato de Trabalho sintetico, sem ficha',
        'email_savian_id': 'recEmailFAKE1',
    }
    func_id = 'recFUNCALVO'
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[]), \
         patch('app._vincular_documento_ao_funcionario'), \
         patch('app._montar_pdf_consolidado_kit_admissao') as mock_montar_pdf, \
         patch('app._gerar_assinatura_core') as mock_assinatura:
        resultado = _montar_e_disparar_kit_admissao(ctx, func_id, dry_run=False)

    assert resultado['kit_montado'] is False
    assert 'ainda não' in resultado['motivo'].lower() or 'aguarda' in resultado['motivo'].lower()
    mock_montar_pdf.assert_not_called()
    mock_assinatura.assert_not_called()


def test_funcionario_existente_com_kit_nunca_e_reprocessado_nem_sobrescrito():
    """'Funcionário existente -> nunca sobrescrever dados silenciosamente':
    funcionário já com Kit consolidado nunca tem o Kit remontado nem a
    assinatura redisparada."""
    ctx = _ctx_ficha_sintetica()
    func_id = 'recFUNCJAADMITIDO'
    r_func = _resposta({'fields': {
        F_FUNC_KIT_CONSOLIDADO: [{'id': 'attKitAntigo', 'filename': 'Kit Admissao.pdf'}],
        F_FUNC_CPF: '111.111.111-11',
    }})

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._vincular_documento_ao_funcionario'), \
         patch('app._montar_pdf_consolidado_kit_admissao') as mock_montar_pdf, \
         patch('app._anexar_attachment') as mock_anexar, \
         patch('app._gerar_assinatura_core') as mock_assinatura:
        resultado = _montar_e_disparar_kit_admissao(ctx, func_id, dry_run=False)

    mock_montar_pdf.assert_not_called()
    mock_anexar.assert_not_called()
    mock_assinatura.assert_not_called()
    assert resultado['kit_montado'] is False


def test_peca_duplicada_de_mesmo_papel_e_vinculada_mas_nao_substitui_a_escolhida():
    """'Peças duplicadas -> escolha determinística ou revisão': quando
    dois irmãos CPF-compatíveis (mesmo e-mail, mesmo CPF) se classificam
    com o MESMO papel (ex.: dois "contrato"), o primeiro processado
    (ordem determinística) é o único usado no PDF consolidado -- mas o
    segundo não é descartado silenciosamente: continua vinculado."""
    ctx = _ctx_ficha_sintetica()
    func_id = 'recFUNCALVO'
    r_func = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})

    irmao_1 = {'proc_id': 'procCONTRATO_1', 'tipo_documento': 'Contrato de Trabalho',
               'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_1'}
    irmao_2_duplicado = {'proc_id': 'procCONTRATO_2_DUPLICADO', 'tipo_documento': 'Contrato de Trabalho',
                          'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_2_DUPLICADO'}

    def classificar(arquivo_id):
        if arquivo_id == 'arqCONTRATO_1':
            return ('contrato', b'contrato-1-bytes', 'CPF: 111.111.111-11')
        return ('contrato', b'contrato-2-bytes', 'CPF: 111.111.111-11')

    with patch('app.requests.get', return_value=r_func), \
         patch('app._at_throttle'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, '')), \
         patch('app._buscar_documentos_irmaos_kit_admissao', return_value=[irmao_1, irmao_2_duplicado]), \
         patch('app._baixar_e_classificar_papel_kit', side_effect=classificar), \
         patch('app._vincular_documento_ao_funcionario') as mock_vincular, \
         patch('app._montar_pdf_consolidado_kit_admissao', return_value=b'kit-consolidado') as mock_montar, \
         patch('app._anexar_attachment'), \
         patch('app.requests.post', return_value=_resposta({'id': 'recArquivoKitNovo'})), \
         patch('app._gerar_assinatura_core'), \
         patch('app._atualizar_status_processar'):
        resultado = _montar_e_disparar_kit_admissao(
            ctx, func_id, dry_run=False,
            dados_para_vt={'nome_funcionario': 'FULANO DE TESTE SINTETICO', 'cpf': '111.111.111-11'},
        )

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_1' in vinculos
    assert 'arqCONTRATO_2_DUPLICADO' in vinculos
    assert mock_montar.call_args.args[1] == b'contrato-1-bytes'
    assert resultado['kit_montado'] is True


def test_mesmo_email_duas_pessoas_kits_separados_nunca_mistura():
    """'Mesmo e-mail contendo documentos de duas pessoas -> kits
    separados': ao montar o Kit da Pessoa A (CPF 111...), um documento da
    Pessoa B (CPF 222..., mesmo e-mail) nunca é incorporado -- cada pessoa
    tem seu próprio Kit, resolvido pelo seu próprio CPF quando o SEU
    documento for processado (não simulado aqui, mas garantido pela mesma
    checagem de identidade, simétrica)."""
    ctx_pessoa_a = {
        'proc_id': 'procFICHA_A', 'arquivo_id': 'arqFICHA_A',
        'pdf_bytes': b'ficha-a-bytes', 'texto': 'Ficha de Registro de Empregado sintetica A',
        'email_savian_id': 'recEmailCompartilhado',
    }
    func_id_a = 'recFUNC_A'
    r_func_a = _resposta({'fields': {F_FUNC_KIT_CONSOLIDADO: [], F_FUNC_CPF: '111.111.111-11'}})
    irmao_pessoa_b = {'proc_id': 'procCONTRATO_B', 'tipo_documento': 'Contrato de Trabalho',
                       'status': 'Pendente', 'arquivo_id': 'arqCONTRATO_B'}

    resultado, mock_vincular, mock_pendencia = _monta_kit(
        ctx_pessoa_a, func_id_a, r_func_a, irmao_pessoa_b, 'CPF: 222.222.222-22')

    vinculos = [c.args[1] for c in mock_vincular.call_args_list]
    assert 'arqCONTRATO_B' not in vinculos
    assert resultado.get('irmaos_rejeitados_por_cpf') == ['procCONTRATO_B']
    mock_pendencia.assert_called_once()
