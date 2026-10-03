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


@dataclasses.dataclass(frozen=True)
class ResultadoSimulacaoBootstrapContatoColaborador:
    """Resumo de uma simulação (dry-run) -- mesma sanitização de
    `ResultadoBootstrapContatoColaborador` (nenhum telefone em claro),
    mas produzido SEM nenhuma chamada a `repositorio.criar_ou_confirmar`
    (só leitura: `buscar_por_colaborador`/`listar_todos`). Pensado para
    ser o relatório que precede qualquer execução real contra
    Airtable/Postgres de produção (CLAUDE.md raiz §6/§12-I): contagem de
    origem e destino, duplicidade na própria origem, inválidos, quantos
    seriam inserts, quantos ficariam bloqueados por já existirem com
    telefone diferente (candidatos a UPDATE -- nunca automático, mesma
    regra de `ConflitoContatoColaborador`), e o comando exato de
    rollback para a execução real correspondente."""

    total_origem: int
    total_destino_antes: int
    duplicados_na_origem: int
    ignorados_sem_whatsapp: int
    ignorados_invalidos: int
    seriam_criados: int
    ja_existentes_idempotente: int
    atualizacoes_bloqueadas: Tuple[ConflitoBootstrapContatoColaborador, ...]
    plano_rollback: str


def montar_plano_rollback_bootstrap(origem: str) -> str:
    """Comando de rollback determinístico para desfazer uma execução
    real marcada com `origem` -- toda linha escrita por
    `executar_bootstrap_contato_colaborador_whatsapp` carrega essa
    `origem` (ver assinatura padrão abaixo), então o DELETE é sempre
    exato (nunca apaga linha de outra execução/origem). Mesmo texto já
    documentado manualmente em `scripts/bootstrap_contato_colaborador_
    whatsapp_cli.py` -- esta função é a única fonte, para o CLI e o
    relatório de simulação nunca divergirem."""
    _exigir_texto_local(origem, 'origem')
    origem_escapada = origem.replace("'", "''")
    return (
        "DELETE FROM contato_colaborador_observado "
        f"WHERE origem = '{origem_escapada}'"
    )


def _exigir_texto_local(valor: str, nome_campo: str) -> None:
    if not (valor or '').strip():
        raise ValueError(f'{nome_campo} deve ser texto nao vazio')


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


def simular_bootstrap_contato_colaborador_whatsapp(
    fonte_funcionarios: FonteFuncionariosContatoParaBootstrap,
    repositorio: RepositorioContatoColaborador,
    chave_hmac: bytes,
    origem: str = 'bootstrap_airtable_funcionarios_contato',
    canal: str = CANAL_WHATSAPP,
) -> ResultadoSimulacaoBootstrapContatoColaborador:
    """Dry-run de `executar_bootstrap_contato_colaborador_whatsapp` --
    MESMA classificação por candidato, só que NUNCA chama
    `repositorio.criar_ou_confirmar` (nenhuma escrita, em nenhuma
    hipótese): só `buscar_por_colaborador` e `listar_todos`, ambos
    leitura. Não precisa de `chave_fernet` nem de `relogio` -- não cifra
    nem persiste nada, só calcula o `hash_auxiliar` (determinístico, sem
    nonce) para comparar contra o que já existe.

    Pensado para produzir, ANTES de qualquer execução real contra
    Airtable/Postgres de produção (CLAUDE.md raiz §6/§12-I), exatamente
    as contagens exigidas por uma autorização de fase: origem vs.
    destino, duplicidade na própria origem (mesmo `func_id` duas vezes
    na mesma leitura -- só a primeira ocorrência é avaliada, mesma
    disciplina de idempotência de `executar_...`), inválidos, quantos
    seriam INSERTs (`seriam_criados`), quantos já existem de forma
    idempotente (`ja_existentes_idempotente`), e quantos ficariam
    bloqueados como possível UPDATE -- telefone diferente do já
    persistido, que esta arquitetura nunca sobrescreve automaticamente
    (`atualizacoes_bloqueadas`, mesma semântica de
    `ConflitoBootstrapContatoColaborador` -- sempre exige reconciliação
    humana, nunca é resolvido aqui)."""
    if not chave_hmac:
        raise ValueError('chave_hmac nao pode ser vazia')

    candidatos = list(fonte_funcionarios.listar_funcionarios_contato())
    total_origem = len(candidatos)

    func_ids_vistos: set = set()
    duplicados_na_origem = 0
    ignorados_sem_whatsapp = 0
    ignorados_invalidos = 0
    seriam_criados = 0
    ja_existentes_idempotente = 0
    atualizacoes_bloqueadas: List[ConflitoBootstrapContatoColaborador] = []

    for candidato in candidatos:
        if candidato.func_id in func_ids_vistos:
            duplicados_na_origem += 1
            continue
        func_ids_vistos.add(candidato.func_id)

        if not candidato.whatsapp_bruto:
            ignorados_sem_whatsapp += 1
            continue

        numero_normalizado = normalizar_numero_whatsapp_v1(candidato.whatsapp_bruto)
        if numero_normalizado is None:
            ignorados_invalidos += 1
            continue

        hash_auxiliar = calcular_hash_auxiliar_contato(chave_hmac, numero_normalizado)
        existente = repositorio.buscar_por_colaborador(candidato.func_id, canal)
        if existente is None:
            seriam_criados += 1
        elif existente.hash_auxiliar == hash_auxiliar:
            ja_existentes_idempotente += 1
        else:
            atualizacoes_bloqueadas.append(ConflitoBootstrapContatoColaborador(
                func_id_tentativa=candidato.func_id,
                hash_auxiliar_existente=existente.hash_auxiliar,
            ))

    return ResultadoSimulacaoBootstrapContatoColaborador(
        total_origem=total_origem,
        total_destino_antes=len(repositorio.listar_todos()),
        duplicados_na_origem=duplicados_na_origem,
        ignorados_sem_whatsapp=ignorados_sem_whatsapp,
        ignorados_invalidos=ignorados_invalidos,
        seriam_criados=seriam_criados,
        ja_existentes_idempotente=ja_existentes_idempotente,
        atualizacoes_bloqueadas=tuple(atualizacoes_bloqueadas),
        plano_rollback=montar_plano_rollback_bootstrap(origem),
    )
