"""Ingestão REAL em lote de conteúdo de documento (Airtable -> S3/R2 +
Postgres) -- missão "INGESTÃO DE DOCUMENTO EM LOTE REAL" (Fase 4).

Problema real que motivou (ver
docs/decisoes/ingestao-documento-lote-real-v1.md): registros de
`Documento` já existiam no Postgres sem conteúdo real no armazenamento
(metadado órfão) -- nenhuma ferramenta existente ingeria o BINÁRIO real
a partir do Airtable; todas pressupõem que a entrada já aconteceu.

Reaproveita, sem reimplementar nada:
- `FonteInventarioHoleritesAirtableShadow`/`FonteInventarioPrestacaoAirtableShadow`
  (já usadas pelo inventário real da Prestação) para descobrir QUAIS
  registros do Airtable pertencem a 1 cliente + 1 competência -- a
  resolução de vínculo/Folha Mensal é a MESMA já validada em produção;
- `AdaptadorEntradaDuravel` (porta oficial de entrada durável, Fase 2)
  para armazenar o blob e persistir `Documento`/`EventoHistorico` --
  idempotente por hash, sem reimplementar dedup aqui.

Disparo SEMPRE manual (nunca cron/scheduler) -- ver
`scripts/ingerir_documentos_lote_real_cli.py`. Nenhum dado pessoal
(CPF, nome) é logado/impresso por este módulo -- o resumo só expõe
hash, id de registro Airtable (não é dado pessoal), tipo documental e
contagens. `nome_original`/`metadados` continuam fluindo para
armazenamento/Postgres como em todo o resto do Módulo 01 (mesmo
comportamento já existente em `ServicoEntradaDocumental`) -- isto não é
um log nem um print.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Set, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.modulo01.adaptador_entrada_duravel import AdaptadorEntradaDuravel
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentos, RepositorioHistorico

from .adapters.airtable_anexos_prestacao import buscar_anexos_por_registro
from .adapters.airtable_holerites_prestacao import (
    TABLE_HOL,
    TIPO_HOLERITE,
    FonteInventarioHoleritesAirtableShadow,
)
from .adapters.airtable_inventario_prestacao import (
    TABLE_EXTRATO,
    TABLE_FGTS,
    FonteInventarioPrestacaoAirtableShadow,
)
from .adapters.airtable_leitura import LeitorAirtableSomenteLeitura
from .adapters.airtable_vinculos_prestacao import FonteVinculosPrestacaoAirtableShadow
from .contratos import TipoDocumental

# Campo de anexo (binário) de cada tabela de origem -- confirmado por
# leitura READ-ONLY do schema real do Airtable (`get_table_schema`,
# nunca escrita), ver docs/decisoes/ingestao-documento-lote-real-v1.md
# §"Schema confirmado". Duplicado aqui pela mesma disciplina já adotada
# em airtable_escrita.py/airtable_leitura.py (módulo novo não importa
# app.py -- CLAUDE.md §7).
F_HOL_PDF = 'fldGXsgmuADtZIgtx'
F_EXT_PDF = 'fldznv1E24rfbZt34'
F_FGTS_ANEXO = 'fldYZS5KB9yKK4lMH'

TIPO_FGTS = 'FGTS'

# tipo_documental (string EXATA como os inventários reais já a
# produzem -- casing/valor herdado deles, nunca normalizado aqui) ->
# (tabela, campo de anexo). Guias/DCTFWeb (TABLE_GUIAS) ficam DE FORA
# desta ingestão v1 -- decisão registrada: aquela tabela nunca carrega
# vínculo de cliente real (broadcast por desenho, ver
# `airtable_inventario_prestacao.py`); ingerir conteúdo sob atribuição
# de cliente inventada seria pior que simplesmente não ingerir.
_TABELA_E_CAMPO_POR_TIPO: Mapping[str, Tuple[str, str]] = {
    TIPO_HOLERITE: (TABLE_HOL, F_HOL_PDF),
    TipoDocumental.EXTRATO_CLIENTE.value: (TABLE_EXTRATO, F_EXT_PDF),
    TIPO_FGTS: (TABLE_FGTS, F_FGTS_ANEXO),
}


class CompetenciaInvalida(ValueError):
    """`competencia_base` fora do formato AAAA-MM."""


def parse_competencia(competencia: str) -> Tuple[int, int]:
    """Validação local e pequena -- mesma disciplina de duplicação já
    usada em `airtable_holerites_prestacao._folha_mensal`/
    `airtable_inventario_prestacao._folha_mensal`. Este módulo
    (`documental/importacao_lote/`) não importa `orquestrador/` (uma
    camada acima dele) só para reusar uma validação de 5 linhas --
    custo aceito e documentado, mesmo padrão já aplicado nos dois
    módulos citados."""
    try:
        ano_texto, mes_texto = competencia.split('-', maxsplit=1)
        ano, mes = int(ano_texto), int(mes_texto)
    except (AttributeError, TypeError, ValueError) as exc:
        raise CompetenciaInvalida(
            f'competência deve ser AAAA-MM (recebido: {competencia!r})'
        ) from exc
    if len(ano_texto) != 4 or len(mes_texto) != 2 or not 1 <= mes <= 12:
        raise CompetenciaInvalida(f'competência deve ser AAAA-MM (recebido: {competencia!r})')
    return ano, mes


@dataclass(frozen=True)
class FalhaIngestaoAnexo:
    """Uma falha ISOLADA de 1 anexo -- nunca derruba o lote (ver
    `ingerir_documentos_lote`). Nunca carrega `nome_original` nem
    qualquer outro dado pessoal: só o id do registro Airtable (não é
    dado pessoal, é um identificador técnico), a tabela e o motivo
    técnico sanitizado."""

    registro_airtable_id: str
    tabela: str
    indice_anexo: int
    motivo: str


@dataclass(frozen=True)
class ResumoIngestaoLote:
    """Resumo final -- a única saída que a CLI imprime. Nenhum campo
    aqui pode conter CPF/nome (ver CLAUDE.md §6)."""

    cliente_id: str
    competencia_base: str
    anexos_encontrados: int = 0
    documentos_ingeridos: int = 0
    documentos_ja_existentes: int = 0
    registros_sem_anexo: Tuple[str, ...] = field(default_factory=tuple)
    falhas: Tuple[FalhaIngestaoAnexo, ...] = field(default_factory=tuple)

    def como_dict(self) -> dict:
        return {
            'cliente_id': self.cliente_id,
            'competencia_base': self.competencia_base,
            'anexos_encontrados': self.anexos_encontrados,
            'documentos_ingeridos': self.documentos_ingeridos,
            'documentos_ja_existentes': self.documentos_ja_existentes,
            'registros_sem_anexo': list(self.registros_sem_anexo),
            'total_falhas': len(self.falhas),
            'falhas': [
                {
                    'registro_airtable_id': falha.registro_airtable_id,
                    'tabela': falha.tabela,
                    'indice_anexo': falha.indice_anexo,
                    'motivo': falha.motivo,
                }
                for falha in self.falhas
            ],
        }


class FalhaDownloadAnexo(Exception):
    """O download dos bytes reais do anexo (a partir da URL do
    Airtable) falhou. A mensagem NUNCA inclui a URL -- o nome do
    arquivo no Airtable costuma conter o nome da pessoa (ex.: "João
    Silva - Holerite.pdf"), e a URL de anexo o reproduz."""


def _baixar_anexo_padrao(url: str, timeout: int = 60) -> bytes:
    """Downloader real, injetável (testes nunca usam este caminho).
    Import local de `requests` -- único ponto deste módulo acoplado ao
    cliente HTTP, mesma disciplina de `airtable_leitura.py`."""
    import requests

    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        raise FalhaDownloadAnexo(
            f'falha ao baixar anexo (status={status}, tipo={type(exc).__name__}) -- '
            f'URL omitida do erro (pode conter nome de pessoa no nome do arquivo)'
        ) from None
    return r.content


def _tipo_documental_suportado(tipo_documental: str) -> bool:
    return tipo_documental in _TABELA_E_CAMPO_POR_TIPO


def coletar_itens_cliente_competencia(
    *,
    leitor: LeitorAirtableSomenteLeitura,
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
) -> Tuple:
    """Reaproveita os MESMOS compositores de inventário real já usados
    pela Prestação -- nunca reimplementa resolução de vínculo/Folha
    Mensal. Guias/DCTFWeb (broadcast, sem vínculo de cliente real) são
    descartados aqui (ver módulo, docstring de topo)."""
    fonte_vinculos = FonteVinculosPrestacaoAirtableShadow(leitor)
    itens_holerite = FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos).listar(cliente, competencia)
    itens_extrato_fgts_guias = FonteInventarioPrestacaoAirtableShadow(leitor).listar(cliente, competencia)
    itens_extrato_fgts = tuple(
        item for item in itens_extrato_fgts_guias if _tipo_documental_suportado(item.tipo_documental)
    )
    return tuple(itens_holerite) + itens_extrato_fgts


def ingerir_documentos_lote(
    *,
    leitor: LeitorAirtableSomenteLeitura,
    armazenamento: ArmazenamentoArquivos,
    repositorio_documentos: RepositorioDocumentos,
    repositorio_historico: RepositorioHistorico,
    cliente_id: str,
    competencia_base: str,
    baixar_anexo: Callable[[str], bytes] = _baixar_anexo_padrao,
) -> ResumoIngestaoLote:
    """Ingestão REAL em lote -- UMA invocação cobre TODOS os documentos
    encontrados para `cliente_id` + `competencia_base` (nunca processa
    "tudo"; fail-closed por desenho, mesmo princípio de
    `compor_dependencias_a_partir_do_ambiente`).

    Idempotente por hash (via `AdaptadorEntradaDuravel`): o mesmo
    conteúdo, reingerido, nunca duplica `Documento`. A falha de 1 anexo
    é isolada (`FalhaIngestaoAnexo`) e nunca interrompe o processamento
    dos demais -- ver item 7 do pedido."""
    if not cliente_id or not cliente_id.strip():
        raise ValueError('cliente_id é obrigatório')
    ano, mes = parse_competencia(competencia_base)
    competencia_normalizada = f'{ano:04d}-{mes:02d}'
    cliente = ReferenciaCanonica('CLIENTE', cliente_id.strip())
    competencia = ReferenciaCanonica('COMPETENCIA', competencia_normalizada)

    itens = coletar_itens_cliente_competencia(leitor=leitor, cliente=cliente, competencia=competencia)

    por_tabela_campo: Dict[Tuple[str, str], List] = {}
    for item in itens:
        chave = _TABELA_E_CAMPO_POR_TIPO[item.tipo_documental]
        por_tabela_campo.setdefault(chave, []).append(item)

    anexos_por_registro: Dict[str, Tuple[dict, ...]] = {}
    tabela_por_registro: Dict[str, str] = {}
    for (tabela, campo), itens_da_tabela in por_tabela_campo.items():
        registro_ids = [item.documento_id for item in itens_da_tabela]
        for registro_id in registro_ids:
            tabela_por_registro[registro_id] = tabela
        anexos_por_registro.update(buscar_anexos_por_registro(leitor, tabela, campo, registro_ids))

    adaptador = AdaptadorEntradaDuravel(repositorio_documentos, repositorio_historico, armazenamento)

    registros_sem_anexo: List[str] = []
    falhas: List[FalhaIngestaoAnexo] = []
    anexos_encontrados = 0
    documentos_ingeridos = 0
    documentos_ja_existentes = 0

    registros_vistos: Set[str] = set()
    for item in itens:
        registro_id = item.documento_id
        if registro_id in registros_vistos:
            # Mesmo registro Airtable já processado nesta execução --
            # pode acontecer se o mesmo colaborador/registro resolver
            # para o cliente pedido por mais de um caminho de vínculo.
            # Nunca reprocessa; nunca conta duas vezes.
            continue
        registros_vistos.add(registro_id)

        tabela = tabela_por_registro.get(registro_id, '')
        anexos = anexos_por_registro.get(registro_id, ())
        if not anexos:
            registros_sem_anexo.append(registro_id)
            continue

        for indice, anexo in enumerate(anexos):
            anexos_encontrados += 1
            try:
                url = anexo.get('url')
                if not url:
                    raise FalhaDownloadAnexo('anexo sem URL no Airtable')
                conteudo = baixar_anexo(url)
                if not conteudo:
                    raise FalhaDownloadAnexo('conteúdo vazio após download')

                hash_sha256 = hashlib.sha256(conteudo).hexdigest()
                ja_existia = repositorio_documentos.buscar_por_hash(hash_sha256) is not None

                nome_original = anexo.get('filename') or f'{registro_id}-{indice}.bin'
                mime_type = anexo.get('type') or 'application/octet-stream'
                adaptador.registrar_entrada(
                    conteudo=conteudo,
                    nome_original=nome_original,
                    mime_type=mime_type,
                    origem=f'airtable:{tabela}:{registro_id}',
                    metadados={
                        'airtable_tabela': tabela,
                        'airtable_registro_id': registro_id,
                        'tipo_documental': item.tipo_documental,
                        'cliente_id': cliente_id,
                        'competencia_base': competencia_normalizada,
                    },
                )
                if ja_existia:
                    documentos_ja_existentes += 1
                else:
                    documentos_ingeridos += 1
            except Exception as exc:
                falhas.append(FalhaIngestaoAnexo(
                    registro_airtable_id=registro_id, tabela=tabela,
                    indice_anexo=indice, motivo=str(exc),
                ))

    return ResumoIngestaoLote(
        cliente_id=cliente_id,
        competencia_base=competencia_normalizada,
        anexos_encontrados=anexos_encontrados,
        documentos_ingeridos=documentos_ingeridos,
        documentos_ja_existentes=documentos_ja_existentes,
        registros_sem_anexo=tuple(sorted(registros_sem_anexo)),
        falhas=tuple(falhas),
    )
