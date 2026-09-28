"""Capacidade central de localização documental do Magnata OS.

Implementa a seção "Busca documental" de `MAGNATA_OS_CENTRAL_FUNDACAO.md`:
consulta fontes em ordem de prioridade e devolve, além dos candidatos,
o RASTRO da busca -- onde procurou, o que encontrou em cada fonte e por
que um documento foi selecionado ou bloqueado.

Localizar é diferente de entregar (princípio 4 da Fundação) e também é
diferente de VALIDAR: esta capacidade nunca decide se um candidato
satisfaz a necessidade de negócio -- isso continua sendo papel do
corredor de classificação. Ela só responde "o que existe, onde, e com
que grau de certeza".

Genérica na necessidade: não conhece Prestação de Contas, tipo
documental, cliente ou colaborador. Quem chama passa a necessidade e as
fontes; cada fonte segue o mesmo formato de
`FonteCandidatosDocumentaisPorNecessidade` (`candidatos_para`), então
`FonteCandidatosDocumentoInventarioInterna` já serve como fonte, via
`FonteNomeada`.

Regras (fail-closed, nunca silenciosas):

- fontes consultadas na ordem recebida; a primeira que devolver
  candidato encerra a busca -- as seguintes ficam registradas como
  `NAO_CONSULTADA`, nunca omitidas;
- fonte que lança exceção fica `FALHOU` (só o tipo da exceção é
  registrado -- a mensagem pode carregar dado pessoal); a busca segue
  para a próxima fonte;
- se qualquer fonte de prioridade MAIOR que a do candidato falhou, o
  resultado é `INDETERMINADO`: a fonte que falhou poderia ter um
  documento diferente, então nunca se seleciona nada sobre essa lacuna;
- nenhum candidato em nenhuma fonte, com alguma falha: `INDETERMINADO`
  (nunca "não existe" quando não se conseguiu olhar tudo);
- nenhum candidato, todas as fontes consultadas sem falha:
  `NAO_LOCALIZADO` -- ausência NAS FONTES CONSULTADAS, nunca ausência
  global;
- candidatos com mais de um conteúdo distinto (hash), ou o mesmo
  `documento_id` com hashes diferentes: `AMBIGUO` -- vira exceção
  humana (Plano C), nunca escolha silenciosa;
- repetição exata (mesmo id e hash) é removida; registros distintos com
  o mesmo conteúdo (hash) continuam todos no resultado (cada um tem
  proveniência própria) mas contam como UM conteúdo; exatamente um
  conteúdo: `LOCALIZADO`, com o documento selecionado;
- desempate por versão: só quando a FONTE declara um critério de versão
  (`FonteNomeada.data_versao`). Conteúdos distintos viram `LOCALIZADO`
  pelo mais recente se TODOS têm data e o mais recente é único; sem data
  em algum candidato ou empate na data mais recente, continua `AMBIGUO`.
  Os candidatos substituídos continuam no resultado e na evidência.
  Critério em uso: e-mail -- "o segundo e-mail é o que vale" (regra de
  negócio confirmada pela operação), via `data_recebimento_email`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, Tuple, TypeVar

from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio_esteira import RepositorioLotes


ORIGEM_EMAIL = "email"  # mesmo valor de adapters.email_captura.ORIGEM_EMAIL


N = TypeVar("N")
N_contra = TypeVar("N_contra", contravariant=True)


class FonteCandidatos(Protocol[N_contra]):
    """Mesmo formato de `FonteCandidatosDocumentaisPorNecessidade`."""

    def candidatos_para(self, necessidade: N_contra) -> Tuple[Documento, ...]: ...


@dataclass(frozen=True)
class FonteNomeada(Generic[N]):
    """Fonte com identificador estável para o rastro da busca.

    `data_versao`, quando informado, declara que nesta fonte o documento
    mais recente substitui os anteriores e diz qual é a data de cada um
    (`None` = data desconhecida, que impede o desempate)."""

    nome: str
    fonte: FonteCandidatos[N]
    data_versao: Optional[Callable[[Documento], Optional[datetime]]] = None

    def __post_init__(self) -> None:
        if not self.nome or not self.nome.strip():
            raise ValueError("nome da fonte é obrigatório")


class StatusConsultaFonte(str, Enum):
    CONSULTADA = "CONSULTADA"
    FALHOU = "FALHOU"
    NAO_CONSULTADA = "NAO_CONSULTADA"


class DecisaoLocalizacao(str, Enum):
    LOCALIZADO = "LOCALIZADO"
    AMBIGUO = "AMBIGUO"
    NAO_LOCALIZADO = "NAO_LOCALIZADO"
    INDETERMINADO = "INDETERMINADO"


@dataclass(frozen=True)
class ConsultaFonte:
    """Uma linha do rastro: o que aconteceu com uma fonte."""

    fonte: str
    status: StatusConsultaFonte
    documento_ids: Tuple[str, ...] = ()
    erro_tipo: str | None = None


@dataclass(frozen=True)
class ResultadoLocalizacao:
    decisao: DecisaoLocalizacao
    motivo: str
    consultas: Tuple[ConsultaFonte, ...]
    candidatos: Tuple[Documento, ...]
    documento_selecionado: Documento | None = None
    fonte_selecionada: str | None = None

    def __post_init__(self) -> None:
        selecionado = self.documento_selecionado is not None
        if selecionado != (self.decisao is DecisaoLocalizacao.LOCALIZADO):
            raise ValueError("documento_selecionado existe se e somente se LOCALIZADO")

    @property
    def documentos_do_conteudo_selecionado(self) -> Tuple[Documento, ...]:
        """Todos os registros com o mesmo conteúdo (hash) do selecionado
        -- vazio se nada foi selecionado."""
        if self.documento_selecionado is None:
            return ()
        return tuple(
            d for d in self.candidatos if d.hash_sha256 == self.documento_selecionado.hash_sha256
        )

    @property
    def requer_acao_humana(self) -> bool:
        """AMBIGUO e INDETERMINADO nunca seguem automaticamente."""
        return self.decisao in (DecisaoLocalizacao.AMBIGUO, DecisaoLocalizacao.INDETERMINADO)

    def como_evidencia(self) -> Mapping[str, object]:
        """Registro auditável: só ids, hashes e nomes de fonte -- nunca
        nome de arquivo nem conteúdo (podem carregar dado pessoal)."""
        return {
            "decisao": self.decisao.value,
            "motivo": self.motivo,
            "fonte_selecionada": self.fonte_selecionada,
            "documento_selecionado": (
                self.documento_selecionado.documento_id if self.documento_selecionado else None
            ),
            "candidatos": [
                {"documento_id": d.documento_id, "hash_sha256": d.hash_sha256}
                for d in self.candidatos
            ],
            "consultas": [
                {
                    "fonte": c.fonte,
                    "status": c.status.value,
                    "documento_ids": list(c.documento_ids),
                    "erro_tipo": c.erro_tipo,
                }
                for c in self.consultas
            ],
        }


def localizar_documento(
    necessidade: N,
    fontes: Sequence[FonteNomeada[N]],
) -> ResultadoLocalizacao:
    """Busca `necessidade` nas `fontes`, em ordem de prioridade."""
    if not fontes:
        raise ValueError("ao menos 1 fonte é obrigatória")
    nomes = [f.nome for f in fontes]
    if len(set(nomes)) != len(nomes):
        raise ValueError("nomes de fonte devem ser únicos")

    consultas: list[ConsultaFonte] = []
    falhas: list[str] = []
    encontrados: Tuple[Documento, ...] = ()
    fonte_com_candidatos: str | None = None

    fonte_por_nome = {f.nome: f for f in fontes}

    for indice, fonte in enumerate(fontes):
        try:
            candidatos = tuple(fonte.fonte.candidatos_para(necessidade))
        except Exception as exc:  # a falha vira rastro, nunca some
            consultas.append(
                ConsultaFonte(fonte.nome, StatusConsultaFonte.FALHOU, erro_tipo=type(exc).__name__)
            )
            falhas.append(fonte.nome)
            continue
        consultas.append(
            ConsultaFonte(
                fonte.nome,
                StatusConsultaFonte.CONSULTADA,
                documento_ids=tuple(d.documento_id for d in candidatos),
            )
        )
        if candidatos:
            encontrados = candidatos
            fonte_com_candidatos = fonte.nome
            consultas.extend(
                ConsultaFonte(restante.nome, StatusConsultaFonte.NAO_CONSULTADA)
                for restante in fontes[indice + 1:]
            )
            break

    candidatos = _sem_repeticao(encontrados)
    rastro = tuple(consultas)

    if falhas:
        if candidatos:
            motivo = (
                f"candidato em '{fonte_com_candidatos}', mas fonte(s) de maior "
                f"prioridade falharam: {', '.join(falhas)}"
            )
        else:
            motivo = f"nenhum candidato e fonte(s) falharam: {', '.join(falhas)}"
        return ResultadoLocalizacao(DecisaoLocalizacao.INDETERMINADO, motivo, rastro, candidatos)

    if not candidatos:
        return ResultadoLocalizacao(
            DecisaoLocalizacao.NAO_LOCALIZADO,
            "nenhum candidato nas fontes consultadas",
            rastro,
            (),
        )

    por_hash = _agrupar_por_hash(candidatos)
    if len(por_hash) == 1:
        return ResultadoLocalizacao(
            DecisaoLocalizacao.LOCALIZADO,
            f"conteúdo único em '{fonte_com_candidatos}'",
            rastro,
            candidatos,
            documento_selecionado=candidatos[0],
            fonte_selecionada=fonte_com_candidatos,
        )

    motivo = f"{len(por_hash)} conteúdos distintos em '{fonte_com_candidatos}'"
    data_versao = fonte_por_nome[fonte_com_candidatos].data_versao
    if data_versao is None:
        return ResultadoLocalizacao(DecisaoLocalizacao.AMBIGUO, motivo, rastro, candidatos)

    hash_mais_recente, motivo_desempate = _desempatar_por_versao(por_hash, data_versao)
    if hash_mais_recente is None:
        return ResultadoLocalizacao(
            DecisaoLocalizacao.AMBIGUO, f"{motivo}; {motivo_desempate}", rastro, candidatos
        )
    return ResultadoLocalizacao(
        DecisaoLocalizacao.LOCALIZADO,
        f"{motivo}; {motivo_desempate}",
        rastro,
        candidatos,
        documento_selecionado=por_hash[hash_mais_recente][0],
        fonte_selecionada=fonte_com_candidatos,
    )


def _sem_repeticao(documentos: Tuple[Documento, ...]) -> Tuple[Documento, ...]:
    """Remove só a repetição EXATA (mesmo `documento_id` e mesmo hash).
    Registros distintos com o mesmo conteúdo continuam todos presentes:
    cada um tem proveniência própria, que quem consome precisa preservar.
    Ordem determinística por (`documento_id`, hash)."""
    vistos: dict[tuple[str, str], Documento] = {}
    for documento in documentos:
        vistos.setdefault((documento.documento_id, documento.hash_sha256), documento)
    return tuple(vistos[chave] for chave in sorted(vistos))


def _agrupar_por_hash(candidatos: Tuple[Documento, ...]) -> dict[str, Tuple[Documento, ...]]:
    """Mesmo hash = mesmo conteúdo (ex.: o mesmo arquivo baixado várias
    vezes). Mais de um grupo = conteúdos distintos; um `documento_id`
    com dois hashes cai em dois grupos."""
    grupos: dict[str, list[Documento]] = {}
    for documento in candidatos:
        grupos.setdefault(documento.hash_sha256, []).append(documento)
    return {h: tuple(docs) for h, docs in grupos.items()}


def _desempatar_por_versao(
    por_hash: Mapping[str, Tuple[Documento, ...]],
    data_versao: Callable[[Documento], Optional[datetime]],
) -> Tuple[Optional[str], str]:
    """Data de um conteúdo = a mais recente entre seus registros; qualquer
    registro sem data impede o desempate (nunca se presume a ordem)."""
    datas: dict[str, datetime] = {}
    sem_data: list[str] = []
    for hash_sha256, documentos in por_hash.items():
        datas_do_conteudo = [data_versao(d) for d in documentos]
        sem_data.extend(d.documento_id for d, data in zip(documentos, datas_do_conteudo) if data is None)
        if all(data is not None for data in datas_do_conteudo):
            datas[hash_sha256] = max(datas_do_conteudo)
    if sem_data:
        return None, f"desempate por versão impossível: sem data em {', '.join(sorted(sem_data))}"
    maior = max(datas.values())
    no_topo = [h for h, data in datas.items() if data == maior]
    if len(no_topo) > 1:
        return None, "desempate por versão impossível: mesma data mais recente"
    return no_topo[0], f"mais recente vale: {por_hash[no_topo[0]][0].documento_id}"


def data_recebimento_email(
    repositorio_lotes: RepositorioLotes,
) -> Callable[[Documento], Optional[datetime]]:
    """Critério de versão para fontes de e-mail: a data em que o E-MAIL
    chegou (`recebido_em_origem`, gravado no lote pela captura).

    Nunca usa `Documento.recebido_em`: esse é o horário em que o sistema
    registrou o arquivo, e uma captura de backlog pode registrar e-mails
    antigos depois dos novos. Documento sem lote, lote que não é de
    e-mail ou data ausente/inválida devolvem `None` (sem desempate)."""

    def _data(documento: Documento) -> Optional[datetime]:
        if not documento.lote_id:
            return None
        lote = repositorio_lotes.buscar_por_id(documento.lote_id)
        if lote is None or lote.origem != ORIGEM_EMAIL:
            return None
        valor = lote.metadados.get("recebido_em_origem")
        if not isinstance(valor, str):
            return None
        try:
            data = datetime.fromisoformat(valor)
        except ValueError:
            return None
        # Data sem fuso não é comparável com data com fuso: sem desempate.
        return data if data.tzinfo is not None else None

    return _data
