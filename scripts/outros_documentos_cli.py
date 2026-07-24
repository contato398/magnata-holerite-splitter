"""
Comando manual interno para aplicar recibos de "Outros documentos" aos
Envios de Documentos correspondentes (Fix v3.01 -- ver app.py,
_outros_documentos_por_envio / _dry_run_outros_documentos_para_envios /
_aplicar_outros_documentos_no_envio).

Execucao manual apenas -- sem rota HTTP, sem job, sem cron. Roda no mesmo
ambiente que ja tem AIRTABLE_API_KEY configurada (ex.: shell do Render),
sem abrir nenhuma porta nem expor nenhum endpoint novo.

Uso:
    python -m scripts.outros_documentos_cli dry-run --competencia "Junho 2026"
    python -m scripts.outros_documentos_cli aplicar  --competencia "Junho 2026" --envio-id recXXXXXXXXXXXXXX

Regras:
  - "aplicar" sempre refaz o dry-run internamente antes de agir -- nunca
    confia num relatorio de execucao anterior.
  - Se houver conflito (nome igual, tamanho diferente) para o envio_id
    pedido, a aplicacao e interrompida sem nenhuma escrita -- sem opcao
    de forcar/ignorar.
  - Escreve no maximo em UM envio_id por execucao (sem modo lote).
  - Exige confirmacao textual exata "CONFIRMAR" antes de qualquer PATCH;
    qualquer outra entrada cancela sem escrever nada.
  - Antes de confirmar, valida por leitura (Meta API) que o campo
    'Arquivos' de Envios de Documentos corresponde ao Field ID esperado
    (F_ENVIO_ARQUIVOS) -- esse campo tambem e usado hoje por Cartao Ponto,
    entao a equivalencia nome<->Field ID nunca e assumida silenciosamente.

Rollback: nao ha desfazer automatico. Antes de cada PATCH este comando
registra em log os attachment IDs que ja estavam no campo 'Arquivos' do
Envio (evento 'pre_patch'). Se for necessario reverter, um humano com
acesso ao Airtable deve restaurar manualmente esse campo para a lista de
IDs registrada nesse log, usando o correlation_id da execucao para
localizar a linha certa.
"""

import argparse
import json
import logging
import secrets
import sys

import requests

from app import (
    AIRTABLE_API_KEY,
    BASE_ID,
    TABLE_ENVIOS,
    F_ENVIO_ARQUIVOS,
    _at_throttle,
    _at_headers,
    _dry_run_outros_documentos_para_envios,
    _aplicar_outros_documentos_no_envio,
)

logger = logging.getLogger('outros_documentos_cli')

CAMPO_ARQUIVOS_NOME = 'Arquivos'


class ConfiguracaoAusente(Exception):
    """AIRTABLE_API_KEY ou BASE_ID nao configurados no ambiente."""


def _validar_configuracao():
    faltando = []
    if not AIRTABLE_API_KEY:
        faltando.append('AIRTABLE_API_KEY')
    if not BASE_ID:
        faltando.append('BASE_ID')
    if faltando:
        raise ConfiguracaoAusente(
            'Configuracao ausente: ' + ', '.join(faltando) + '. '
            'Defina as variaveis de ambiente antes de rodar este comando '
            '(nao le .env.txt nem nenhum arquivo local -- so os.environ).'
        )


def _novo_correlation_id():
    return f"odc{secrets.token_hex(8)}"


def _log(evento, correlation_id, **campos):
    payload = {'evento': evento, 'correlation_id': correlation_id}
    payload.update(campos)
    logger.info('outros_documentos_cli %s', json.dumps(payload, ensure_ascii=False, default=str))


def confirmar_campo_arquivos():
    """
    Confirma, por leitura (Airtable Meta API -- GET, nunca escreve), que o
    campo 'Arquivos' de Envios de Documentos corresponde ao Field ID
    F_ENVIO_ARQUIVOS. Esse campo tambem e usado hoje por Cartao Ponto
    (ver comentario de F_ENVIO_ARQUIVOS em app.py); esta funcao existe
    para nunca assumir essa equivalencia em silencio.

    Se a confirmacao nao for possivel por qualquer motivo (rede, schema
    mudou, campo nao encontrado, resposta inesperada), retorna False --
    quem chama deve interromper com CAMPO_ARQUIVOS_NAO_CONFIRMADO.
    """
    try:
        r = requests.get(
            f'https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            timeout=15,
        )
        if not r.ok:
            return False
        tabelas = r.json().get('tables', [])
        tabela_envios = next((t for t in tabelas if t.get('id') == TABLE_ENVIOS), None)
        if not tabela_envios:
            return False
        campo = next(
            (f for f in tabela_envios.get('fields', []) if f.get('name') == CAMPO_ARQUIVOS_NOME),
            None,
        )
        if not campo:
            return False
        return campo.get('id') == F_ENVIO_ARQUIVOS
    except Exception:
        return False


def _ler_attachments_atuais(envio_id):
    """Leitura pre-PATCH dos attachment IDs atuais do Envio, para permitir
    rollback manual. So leitura -- nunca escreve."""
    _at_throttle()
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ENVIOS}/{envio_id}',
        headers=_at_headers(),
        timeout=30,
    )
    r.raise_for_status()
    arquivos = r.json().get('fields', {}).get(CAMPO_ARQUIVOS_NOME) or []
    return [a.get('id') for a in arquivos]


def cmd_dry_run(competencia, correlation_id):
    """Somente leitura. Nunca chama _aplicar_outros_documentos_no_envio."""
    _log('inicio', correlation_id, modo='dry-run', competencia=competencia)

    resultado = _dry_run_outros_documentos_para_envios(competencia)
    afetados = [e for e in resultado['envios'] if e['qtd_a_adicionar'] > 0]

    print(f"\n=== DRY-RUN | competencia={competencia!r} | correlation_id={correlation_id} ===\n")
    if not afetados:
        print('Nenhum envio com anexos novos para esta competencia.')
    for e in afetados:
        print(f"envio_id={e['envio_id']} | envio_nome={e['envio_nome']}")
        print(f"  anexos atuais: {e['qtd_ja_existentes_no_envio']}")
        print(f"  anexos novos a adicionar: {e['qtd_a_adicionar']} -> {e['filenames_a_adicionar']}")
        print(f"  duplicados evitados: {e['duplicados_evitados']}")
        if e['conflitos']:
            print(f"  CONFLITOS (nao aplicaveis automaticamente): {e['conflitos']}")
        print()

    if resultado['rejeitados']:
        print(f"Rejeitados (sem PDF ou sem Envio vinculado): {len(resultado['rejeitados'])}")
        for rej in resultado['rejeitados']:
            print(f"  - {rej['record_id']} | {rej['documento']} | motivo={rej['motivo']}")

    _log(
        'fim', correlation_id, modo='dry-run', competencia=competencia,
        envios_afetados=[e['envio_id'] for e in afetados],
        total_rejeitados=len(resultado['rejeitados']),
    )
    return resultado


def cmd_aplicar(competencia, envio_id, correlation_id, confirmar_input=input):
    """
    Escreve em UM envio_id, se e somente se:
      - o campo 'Arquivos' foi confirmado (Meta API);
      - o dry-run refeito na hora encontra o envio_id com algo a adicionar;
      - nao ha conflito para esse envio_id;
      - o operador digita exatamente 'CONFIRMAR' quando solicitado.
    Qualquer outro caminho retorna sem chamar _aplicar_outros_documentos_no_envio.
    """
    _log('inicio', correlation_id, modo='aplicar', competencia=competencia, envio_id=envio_id)

    if not confirmar_campo_arquivos():
        _log('erro', correlation_id, motivo='CAMPO_ARQUIVOS_NAO_CONFIRMADO', envio_id=envio_id)
        print('CAMPO_ARQUIVOS_NAO_CONFIRMADO')
        print(
            "Nao foi possivel confirmar, por leitura via Meta API, que o campo 'Arquivos' "
            f"de Envios de Documentos corresponde ao Field ID {F_ENVIO_ARQUIVOS}. "
            'Abortando sem nenhuma escrita.'
        )
        return 'CAMPO_ARQUIVOS_NAO_CONFIRMADO'

    # Sempre refaz o dry-run -- nunca confia em relatorio anterior.
    resultado = _dry_run_outros_documentos_para_envios(competencia)
    alvo = next((e for e in resultado['envios'] if e['envio_id'] == envio_id), None)

    if alvo is None:
        print(f'Nenhum recibo novo encontrado para envio_id={envio_id} nesta competencia.')
        _log('fim', correlation_id, status='sem_novidade', envio_id=envio_id,
             motivo='nao_encontrado_no_dry_run')
        return 'sem_novidade'

    print(f"\n=== APLICAR | envio_id={envio_id} | correlation_id={correlation_id} ===")
    print(f"envio_nome={alvo['envio_nome']}")
    print(f"anexos atuais: {alvo['qtd_ja_existentes_no_envio']}")
    print(f"anexos a adicionar: {alvo['qtd_a_adicionar']} -> {alvo['filenames_a_adicionar']}")
    print(f"duplicados evitados: {alvo['duplicados_evitados']}")

    if alvo['conflitos']:
        print('\nCONFLITOS DETECTADOS -- aplicacao interrompida, nenhuma escrita sera feita.')
        print(alvo['conflitos'])
        _log('fim', correlation_id, status='conflito_detectado', envio_id=envio_id,
             conflitos=alvo['conflitos'])
        return 'conflito_detectado'

    if alvo['qtd_a_adicionar'] == 0:
        print('\nNenhuma novidade apos deduplicacao -- nada a aplicar.')
        _log('fim', correlation_id, status='sem_novidade', envio_id=envio_id)
        return 'sem_novidade'

    resposta = confirmar_input(
        f"\nDigite CONFIRMAR para aplicar {alvo['qtd_a_adicionar']} anexo(s) "
        f"ao envio {envio_id}: "
    )
    if resposta != 'CONFIRMAR':
        print('Cancelado -- nenhuma escrita foi feita.')
        _log('cancelamento', correlation_id, envio_id=envio_id)
        return 'cancelado'

    ids_antes = _ler_attachments_atuais(envio_id)
    _log('pre_patch', correlation_id, envio_id=envio_id, attachment_ids_existentes=ids_antes)

    resultado_aplicacao = _aplicar_outros_documentos_no_envio(envio_id, competencia)

    _log(
        'pos_patch', correlation_id, envio_id=envio_id,
        status=resultado_aplicacao.get('status'),
        adicionados=resultado_aplicacao.get('adicionados'),
        total_apos=resultado_aplicacao.get('total_apos'),
    )

    print(f"\nResultado: {resultado_aplicacao['status']}")
    if resultado_aplicacao.get('adicionados'):
        print(f"Adicionados: {resultado_aplicacao['adicionados']}")
    print(
        '\nRollback: nao ha desfazer automatico. Se for necessario reverter, um humano com '
        f"acesso ao Airtable deve restaurar manualmente o campo 'Arquivos' do Envio {envio_id} "
        f"para os attachment IDs registrados no log 'pre_patch' acima (correlation_id={correlation_id})."
    )
    return resultado_aplicacao['status']


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -m scripts.outros_documentos_cli',
        description=(
            'Comando manual para aplicar recibos de "Outros documentos" aos '
            'Envios de Documentos. Sem rota HTTP, sem job, sem cron.'
        ),
    )
    sub = parser.add_subparsers(dest='modo', required=True)

    p_dry = sub.add_parser('dry-run', help='Somente leitura -- nunca escreve.')
    p_dry.add_argument('--competencia', required=True)

    p_aplicar = sub.add_parser('aplicar', help='Escreve em UM envio, apos confirmacao explicita.')
    p_aplicar.add_argument('--competencia', required=True)
    p_aplicar.add_argument('--envio-id', required=True)

    args = parser.parse_args(argv)

    try:
        _validar_configuracao()
    except ConfiguracaoAusente as exc:
        print(str(exc))
        sys.exit(1)

    correlation_id = _novo_correlation_id()

    if args.modo == 'dry-run':
        cmd_dry_run(args.competencia, correlation_id)
    elif args.modo == 'aplicar':
        cmd_aplicar(args.competencia, args.envio_id, correlation_id)


if __name__ == '__main__':
    main()
