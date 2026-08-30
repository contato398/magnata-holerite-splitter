"""Adapter READ-ONLY de Holerites por cliente/competência (missão
"INVENTÁRIO DOCUMENTAL REAL DA PRESTAÇÃO", Fase 4).

`TABLE_HOL` (Holerites) só linka o Funcionário (`F_HOL_FUNC`) — nunca o
Cliente diretamente (schema já confirmado por leitura live de
Clientes/Locais/Funcionários na missão anterior; Holerites em si NÃO
foi lido live nesta missão, só o campo já duplicado em `airtable_
leitura.py::holerites_existentes_na_folha`). Por isso este adapter
reaproveita `FonteVinculosPrestacaoAirtableShadow` (Funcionário->Local
->Cliente, já existente) para resolver a qual cliente cada Holerite
pertence — nunca reimplementa essa resolução.

Colaborador SEMPRE sanitizado (`ReferenciaCanonica('COLABORADOR',
func_id)`), nunca CPF/nome — este adapter nunca solicita esses campos.

Fiel à cláusula pétrea #9 do corredor: qualquer resolução que não seja
`RESOLVIDA` com exatamente o cliente pedido entre os confirmados é
descartada (o Holerite simplesmente não aparece para este cliente) --
nunca uma suposição. Um Holerite cujo colaborador resolve para 2+
clientes (vínculo múltiplo genuíno) aparece para CADA um desses
clientes -- mesma identidade documental, nunca duplicada fisicamente,
mesma semântica de `itens_para_multiplos_clientes_do_vinculo`."""
from __future__ import annotations

from typing import Tuple

from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.vinculos_prestacao import (
    FonteVinculosPrestacao,
    resolver_clientes_validado,
)

from .airtable_leitura import LeitorAirtableSomenteLeitura

TABLE_HOL = 'tblVaUgZeFfa5zRcH'
F_HOL_FUNC = 'fldTXMjeHfgyDas9f'
TIPO_HOLERITE = 'Holerite'

_MESES_PT = (
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
)


def _folha_mensal(competencia_id: str) -> str:
    """Cópia local e pequena do helper já usado em `airtable_inventario_
    prestacao.py` -- duplicada de propósito para não depender de um
    símbolo privado (`_`) de outro módulo adapter, mesma disciplina já
    usada em `airtable_colaboradores_esperados_prestacao.py`."""
    try:
        ano_texto, mes_texto = competencia_id.split('-', maxsplit=1)
        ano = int(ano_texto)
        mes = int(mes_texto)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError('competencia deve usar o formato AAAA-MM') from exc
    if len(ano_texto) != 4 or len(mes_texto) != 2 or not 1 <= mes <= 12:
        raise ValueError('competencia deve usar o formato AAAA-MM')
    return f'{_MESES_PT[mes - 1]} {ano}'


def _ids_vinculados(valor: object) -> Tuple[str, ...]:
    if not isinstance(valor, list):
        return ()
    ids = {
        item if isinstance(item, str) else item.get('id')
        for item in valor
        if isinstance(item, str) or (isinstance(item, dict) and isinstance(item.get('id'), str))
    }
    return tuple(sorted(item for item in ids if item))


class FonteInventarioHoleritesAirtableShadow:
    """Implementa `FonteInventarioPrestacao` para a família Holerite."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura, fonte_vinculos: FonteVinculosPrestacao):
        self._leitor = leitor
        self._fonte_vinculos = fonte_vinculos

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        if competencia.tipo_entidade != 'COMPETENCIA':
            raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')

        folha = _folha_mensal(competencia.entidade_id)
        registros = self._leitor.listar_registros(
            table_id=TABLE_HOL, fields=[F_HOL_FUNC],
            filter_by_formula=f'{{Folha Mensal}}="{folha}"',
        )
        itens = []
        for registro in registros:
            for func_id in _ids_vinculados(registro.get('fields', {}).get(F_HOL_FUNC)):
                origem = ReferenciaCanonica('FUNCIONARIO', func_id)
                try:
                    resolucao = resolver_clientes_validado(self._fonte_vinculos, origem, competencia)
                except ValueError:
                    continue
                if resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA:
                    continue
                if cliente not in resolucao.valores_confirmados:
                    continue
                itens.append(ItemInventarioPrestacao(
                    documento_id=registro['id'], tipo_documental=TIPO_HOLERITE,
                    cliente=cliente, competencia=competencia,
                    colaborador=ReferenciaCanonica('COLABORADOR', func_id),
                ))
        return tuple(sorted(itens, key=lambda item: item.documento_id))
