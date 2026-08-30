"""Adapter temporário read-only de colaboradores ESPERADOS por cliente
da prestação (ADENDO DE CONTINUIDADE, item 3 — "investigar se a
composição esperada de colaboradores por cliente pode ser derivada das
estruturas/vínculos já conhecidos, antes de parar para pedir decisão
humana").

Direção INVERSA de `FonteVinculosPrestacaoAirtableShadow`
(`airtable_vinculos_prestacao.py`, que resolve COLABORADOR/
FUNCIONARIO/UNIDADE_POSTO -> CLIENTE): aqui a pergunta é CLIENTE ->
quais COLABORADORES esperados. Auditoria confirmou que isso É derivável
das MESMAS 2 tabelas/campos já usados por aquele adapter (Local<->
Cliente via `F_LOCAL_CLIENTE`, Funcionário<->Local via `F_FUNC_LOCAIS`)
+ o campo de Status do Funcionário já documentado em `app.py`
(`F_FUNC_STATUS`/`STATUS_FUNCIONARIO_ATIVO`, duplicado aqui — nunca
importado do legado, mesma disciplina de `airtable_vinculos_
prestacao.py`) para restringir a colaboradores ATIVOS.

GAP registrado, não escondido: não existe, no schema auditado até
agora, nenhum campo de vínculo com validade/período (início/fim)
separado do Status — "esperado NESTA competência" é aproximado por
"vinculado a um Local deste cliente E Status atual = Ativo" (a mesma
aproximação, implícita, que já vale para toda leitura de vínculo deste
módulo — nenhuma tabela de histórico de vínculo por mês foi encontrada
no repositório). Se essa aproximação se mostrar insuficiente para um
cliente real, é uma decisão humana nova, não algo a inferir aqui.

Sem `filterByFormula` por nome de campo — este pacote só duplica IDs de
campo (nunca nomes de campo, ver `magnata_os/documental/
importacao_lote/CLAUDE.md`), e o Airtable exige o NOME do campo dentro
de uma fórmula. Busca TODOS os registros de cada tabela (mesmo padrão
já usado por `listar_clientes()`/`listar_funcionarios()` em
`airtable_leitura.py`) e filtra em Python — mais registros trafegados,
zero risco de fórmula malformada ou campo errado.

NUNCA chamado com Airtable live nesta missão — testado só com um
`LeitorAirtableSomenteLeitura` fake (mesma disciplina do restante deste
pacote de adapters, ver `test_airtable_colaboradores_esperados_
prestacao.py`).

Identidade sempre `ReferenciaCanonica('COLABORADOR', func_id)` — nunca
CPF/nome; este adapter nunca sequer SOLICITA os campos `Nome Completo`/
`CPF` ao Airtable (least-privilege de campo, não só de escrita)."""
from __future__ import annotations

from typing import FrozenSet, Tuple

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica

from .airtable_leitura import LeitorAirtableSomenteLeitura, TABLE_FUNC
from .airtable_vinculos_prestacao import F_FUNC_LOCAIS, F_LOCAL_CLIENTE, TABLE_LOCAIS

# Duplicado de app.py::F_FUNC_STATUS/STATUS_FUNCIONARIO_ATIVO (legado
# protegido, NUNCA importado — mesma disciplina de TABLE_LOCAIS/
# F_FUNC_LOCAIS/F_LOCAL_CLIENTE em airtable_vinculos_prestacao.py).
F_FUNC_STATUS = 'fld5T04dlg1Yt6Xj8'
STATUS_FUNCIONARIO_ATIVO = 'Ativo'


def _ids_vinculados(valor: object) -> Tuple[str, ...]:
    """Cópia local e pequena do helper já usado em
    `airtable_vinculos_prestacao.py` -- duplicada de propósito para não
    depender de um símbolo privado (`_`) de outro módulo adapter;
    lógica idêntica, mantida em sincronia por teste (`test_adapter_usa_
    somente_superficie_read_only`, análogo)."""
    if not isinstance(valor, list):
        return ()
    ids = {
        item if isinstance(item, str) else item.get('id')
        for item in valor
        if isinstance(item, str) or (isinstance(item, dict) and isinstance(item.get('id'), str))
    }
    return tuple(sorted(item for item in ids if item))


class FonteColaboradoresEsperadosPrestacaoAirtableShadow:
    """Lê Cliente -> Locais -> Funcionários com Status=Ativo, sem
    nenhuma escrita. Implementa `FonteColaboradoresEsperadosPrestacao`
    (Protocol, `magnata_os/classificacao/fonte_colaboradores_esperados_
    prestacao.py`) — mesmo papel de `FonteVinculosPrestacaoAirtableShadow`
    para `FonteVinculosPrestacao`, direção inversa."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura):
        self._leitor = leitor

    def colaboradores_esperados_para(
        self, cliente: ReferenciaCanonica, contexto: ContextoCicloPrestacao,
    ) -> Tuple[ReferenciaCanonica, ...]:
        if cliente.tipo_entidade != 'CLIENTE':
            raise ValueError('cliente deve ser referencia canonica de CLIENTE')
        locais_do_cliente = self._locais_do_cliente(cliente.entidade_id)
        if not locais_do_cliente:
            return ()
        return self._colaboradores_ativos_dos_locais(locais_do_cliente)

    def _locais_do_cliente(self, cliente_id: str) -> FrozenSet[str]:
        registros = self._leitor.listar_registros(table_id=TABLE_LOCAIS, fields=[F_LOCAL_CLIENTE])
        return frozenset(
            registro['id']
            for registro in registros
            if cliente_id in _ids_vinculados(registro.get('fields', {}).get(F_LOCAL_CLIENTE))
        )

    def _colaboradores_ativos_dos_locais(self, locais: FrozenSet[str]) -> Tuple[ReferenciaCanonica, ...]:
        registros = self._leitor.listar_registros(table_id=TABLE_FUNC, fields=[F_FUNC_LOCAIS, F_FUNC_STATUS])
        ids_ativos = sorted({
            registro['id']
            for registro in registros
            if registro.get('fields', {}).get(F_FUNC_STATUS) == STATUS_FUNCIONARIO_ATIVO
            and locais.intersection(_ids_vinculados(registro.get('fields', {}).get(F_FUNC_LOCAIS)))
        })
        return tuple(ReferenciaCanonica('COLABORADOR', func_id) for func_id in ids_ativos)
