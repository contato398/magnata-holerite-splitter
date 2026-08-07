"""Adapter de leitura do pacote externo (ZIP + manifestos JSON).

Fala só com o filesystem/zip — nenhuma regra de negócio aqui, só
extração de dados brutos para os tipos de `contratos.py`. Formato real
confirmado por inspeção (Gate 1): ver
`documentos_julho_2026_organizados/{indice_holerites_julho_2026.json,
indice_extratos_por_cliente.json}` dentro do ZIP.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from ..contratos import ItemManifestoExtrato, ItemManifestoHolerite

_PASTA_RAIZ = 'documentos_julho_2026_organizados'
_MANIFESTO_HOLERITES = f'{_PASTA_RAIZ}/indice_holerites_julho_2026.json'
_MANIFESTO_EXTRATOS = f'{_PASTA_RAIZ}/indice_extratos_por_cliente.json'
_PREFIXO_CLIENTE_RE = re.compile(r'^\s*(\d+)\s*-\s*')


def calcular_sha256_arquivo(caminho: str) -> str:
    """SHA-256 do ZIP inteiro — usado na identidade de ingestão
    (`package_sha256`). Lido em blocos para não carregar o arquivo
    inteiro na memória de uma vez."""
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloco)
    return h.hexdigest()


def _extrair_prefixo_numerico(texto: str) -> str | None:
    """`source_service_number` — o prefixo numérico do pacote (ex.: "3"
    de "3 - CASTROLANDA..."). Nunca tratado como ID canônico do Airtable
    sem prova de correspondência (determinação 1 desta rodada)."""
    if not texto:
        return None
    m = _PREFIXO_CLIENTE_RE.match(texto)
    return m.group(1) if m else None


def ler_manifesto_holerites(caminho_zip: str) -> list[ItemManifestoHolerite]:
    with zipfile.ZipFile(caminho_zip) as z:
        bruto = json.loads(z.read(_MANIFESTO_HOLERITES).decode('utf-8'))

    itens = []
    for i, reg in enumerate(bruto):
        code = reg.get('code')
        manifesto_item_id = f'holerite:{code if code is not None else i}'
        itens.append(ItemManifestoHolerite(
            manifesto_item_id=manifesto_item_id,
            source_service_number=_extrair_prefixo_numerico(reg.get('client', '')),
            nome_manifesto=reg.get('name', ''),
            cpf_mascarado=reg.get('cpf_mascarado', ''),
            filename=reg.get('filename', ''),
            pagina=reg.get('page', 0),
        ))
    return itens


def ler_manifesto_extratos(caminho_zip: str) -> list[ItemManifestoExtrato]:
    with zipfile.ZipFile(caminho_zip) as z:
        bruto = json.loads(z.read(_MANIFESTO_EXTRATOS).decode('utf-8'))

    itens = []
    for reg in bruto:
        num = reg.get('num')
        itens.append(ItemManifestoExtrato(
            manifesto_item_id=f'extrato:{num}',
            source_service_number=str(num) if num is not None else '',
            nome_manifesto=reg.get('name', ''),
            linha_bruta=reg.get('line', ''),
            filename=reg.get('filename', ''),
            paginas_origem=tuple(reg.get('source_pages') or []),
        ))
    return itens


def _indice_caminhos_por_basename(caminho_zip: str, prefixo: str) -> dict[str, str]:
    with zipfile.ZipFile(caminho_zip) as z:
        return {
            Path(n).name: n
            for n in z.namelist()
            if n.startswith(prefixo) and n.lower().endswith('.pdf')
        }


def ler_pdf_holerite_bytes(caminho_zip: str, filename: str) -> bytes | None:
    indice = _indice_caminhos_por_basename(caminho_zip, f'{_PASTA_RAIZ}/holerites_por_cliente/')
    caminho_interno = indice.get(filename)
    if not caminho_interno:
        return None
    with zipfile.ZipFile(caminho_zip) as z:
        return z.read(caminho_interno)


def ler_pdf_extrato_bytes(caminho_zip: str, filename: str) -> bytes | None:
    indice = _indice_caminhos_por_basename(caminho_zip, f'{_PASTA_RAIZ}/extratos_por_cliente/')
    caminho_interno = indice.get(filename)
    if not caminho_interno:
        return None
    with zipfile.ZipFile(caminho_zip) as z:
        return z.read(caminho_interno)


def _corrigir_nome_cp437_utf8(nome: str) -> str:
    """Alguns pacotes gravam nome de entrada em UTF-8 nos bytes mas sem
    marcar a flag UTF-8 do ZIP (flag_bits & 0x800 == 0) — o zipfile então
    decodifica como CP437 por padrão, produzindo mojibake (ex.:
    "Serviço" -> "Servi├ºo"). Round-trip cp437->utf-8 recupera o nome
    correto; se não for esse o caso, devolve o nome original sem
    alteração (nunca lança)."""
    try:
        return nome.encode('cp437').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return nome


def listar_relatorios_gerais(caminho_zip: str) -> list[str]:
    """Nomes dos relatórios gerais (ex.: RelatoriodeLiquidos) — usados só
    para confirmar que ficam FORA do fluxo de colaborador/cliente, nunca
    processados como holerite/extrato."""
    with zipfile.ZipFile(caminho_zip) as z:
        return [
            _corrigir_nome_cp437_utf8(Path(n).name) for n in z.namelist()
            if n.startswith(f'{_PASTA_RAIZ}/relatorios_gerais/') and n.lower().endswith('.pdf')
        ]
