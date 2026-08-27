"""Classificação conservadora de Guia DCTFWeb/DARF, sem efeitos externos."""

from app import classificar_documento


def test_guia_dctfweb_e_identificada():
    assert classificar_documento("Guia de Recolhimento DCTFWeb") == (
        "Guia DCTFWeb/DARF",
        1,
    )


def test_darf_com_sinal_explicito_de_dctfweb_e_identificado():
    assert classificar_documento("DARF - DCTFWeb") == (
        "Guia DCTFWeb/DARF",
        1,
    )


def test_declaracao_nao_e_classificada_como_guia():
    assert classificar_documento("Declaração DCTFWeb") == (
        "DCTFWeb - Declaração",
        1,
    )


def test_recibo_nao_e_classificado_como_guia():
    assert classificar_documento("Recibo de Entrega da DCTFWeb") == (
        "DCTFWeb - Recibo de Entrega",
        1,
    )


def test_recibo_tem_precedencia_sobre_mencao_a_guia():
    texto = "Recibo de Entrega da DCTFWeb referente à Guia DCTFWeb"
    assert classificar_documento(texto)[0] == "DCTFWeb - Recibo de Entrega"


def test_guia_tem_precedencia_sobre_declaracao_generica():
    assert classificar_documento("Guia DCTFWeb")[0] == "Guia DCTFWeb/DARF"


def test_darf_sem_sinal_de_dctfweb_permanece_generico():
    assert classificar_documento("DARF - Documento de Arrecadação")[0] == "Guia"


def test_comprovante_de_pagamento_nao_entra_na_classificacao_da_guia():
    assert classificar_documento("Comprovante de pagamento bancário")[0] == "Outro"
