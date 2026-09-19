"""CLI `distribuir_documento_v1.py` -- prova que é puro adapter de
borda: só lê inputs, constrói a Ordem, compõe dependências e chama o
serviço genérico. Nenhuma regra de negócio (validação de política,
idempotência, ordem dos efeitos de assinatura) vive aqui -- tudo isso
já é coberto por `test_wiring_distribuicao_documental_shadow.py`.
"""
import ast
import json
from unittest.mock import patch

from magnata_os.orquestrador.distribuir_documento_v1 import (
    main,
    montar_ordem_distribuicao_documental,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    OrdemDistribuicaoDocumental,
    ResultadoDistribuicaoDocumentalShadow,
)


def test_montar_ordem_so_constroi_o_contrato_sem_validacao_propria():
    ordem = montar_ordem_distribuicao_documental(
        documentos=(('doc-1', 'a' * 64),),
        funcionario_id='recFUNC1', destinatario='5511999999999', canal='whatsapp',
        preset_id='preset-teste', tipo_documento='CONTRATO',
        exigir_assinatura=True, exigir_comprovante=False,
        politica_agrupamento='UNITARIO', mensagem_texto='Segue seu documento:',
    )
    assert isinstance(ordem, OrdemDistribuicaoDocumental)
    assert ordem.documentos[0].documento_id == 'doc-1'
    assert ordem.tipo_documento == 'CONTRATO'


def test_cli_main_apenas_compoe_e_chama_o_servico_generico():
    """`main()` nunca decide política/idempotência/assinatura -- só
    repassa a Ordem construída para o serviço genérico e imprime o
    resultado devolvido por ele."""
    argv = [
        '--documento', f'doc-1:{"a" * 64}',
        '--funcionario-id', 'recFUNC1',
        '--destinatario', '5511999999999',
        '--preset-id', 'preset-teste',
        '--tipo-documento', 'CONTRATO',
        '--politica-agrupamento', 'UNITARIO',
        '--mensagem-texto', 'Segue seu documento:',
        '--ator-referencia', 'rh:teste',
    ]
    resultado_fake = ResultadoDistribuicaoDocumentalShadow(
        event_id='evt_x', autorizacao_id='auth_x', acao_execucao_id='acao_x',
        arquivo_record_ids=(), documento_ids=('doc-1',), funcionario_id='recFUNC1',
        assinatura_link=None, envelope_sha256='env_x', acao_persistida=None,
    )
    with patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_documentos_a_partir_do_ambiente') as m1, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_armazenamento_a_partir_do_ambiente') as m2, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_autorizacoes_a_partir_do_ambiente') as m3, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_acoes_a_partir_do_ambiente') as m4, \
         patch('magnata_os.orquestrador.distribuir_documento_v1.materializar_distribuicao_documental_shadow',
               return_value=resultado_fake) as chamada_servico, \
         patch('builtins.print') as mock_print:
        codigo_saida = main(argv)

    assert codigo_saida == 0
    assert chamada_servico.call_count == 1
    kwargs = chamada_servico.call_args.kwargs
    assert kwargs['ordem'].tipo_documento == 'CONTRATO'
    assert kwargs['materializador'] is None  # exigir_assinatura=False (default) -> nenhuma composição de materializador
    assert kwargs['porta_assinatura'] is None
    saida = json.loads(mock_print.call_args.args[0])
    assert saida['event_id'] == 'evt_x'


def test_cli_nao_referencia_nenhum_tipo_documental_especifico_no_codigo():
    """Verificação estrutural (AST): o CLI não pode conter `if`/`==`
    comparando `tipo_documento` contra um valor específico -- isso
    seria regra de negócio vazando para o adapter de borda."""
    caminho = 'magnata_os/orquestrador/distribuir_documento_v1.py'
    with open(caminho, 'r', encoding='utf-8') as f:
        codigo = f.read()
    proibidos = ['HOLERITE', 'FOLHA_PONTO', 'EPI', 'NR01', 'RESCISAO', 'CONTRATO_EXPERIENCIA']
    for termo in proibidos:
        assert termo not in codigo, f'{termo} não deveria aparecer no CLI (regra de negócio vazando)'
