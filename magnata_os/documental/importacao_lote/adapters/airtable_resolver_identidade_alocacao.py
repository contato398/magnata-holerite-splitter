"""Adapter REAL, read-only, de IDENTIFICAÇÃO e SNAPSHOT para a missão
"CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1" (`magnata_os/documental/alocacao/
confirmacao.py`, `comparacao_airtable.py`). Único ponto deste
repositório que fala com o Airtable para esta missão -- "qualquer
leitura do Airtable deve passar por adapter substituível" (regra
pétrea da missão): trocar a fonte de identidade/snapshot no futuro
significa trocar ESTA classe por outra com a mesma superfície, nunca
tocar `confirmacao.py`/`comparacao_airtable.py`.

Fala só com `LeitorAirtableSomenteLeitura` (só métodos GET, já
existente) -- nenhum método novo adicionado a `airtable_leitura.py`,
nenhuma escrita, nenhuma dependência nova do schema Airtable além do
que este pacote já duplica e confirma.

3 responsabilidades, cada uma com um método próprio -- nunca uma
fundida na outra (mesma disciplina de CLAUDE.md raiz §4, "manter
sempre separados"):

  1. **Resolução de borda** (`resolver_colaborador_id`): CPF -> id,
     usada só por quem MONTA uma `SolicitacaoConfirmacaoAlocacao`
     (fora deste módulo) -- `confirmacao.py` nunca chama isto.
  2. **Re-confirmação no momento da aplicação**
     (`confirmar_colaborador_existe`/`confirmar_posto_existe`): valida
     que um id JÁ SELECIONADO ainda existe no snapshot atual -- é o
     que `confirmacao.py::aplicar_confirmacao_alocacao` de fato chama.
  3. **Snapshot para comparação** (`postos_atuais_do_colaborador`):
     usado só por `comparacao_airtable.py` (FASE 6, diagnóstico
     read-only, nunca reconciliação).

Reaproveita EXATAMENTE o que já está confirmado neste pacote de
adapters, nada novo é inventado:
  - `listar_funcionarios()` (já existente, mesmo método já usado por
    `magnata_os.documental.alocacao.wiring` para resolver CPF ->
    colaborador_id) -- devolve `fields` chaveados por NOME (`'CPF'`),
    então não depende de nenhum Field ID de CPF (que este pacote nunca
    confirmou nem duplicou até hoje).
  - `normalizar_cpf` (`magnata_os.documental.importacao_lote.dominio`,
    já existente, puro) -- mesma normalização (só dígitos) usada em
    toda comparação de CPF do repositório.
  - `TABLE_LOCAIS`/`F_LOCAL_CLIENTE` e `TABLE_FUNC`/`F_FUNC_LOCAIS` (já
    confirmados por auditoria real de schema,
    `docs/decisoes/piloto-real-prestacao-readonly-v1.md`, já
    duplicados em `airtable_vinculos_prestacao.py`).

Posto é identificado por `posto_id` (Airtable record id) -- NUNCA
resolvido por nome livre. Um Field ID de 'Nome' para a tabela Locais
NÃO está confirmado em nenhum documento nem código deste repositório
até hoje; fabricar um aqui sem prova real violaria a disciplina já
estabelecida em todo este pacote (CLAUDE.md raiz §11 -- um Field ID
errado silenciosamente nunca encontraria nada e pareceria,
incorretamente, "posto não identificado" para sempre). A convenção já
usada em todo o subsistema de alocação (`eventos.py`, `captura.py`,
`resolucao.py`) já trata posto como `posto_id` opaco.

NUNCA chamado com Airtable live nesta missão -- testado só com
`Mock()`/fake de leitor (mesma disciplina de todo o resto deste
pacote, ver `test_magnata_os_documental_alocacao_confirmacao_shadow_v1.py`)."""
from __future__ import annotations

from typing import FrozenSet, Optional

from ..dominio import normalizar_cpf
from .airtable_leitura import LeitorAirtableSomenteLeitura, TABLE_FUNC
from .airtable_vinculos_prestacao import F_FUNC_LOCAIS, F_LOCAL_CLIENTE, TABLE_LOCAIS


def _ids_vinculados(valor: object) -> tuple:
    """Cópia local e pequena do helper já usado em
    `airtable_vinculos_prestacao.py`/`airtable_colaboradores_esperados_
    prestacao.py` -- duplicada de propósito para não depender de um
    símbolo privado (`_`) de outro módulo adapter (mesma disciplina já
    estabelecida nesses 2 adapters)."""
    if not isinstance(valor, list):
        return ()
    ids = {
        item if isinstance(item, str) else item.get('id')
        for item in valor
        if isinstance(item, str) or (isinstance(item, dict) and isinstance(item.get('id'), str))
    }
    return tuple(sorted(item for item in ids if item))


class ColaboradorAmbiguoError(ValueError):
    """Mais de um colaborador cadastrado com o mesmo CPF -- nunca
    escolhe o primeiro; dado de cadastro duplicado é sempre reportado,
    nunca resolvido por adivinhação (mesma disciplina de
    `ClassificacaoCorrespondencia.AMBIGUOUS` em todo este pacote)."""


class ResolverIdentidadeAlocacaoAirtableShadow:
    """Identificação/snapshot real de colaborador e posto -- SOMENTE
    leitura, nunca escreve nada no Airtable, nunca decide data
    efetiva."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura) -> None:
        self._leitor = leitor

    # ── 1. Resolução de borda (fora de `confirmacao.py`) ────────────────

    def resolver_colaborador_id(self, cpf: str) -> Optional[str]:
        """CPF -> func_id, só quando exatamente 1 colaborador casa.
        Levanta `ColaboradorAmbiguoError` se mais de 1 casar -- nunca
        escolhe o primeiro."""
        candidatos = self._candidatos_por_cpf(cpf)
        if len(candidatos) > 1:
            raise ColaboradorAmbiguoError(
                f'{len(candidatos)} colaboradores cadastrados com o mesmo CPF')
        return candidatos[0].func_id if candidatos else None

    # ── 2. Re-confirmação de identidade já selecionada ──────────────────

    def confirmar_colaborador_existe(self, colaborador_id: str) -> bool:
        """Confirma que `colaborador_id` corresponde a um Funcionário
        real e atual no Airtable -- nunca resolve por CPF/nome aqui."""
        return any(
            candidato.func_id == colaborador_id
            for candidato in self._leitor.listar_funcionarios()
        )

    def confirmar_posto_existe(self, posto_id: str) -> bool:
        """Confirma que `posto_id` corresponde a um Local real e atual
        no Airtable -- nunca resolve por nome, só valida existência do
        record id já informado (ver docstring do módulo)."""
        registros = self._leitor.listar_registros(table_id=TABLE_LOCAIS, fields=[F_LOCAL_CLIENTE])
        return any(registro.get('id') == posto_id for registro in registros)

    # ── 3. Snapshot para comparação (FASE 6, diagnóstico) ───────────────

    def postos_atuais_do_colaborador(self, colaborador_id: str) -> FrozenSet[str]:
        """Locais atualmente vinculados a este Funcionário segundo o
        Airtable ("Locais de trabalho", `F_FUNC_LOCAIS`) -- fotografia
        operacional CORRENTE, nunca histórica (Airtable não guarda
        vigência). Usado só por `comparacao_airtable.py`, nunca por
        `confirmacao.py`."""
        registros = self._leitor.listar_registros(table_id=TABLE_FUNC, fields=[F_FUNC_LOCAIS])
        locais: set = set()
        for registro in registros:
            if registro.get('id') == colaborador_id:
                locais.update(_ids_vinculados(registro.get('fields', {}).get(F_FUNC_LOCAIS)))
        return frozenset(locais)

    def _candidatos_por_cpf(self, cpf: str):
        alvo = normalizar_cpf(cpf)
        return [
            candidato for candidato in self._leitor.listar_funcionarios()
            if candidato.cpf and normalizar_cpf(candidato.cpf) == alvo and alvo
        ]
