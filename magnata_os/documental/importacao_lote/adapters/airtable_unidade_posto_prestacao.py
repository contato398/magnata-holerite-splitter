"""Adapter REAL read-only de UNIDADE_POSTO da prestação (missão
"MESCLAR PR #107 + CONSTRUIR OS DOIS ADAPTERS REAIS QUE BLOQUEIAM A
PRIMEIRA VALIDAÇÃO LIVE — FonteUnidadePostoPrestacao +
FonteCandidatosRelacaoDocumental"; corrigido pelo "ADENDO PRÉ-MERGE —
PR #108 — CORRIGIR TEMPORALIDADE DO SNAPSHOT").

Fecha a pendência mais antiga registrada (PR #106/#107, seção "adapters
reais"): implementa `FonteUnidadePostoPrestacao` (Protocol,
`classificacao/vinculo_unidade_prestacao.py`) sobre o MESMO
`LeitorAirtableSomenteLeitura` já existente, lendo o MESMO link
Funcionário→Local já lido por `FonteVinculosPrestacaoAirtableShadow`
(`F_FUNC_LOCAIS`, `TABLE_FUNC` — reaproveitados diretamente, nunca uma
segunda leitura da mesma tabela com IDs redefinidos). A diferença: este
adapter resolve o PRÓPRIO Local como UNIDADE_POSTO (identidade do
posto), nunca segue até o Cliente (isso continua exclusivamente em
`FonteVinculosPrestacaoAirtableShadow`).

CORREÇÃO (adendo pré-merge ao PR #108, achado real): a primeira versão
deste adapter usava `ContextoCicloPrestacao.competencia_base` (que
significa "qual competência este runner está processando agora") como
se fosse prova de que o SNAPSHOT do Airtable é válido para aquela
competência. São conceitos DIFERENTES e NUNCA podem ser confundidos
(nem no código, nem no nome, nem no ADR): o runner pode estar
processando a competência DOCUMENTAL de um cliente com deslocamento
(ex.: SKY Tatuí, ciclo-base Julho/2026 → competência documental
Junho/2026, `competencia_esperada_prestacao.py`) — o snapshot CORRENTE
de Funcionário→Local, lido HOJE, não prova nada sobre Junho.

Auditoria (§3 do adendo): nenhum contrato de "vigência de fonte"/
"as_of"/"snapshot_version" existe em nenhum lugar do repositório —
confirmado por busca. Menor contrato explícito criado NA BORDA (aqui,
no adapter -- nunca no motor semântico): `competencia_snapshot_
comprovada`, um parâmetro do construtor, DESACOPLADO de qualquer
`ContextoCicloPrestacao`. É responsabilidade de QUEM CONSTRÓI este
adapter fornecer esse valor só quando tiver prova real de que o
snapshot Airtable é válido para aquela competência EXATA (tipicamente:
a competência documental do cliente sem nenhum deslocamento, e a
leitura acontecendo dentro do próprio período) -- nunca inferido, nunca
copiado de `ContextoCicloPrestacao.competencia_base` sem essa prova.
Sem esse parâmetro (`None`, o default -- "sem evidência de vigência
nenhuma"), toda resolução cai em `NAO_ENCONTRADA` com o motivo
sanitizado já cadastrado (`MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA`,
`vinculo_unidade_prestacao.py`) — nunca `RESOLVIDA` "com ressalva",
nunca um falso positivo por coincidência de valores."""
from __future__ import annotations

from typing import Optional, Tuple

from magnata_os.classificacao.contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EvidenciaSanitizada,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.vinculo_unidade_prestacao import MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA

from .airtable_leitura import LeitorAirtableSomenteLeitura, TABLE_FUNC
from .airtable_link_utils import filtro_ids, ids_vinculados
from .airtable_vinculos_prestacao import F_FUNC_LOCAIS


def _formatar_competencia(ano_mes: Tuple[int, int]) -> str:
    """Mesmo formato canônico já usado em todo o repositório
    (`resolucao_semantica.py`/`ciclo_prestacao.py`/`inventario_
    prestacao_resultados.py`) -- nunca um segundo formato paralelo."""
    ano, mes = ano_mes
    return f'{ano:04d}-{mes:02d}'


class FonteUnidadePostoPrestacaoAirtableShadow:
    """Lê o link Funcionário→Local sem qualquer escrita.

    `competencia_snapshot_comprovada`: a ÚNICA competência para a qual
    quem construiu este adapter tem prova real de que o snapshot atual
    do Airtable é válido -- NUNCA a competência que o runner está
    processando (`ContextoCicloPrestacao`, conceito DIFERENTE, nunca
    aceito aqui nem por engano de nome). `None` (default) significa
    "nenhuma vigência comprovada" -- toda resolução cai em
    `NAO_ENCONTRADA`, nunca `RESOLVIDA` por suposição."""

    def __init__(
        self, leitor: LeitorAirtableSomenteLeitura,
        competencia_snapshot_comprovada: Optional[Tuple[int, int]] = None,
    ):
        self._leitor = leitor
        self._competencia_snapshot_comprovada = (
            _formatar_competencia(competencia_snapshot_comprovada)
            if competencia_snapshot_comprovada is not None else None
        )

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        if competencia.tipo_entidade != 'COMPETENCIA':
            raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')
        if (
            self._competencia_snapshot_comprovada is None
            or competencia.entidade_id != self._competencia_snapshot_comprovada
        ):
            # Sem vigência comprovada para esta competência exata --
            # nunca promove o snapshot corrente a verdade para uma
            # competência que ele não prova (histórica ou não).
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
                metodo='funcionario_local_airtable_readonly', motivos=(MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA,),
            )

        registros = self._leitor.listar_registros(
            table_id=TABLE_FUNC, fields=[F_FUNC_LOCAIS],
            filter_by_formula=filtro_ids((colaborador.entidade_id,)),
        )
        locais = tuple(sorted({
            local_id
            for registro in registros
            for local_id in ids_vinculados(registro.get('fields', {}).get(F_FUNC_LOCAIS))
        }))

        if not locais:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
                metodo='funcionario_local_airtable_readonly',
            )

        postos = tuple(ReferenciaCanonica('UNIDADE_POSTO', local_id) for local_id in locais)
        evidencias = tuple(
            EvidenciaSanitizada(
                tipo_evidencia='UNIDADE_POSTO_CANONICA', fonte='airtable_readonly',
                referencia_fonte=local_id, metodo='funcionario_local', forca=NivelConfianca.FORTE,
                entidade_candidata=ReferenciaCanonica('UNIDADE_POSTO', local_id),
                motivo_sanitizado='vinculo_explicito',
            )
            for local_id in locais
        )
        # Cardinalidade múltipla genuína (§3 da missão anterior): 2+
        # postos legítimos na MESMA competência nunca são colapsados a
        # 1 -- todos entram como valores_confirmados, nunca AMBIGUA
        # (múltiplos postos não é incerteza, é composição real).
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=postos, evidencias=evidencias, metodo='funcionario_local',
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
