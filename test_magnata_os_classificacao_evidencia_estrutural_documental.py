"""Testes de `evidencia_estrutural_documental.py` (Fase C da missão
"CAPACIDADES TRANSVERSAIS DO MOTOR DOCUMENTAL"). Todos os CPFs/CNPJs
usados são SINTÉTICOS (números válidos apenas no formato, não
correspondem a nenhuma pessoa/empresa real) -- nunca dado real, seguindo
LGPD (`/CLAUDE.md` §6)."""
from magnata_os.classificacao.contratos import NivelConfianca
from magnata_os.classificacao.evidencia_estrutural_documental import (
    TIPO_EVIDENCIA_MULTIPLAS_PAGINAS,
    TIPO_EVIDENCIA_MULTIPLOS_CNPJS,
    TIPO_EVIDENCIA_MULTIPLOS_CPFS,
    EvidenciaEstruturalDocumento,
    analisar_estrutura_documento,
    evidencias_sanitizadas_de_estrutura,
)

_CNPJ_A = '11.222.333/0001-81'
_CNPJ_B = '44.555.666/0001-72'
_CPF_A = '111.444.777-35'
_CPF_B = '222.555.888-06'


def test_documento_de_1_pagina_sem_entidade_conta_zero():
    evidencia = analisar_estrutura_documento(('texto qualquer sem identificador nenhum',))
    assert evidencia == EvidenciaEstruturalDocumento(
        total_paginas=1, quantidade_cnpjs_distintos=0, quantidade_cpfs_distintos=0,
    )


def test_conta_cnpjs_distintos_entre_paginas():
    paginas = (f'Tomador CNPJ {_CNPJ_A}', 'pagina de detalhe sem cnpj', f'Tomador CNPJ {_CNPJ_B}')
    evidencia = analisar_estrutura_documento(paginas)
    assert evidencia.quantidade_cnpjs_distintos == 2
    assert evidencia.total_paginas == 3


def test_conta_cpfs_distintos_entre_paginas():
    paginas = (f'CPF: {_CPF_A}', f'CPF: {_CPF_B}', f'CPF: {_CPF_A}')
    evidencia = analisar_estrutura_documento(paginas)
    assert evidencia.quantidade_cpfs_distintos == 2


def test_evidencia_nunca_expoe_cpf_ou_cnpj_bruto():
    """EvidenciaEstruturalDocumento só tem campos inteiros -- nenhum
    campo pode conter texto (o que abriria espaço para um identificador
    real vazar pela evidência)."""
    campos = EvidenciaEstruturalDocumento.__dataclass_fields__
    for nome_campo, campo in campos.items():
        assert campo.type in ('int',), (
            f'{nome_campo}: evidência estrutural só pode expor inteiros, nunca texto')


def test_evidencias_sanitizadas_multiplas_paginas_e_entidades():
    evidencia = EvidenciaEstruturalDocumento(
        total_paginas=3, quantidade_cnpjs_distintos=2, quantidade_cpfs_distintos=0,
    )
    evidencias = evidencias_sanitizadas_de_estrutura(evidencia)
    tipos = {e.tipo_evidencia for e in evidencias}
    assert tipos == {TIPO_EVIDENCIA_MULTIPLOS_CNPJS, TIPO_EVIDENCIA_MULTIPLAS_PAGINAS}
    for e in evidencias:
        assert e.referencia_fonte  # nunca vazio
        assert isinstance(e.forca, NivelConfianca)


def test_evidencias_sanitizadas_documento_unitario_sem_sinal_de_multiplicidade():
    evidencia = EvidenciaEstruturalDocumento(
        total_paginas=1, quantidade_cnpjs_distintos=1, quantidade_cpfs_distintos=0,
    )
    assert evidencias_sanitizadas_de_estrutura(evidencia) == ()


def test_evidencia_estrutural_rejeita_contagem_negativa():
    import pytest
    with pytest.raises(ValueError):
        EvidenciaEstruturalDocumento(
            total_paginas=1, quantidade_cnpjs_distintos=-1, quantidade_cpfs_distintos=0,
        )
