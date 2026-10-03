"""Fronteira HTTP da ingestão REAL em lote (Modulo 01 -- painel
operacional, "eliminar dependência de Shell/terminal").

O usuário (dono do produto) decidiu desde o início da automação que
NUNCA quer precisar entrar no Shell do Render ou digitar comando de
terminal para operar o sistema. `scripts/ingerir_documentos_lote_real_cli.py`
(PR #221) provou a lógica; este módulo expõe a MESMA lógica para o
painel web clicar, sem duplicar nada -- só traduz
`Sujeito`/parâmetros HTTP <-> `ingerir_documentos_lote`.

Isolado de `blueprint_esteira.py` de propósito, mesma disciplina de
`api_contexto.py` (Fase 5, "dados reais"): quem monta dependências de
ambiente/chama o núcleo fica aqui, perto do próprio núcleo de
ingestão (`importacao_lote/`); o blueprint em `modulo01/adapters/`
continua só traduzindo HTTP <-> estes tipos, nunca reimplementando
composição de dependências reais.

Autorização: reaproveita a MESMA hierarquia de erro
(`magnata_os.documental.modulo01.api.erros.ApiError`) e o MESMO
mecanismo de perfil (`exigir_perfil`/`Sujeito`/`Perfil`, via o shim
`modulo01.api.autorizacao`) já usados pelos outros 9 endpoints da
esteira -- nenhuma autenticação/autorização nova inventada aqui. A
sessão em si (quem é o sujeito autenticado) continua sendo validada
pelo decorator `exigir_sessao_com_perfil` no blueprint, exatamente como
nos outros endpoints -- este módulo só recebe o `Sujeito` já
construído e aplica a regra fina de perfil (`PERMISSAO_INGESTAO_LOTE`),
o mesmo padrão já documentado em `blueprint_esteira.py`.

Nenhum dado pessoal na resposta: o retorno é exatamente
`ResumoIngestaoLote.como_dict()` (contagens, ids de registro Airtable,
nunca CPF/nome -- ver `ingestao_documentos_lote_real.py`).

Limitação declarada (V1, ver docs/decisoes/painel-ingestao-documentos-lote-ui-v1.md):
esta chamada é SÍNCRONA e BLOQUEANTE -- a requisição HTTP só responde
quando TODOS os documentos do cliente+competência tiverem sido
processados. Para poucos documentos isso é aceitável; para um lote
grande, o navegador fica esperando minutos com a aba presa nessa
requisição. Aceito para V1 (nenhum worker assíncrono/fila foi
construído); registrado como risco, não escondido.

Composição de dependências REAIS duplicada aqui, não importada de
`magnata_os.orquestrador.composicao_prestacao_real_v1` (que já faz
exatamente isto, reusado pelo CLI do PR #221): este módulo vive em
`magnata_os/documental/` e `documental/` nunca pode importar
`magnata_os.orquestrador` (regra de dependência acíclica verificada em
`tests/test_magnata_os_arquitetura_dependencias_aciclicas.py` --
`orquestrador` coordena/compõe sobre `documental`, nunca o contrário).
Mesma disciplina de duplicação já aceita e documentada em
`importacao_lote/CLAUDE.md` ("IDs de tabela/campo do Airtable
duplicados aqui, não importados de app.py... custo aceito"): os dois
compositores (este e o do orquestrador) precisam ser atualizados
juntos se o ambiente mudar -- registrado, não escondido. Reusa as
MESMAS variáveis de ambiente (`AIRTABLE_API_KEY`, `DATABASE_URL`,
`ORQUESTRADOR_S3_BUCKET`/`_PREFIXO`/`_ENDPOINT_URL`/`_REGION`) e os
MESMOS adapters concretos (`LeitorAirtableSomenteLeitura`,
`abrir_conexao`, `ArmazenamentoArquivosS3`) -- nenhum provedor novo,
nenhuma credencial nova.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, FrozenSet

from magnata_os.documental.modulo01.adapters.conexao import (
    ConfiguracaoBancoAusente,
    FalhaConexaoBanco,
    abrir_conexao,
)
from magnata_os.documental.modulo01.adapters.postgres_repositorio import (
    RepositorioDocumentosPostgres,
    RepositorioHistoricoPostgres,
)
from magnata_os.documental.modulo01.adapters.s3_armazenamento import ArmazenamentoArquivosS3
from magnata_os.documental.modulo01.api.autorizacao import Perfil, Sujeito, exigir_perfil
from magnata_os.documental.modulo01.api.erros import ApiError, ErroInternoNaoExposto

from .adapters.airtable_leitura import LeitorAirtableSomenteLeitura
from .ingestao_documentos_lote_real import (
    CompetenciaInvalida,
    ResumoIngestaoLote,
    ingerir_documentos_lote,
    parse_competencia,
)


@dataclass(frozen=True)
class DependenciasIngestaoLoteHttp:
    """Só o que `ingerir_documentos_lote` precisa -- subconjunto de
    `DependenciasPrestacaoReal` (orquestrador), composto de novo aqui
    por causa da regra de dependência acíclica (ver docstring do
    módulo). `conexao`: fechada por `fechar_dependencias_reais`."""

    leitor_airtable: object
    armazenamento: object
    repositorio_documentos: object
    repositorio_historico: object
    conexao: object


def _compor_armazenamento_s3_a_partir_do_ambiente() -> ArmazenamentoArquivosS3:
    """Mesma composição de
    `magnata_os.orquestrador.ciclo_producao_v1._compor_armazenamento_a_partir_do_ambiente`
    -- duplicada aqui pela mesma razão (ver docstring do módulo), nunca
    importada de lá. Mesmas variáveis de ambiente, mesmo comportamento
    (inclusive o endpoint customizado opcional, S3/R2)."""
    bucket = (os.environ.get('ORQUESTRADOR_S3_BUCKET') or '').strip()
    if not bucket:
        raise RuntimeError(
            'ORQUESTRADOR_S3_BUCKET não configurado -- a ingestão em lote '
            'nunca infere bucket por padrão (fail-closed).'
        )
    prefixo = os.environ.get('ORQUESTRADOR_S3_PREFIXO', 'documentos/')
    endpoint_url = (os.environ.get('ORQUESTRADOR_S3_ENDPOINT_URL') or '').strip()
    import boto3  # import local -- mesma disciplina do compositor original

    if endpoint_url:
        regiao = (os.environ.get('ORQUESTRADOR_S3_REGION') or '').strip() or 'us-east-1'
        cliente = boto3.client('s3', endpoint_url=endpoint_url, region_name=regiao)
    else:
        cliente = boto3.client('s3')
    return ArmazenamentoArquivosS3(cliente, bucket=bucket, prefixo=prefixo)


def compor_dependencias_ingestao_lote_a_partir_do_ambiente() -> DependenciasIngestaoLoteHttp:
    """Compõe Airtable (somente leitura) + S3/R2 + Postgres reais a
    partir do ambiente -- sem configuração, erro explícito (nunca
    default silencioso), mesmo princípio de
    `compor_dependencias_a_partir_do_ambiente` (orquestrador)."""
    chave_airtable = os.environ.get('AIRTABLE_API_KEY', '').strip()
    if not chave_airtable:
        raise RuntimeError(
            'AIRTABLE_API_KEY ausente -- ponte somente leitura do Airtable é obrigatória nesta fase'
        )
    armazenamento = _compor_armazenamento_s3_a_partir_do_ambiente()  # antes da conexao, mesma ordem do orquestrador
    conexao = abrir_conexao()
    return DependenciasIngestaoLoteHttp(
        leitor_airtable=LeitorAirtableSomenteLeitura(chave_airtable),
        armazenamento=armazenamento,
        repositorio_documentos=RepositorioDocumentosPostgres(conexao),
        repositorio_historico=RepositorioHistoricoPostgres(conexao),
        conexao=conexao,
    )


def fechar_dependencias_ingestao_lote(dependencias: DependenciasIngestaoLoteHttp) -> None:
    conexao = getattr(dependencias, 'conexao', None)
    if conexao is not None:
        conexao.close()

# Mesmo conjunto de `PERMISSAO_FILA_OPERACIONAL`
# (magnata_os/documental/modulo01/api/handlers.py) -- duplicado aqui,
# não importado de lá: esta ação pertence ao módulo de importação em
# lote, não à esteira em si, e handlers.py não é (nem deve virar) ponto
# de composição de outros módulos. Mesma disciplina já documentada em
# `importacao_lote/CLAUDE.md` ("IDs de tabela/campo do Airtable
# duplicados aqui, não importados de app.py").
# AUDITOR fica de fora de propósito: disparar ingestão é uma ação
# operacional (escreve conteúdo real no armazenamento/Postgres), nunca
# uma consulta -- o mesmo raciocínio que já separa
# PERMISSAO_LEITURA_GERAL de PERMISSAO_FILA_OPERACIONAL em handlers.py.
PERMISSAO_INGESTAO_LOTE: FrozenSet[Perfil] = frozenset({Perfil.OPERACIONAL, Perfil.GESTOR})


class ParametrosIngestaoInvalidos(ApiError):
    """`cliente`/`competencia` ausentes ou em formato inválido."""

    codigo = 'PARAMETROS_INGESTAO_INVALIDOS'
    status_http = 400


class ConfiguracaoIngestaoAusente(ApiError):
    """Ambiente sem `AIRTABLE_API_KEY`/`DATABASE_URL`/bucket configurados
    -- nunca finge sucesso nem cai para um caminho simulado. Mensagem
    sempre a partir de uma excecao já sanitizada (RuntimeError/
    ConfiguracaoBancoAusente explícitas dos próprios compositores,
    nunca a mensagem crua de uma excecao de infraestrutura)."""

    codigo = 'CONFIGURACAO_INGESTAO_AUSENTE'
    status_http = 503


def executar_ingestao_lote_http(
    sujeito: Sujeito,
    cliente_id: str,
    competencia_base: str,
    *,
    compor_dependencias: Callable[[], DependenciasIngestaoLoteHttp] = compor_dependencias_ingestao_lote_a_partir_do_ambiente,
    fechar: Callable[[DependenciasIngestaoLoteHttp], None] = fechar_dependencias_ingestao_lote,
    ingerir: Callable[..., ResumoIngestaoLote] = ingerir_documentos_lote,
) -> dict:
    """Valida permissão + parâmetros, compõe as dependências REAIS do
    ambiente (Airtable/S3/Postgres -- as MESMAS do CLI, PR #221),
    executa `ingerir_documentos_lote` e devolve o resumo já em dict
    (`ResumoIngestaoLote.como_dict()`). `compor_dependencias`/`fechar`/
    `ingerir` são injetáveis -- todo teste deste módulo substitui os 3,
    nunca toca Airtable/S3/Postgres real."""
    exigir_perfil(sujeito, PERMISSAO_INGESTAO_LOTE)

    if not cliente_id or not str(cliente_id).strip():
        raise ParametrosIngestaoInvalidos('O campo "cliente" (id do registro Airtable) é obrigatório.')
    try:
        parse_competencia(competencia_base or '')
    except CompetenciaInvalida as exc:
        raise ParametrosIngestaoInvalidos(str(exc)) from exc

    try:
        dependencias = compor_dependencias()
    except (RuntimeError, ConfiguracaoBancoAusente) as exc:
        raise ConfiguracaoIngestaoAusente(
            f'Ingestão em lote não está configurada neste ambiente: {exc}'
        ) from exc
    except FalhaConexaoBanco as exc:
        raise ErroInternoNaoExposto() from exc

    try:
        resumo = ingerir(
            leitor=dependencias.leitor_airtable,
            armazenamento=dependencias.armazenamento,
            repositorio_documentos=dependencias.repositorio_documentos,
            repositorio_historico=dependencias.repositorio_historico,
            cliente_id=cliente_id,
            competencia_base=competencia_base,
        )
    except (ValueError, CompetenciaInvalida) as exc:
        raise ParametrosIngestaoInvalidos(str(exc)) from exc
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 -- fronteira que nunca vaza detalhe tecnico (ver erros.py)
        raise ErroInternoNaoExposto() from exc
    finally:
        fechar(dependencias)

    return resumo.como_dict()
