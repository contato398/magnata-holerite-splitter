"""J4 -- composição REAL do contexto da Prestação para UM cliente e UMA
competência ("Prestação do cliente X -- competência Y").

Fecha a peça que faltava (auditoria Gate J, §8 J4; docstring de
`orquestrador/executar_prestacao_contato_ate_pending_shadow_v1.py`: "a
composição real de `ContextoComposicaoPrestacao` ainda não existe").
Não cria motor, fonte nem regra: só LIGA peças que já existem.

Decisão J2 (missão "Prestação -> esteira documental inteligente"):
fonte INTERNA primeiro; Airtable só como PONTE somente leitura, através
dos adapters já existentes, onde não existe fonte interna equivalente.

| Campo | Fonte |
|---|---|
| requisitos | cadastro canônico em código (`CADASTRO_REQUISITOS_PRESTACAO_V2`) -- interno |
| competência esperada | `POLITICA_COMPETENCIA_PRESTACAO_V1` -- interno |
| documentos / histórico / lotes / execuções | Postgres (modulo01, execucoes_prestacao) -- interno |
| arquivos | armazenamento injetado (S3 em produção) -- interno |
| documentos derivados de PDF composto | porta oficial `AdaptadorEntradaDuravel` -- interno |
| unidade/posto | alocação histórica Postgres, com o snapshot Airtable só como fonte corrente -- interno primeiro |
| clientes ativos, colaboradores esperados, vínculos, candidatos a colaborador (CPF), cliente direto por CNPJ | Airtable somente leitura -- ponte (não há fonte interna equivalente hoje) |
| localização | índice J3 com frescor (quando disponível) + busca por conteúdo; "e-mail mais recente vale" aplicado depois da conferência |

Nenhuma leitura de ambiente aqui além de `compor_a_partir_do_ambiente`,
que só REUTILIZA os compositores já existentes (conexão Postgres, S3,
leitor Airtable). Falha de configuração é sempre erro explícito.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

from magnata_os.central.localizacao import FonteNomeada, data_recebimento_email

from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    CADASTRO_REQUISITOS_PRESTACAO_V2,
    FonteRequisitosPrestacaoCanonica,
)
from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    ContextoCicloPrestacao,
    PoliticaCompetenciaPrestacao,
)
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import ContextoComposicaoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_indice_com_frescor import FonteIndiceComFrescor
from magnata_os.classificacao.fonte_candidatos_por_conteudo import FonteCandidatosPorConteudo
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE


class LeitorAirtableComCache:
    """Mesma superfície somente leitura do leitor Airtable, com cache POR
    EXECUÇÃO das listagens completas usadas por página de documento
    (`listar_clientes` na resolução de cliente por CNPJ,
    `listar_funcionarios` nos candidatos). Sem cache, a busca por conteúdo
    faria uma chamada à API por página lida. `listar_registros` (consultas
    filtradas) nunca é cacheado. Nunca escreve."""

    def __init__(self, leitor: object) -> None:
        self._leitor = leitor
        self._clientes = None
        self._funcionarios = None

    def listar_clientes(self):
        if self._clientes is None:
            self._clientes = list(self._leitor.listar_clientes())
        return self._clientes

    def listar_funcionarios(self):
        if self._funcionarios is None:
            self._funcionarios = list(self._leitor.listar_funcionarios())
        return self._funcionarios

    def listar_registros(self, *args, **kwargs):
        return self._leitor.listar_registros(*args, **kwargs)


class ClienteNaoAtivo(Exception):
    """O cliente pedido não está ativo na fonte de clientes -- nunca é
    fabricado como ativo."""


@dataclass(frozen=True)
class FonteClienteUnico:
    """Restringe a fonte de clientes ativos a UM cliente. Se ele não
    estiver ativo, não devolve nada (fail-closed) -- quem compõe já
    verificou antes com `verificar_cliente_ativo`."""

    fonte: object
    cliente: ReferenciaCanonica

    def listar_ativos(self, contexto: Optional[ContextoCicloPrestacao] = None) -> Tuple[ReferenciaCanonica, ...]:
        return tuple(c for c in self.fonte.listar_ativos(contexto) if c == self.cliente)


@dataclass(frozen=True)
class DependenciasPrestacaoReal:
    """Tudo que a composição precisa, já construído. Em produção vem de
    `compor_a_partir_do_ambiente`; em teste, de fakes."""

    leitor_airtable: object
    repositorio_documentos: object
    repositorio_historico: object
    repositorio_lotes: object
    repositorio_execucoes_prestacao: object
    armazenamento: object
    fonte_unidade_posto_historica: object
    indice_documental: Optional[object] = None
    cnpj_proprio: Optional[str] = None
    """CNPJ da própria Magnata, ignorado ao identificar o cliente de um
    documento (evita que documento emitido pela Magnata resolva para ela
    mesma se ela estiver cadastrada como cliente)."""
    conexao: Optional[object] = None
    """Conexão a fechar ao final (`fechar_dependencias`)."""
    motor_ocr: Optional[object] = None
    """Porta `MotorOcr`; `None` enquanto nenhum motor estiver instalado."""
    repositorio_estados_esteira: Optional[object] = None
    """Só para a coleta de e-mail (pipeline do Módulo 01)."""


def parse_competencia(competencia: str) -> Tuple[int, int]:
    try:
        ano, mes = (int(p) for p in competencia.split('-'))
    except ValueError as exc:
        raise ValueError(f'competência deve ser AAAA-MM (recebido: {competencia!r})') from exc
    if not 1 <= mes <= 12:
        raise ValueError(f'mês inválido na competência {competencia!r}')
    return ano, mes


def montar_contexto_prestacao(
    *,
    cliente_id: str,
    competencia_base: str,
    dependencias: DependenciasPrestacaoReal,
    politica_competencia: PoliticaCompetenciaPrestacao = POLITICA_COMPETENCIA_PRESTACAO_V1,
    competencia_snapshot_airtable_comprovada: Optional[Tuple[int, int]] = None,
) -> ContextoComposicaoPrestacao:
    """Monta o contexto REAL para um cliente e uma competência-base.

    `competencia_snapshot_airtable_comprovada`: só informar quando o
    operador SABE que o vínculo Funcionário->Local lido hoje no Airtable
    vale para aquela competência (ver adapter de unidade/posto). Sem
    isso, unidade/posto só resolve pela alocação histórica interna --
    nunca por um snapshot sem prova de vigência.
    """
    from magnata_os.documental.importacao_lote.adapters.airtable_cliente_direto_documento import (
        FonteClienteDiretoDocumentoAirtableShadow,
    )
    from magnata_os.documental.importacao_lote.adapters.airtable_clientes_prestacao import (
        FonteClientesPrestacaoAirtable,
    )
    from magnata_os.documental.importacao_lote.adapters.airtable_colaboradores_esperados_prestacao import (
        FonteColaboradoresEsperadosPrestacaoAirtableShadow,
    )
    from magnata_os.documental.importacao_lote.adapters.airtable_unidade_posto_prestacao import (
        FonteUnidadePostoPrestacaoAirtableShadow,
    )
    from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
        FonteVinculosPrestacaoAirtableShadow,
    )
    from magnata_os.documental.modulo01.adaptador_entrada_duravel import AdaptadorEntradaDuravel

    from magnata_os.classificacao.fonte_unidade_posto_com_prioridade_historica import (
        FonteUnidadePostoPrestacaoComPrioridadeHistorica,
    )

    if not cliente_id or not cliente_id.strip():
        raise ValueError('cliente_id é obrigatório')
    ano, mes = parse_competencia(competencia_base)
    cliente = ReferenciaCanonica('CLIENTE', cliente_id.strip())
    d = dependencias
    leitor = LeitorAirtableComCache(d.leitor_airtable)

    fonte_clientes = FonteClientesPrestacaoAirtable(leitor)
    ciclo = ContextoCicloPrestacao(competencia_base=(ano, mes))
    if cliente not in fonte_clientes.listar_ativos(ciclo):
        raise ClienteNaoAtivo(f'cliente {cliente.entidade_id} não está ativo')

    competencia_esperada = politica_competencia.competencia_esperada_para(ciclo, cliente, TIPO_HOLERITE)
    if competencia_esperada is None:
        raise ValueError(f'sem competência esperada para o cliente {cliente.entidade_id}')

    candidatos = tuple(leitor.listar_funcionarios())
    fonte_cliente_direto = FonteClienteDiretoDocumentoAirtableShadow(leitor, cnpj_excluido=d.cnpj_proprio)

    # Localização: busca por conteúdo SEM critério de versão (ela devolve
    # todos os documentos da pessoa/cliente, de todos os tipos e meses);
    # "o e-mail mais recente vale" é aplicado DEPOIS da conferência, entre
    # os elegíveis da mesma necessidade (`data_versao_documento`).
    # Com índice J3 disponível, ele é lido COM FRESCOR: candidatos do
    # índice + busca por conteúdo só entre documentos registrados depois
    # deles -- versão corrigida reenviada nunca fica invisível
    # (`fonte_candidatos_indice_com_frescor.py`).
    conteudo = FonteCandidatosPorConteudo(
        d.repositorio_documentos, d.armazenamento, candidatos, fonte_cliente_direto, motor_ocr=d.motor_ocr,
    )
    fontes = (
        (FonteNomeada('indice_com_frescor', FonteIndiceComFrescor(d.indice_documental, d.repositorio_documentos, conteudo)),)
        if d.indice_documental is not None
        else (FonteNomeada('conteudo', conteudo),)
    )

    return ContextoComposicaoPrestacao(
        competencia_base=f'{ano:04d}-{mes:02d}',
        fonte_clientes=FonteClienteUnico(fonte_clientes, cliente),
        fonte_requisitos=FonteRequisitosPrestacaoCanonica(CADASTRO_REQUISITOS_PRESTACAO_V2),
        repositorio_execucoes=d.repositorio_execucoes_prestacao,
        requisitos_base=CADASTRO_REQUISITOS_PRESTACAO_V2.requisitos_base_documentais(),
        competencias_por_cliente={
            cliente: ReferenciaCanonica('COMPETENCIA', f'{competencia_esperada[0]:04d}-{competencia_esperada[1]:02d}'),
        },
        politica_competencia=politica_competencia,
        fonte_colaboradores_esperados=FonteColaboradoresEsperadosPrestacaoAirtableShadow(leitor),
        repositorio_documentos=d.repositorio_documentos,
        armazenamento_arquivos=d.armazenamento,
        tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
        fontes_localizacao=fontes,
        data_versao_documento=data_recebimento_email(d.repositorio_lotes),
        motor_ocr=d.motor_ocr,
        candidatos_colaborador=candidatos,
        fonte_vinculos=FonteVinculosPrestacaoAirtableShadow(leitor),
        indice_documental=d.indice_documental,
        entrada_documentos_derivados=AdaptadorEntradaDuravel(
            d.repositorio_documentos, d.repositorio_historico, d.armazenamento,
        ),
        fonte_unidade_posto=FonteUnidadePostoPrestacaoComPrioridadeHistorica(
            d.fonte_unidade_posto_historica,
            FonteUnidadePostoPrestacaoAirtableShadow(leitor, competencia_snapshot_airtable_comprovada),
        ),
        fonte_cliente_direto=fonte_cliente_direto,
    )


def compor_dependencias_a_partir_do_ambiente(conexao=None) -> DependenciasPrestacaoReal:
    """Reutiliza os compositores existentes: `abrir_conexao`
    (`DATABASE_URL`), o armazenamento S3 de `ciclo_producao_v1`
    (`ORQUESTRADOR_S3_BUCKET`) e o leitor Airtable somente leitura
    (`AIRTABLE_API_KEY`). Sem configuração: erro explícito, nunca
    default silencioso. Índice documental J3: não composto aqui até a
    migration 0011 ser aplicada (gate humano)."""
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres
    from magnata_os.documental.importacao_lote.adapters.airtable_leitura import LeitorAirtableSomenteLeitura
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import (
        RepositorioDocumentosPostgres,
        RepositorioHistoricoPostgres,
    )
    from magnata_os.documental.modulo01.adapters.postgres_repositorio_esteira import (
        RepositorioEstadosEsteiraPostgres,
        RepositorioLotesPostgres,
    )
    from .ciclo_producao_v1 import _compor_armazenamento_a_partir_do_ambiente

    from magnata_os.classificacao.adapters.postgres_execucoes_prestacao import RepositorioExecucoesPrestacaoPostgres

    chave_airtable = os.environ.get('AIRTABLE_API_KEY', '').strip()
    if not chave_airtable:
        raise RuntimeError('AIRTABLE_API_KEY ausente -- ponte somente leitura do Airtable é obrigatória nesta fase')
    armazenamento = _compor_armazenamento_a_partir_do_ambiente()  # antes da conexão: falha sem conexão aberta
    conexao = conexao if conexao is not None else abrir_conexao()
    return DependenciasPrestacaoReal(
        leitor_airtable=LeitorAirtableSomenteLeitura(chave_airtable),
        repositorio_documentos=RepositorioDocumentosPostgres(conexao),
        repositorio_historico=RepositorioHistoricoPostgres(conexao),
        repositorio_lotes=RepositorioLotesPostgres(conexao),
        repositorio_execucoes_prestacao=RepositorioExecucoesPrestacaoPostgres(conexao),
        armazenamento=armazenamento,
        fonte_unidade_posto_historica=RepositorioAlocacaoPostgres(conexao),
        cnpj_proprio=os.environ.get('MAGNATA_CNPJ_PROPRIO', '').strip() or None,
        conexao=conexao,
        repositorio_estados_esteira=RepositorioEstadosEsteiraPostgres(conexao),
    )


def fechar_dependencias(dependencias: DependenciasPrestacaoReal) -> None:
    conexao = dependencias.conexao
    if conexao is not None:
        conexao.close()
