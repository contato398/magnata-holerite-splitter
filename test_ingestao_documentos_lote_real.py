"""Testes de `ingestao_documentos_lote_real` (missão "INGESTÃO DE
DOCUMENTO EM LOTE REAL") -- nunca tocam rede real: o downloader de
anexo é sempre um duplo de teste injetado (`baixar_anexo`), e o leitor
Airtable é sempre `_LeitorFake` (sem `requests`)."""
import hashlib

import pytest

from magnata_os.documental.importacao_lote.adapters.airtable_holerites_prestacao import (
    F_HOL_FUNC,
    TABLE_HOL,
)
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
    F_FGTS_CLIENTE,
    TABLE_FGTS,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (
    F_EXT_CLIENTE,
    TABLE_EXTRATO,
    TABLE_FUNC,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_LOCAIS,
)
from magnata_os.documental.importacao_lote.ingestao_documentos_lote_real import (
    F_EXT_PDF,
    F_FGTS_ANEXO,
    F_HOL_PDF,
    CompetenciaInvalida,
    FalhaDownloadAnexo,
    ingerir_documentos_lote,
    parse_competencia,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)

_CLIENTE_ID = 'rec_cliente'
_COMPETENCIA = '2026-07'


class _LeitorFake:
    """Devolve o conteúdo completo da tabela pedida, ignorando o filtro
    (mesma convenção já usada em `test_airtable_holerites_prestacao.py`)
    -- cada teste já monta só os registros relevantes por tabela."""

    def __init__(self, tabelas: dict):
        self._tabelas = tabelas
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        registros = list(self._tabelas.get(table_id, []))
        if filter_by_formula and 'RECORD_ID()' in filter_by_formula:
            # Filtros por Folha Mensal (inventários reais) passam direto,
            # como na convenção já usada em test_airtable_holerites_
            # prestacao.py -- só filtros por RECORD_ID() (vínculo e busca
            # de anexo, ambos deste módulo) são de fato aplicados aqui,
            # para que "funcionário sem vínculo" seja um caso real no fake.
            registros = [r for r in registros if f'"{r["id"]}"' in filter_by_formula]
        return registros


def _leitor(*, holerites=(), extratos=(), fgts=()):
    """Monta o vínculo Funcionário->Local->Cliente para `rec_func_a`
    (dono de qualquer Holerite nos fixtures), mais as tabelas
    documentais passadas por quem chama."""
    return _LeitorFake({
        TABLE_FUNC: [{'id': 'rec_func_a', 'fields': {F_FUNC_LOCAIS: ['rec_local_1']}}],
        TABLE_LOCAIS: [{'id': 'rec_local_1', 'fields': {F_LOCAL_CLIENTE: [_CLIENTE_ID]}}],
        TABLE_HOL: list(holerites),
        TABLE_EXTRATO: list(extratos),
        TABLE_FGTS: list(fgts),
    })


def _anexo(url: str, filename: str = 'documento.pdf', tipo: str = 'application/pdf') -> dict:
    return {'id': f'att_{url}', 'url': url, 'filename': filename, 'type': tipo}


def _dependencias():
    return {
        'armazenamento': ArmazenamentoArquivosEmMemoria(),
        'repositorio_documentos': RepositorioDocumentosEmMemoria(),
        'repositorio_historico': RepositorioHistoricoEmMemoria(),
    }


def _baixar_de(conteudos_por_url: dict):
    def _baixar(url: str) -> bytes:
        if url not in conteudos_por_url:
            raise FalhaDownloadAnexo('anexo indisponivel (status=404, tipo=HTTPError)')
        valor = conteudos_por_url[url]
        if isinstance(valor, Exception):
            raise valor
        return valor
    return _baixar


# ── parse_competencia ───────────────────────────────────────────────────

def test_parse_competencia_aceita_formato_valido():
    assert parse_competencia('2026-07') == (2026, 7)


def test_parse_competencia_rejeita_formato_invalido():
    with pytest.raises(CompetenciaInvalida):
        parse_competencia('07-2026')


# ── documento novo ──────────────────────────────────────────────────────

def test_documento_novo_e_ingerido_no_armazenamento_e_repositorio_fake():
    holerite = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a'], F_HOL_PDF: [_anexo('https://airtable.test/a1')]}}
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()
    conteudo = b'PDF holerite real'

    resumo = ingerir_documentos_lote(
        leitor=leitor,
        cliente_id=_CLIENTE_ID,
        competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({'https://airtable.test/a1': conteudo}),
        **deps,
    )

    assert resumo.anexos_encontrados == 1
    assert resumo.documentos_ingeridos == 1
    assert resumo.documentos_ja_existentes == 0
    assert resumo.falhas == ()

    hash_esperado = hashlib.sha256(conteudo).hexdigest()
    assert deps['repositorio_documentos'].buscar_por_hash(hash_esperado) is not None
    assert deps['armazenamento'].existe(hash_esperado)
    with deps['armazenamento'].abrir_leitura(hash_esperado) as arquivo:
        assert arquivo.read() == conteudo


# ── idempotência ─────────────────────────────────────────────────────────

def test_documento_ja_existente_mesmo_hash_e_idempotente_nunca_duplica():
    holerite = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a'], F_HOL_PDF: [_anexo('https://airtable.test/a1')]}}
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()
    conteudo = b'PDF holerite real'
    baixar = _baixar_de({'https://airtable.test/a1': conteudo})

    primeiro = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA, baixar_anexo=baixar, **deps,
    )
    segundo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA, baixar_anexo=baixar, **deps,
    )

    assert primeiro.documentos_ingeridos == 1 and primeiro.documentos_ja_existentes == 0
    assert segundo.documentos_ingeridos == 0 and segundo.documentos_ja_existentes == 1
    assert len(deps['repositorio_documentos'].listar_todos()) == 1


# ── lote com múltiplos documentos ────────────────────────────────────────

def test_lote_com_multiplos_documentos_todos_processados_numa_execucao():
    holerite = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a'], F_HOL_PDF: [_anexo('https://airtable.test/hol')]}}
    extrato = {'id': 'rec_ext_1', 'fields': {F_EXT_CLIENTE: [_CLIENTE_ID], F_EXT_PDF: [_anexo('https://airtable.test/ext')]}}
    fgts = {'id': 'rec_fgts_1', 'fields': {F_FGTS_CLIENTE: [_CLIENTE_ID], F_FGTS_ANEXO: [_anexo('https://airtable.test/fgts')]}}
    leitor = _leitor(holerites=[holerite], extratos=[extrato], fgts=[fgts])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({
            'https://airtable.test/hol': b'conteudo holerite',
            'https://airtable.test/ext': b'conteudo extrato',
            'https://airtable.test/fgts': b'conteudo fgts',
        }),
        **deps,
    )

    assert resumo.anexos_encontrados == 3
    assert resumo.documentos_ingeridos == 3
    assert resumo.falhas == ()
    assert len(deps['repositorio_documentos'].listar_todos()) == 3


def test_multiplos_anexos_no_mesmo_registro_sao_todos_processados():
    holerite = {
        'id': 'rec_hol_1',
        'fields': {
            F_HOL_FUNC: ['rec_func_a'],
            F_HOL_PDF: [_anexo('https://airtable.test/a1'), _anexo('https://airtable.test/a2')],
        },
    }
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({
            'https://airtable.test/a1': b'anexo 1',
            'https://airtable.test/a2': b'anexo 2',
        }),
        **deps,
    )

    assert resumo.anexos_encontrados == 2
    assert resumo.documentos_ingeridos == 2
    assert resumo.falhas == ()


# ── falha isolada ────────────────────────────────────────────────────────

def test_anexo_inacessivel_falha_isolada_nunca_derruba_o_lote():
    holerite_ok = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a'], F_HOL_PDF: [_anexo('https://airtable.test/ok')]}}
    extrato_quebrado = {'id': 'rec_ext_1', 'fields': {F_EXT_CLIENTE: [_CLIENTE_ID], F_EXT_PDF: [_anexo('https://airtable.test/corrompido')]}}
    leitor = _leitor(holerites=[holerite_ok], extratos=[extrato_quebrado])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({'https://airtable.test/ok': b'conteudo ok'}),
        **deps,
    )

    assert resumo.documentos_ingeridos == 1
    assert len(resumo.falhas) == 1
    falha = resumo.falhas[0]
    assert falha.registro_airtable_id == 'rec_ext_1'
    # A falha nunca inclui a URL (poderia conter nome de pessoa no nome do arquivo).
    assert 'corrompido' not in falha.motivo
    assert 'https://' not in falha.motivo


def test_anexo_sem_url_e_falha_isolada():
    holerite = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a'], F_HOL_PDF: [{'id': 'att_1', 'filename': 'sem_url.pdf'}]}}
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({}),
        **deps,
    )

    assert resumo.documentos_ingeridos == 0
    assert len(resumo.falhas) == 1


def test_registro_sem_nenhum_anexo_e_listado_separado_nunca_como_falha():
    holerite = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a'], F_HOL_PDF: []}}
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({}),
        **deps,
    )

    assert resumo.registros_sem_anexo == ('rec_hol_1',)
    assert resumo.falhas == ()
    assert resumo.anexos_encontrados == 0


# ── escopo fail-closed ───────────────────────────────────────────────────

def test_cliente_sem_vinculo_nao_ingere_nada():
    holerite = {'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_desconhecido'], F_HOL_PDF: [_anexo('https://airtable.test/a1')]}}
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({'https://airtable.test/a1': b'nunca deveria ser lido'}),
        **deps,
    )

    assert resumo.anexos_encontrados == 0
    assert resumo.documentos_ingeridos == 0
    assert len(deps['repositorio_documentos'].listar_todos()) == 0


def test_cliente_id_vazio_e_rejeitado_fail_closed():
    leitor = _leitor()
    with pytest.raises(ValueError):
        ingerir_documentos_lote(
            leitor=leitor, cliente_id='   ', competencia_base=_COMPETENCIA,
            baixar_anexo=_baixar_de({}), **_dependencias(),
        )


# ── nenhum dado pessoal no resumo ────────────────────────────────────────

def test_resumo_nunca_contem_nome_do_arquivo_nem_dado_pessoal():
    nome_pessoal = 'Fulano de Tal - Holerite.pdf'
    holerite = {
        'id': 'rec_hol_1',
        'fields': {
            F_HOL_FUNC: ['rec_func_a'],
            F_HOL_PDF: [_anexo('https://airtable.test/a1', filename=nome_pessoal)],
        },
    }
    leitor = _leitor(holerites=[holerite])
    deps = _dependencias()

    resumo = ingerir_documentos_lote(
        leitor=leitor, cliente_id=_CLIENTE_ID, competencia_base=_COMPETENCIA,
        baixar_anexo=_baixar_de({'https://airtable.test/a1': b'conteudo'}),
        **deps,
    )

    texto_resumo = repr(resumo.como_dict())
    assert 'Fulano' not in texto_resumo
    assert nome_pessoal not in texto_resumo
