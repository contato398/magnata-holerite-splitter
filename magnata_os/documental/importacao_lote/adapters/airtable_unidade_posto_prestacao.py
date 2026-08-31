"""Adapter REAL read-only de UNIDADE_POSTO da prestação (missão
"MESCLAR PR #107 + CONSTRUIR OS DOIS ADAPTERS REAIS QUE BLOQUEIAM A
PRIMEIRA VALIDAÇÃO LIVE — FonteUnidadePostoPrestacao +
FonteCandidatosRelacaoDocumental").

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

TEMPORALIDADE (regra pétrea desde o adendo pré-merge ao PR #106 —
"vínculo/posto corrente nunca prova histórico sem evidência de
vigência"): o schema Airtable de Funcionário/Local NÃO tem nenhum campo
de vigência/período (confirmado por auditoria anterior, sessão
anterior desta mesma missão macro) — este adapter só pode responder
pela competência CORRENTE do ciclo, injetada uma única vez via
`ContextoCicloPrestacao` (nunca lida do relógio aqui, cláusula pétrea
"competência entra uma vez, na borda"). Para qualquer competência
diferente da corrente, devolve `NAO_ENCONTRADA` com o motivo sanitizado
já cadastrado (`MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA`,
`vinculo_unidade_prestacao.py`) — nunca `RESOLVIDA` "com ressalva"."""
from __future__ import annotations

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
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


def _formatar_competencia(ano_mes: tuple[int, int]) -> str:
    """Mesmo formato canônico já usado em todo o repositório
    (`resolucao_semantica.py`/`ciclo_prestacao.py`/`inventario_
    prestacao_resultados.py`) -- nunca um segundo formato paralelo."""
    ano, mes = ano_mes
    return f'{ano:04d}-{mes:02d}'


class FonteUnidadePostoPrestacaoAirtableShadow:
    """Lê o link Funcionário→Local sem qualquer escrita. `contexto_
    ciclo` é a competência CORRENTE do ciclo em execução, injetada uma
    única vez por quem compõe o corredor -- nunca redescoberta por
    documento, nunca lida do relógio dentro deste adapter."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura, contexto_ciclo: ContextoCicloPrestacao):
        self._leitor = leitor
        self._competencia_corrente = _formatar_competencia(contexto_ciclo.competencia_base)

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        if competencia.tipo_entidade != 'COMPETENCIA':
            raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')
        if competencia.entidade_id != self._competencia_corrente:
            # Sem evidência de vigência para competência histórica --
            # nunca promove o posto corrente a verdade histórica.
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
