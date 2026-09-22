"""Bootstrap TRANSITÓRIO de Contato Canônico de Colaborador V1 a partir
do Airtable -- único ponto deste repositório que lê o campo `WhatsApp`
de Funcionários do Airtable para popular `contato_colaborador_observado`
(migration 0004).

**Airtable NUNCA é consultado em runtime de resolução** -- mesma regra
pétrea de `bootstrap_identidade_colaborador_airtable.py`: este módulo
só alimenta a tabela, uma vez (ou a cada reconciliação explicitamente
disparada por um operador), nunca é chamado pela porta de runtime
(`contato_colaborador.resolver_contato_colaborador_para_ordem`, que só
conhece o repositório persistido).

**Nesta sessão: nunca executado contra Airtable real** -- autorização
explícita cobre só código + testes com fakes/mocks
(`FonteFuncionariosContatoParaBootstrap` é satisfeito por qualquer
objeto com `listar_funcionarios_contato()`, nunca só por um cliente
Airtable real).

Telefone bruto nunca sai deste módulo em claro além do necessário para
normalizar e cifrar: é lido de
`CandidatoFuncionarioContato.whatsapp_bruto` (novo, definido aqui --
`CandidatoFuncionario` de `importacao_lote/contratos.py` não carrega
contato, e este módulo não altera esse contrato compartilhado),
normalizado (`contato_colaborador.normalizar_numero_whatsapp_v1`,
reaproveitado sem alteração) e imediatamente cifrado
(`contato_colaborador.cifrar_valor_contato`) + reduzido a
`hash_auxiliar` (`contato_colaborador.calcular_hash_auxiliar_contato`)
-- o valor em claro nunca é persistido em
`ResultadoBootstrapContatoColaborador`.

**Chaves são parâmetros explícitos desta função** -- nunca lidas
daqui de `configuracao_contato_colaborador.versao_atual()` sozinho,
mesmo padrão de `bootstrap_identidade_colaborador_airtable.py` (permite
backfill sob uma versão nova antes de promover CURRENT)."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import List, Optional, Protocol, Tuple

from ...alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    ConflitoContatoColaborador,
    RegistroContatoColaborador,
    RepositorioContatoColaborador,
    calcular_hash_auxiliar_contato,
    cifrar_valor_contato,
    normalizar_numero_whatsapp_v1,
)


@dataclasses.dataclass(frozen=True)
class CandidatoFuncionarioContato:
    """Par (func_id, telefone bruto) vindo da fonte de bootstrap --
    definido aqui, isolado, para não alterar `CandidatoFuncionario`
    (`importacao_lote/contratos.py`, contrato compartilhado por outros
    fluxos que não carregam nem precisam de contato)."""

    func_id: str
    whatsapp_bruto: Optional[str]


class FonteFuncionariosContatoParaBootstrap(Protocol):
    """Porta neutra -- satisfeita por um leitor Airtable real (fora do
    escopo desta missão) ou por qualquer fake/mock de teste. Este
    módulo nunca importa Airtable diretamente -- só duck-typing contra
    esta assinatura mínima."""

    def listar_funcionarios_contato(self) -> List[CandidatoFuncionarioContato]: ...


@dataclasses.dataclass(frozen=True)
class ConflitoBootstrapContatoColaborador:
    """Um `func_id` cujo telefone já está registrado com um
    `hash_auxiliar` DIFERENTE (ou seja, telefone mudou) -- nunca
    resolvido automaticamente, sempre reportado para reconciliação
    humana (nenhum telefone em claro aqui, só os ids/hashes opacos em
    disputa)."""

    func_id_tentativa: str
    hash_auxiliar_existente: str


@dataclasses.dataclass(frozen=True)
class ResultadoBootstrapContatoColaborador:
    """Resumo sanitizado do bootstrap -- nenhum telefone em claro, só
    contagens e os ids/hashes opacos envolvidos em conflito."""

    processados: int
    criados: int
    ja_existentes: int
    ignorados_sem_whatsapp: int
    ignorados_invalidos: int
    conflitos: Tuple[ConflitoBootstrapContatoColaborador, ...] = ()


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


def executar_bootstrap_contato_colaborador_whatsapp(
    fonte_funcionarios: FonteFuncionariosContatoParaBootstrap,
    repositorio: RepositorioContatoColaborador,
    chave_fernet: bytes,
    chave_hmac: bytes,
    versao_chave: str,
    origem: str = 'bootstrap_airtable_funcionarios_contato',
    canal: str = CANAL_WHATSAPP,
    relogio=_relogio_padrao,
) -> ResultadoBootstrapContatoColaborador:
    """Itera `fonte_funcionarios.listar_funcionarios_contato()` UMA VEZ
    (nunca paginação/retry aqui -- responsabilidade de quem implementa
    `FonteFuncionariosContatoParaBootstrap`, mesma separação já usada em
    todo o pacote de adapters) e, para cada candidato com WhatsApp
    normalizável, registra (ou confirma idempotentemente, ou reporta
    conflito) o contato correspondente.

    Fail-closed por candidato, nunca aborta o bootstrap inteiro:
    - sem `whatsapp_bruto` -> `ignorados_sem_whatsapp` (nunca inventa);
    - `whatsapp_bruto` presente mas não normalizável -> `ignorados_
      invalidos` (nunca persiste um valor duvidoso);
    - telefone já registrado com hash diferente -> conflito reportado,
      nunca sobrescrito, nunca aborta o restante do bootstrap (mesma
      disciplina de tolerância a erro isolado já usada por
      `executar_bootstrap_identidade_colaborador_cpf`)."""
    if not chave_fernet:
        raise ValueError('chave_fernet nao pode ser vazia')
    if not chave_hmac:
        raise ValueError('chave_hmac nao pode ser vazia')
    if not (versao_chave or '').strip():
        raise ValueError('versao_chave deve ser texto nao vazio')

    processados = 0
    criados = 0
    ja_existentes = 0
    ignorados_sem_whatsapp = 0
    ignorados_invalidos = 0
    conflitos: List[ConflitoBootstrapContatoColaborador] = []

    for candidato in fonte_funcionarios.listar_funcionarios_contato():
        processados += 1
        if not candidato.whatsapp_bruto:
            ignorados_sem_whatsapp += 1
            continue

        numero_normalizado = normalizar_numero_whatsapp_v1(candidato.whatsapp_bruto)
        if numero_normalizado is None:
            ignorados_invalidos += 1
            continue

        valor_cifrado = cifrar_valor_contato(chave_fernet, numero_normalizado)
        hash_auxiliar = calcular_hash_auxiliar_contato(chave_hmac, numero_normalizado)
        agora = relogio()
        registro = RegistroContatoColaborador(
            colaborador_id=candidato.func_id,
            canal=canal,
            valor_cifrado=valor_cifrado,
            hash_auxiliar=hash_auxiliar,
            versao_chave=versao_chave,
            origem=origem,
            criado_em=agora,
            atualizado_em=agora,
        )
        try:
            _registro_persistido, criado_agora = repositorio.criar_ou_confirmar(registro)
        except ConflitoContatoColaborador as exc:
            conflitos.append(ConflitoBootstrapContatoColaborador(
                func_id_tentativa=candidato.func_id,
                hash_auxiliar_existente=exc.hash_auxiliar_existente,
            ))
            continue

        if criado_agora:
            criados += 1
        else:
            ja_existentes += 1

    return ResultadoBootstrapContatoColaborador(
        processados=processados, criados=criados, ja_existentes=ja_existentes,
        ignorados_sem_whatsapp=ignorados_sem_whatsapp, ignorados_invalidos=ignorados_invalidos,
        conflitos=tuple(conflitos),
    )
