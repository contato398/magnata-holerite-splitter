"""
src/report_generator.py — Template narrativo da "Ficha de Auditoria Individual"

ORDEM DE DESIGN DA DIRETORIA (27/06/2026): esta entrega é SÓ o template/
layout de apresentação. Não lê dado real da Secullum/Airtable, não assume
que o saneamento de escalas (previsto para o dia seguinte) já ocorreu, e
não dispara nenhum processamento em massa. O único objetivo é fixar a
estética da ficha e validá-la com 1 colaborador FICTÍCIO antes de qualquer
nova tentativa de leitura/processamento real — aguardar aprovação da
diretoria para o próximo passo (ligar isso aos dados reais).

Formato de entrada esperado por `montar_ficha` — um dict já normalizado
(não o shape bruto da Secullum/Airtable; a função que faz essa tradução é
trabalho futuro, deliberadamente fora desta entrega):

    {
        'nome': str,
        'cpf': str,                      # com ou sem máscara
        'condominio': str,                # Posto/Local de trabalho
        'horario_escala': str,             # rótulo da escala no sistema
        'horas_trabalhadas_mes': str,      # 'HH:MM'
        'ocorrencias': {
            'faltas_integrais':  [str, ...],   # 1 item por dia/evento
            'atrasos_entradas':  [str, ...],
            'atestados_medicos': [str, ...],
            'trocas_ft':         [str, ...],
            'batidas_impares':   [str, ...],
            'intervalo_zelo':    [str, ...],   # extra, opcional (achado real
                                                 # de v2.55 sem categoria própria
                                                 # no template oficial)
        },
        'bonus': {'pago': bool, 'motivos': [str, ...]},
        'art71': {'horas': str, 'justificativa': str},   # 'HH:00' + texto
    }

Cada item de `ocorrencias` é UM evento (1 dia), não uma frase com vários
eventos concatenados — é isso que permite quebrar linha por evento em vez
de produzir texto corrido numa única célula/linha.
"""

LARGURA = 70
BONUS_VALOR_PADRAO = 'R$ 100,00'


def _cabecalho(condominio: str) -> str:
    linha = '=' * LARGURA
    return f'{linha}\n👤 FICHA DE AUDITORIA INDIVIDUAL - CONDOMÍNIO: {condominio}\n{linha}'


def _separador() -> str:
    return '-' * LARGURA


def _bloco_ocorrencia(rotulo: str, itens: list, texto_vazio: str) -> str:
    """Renderiza 1 categoria do Histórico Analítico.

    Sem itens: '» RÓTULO:      texto_vazio' (1 linha).
    Com itens: cabeçalho da categoria + 1 linha própria por evento — nunca
    concatena vários dias numa única linha corrida.
    """
    rotulo_fmt = f'» {rotulo}:'
    if not itens:
        return f'{rotulo_fmt:<25}{texto_vazio}'
    linhas = [rotulo_fmt]
    for item in itens:
        linhas.append(f'    - {item}')
    return '\n'.join(linhas)


def montar_ficha(dados: dict) -> str:
    """Monta o texto completo de 1 Ficha de Auditoria Individual."""
    oc = dados.get('ocorrencias') or {}
    bonus = dados.get('bonus') or {}
    art71 = dados.get('art71') or {}

    partes = [
        _cabecalho(dados.get('condominio') or 'SEM POSTO CADASTRADO'),
        f'• Nome do Colaborador: {dados.get("nome", "")}',
        f'• CPF: {dados.get("cpf", "")}  |  '
        f'• Horas Trabalhadas no Mês: {dados.get("horas_trabalhadas_mes", "00:00")}',
        f'• Horário/Escala Contratual no Sistema: {dados.get("horario_escala", "(não informado)")}',
        '',
        _separador(),
        '📋 HISTÓRICO ANALÍTICO DE OCORRÊNCIAS (RAIO-X DO MÊS)',
        _separador(),
        _bloco_ocorrencia('FALTAS INTEGRAIS', oc.get('faltas_integrais') or [], 'Nenhuma'),
        _bloco_ocorrencia('ATRASOS / ENTRADAS', oc.get('atrasos_entradas') or [], 'Regular'),
        _bloco_ocorrencia('ATESTADOS MÉDICOS', oc.get('atestados_medicos') or [],
                           'Não rastreado pelo sistema — confirmar manualmente com o RH'),
        _bloco_ocorrencia('TROCAS / FT (FOLGAS)', oc.get('trocas_ft') or [], 'Nenhuma'),
        _bloco_ocorrencia('BATIDAS ÍMPARES (ESQ)', oc.get('batidas_impares') or [], 'Nenhuma'),
    ]
    if oc.get('intervalo_zelo'):
        partes.append(_bloco_ocorrencia('INTERVALO (ZELO)', oc['intervalo_zelo'], ''))

    pago = bool(bonus.get('pago'))
    motivos = bonus.get('motivos') or []
    partes += [
        '',
        _separador(),
        '⚖️ CONCLUSÃO JURÍDICA E FINANCEIRA DO DEPARTAMENTO PESSOAL',
        _separador(),
        f'💰 BÔNUS DE ASSIDUIDADE ({BONUS_VALOR_PADRAO}): {"PAGO" if pago else "RETIDO"}',
    ]
    if pago or not motivos:
        partes.append('   ↳ Motivo Legal: 100% assíduo no período — nenhuma ocorrência de corte.')
    else:
        partes.append('   ↳ Motivo Legal:')
        for motivo in motivos:
            partes.append(f'        - {motivo}')

    partes += [
        '',
        f'🕒 HORAS EXTRAS ART. 71 CLT: {art71.get("horas", "00:00")}',
        f'   ↳ Justificativa Operacional: {art71.get("justificativa", "(não informado)")}',
        '=' * LARGURA,
    ]
    return '\n'.join(partes)


def gerar_relatorio_textual(colaboradores: list) -> str:
    """Concatena várias fichas, agrupadas/ordenadas por Condomínio e depois por Nome.

    `colaboradores`: lista de dicts no shape descrito no topo do módulo.
    """
    ordenados = sorted(
        colaboradores,
        key=lambda d: (d.get('condominio') or '', d.get('nome') or ''),
    )
    return '\n\n'.join(montar_ficha(c) for c in ordenados)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ DRY RUN ESTRUTURAL — 1 colaborador FICTÍCIO, só para validar a estética    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def colaborador_ficticio_exemplo() -> dict:
    """Dado 100% inventado — não vem de nenhuma chamada à Secullum/Airtable.

    Cobre de propósito TODAS as categorias com mais de 1 evento, pra provar
    que a quebra de linha funciona tanto com 1 item quanto com vários.
    """
    return {
        'nome': 'FULANO DE TAL EXEMPLO DA SILVA (FICTÍCIO)',
        'cpf': '000.000.000-00',
        'condominio': 'CONDOMÍNIO MODELO (EXEMPLO)',
        'horario_escala': '12x36 - 06h às 18h PAR',
        'horas_trabalhadas_mes': '187:30',
        'ocorrencias': {
            'faltas_integrais': ['Falta no dia 08/06'],
            'atrasos_entradas': [
                'Atraso de 15min no dia 10/06',
                'Saída antecipada de 20min no dia 22/06',
            ],
            'atestados_medicos': [],
            'trocas_ft': ['Cobriu Folga Trabalhada no dia 15/06 (referente à falta de Outro Colaborador Exemplo)'],
            'batidas_impares': ['Esquecimento de batida de saída no dia 20/06'],
            'intervalo_zelo': ['Intervalo não registrado (falta de zelo) em 27/06'],
        },
        'bonus': {
            'pago': False,
            'motivos': [
                'Falta no dia 08/06',
                'Atraso de 15min no dia 10/06',
                'Saída antecipada de 20min no dia 22/06',
            ],
        },
        'art71': {
            'horas': '14:00',
            'justificativa': '14 plantões em Turno Solo identificados = 14:00 horas extras.',
        },
    }


def executar_dry_run_estrutural() -> str:
    """Imprime na tela a ficha do colaborador fictício — só layout, sem dado real."""
    ficha = montar_ficha(colaborador_ficticio_exemplo())
    print(ficha)
    return ficha


if __name__ == '__main__':
    executar_dry_run_estrutural()
