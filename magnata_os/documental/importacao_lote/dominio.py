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
    CompetenciaExtraida,
    ConfiguracaoExecucao,
    Identidades,
    MotivoSanitizado,
    ResultadoCompetencia,
    ResultadoCorrespondencia,
    StatusExtracaoCompetencia,
    TipoDocumental,
    ValidacaoPdf,
)

TAMANHO_MINIMO_PDF_BYTES = 100
ASSINATURA_PDF = b'%PDF'

_CNPJ_RE = re.compile(r'\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}')
_CPF_RE = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}')

# Competência numérica MM/AAAA (ex.: "07/2026", "07 / 2026"). Lookbehind
# negativo evita capturar a cauda de uma data completa DD/MM/AAAA (ex.:
# "05/07/2026") como se fosse a competência — mitigação adicional, não a
# defesa principal (essa é o marcador semântico obrigatório, ver
# `_MARCADOR_COMPETENCIA_RE` abaixo).
_COMPETENCIA_NUMERICA_RE = re.compile(r'(?<!\d{2}/)(?<!\d{2}-)\b(0[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})\b')

_MESES_PT_COMPETENCIA = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6,
    'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12,
}
_COMPETENCIA_NOME_MES_RE = re.compile(
    r'\b(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|'
    r'outubro|novembro|dezembro)\s*(?:/|de|,)?\s*(20\d{2})\b',
    re.IGNORECASE,
)

# Marcador semântico OBRIGATÓRIO (revisão adversarial desta rodada): uma
# data MM/AAAA ou "mês por extenso + ano" só conta como candidata a
# competência quando aparece na MESMA linha que um destes marcadores —
# nunca por coincidência. Data de pagamento, admissão, período de
# férias, data de impressão etc. nunca têm estas palavras — ficam de
# fora por construção, mesmo que o formato MM/AAAA bata.
_MARCADOR_COMPETENCIA_RE = re.compile(
    r'compet[êe]ncia|m[êe]s\s+de\s+refer[êe]ncia', re.IGNORECASE)


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


# ── Competência documental (Macro 5) ─────────────────────────────────────
#
# Extração e validação de competência são passos PUROS e SEPARADOS:
#   1. extrair_competencia_de_texto  — só olha o CONTEÚDO do PDF, nunca
#      sabe qual competência é esperada.
#   2. validar_competencia           — compara o resultado da extração
#      contra a competência ESPERADA (`ConfiguracaoExecucao.ano`/`.mes`,
#      nunca resolvida por este módulo sozinho).
# Nunca fundidas com `resolver_funcionario`/`resolver_cliente` — mesma
# disciplina de dimensões independentes do CLAUDE.md raiz §4. Nesta
# primeira versão, uma execução tem exatamente UMA competência esperada;
# item divergente/ambíguo/não-extraível fica isolado e bloqueado, nunca
# remapeado automaticamente.

def _normalizar_nome_mes(nome_mes: str) -> str:
    s = unicodedata.normalize('NFKD', nome_mes)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _datas_candidatas_na_linha(linha: str) -> list[tuple[int, int, str]]:
    achados: list[tuple[int, int, str]] = []
    for m in _COMPETENCIA_NUMERICA_RE.finditer(linha):
        mes, ano = int(m.group(1)), int(m.group(2))
        achados.append((ano, mes, 'mm_aaaa_numerico'))
    for m in _COMPETENCIA_NOME_MES_RE.finditer(linha):
        mes = _MESES_PT_COMPETENCIA.get(_normalizar_nome_mes(m.group(1)))
        if mes is None:
            continue
        ano = int(m.group(2))
        achados.append((ano, mes, 'nome_mes_pt'))
    return achados


def extrair_competencia_de_texto(texto: str) -> CompetenciaExtraida:
    """Extrai a competência (mês/ano) do CONTEÚDO do PDF — nunca da
    configuração, que é só a competência ESPERADA. Nunca retorna nem usa
    o texto/trecho bruto no resultado — só (ano, mes) e um código de
    estratégia sanitizado (auditoria).

    Revisão adversarial (Macro 5): uma data só é candidata quando aparece
    na MESMA linha de um marcador semântico explícito de competência
    (`_MARCADOR_COMPETENCIA_RE`) — data de pagamento, admissão, período
    de férias, impressão, ou qualquer MM/AAAA "solto" no texto NUNCA
    vencem uma competência marcada, e nunca são aceitas sozinhas por
    coincidência (o texto extraído de PDF já vem quebrado em linhas por
    `pdfplumber`, uma por campo do documento — mesmo padrão usado para
    granularidade aqui). Duas estratégias tentadas por linha marcada:
    (1) numérica MM/AAAA; (2) nome do mês por extenso em português + ano.

    Mais de um valor (ano, mes) DISTINTO encontrado em linhas marcadas —
    mesma estratégia ou estratégias diferentes, mesma linha ou linhas
    diferentes — nunca é decidido por aproximação: vira AMBIGUA. Nenhuma
    linha marcada com data válida vira NAO_ENCONTRADA (inclusive quando
    só existem datas genéricas sem marcador, ou quando a linha marcada
    tem mês/ano fora do formato válido — nunca uma confirmação por mera
    coincidência)."""
    if not texto:
        return CompetenciaExtraida(StatusExtracaoCompetencia.NAO_ENCONTRADA, None, None)

    achados: list[tuple[int, int, str]] = []
    for linha in texto.split('\n'):
        if not _MARCADOR_COMPETENCIA_RE.search(linha):
            continue
        achados.extend(_datas_candidatas_na_linha(linha))

    distintos = {(ano, mes) for ano, mes, _estrategia in achados}
    if not distintos:
        return CompetenciaExtraida(StatusExtracaoCompetencia.NAO_ENCONTRADA, None, None)
    if len(distintos) > 1:
        return CompetenciaExtraida(StatusExtracaoCompetencia.AMBIGUA, None, None)

    ano_mes = next(iter(distintos))
    estrategia = achados[0][2]
    return CompetenciaExtraida(StatusExtracaoCompetencia.ENCONTRADA, ano_mes, estrategia)


def validar_competencia(
    extraida: CompetenciaExtraida, ano_esperado: int, mes_esperado: int,
) -> ResultadoCompetencia:
    """Compara a competência extraída do CONTEÚDO do PDF com a
    competência ESPERADA — a configuração (`ConfiguracaoExecucao`) é
    tratada só como o valor esperado, nunca como fonte de verdade do que
    está no documento (requisito obrigatório Macro 5). Só `CONFIRMADA`
    libera `pronto_para_gravacao`; qualquer outro resultado bloqueia a
    gravação deste item, isolado, sem remapeamento automático."""
    if extraida.status == StatusExtracaoCompetencia.NAO_ENCONTRADA:
        return ResultadoCompetencia.NAO_EXTRAIVEL
    if extraida.status == StatusExtracaoCompetencia.AMBIGUA:
        return ResultadoCompetencia.AMBIGUA
    if extraida.ano_mes == (ano_esperado, mes_esperado):
        return ResultadoCompetencia.CONFIRMADA
    return ResultadoCompetencia.DIVERGENTE


# Únicos códigos de estratégia que `extrair_competencia_de_texto` pode
# produzir — usado como lista branca pela defesa obrigatória do
# escritor (`competencia_apta_para_gravacao`), nunca aceita um valor de
# estratégia arbitrário vindo de um `ResultadoItem` construído por outro
# caminho.
ESTRATEGIAS_COMPETENCIA_VALIDAS = frozenset({'mm_aaaa_numerico', 'nome_mes_pt'})

_ANO_MINIMO_PLAUSIVEL = 2000
_ANO_MAXIMO_PLAUSIVEL = 2099


def competencia_apta_para_gravacao(
    resultado_competencia: ResultadoCompetencia | None,
    ano_mes_extraido: tuple[int, int] | None,
    estrategia: str | None,
    ano_esperado: int,
    mes_esperado: int,
) -> bool:
    """Defesa em profundidade (revisão adversarial Macro 5): NUNCA
    confia só no enum `resultado_competencia` informado pelo chamador —
    reconfirma aqui, a partir dos valores primitivos, que a competência
    extraída é de fato igual à esperada, com evidência consistente.
    Único ponto que decide "apto para gravar" — usado tanto por
    `classificar_item` (decisão do dry-run) quanto por `escritor.py`
    (defesa obrigatória, independente, no momento real da escrita).

    Recusa (retorna False) quando QUALQUER uma destas condições vale —
    mesmo que `resultado_competencia` diga CONFIRMADA:
      * `resultado_competencia` não é CONFIRMADA (ausente, DIVERGENTE,
        AMBIGUA ou NAO_EXTRAIVEL);
      * a competência esperada (`ano_esperado`/`mes_esperado`) é
        implausível (mês fora de 1-12, ano fora de uma faixa plausível)
        — nunca confirma contra uma configuração claramente inválida;
      * `ano_mes_extraido` está ausente — não há evidência extraída
        para comprovar a igualdade;
      * `estrategia` está ausente ou não é uma das estratégias que este
        módulo sabe produzir (`ESTRATEGIAS_COMPETENCIA_VALIDAS`) —
        nunca aceita um código de estratégia arbitrário;
      * o mês/ano extraído está fora da faixa plausível;
      * o valor extraído, comparado byte a byte com o esperado, diverge
        — reconfirmação direta, nunca herdada do enum sozinho.
    """
    if resultado_competencia != ResultadoCompetencia.CONFIRMADA:
        return False
    if not (1 <= mes_esperado <= 12):
        return False
    if not (_ANO_MINIMO_PLAUSIVEL <= ano_esperado <= _ANO_MAXIMO_PLAUSIVEL):
        return False
    if ano_mes_extraido is None:
        return False
    if estrategia not in ESTRATEGIAS_COMPETENCIA_VALIDAS:
        return False

    ano_extraido, mes_extraido = ano_mes_extraido
    if not (1 <= mes_extraido <= 12):
        return False
    if not (_ANO_MINIMO_PLAUSIVEL <= ano_extraido <= _ANO_MAXIMO_PLAUSIVEL):
        return False

    return (ano_extraido, mes_extraido) == (ano_esperado, mes_esperado)


# ── Classificação final (combina validação + correspondência + duplicidade) ─

def classificar_item(
    manifesto_item_id: str,
    tipo: TipoDocumental,
    validacao: ValidacaoPdf,
    correspondencia: ResultadoCorrespondencia,
    identidades: Identidades,
    documento_ja_existe: bool | None,
    competencia_extraida: CompetenciaExtraida | None = None,
    resultado_competencia: ResultadoCompetencia | None = None,
    ano_esperado: int | None = None,
    mes_esperado: int | None = None,
) -> 'ResultadoItem':
    """Função pura de decisão — nunca grava nada, só classifica.

    `documento_ja_existe`: True/False vindos de leitura já feita no
    Airtable (fora deste módulo); None quando a leitura não pôde ser
    feita (conector indisponível) — nesse caso o item nunca é elevado a
    EXACT/pronto-para-gravação; fica marcado como bloqueado por leitura
    ausente, nunca tratado como 'sem duplicidade' por omissão.

    `competencia_extraida`/`resultado_competencia`/`ano_esperado`/
    `mes_esperado` (Macro 5): dimensão independente da correspondência
    de entidade — nunca fundida com `classificacao`. Os dois primeiros
    são `None` só quando o PDF nunca chegou a ser lido (item já
    `INVALID` por outro motivo); quando presentes, são sempre anexados
    ao `ResultadoItem`, em qualquer ramo — para que o relatório agregado
    tenha visibilidade completa da competência mesmo em itens bloqueados
    por outro motivo (entidade, duplicidade, leitura ausente). Só o ramo
    final (EXACT + sem duplicidade) decide `pronto_para_gravacao` — e
    faz isso via `competencia_apta_para_gravacao` (revisão adversarial:
    nunca confia só no enum `resultado_competencia`, reconfirma a
    igualdade extraído==esperado a partir dos valores primitivos).
    """
    from .contratos import ResultadoItem  # import local evita ciclo

    ano_mes_extraido = competencia_extraida.ano_mes if competencia_extraida is not None else None
    estrategia_competencia = competencia_extraida.estrategia if competencia_extraida is not None else None

    if not validacao.valido:
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.INVALID, False,
            None, None, None, validacao.motivo)

    if correspondencia.classificacao != ClassificacaoCorrespondencia.EXACT:
        # ambiguous / not_found / conflict — nunca gravado automaticamente,
        # vai para a fila de exceções.
        return ResultadoItem(
            manifesto_item_id, tipo, correspondencia.classificacao, False,
            None, None, None, correspondencia.motivo, correspondencia.criterio_usado,
            resultado_competencia, ano_mes_extraido, estrategia_competencia)

    if documento_ja_existe is None:
        # EXACT na correspondência, mas sem confirmação de duplicidade —
        # nunca elevado a pronto_para_gravacao por omissão de leitura.
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.EXACT, False,
            correspondencia.entidade_id, identidades.identidade_documental,
            truncar_hash(identidades.identidade_documental),
            MotivoSanitizado.LEITURA_AIRTABLE_INDISPONIVEL, correspondencia.criterio_usado,
            resultado_competencia, ano_mes_extraido, estrategia_competencia)

    if documento_ja_existe:
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.DUPLICATE, False,
            correspondencia.entidade_id, identidades.identidade_documental,
            truncar_hash(identidades.identidade_documental),
            MotivoSanitizado.DOCUMENTO_JA_EXISTENTE, correspondencia.criterio_usado,
            resultado_competencia, ano_mes_extraido, estrategia_competencia)

    apto_por_competencia = (
        ano_esperado is not None and mes_esperado is not None
        and competencia_apta_para_gravacao(
            resultado_competencia, ano_mes_extraido, estrategia_competencia,
            ano_esperado, mes_esperado)
    )
    if apto_por_competencia:
        # EXACT + validado + confirmado sem duplicidade prévia por leitura
        # real + competência do PDF confirmada e igual à esperada (via
        # `competencia_apta_para_gravacao`, reconfirmada por valor, nunca
        # só pelo enum) → pronto para a fase de escrita. Este dry-run
        # nunca grava — a gravação é uma fase futura, fora deste comando.
        return ResultadoItem(
            manifesto_item_id, tipo, ClassificacaoCorrespondencia.EXACT, True,
            correspondencia.entidade_id, identidades.identidade_documental,
            truncar_hash(identidades.identidade_documental),
            MotivoSanitizado.OK, correspondencia.criterio_usado,
            resultado_competencia, ano_mes_extraido, estrategia_competencia)

    # EXACT, sem duplicidade — mas a competência não foi confirmada
    # (não-extraível, ambígua ou divergente da esperada). Bloqueado só
    # nesta dimensão: `classificacao` continua EXACT (a entidade FOI
    # resolvida corretamente), só `pronto_para_gravacao` cai para False.
    motivo_competencia = {
        ResultadoCompetencia.DIVERGENTE: MotivoSanitizado.COMPETENCIA_DIVERGENTE,
        ResultadoCompetencia.AMBIGUA: MotivoSanitizado.COMPETENCIA_AMBIGUA,
    }.get(resultado_competencia, MotivoSanitizado.COMPETENCIA_NAO_EXTRAIVEL)

    return ResultadoItem(
        manifesto_item_id, tipo, ClassificacaoCorrespondencia.EXACT, False,
        correspondencia.entidade_id, identidades.identidade_documental,
        truncar_hash(identidades.identidade_documental),
        motivo_competencia, correspondencia.criterio_usado,
        resultado_competencia, ano_mes_extraido, estrategia_competencia)
