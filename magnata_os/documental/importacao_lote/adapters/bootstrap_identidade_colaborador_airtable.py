"""Bootstrap TRANSITÓRIO de Identidade Canônica de Colaborador V1 a
partir do Airtable -- único ponto deste repositório que lê CPF de
Funcionários do Airtable para popular
`identidade_colaborador_observada` (migration 0003).

**Airtable NUNCA é consultado em runtime de resolução** -- essa regra
pétrea do ULTRAPLAN aprovado é estrutural aqui: este módulo só
alimenta a tabela, uma vez (ou a cada rotação/reconciliação
explicitamente disparada por um operador), nunca é chamado pela porta
de runtime (`identidade_colaborador.resolver_identidade_colaborador`,
que só conhece o repositório persistido).

**Nesta sessão: nunca executado contra Airtable real** -- autorização
explícita cobre só código + testes com fakes/mocks (`FonteFuncionarios
ParaBootstrap` é satisfeito por qualquer objeto com
`listar_funcionarios()`, nunca só por `LeitorAirtableSomenteLeitura`
real).

CPF nunca sai deste módulo em claro: é lido de
`CandidatoFuncionario.cpf` (já existente,
`importacao_lote/contratos.py`), normalizado
(`importacao_lote/dominio.normalizar_cpf`, reaproveitado sem
alteração) e imediatamente transformado em HMAC
(`identidade_colaborador.calcular_identificador_hash`) -- nunca
persistido, nunca logado, nunca em `ResultadoBootstrapIdentidade
Colaborador`.

**Rotação:** `versao_chave`/`chave_hmac` são parâmetros explícitos
desta função -- nunca lidos daqui de `configuracao_identidade_
colaborador.versao_atual()` sozinho. Isso é o que permite "backfill da
nova versão antes de promover CURRENT": um operador chama este
bootstrap passando a chave/versão NOVA (via `configuracao_identidade_
colaborador.obter_chave_para_versao('v2')`, por exemplo), confirma o
resultado, e só DEPOIS promove a variável de ambiente de versão atual
-- este módulo nunca decide sozinho qual versão é "a atual"."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import List, Protocol, Tuple

from ...alocacao.identidade_colaborador import (
    ConflitoIdentidadeColaborador,
    IdentidadeColaboradorObservada,
    RepositorioIdentidadeColaborador,
    calcular_identificador_hash,
)
from ..contratos import CandidatoFuncionario
from ..dominio import normalizar_cpf

TIPO_IDENTIFICADOR_CPF = 'CPF'


class FonteFuncionariosParaBootstrap(Protocol):
    """Porta neutra -- satisfeita por `LeitorAirtableSomenteLeitura.
    listar_funcionarios()` (já existente, nunca alterado) ou por
    qualquer fake/mock de teste. Este módulo nunca importa Airtable
    diretamente -- só duck-typing contra esta assinatura mínima."""

    def listar_funcionarios(self) -> List[CandidatoFuncionario]: ...


@dataclasses.dataclass(frozen=True)
class ConflitoBootstrapIdentidadeColaborador:
    """Um `func_id` cujo CPF já está registrado para OUTRO
    colaborador_id -- nunca resolvido automaticamente, sempre reportado
    para revisão humana (nenhum CPF em claro aqui, só os 2 ids em
    disputa)."""

    func_id_tentativa: str
    colaborador_id_ja_registrado: str


@dataclasses.dataclass(frozen=True)
class ResultadoBootstrapIdentidadeColaborador:
    """Resumo sanitizado do bootstrap -- nenhum CPF, nenhum nome, só
    contagens e os ids opacos envolvidos em conflito."""

    processados: int
    criados: int
    ja_existentes: int
    ignorados_sem_cpf: int
    conflitos: Tuple[ConflitoBootstrapIdentidadeColaborador, ...] = ()


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


def executar_bootstrap_identidade_colaborador_cpf(
    fonte_funcionarios: FonteFuncionariosParaBootstrap,
    repositorio: RepositorioIdentidadeColaborador,
    chave_hmac: bytes,
    versao_chave: str,
    origem: str = 'bootstrap_airtable_funcionarios',
    relogio=_relogio_padrao,
) -> ResultadoBootstrapIdentidadeColaborador:
    """Itera `fonte_funcionarios.listar_funcionarios()` UMA VEZ (nunca
    paginação/retry aqui -- isso é responsabilidade de quem implementa
    `FonteFuncionariosParaBootstrap`, mesma separação já usada em todo
    o pacote de adapters) e, para cada `CandidatoFuncionario` com CPF
    preenchido, registra (ou confirma idempotentemente, ou reporta
    conflito) a identidade correspondente.

    Nunca aborta no primeiro conflito -- um `func_id` com problema não
    impede o restante do bootstrap (mesma disciplina de tolerância a
    erro isolado já usada por `ServicoCriacaoLote._processar_um_
    arquivo`)."""
    if not chave_hmac:
        raise ValueError('chave_hmac nao pode ser vazia')
    if not (versao_chave or '').strip():
        raise ValueError('versao_chave deve ser texto nao vazio')

    processados = 0
    criados = 0
    ja_existentes = 0
    ignorados_sem_cpf = 0
    conflitos: List[ConflitoBootstrapIdentidadeColaborador] = []

    for candidato in fonte_funcionarios.listar_funcionarios():
        processados += 1
        cpf_normalizado = normalizar_cpf(candidato.cpf) if candidato.cpf else ''
        if not cpf_normalizado:
            ignorados_sem_cpf += 1
            continue

        identificador_hash = calcular_identificador_hash(chave_hmac, cpf_normalizado)
        agora = relogio()
        identidade = IdentidadeColaboradorObservada(
            tipo_identificador=TIPO_IDENTIFICADOR_CPF,
            identificador_hash=identificador_hash,
            colaborador_id=candidato.func_id,
            origem=origem,
            versao_chave=versao_chave,
            criado_em=agora,
            atualizado_em=agora,
        )
        try:
            _identidade_persistida, criada_agora = repositorio.criar_se_ausente(identidade)
        except ConflitoIdentidadeColaborador as exc:
            conflitos.append(ConflitoBootstrapIdentidadeColaborador(
                func_id_tentativa=candidato.func_id,
                colaborador_id_ja_registrado=exc.colaborador_id_existente,
            ))
            continue

        if criada_agora:
            criados += 1
        else:
            ja_existentes += 1

    return ResultadoBootstrapIdentidadeColaborador(
        processados=processados, criados=criados, ja_existentes=ja_existentes,
        ignorados_sem_cpf=ignorados_sem_cpf, conflitos=tuple(conflitos),
    )
