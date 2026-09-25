"""SHADOW -- prova integrada até PENDING, NUNCA composition root
operacional de produção. Fecha a costura entre a aquisição da
Prestação (`executar_prestacao_ate_distribuicao_documental_shadow`,
`wiring_prestacao_distribuicao_documental_shadow.py`, já existente e
intocado) e o resolvedor real do Contato Canônico do Colaborador
(`construir_resolvedor_parametros_ordem_prestacao_contato_v1`,
`resolver_parametros_ordem_prestacao_contato_v1.py`, já existente e
intocado) -- até esta correção, os dois só se encontravam em
`test_integracao_prestacao_contato_ate_pending.py`; nenhum código de
produção os ligava.

**AVISO DE SEGURANÇA -- LER ANTES DE REUTILIZAR (correção pós-auditoria
final do PR #181):** o nome deste módulo/função leva `_shadow_` de
propósito. A cadeia que ele fecha termina em PENDING usando
`autorizar_preview_assinatura_shadow` -- uma autorização SINTÉTICA,
criada automaticamente pela composição para provar a integração, NUNCA
uma decisão humana real. Isso é correto e suficiente para PROVAR esta
etapa (Gate A/F da auditoria), mas **nunca deve ser lido, chamado ou
apresentado como um entrypoint operacional de produção**. Um runtime
real que de fato dispare uma ação a partir de PENDING para um
colaborador real precisará, antes disso, obter autorização LEGÍTIMA
depois de `WAITING_GATE` (decisão humana real, não esta função) -- isso
é trabalho de uma fase futura e distinta, com seus próprios gates
(G/H/I da auditoria), nunca decidido silenciosamente aqui.

GAP FECHADO (ver auditoria "AUDITORIA CANÔNICA DO ELO", classificação
"GAP DE INTEGRAÇÃO"): este módulo é a ÚNICA peça nova desta correção --
não duplica nem reescreve nenhuma regra de composição, preview,
autorização, plano, envelope ou persistência já existente em
`wiring_prestacao_distribuicao_documental_shadow.py`/`wiring_
distribuicao_documental_shadow.py`; só monta o resolvedor real e
delega.

Responsabilidade ESTRITA:
    1. compor `RepositorioContatoColaborador` (Postgres real) e a
       chave Fernet a partir do ambiente (`configuracao_contato_
       colaborador.py`, `adapters/postgres_contato_colaborador.py`,
       já existentes e intocados);
    2. construir o resolvedor real (`construir_resolvedor_parametros_
       ordem_prestacao_contato_v1`, já existente e intocado);
    3. chamar `executar_prestacao_ate_distribuicao_documental_shadow`
       (já existente e intocado) com esse resolvedor.

Nunca:
    - compõe `ContextoComposicaoPrestacao` a partir de fontes reais
      (Airtable) de clientes/requisitos/colaboradores esperados/
      candidatos por necessidade -- isso é responsabilidade de uma
      missão FUTURA e SEPARADA (composição real do ambiente de
      aquisição da Prestação), fora de escopo aqui. `contexto` é
      SEMPRE dependência explícita de quem chama esta função --
      fake/em memória para prova local, real só quando essa missão
      futura existir. Nunca inventado/composto sozinho por este
      módulo;
    - decide `preset_id`/`tipo_documento`/`mensagem_texto` -- seguem
      sendo dependência explícita do chamador, mesma disciplina de
      `construir_resolvedor_parametros_ordem_prestacao_contato_v1`;
    - resolve telefone diretamente -- delega inteiramente ao
      resolvedor real;
    - consulta Airtable -- nenhum import de cliente Airtable neste
      módulo;
    - dispara transporte real -- nenhum import de `porta_execucao`/
      `transporte_real_habilitado`/`ExecutorEvolutionLegado`/
      `ciclo_producao_v1` neste módulo. Termina estritamente em
      PENDING, mesma garantia estrutural do núcleo genérico;
    - vira gerente -- nunca decide autorização real, nunca cria
      segundo Orquestrador/motor/fila/scheduler; apenas compõe
      capacidades já existentes.

Não é CLI/script executável nesta V1 -- composição real de
`ContextoComposicaoPrestacao` (Fonte* Airtable) ainda não existe em
nenhum lugar do repositório (confirmado por auditoria), então um
`main()` aqui não teria como rodar de ponta a ponta sem essa peça
futura. Este módulo entrega a composição PURA (zero leitura de
ambiente na função principal) mais os 2 compositores de ambiente que
já são genuinamente reutilizáveis hoje (contato + chave) -- prontos
para uma futura missão de composição real da Prestação os consumir,
sem reescrevê-los."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Tuple

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
)
from magnata_os.documental.alocacao.configuracao_contato_colaborador import (
    carregar_configuracao_segredo_contato,
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
from .obrigacao_assinatura import PortaObrigacaoAssinatura
from .repositorio_acoes_execucao_plano_postgres import RepositorioAcoesExecucaoPlanoPostgres
from .repositorio_execucoes import RepositorioExecucoes
from .resolver_parametros_ordem_prestacao_contato_v1 import (
    MensagemTextoPrestacao,
    construir_resolvedor_parametros_ordem_prestacao_contato_v1,
)
from .wiring_distribuicao_documental_shadow import ResultadoDistribuicaoDocumentalShadow
from .wiring_prestacao_distribuicao_documental_shadow import (
    executar_prestacao_ate_distribuicao_documental_shadow,
)

__all__ = [
    'executar_prestacao_contato_ate_pending_shadow_v1',
    'compor_repositorio_contato_a_partir_do_ambiente',
    'compor_chave_fernet_contato_a_partir_do_ambiente',
]


def executar_prestacao_contato_ate_pending_shadow_v1(
    *,
    contexto: ContextoComposicaoPrestacao,
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
    trios_prontos: Optional[Tuple] = None,
) -> Tuple[ResultadoDistribuicaoDocumentalShadow, ...]:
    """SHADOW -- prova integrada, NÃO composition root operacional de
    produção (ver aviso de segurança no topo do módulo). Composição
    pura (zero I/O de ambiente aqui -- tudo já vem pronto por
    parâmetro) que fecha CLIENTE+COMPETÊNCIA -> pacote PRONTO ->
    destinatário resolvido pelo Contato Canônico -> Ordem -> Evento ->
    WAITING_GATE -> Preview -> autorização SHADOW (sintética, nunca
    decisão humana real) -> Plano -> Envelope -> AÇÃO PENDING, sem
    transporte real.

    Constrói o resolvedor real (`construir_resolvedor_parametros_
    ordem_prestacao_contato_v1`) sobre `repositorio_contato`/`chave_
    fernet` e delega inteiramente a `executar_prestacao_ate_
    distribuicao_documental_shadow` -- nenhuma lógica de composição,
    isolamento por cliente, fail-closed ou idempotência é duplicada
    aqui; ambas já pertencem, respectivamente, ao resolvedor e ao
    wiring de Prestação (intocados). Um futuro runtime real de
    produção NUNCA deve chamar esta função esperando autorização
    legítima -- precisará, antes de qualquer ação real, de uma decisão
    humana real depois de `WAITING_GATE` (fora de escopo aqui)."""
    resolver_parametros_ordem = construir_resolvedor_parametros_ordem_prestacao_contato_v1(
        repositorio_contato=repositorio_contato,
        chave_fernet=chave_fernet,
        preset_id=preset_id,
        tipo_documento=tipo_documento,
        montar_mensagem_texto=montar_mensagem_texto,
        canal=canal,
    )
    return executar_prestacao_ate_distribuicao_documental_shadow(
        contexto=contexto,
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
        trios_prontos=trios_prontos,
    )


# ---------------------------------------------------------------------
# Compositores de ambiente -- mesmo padrão de `distribuir_documento_v1.
# _compor_*_a_partir_do_ambiente`: só aqui se lê variável de ambiente ou
# se abre conexão real; a função de composição pura acima nunca faz
# isso sozinha. Falha de configuração é sempre erro explícito (já
# levantado pelos próprios módulos reutilizados), nunca um default
# silencioso.
# ---------------------------------------------------------------------

def compor_repositorio_contato_a_partir_do_ambiente() -> RepositorioContatoColaborador:
    """Postgres real -- mesma conexão real já usada por `distribuir_
    documento_v1._compor_repositorio_documentos_a_partir_do_ambiente`
    e pelos demais compositores de `ciclo_producao_v1.py`."""
    from magnata_os.documental.alocacao.adapters.postgres_contato_colaborador import (
        RepositorioContatoColaboradorPostgres,
    )
    from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao
    return RepositorioContatoColaboradorPostgres(abrir_conexao())


def compor_chave_fernet_contato_a_partir_do_ambiente() -> bytes:
    """Chave Fernet da versão ATUAL (`configuracao_contato_
    colaborador.versao_atual()`), sempre de variável de ambiente,
    nunca hardcoded -- levanta `SegredoContatoColaboradorAusente`
    (fail-closed) se a configuração não estiver presente."""
    configuracao = carregar_configuracao_segredo_contato(os.environ)
    return configuracao.obter_chave_fernet_atual()
