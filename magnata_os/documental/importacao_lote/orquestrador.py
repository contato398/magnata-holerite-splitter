"""Orquestrador do dry-run — liga núcleo (dominio.py) e adapters, sem
gravar nada. Aceita candidatos e "já existentes" já obtidos por leitura
(injeção), para não forçar acoplamento com uma biblioteca HTTP
específica aqui — quem chama decide como obteve a leitura (adapter
`airtable_leitura.py` em produção; conector interativo nesta rodada).

CPF completo é extraído do PDF (via pdfplumber) só em memória, usado
imediatamente para resolver func_id e descartado — nunca retorna no
resultado, nunca é logado.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from . import dominio
from .contratos import (
    CandidatoCliente,
    CandidatoFuncionario,
    ConfiguracaoExecucao,
    ItemManifestoExtrato,
    ItemManifestoHolerite,
    ResultadoItem,
    TipoDocumental,
)


def _extrair_texto_pdf(conteudo: bytes) -> str:
    import pdfplumber
    texto = ''
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pagina in pdf.pages:
            texto += (pagina.extract_text() or '') + '\n'
    return texto


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
    if validacao.valido:
        # extração em memória, só para resolver func_id — descartada ao
        # sair deste escopo de função, nunca propagada adiante.
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

    return dominio.classificar_item(
        item.manifesto_item_id, TipoDocumental.HOLERITE, validacao,
        correspondencia, identidades, documento_ja_existe)


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

    return dominio.classificar_item(
        item.manifesto_item_id, TipoDocumental.EXTRATO_CLIENTE, validacao,
        correspondencia, identidades, documento_ja_existe)
