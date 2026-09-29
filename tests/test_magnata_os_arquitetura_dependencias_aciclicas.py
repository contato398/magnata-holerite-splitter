"""Direção das dependências entre Prestação e Orquestrador (sem ping-pong):

    classificacao (domínio da Prestação)  <-  orquestrador (coordena, compõe, executa)
    documental    (esteira, entrada)      <-  orquestrador

A Prestação produz necessidades/Ordens; o Orquestrador coordena; o canal
executa. Se o domínio importasse o Orquestrador, abriria caminho para
"Prestação pergunta ao Orquestrador que pergunta à Prestação".
Verificação estática (AST), sem importar os módulos.

Escopo verificado (e só este): `classificacao/` e `documental/` nunca
importam `magnata_os.orquestrador`; `central/` nunca importa
`magnata_os.classificacao`. NÃO verificado aqui (pré-existente, fora
desta regra): `documental/` <-> `classificacao/` se importam em alguns
módulos (ex.: `documental/alocacao`, `importacao_lote`), e `central/`
importa enums do Orquestrador. `importlib.import_module` dinâmico não é
visto por AST.
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
                partes = pacote.split(".")
                base = partes[: len(partes) - (no.level - 1)]
                modulo = ".".join(base + ([no.module] if no.module else []))
            else:
                modulo = no.module or ""
            yield modulo
            # `from .. import orquestrador` / `from magnata_os import orquestrador`
            for nome in no.names:
                yield f"{modulo}.{nome.name}"


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


def test_verificacao_enxerga_imports_relativos_e_de_pacote(tmp_path, monkeypatch):
    """Garante que a verificação não passa por não ver nada."""
    arquivo = RAIZ / "classificacao" / "_sonda_arquitetura_teste.py"
    try:
        arquivo.write_text(
            "from .. import orquestrador\nfrom ..orquestrador import motor\n", encoding="utf-8",
        )
        assert set(_violacoes("classificacao", "magnata_os.orquestrador")) == {
            "magnata_os/classificacao/_sonda_arquitetura_teste.py -> magnata_os.orquestrador",
            "magnata_os/classificacao/_sonda_arquitetura_teste.py -> magnata_os.orquestrador.motor",
        }
    finally:
        arquivo.unlink()
