"""Orquestrador do dry-run — liga núcleo (dominio.py) e adapters, sem
gravar nada. Aceita candidatos e "já existentes" já obtidos por leitura
(injeção), para não forçar acoplamento com uma biblioteca HTTP
específica aqui — quem chama decide como obteve a leitura (adapter
`airtable_leitura.py` em produção; conector interativo nesta rodada).

CPF completo é extraído do PDF (via pdfplumber) só em memória, usado
imediatamente para resolver func_id e descartado — nunca retorna no
resultado, nunca é logado.

Competência (Macro 5) é extraída do MESMO texto já obtido do PDF — para
holerite, reaproveita a única extração já feita para o CPF (nunca uma
segunda leitura do mesmo item); para extrato, que antes não lia o
conteúdo do PDF, esta é a única extração adicionada, seguindo o mesmo
padrão de isolamento por item em caso de falha (PDF corrompido derruba
só este item, nunca o lote inteiro).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..extracao_texto import extrair_texto_pdf as _extrair_texto_pdf
from . import dominio
from .contratos import (
    CandidatoCliente,
    CandidatoFuncionario,
    ClassificacaoCorrespondencia,
    ConfiguracaoExecucao,
    ItemManifestoExtrato,
    ItemManifestoHolerite,
    ResultadoCompetencia,
    ResultadoItem,
    TipoDocumental,
)

# `_extrair_texto_pdf` foi promovida para `magnata_os/documental/
# extracao_texto.py` (função pública `extrair_texto_pdf`), para reúso
# por outros módulos (ex.: classificacao/roteamento_documental.py) sem
# duplicar a lógica. Reimportada aqui com o nome antigo — nenhum
# chamador deste módulo (processar_holerite/processar_extrato) precisa
# mudar; comportamento idêntico.


@dataclass
class RelatorioLote:
    itens: list[ResultadoItem]
    relatorios_gerais_excluidos: list[str]

    def contagem(self) -> dict[str, int]:
        contagem = {}
        for item in self.itens:
            chave = item.classificacao.value
            contagem[chave] = contagem.get(chave, 0) + 1
        return contagem

    def contagem_competencia(self) -> dict[str, int]:
        """Agregado da dimensão de COMPETÊNCIA — independente da
        contagem por `classificacao` acima (Macro 5). Itens cujo PDF
        nunca foi lido (já `INVALID` por outro motivo) entram em
        'nao_computada', nunca num valor de `ResultadoCompetencia`
        inventado. Faz parte do relatório agregado completo produzido
        ANTES de qualquer escrita."""
        contagem: dict[str, int] = {}
        for item in self.itens:
            chave = item.resultado_competencia.value if item.resultado_competencia else 'nao_computada'
            contagem[chave] = contagem.get(chave, 0) + 1
        return contagem

    def itens_bloqueados_por_competencia(self) -> list[ResultadoItem]:
        """Itens com entidade resolvida (EXACT) e sem duplicidade, mas
        bloqueados só pela dimensão de competência — fila explícita para
        revisão humana. Nesta primeira versão, nunca remapeados
        automaticamente para a competência esperada."""
        bloqueados = {
            ResultadoCompetencia.DIVERGENTE,
            ResultadoCompetencia.AMBIGUA,
            ResultadoCompetencia.NAO_EXTRAIVEL,
        }
        return [
            item for item in self.itens
            if item.classificacao == ClassificacaoCorrespondencia.EXACT
            and not item.pronto_para_gravacao
            and item.resultado_competencia in bloqueados
        ]


def processar_holerite(
    item: ItemManifestoHolerite,
    pdf_bytes: bytes | None,
    config: ConfiguracaoExecucao,
    candidatos_funcionario: list[CandidatoFuncionario],
    func_ids_ja_com_holerite: set[str] | None,
) -> ResultadoItem:
    if pdf_bytes is None:
        from .contratos import MotivoSanitizado, ClassificacaoCorrespondencia
        return ResultadoItem(
            item.manifesto_item_id, TipoDocumental.HOLERITE,
            ClassificacaoCorrespondencia.INVALID, False, None, None, None,
            MotivoSanitizado.ARQUIVO_AUSENTE_NO_PACOTE)

    validacao = dominio.validar_pdf_bytes(pdf_bytes)

    cpf_extraido = None
    competencia_extraida = None
    if validacao.valido:
        # extração em memória, reaproveitada para CPF (só resolver
        # func_id, descartado ao sair deste escopo) e para competência
        # (Macro 5, requisito obrigatório: reutilizar a mesma extração
        # quando o fluxo já lê o PDF — nunca uma segunda leitura).
        # Achado do Ultrareview: um PDF com assinatura/tamanho válidos mas
        # estrutura interna corrompida fazia pdfplumber lançar exceção
        # sem tratamento, derrubando o lote inteiro — contraria "continuar
        # os casos válidos quando um caso isolado falhar". Corrigido:
        # falha de leitura vira classificação INVALID só deste item, o
        # lote segue para os demais.
        try:
            texto = _extrair_texto_pdf(pdf_bytes)
        except Exception:
            from .contratos import ClassificacaoCorrespondencia, MotivoSanitizado
            return ResultadoItem(
                item.manifesto_item_id, TipoDocumental.HOLERITE,
                ClassificacaoCorrespondencia.INVALID, False, None, None, None,
                MotivoSanitizado.PDF_ILEGIVEL)
        cpf_extraido = dominio.extrair_cpf_de_texto(texto)
        competencia_extraida = dominio.extrair_competencia_de_texto(texto)
        del texto

    correspondencia = dominio.resolver_funcionario(
        cpf_extraido, item.nome_manifesto, candidatos_funcionario)
    del cpf_extraido

    identidades = dominio.calcular_identidades(
        TipoDocumental.HOLERITE, config, correspondencia.entidade_id,
        validacao.hash_sha256, item.manifesto_item_id)

    documento_ja_existe = None
    if correspondencia.entidade_id and func_ids_ja_com_holerite is not None:
        documento_ja_existe = correspondencia.entidade_id in func_ids_ja_com_holerite

    resultado_competencia = None
    if competencia_extraida is not None:
        resultado_competencia = dominio.validar_competencia(competencia_extraida, config.ano, config.mes)

    return dominio.classificar_item(
        item.manifesto_item_id, TipoDocumental.HOLERITE, validacao,
        correspondencia, identidades, documento_ja_existe,
        competencia_extraida, resultado_competencia, config.ano, config.mes)


def processar_extrato(
    item: ItemManifestoExtrato,
    pdf_bytes: bytes | None,
    config: ConfiguracaoExecucao,
    candidatos_cliente: list[CandidatoCliente],
    cliente_ids_ja_com_extrato: set[str] | None,
) -> ResultadoItem:
    if pdf_bytes is None:
        from .contratos import MotivoSanitizado, ClassificacaoCorrespondencia
        return ResultadoItem(
            item.manifesto_item_id, TipoDocumental.EXTRATO_CLIENTE,
            ClassificacaoCorrespondencia.INVALID, False, None, None, None,
            MotivoSanitizado.ARQUIVO_AUSENTE_NO_PACOTE)

    validacao = dominio.validar_pdf_bytes(pdf_bytes)

    # Antes do Macro 5, este fluxo nunca lia o CONTEÚDO do PDF (só
    # `linha_bruta` do manifesto, para correspondência de cliente). A
    # competência exige o conteúdo — esta é a ÚNICA extração adicionada
    # aqui, uma vez por item, com o mesmo isolamento de falha já usado em
    # `processar_holerite`: PDF corrompido vira INVALID só deste item,
    # nunca derruba o lote inteiro.
    competencia_extraida = None
    if validacao.valido:
        try:
            texto = _extrair_texto_pdf(pdf_bytes)
        except Exception:
            from .contratos import ClassificacaoCorrespondencia, MotivoSanitizado
            return ResultadoItem(
                item.manifesto_item_id, TipoDocumental.EXTRATO_CLIENTE,
                ClassificacaoCorrespondencia.INVALID, False, None, None, None,
                MotivoSanitizado.PDF_ILEGIVEL)
        competencia_extraida = dominio.extrair_competencia_de_texto(texto)
        del texto

    # Correspondência estrita: CNPJ extraído de `linha_bruta` SEMPRE
    # tentado primeiro, mesmo quando o nome do manifesto está truncado e
    # idêntico ao de outro item (caso real: num=20/21 desta execução).
    # Nunca decide pelo nome truncado.
    correspondencia = dominio.resolver_cliente(
        item.linha_bruta, item.nome_manifesto, candidatos_cliente)

    identidades = dominio.calcular_identidades(
        TipoDocumental.EXTRATO_CLIENTE, config, correspondencia.entidade_id,
        validacao.hash_sha256, item.manifesto_item_id)

    documento_ja_existe = None
    if correspondencia.entidade_id and cliente_ids_ja_com_extrato is not None:
        documento_ja_existe = correspondencia.entidade_id in cliente_ids_ja_com_extrato

    resultado_competencia = None
    if competencia_extraida is not None:
        resultado_competencia = dominio.validar_competencia(competencia_extraida, config.ano, config.mes)

    return dominio.classificar_item(
        item.manifesto_item_id, TipoDocumental.EXTRATO_CLIENTE, validacao,
        correspondencia, identidades, documento_ja_existe,
        competencia_extraida, resultado_competencia, config.ano, config.mes)
