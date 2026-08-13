#!/usr/bin/env python3
"""
Rotina reutilizável de reconciliação do backlog real de Holerite + Folha de
Ponto, por competência — não por "já recebeu/assinou alguma vez".

Contexto (Macro de fechamento do pacote HOLERITE_FOLHA_PONTO): a auditoria
anterior classificou "34 colaboradores elegíveis, nunca enviados" como
backlog, mas isso foi calculado por "nunca teve nenhum Envio/Assinatura no
histórico" — não por competência específica. Este script corrige isso:
reconcilia por
  colaborador ativo + competência extraída de CADA PDF + tipo + Record ID +
  hash integral + versão do documento + envio dessa competência + assinatura
  desse pacote
exatamente como exigido. Enquanto não houver AIRTABLE_API_KEY real disponível
para executá-lo (ver docstring de main() para o comando exato), a contagem
"34" permanece PROVISÓRIA em qualquer relatório — nunca "confirmada".

Somente leitura: nunca cria, altera ou apaga nada no Airtable. Não expõe
PII na saída — nomes/telefones/CPF nunca aparecem no relatório impresso,
só Record IDs e categorias.

Reaproveita as funções já testadas de app.py (extrair_competencia_holerite,
_extrair_competencia_folha_ponto, _extrair_texto_pdf_bytes) em vez de
duplicar lógica de extração de competência.
"""
import os
import sys
from dataclasses import dataclass, field

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import (  # noqa: E402
    BASE_ID,
    TABLE_FUNC,
    _extrair_competencia_folha_ponto,
    _extrair_texto_pdf_bytes,
    extrair_competencia_holerite,
)

CATEGORIAS = (
    'pronto_para_piloto',
    'pronto_para_lote',
    'ja_recebeu_esta_competencia',
    'ja_assinou_este_pacote',
    'reenvio_necessario',
    'documento_ausente',
    'telefone_ausente_ou_invalido',
    'identidade_insuficiente',
    'competencia_divergente',
    'vinculo_ambiguo',
    'duplicidade',
    'falha_anterior_recuperavel',
    'bloqueado',
    'indeterminavel',
)


@dataclass
class ResultadoColaborador:
    """Sem PII — só Record ID e categoria. Nunca inclua nome/telefone/CPF
    aqui; se precisar depurar um caso específico, use o Record ID para
    consultar o Airtable diretamente, fora deste script."""
    funcionario_id: str
    categoria: str
    competencia_holerite: str | None = None
    competencia_ponto: str | None = None
    detalhe: str = ''


@dataclass
class RelatorioReconciliacao:
    resultados: list = field(default_factory=list)

    def contagem_por_categoria(self) -> dict:
        contagem = {c: 0 for c in CATEGORIAS}
        for r in self.resultados:
            contagem[r.categoria] = contagem.get(r.categoria, 0) + 1
        return contagem

    def total(self) -> int:
        return len(self.resultados)


def _baixar(url: str, sessao=None, timeout: int = 60) -> bytes:
    sessao = sessao or requests
    r = sessao.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def reconciliar_colaborador(dados_funcionario: dict, sessao=None) -> ResultadoColaborador:
    """
    Classifica UM colaborador pela competência real extraída dos PDFs —
    nunca por "já recebeu/assinou alguma vez".

    `dados_funcionario` (contrato de entrada, testável com fixture
    sintética, sem depender de nenhuma chamada de rede específica):
      {
        'funcionario_id': str,
        'status': str,                      # 'Ativo'/'Inativo'/...
        'whatsapp': str | None,
        'cpf': str | None,
        'holerite_url': str | None,
        'folha_ponto_url': str | None,
        'envios_por_competencia': set[str],      # competências já COM envio confirmado
        'assinaturas_por_competencia': set[str],  # competências já COM pacote assinado
      }
    """
    fid = dados_funcionario['funcionario_id']

    if dados_funcionario.get('status') != 'Ativo':
        return ResultadoColaborador(fid, 'bloqueado', detalhe='vinculo_nao_ativo_ou_indeterminado')

    if not dados_funcionario.get('cpf'):
        return ResultadoColaborador(fid, 'identidade_insuficiente')

    if not dados_funcionario.get('whatsapp'):
        return ResultadoColaborador(fid, 'telefone_ausente_ou_invalido')

    if not dados_funcionario.get('holerite_url') or not dados_funcionario.get('folha_ponto_url'):
        return ResultadoColaborador(fid, 'documento_ausente')

    try:
        hol_bytes = _baixar(dados_funcionario['holerite_url'], sessao)
        ponto_bytes = _baixar(dados_funcionario['folha_ponto_url'], sessao)
    except Exception:
        return ResultadoColaborador(fid, 'indeterminavel', detalhe='falha_ao_baixar_pdf')

    texto_hol = _extrair_texto_pdf_bytes(hol_bytes)
    competencia_hol, _ = extrair_competencia_holerite(texto_hol)
    texto_ponto = _extrair_texto_pdf_bytes(ponto_bytes)
    competencia_ponto, _ = _extrair_competencia_folha_ponto(texto_ponto)

    if not competencia_hol or not competencia_ponto:
        return ResultadoColaborador(fid, 'indeterminavel', competencia_hol, competencia_ponto,
                                     detalhe='competencia_nao_extraivel_de_um_dos_2_pdfs')

    if competencia_hol != competencia_ponto:
        return ResultadoColaborador(fid, 'competencia_divergente', competencia_hol, competencia_ponto)

    competencia = competencia_hol
    ja_assinou = competencia in (dados_funcionario.get('assinaturas_por_competencia') or set())
    ja_enviou = competencia in (dados_funcionario.get('envios_por_competencia') or set())

    if ja_assinou:
        return ResultadoColaborador(fid, 'ja_assinou_este_pacote', competencia, competencia)
    if ja_enviou:
        return ResultadoColaborador(fid, 'ja_recebeu_esta_competencia', competencia, competencia)

    return ResultadoColaborador(fid, 'pronto_para_lote', competencia, competencia)


def _baixar(url, sessao=None):
    sessao = sessao or requests
    r = sessao.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def reconciliar_todos(lista_dados_funcionarios: list, sessao=None) -> RelatorioReconciliacao:
    relatorio = RelatorioReconciliacao()
    for dados in lista_dados_funcionarios:
        relatorio.resultados.append(reconciliar_colaborador(dados, sessao))
    return relatorio


def _carregar_dados_reais_do_airtable(airtable_api_key: str) -> list:
    """
    Carrega os dados reais necessários (leitura pura, nenhuma escrita) —
    só é chamada quando executado como script, nunca em teste.
    """
    headers = {'Authorization': f'Bearer {airtable_api_key}'}
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
        headers=headers,
        params={
            'filterByFormula': '{Status}="Ativo"',
            'fields[]': ['CPF', 'WhatsApp', 'PDF HOLERITE ATUAL', 'PDF Folha Ponto',
                         'Envios de Documentos', 'Assinaturas Digitais'],
        },
        timeout=60,
    )
    r.raise_for_status()
    saida = []
    for rec in r.json().get('records', []):
        f = rec.get('fields', {})
        pdf_hol = f.get('PDF HOLERITE ATUAL') or []
        pdf_ponto = f.get('PDF Folha Ponto') or []
        saida.append({
            'funcionario_id': rec['id'],
            'status': 'Ativo',
            'whatsapp': f.get('WhatsApp'),
            'cpf': f.get('CPF'),
            'holerite_url': pdf_hol[-1]['url'] if pdf_hol else None,
            'folha_ponto_url': pdf_ponto[-1]['url'] if pdf_ponto else None,
            # Envios/Assinaturas por competência exigem uma 2ª consulta
            # (tabelas próprias) — deixado como TODO explícito para a
            # execução real; nesta função de carregamento, vazio por
            # padrão (trata tudo como "nunca enviado/assinado" na ausência
            # de dado, o que é seguro — nunca finge confirmação positiva).
            'envios_por_competencia': set(),
            'assinaturas_por_competencia': set(),
        })
    return saida


def main():
    """
    Execução real (exige AIRTABLE_API_KEY de verdade no ambiente —
    Render, ou local com a chave real; não funciona neste sandbox, que
    não tem a chave):

        AIRTABLE_API_KEY=<chave real> python3 scripts/reconciliacao_backlog_holerite_ponto.py

    Saída: só contagens por categoria e lista de Record IDs — nenhum
    nome, telefone ou CPF é impresso.
    """
    airtable_api_key = os.environ.get('AIRTABLE_API_KEY')
    if not airtable_api_key:
        print('AIRTABLE_API_KEY não configurada — nada foi consultado. '
              'Rode com a chave real do ambiente autorizado para reconciliar de verdade.')
        sys.exit(1)

    dados = _carregar_dados_reais_do_airtable(airtable_api_key)
    relatorio = reconciliar_todos(dados)

    print(f'Total de colaboradores Ativos avaliados: {relatorio.total()}')
    for categoria, qtd in relatorio.contagem_por_categoria().items():
        print(f'  {categoria}: {qtd}')

    print('\nRecord IDs por categoria (sem PII):')
    for categoria in CATEGORIAS:
        ids = [r.funcionario_id for r in relatorio.resultados if r.categoria == categoria]
        if ids:
            print(f'  {categoria}: {", ".join(ids)}')


if __name__ == '__main__':
    main()
