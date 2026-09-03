"""Adapter READ-ONLY de registros diários de Ponto (missão "FONTE DE
INVENTÁRIO DE FOLHA/CARTÃO DE PONTO V1").

Schema REAL já confirmado em produção — reaproveitado, nunca inventado:
tabela `AT_PONTO`/campos `F_FUNC`/`F_DATA`/`F_ENTRADA`/`F_SAIDA_AL`/
`F_RETORNO_AL`/`F_SAIDA` já usados por `src/ingestao_secullum.py`
(espelhamento Secullum -> Airtable, em produção). IDs duplicados aqui
de propósito, nunca importados de `src/ingestao_secullum.py` nem de
`app.py` — mesma disciplina já registrada em
`magnata_os/documental/importacao_lote/CLAUDE.md` ("IDs de tabela/campo
do Airtable duplicados aqui, não importados de app.py"): evita
acoplamento com um módulo Flask não relacionado a este pacote.

Implementa `FonteRegistrosPontoBrutos` (porta do núcleo,
`classificacao/fonte_inventario_ponto_prestacao.py`) — nenhuma regra
semântica mora aqui (nenhuma decisão de vínculo/competência/conflito;
isso é todo responsabilidade da fonte de inventário que consome este
adapter). Só GET — nenhum método de escrita, nenhum campo novo, nenhuma
tabela alterada."""
from __future__ import annotations

import datetime
from typing import Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_inventario_ponto_prestacao import RegistroPontoBruto

from .airtable_leitura import LeitorAirtableSomenteLeitura

AT_PONTO = 'tblmgV10s3dZiP8av'
F_FUNC = 'fldR50BgugvINUG2v'      # Funcionário (link)
F_DATA = 'fldqKMo8FVKTYaSoI'      # Data
F_ENTRADA = 'fldgF4cITGk0inwX4'   # Entrada-
F_SAIDA_AL = 'fldx3dhHn1BHeQzSm'  # Saída-pro-almoço
F_RETORNO_AL = 'fldI6cRPzLQ8Z7q8b'  # Volta-do-almoço
F_SAIDA = 'fldwJgA0KUpR8Mxpa'     # Saída-

_CAMPOS_BATIDA = (F_ENTRADA, F_SAIDA_AL, F_RETORNO_AL, F_SAIDA)


def _id_vinculado_unico(valor: object) -> str | None:
    if not isinstance(valor, list) or len(valor) != 1:
        return None
    item = valor[0]
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and isinstance(item.get('id'), str):
        return item['id']
    return None


class FonteRegistrosPontoAirtableShadow:
    """Implementa `FonteRegistrosPontoBrutos` lendo `AT_PONTO` por
    intervalo de datas. Um registro que não linka EXATAMENTE 1
    Funcionário é descartado (nunca inventa vínculo múltiplo aqui —
    vínculo N:1 de Funcionário->registro de Ponto nunca é esperado pelo
    schema real; se acontecer, é dado corrompido, não uma decisão desta
    fonte)."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def listar_no_intervalo(
        self, data_inicio: datetime.date, data_fim: datetime.date,
    ) -> Tuple[RegistroPontoBruto, ...]:
        formula = (
            f"AND(IS_AFTER({{{F_DATA}}}, '{(data_inicio - datetime.timedelta(days=1)).isoformat()}'), "
            f"IS_BEFORE({{{F_DATA}}}, '{(data_fim + datetime.timedelta(days=1)).isoformat()}'))"
        )
        registros = self._leitor.listar_registros(
            table_id=AT_PONTO,
            fields=[F_FUNC, F_DATA, *_CAMPOS_BATIDA],
            filter_by_formula=formula,
        )
        resultado = []
        for registro in registros:
            fields = registro.get('fields', {})
            func_id = _id_vinculado_unico(fields.get(F_FUNC))
            data_texto = fields.get(F_DATA)
            if not func_id or not isinstance(data_texto, str):
                continue
            try:
                data = datetime.date.fromisoformat(data_texto[:10])
            except ValueError:
                continue
            batidas = tuple(
                fields[campo] for campo in _CAMPOS_BATIDA
                if isinstance(fields.get(campo), str) and fields[campo]
            )
            resultado.append(RegistroPontoBruto(
                documento_id=registro['id'],
                colaborador=ReferenciaCanonica('FUNCIONARIO', func_id),
                data=data,
                batidas=batidas,
                possui_marcacao=bool(batidas),
            ))
        return tuple(resultado)
