"""Porta para aquisição documental ORIENTADA POR NECESSIDADE (evolução
do contrato do ciclo de Prestação V1 -- correção pós-Ultraplan Adendo
"Correlação Necessidade → Aquisição → Resolução").

Por que este Protocol existe: a auditoria (Ultraplan da mesma missão)
confirmou que a aquisição processava documentos em BLOCO
(`_adquirir_inventario_via_corredor`, via
`repositorio_documentos.listar_todos()`), sem NENHUMA associação real e
independente entre um documento e a necessidade/cliente/competência
que motivou buscá-lo. Duas tentativas de reconstruir essa associação
foram avaliadas e rejeitadas:

  - agrupar candidatos pela própria dimensão CLIENTE que o documento
    resolveu (`_candidatos_reais_para_cliente`, removida) -- isso
    reclassificava silenciosamente uma resolução divergente como
    "candidata legítima de outro cliente";
  - avaliar o pool GLOBAL de resoluções contra CADA cliente ativo
    (`c234d22`) -- honesto (nunca reclassifica), mas gera divergência
    cruzada sempre que 2+ clientes têm evidência real na mesma
    execução, mesmo quando os documentos de cada um nunca tiveram
    nenhuma relação real entre si.

Esta porta representa a associação REAL que faltava: para UMA
`NecessidadeDocumentoPrestacao` específica (cliente, competência, tipo
documental, colaborador quando aplicável -- contrato que já existe,
completo, em `ciclo_prestacao.py`), devolve os `Documento`
efetivamente candidatos a satisfazê-la. A decisão de QUAIS documentos
são candidatos é de quem IMPLEMENTA esta porta (busca em Gmail/
Airtable/armazenamento por metadado real, um índice já existente, o
que for) -- NUNCA deste módulo, e NUNCA a partir da resolução
semântica do próprio documento (isso seria, de novo, inferir a
associação a partir do que se está tentando validar).

DELIBERADAMENTE sem nenhum adapter "todos os documentos" neste
arquivo: um adapter assim devolveria o pool global inteiro para
qualquer necessidade, reintroduzindo exatamente a aproximação sem
correlação real já rejeitada. Enquanto uma implementação REAL (busca
complementar por necessidade) não existir, `fonte_candidatos_por_
necessidade` fica `None` em produção -- e a ausência é tratada
explicitamente como ausência de evidência contextual
(`sem_evidencia_documental_real` → REVISAR), nunca um fallback
silencioso para aquisição em bloco."""
from __future__ import annotations

from typing import Protocol, Tuple

from magnata_os.documental.modulo01.dominio import Documento

from .ciclo_prestacao import NecessidadeDocumentoPrestacao


class FonteCandidatosDocumentaisPorNecessidade(Protocol):
    """Devolve os `Documento` candidatos reais para UMA necessidade
    específica -- nunca decide sozinha se algum deles de fato a
    satisfaz (isso continua sendo papel do corredor +
    `avaliar_candidatos_ancora`); só recorta o universo de busca com
    uma correlação real, independente da resolução semântica."""

    def candidatos_para(
        self, necessidade: NecessidadeDocumentoPrestacao,
    ) -> Tuple[Documento, ...]: ...
