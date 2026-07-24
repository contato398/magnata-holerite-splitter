"""
Comando interno e TEMPORARIO para vincular os 39 pares ja aprovados no
diagnostico manual de 2026-07-24 (competencia Junho 2026), escrevendo
F_OD_ENVIO na tabela "Outros documentos".

ESCOPO ESTRITAMENTE FECHADO: so os 39 pares fixos abaixo (PARES_APROVADOS),
nenhum outro, nenhuma descoberta dinamica de novos pares. Depois de
aplicado (ou descartado), este arquivo deve ser removido -- nao e parte
permanente do sistema, ao contrario de scripts/outros_documentos_cli.py.

Uso:
    python -m scripts.vincular_outros_documentos_junho_2026 dry-run
    python -m scripts.vincular_outros_documentos_junho_2026 aplicar

Regras:
  - "aplicar" sempre valida os 39 pares do zero antes de qualquer escrita
    -- nunca confia num dry-run anterior.
  - Se QUALQUER par (exceto os ja corretamente vinculados) divergir do
    esperado -- registro de origem ausente, Envio de destino ausente,
    F_OD_ENVIO ja apontando para outro Envio, funcionario incompativel,
    ou "Enviado em" diferente de 2026-06-15 -- a aplicacao INTEIRA e
    bloqueada: nenhum PATCH e feito, nem nos pares que estariam OK.
  - Excecao a essa regra: se F_OD_ENVIO ja for EXATAMENTE o envio_id
    esperado para aquele par, isso conta como "ja_vinculado" (idempotente)
    -- nao bloqueia os demais e nao gera um novo PATCH para ele.
  - So escreve no campo F_OD_ENVIO ("Envios de Documentos 2"). Nunca em
    Arquivos. Nunca dispara envio. Nunca chama
    _aplicar_outros_documentos_no_envio (nao e importada aqui).
  - Exige confirmacao textual exata "CONFIRMAR" antes do primeiro PATCH.
  - A validacao pre-escrita e tudo-ou-nada (aborta antes de qualquer
    escrita). Ja a escrita em si e uma sequencia de PATCHes independentes
    -- uma falha de rede/API num registro especifico durante a aplicacao
    NAO desfaz PATCHes ja bem-sucedidos em outros registros (Airtable nao
    oferece transacao entre registros diferentes); essa falha parcial e
    reportada explicitamente, nunca escondida.

Rollback: nao ha desfazer automatico. Antes de cada PATCH este comando
registra em log (evento 'snapshot_pre_patch', com o correlation_id da
execucao) o valor anterior de F_OD_ENVIO. Para reverter, um humano com
acesso ao Airtable deve restaurar esse valor manualmente.
"""

import argparse
import json
import logging
import re
import secrets
import sys
from datetime import datetime, timezone

import requests

from app import (
    AIRTABLE_API_KEY,
    BASE_ID,
    TABLE_ENVIOS,
    TABLE_OUTROS_DOCS,
    TABLE_FUNC,
    F_OD_DOCUMENTO,
    F_OD_ENVIO,
    _at_throttle,
    _at_headers,
)

logger = logging.getLogger('vincular_outros_documentos_junho_2026')

DATA_ENVIADO_ESPERADA = '2026-06-15'
CAMPO_ENVIADO_EM = 'Enviado em'
CAMPO_DATA_ENVIO = 'Data envio'
CAMPO_FUNC_ENVIO = 'Funcionário(s) Vinculado(s)'

_PADRAO_NOME_DOCUMENTO = re.compile(r'^Assiduidade\s+\S+\s+\d{4}\s*-\s*(.+)$', re.IGNORECASE)

# Allowlist fixa -- exatamente os 39 pares aprovados no diagnostico manual
# de 2026-07-24 (competencia Junho 2026). NAO adicionar, remover, nem
# gerar dinamicamente a partir de nenhuma consulta.
PARES_APROVADOS = {
    'rec0jP97qqztAKvPe': 'recEBy05FrKYZNjbH',
    'rec11mbbtJKpg9qNz': 'recvkK5NK675tRorU',
    'rec1S5n7t6uMaP4L4': 'recuVrTFB0W9tWKET',
    'rec3DXKhgMKg6r8fw': 'recCI4gBEBWTP5bKT',
    'rec3YDjDrL9rIhcHo': 'recnu47gLtuHDoTf9',
    'rec4KlNtHprfFVlUz': 'recKHhjuvt6F8RB6R',
    'rec4afBIchE3FB6aa': 'recIVNVo0D5NNSpS5',
    'rec5zwouTXHuLdZOm': 'recIlfKfdxRNqcdJ8',
    'rec6A2uN0KDcvfPKj': 'recbBFRciRU7YjecH',
    'rec8S8jl89jdjqMKE': 'recmZ0JZViBJw5N5q',
    'recAAeL2oDyAJ8xYs': 'recYbZt2HmtIxjS0P',
    'recBiuXyth3op6F4V': 'recrL0LzYhd2vHHos',
    'recC7tVBYtDJgrXRx': 'recbAd1r7MlJQEkgb',
    'recCEE8XKRB1LphiD': 'recKPF24Wz03cSQQE',
    'recEihLIuuucDwEnU': 'reck5qFmXVSi9JooV',
    'recEohHdnb5ewtJEK': 'recKEupL2BFMFYAll',
    'recFvJkCbj0FCsDp1': 'recrxrd1xQvZi6ICY',
    'recH5j2GlSWi0yUQe': 'recREVy5IWYYwXATb',
    'recK1mkHI5RYMqxvL': 'recJenZD9GoZbVRdQ',
    'recLSAQZjlZzliiy3': 'recaVcv7Q7SbJNrq0',
    'recNpOYTdVRxUrpSU': 'recka7UzPw0jcaaWZ',
    'recPPUgw9plINapXc': 'recRtOnKycfQXXbML',
    'recRRt087y5mFCYnK': 'recKQdNvwFT59M8PC',
    'recV48A7XouUaA0IH': 'recqk23xEBDjkfV44',
    'recWfIj4v3Bnb09uw': 'recjSf4ma9kPLIqRZ',
    'recbjD6680wYDw7Mp': 'recVU6govfcXv18f2',
    'recdU04MydfdbrPMT': 'rechlv3hKIEGhxPgh',
    'rechuE2ZunPLUk8T2': 'recynhTQzqonb2c0X',
    'reciv2CTvmcadjHIT': 'reckHNzvKUp2rcIo2',
    'reckOQr2OJo4wwyuW': 'recZ27Hf9z7xCOLEf',
    'reckXYFxzySz98Rp2': 'recMv6jwgVY4E1CeS',
    'recnEDVMH7ul63dvK': 'recxXUY8FnSmd74bS',
    'recq5aM6iUW8au8pZ': 'recixVYnFqidwoA2L',
    'recqFg2yygHgzuPFB': 'recL7ooQuugh8iosW',
    'recrdz9FEGvZ2SDIs': 'recLfj0rParVhRYOI',
    'recsDfODWSmjyMEZr': 'recm3NCwciQQYwpGO',
    'recsMdM4XHyg2GvlF': 'recjdWFmG0NQ4SXAU',
    'recxofmoNWOcRH6Z0': 'recJnwCYWF6goryTg',
    'reczv7fjlIdWTjepv': 'recaPY3X7u7LucLwV',
}

if len(PARES_APROVADOS) != 39:
    raise RuntimeError(
        f'PARES_APROVADOS deveria ter exatamente 39 entradas, tem {len(PARES_APROVADOS)}. '
        'Corrigir a allowlist antes de usar este comando.'
    )


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
            'Defina as variaveis de ambiente antes de rodar este comando.'
        )


def _novo_correlation_id():
    return f"vod{secrets.token_hex(8)}"


def _log(evento, correlation_id, **campos):
    payload = {'evento': evento, 'correlation_id': correlation_id}
    payload.update(campos)
    logger.info(
        'vincular_outros_documentos_junho_2026 %s',
        json.dumps(payload, ensure_ascii=False, default=str),
    )


def _extrair_nome_do_documento(doc):
    m = _PADRAO_NOME_DOCUMENTO.match(doc or '')
    return (m.group(1).strip() if m else (doc or '').strip())


def _get_registro(table_id, record_id):
    _at_throttle()
    return requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}',
        headers=_at_headers(),
        timeout=30,
    )


def _item_funcionario_compativel(item, nome_esperado):
    """
    Confere se UM item da lista 'Funcionario(s) Vinculado(s)' do Envio e
    compativel com nome_esperado. A API do Airtable pode retornar um item
    de campo de link de duas formas:
      - objeto {'id': ..., 'name': ...} (quando o nome vem embutido);
      - string 'recXXXX' (so o ID) -- nesse caso busca o registro do
        Funcionario e compara pelo record_id (confirma que o registro
        retornado e o mesmo que foi pedido) e pelo Nome Completo
        normalizado.
    """
    if isinstance(item, dict):
        nome = item.get('name') or ''
        return nome.strip().casefold() == nome_esperado.strip().casefold()

    if isinstance(item, str):
        r_func = _get_registro(TABLE_FUNC, item)
        if r_func.status_code == 404:
            return False
        r_func.raise_for_status()
        corpo_func = r_func.json()
        nome = corpo_func.get('fields', {}).get('Nome Completo') or ''
        return (
            corpo_func.get('id') == item
            and nome.strip().casefold() == nome_esperado.strip().casefold()
        )

    return False


def validar_par(record_id, envio_id_esperado):
    """
    Valida UM par sem escrever nada.

    Retorna dict com 'status' em {'ok', 'ja_vinculado', 'divergente'} e,
    quando 'divergente', um 'motivo' explicito. Nunca escreve.
    """
    r_od = _get_registro(TABLE_OUTROS_DOCS, record_id)
    if r_od.status_code == 404:
        return {'status': 'divergente', 'motivo': 'registro_origem_nao_encontrado'}
    r_od.raise_for_status()
    campos_od = r_od.json().get('fields', {})

    # Confere o vinculo atual ANTES de buscar o Envio -- se ja houver
    # qualquer vinculo (correto ou divergente), a comparacao e so de IDs,
    # nao precisa dos campos do Envio.
    vinculo_atual = campos_od.get(F_OD_ENVIO) or []
    ids_atual = [v['id'] if isinstance(v, dict) else v for v in vinculo_atual]

    if ids_atual:
        if ids_atual == [envio_id_esperado]:
            return {'status': 'ja_vinculado', 'valor_atual_od': ids_atual}
        return {
            'status': 'divergente', 'motivo': 'vinculo_diferente_ja_existe',
            'valor_atual_od': ids_atual,
        }

    r_envio = _get_registro(TABLE_ENVIOS, envio_id_esperado)
    if r_envio.status_code == 404:
        return {'status': 'divergente', 'motivo': 'envio_destino_nao_encontrado'}
    r_envio.raise_for_status()
    campos_envio = r_envio.json().get('fields', {})

    nome_esperado = _extrair_nome_do_documento(campos_od.get(F_OD_DOCUMENTO, ''))
    func_links = campos_envio.get(CAMPO_FUNC_ENVIO) or []
    compativel = any(_item_funcionario_compativel(item, nome_esperado) for item in func_links)
    if not compativel:
        return {
            'status': 'divergente', 'motivo': 'funcionario_incompativel',
            'nome_esperado': nome_esperado, 'func_links': func_links,
        }

    enviado_em = campos_envio.get(CAMPO_ENVIADO_EM) or campos_envio.get(CAMPO_DATA_ENVIO)
    data_atual = (enviado_em or '')[:10]
    if data_atual != DATA_ENVIADO_ESPERADA:
        return {
            'status': 'divergente', 'motivo': 'data_enviado_em_diferente',
            'enviado_em_atual': enviado_em,
        }

    return {'status': 'ok', 'valor_atual_od': ids_atual}


def _validar_todos(correlation_id):
    resultados = {}
    for record_id, envio_id in PARES_APROVADOS.items():
        resultados[record_id] = validar_par(record_id, envio_id)
    return resultados


def cmd_dry_run(correlation_id):
    """Somente leitura. Valida os 39 pares e reporta -- nunca escreve."""
    _log('inicio', correlation_id, modo='dry-run', total_pares=len(PARES_APROVADOS))

    resultados = _validar_todos(correlation_id)
    ok = [k for k, v in resultados.items() if v['status'] == 'ok']
    ja_vinculado = [k for k, v in resultados.items() if v['status'] == 'ja_vinculado']
    divergente = [k for k, v in resultados.items() if v['status'] == 'divergente']

    print(f"\n=== DRY-RUN | vincular_outros_documentos_junho_2026 | correlation_id={correlation_id} ===\n")
    print(f"Total de pares: {len(PARES_APROVADOS)}")
    print(f"OK para aplicar: {len(ok)}")
    print(f"Ja vinculados (idempotente, sem acao): {len(ja_vinculado)}")
    print(f"Divergentes (bloqueiam a aplicacao inteira): {len(divergente)}")
    if divergente:
        print("\nDivergencias:")
        for rid in divergente:
            print(f"  {rid} -> {PARES_APROVADOS[rid]} | {resultados[rid]['motivo']}")

    _log(
        'fim', correlation_id, modo='dry-run',
        ok=len(ok), ja_vinculado=len(ja_vinculado), divergente=len(divergente),
    )
    return resultados


def cmd_aplicar(correlation_id, confirmar_input=input):
    """
    Valida os 39 pares do zero. Se houver qualquer divergencia, bloqueia
    tudo (zero PATCH). Caso contrario, pede confirmacao textual exata
    'CONFIRMAR' e so entao aplica PATCH em F_OD_ENVIO dos pares 'ok'
    (pares 'ja_vinculado' sao pulados, sem escrita).
    """
    _log('inicio', correlation_id, modo='aplicar', total_pares=len(PARES_APROVADOS))

    resultados = _validar_todos(correlation_id)
    divergencias = {k: v for k, v in resultados.items() if v['status'] == 'divergente'}

    if divergencias:
        _log(
            'bloqueado', correlation_id, motivo='divergencias_detectadas',
            quantidade=len(divergencias),
            detalhe={k: v['motivo'] for k, v in divergencias.items()},
        )
        print(f"\nBLOQUEADO: {len(divergencias)} divergencia(s) detectada(s). Nenhum PATCH sera feito.")
        for rid, info in divergencias.items():
            print(f"  {rid} -> {PARES_APROVADOS[rid]} | {info['motivo']}")
        return 'bloqueado'

    a_aplicar = {k: v for k, v in resultados.items() if v['status'] == 'ok'}
    ja_vinculados = {k: v for k, v in resultados.items() if v['status'] == 'ja_vinculado'}

    print(f"\n=== APLICAR | vincular_outros_documentos_junho_2026 | correlation_id={correlation_id} ===")
    print(f"Sem divergencias. {len(a_aplicar)} a aplicar, {len(ja_vinculados)} ja vinculados (sem acao).")

    if not a_aplicar:
        print('Nada a aplicar -- todos os pares ja estao vinculados corretamente.')
        _log('fim', correlation_id, status='nada_a_aplicar', ja_vinculados=len(ja_vinculados))
        return 'nada_a_aplicar'

    resposta = confirmar_input(
        f"\nDigite CONFIRMAR para aplicar {len(a_aplicar)} vinculo(s) em F_OD_ENVIO: "
    )
    if resposta != 'CONFIRMAR':
        print('Cancelado -- nenhuma escrita foi feita.')
        _log('cancelamento', correlation_id, a_aplicar=len(a_aplicar))
        return 'cancelado'

    aplicados = []
    erros = []
    for record_id, info in a_aplicar.items():
        envio_id = PARES_APROVADOS[record_id]
        timestamp = datetime.now(timezone.utc).isoformat()
        snapshot = {
            'record_id': record_id,
            'valor_anterior_F_OD_ENVIO': info.get('valor_atual_od') or [],
            'valor_novo_F_OD_ENVIO': [envio_id],
            'timestamp': timestamp,
        }
        _log('snapshot_pre_patch', correlation_id, **snapshot)

        try:
            _at_throttle()
            r = requests.patch(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_OUTROS_DOCS}/{record_id}',
                headers=_at_headers(),
                json={'fields': {F_OD_ENVIO: [envio_id]}, 'typecast': True},
                timeout=30,
            )
            if not r.ok:
                erros.append({'record_id': record_id, 'status_code': r.status_code, 'texto': (r.text or '')[:300]})
                _log('erro_patch', correlation_id, record_id=record_id, status_code=r.status_code)
                continue
            aplicados.append(record_id)
            _log('patch_aplicado', correlation_id, record_id=record_id, envio_id=envio_id)
        except Exception as exc:
            erros.append({'record_id': record_id, 'excecao': str(exc)})
            _log('erro_patch', correlation_id, record_id=record_id, excecao=str(exc))

    print(f"\nAplicados: {len(aplicados)}/{len(a_aplicar)}")
    if erros:
        print(f"ERROS (falha parcial de API -- ver log 'erro_patch'): {len(erros)}")
        for e in erros:
            print(f"  {e['record_id']}: {e.get('status_code') or e.get('excecao')}")

    _log(
        'fim', correlation_id, aplicados=len(aplicados), erros=len(erros),
        ja_vinculados=len(ja_vinculados),
    )
    return {'aplicados': aplicados, 'erros': erros, 'ja_vinculados': list(ja_vinculados)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -m scripts.vincular_outros_documentos_junho_2026',
        description=(
            'Comando TEMPORARIO para vincular os 39 pares aprovados (Junho 2026) '
            'em F_OD_ENVIO. Sem rota HTTP, sem job, sem cron.'
        ),
    )
    sub = parser.add_subparsers(dest='modo', required=True)
    sub.add_parser('dry-run', help='Somente leitura -- valida os 39 pares, nunca escreve.')
    sub.add_parser('aplicar', help='Escreve F_OD_ENVIO apos validacao completa e confirmacao.')

    args = parser.parse_args(argv)

    try:
        _validar_configuracao()
    except ConfiguracaoAusente as exc:
        print(str(exc))
        sys.exit(1)

    correlation_id = _novo_correlation_id()

    if args.modo == 'dry-run':
        cmd_dry_run(correlation_id)
    elif args.modo == 'aplicar':
        cmd_aplicar(correlation_id)


if __name__ == '__main__':
    main()
