"""Ponte CONTEÚDO → MOTOR SEMÂNTICO multi-evidência (missão "INTEGRAÇÃO
REAL DO CONTEÚDO DOCUMENTAL AO MOTOR SEMÂNTICO", Fases 2/4).

Auditoria (Fase 1) confirmou que `roteamento_documental.py` já é a
ponte bytes→texto→classificação real (`extrair_texto_seguro` +
`classificar_documento`) — mas alimenta só o classificador textual de
17 regras, nunca os produtores de evidência mais novos (fiscal, ponto,
temporal, rótulo alternativo de extrato, finalidade de pagamento) nem o
`ResolucaoDimensao`/8-estados do motor geral. Este módulo fecha esse
gap: uma ponte texto → `ResolucaoDimensao(TIPO_DOCUMENTAL)` que agrega
TODOS os produtores de evidência já existentes para o MESMO
`resolver_tipo_documental` — nunca um segundo motor, nunca decide
sozinho entre as evidências (isso continua sendo `resolver_tipo_
documental`).

Reaproveita, sem duplicar:
  - `extrair_texto_seguro` (`roteamento_documental.py`) — extração de
    texto de bytes de PDF, já existente;
  - `hipoteses_textuais_de_classificacao(classificar_documento(...))`
    — as 17 regras do classificador legado;
  - `hipoteses_fiscais_de_texto` — Código de Receita, linha digitável;
  - `hipoteses_estruturais_de_ponto` — Folha de Ponto por estrutura;
  - `hipoteses_temporais_de_certidao` — validade de Certidão;
  - `hipoteses_de_rotulo_alternativo_de_extrato` — "Resumo da Folha";
  - `hipoteses_de_finalidade_pagamento` (+ `sinais_textuais_de_
    finalidade_pagamento` + `reconciliar_evidencia_fiscal_com_
    finalidade`) — Salário/FGTS/DCTF-DARF/VR-VA/Assiduidade/Diárias/
    Horas Extras;
  - `hipoteses_de_relatorio_beneficios` (Adendo substitutivo ao PR #105)
    — relatório/pedido de benefícios (VR/VA/iFood/etc., fornecedor é
    metadado, nunca identidade)."""
from __future__ import annotations

from typing import Optional, Tuple

from .classificador_documental import classificar_documento
from .contratos import ResolucaoDimensao
from .finalidade_comprovante_pagamento import (
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from .produtores_evidencia_beneficios import hipoteses_de_relatorio_beneficios
from .produtores_evidencia_documental import hipoteses_textuais_de_classificacao
from .produtores_evidencia_extrato import hipoteses_de_rotulo_alternativo_de_extrato
from .produtores_evidencia_fiscal import (
    hipoteses_fiscais_de_texto,
    reconciliar_evidencia_fiscal_com_finalidade,
)
from .produtores_evidencia_ponto import hipoteses_estruturais_de_ponto
from .produtores_evidencia_temporal import hipoteses_temporais_de_certidao
from .resolucao_tipo_documental import HipoteseTipoDocumental, resolver_tipo_documental
from .roteamento_documental import extrair_texto_seguro


def hipoteses_multi_evidencia_de_texto(texto: Optional[str]) -> Tuple[HipoteseTipoDocumental, ...]:
    """Une TODAS as hipóteses já produzidas pelos produtores existentes
    para o MESMO texto — nunca decide entre elas, só agrega para o
    resolvedor único (`resolver_tipo_documental` continua sendo o
    ÚNICO ponto que combina força/conflito)."""
    if not texto:
        return ()
    ocorrencias_finalidade = (
        sinais_textuais_de_finalidade_pagamento(texto)
        + reconciliar_evidencia_fiscal_com_finalidade(texto)
    )
    return (
        hipoteses_textuais_de_classificacao(classificar_documento(texto))
        + hipoteses_fiscais_de_texto(texto)
        + hipoteses_estruturais_de_ponto(texto)
        + hipoteses_temporais_de_certidao(texto)
        + hipoteses_de_rotulo_alternativo_de_extrato(texto)
        + hipoteses_de_finalidade_pagamento(ocorrencias_finalidade)
        + hipoteses_de_relatorio_beneficios(texto)
    )


def resolver_tipo_documental_de_texto(texto: Optional[str]) -> ResolucaoDimensao:
    """Ponte completa: texto (já extraído, ou `None` — PDF sem texto
    extraível, Fase 3: extração ≠ classificação, nunca inventa um tipo
    para texto ausente) → `ResolucaoDimensao(TIPO_DOCUMENTAL)`, usando
    o MESMO `resolver_tipo_documental` de sempre."""
    return resolver_tipo_documental(hipoteses_multi_evidencia_de_texto(texto))


def resolver_tipo_documental_de_pdf(conteudo_pdf: bytes) -> ResolucaoDimensao:
    """Ponte completa a partir de BYTES de PDF — reaproveita `extrair_
    texto_seguro` (`roteamento_documental.py`, já existente, nunca uma
    segunda extração) e delega a `resolver_tipo_documental_de_texto`.
    PDF corrompido/sem texto extraível vira `texto=None`, tratado pelo
    resolvedor como ausência total de evidência (nunca uma exceção,
    nunca uma classificação inventada)."""
    return resolver_tipo_documental_de_texto(extrair_texto_seguro(conteudo_pdf))
