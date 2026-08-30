"""Testes do cadastro canônico versionado (Fases 5-8 da missão
"CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO")."""
import pytest

from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    CADASTRO_REQUISITOS_PRESTACAO_V1,
    CADASTRO_REQUISITOS_PRESTACAO_V2,
    HOLERITE_TIPO_DOCUMENTAL,
    REQUISITOS_BASE_CANONICOS_V1,
    REQUISITOS_BASE_CANONICOS_V2,
    REQUISITOS_DIVERGENTES_ENTRE_FONTES,
    REQUISITOS_DIVERGENTES_ENTRE_FONTES_V2,
    CadastroRequisitosPrestacao,
    ConfiguracaoCondicionalCliente,
    EstadoConfiguracaoRequisito,
    FonteRequisitosPrestacaoCanonica,
    RequisitoCanonico,
)
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_1')


def test_requisito_sem_evidencia_nunca_e_aceito():
    with pytest.raises(ValueError):
        RequisitoCanonico('FGTS', evidencia='')


def test_requisito_com_tipo_fora_do_universo_e_rejeitado():
    with pytest.raises(ValueError):
        RequisitoCanonico('Tipo Inventado', evidencia='qualquer coisa')


def test_configuracao_condicional_nao_configurado_nunca_e_entrada_explicita():
    """NAO_CONFIGURADO é ausência de entrada -- nunca uma linha
    explícita (cláusula pétrea #4: "ausência de evidência não vira
    False")."""
    with pytest.raises(ValueError):
        ConfiguracaoCondicionalCliente(
            cliente_id='rec_1', tipo_documental='Certidão',
            estado=EstadoConfiguracaoRequisito.NAO_CONFIGURADO, evidencia='qualquer coisa',
        )


def test_configuracao_condicional_explicita_exige_evidencia():
    with pytest.raises(ValueError):
        ConfiguracaoCondicionalCliente(
            cliente_id='rec_1', tipo_documental='Certidão',
            estado=EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE, evidencia='',
        )


def test_base_canonica_v1_e_a_intersecao_das_2_fontes():
    """Fase 3: só o que as 2 fontes canônicas (Família B +
    CAPACIDADES_DOCUMENTO) concordam vira base universal."""
    tipos_base = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V1}
    assert tipos_base == {'FGTS', 'DCTFWeb - Declaração', 'DCTFWeb - Recibo de Entrega', 'Extrato da Folha de Pagamento'}


def test_divergentes_nunca_entram_na_base_universal():
    tipos_divergentes = {tipo for tipo, _motivo in REQUISITOS_DIVERGENTES_ENTRE_FONTES}
    tipos_base = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V1}
    assert tipos_divergentes.isdisjoint(tipos_base)
    assert tipos_divergentes == {'Guia DCTFWeb/DARF'}


def test_holerite_e_universal_mas_nunca_via_contagem_plana():
    """Registro HISTÓRICO do cadastro V1 (Adendo de Regra de Negócio --
    Holerite, vigente em V1): universal, mas NUNCA avaliado pela
    contagem plana de REQUISITOS_BASE_CANONICOS_V1. Este teste continua
    verde porque V1 NUNCA é sobrescrito em silêncio (missão "FECHAMENTO
    DA BASE CANÔNICA" só cria V2) -- mas o comportamento EFETIVO a
    partir de V2 é outro: ver `test_holerite_nao_e_mais_universal_em_v2`
    abaixo, que prova a reversão."""
    assert HOLERITE_TIPO_DOCUMENTAL == 'Holerite'
    tipos_base = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V1}
    assert HOLERITE_TIPO_DOCUMENTAL not in tipos_base
    tipos_divergentes = {tipo for tipo, _motivo in REQUISITOS_DIVERGENTES_ENTRE_FONTES}
    assert HOLERITE_TIPO_DOCUMENTAL not in tipos_divergentes  # nao e mais divergente -- e universal confirmado (em V1)


# ============================================================================
# CADASTRO V2 -- missão "FECHAMENTO DA BASE CANÔNICA + PREPARAÇÃO DO
# PRIMEIRO CICLO PILOTO REAL READ-ONLY" (2026-08-30).
# ============================================================================

def test_guia_dctf_darf_promovido_a_base_universal_em_v2():
    """Decisão de negócio #1 da missão: Guia DCTFWeb/DARF sai de
    REQUISITOS_DIVERGENTES_ENTRE_FONTES e entra na base universal V2."""
    tipos_base_v2 = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V2}
    assert 'Guia DCTFWeb/DARF' in tipos_base_v2
    assert REQUISITOS_DIVERGENTES_ENTRE_FONTES_V2 == ()


def test_base_v2_preserva_toda_a_base_v1_mais_guia_dctf_darf():
    tipos_base_v1 = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V1}
    tipos_base_v2 = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V2}
    assert tipos_base_v2 == tipos_base_v1 | {'Guia DCTFWeb/DARF'}


def test_v1_nunca_e_sobrescrito_pela_existencia_de_v2():
    """Cláusula constitucional: nunca sobrescrever silenciosamente uma
    versão anterior -- V1 continua exatamente como era (4 itens, sem
    Guia DCTFWeb/DARF)."""
    tipos_base_v1 = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V1}
    assert tipos_base_v1 == {'FGTS', 'DCTFWeb - Declaração', 'DCTFWeb - Recibo de Entrega', 'Extrato da Folha de Pagamento'}
    assert CADASTRO_REQUISITOS_PRESTACAO_V1.versao == '1'
    assert CADASTRO_REQUISITOS_PRESTACAO_V2.versao == '2'


def test_holerite_nao_e_mais_universal_em_v2():
    """Decisão de negócio #2 da missão (reversão do Adendo, mensagem
    distinta do humano): Holerite NUNCA esteve na base universal (nem
    em V1 nem em V2) -- mas a partir de V2 ele TAMBÉM deixa de ser
    avaliado incondicionalmente para todo cliente. Sem nenhuma
    ConfiguracaoCondicionalCliente explícita, um cliente qualquer fica
    NAO_CONFIGURADO para Holerite -- nunca CONFIGURADO_NAO_EXIGE nem
    CONFIGURADO_EXIGE por omissão."""
    tipos_base_v2 = {r.tipo_documental for r in REQUISITOS_BASE_CANONICOS_V2}
    assert HOLERITE_TIPO_DOCUMENTAL not in tipos_base_v2
    assert CADASTRO_REQUISITOS_PRESTACAO_V2.estado_condicional(
        'rec_qualquer_cliente', HOLERITE_TIPO_DOCUMENTAL,
    ) == EstadoConfiguracaoRequisito.NAO_CONFIGURADO


def test_holerite_pode_ser_configurado_condicionalmente_em_v2():
    """Holerite continua sendo um tipo_documental válido -- só que agora
    exige configuração explícita por cliente, como qualquer outro
    condicional (nunca universal por padrão)."""
    cadastro = CadastroRequisitosPrestacao(
        versao='teste-v2-holerite-condicional', requisitos_base=REQUISITOS_BASE_CANONICOS_V2,
        condicionais=(
            ConfiguracaoCondicionalCliente(
                'rec_1', HOLERITE_TIPO_DOCUMENTAL, EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE,
                evidencia='configuracao sintetica de teste -- prova que Holerite aceita condicional em V2',
            ),
        ),
    )
    assert cadastro.estado_condicional('rec_1', HOLERITE_TIPO_DOCUMENTAL) == EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE
    registros = cadastro.registros_condicionais_para('rec_1')
    assert len(registros) == 1
    assert registros[0].tipo_documental == HOLERITE_TIPO_DOCUMENTAL
    # Outro cliente, sem configuração, continua NAO_CONFIGURADO -- nunca herda.
    assert cadastro.estado_condicional('rec_2', HOLERITE_TIPO_DOCUMENTAL) == EstadoConfiguracaoRequisito.NAO_CONFIGURADO


def test_fonte_requisitos_canonica_v2_satisfaz_o_protocol_do_pr98():
    fonte = FonteRequisitosPrestacaoCanonica(CADASTRO_REQUISITOS_PRESTACAO_V2)
    registros = fonte.registros_para(_CLIENTE, _CONTEXTO)
    assert registros == ()  # cadastro v2 tambem comeca com zero condicionais configurados


def test_base_documental_v2_alimenta_politica_requisitos_sem_dto_novo():
    requisitos = CADASTRO_REQUISITOS_PRESTACAO_V2.requisitos_base_documentais()
    assert all(isinstance(r, RequisitoDocumentalPrestacao) for r in requisitos)
    tipos = {r.tipo_documental for r in requisitos}
    assert 'Guia DCTFWeb/DARF' in tipos
    assert HOLERITE_TIPO_DOCUMENTAL not in tipos


def test_cliente_sem_configuracao_condicional_fica_explicitamente_nao_configurado():
    cadastro = CadastroRequisitosPrestacao(versao='teste', requisitos_base=())
    assert cadastro.estado_condicional('rec_x', 'Certidão') == EstadoConfiguracaoRequisito.NAO_CONFIGURADO


def test_cliente_configurado_exige_aparece_nos_registros():
    cadastro = CadastroRequisitosPrestacao(
        versao='teste', requisitos_base=(),
        condicionais=(ConfiguracaoCondicionalCliente('rec_1', 'Certidão', EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE, 'teste'),),
    )
    registros = cadastro.registros_condicionais_para('rec_1')
    assert len(registros) == 1
    assert registros[0].tipo_documental == 'Certidão'


def test_cliente_configurado_nao_exige_nunca_aparece_nos_registros():
    cadastro = CadastroRequisitosPrestacao(
        versao='teste', requisitos_base=(),
        condicionais=(ConfiguracaoCondicionalCliente('rec_1', 'Certidão', EstadoConfiguracaoRequisito.CONFIGURADO_NAO_EXIGE, 'teste'),),
    )
    assert cadastro.registros_condicionais_para('rec_1') == ()
    assert cadastro.estado_condicional('rec_1', 'Certidão') == EstadoConfiguracaoRequisito.CONFIGURADO_NAO_EXIGE


def test_cadastro_rejeita_configuracao_duplicada_para_mesmo_cliente_e_tipo():
    with pytest.raises(ValueError):
        CadastroRequisitosPrestacao(
            versao='teste', requisitos_base=(),
            condicionais=(
                ConfiguracaoCondicionalCliente('rec_1', 'Certidão', EstadoConfiguracaoRequisito.CONFIGURADO_EXIGE, 'a'),
                ConfiguracaoCondicionalCliente('rec_1', 'Certidão', EstadoConfiguracaoRequisito.CONFIGURADO_NAO_EXIGE, 'b'),
            ),
        )


def test_fonte_requisitos_canonica_satisfaz_o_protocol_do_pr98():
    fonte = FonteRequisitosPrestacaoCanonica(CADASTRO_REQUISITOS_PRESTACAO_V1)
    registros = fonte.registros_para(_CLIENTE, _CONTEXTO)
    assert registros == ()  # cadastro v1 nao tem nenhum condicional configurado


def test_fonte_requisitos_canonica_reporta_nao_configurados():
    fonte = FonteRequisitosPrestacaoCanonica(CADASTRO_REQUISITOS_PRESTACAO_V1)
    tipos_interesse = tuple(tipo for tipo, _m in REQUISITOS_DIVERGENTES_ENTRE_FONTES)
    nao_configurados = fonte.requisitos_nao_configurados_para(_CLIENTE, _CONTEXTO, tipos_interesse)
    assert set(nao_configurados) == set(tipos_interesse)  # nenhum cliente configurado no v1


def test_base_documental_do_cadastro_alimenta_politica_requisitos_sem_dto_novo():
    """Fase 5: a base do cadastro vira RequisitoDocumentalPrestacao --
    o MESMO contrato já consumido por PoliticaRequisitosPrestacao,
    nunca um DTO novo."""
    requisitos = CADASTRO_REQUISITOS_PRESTACAO_V1.requisitos_base_documentais()
    assert all(isinstance(r, RequisitoDocumentalPrestacao) for r in requisitos)
    politica = PoliticaRequisitosPrestacao(version='1', requisitos_base=requisitos)
    assert politica.requisitos_para(_CLIENTE, ReferenciaCanonica('COMPETENCIA', '2026-07')) == requisitos
