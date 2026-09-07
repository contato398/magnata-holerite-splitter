"""Identidade Canônica de Colaborador V1 -- domínio puro.

Fecha a lacuna comprovada por auditoria (ULTRAPLAN "IDENTIDADE
CANÔNICA DE COLABORADOR V1"): não existia nenhuma capacidade
persistente, não-Airtable, que traduzisse um identificador OBSERVADO
(ex.: CPF extraído de um documento) para o `colaborador_id` opaco já
usado em todo o Magnata OS (`vinculo_trabalhista.colaborador_id`,
`ReferenciaCanonica('COLABORADOR', ...)` em `classificacao/`).

**Nenhuma dependência de Postgres/Airtable/Flask aqui** (mesma
disciplina de `magnata_os/CLAUDE.md`) -- só `hmac`/`hashlib` da stdlib
para a derivação do identificador protegido (função pura, recebe a
chave já pronta, nunca lê variável de ambiente sozinha -- isso é
responsabilidade de `configuracao_identidade_colaborador.py`).

**`colaborador_id` é LEGADO/TRANSICIONAL** (Opção A do ULTRAPLAN
aprovado): hoje é sempre o Airtable record id de Funcionários, nunca
uma identidade própria do Magnata OS. Este módulo trata esse valor como
opaco em todo lugar -- nunca assume nada sobre sua origem, para que uma
futura identidade Magnata própria (Opção B, fora de escopo) exija só um
mapeamento adicional, nunca reescrever este módulo.

**CPF nunca em claro.** `IdentidadeColaboradorObservada.identificador_
hash` é sempre o HMAC-SHA256 (hex) do valor normalizado -- SHA-256 puro
foi avaliado e reprovado no ULTRAPLAN aprovado (domínio pequeno de CPF,
suscetível a força bruta sem segredo). Nenhuma função aqui aceita nem
devolve o valor em claro do identificador.

Padrão de resolução reaproveitado, nunca reinventado: `ResolucaoDimensao`/
`EstadoResolucaoDimensao` (`classificacao/contratos.py`, dimensão
COLABORADOR) -- mesmo vocabulário já usado por `identificacao_
documental.py`/`ciclo_prestacao.py`. Nenhum estado novo, nenhum enum
paralelo.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol, Tuple

from magnata_os.classificacao.contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EvidenciaSanitizada,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)


def _exigir_texto(valor: str, nome_campo: str) -> None:
    if not (valor or '').strip():
        raise ValueError(f'{nome_campo} deve ser texto nao vazio')


@dataclasses.dataclass(frozen=True)
class IdentidadeColaboradorObservada:
    """Uma linha da tabela `identidade_colaborador_observada` (migration
    0003) -- imutável, mesma disciplina de `Documento`/`EventoHistorico`
    (Módulo 01)."""

    tipo_identificador: str
    identificador_hash: str
    colaborador_id: str
    origem: str
    versao_chave: str
    criado_em: datetime
    atualizado_em: datetime

    def __post_init__(self) -> None:
        _exigir_texto(self.tipo_identificador, 'tipo_identificador')
        _exigir_texto(self.identificador_hash, 'identificador_hash')
        _exigir_texto(self.colaborador_id, 'colaborador_id')
        _exigir_texto(self.origem, 'origem')
        _exigir_texto(self.versao_chave, 'versao_chave')


class ConflitoIdentidadeColaborador(Exception):
    """O MESMO identificador (tipo_identificador + identificador_hash)
    já está registrado para um `colaborador_id` DIFERENTE do que está
    sendo inserido -- nunca resolvido por sobrescrita silenciosa (mesmo
    princípio de "arquivo original é imutável", CLAUDE.md raiz §4, já
    aplicado a `documentos.hash_sha256`).

    Carrega os 2 ids opacos em disputa como atributos estruturados
    (nunca só no texto da mensagem) -- quem captura a exceção nunca
    precisa fazer parsing de string para saber quem conflitou."""

    def __init__(self, colaborador_id_existente: str, colaborador_id_tentativa: str) -> None:
        self.colaborador_id_existente = colaborador_id_existente
        self.colaborador_id_tentativa = colaborador_id_tentativa
        super().__init__(
            f'identificador ja registrado para colaborador_id={colaborador_id_existente!r}, '
            f'tentativa de registrar para colaborador_id={colaborador_id_tentativa!r}'
        )


def calcular_identificador_hash(chave_hmac: bytes, valor_normalizado: str) -> str:
    """HMAC-SHA256 (hex) do valor já normalizado, com a chave secreta já
    resolvida por quem chama (esta função nunca lê variável de ambiente
    nem decide qual versão de chave usar -- isso é
    `configuracao_identidade_colaborador.py`).

    Determinístico: o MESMO valor + a MESMA chave sempre produzem o
    MESMO hash -- é o que permite o lookup por igualdade no repositório
    (nunca comparação parcial/fuzzy). Chaves diferentes (rotação)
    produzem hashes diferentes para o mesmo valor -- por isso
    `versao_chave` nunca precisa fazer parte da chave primária da
    tabela (0003): o próprio hash já muda."""
    if not chave_hmac:
        raise ValueError('chave_hmac nao pode ser vazia')
    if not valor_normalizado:
        raise ValueError('valor_normalizado nao pode ser vazio')
    return hmac.new(chave_hmac, valor_normalizado.encode('utf-8'), hashlib.sha256).hexdigest()


class RepositorioIdentidadeColaborador(Protocol):
    """Contrato que qualquer adapter (memória, Postgres) precisa
    cumprir. `criar_se_ausente` é a ÚNICA forma de escrita -- garante
    que o mesmo (tipo_identificador, identificador_hash) nunca gera uma
    segunda linha, e que um conflito real (mesmo identificador, outro
    colaborador_id) é sempre reportado, nunca sobrescrito."""

    def buscar_por_identificador(
        self, tipo_identificador: str, identificador_hash: str,
    ) -> Optional[IdentidadeColaboradorObservada]: ...

    def criar_se_ausente(
        self, identidade: IdentidadeColaboradorObservada,
    ) -> Tuple[IdentidadeColaboradorObservada, bool]: ...

    def listar_todos(self) -> List[IdentidadeColaboradorObservada]: ...


class RepositorioIdentidadeColaboradorEmMemoria:
    """Implementação em memória -- para testes e para a fase de
    fundação desta missão (nenhum Postgres real conectado). Protegida
    por `threading.Lock` único, mesma disciplina de
    `RepositorioDocumentosEmMemoria` (Módulo 01): `criar_se_ausente` é
    atômica sob chamadas concorrentes."""

    def __init__(self) -> None:
        self._por_chave: Dict[Tuple[str, str], IdentidadeColaboradorObservada] = {}
        self._lock = threading.Lock()

    def buscar_por_identificador(
        self, tipo_identificador: str, identificador_hash: str,
    ) -> Optional[IdentidadeColaboradorObservada]:
        with self._lock:
            return self._por_chave.get((tipo_identificador, identificador_hash))

    def criar_se_ausente(
        self, identidade: IdentidadeColaboradorObservada,
    ) -> Tuple[IdentidadeColaboradorObservada, bool]:
        """Atômica: sob o mesmo lock, confere se já existe uma linha
        para esta chave e, se existir com `colaborador_id` DIFERENTE,
        levanta `ConflitoIdentidadeColaborador` -- nunca sobrescreve. Se
        já existir com o MESMO `colaborador_id` (reprocessamento
        idempotente do mesmo bootstrap), devolve a linha existente sem
        criar uma segunda. Retorna (identidade, criada_agora)."""
        chave = (identidade.tipo_identificador, identidade.identificador_hash)
        with self._lock:
            existente = self._por_chave.get(chave)
            if existente is not None:
                if existente.colaborador_id != identidade.colaborador_id:
                    raise ConflitoIdentidadeColaborador(
                        existente.colaborador_id, identidade.colaborador_id,
                    )
                return existente, False
            self._por_chave[chave] = identidade
            return identidade, True

    def listar_todos(self) -> List[IdentidadeColaboradorObservada]:
        with self._lock:
            return list(self._por_chave.values())


def _resolucao(
    estado: EstadoResolucaoDimensao,
    valores_confirmados: Tuple[ReferenciaCanonica, ...] = (),
    candidatos: Tuple[ReferenciaCanonica, ...] = (),
    metodo: str = 'resolver_identidade_colaborador',
) -> ResolucaoDimensao:
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.COLABORADOR,
        estado=estado,
        valores_confirmados=valores_confirmados,
        candidatos=candidatos,
        evidencias=(
            EvidenciaSanitizada(
                tipo_evidencia='IDENTIFICADOR_OBSERVADO_HASH',
                fonte='identidade_colaborador_observada',
                referencia_fonte='lookup_por_hash',
                metodo=metodo,
                forca=NivelConfianca.FORTE if estado == EstadoResolucaoDimensao.RESOLVIDA
                else NivelConfianca.INDETERMINADA,
            ),
        ),
        metodo=metodo,
        confianca=ConfiancaResolucao(
            NivelConfianca.FORTE if estado == EstadoResolucaoDimensao.RESOLVIDA
            else NivelConfianca.INDETERMINADA
        ),
    )


def resolver_identidade_colaborador(
    repositorio: RepositorioIdentidadeColaborador,
    tipo_identificador: str,
    identificador_hash: str,
) -> ResolucaoDimensao:
    """Porta de runtime única desta missão: dado um `identificador_hash`
    JÁ CALCULADO (nunca o valor em claro -- quem chama já normalizou e
    aplicou `calcular_identificador_hash` com a chave/versão vigente),
    devolve a resolução da dimensão COLABORADOR.

    Nunca conhece Airtable, HMAC, CPF, Holerite, Ponto, Gmail ou SKY --
    só consulta o repositório por hash exato e traduz o resultado para
    o vocabulário já existente (`ResolucaoDimensao`). Serve qualquer
    documento individualizado, qualquer `tipo_identificador` (CPF hoje,
    outro tipo futuro sem mudar esta função).

    RESOLVIDA: exatamente 1 linha encontrada para o hash.
    NAO_ENCONTRADA: nenhuma linha para o hash -- nunca inventa.
    (CONFLITO nunca nasce aqui: a unicidade de `identificador_hash` já
    é garantida pela chave primária da tabela -- um conflito de
    identidade só pode acontecer no MOMENTO DA ESCRITA, em
    `RepositorioIdentidadeColaborador.criar_se_ausente`, nunca na
    leitura.)"""
    _exigir_texto(tipo_identificador, 'tipo_identificador')
    _exigir_texto(identificador_hash, 'identificador_hash')

    encontrada = repositorio.buscar_por_identificador(tipo_identificador, identificador_hash)
    if encontrada is None:
        return _resolucao(EstadoResolucaoDimensao.NAO_ENCONTRADA)

    colaborador_ref = ReferenciaCanonica('COLABORADOR', encontrada.colaborador_id)
    return _resolucao(EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(colaborador_ref,))
