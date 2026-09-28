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
- mesmo conteúdo (hash) repetido na fonte é deduplicado; exatamente um
  conteúdo: `LOCALIZADO`, com o documento selecionado.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Mapping, Protocol, Sequence, Tuple, TypeVar

from magnata_os.documental.modulo01.dominio import Documento


N = TypeVar("N")
N_contra = TypeVar("N_contra", contravariant=True)


class FonteCandidatos(Protocol[N_contra]):
    """Mesmo formato de `FonteCandidatosDocumentaisPorNecessidade`."""

    def candidatos_para(self, necessidade: N_contra) -> Tuple[Documento, ...]: ...


@dataclass(frozen=True)
class FonteNomeada(Generic[N]):
    """Fonte com identificador estável para o rastro da busca."""

    nome: str
    fonte: FonteCandidatos[N]

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

    unicos = _deduplicar_por_hash(encontrados)
    rastro = tuple(consultas)

    if falhas:
        if unicos:
            motivo = (
                f"candidato em '{fonte_com_candidatos}', mas fonte(s) de maior "
                f"prioridade falharam: {', '.join(falhas)}"
            )
        else:
            motivo = f"nenhum candidato e fonte(s) falharam: {', '.join(falhas)}"
        return ResultadoLocalizacao(DecisaoLocalizacao.INDETERMINADO, motivo, rastro, unicos)

    if not unicos:
        return ResultadoLocalizacao(
            DecisaoLocalizacao.NAO_LOCALIZADO,
            "nenhum candidato nas fontes consultadas",
            rastro,
            (),
        )

    if _conteudo_conflitante(unicos):
        return ResultadoLocalizacao(
            DecisaoLocalizacao.AMBIGUO,
            f"{len(unicos)} conteúdos distintos em '{fonte_com_candidatos}'",
            rastro,
            unicos,
        )

    return ResultadoLocalizacao(
        DecisaoLocalizacao.LOCALIZADO,
        f"conteúdo único em '{fonte_com_candidatos}'",
        rastro,
        unicos,
        documento_selecionado=unicos[0],
        fonte_selecionada=fonte_com_candidatos,
    )


def _deduplicar_por_hash(documentos: Tuple[Documento, ...]) -> Tuple[Documento, ...]:
    """Um documento por hash (mesmo conteúdo = mesmo documento), preferindo
    o menor `documento_id` para o resultado ser determinístico. Um
    `documento_id` com dois hashes cai em dois grupos e continua visível
    para `_conteudo_conflitante`."""
    por_hash: dict[str, Documento] = {}
    for documento in sorted(documentos, key=lambda d: (d.hash_sha256, d.documento_id)):
        por_hash.setdefault(documento.hash_sha256, documento)
    return tuple(sorted(por_hash.values(), key=lambda d: (d.documento_id, d.hash_sha256)))


def _conteudo_conflitante(unicos: Tuple[Documento, ...]) -> bool:
    return len({d.hash_sha256 for d in unicos}) > 1
