"""Resolvedor REAL, read-only, de IDENTIDADE (nunca data) para a missão
"CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1" (`magnata_os/documental/alocacao/
confirmacao.py`). Confirma que um CPF corresponde a um colaborador REAL
conhecido e que um `posto_id` corresponde a um Local REAL e atual, ambos
por LEITURA do Airtable via `LeitorAirtableSomenteLeitura` (só métodos
GET, já existente -- nenhum método novo adicionado a
`airtable_leitura.py`).

Nunca decide `data_efetiva` -- essa responsabilidade é inteiramente da
confirmação humana (`confirmacao.py`); este adapter só resolve/confirma
IDENTIDADE.

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
  - `TABLE_LOCAIS`/`F_LOCAL_CLIENTE` (já confirmados por auditoria real
    de schema, `docs/decisoes/piloto-real-prestacao-readonly-v1.md`,
    já duplicados em `airtable_vinculos_prestacao.py`) -- usados aqui
    só para CONFIRMAR EXISTÊNCIA do record id de Local já informado.

Posto é identificado por `posto_id` (Airtable record id) -- NUNCA
resolvido por nome livre. Um Field ID de 'Nome' para a tabela Locais
NÃO está confirmado em nenhum documento nem código deste repositório
até hoje; fabricar um aqui sem prova real violaria a disciplina já
estabelecida em todo este pacote (CLAUDE.md raiz §11, "nunca afirmar
sucesso sem ter testado" -- um Field ID errado silenciosamente nunca
encontraria nada e pareceria, incorretamente, "posto não identificado"
para sempre). A convenção já usada em todo o subsistema de alocação
(`eventos.py`, `captura.py`, `resolucao.py`) já trata posto como
`posto_id` opaco, nunca como nome -- este adapter só estende essa
mesma convenção até a fronteira de identificação.

NUNCA chamado com Airtable live nesta missão -- testado só com
`Mock()`/fake de leitor (mesma disciplina de todo o resto deste
pacote, ver `test_magnata_os_documental_alocacao_confirmacao_shadow_v1.py`)."""
from __future__ import annotations

from typing import Optional

from ..dominio import normalizar_cpf
from .airtable_leitura import LeitorAirtableSomenteLeitura
from .airtable_vinculos_prestacao import F_LOCAL_CLIENTE, TABLE_LOCAIS


class ColaboradorAmbiguoError(ValueError):
    """Mais de um colaborador cadastrado com o mesmo CPF -- nunca
    escolhe o primeiro; dado de cadastro duplicado é sempre reportado,
    nunca resolvido por adivinhação (mesma disciplina de
    `ClassificacaoCorrespondencia.AMBIGUOUS` em todo este pacote)."""


class ResolverIdentidadeAlocacaoAirtableShadow:
    """Resolve/confirma identidade real de colaborador (via CPF) e posto
    (via record id já conhecido) -- SOMENTE leitura, nunca escreve nada
    no Airtable, nunca decide data efetiva."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura) -> None:
        self._leitor = leitor

    def resolver_colaborador_id(self, cpf: str) -> Optional[str]:
        """CPF -> func_id, só quando exatamente 1 colaborador casa.
        Levanta `ColaboradorAmbiguoError` se mais de 1 casar -- nunca
        escolhe o primeiro."""
        alvo = normalizar_cpf(cpf)
        candidatos = [
            candidato for candidato in self._leitor.listar_funcionarios()
            if candidato.cpf and normalizar_cpf(candidato.cpf) == alvo and alvo
        ]
        if len(candidatos) > 1:
            raise ColaboradorAmbiguoError(
                f'{len(candidatos)} colaboradores cadastrados com o mesmo CPF')
        return candidatos[0].func_id if candidatos else None

    def confirmar_posto_existe(self, posto_id: str) -> bool:
        """Confirma que `posto_id` corresponde a um Local REAL e atual
        no Airtable -- nunca resolve por nome, só valida existência do
        record id já informado (ver docstring do módulo)."""
        registros = self._leitor.listar_registros(table_id=TABLE_LOCAIS, fields=[F_LOCAL_CLIENTE])
        return any(registro.get('id') == posto_id for registro in registros)
