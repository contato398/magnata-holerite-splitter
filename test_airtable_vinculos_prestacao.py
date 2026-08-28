from pathlib import Path

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
)
from magnata_os.classificacao.vinculos_prestacao import (
    FonteVinculosPrestacao,
    resolver_clientes_validado,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_LOCAIS,
    FonteVinculosPrestacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import TABLE_FUNC


COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-07")


class LeitorFake:
    def __init__(self, funcionarios=(), locais=()):
        self._funcionarios = list(funcionarios)
        self._locais = list(locais)
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._funcionarios if table_id == TABLE_FUNC else self._locais


def _resolver(leitor, origem):
    fonte: FonteVinculosPrestacao = FonteVinculosPrestacaoAirtableShadow(leitor)
    return resolver_clientes_validado(fonte, origem, COMPETENCIA)


def test_funcionario_com_vinculo_unico_e_resolvido():
    leitor = LeitorFake(
        funcionarios=({"id": "func-1", "fields": {F_FUNC_LOCAIS: ["local-1"]}},),
        locais=({"id": "local-1", "fields": {F_LOCAL_CLIENTE: ["cliente-1"]}},),
    )
    resultado = _resolver(leitor, ReferenciaCanonica("FUNCIONARIO", "func-1"))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (
        ReferenciaCanonica("CLIENTE", "cliente-1"),
    )
    assert tuple(chamada[0] for chamada in leitor.chamadas) == (
        TABLE_FUNC,
        TABLE_LOCAIS,
    )


def test_unidade_com_cliente_unico_e_resolvida():
    leitor = LeitorFake(
        locais=({"id": "local-1", "fields": {F_LOCAL_CLIENTE: ["cliente-1"]}},)
    )
    resultado = _resolver(
        leitor, ReferenciaCanonica("UNIDADE_POSTO", "local-1")
    )
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.dimensao == DimensaoResolucao.CLIENTE
    assert tuple(chamada[0] for chamada in leitor.chamadas) == (TABLE_LOCAIS,)


def test_sem_vinculo_e_nao_encontrada():
    leitor = LeitorFake(
        funcionarios=({"id": "func-1", "fields": {F_FUNC_LOCAIS: []}},)
    )
    resultado = _resolver(leitor, ReferenciaCanonica("COLABORADOR", "func-1"))
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.valores_confirmados == ()
    assert resultado.candidatos == ()


def test_dois_clientes_sao_ambiguos_sem_escolher_primeiro():
    leitor = LeitorFake(
        locais=(
            {
                "id": "local-1",
                "fields": {F_LOCAL_CLIENTE: ["cliente-b", "cliente-a"]},
            },
        )
    )
    resultado = _resolver(
        leitor, ReferenciaCanonica("UNIDADE_POSTO", "local-1")
    )
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA
    assert resultado.valores_confirmados == ()
    assert resultado.candidatos == (
        ReferenciaCanonica("CLIENTE", "cliente-a"),
        ReferenciaCanonica("CLIENTE", "cliente-b"),
    )


def test_saida_e_validada_pelo_contrato_neutro():
    leitor = LeitorFake(
        locais=({"id": "local-1", "fields": {F_LOCAL_CLIENTE: ["cliente-1"]}},)
    )
    resultado = _resolver(
        leitor, ReferenciaCanonica("UNIDADE_POSTO", "local-1")
    )
    assert resultado.dimensao == DimensaoResolucao.CLIENTE


def test_adapter_usa_somente_superficie_read_only():
    caminho = Path(
        "magnata_os/documental/importacao_lote/adapters/airtable_vinculos_prestacao.py"
    )
    conteudo = caminho.read_text(encoding="utf-8").lower()
    assert "listar_registros" in conteudo
    assert all(termo not in conteudo for termo in ("requests.post", "patch(", "delete("))


def test_resolucao_nao_expoe_pii_ou_payload():
    leitor = LeitorFake(
        locais=({"id": "local-1", "fields": {F_LOCAL_CLIENTE: ["cliente-1"]}},)
    )
    resultado = _resolver(
        leitor, ReferenciaCanonica("UNIDADE_POSTO", "local-1")
    )
    representacao = repr(resultado).lower()
    assert all(
        termo not in representacao
        for termo in ("nome", "cpf", "cnpj", "email", "payload", "conteudo_bruto")
    )
