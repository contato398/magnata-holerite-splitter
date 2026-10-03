"""SHADOW -- fecha DIAGNÓSTICO REAL -> SELEÇÃO/CURADORIA DO OPERADOR ->
ORDEM REAL COMPOSTA (ainda em modo sombra, parando em PENDING), sem
transporte real.

Módulo irmão de `executar_prestacao_contato_ate_pending_shadow_v1.py`
(mesma disciplina, mesmo aviso de segurança abaixo) -- a diferença
ESTRITA entre os dois é qual composition root do wiring de Prestação é
chamado por baixo:

    - `executar_prestacao_contato_ate_pending_shadow_v1` chama
      `executar_prestacao_ate_distribuicao_documental_shadow`
      ("manda tudo que está PRONTO", sem curadoria humana);
    - este módulo chama `executar_prestacao_selecionada_ate_
      distribuicao_documental_shadow` ("só o que o operador
      selecionou", PR #210) -- mesmo núcleo genérico, mesmo
      isolamento por colaborador, mesmo padrão seguro por default
      (seleção vazia = zero Ordem).

Reaproveita, SEM DUPLICAR:
    - `construir_resolvedor_parametros_ordem_prestacao_contato_v1`
      (`resolver_parametros_ordem_prestacao_contato_v1.py`, já existente
      e intocado) -- o mesmo resolvedor real de destinatário (Contato
      Canônico de Colaborador V1, nunca Airtable, nunca telefone
      hardcoded);
    - `executar_prestacao_selecionada_ate_distribuicao_documental_shadow`
      (`wiring_prestacao_distribuicao_documental_shadow.py`, já existente
      e intocado, PR #210) -- toda a lógica de filtro pela seleção,
      isolamento por colaborador, fail-closed de preset divergente e
      idempotência já pertence a ele, nunca duplicada aqui;
    - `compor_repositorio_contato_a_partir_do_ambiente`/`compor_chave_
      fernet_contato_a_partir_do_ambiente` (`executar_prestacao_contato_
      ate_pending_shadow_v1.py`, já existentes e intocados) -- os mesmos
      2 compositores de ambiente, reexportados aqui, nunca reimplementados.

**AVISO DE SEGURANÇA -- LER ANTES DE REUTILIZAR (mesma disciplina do
módulo irmão):** o nome deste módulo/função leva `_shadow_` de
propósito. A cadeia termina em PENDING usando `autorizar_preview_
assinatura_shadow` -- uma autorização SINTÉTICA, criada automaticamente
pela composição para provar a integração, NUNCA uma decisão humana
real. Isso é correto e suficiente para fechar este elo, mas **nunca deve
ser lido, chamado ou apresentado como um entrypoint operacional de
produção**. Um runtime real que de fato dispare uma ação a partir de
PENDING para um colaborador real precisará, antes disso, obter
autorização LEGÍTIMA depois de `WAITING_GATE` (decisão humana real, não
esta função) -- trabalho de uma fase futura e distinta, com seus
próprios gates, nunca decidido silenciosamente aqui.

Responsabilidade ESTRITA:
    1. compor `RepositorioContatoColaborador` (Postgres real) e a chave
       Fernet a partir do ambiente (reexportado, intocado);
    2. construir o resolvedor real
       (`construir_resolvedor_parametros_ordem_prestacao_contato_v1`,
       intocado);
    3. chamar `executar_prestacao_selecionada_ate_distribuicao_
       documental_shadow` (intocado) com esse resolvedor e a
       `SelecaoEnvioOperador` do chamador.

Nunca:
    - compõe `ContextoComposicaoPrestacao` a partir de fontes reais --
      `contexto` é SEMPRE dependência explícita de quem chama esta
      função (real, via `composicao_prestacao_real_v1.py`, ou fake para
      prova local). Nunca inventado/composto sozinho por este módulo;
    - decide `preset_id`/`tipo_documento`/`mensagem_texto` -- seguem
      sendo dependência explícita do chamador, mesma disciplina de
      `construir_resolvedor_parametros_ordem_prestacao_contato_v1`;
    - decide a `SelecaoEnvioOperador` -- é sempre dependência explícita
      do chamador (a curadoria é do operador, nunca inferida aqui);
    - resolve telefone diretamente -- delega inteiramente ao resolvedor
      real;
    - consulta Airtable -- nenhum import de cliente Airtable neste
      módulo;
    - dispara transporte real -- nenhum import de `porta_execucao`/
      `transporte_real_habilitado`/`ExecutorEvolutionLegado`/
      `ciclo_producao_v1` neste módulo. Termina estritamente em
      PENDING, mesma garantia estrutural do núcleo genérico."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
)
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    RepositorioContatoColaborador,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos
from magnata_os.documental.modulo01.materializador_arquivo import MaterializadorArquivoLegado
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentos

from .adapters.postgres_conclusao_obrigacao_assinatura import (
    RepositorioConclusaoObrigacaoAssinaturaPostgres,
)
from .autorizacao_gate import RepositorioAutorizacoesGate
from .executar_prestacao_contato_ate_pending_shadow_v1 import (
    compor_chave_fernet_contato_a_partir_do_ambiente,
    compor_repositorio_contato_a_partir_do_ambiente,
)
from .obrigacao_assinatura import PortaObrigacaoAssinatura
from .repositorio_acoes_execucao_plano_postgres import RepositorioAcoesExecucaoPlanoPostgres
from .repositorio_execucoes import RepositorioExecucoes
from .resolver_parametros_ordem_prestacao_contato_v1 import (
    MensagemTextoPrestacao,
    construir_resolvedor_parametros_ordem_prestacao_contato_v1,
)
from .selecao_envio_operador_v1 import SelecaoEnvioOperador
from .wiring_distribuicao_documental_shadow import ResultadoDistribuicaoDocumentalShadow
from .wiring_prestacao_distribuicao_documental_shadow import (
    executar_prestacao_selecionada_ate_distribuicao_documental_shadow,
)

__all__ = [
    'executar_prestacao_selecionada_contato_ate_pending_shadow_v1',
    'compor_repositorio_contato_a_partir_do_ambiente',
    'compor_chave_fernet_contato_a_partir_do_ambiente',
]


def executar_prestacao_selecionada_contato_ate_pending_shadow_v1(
    *,
    contexto: ContextoComposicaoPrestacao,
    selecao_operador: SelecaoEnvioOperador,
    repositorio_contato: RepositorioContatoColaborador,
    chave_fernet: bytes,
    preset_id: str,
    tipo_documento: str,
    montar_mensagem_texto: MensagemTextoPrestacao,
    repositorio_documentos: RepositorioDocumentos,
    armazenamento: ArmazenamentoArquivos,
    materializador: Optional[MaterializadorArquivoLegado],
    porta_assinatura: Optional[PortaObrigacaoAssinatura],
    repositorio_execucoes: RepositorioExecucoes,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime,
    canal: str = CANAL_WHATSAPP,
    repositorio_conclusao: Optional[RepositorioConclusaoObrigacaoAssinaturaPostgres] = None,
) -> Tuple[ResultadoDistribuicaoDocumentalShadow, ...]:
    """SHADOW -- prova/composição integrada, NÃO composition root
    operacional de produção (ver aviso de segurança no topo do módulo).
    Composição pura (zero I/O de ambiente aqui -- tudo já vem pronto por
    parâmetro) que fecha CLIENTE+COMPETÊNCIA -> pacote PRONTO -> só o
    que a `SelecaoEnvioOperador` escolheu -> destinatário resolvido pelo
    Contato Canônico -> Ordem -> Evento -> WAITING_GATE -> Preview ->
    autorização SHADOW (sintética, nunca decisão humana real) -> Plano
    -> Envelope -> AÇÃO PENDING, sem transporte real.

    Constrói o resolvedor real (`construir_resolvedor_parametros_
    ordem_prestacao_contato_v1`) sobre `repositorio_contato`/`chave_
    fernet` e delega inteiramente a `executar_prestacao_selecionada_
    ate_distribuicao_documental_shadow` -- nenhuma lógica de filtro,
    isolamento por colaborador, fail-closed ou idempotência é duplicada
    aqui; todas já pertencem ao wiring de Prestação (intocado). Um
    futuro runtime real de produção NUNCA deve chamar esta função
    esperando autorização legítima -- precisará, antes de qualquer ação
    real, de uma decisão humana real depois de `WAITING_GATE` (fora de
    escopo aqui)."""
    resolver_parametros_ordem = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repositorio_contato,
        chave_fernet=chave_fernet,
        preset_id=preset_id,
        tipo_documento=tipo_documento,
        montar_mensagem_texto=montar_mensagem_texto,
        canal=canal,
    )
    return executar_prestacao_selecionada_ate_distribuicao_documental_shadow(
        contexto=contexto,
        selecao_operador=selecao_operador,
        resolver_parametros_ordem=resolver_parametros_ordem,
        repositorio_documentos=repositorio_documentos,
        armazenamento=armazenamento,
        materializador=materializador,
        porta_assinatura=porta_assinatura,
        repositorio_execucoes=repositorio_execucoes,
        repositorio_autorizacoes=repositorio_autorizacoes,
        repositorio_acoes=repositorio_acoes,
        ator_referencia=ator_referencia,
        proveniencia=proveniencia,
        instante=instante,
        repositorio_conclusao=repositorio_conclusao,
    )
