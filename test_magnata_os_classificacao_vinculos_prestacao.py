from pathlib import Path

import pytest

from magnata_os.classificacao.contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EvidenciaSanitizada,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.vinculos_prestacao import (
    FonteVinculosPrestacao,
    resolver_clientes_validado,
)


COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-07")
CLIENTE_A = ReferenciaCanonica("CLIENTE", "cliente-a")
CLIENTE_B = ReferenciaCanonica("CLIENTE", "cliente-b")


def _evidencia(origem: ReferenciaCanonica) -> EvidenciaSanitizada:
    return EvidenciaSanitizada(
        tipo_evidencia="VINCULO_CANONICO",
        fonte="fonte_teste",
        referencia_fonte=origem.entidade_id,
        metodo="vinculo_explicito",
        forca=NivelConfianca.FORTE,
        entidade_candidata=CLIENTE_A,
        motivo_sanitizado="vinculo_confirmado",
    )


def _resolucao(
    estado: EstadoResolucaoDimensao,
    origem: ReferenciaCanonica,
    confirmados: tuple[ReferenciaCanonica, ...] = (),
    candidatos: tuple[ReferenciaCanonica, ...] = (),
) -> ResolucaoDimensao:
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=estado,
        valores_confirmados=confirmados,
        candidatos=candidatos,
        evidencias=(_evidencia(origem),),
        metodo="vinculo_explicito",
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )


class FonteFake:
    def __init__(self, resultados: dict[str, ResolucaoDimensao]):
        self._resultados = dict(resultados)

    def resolver_clientes(
        self,
        origem: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        assert competencia == COMPETENCIA
        return self._resultados[origem.entidade_id]


def _resolver(origem: ReferenciaCanonica, resultado: ResolucaoDimensao):
    fonte: FonteVinculosPrestacao = FonteFake({origem.entidade_id: resultado})
    return resolver_clientes_validado(fonte, origem, COMPETENCIA)


@pytest.mark.parametrize("tipo_origem", ("COLABORADOR", "FUNCIONARIO"))
def test_colaborador_ou_funcionario_resolve_um_cliente(tipo_origem):
    origem = ReferenciaCanonica(tipo_origem, "pessoa-1")
    resultado = _resolver(
        origem,
        _resolucao(EstadoResolucaoDimensao.RESOLVIDA, origem, (CLIENTE_A,)),
    )
    assert resultado.valores_confirmados == (CLIENTE_A,)


def test_unidade_resolve_um_cliente():
    origem = ReferenciaCanonica("UNIDADE_POSTO", "unidade-1")
    resultado = _resolver(
        origem,
        _resolucao(EstadoResolucaoDimensao.RESOLVIDA, origem, (CLIENTE_A,)),
    )
    assert resultado.valores_confirmados == (CLIENTE_A,)


def test_nenhum_cliente_e_nao_encontrada():
    origem = ReferenciaCanonica("COLABORADOR", "pessoa-1")
    resultado = _resolver(
        origem,
        _resolucao(EstadoResolucaoDimensao.NAO_ENCONTRADA, origem),
    )
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_multiplos_clientes_validos_sao_ambiguos_sem_inferir_primeiro():
    origem = ReferenciaCanonica("FUNCIONARIO", "pessoa-1")
    resultado = _resolver(
        origem,
        _resolucao(
            EstadoResolucaoDimensao.AMBIGUA,
            origem,
            candidatos=(CLIENTE_A, CLIENTE_B),
        ),
    )
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA
    assert resultado.valores_confirmados == ()
    assert resultado.candidatos == (CLIENTE_A, CLIENTE_B)


def test_conflito_e_explicito():
    origem = ReferenciaCanonica("UNIDADE_POSTO", "unidade-1")
    resultado = _resolver(
        origem,
        _resolucao(
            EstadoResolucaoDimensao.CONFLITO,
            origem,
            candidatos=(CLIENTE_A, CLIENTE_B),
        ),
    )
    assert resultado.estado == EstadoResolucaoDimensao.CONFLITO
    assert resultado.valores_confirmados == ()


def test_dimensao_retornada_deve_ser_cliente():
    origem = ReferenciaCanonica("COLABORADOR", "pessoa-1")
    invalida = ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica("UNIDADE_POSTO", "unidade-1"),),
    )
    with pytest.raises(ValueError, match="dimensao CLIENTE"):
        _resolver(origem, invalida)


def test_evidencias_permanecem_sanitizadas():
    origem = ReferenciaCanonica("COLABORADOR", "pessoa-1")
    resultado = _resolver(
        origem,
        _resolucao(EstadoResolucaoDimensao.RESOLVIDA, origem, (CLIENTE_A,)),
    )
    evidencia = resultado.evidencias[0]
    assert evidencia.motivo_sanitizado == "vinculo_confirmado"
    assert all(
        not hasattr(evidencia, campo)
        for campo in ("nome", "cpf", "cnpj", "email", "payload", "conteudo_bruto")
    )


def test_modulo_nao_possui_dependencia_externa():
    caminho = Path("magnata_os/classificacao/vinculos_prestacao.py")
    conteudo = caminho.read_text(encoding="utf-8").lower()
    assert "app.py" not in conteudo
    assert "airtable" not in conteudo
    assert "requests" not in conteudo
    assert "http" not in conteudo
