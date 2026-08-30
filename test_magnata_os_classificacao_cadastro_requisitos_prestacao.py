"""Testes do cadastro canônico versionado (Fases 5-8 da missão
"CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO")."""
import pytest

from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    CADASTRO_REQUISITOS_PRESTACAO_V1,
    REQUISITOS_BASE_CANONICOS_V1,
    REQUISITOS_DIVERGENTES_ENTRE_FONTES,
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
    assert tipos_divergentes == {'Holerite', 'Guia DCTFWeb/DARF'}


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
