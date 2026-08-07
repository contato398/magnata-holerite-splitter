"""Contratos (tipos puros) da importação em lote.

Sem dependência de Flask, driver de banco, boto3 ou cliente Airtable —
só `dataclasses`, `Enum` e tipos nativos, seguindo a mesma regra de
pureza de domínio já usada em `magnata_os/documental/modulo01/dominio.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TipoDocumental(str, Enum):
    HOLERITE = 'holerite'
    EXTRATO_CLIENTE = 'extrato_cliente'


class ClassificacaoCorrespondencia(str, Enum):
    """Resultado da correspondência de uma entidade (colaborador ou
    cliente) contra o cadastro. Só EXACT pode seguir para gravação —
    todas as outras vão para a fila de exceções (nunca decididas
    automaticamente)."""
    EXACT = 'exact'
    DUPLICATE = 'duplicate'
    AMBIGUOUS = 'ambiguous'
    NOT_FOUND = 'not_found'
    CONFLICT = 'conflict'
    INVALID = 'invalid'


class MotivoSanitizado(str, Enum):
    """Códigos de motivo — nunca texto livre com dado pessoal."""
    OK = 'ok'
    PDF_SEM_ASSINATURA = 'pdf_sem_assinatura'
    PDF_VAZIO = 'pdf_vazio'
    PDF_MIME_INESPERADO = 'pdf_mime_inesperado'
    ARQUIVO_AUSENTE_NO_PACOTE = 'arquivo_ausente_no_pacote'
    CAMPO_MANIFESTO_AUSENTE = 'campo_manifesto_ausente'
    VERSAO_ANTIGA_BLOQUEADA = 'versao_antiga_bloqueada'
    COLABORADOR_NAO_ENCONTRADO = 'colaborador_nao_encontrado'
    COLABORADOR_AMBIGUO = 'colaborador_ambiguo'
    CLIENTE_NAO_ENCONTRADO = 'cliente_nao_encontrado'
    CLIENTE_AMBIGUO = 'cliente_ambiguo'
    CLIENTE_CONFLITO_CNPJ = 'cliente_conflito_cnpj'
    DOCUMENTO_JA_EXISTENTE = 'documento_ja_existente'
    RELATORIO_GERAL_EXCLUIDO = 'relatorio_geral_excluido_do_fluxo'
    LEITURA_AIRTABLE_INDISPONIVEL = 'leitura_airtable_indisponivel'


@dataclass(frozen=True)
class ConfiguracaoExecucao:
    """Parâmetros de UMA execução — nunca constantes do módulo (Ajuste 4
    da revisão do UltraPlan). `mes_cont_id` é o record id canônico já
    resolvido e aprovado para esta competência; o módulo nunca resolve
    competência por nome sozinho."""
    mes_cont_id: str
    ano: int
    mes: int
    message_id_estavel: str
    package_sha256: str
    mes_cont_id_duplicado_bloqueado: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ItemManifestoHolerite:
    manifesto_item_id: str          # ex.: "holerite:001"
    source_service_number: str | None   # prefixo numérico de `client` — nunca ID canônico sem prova
    nome_manifesto: str
    cpf_mascarado: str
    filename: str
    pagina: int


@dataclass(frozen=True)
class ItemManifestoExtrato:
    manifesto_item_id: str          # ex.: "extrato:20"
    source_service_number: str      # campo `num` do manifesto — nunca ID canônico sem prova
    nome_manifesto: str
    linha_bruta: str                # texto livre com CNPJ embutido
    filename: str
    paginas_origem: tuple[int, ...]


@dataclass(frozen=True)
class ValidacaoPdf:
    valido: bool
    motivo: MotivoSanitizado
    tamanho_bytes: int
    hash_sha256: str | None


@dataclass(frozen=True)
class CandidatoFuncionario:
    func_id: str
    cpf: str | None
    nome_normalizado: str


@dataclass(frozen=True)
class CandidatoCliente:
    cliente_id: str
    cnpj: str | None
    nome_normalizado: str


@dataclass(frozen=True)
class ResultadoCorrespondencia:
    classificacao: ClassificacaoCorrespondencia
    entidade_id: str | None         # record id resolvido, só quando EXACT
    motivo: MotivoSanitizado
    criterio_usado: str | None = None   # ex.: "cpf_exato", "cnpj_exato" — auditoria sanitizada


@dataclass(frozen=True)
class Identidades:
    identidade_documental: str | None   # None se entidade não resolvida (EXACT)
    identidade_ingestao: str


@dataclass(frozen=True)
class ResultadoItem:
    """Resultado de UM item no dry-run. `classificacao` é o vocabulário
    pedido no comando (exact/duplicate/ambiguous/not_found/conflict/
    invalid) — é o campo primário do relatório. `pronto_para_gravacao`
    é só True quando EXACT + validado + confirmado sem duplicidade por
    leitura real no Airtable (nunca por omissão de leitura)."""
    manifesto_item_id: str
    tipo_documental: TipoDocumental
    classificacao: ClassificacaoCorrespondencia
    pronto_para_gravacao: bool
    entidade_resolvida: str | None
    identidade_documental: str | None
    identidade_documental_truncada: str | None
    motivo: MotivoSanitizado
    criterio_usado: str | None = None
