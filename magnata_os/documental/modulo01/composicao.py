"""Composition root V1 do Módulo 01 (Documental).

Monta explicitamente o pipeline completo:

    FonteMensagensEmail
    -> AdapterCapturaEmail
    -> ServicoCriacaoLote
    -> ServicoEntradaDocumental / ServicoAvancoEsteira
    -> repositórios (Documentos, Histórico, Lotes, Estados da Esteira)
    -> FonteCandidatosFuncionario (opcional)

a partir de dependências JÁ CONSTRUÍDAS, injetadas por quem chama —
mesmo padrão já usado em `magnata_os/orquestrador/
fabrica_repositorio_execucoes.py` (composição explícita, sem fallback
silencioso, sem decidir backend sozinha).

O QUE ESTE MÓDULO NUNCA FAZ (por design, não por descuido):
  - não lê nenhuma variável de ambiente (nem `DATABASE_URL`, nem
    `AIRTABLE_API_KEY`, nem credencial de Gmail) -- isso é
    responsabilidade de quem monta as dependências antes de chamar
    `construir_pipeline_modulo01` (o "bootstrap externo", fora de
    escopo desta missão -- ver `adapters/conexao.py::ler_database_url`
    e `scripts/prestacao_readiness_shadow_real.py::CREDENCIAL_ENV`
    para onde esse próximo gate, quando autorizado, deve ler cada uma);
  - não abre conexão de rede nem de banco -- recebe repositórios e
    fontes já prontos, nunca os constrói a partir de credencial;
  - não importa `psycopg`, cliente Gmail (`googleapiclient`) nem
    cliente Airtable (`requests` contra a API) -- só os Protocols/
    classes já existentes deste pacote;
  - não conhece regra de negócio (classificação, identificação de
    colaborador, SQL, HTTP) -- só amarra os serviços/adapters já
    existentes, sem reimplementar nada deles;
  - não ativa nenhuma captura real -- construir o pipeline nunca
    chama `capturar_novas_mensagens()` sozinho.

Cada dependência é um Protocol/classe já existente no pacote:
  - `RepositorioDocumentos`/`RepositorioHistorico` (repositorio.py) --
    hoje têm implementação Postgres real (`adapters/
    postgres_repositorio.py`) e em memória (testes).
  - `RepositorioLotes`/`RepositorioEstadosEsteira`
    (repositorio_esteira.py) -- hoje só têm implementação em memória;
    uma implementação Postgres real é trabalho futuro, fora desta
    missão (nenhuma migration/schema foi criada aqui).
  - `FonteMensagensEmail` (adapters/email_captura.py) -- hoje só tem
    implementação de teste; `ClienteGmailReadOnly` (adapters/
    email_gmail_readonly.py) a satisfaz por herança/interface, mas
    constrói o recurso Gmail real dentro do próprio `__init__`
    (`construir_recurso(credenciais)`) -- por isso NUNCA é instanciada
    aqui dentro; quem tiver credencial Gmail real autorizada monta
    `ClienteGmailReadOnly` primeiro e passa a instância pronta.
  - `FonteCandidatosFuncionario` (servico_lote.py) -- opcional
    (`None` por padrão, preservando o comportamento seguro já
    existente de `ServicoCriacaoLote`).
    `LeitorAirtableSomenteLeitura` (adapters/airtable_leitura.py, em
    `magnata_os/documental/importacao_lote/`) já a satisfaz por duck
    typing, sem adapter novo -- mas, pelo mesmo motivo do Gmail, este
    módulo nunca a instancia: quem tiver `AIRTABLE_API_KEY` autorizada
    constrói `LeitorAirtableSomenteLeitura(api_key)` primeiro e passa a
    instância pronta.

Construir o pipeline (`construir_pipeline_modulo01`) NUNCA ativa
produção externa -- é só a montagem das dependências recebidas. A
ativação real (credencial Gmail, `AIRTABLE_API_KEY`, `DATABASE_URL`
real, agendador chamando `capturar_novas_mensagens()` de verdade)
continua sendo um gate operacional separado, explicitamente fora de
escopo desta missão (ver docs/decisoes/
composition-root-modulo01-v1.md).
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Callable, Optional

from .adapters.email_captura import AdapterCapturaEmail, FonteMensagensEmail
from .repositorio import RepositorioDocumentos, RepositorioHistorico
from .repositorio_esteira import RepositorioEstadosEsteira, RepositorioLotes
from .servico_avanco_esteira import ServicoAvancoEsteira
from .servico_entrada import ServicoEntradaDocumental
from .servico_lote import FonteCandidatosFuncionario, ServicoCriacaoLote


@dataclasses.dataclass(frozen=True)
class PipelineModulo01:
    """Container operacional do pipeline já montado -- cada campo é a
    MESMA instância usada pelos demais (nunca uma cópia), para que quem
    consome possa inspecionar/reutilizar qualquer camada
    individualmente (ex.: chamar `servico_lote.criar_lote(...)`
    diretamente, fora do fluxo de e-mail, sem montar tudo de novo)."""

    servico_entrada: ServicoEntradaDocumental
    servico_avanco: ServicoAvancoEsteira
    servico_lote: ServicoCriacaoLote
    adapter_captura_email: AdapterCapturaEmail


def construir_pipeline_modulo01(
    *,
    repositorio_documentos: RepositorioDocumentos,
    repositorio_historico: RepositorioHistorico,
    repositorio_lotes: RepositorioLotes,
    repositorio_estados_esteira: RepositorioEstadosEsteira,
    fonte_mensagens: FonteMensagensEmail,
    fonte_candidatos_funcionario: Optional[FonteCandidatosFuncionario] = None,
    relogio: Optional[Callable[[], datetime]] = None,
) -> PipelineModulo01:
    """Monta o pipeline completo do Módulo 01 a partir de dependências
    já construídas -- nunca decide backend, nunca lê configuração,
    nunca abre conexão/rede. Todas as dependências obrigatórias são
    keyword-only e sem default (exceto `fonte_candidatos_funcionario`,
    que preserva o default seguro `None` já existente em
    `ServicoCriacaoLote`, e `relogio`, opcional para testes
    determinísticos) -- nenhum fallback silencioso, mesmo espírito de
    `orquestrador/fabrica_repositorio_execucoes.py`.

    `relogio`, quando fornecido, é repassado aos três serviços que o
    aceitam (`ServicoEntradaDocumental`, `ServicoAvancoEsteira`,
    `ServicoCriacaoLote`) -- para que um teste determinístico controle
    o "agora" do pipeline inteiro com um único relógio fake, nunca três
    relógios divergentes. Quando `None`, cada serviço usa seu próprio
    default (`datetime.now(timezone.utc)`).
    """
    kwargs_relogio = {'relogio': relogio} if relogio is not None else {}

    servico_entrada = ServicoEntradaDocumental(
        repositorio_documentos, repositorio_historico, **kwargs_relogio,
    )
    servico_avanco = ServicoAvancoEsteira(
        repositorio_estados_esteira, repositorio_historico, **kwargs_relogio,
    )
    servico_lote = ServicoCriacaoLote(
        repositorio_lotes, servico_entrada, servico_avanco,
        fonte_candidatos_funcionario=fonte_candidatos_funcionario,
        **kwargs_relogio,
    )
    adapter_captura_email = AdapterCapturaEmail(fonte_mensagens, servico_lote)

    return PipelineModulo01(
        servico_entrada=servico_entrada,
        servico_avanco=servico_avanco,
        servico_lote=servico_lote,
        adapter_captura_email=adapter_captura_email,
    )
