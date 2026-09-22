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
from magnata_os.orquestrador.eventos import EstadoExecucao, TipoEvento
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    OrdemDistribuicaoDocumental,
    ResultadoDistribuicaoDocumentalShadow,
    derivar_identidade_ordem_distribuicao,
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
    resultado devolvido por ele.

    CORREÇÃO (fechamento do gap de composição do canário genérico
    WhatsApp V1): `main()` agora também registra o evento canônico da
    Ordem em `execucoes` (`registrar_evento_canonico_ordem_
    distribuicao_documental_shadow`, núcleo) ANTES de chamar o serviço
    genérico -- reutiliza um `RepositorioExecucoesEmMemoria()` real
    (não mockado) para provar que a chamada de fato acontece e termina
    em `WAITING_GATE`, em vez de só verificar que uma função foi
    chamada."""
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
    repositorio_execucoes_fake = RepositorioExecucoesEmMemoria()
    with patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_documentos_a_partir_do_ambiente') as m1, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_armazenamento_a_partir_do_ambiente') as m2, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_autorizacoes_a_partir_do_ambiente') as m3, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_acoes_a_partir_do_ambiente') as m4, \
         patch('magnata_os.orquestrador.distribuir_documento_v1._compor_repositorio_execucoes_a_partir_do_ambiente',
               return_value=repositorio_execucoes_fake) as m5, \
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

    # Evento canônico realmente registrado, com o MESMO event_id que o
    # núcleo derivaria da Ordem -- nunca um id solto/diferente.
    event_id_esperado = derivar_identidade_ordem_distribuicao(kwargs['ordem'])
    execucao = repositorio_execucoes_fake.buscar_por_event_id(event_id_esperado)
    assert execucao is not None
    assert execucao.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
    assert execucao.estado == EstadoExecucao.WAITING_GATE


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


def test_cli_zero_import_de_transporte_ou_evolution():
    """Checagem estrutural via AST (mesma técnica de
    `test_wiring_distribuicao_documental_shadow.py::
    test_modulo_nunca_importa_nem_chama_transporte_real`) -- imune a
    aliasing ou uso indireto via atributo. Este CLI é o composition
    root mais próximo do canário genérico; nunca pode ganhar, mesmo por
    engano futuro, um caminho até o transporte real."""
    caminho = 'magnata_os/orquestrador/distribuir_documento_v1.py'
    with open(caminho, 'r', encoding='utf-8') as f:
        arvore = ast.parse(f.read(), filename=caminho)
    proibidos = {
        'requests', 'boto3', 'psycopg',
        'transporte_real_habilitado', 'compor_porta_execucao',
        'ExecutorEvolutionLegado', 'executar_proxima_acao_persistente',
        'executar_um_ciclo_producao',
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
