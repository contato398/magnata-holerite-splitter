"""E2E de wiring real (missão "MERGE PR #108 + FECHAR BLOQUEIOS REAIS
DO CORREDOR LIVE V2 + REVISÃO ADVERSARIAL PRÉ-ENTREGA", §5/§6/§13/§16).

Prova que os 2 adapters reais novos desta missão --
`FonteClienteDiretoDocumentoAirtableShadow` (cliente_direto Extrato/
FGTS Guia, capacidade compartilhada) e `FonteEscopoClientesPor
InventarioAirtableShadow` (escopo histórico real de candidatos) --
compõem, SEM NENHUM AJUSTE, com o corredor já existente
(`resolucao_documento_prestacao.processar_documento_prestacao`,
`corredor_relacao_documental.resolver_relacao_e_avancar`). Nenhum
acesso Airtable real -- só `Mock()`/fakes locais, mesma disciplina do
resto da sessão.

Isso é o nível de "wiring" desta missão: prova de composição real,
testada -- nunca um orquestrador de produção novo (ausente hoje para
todo o corredor `classificacao/`, achado registrado no ADR desta
missão, fora de escopo criar aqui sem gate humano separado)."""
from unittest.mock import Mock

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
)
from magnata_os.classificacao.fonte_candidatos_relacao_documental_do_inventario import (
    FonteCandidatosRelacaoDocumentalDoInventario,
)
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.relacao_documental import TipoRelacaoDocumental
from magnata_os.classificacao.resolucao_documento_prestacao import (
    ContextoResolucaoDocumentoPrestacao,
    EstadoCorredorDocumentoPrestacao,
    processar_documento_prestacao,
)
from magnata_os.documental.importacao_lote.adapters.airtable_cliente_direto_documento import (
    FonteClienteDiretoDocumentoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
    F_FGTS_CLIENTE,
    FonteEscopoClientesPorInventarioAirtableShadow,
    TABLE_FGTS,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (
    F_EXT_CLIENTE,
    TABLE_EXTRATO,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoCliente
from magnata_os.classificacao.contratos import ReferenciaCanonica

_CNPJ_SKY = '11.222.333/0001-44'
_CANDIDATOS_CLIENTE = [
    CandidatoCliente(cliente_id='recCLI_SKY', cnpj=_CNPJ_SKY, nome_normalizado='EDIFICIO SKY TATUI'),
]


class _FonteInventarioFake:
    def __init__(self, itens_por_cliente):
        self._itens_por_cliente = itens_por_cliente

    def listar(self, cliente, competencia):
        return tuple(item for item in self._itens_por_cliente.get(cliente, ()) if item.competencia == competencia)


def _leitor_clientes():
    leitor = Mock()
    leitor.listar_clientes.return_value = _CANDIDATOS_CLIENTE
    return leitor


# --- E2E Extrato: texto real -> cliente_direto real -> corredor avança ---

def test_e2e_extrato_com_cnpj_no_texto_resolve_cliente_direto_e_avanca():
    fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(_leitor_clientes())
    texto = f'Extrato da Folha de Pagamento -- Julho/2026\nCompetência: 07/2026\nCNPJ: {_CNPJ_SKY}'

    cliente_direto = fonte_cliente_direto.resolver_cliente_direto(texto)
    assert cliente_direto == ReferenciaCanonica('CLIENTE', 'recCLI_SKY')

    resultado = processar_documento_prestacao(texto, ContextoResolucaoDocumentoPrestacao(
        documento_id='doc-extrato-1', hash_sha256='a' * 64,
        competencia_esperada=(2026, 7), cliente_direto=cliente_direto,
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    resolucao_cliente = next(
        r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.CLIENTE
    )
    assert resolucao_cliente.valores_confirmados == (ReferenciaCanonica('CLIENTE', 'recCLI_SKY'),)


def test_e2e_extrato_sem_cnpj_no_texto_nunca_inventa_cliente_nunca_avanca():
    fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(_leitor_clientes())
    texto = 'Extrato da Folha de Pagamento -- Julho/2026\nCompetência: 07/2026'

    cliente_direto = fonte_cliente_direto.resolver_cliente_direto(texto)
    assert cliente_direto is None

    resultado = processar_documento_prestacao(texto, ContextoResolucaoDocumentoPrestacao(
        documento_id='doc-extrato-2', hash_sha256='b' * 64,
        competencia_esperada=(2026, 7), cliente_direto=cliente_direto,
    ))
    # Sem cliente_direto, CLIENTE fica NAO_AVALIADA -- nunca inventado,
    # nunca avança automaticamente (Fase 16 do corredor, preservada).
    assert resultado.estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


# --- E2E FGTS Guia: MESMO adapter (capacidade compartilhada, §7 da missão) ---

def test_e2e_fgts_guia_com_cnpj_no_texto_resolve_cliente_direto_e_avanca():
    fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(_leitor_clientes())
    texto = f'Guia do FGTS Digital -- Total FGTS\nCompetência: 07/2026\nCNPJ: {_CNPJ_SKY}'

    cliente_direto = fonte_cliente_direto.resolver_cliente_direto(texto)
    assert cliente_direto == ReferenciaCanonica('CLIENTE', 'recCLI_SKY')

    resultado = processar_documento_prestacao(texto, ContextoResolucaoDocumentoPrestacao(
        documento_id='doc-fgts-1', hash_sha256='c' * 64,
        competencia_esperada=(2026, 7), cliente_direto=cliente_direto,
    ))
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_e2e_fgts_guia_sem_cnpj_no_texto_nunca_resolve():
    fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(_leitor_clientes())
    texto = 'Guia do FGTS Digital -- Total FGTS\nCompetência: 07/2026'
    assert fonte_cliente_direto.resolver_cliente_direto(texto) is None


# --- E2E escopo histórico real -> candidatos -> relação (§13/§16 da missão) ---

def test_e2e_escopo_historico_real_encontra_candidato_via_corredor_de_relacao():
    """`FonteEscopoClientesPorInventarioAirtableShadow` (evidência real
    de Airtable, nunca "ativos hoje") alimenta `FonteCandidatosRelacao
    DocumentalDoInventario`, que alimenta `resolver_relacao_e_avancar`
    -- sem NENHUM ajuste em qualquer uma das 3 peças, provando que a
    lacuna de "escopo fake" registrada no ADR anterior está fechada com
    evidência real."""
    from magnata_os.classificacao.corredor_relacao_documental import (
        ContextoRelacaoDocumentoPrestacao,
        resolver_relacao_e_avancar,
    )
    from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
    from magnata_os.classificacao.relacao_documental import DadosCorrelacaoDocumental

    leitor_escopo = Mock()
    leitor_escopo.listar_registros.side_effect = [
        [],  # TABLE_EXTRATO (1o na ordem de FonteEscopoClientesPorInventarioAirtableShadow)
        [{'id': 'recFGTS_HIST', 'fields': {F_FGTS_CLIENTE: ['recCLI_SKY']}}],  # TABLE_FGTS
    ]
    fonte_escopo = FonteEscopoClientesPorInventarioAirtableShadow(leitor_escopo)

    competencia_ref = ReferenciaCanonica('COMPETENCIA', '2026-06')  # competência documental SKY (-1)
    item_fgts = ItemInventarioPrestacao(
        documento_id='rel-fgts-real', tipo_documental='FGTS',
        cliente=ReferenciaCanonica('CLIENTE', 'recCLI_SKY'), competencia=competencia_ref,
    )
    fonte_candidatos = FonteCandidatosRelacaoDocumentalDoInventario(
        fonte_escopo_clientes=fonte_escopo,
        fonte_inventario=_FonteInventarioFake({ReferenciaCanonica('CLIENTE', 'recCLI_SKY'): (item_fgts,)}),
    )

    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-fgts-real-1', tipo_documental='Comprovante de Pagamento - FGTS',
        competencia=(2026, 6),
        dados_correlacao=DadosCorrelacaoDocumental(),
        fonte_candidatos=fonte_candidatos,
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.resolucao_relacao.candidatos_documento_a_id == ('rel-fgts-real',)
