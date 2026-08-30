"""Produtor TEMPORAL/CERTIDÃO (missão "FECHAMENTO AMPLO DA COBERTURA
DOCUMENTAL", Fase 2E.3, Fase G).

Primeira capacidade SEMÂNTICA de código para Certidões — antes desta
missão, Certidões só existiam como registro no Airtable (achado
registrado na auditoria da Fase 2E, `MAGNATA_AI_ENGINEERING_POWERPACK_
ETAPA1.md`). O motor agora reconhece por CONTEÚDO e ESTRUTURA (palavra
"certidão" + emissão/validade/vencimento declarados), nunca depende do
Airtable para decidir identidade (cláusula pétrea #12 desta missão:
"Airtable não é o cérebro") — Airtable pode no futuro fornecer só
vínculo/estado de uma Certidão já reconhecida pelo motor.

A palavra "certidão" sozinha NUNCA basta (cláusula pétrea #6: "palavra
ou frase isolada nunca são identidade suficiente") — é sempre FRACA;
só combinada com emissão OU validade declaradas (também FRACA cada)
a força combinada sobe (regra já existente em `resolver_tipo_
documental`, não duplicada aqui)."""
from __future__ import annotations

import re
from typing import Tuple

from .contratos import EvidenciaSanitizada, NivelConfianca
from .resolucao_tipo_documental import HipoteseTipoDocumental

TIPO_CERTIDAO = 'Certidão'

_PADRAO_CERTIDAO = re.compile(r'\bCertid[ãa]o\b', re.IGNORECASE)
_PADRAO_VALIDADE = re.compile(
    r'V[áa]lid[ao]\s+at[ée]|Data\s+de\s+Validade|Vencimento\s*[:\-]', re.IGNORECASE,
)
_PADRAO_EMISSAO = re.compile(r'Emitid[ao]\s+em|Data\s+de\s+Emiss[ãa]o', re.IGNORECASE)


def hipoteses_temporais_de_certidao(texto: str) -> Tuple[HipoteseTipoDocumental, ...]:
    """A palavra "certidão" é NECESSÁRIA (sem ela, nenhuma hipótese --
    nunca infere Certidão só por ter data de validade, o que colidiria
    com qualquer outro documento com prazo), mas nunca SUFICIENTE
    sozinha -- precisa de emissão OU validade declaradas para reforçar
    e virar RESOLVIDA (2 FRACA -> MODERADA, regra já existente)."""
    if not texto or not _PADRAO_CERTIDAO.search(texto):
        return ()
    evidencias = [EvidenciaSanitizada(
        tipo_evidencia='CERTIDAO_PALAVRA_CHAVE', fonte='produtor_evidencia_temporal',
        referencia_fonte='certidao', metodo='regex_certidao', forca=NivelConfianca.FRACA,
    )]
    if _PADRAO_VALIDADE.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='CERTIDAO_VALIDADE_DECLARADA', fonte='produtor_evidencia_temporal',
            referencia_fonte='validade_ou_vencimento', metodo='regex_validade',
            forca=NivelConfianca.FRACA,
        ))
    if _PADRAO_EMISSAO.search(texto):
        evidencias.append(EvidenciaSanitizada(
            tipo_evidencia='CERTIDAO_EMISSAO_DECLARADA', fonte='produtor_evidencia_temporal',
            referencia_fonte='data_de_emissao', metodo='regex_emissao',
            forca=NivelConfianca.FRACA,
        ))
    return (HipoteseTipoDocumental(tipo_documental=TIPO_CERTIDAO, evidencias=tuple(evidencias)),)
