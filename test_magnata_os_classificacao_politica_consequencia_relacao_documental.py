"""Testes de `politica_consequencia_relacao_documental.py` (missão
"CORRIGIR METADADOS + MERGE PR #106 + COSTURA AUTOMÁTICA DE RELAÇÃO
DOCUMENTO↔DOCUMENTO NO CORREDOR V1", §7)."""
import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.politica_consequencia_relacao_documental import (
    RegraConsequenciaRelacao,
    derivar_referencias_herdadas,
    regra_para_tipo_comprovante,
    tipos_comprovante_com_regra_cadastrada,
)
from magnata_os.classificacao.relacao_documental import TipoRelacaoDocumental


def test_tipo_sem_regra_devolve_none_nunca_inventa():
    assert regra_para_tipo_comprovante('Tipo Que Nao Existe Ainda') is None


def test_beneficios_regra_permite_derivar_referencias():
    regra = regra_para_tipo_comprovante('Comprovante de Pagamento - VR/VA')
    assert regra is not None
    assert regra.tipo_relatante == 'Relatório de Benefícios'
    assert regra.pode_derivar_referencias_do_relatante is True
    assert regra.preserva_broadcast is False


def test_fgts_regra_permite_derivar_referencias():
    regra = regra_para_tipo_comprovante('Comprovante de Pagamento - FGTS')
    assert regra is not None
    assert regra.tipo_relatante == 'FGTS'
    assert regra.pode_derivar_referencias_do_relatante is True


def test_dctf_regra_preserva_broadcast_nunca_deriva():
    regra = regra_para_tipo_comprovante('Comprovante de Pagamento - DCTF/DARF')
    assert regra is not None
    assert regra.tipo_relatante == 'Guia DCTFWeb/DARF'
    assert regra.pode_derivar_referencias_do_relatante is False
    assert regra.preserva_broadcast is True


def test_regra_nunca_deriva_e_preserva_broadcast_ao_mesmo_tempo():
    with pytest.raises(ValueError):
        RegraConsequenciaRelacao(
            tipo_relatante='X', tipo_comprovante='Y', tipo_relacao=TipoRelacaoDocumental.COMPROVA,
            pode_derivar_referencias_do_relatante=True, preserva_broadcast=True, motivo_registrado='invalido',
        )


def test_tipos_comprovante_com_regra_cadastrada():
    tipos = tipos_comprovante_com_regra_cadastrada()
    assert tipos == {
        'Comprovante de Pagamento - VR/VA', 'Comprovante de Pagamento - FGTS', 'Comprovante de Pagamento - DCTF/DARF',
    }


def test_derivar_referencias_herdadas_so_com_relacao_resolvida():
    referencias = (ReferenciaCanonica('CLIENTE', 'cli-a'), ReferenciaCanonica('CLIENTE', 'cli-b'))
    assert derivar_referencias_herdadas(True, referencias) == referencias
    assert derivar_referencias_herdadas(False, referencias) == ()
