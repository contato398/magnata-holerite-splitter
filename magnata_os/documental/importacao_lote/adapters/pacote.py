"""Adapter de leitura do pacote externo (ZIP + manifestos JSON).

Fala só com o filesystem/zip — nenhuma regra de negócio aqui, só
extração de dados brutos para os tipos de `contratos.py`. Formato real
confirmado por inspeção (Gate 1): pasta raiz com
`indice_holerites_<competência>.json` + `indice_extratos_por_cliente.json`,
subpastas `holerites_por_cliente/`, `extratos_por_cliente/`,
`relatorios_gerais/`.

IMPORTANTE (achado do Ultrareview, corrigido): a pasta raiz e o nome do
manifesto de holerites NUNCA são hard-coded para "julho_2026" — são
localizados por padrão de nome dentro do ZIP, para que o mesmo módulo
sirva qualquer competência futura sem alteração de código.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from ..contratos import ItemManifestoExtrato, ItemManifestoHolerite

_PREFIXO_MANIFESTO_HOLERITES = 'indice_holerites_'
_NOME_MANIFESTO_EXTRATOS = 'indice_extratos_por_cliente.json'
_PREFIXO_CLIENTE_RE = re.compile(r'^\s*(\d+)\s*-\s*')

# Limite defensivo contra zip bomb — nenhum PDF individual do pacote tem
# motivo legítimo para descomprimir acima disto. Achado do Ultrareview:
# `zipfile.read()` não tinha nenhum teto antes desta correção. Entradas
# maiores são tratadas como indisponíveis (mesmo sinal de "arquivo
# ausente"), nunca lidas.
_TAMANHO_MAXIMO_ENTRADA_BYTES = 50 * 1024 * 1024  # 50 MB


def _caminho_manifesto_holerites(z: zipfile.ZipFile) -> str:
    """Localiza o manifesto de holerites por padrão de nome (prefixo),
    nunca por competência exata — funciona para qualquer mês."""
    candidatos = [
        n for n in z.namelist()
        if Path(n).name.startswith(_PREFIXO_MANIFESTO_HOLERITES) and n.lower().endswith('.json')
    ]
    if not candidatos:
        raise FileNotFoundError(
            f'Nenhum manifesto de holerites encontrado (esperado um arquivo '
            f'"{_PREFIXO_MANIFESTO_HOLERITES}*.json") — pacote fora do formato esperado.')
    if len(candidatos) > 1:
        raise ValueError(
            f'Mais de um manifesto de holerites candidato encontrado no pacote: '
            f'{candidatos} — ambíguo, não decido sozinho qual usar.')
    return candidatos[0]


def _raiz_pacote(z: zipfile.ZipFile) -> str:
    """Pasta raiz do pacote, derivada do manifesto de holerites (o único
    arquivo com nome previsível por padrão)."""
    return str(Path(_caminho_manifesto_holerites(z)).parent)


def _caminho_manifesto_extratos(z: zipfile.ZipFile, raiz: str) -> str:
    candidato = f'{raiz}/{_NOME_MANIFESTO_EXTRATOS}'
    if candidato not in z.namelist():
        raise FileNotFoundError(
            f'Manifesto de extratos "{_NOME_MANIFESTO_EXTRATOS}" não encontrado em "{raiz}/".')
    return candidato


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
        caminho_manifesto = _caminho_manifesto_holerites(z)
        bruto = json.loads(z.read(caminho_manifesto).decode('utf-8'))

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
        raiz = _raiz_pacote(z)
        caminho_manifesto = _caminho_manifesto_extratos(z, raiz)
        bruto = json.loads(z.read(caminho_manifesto).decode('utf-8'))

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


def _indice_caminhos_por_basename(z: zipfile.ZipFile, prefixo: str) -> dict[str, zipfile.ZipInfo]:
    return {
        Path(info.filename).name: info
        for info in z.infolist()
        if info.filename.startswith(prefixo) and info.filename.lower().endswith('.pdf')
    }


def _ler_entrada_com_limite(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes | None:
    """Lê uma entrada do ZIP só se o tamanho descomprimido estiver dentro
    do limite defensivo — nunca confia cegamente no tamanho declarado
    para decidir, mas o `file_size` do ZipInfo já é suficiente para
    recusar antes de descomprimir qualquer coisa."""
    if info.file_size > _TAMANHO_MAXIMO_ENTRADA_BYTES:
        return None
    return z.read(info)


def ler_pdf_holerite_bytes(caminho_zip: str, filename: str) -> bytes | None:
    with zipfile.ZipFile(caminho_zip) as z:
        raiz = _raiz_pacote(z)
        indice = _indice_caminhos_por_basename(z, f'{raiz}/holerites_por_cliente/')
        info = indice.get(filename)
        if not info:
            return None
        return _ler_entrada_com_limite(z, info)


def ler_pdf_extrato_bytes(caminho_zip: str, filename: str) -> bytes | None:
    with zipfile.ZipFile(caminho_zip) as z:
        raiz = _raiz_pacote(z)
        indice = _indice_caminhos_por_basename(z, f'{raiz}/extratos_por_cliente/')
        info = indice.get(filename)
        if not info:
            return None
        return _ler_entrada_com_limite(z, info)


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
        raiz = _raiz_pacote(z)
        return [
            _corrigir_nome_cp437_utf8(Path(n).name) for n in z.namelist()
            if n.startswith(f'{raiz}/relatorios_gerais/') and n.lower().endswith('.pdf')
        ]
