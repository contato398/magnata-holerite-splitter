"""Núcleo puro da importação em lote: validação, normalização,
correspondência determinística, identidades e classificação.

Regra de pureza (magnata_os/CLAUDE.md): nada aqui importa `flask`,
driver de banco, `boto3` nem cliente Airtable. Extração de texto de PDF
(pdfplumber) fica no adapter — este módulo só recebe bytes/strings já
obtidos e devolve decisões.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from .contratos import (
    CandidatoCliente,
    CandidatoFuncionario,
    ClassificacaoCorrespondencia,
    ConfiguracaoExecucao,
    Identidades,
    MotivoSanitizado,
    ResultadoCorrespondencia,
    TipoDocumental,
    ValidacaoPdf,
)

TAMANHO_MINIMO_PDF_BYTES = 100
ASSINATURA_PDF = b'%PDF'

_CNPJ_RE = re.compile(r'\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}')
_CPF_RE = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}')


# ── Validação ─────────────────────────────────────────────────────────────

def validar_pdf_bytes(conteudo: bytes) -> ValidacaoPdf:
    """Confere assinatura, tamanho mínimo e não-vazio. Nunca confia só no
    MIME declarado — a assinatura de bytes é a fonte de verdade (mesmo
    padrão já usado em /processar-holerites)."""
    tamanho = len(conteudo)
    if tamanho == 0:
        return ValidacaoPdf(False, MotivoSanitizado.PDF_VAZIO, 0, None)
    if tamanho < TAMANHO_MINIMO_PDF_BYTES:
        return ValidacaoPdf(False, MotivoSanitizado.PDF_VAZIO, tamanho, None)
    if not conteudo[:4] == ASSINATURA_PDF:
        return ValidacaoPdf(False, MotivoSanitizado.PDF_SEM_ASSINATURA, tamanho, None)
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    return ValidacaoPdf(True, MotivoSanitizado.OK, tamanho, hash_sha256)


# ── Normalização ──────────────────────────────────────────────────────────

def normalizar_nome(nome: str) -> str:
    """Maiúsculas, sem acento, espaços colapsados — mesmo critério já
    usado em produção (`_normalizar_nome` em app.py), reimplementado aqui
    para manter o núcleo sem import de app.py (legado protegido)."""
    if not nome:
        return ''
    s = unicodedata.normalize('NFKD', nome)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s+', ' ', s).strip()
    return s.upper()


def normalizar_cnpj(cnpj: str) -> str:
    return re.sub(r'\D', '', cnpj or '')


def normalizar_cpf(cpf: str) -> str:
    return re.sub(r'\D', '', cpf or '')


def extrair_cnpjs_de_texto(texto: str) -> list[str]:
    """Extrai CNPJs (14 dígitos, normalizados) de um texto livre — usado
    para resolver cliente a partir do campo `line` do manifesto de
    extratos, que não traz CNPJ como campo estruturado."""
    if not texto:
        return []
    candidatos = [normalizar_cnpj(c) for c in _CNPJ_RE.findall(texto)]
    return [c for c in candidatos if len(c) == 14]


def extrair_cpf_de_texto(texto: str) -> str | None:
    """Extrai o primeiro CPF completo (formato XXX.XXX.XXX-XX) de um
    texto — usado só em memória, sobre o texto já extraído do PDF, pelo
    tempo mínimo necessário para resolver func_id. Nunca retorna mais
    que o necessário para a chamada corrente."""
    if not texto:
        return None
    m = _CPF_RE.search(texto)
    return normalizar_cpf(m.group(0)) if m else None


# ── Correspondência de colaborador ──────────────────────────────────────

def resolver_funcionario(
    cpf_extraido: str | None,
    nome_manifesto: str,
    candidatos: list[CandidatoFuncionario],
) -> ResultadoCorrespondencia:
    """Ordem determinística: CPF exato → nome normalizado único →
    ambíguo/não encontrado. Nunca decide por aproximação."""
    if cpf_extraido:
        achados = [c for c in candidatos if c.cpf and normalizar_cpf(c.cpf) == cpf_extraido]
        if len(achados) == 1:
            return ResultadoCorrespondencia(
                ClassificacaoCorrespondencia.EXACT, achados[0].func_id, MotivoSanitizado.OK, 'cpf_exato')
        if len(achados) > 1:
            return ResultadoCorrespondencia(
                ClassificacaoCorrespondencia.AMBIGUOUS, None, MotivoSanitizado.COLABORADOR_AMBIGUO, 'cpf_exato')

    nome_norm = normalizar_nome(nome_manifesto)
    achados_nome = [c for c in candidatos if c.nome_normalizado == nome_norm]
    if len(achados_nome) == 1:
        return ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.EXACT, achados_nome[0].func_id, MotivoSanitizado.OK, 'nome_normalizado_exato')
    if len(achados_nome) > 1:
        return ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.AMBIGUOUS, None, MotivoSanitizado.COLABORADOR_AMBIGUO, 'nome_normalizado_exato')

    return ResultadoCorrespondencia(
        ClassificacaoCorrespondencia.NOT_FOUND, None, MotivoSanitizado.COLABORADOR_NAO_ENCONTRADO, None)


# ── Correspondência de cliente ───────────────────────────────────────────

def resolver_cliente(
    linha_bruta: str,
    nome_manifesto: str,
    candidatos: list[CandidatoCliente],
) -> ResultadoCorrespondencia:
    """Ordem determinística e ESTRITA (Ajuste 10 + determinação 2 desta
    rodada): CNPJ exato extraído de `linha_bruta` primeiro — mesmo para
    itens com nome truncado idêntico (ex.: num=20/21), a tentativa por
    CNPJ acontece ANTES de qualquer decisão por nome. Só cai para nome
    normalizado único se não houver CNPJ extraível na linha. Nunca decide
    pelo nome truncado quando há CNPJs candidatos divergentes."""
    cnpjs = extrair_cnpjs_de_texto(linha_bruta)
    if cnpjs:
        achados_cnpj = [c for c in candidatos if c.cnpj and normalizar_cnpj(c.cnpj) in cnpjs]
        # dedup por cliente_id (o mesmo CNPJ pode aparecer >1x na linha)
        achados_cnpj_unicos = list({c.cliente_id: c for c in achados_cnpj}.values())
        if len(achados_cnpj_unicos) == 1:
            return ResultadoCorrespondencia(
                ClassificacaoCorrespondencia.EXACT, achados_cnpj_unicos[0].cliente_id,
                MotivoSanitizado.OK, 'cnpj_exato')
        if len(achados_cnpj_unicos) > 1:
            return ResultadoCorrespondencia(
                ClassificacaoCorrespondencia.CONFLICT, None,
                MotivoSanitizado.CLIENTE_CONFLITO_CNPJ, 'cnpj_exato')
        # CNPJ(s) extraído(s) da linha mas nenhum bate no cadastro —
        # não cai para nome: é not_found explícito, não ambiguidade de nome.
        return ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.NOT_FOUND, None,
            MotivoSanitizado.CLIENTE_NAO_ENCONTRADO, 'cnpj_exato')

    nome_norm = normalizar_nome(nome_manifesto)
    achados_nome = [c for c in candidatos if c.nome_normalizado == nome_norm]
    if len(achados_nome) == 1:
        return ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.EXACT, achados_nome[0].cliente_id,
            MotivoSanitizado.OK, 'nome_normalizado_unico')
    if len(achados_nome) > 1:
        return ResultadoCorrespondencia(
            ClassificacaoCorrespondencia.AMBIGUOUS, None,
            MotivoSanitizado.CLIENTE_AMBIGUO, 'nome_normalizado_unico')

    return ResultadoCorrespondencia(
        ClassificacaoCorrespondencia.NOT_FOUND, None, MotivoSanitizado.CLIENTE_NAO_ENCONTRADO, None)


# ── Identidades ───────────────────────────────────────────────────────────

def calcular_identidade_documental(
    tipo: TipoDocumental, mes_cont_id: str, entidade_id: str, pdf_hash_sha256: str,
) -> str:
    """Identidade do DOCUMENTO — só IDs já resolvidos, nunca CPF/nome
    (Ajuste 1). Detecta o mesmo documento chegando por outro pacote."""
    base = f'{tipo.value}|{mes_cont_id}|{entidade_id}|{pdf_hash_sha256}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def calcular_identidade_ingestao(
    message_id_estavel: str, package_sha256: str, manifesto_item_id: str,
) -> str:
    """Identidade da OCORRÊNCIA de processamento — identificador estável
    de origem (nunca data em texto, Ajuste 3), hash do pacote real e o
    item do manifesto."""
    base = f'{message_id_estavel}|{package_sha256}|{manifesto_item_id}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def calcular_identidades(
    tipo: TipoDocumental,
    config: ConfiguracaoExecucao,
    entidade_id: str | None,
    pdf_hash_sha256: str | None,
    manifesto_item_id: str,
) -> Identidades:
    identidade_documental = None
    if entidade_id and pdf_hash_sha256:
        identidade_documental = calcular_identidade_documental(
            tipo, config.mes_cont_id, entidade_id, pdf_hash_sha256)
    identidade_ingestao = calcular_identidade_ingestao(
        config.message_id_estavel, config.package_sha256, manifesto_item_id)
    return Identidades(identidade_documental, identidade_ingestao)


def truncar_hash(hash_hex: str | None, tamanho: int = 12) -> str | None:
    """Trunca um hash para uso em relatório/log — nunca o hash completo
    de dado sensível é necessário para auditoria humana."""
    if not hash_hex:
        return None
    return hash_hex[:tamanho]


# ── Classificação final (combina validação + correspondência + duplicidade) ─

def classificar_item(
    manifesto_item_id: str,
    tipo: TipoDocumental,
    validacao: ValidacaoPdf,
    correspondencia: ResultadoCorrespondencia,
    identidades: Identidades,
    documento_ja_existe: bool | None,
) -> 'ResultadoItem':
    """Função pura de decisão — nunca grava nada, só classifica.

    `documento_ja_existe`: True/False vindos de leitura já feita no
    Airtable (fora deste módulo); None quando a leitura não pôde ser
    feita (conector indisponível) — nesse caso o item nunca é elevado a
    EXACT/pronto-para-gravação; fica marcado como bloqueado por leitura
    ausente, nunca tratado como 'sem duplicidade' por omissão.
    """
    from .contratos import ResultadoItem  # import local evita ciclo

    if not validacao.valido:
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.INVALID, False,
            None, None, None, validacao.motivo)

    if correspondencia.classificacao != ClassificacaoCorrespondencia.EXACT:
        # ambiguous / not_found / conflict — nunca gravado automaticamente,
        # vai para a fila de exceções.
        return ResultadoItem(
            manifesto_item_id, tipo, correspondencia.classificacao, False,
            None, None, None, correspondencia.motivo, correspondencia.criterio_usado)

    if documento_ja_existe is None:
        # EXACT na correspondência, mas sem confirmação de duplicidade —
        # nunca elevado a pronto_para_gravacao por omissão de leitura.
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.EXACT, False,
            correspondencia.entidade_id, identidades.identidade_documental,
            truncar_hash(identidades.identidade_documental),
            MotivoSanitizado.LEITURA_AIRTABLE_INDISPONIVEL, correspondencia.criterio_usado)

    if documento_ja_existe:
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.DUPLICATE, False,
            correspondencia.entidade_id, identidades.identidade_documental,
            truncar_hash(identidades.identidade_documental),
            MotivoSanitizado.DOCUMENTO_JA_EXISTENTE, correspondencia.criterio_usado)

    # EXACT + validado + confirmado sem duplicidade prévia por leitura real
    # → pronto para a fase de escrita. Este dry-run nunca grava — a
    # gravação é uma fase futura, fora deste comando.
    return ResultadoItem(
        manifesto_item_id, tipo, ClassificacaoCorrespondencia.EXACT, True,
        correspondencia.entidade_id, identidades.identidade_documental,
        truncar_hash(identidades.identidade_documental),
        MotivoSanitizado.OK, correspondencia.criterio_usado)
