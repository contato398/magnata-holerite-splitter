"""Dependências entre camadas são acíclicas e numa só direção:

    documental (esteira, entrada)  <-  classificacao (Prestação/domínio)
                                   <-  orquestrador (coordena, compõe, executa)

A Prestação produz necessidades/Ordens; o Orquestrador coordena; o canal
executa. Se o domínio importasse o Orquestrador, abriria caminho para
"Prestação pergunta ao Orquestrador que pergunta à Prestação" (ping-pong).
Verificação estática (AST), sem importar os módulos.
"""
import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent / "magnata_os"


def _imports(arquivo: Path):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    pacote = ".".join(arquivo.relative_to(RAIZ.parent).with_suffix("").parts[:-1])
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for nome in no.names:
                yield nome.name
        elif isinstance(no, ast.ImportFrom):
            if no.level:
                base = pacote.split(".")[: len(pacote.split(".")) - (no.level - 1)]
                yield ".".join(base + ([no.module] if no.module else []))
            elif no.module:
                yield no.module


def _violacoes(camada: str, proibido: str):
    return sorted(
        f"{arquivo.relative_to(RAIZ.parent)} -> {modulo}"
        for arquivo in (RAIZ / camada).rglob("*.py")
        for modulo in _imports(arquivo)
        if modulo == proibido or modulo.startswith(proibido + ".")
    )


@pytest.mark.parametrize("camada", ["classificacao", "documental"])
def test_dominio_e_esteira_nunca_importam_o_orquestrador(camada):
    assert _violacoes(camada, "magnata_os.orquestrador") == []


def test_capacidades_centrais_nunca_importam_o_dominio_da_prestacao():
    assert _violacoes("central", "magnata_os.classificacao") == []


def test_verificacao_enxerga_imports_relativos():
    """Garante que a verificação não passa por não ver nada."""
    assert any(m.startswith("magnata_os.classificacao") for m in _imports(RAIZ / "orquestrador" / "prestacao_cliente_competencia_v1.py"))
