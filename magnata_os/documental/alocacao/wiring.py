"""Wiring SHADOW de `VinculoIniciado` a partir do extrator de admissão
JÁ EXISTENTE (missão "WIRING REAL DE VÍNCULO V1 EM MODO SHADOW").

Reaproveita `src.sync_new_employees.extrair_dados_holerite` -- regex
já testado contra holerites reais (ver docstring daquele módulo:
"testado contra 2 holerites reais"), nunca reimplementado aqui. Zero
I/O deste módulo em si -- identidade do colaborador é sempre INJETADA
(`resolver_colaborador_id`), nunca resolvida por chamada direta a
Airtable aqui (Protocol/adapter, mesma disciplina de todo o resto do
projeto).

**Custo de reuso, registrado, não escondido:** `sync_new_employees.py`
importa `flask`/`requests`/`pdfplumber` no nível do módulo (rotas Flask
e I/O real vivem no mesmo arquivo que o extrator puro) -- importar
`extrair_dados_holerite` daqui traz essas dependências transitivamente.
Aceito deliberadamente: a alternativa seria reimplementar o regex
(proibido pela missão) ou promover o extrator para um módulo neutro
(edição de `sync_new_employees.py`, fora do escopo mínimo desta
missão -- nenhuma modificação nele foi necessária ou feita).

**FATO DOCUMENTAL vs AÇÃO OPERACIONAL (Fase 6 da missão):** este módulo
só constrói o EVENTO -- nunca decide se um vínculo deve ser
ativado/inativado no Airtable, nunca aciona folha/FGTS/benefícios.
Aplicar o evento (via `captura.aplicar_vinculo_iniciado`) em modo
shadow (repositório sintético/efêmero, nunca Postgres de produção) é
tudo o que este módulo autoriza.

**RESCISÃO NÃO IMPLEMENTADA AQUI -- parada deliberada, registrada, não
esquecida:** o extrator real (`app.py::extrair_dados_rescisao`) vive
dentro do arquivo protegido. Reaproveitá-lo exigiria (a) importar
contra `app.py` -- quebra a mesma disciplina de decoupling já
documentada em `magnata_os/documental/importacao_lote/CLAUDE.md`
("app.py é legado protegido... este módulo não cria dependência de
import contra ele") -- ou (b) mover a função para fora dele, uma
edição de `app.py`. As 2 opções exigem autorização humana explícita
(`/CLAUDE.md` §7), fora do escopo desta missão. Ver ADR
`docs/decisoes/wiring-vinculo-shadow-v1.md`."""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from src.sync_new_employees import extrair_dados_holerite

from .eventos import VinculoIniciado

ORIGEM_HOLERITE_DATA_ADMISSAO = 'holerite_data_admissao'


class CpfAusenteError(ValueError):
    """O documento não trouxe CPF extraível -- nunca inferido/adivinhado."""


class DataEfetivaAusenteError(ValueError):
    """O documento não trouxe a data efetiva (Admissão) -- nunca
    assumida como "hoje" nem inferida de outro campo. Mesma regra
    central já imposta por `eventos.VinculoIniciado.__post_init__`;
    esta exceção só antecipa o motivo ANTES de tentar construir o
    evento, com uma mensagem específica do contexto de admissão."""


class ColaboradorNaoIdentificadoError(ValueError):
    """O CPF extraído não resolveu para nenhum colaborador conhecido
    (`resolver_colaborador_id` devolveu `None`) -- nunca inventa uma
    identidade nova nem escolhe um candidato arbitrário."""


def _data_br_para_date(data_br: str) -> date:
    dia, mes, ano = data_br.split('/')
    return date(int(ano), int(mes), int(dia))


def construir_vinculo_iniciado_de_holerite(
    texto: str, resolver_colaborador_id: Callable[[str], Optional[str]],
) -> VinculoIniciado:
    """`texto`: conteúdo já extraído (sintético nesta missão -- nunca
    um holerite real da Magnata; a extração de PDF real já é
    responsabilidade comprovada de `extrair_texto_pdf`/`pdfplumber`,
    fora do escopo deste módulo). `resolver_colaborador_id(cpf)`:
    injetado por quem chama -- em shadow/teste, um resolvedor
    sintético (dict CPF->id); em produção futura (fora do escopo desta
    missão, exige autorização própria), reaproveitaria
    `sync_new_employees.buscar_funcionario_por_cpf` já existente,
    nunca uma segunda implementação de busca."""
    dados = extrair_dados_holerite(texto)
    if not dados.get('cpf'):
        raise CpfAusenteError('documento nao trouxe CPF extraivel')
    if not dados.get('admissao'):
        raise DataEfetivaAusenteError('documento nao trouxe Data de Admissao extraivel')
    colaborador_id = resolver_colaborador_id(dados['cpf'])
    if colaborador_id is None:
        raise ColaboradorNaoIdentificadoError(
            'CPF extraido nao resolveu para nenhum colaborador conhecido')
    return VinculoIniciado(
        colaborador_id=colaborador_id,
        data_efetiva=_data_br_para_date(dados['admissao']),
        origem_evidencia=ORIGEM_HOLERITE_DATA_ADMISSAO,
    )
