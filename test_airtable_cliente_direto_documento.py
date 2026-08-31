"""Testes de `airtable_cliente_direto_documento.py` (missão "MERGE PR
#108 + FECHAR BLOQUEIOS REAIS DO CORREDOR LIVE V2"). Casos A-H mapeados
1:1 aos §17 (Extrato) e §18 (FGTS Guia) da missão -- capacidade
COMPARTILHADA (§7): um único adapter/Protocol serve as 2 famílias,
provado abaixo com fixtures de Extrato e de Guia FGTS.

Nenhum acesso Airtable real -- só `Mock()` local, mesmo padrão de
`test_airtable_inventario_prestacao.py`/`test_airtable_unidade_posto_
prestacao.py`."""
from unittest.mock import Mock

import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.adapters.airtable_cliente_direto_documento import (
    FonteClienteDiretoDocumentoAirtableShadow,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoCliente

_CLIENTE_A_CNPJ = '11.222.333/0001-44'
_CLIENTE_B_CNPJ = '55.666.777/0001-88'
_CNPJ_DESCONHECIDO = '99.999.999/0001-99'

_CANDIDATOS = [
    CandidatoCliente(cliente_id='recCLIENTE_A', cnpj=_CLIENTE_A_CNPJ, nome_normalizado='CLIENTE A LTDA'),
    CandidatoCliente(cliente_id='recCLIENTE_B', cnpj=_CLIENTE_B_CNPJ, nome_normalizado='CLIENTE B LTDA'),
]


def _fonte(candidatos=_CANDIDATOS):
    leitor = Mock()
    leitor.listar_clientes.return_value = candidatos
    return FonteClienteDiretoDocumentoAirtableShadow(leitor), leitor


# --- Extrato (§17 da missão) ---

def test_caso_a_extrato_com_cnpj_comprovado_resolve_cliente_direto():
    fonte, _ = _fonte()
    texto = f'EXTRATO MENSAL\nTomador: Cliente A Ltda\nCNPJ: {_CLIENTE_A_CNPJ}\n'
    resultado = fonte.resolver_cliente_direto(texto)
    assert resultado == ReferenciaCanonica('CLIENTE', 'recCLIENTE_A')


def test_caso_b_extrato_sem_cnpj_no_texto_nunca_inventa():
    fonte, _ = _fonte()
    texto = 'EXTRATO MENSAL\nsem nenhum identificador estruturado aqui\n'
    assert fonte.resolver_cliente_direto(texto) is None


def test_caso_c_extrato_historico_com_cnpj_comprovado_resolve_igual():
    """A resolução nunca depende de competência/ciclo -- é evidência
    intrínseca do documento (CNPJ no texto), então funciona idêntico
    para um documento de competência histórica (nenhum acoplamento
    temporal aqui -- exatamente para nunca reabrir a MESMA confusão já
    corrigida em UNIDADE_POSTO/EscopoClientesFixo/EscopoClientesAtivos
    DoCiclo nesta sessão)."""
    fonte, _ = _fonte()
    texto = f'EXTRATO MENSAL - COMPETÊNCIA 06/2025\nCNPJ: {_CLIENTE_A_CNPJ}\n'
    resultado = fonte.resolver_cliente_direto(texto)
    assert resultado == ReferenciaCanonica('CLIENTE', 'recCLIENTE_A')


def test_caso_d_label_ou_tipo_documental_sozinho_nunca_resolve():
    """"Este tipo normalmente pertence a X" nunca é evidência (§4 da
    missão) -- um texto que só contém o RÓTULO do tipo documental,
    nenhum CNPJ, nunca resolve, mesmo que o nome do cliente apareça
    livre no texto (nome de texto integral NUNCA é evidência aceita,
    ver docstring do módulo)."""
    fonte, _ = _fonte()
    texto = 'EXTRATO MENSAL\nCliente A Ltda aparece aqui só como texto solto, sem CNPJ.\n'
    assert fonte.resolver_cliente_direto(texto) is None


def test_cnpjs_de_2_clientes_diferentes_no_mesmo_texto_nunca_resolve():
    fonte, _ = _fonte()
    texto = f'CNPJ: {_CLIENTE_A_CNPJ}\nCNPJ: {_CLIENTE_B_CNPJ}\n'
    assert fonte.resolver_cliente_direto(texto) is None


def test_cnpj_desconhecido_no_cadastro_nunca_resolve():
    fonte, _ = _fonte()
    texto = f'CNPJ: {_CNPJ_DESCONHECIDO}\n'
    assert fonte.resolver_cliente_direto(texto) is None


# --- FGTS Guia (§18 da missão -- MESMO adapter, capacidade compartilhada) ---

def test_caso_e_guia_fgts_com_cnpj_comprovado_resolve_cliente_a():
    fonte, _ = _fonte()
    texto = f'GUIA FGTS DIGITAL\nEmpregador CNPJ: {_CLIENTE_A_CNPJ}\nCompetência: 07/2026\n'
    resultado = fonte.resolver_cliente_direto(texto)
    assert resultado == ReferenciaCanonica('CLIENTE', 'recCLIENTE_A')


def test_caso_f_guia_fgts_sem_evidencia_de_cliente_nunca_resolve():
    fonte, _ = _fonte()
    texto = 'GUIA FGTS DIGITAL\nsem CNPJ legível neste texto\n'
    assert fonte.resolver_cliente_direto(texto) is None


def test_caso_h_resultado_e_sempre_no_maximo_1_cliente_nunca_broadcast():
    """Estrutural, não só comportamental: o tipo de retorno é
    `Optional[ReferenciaCanonica]` -- nunca uma coleção -- tornando
    broadcast estruturalmente impossível para este contrato."""
    import inspect

    from magnata_os.classificacao.fonte_cliente_direto_documento import FonteClienteDiretoDocumento

    assinatura = inspect.signature(FonteClienteDiretoDocumento.resolver_cliente_direto)
    assert 'Tuple' not in str(assinatura.return_annotation)
    assert 'List' not in str(assinatura.return_annotation)


def test_reusa_leitor_listar_clientes_nenhuma_tabela_nova():
    fonte, leitor = _fonte()
    fonte.resolver_cliente_direto(f'CNPJ: {_CLIENTE_A_CNPJ}')
    leitor.listar_clientes.assert_called_once_with()


# --- cnpj_excluido (achado da revisão adversarial, checkpoint pré-merge #109) ---

def test_cnpj_excluido_evita_conflict_desnecessario_quando_cadastrado_por_engano():
    """Se o CNPJ da própria Magnata (emissora, aparece em todo
    documento) estivesse, por engano, cadastrado como Cliente, um
    documento com CNPJ_MAGNATA + CNPJ_CLIENTE_A cairia em CONFLICT sem
    a exclusão (2 clientes cadastrados no mesmo texto). Com
    cnpj_excluido=CNPJ_MAGNATA, resolve normalmente para o cliente
    real."""
    cnpj_magnata = '17.987.187/0001-61'
    candidatos_com_magnata_cadastrada = _CANDIDATOS + [
        CandidatoCliente(cliente_id='recMAGNATA', cnpj=cnpj_magnata, nome_normalizado='MAGNATA PORTARIA E SERVICOS'),
    ]
    fonte, leitor = _fonte(candidatos_com_magnata_cadastrada)
    leitor2 = Mock()
    leitor2.listar_clientes.return_value = candidatos_com_magnata_cadastrada
    fonte_com_exclusao = FonteClienteDiretoDocumentoAirtableShadow(leitor2, cnpj_excluido=cnpj_magnata)

    texto = f'Extrato Mensal\nEmitido por CNPJ: {cnpj_magnata}\nCliente CNPJ: {_CLIENTE_A_CNPJ}\n'

    # Sem exclusão: 2 clientes cadastrados no texto -> CONFLICT -> None
    assert fonte.resolver_cliente_direto(texto) is None
    # Com exclusão: só o cliente real permanece -> resolve
    assert fonte_com_exclusao.resolver_cliente_direto(texto) == ReferenciaCanonica('CLIENTE', 'recCLIENTE_A')


def test_cnpj_excluido_nao_afeta_texto_sem_ocorrencia_dele():
    fonte, _ = _fonte()
    fonte_com_exclusao = FonteClienteDiretoDocumentoAirtableShadow(
        Mock(listar_clientes=Mock(return_value=_CANDIDATOS)), cnpj_excluido='17.987.187/0001-61',
    )
    texto = f'CNPJ: {_CLIENTE_A_CNPJ}'
    assert fonte_com_exclusao.resolver_cliente_direto(texto) == ReferenciaCanonica('CLIENTE', 'recCLIENTE_A')


def test_cnpj_excluido_none_preserva_comportamento_original():
    leitor = Mock()
    leitor.listar_clientes.return_value = _CANDIDATOS
    fonte = FonteClienteDiretoDocumentoAirtableShadow(leitor)  # cnpj_excluido default None
    assert fonte.resolver_cliente_direto(f'CNPJ: {_CLIENTE_A_CNPJ}') == ReferenciaCanonica('CLIENTE', 'recCLIENTE_A')


def test_rejeita_match_por_nome_mesmo_que_ocorresse(monkeypatch):
    """Blindagem explícita contra a suposição implícita
    (`nome_manifesto=''`): mesmo se `resolver_cliente` algum dia
    devolvesse EXACT por nome (nunca deveria, com nome_manifesto vazio
    -- mas o contrato aqui não confia nisso), o adapter só aceita
    quando `criterio_usado == 'cnpj_exato'`, checagem explícita."""
    import magnata_os.documental.importacao_lote.adapters.airtable_cliente_direto_documento as modulo
    from magnata_os.documental.importacao_lote.contratos import (
        ClassificacaoCorrespondencia,
        MotivoSanitizado,
        ResultadoCorrespondencia,
    )

    def _resolver_cliente_fake(texto, nome_manifesto, candidatos):
        return ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.EXACT, 'recCLIENTE_A', MotivoSanitizado.OK, 'nome_normalizado_unico',
        )

    monkeypatch.setattr(modulo, 'resolver_cliente', _resolver_cliente_fake)
    fonte, _ = _fonte()
    assert fonte.resolver_cliente_direto('qualquer texto') is None
