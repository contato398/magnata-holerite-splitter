"""Roteamento por canal (Plano A / Plano B) para `ResolverParametrosOrdemPrestacao`.

Fecha o gap descrito no Ultraplan "Prestação -> Distribuição
Documental -> roteamento por canal": até aqui,
`executar_prestacao_ate_distribuicao_documental_shadow`
(`wiring_prestacao_distribuicao_documental_shadow.py`) já sabe
consumir um pacote PRONTO da Prestação e chegar a PENDING, mas só
existia UM resolvedor real de parâmetros por vez
(`construir_resolvedor_parametros_ordem_prestacao_contato_v1`, sempre
WhatsApp) -- nenhum componente decidia entre 2 canais.

Este módulo NÃO resolve contato, NÃO conhece WhatsApp/e-mail/Evolution/
Gmail/SMTP, NÃO importa nada de transporte e NÃO faz I/O. É só um
combinador puro sobre o mesmo contrato já existente
(`ResolverParametrosOrdemPrestacao`, de
`wiring_prestacao_distribuicao_documental_shadow.py`, reaproveitado,
nunca reconstruído): recebe 2 resolvedores já prontos -- `resolver_
plano_a` (ex.: WhatsApp, hoje `construir_resolvedor_parametros_ordem_
prestacao_contato_v1` com `canal=CANAL_WHATSAPP`, já real) e `resolver_
plano_b` (ex.: e-mail -- nesta V1, responsabilidade explícita de quem
compõe; ver `docs/decisoes/prestacao-distribuicao-canal-fallback-v1.md`
para o que continua pendência) -- e devolve UM resolvedor com a MESMA
assinatura, plugável direto em `executar_prestacao_ate_distribuicao_
documental_shadow` sem qualquer alteração no composition root nem no
núcleo genérico.

Política de fallback (Plano A / Plano B / Plano C):
    1. tenta `resolver_plano_a` (ex.: WhatsApp) para o
       cliente/competência/resultados recebidos;
    2. se `resolver_plano_a` devolver `None` (canal indisponível para
       aquele colaborador -- fail-closed, nunca uma exceção, mesma
       disciplina de `resolver_contato_colaborador_para_ordem`), tenta
       `resolver_plano_b` (ex.: e-mail);
    3. se `resolver_plano_b` também devolver `None`, o combinador
       devolve `None` -- fail-closed, zero Ordem para aquele cliente
       (vira pendência humana -- Plano C, nunca uma tentativa de
       adivinhar destinatário/canal).

Isolamento por cliente: este módulo nunca captura exceção nenhuma --
`resolver_plano_a`/`resolver_plano_b` já são, por contrato (`ResolverParametrosOrdemPrestacao`),
funções fail-closed que devolvem `None` em vez de levantar para
qualquer falha de resolução esperada (contato ausente, descriptografia
falhou, etc.). Uma exceção real aqui é sempre sinal de bug/falha
sistêmica e deve propagar, exatamente como já acontece hoje para
`resolver_parametros_ordem` em `executar_prestacao_ate_distribuicao_
documental_shadow` -- este módulo não muda essa semântica. O isolamento
"falha de 1 destinatário não trava os demais" continua garantido pelo
loop por cliente do composition root (`continue` quando o resolvedor
devolve `None`), não por este módulo.

Idempotência: pura função de dados já resolvidos (sem I/O, sem estado
mutável) -- a mesma chamada com os mesmos argumentos sempre devolve o
mesmo resultado; `executar_prestacao_ate_distribuicao_documental_
shadow` e o núcleo genérico continuam responsáveis pela idempotência de
gravação (hash/replay), inalterada por este módulo.

Zero transporte: nenhum import de `requests`/`boto3`/Evolution/Gmail/
SMTP/`app.py` -- ver `test_zero_import_de_transporte_neste_combinador_
de_canal` (checagem estrutural via AST)."""
from __future__ import annotations

from typing import Tuple

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ResultadoAquisicaoPorNecessidade,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica

from .wiring_prestacao_distribuicao_documental_shadow import (
    ParametrosOrdemPrestacao,
    ResolverParametrosOrdemPrestacao,
)

__all__ = [
    'construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1',
]


def construir_resolvedor_parametros_ordem_prestacao_fallback_canal_v1(
    *,
    resolver_plano_a: ResolverParametrosOrdemPrestacao,
    resolver_plano_b: ResolverParametrosOrdemPrestacao,
) -> ResolverParametrosOrdemPrestacao:
    """Fábrica: fecha sobre os 2 resolvedores já prontos do chamador e
    devolve um único `ResolverParametrosOrdemPrestacao` (Plano A com
    fallback para Plano B) -- pronto para
    `executar_prestacao_ate_distribuicao_documental_shadow=resolver_
    parametros_ordem`, sem nenhuma outra alteração no chamador.

    Nunca decide QUAL canal é `resolver_plano_a`/`resolver_plano_b` --
    isso é sempre decisão explícita de quem compõe (mesma disciplina de
    `preset_id`/`tipo_documento`/`destinatario` em todo este pacote:
    nunca inferidos por heurística)."""

    def _resolver(
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
        resultados_aquisicao: Tuple[ResultadoAquisicaoPorNecessidade, ...],
    ):
        parametros = resolver_plano_a(cliente, competencia, resultados_aquisicao)
        if parametros is not None:
            return parametros
        return resolver_plano_b(cliente, competencia, resultados_aquisicao)

    return _resolver
