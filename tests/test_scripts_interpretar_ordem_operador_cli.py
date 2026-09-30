"""Testes de `scripts/interpretar_ordem_operador_cli.py` -- leitura de
arquivos locais só (diagnostico.json + ordem em texto + diretório de
nomes opcional), nenhuma chamada de rede real, mesma disciplina de
`tests/test_scripts_prestacao_diagnostico_real_cli.py`."""
import json

from scripts.interpretar_ordem_operador_cli import _parse_args, executar, main


def _escrever_json(tmp_path, nome, conteudo):
    caminho = tmp_path / nome
    caminho.write_text(json.dumps(conteudo), encoding='utf-8')
    return str(caminho)


def _diagnostico_1_colaborador():
    return {
        'competencia_base': '2026-09',
        'clientes': [{
            'cliente': 'cliente-1', 'competencia': '2026-09',
            'estado_pacote': 'PRONTO', 'ordem_pronta': True,
            'necessidades': [{
                'cliente': 'cliente-1', 'competencia': '2026-09',
                'tipo_documental': 'HOLERITE', 'colaborador': 'colab-1',
                'situacao': 'PRONTO', 'documentos_avaliados': ['doc-1'],
                'documentos_elegiveis': ['doc-1'], 'localizacao': None,
            }],
        }],
    }


def test_executar_produz_selecao_interpretada_pronta(tmp_path):
    diagnostico_path = _escrever_json(tmp_path, 'diagnostico.json', _diagnostico_1_colaborador())
    diretorio_path = _escrever_json(tmp_path, 'diretorio.json', {'colab-1': 'Fulano da Silva'})

    saida = executar(
        diagnostico_path, 'manda pro Fulano da Silva o holerite de setembro, com assinatura digital e comprovante',
        diretorio_path,
    )

    assert saida['status'] == 'SELECAO_INTERPRETADA_PRONTA_PARA_VALIDACAO'
    assert saida['itens'] == [{
        'cliente_id': 'cliente-1', 'competencia_id': '2026-09', 'colaborador_id': 'colab-1',
        'tipos_documentais': ['HOLERITE'], 'exigir_assinatura_digital_e_comprovante': True,
    }]


def test_executar_produz_pendencia_de_esclarecimento_sem_criar_selecao(tmp_path):
    diagnostico_path = _escrever_json(tmp_path, 'diagnostico.json', _diagnostico_1_colaborador())

    saida = executar(diagnostico_path, 'manda pro Ciclano o holerite de setembro')

    assert saida['status'] == 'PENDENCIA_DE_ESCLARECIMENTO'
    assert saida['duvidas'][0]['codigo'] == 'DESTINATARIO_NAO_ENCONTRADO'
    assert 'itens' not in saida


def test_executar_sem_diretorio_nomes_usa_colaborador_id(tmp_path):
    diagnostico_path = _escrever_json(tmp_path, 'diagnostico.json', _diagnostico_1_colaborador())

    saida = executar(diagnostico_path, 'manda pro colab-1 o holerite de setembro')

    assert saida['status'] == 'SELECAO_INTERPRETADA_PRONTA_PARA_VALIDACAO'
    assert saida['itens'][0]['colaborador_id'] == 'colab-1'


def test_parse_args_exige_diagnostico_e_ordem():
    args = _parse_args(['--diagnostico', 'd.json', '--ordem', 'texto qualquer'])
    assert args.diagnostico == 'd.json'
    assert args.ordem == 'texto qualquer'
    assert args.diretorio_nomes is None


def test_main_imprime_json_e_devolve_0(tmp_path, capsys):
    diagnostico_path = _escrever_json(tmp_path, 'diagnostico.json', _diagnostico_1_colaborador())
    diretorio_path = _escrever_json(tmp_path, 'diretorio.json', {'colab-1': 'Fulano da Silva'})

    codigo = main([
        '--diagnostico', diagnostico_path,
        '--ordem', 'manda pro Fulano da Silva o holerite de setembro',
        '--diretorio-nomes', diretorio_path,
    ])

    assert codigo == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida['status'] == 'SELECAO_INTERPRETADA_PRONTA_PARA_VALIDACAO'


def test_main_arquivo_de_diagnostico_inexistente_retorna_2(capsys):
    codigo = main(['--diagnostico', '/tmp/nao-existe-magnata.json', '--ordem', 'manda pro Fulano o holerite'])
    assert codigo == 2
    assert 'ARQUIVO_NAO_ENCONTRADO' in capsys.readouterr().out
