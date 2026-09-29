"""Fonte de candidatos POR CONTEÚDO: encontra o documento de um
colaborador lendo o texto dos PDFs armazenados, sem depender de índice,
cadastro prévio ou nome de arquivo.

Motivo: o documento existia (dentro de um PDF de 12 páginas), mas a
automação não o achava -- o inventário só conhece o que já foi resolvido,
e um PDF composto nunca é resolvido inteiro. Esta fonte fecha essa lacuna
e deve vir DEPOIS das fontes indexadas em `fontes_localizacao` (a
localização só a consulta quando as anteriores não acham nada).

Critério de correlação: o CPF do colaborador da necessidade aparece em
alguma página. O CPF vem do índice montado dos `CandidatoFuncionario` já
presentes no contexto e é só chave transitória em memória -- nunca sai
daqui (o resultado são `Documento`, a evidência são contagens).

DECISÃO REGISTRADA (conflito com a regra anterior de
`fonte_candidatos_por_necessidade.py`, "nunca a partir da resolução
semântica do próprio documento"): esta fonte usa o CONTEÚDO do documento
para correlacioná-lo à necessidade, por pedido explícito do operador
(missão "Prestação -> esteira documental operacional", §11: "o motor
deve ser capaz de encontrar um documento cujo filename seja
completamente inútil"). Limites que preservam a intenção da regra:
  - a correlação usa só a IDENTIDADE (CPF -> colaborador), nunca a
    resolução semântica do corredor;
  - cliente, competência e tipo continuam validados de forma
    independente pelo corredor e pela elegibilidade -- um documento do
    colaborador certo com mês/cliente/tipo errado é descartado lá;
  - necessidade sem colaborador (tipos de granularidade cliente) não é
    atendida por esta fonte nesta etapa.
Registrado em `docs/magnata-os/MAGNATA_OS_CENTRAL_FUNDACAO.md`.

Falha de leitura de um arquivo não é silenciosa: se nenhum documento
bate e algum arquivo não pôde ser lido, a fonte levanta
`BuscaPorConteudoIncompleta` e a localização registra INDETERMINADO
("não consegui olhar tudo"), nunca "não existe". PDF sem texto
extraível (imagem sem OCR) não é falha de leitura: é contado em
`resumo_ultima_consulta()` como não pesquisável.

Custo: varre `listar_todos()` a cada necessidade (texto cacheado por
hash). Aceitável para o volume atual; o índice persistente (J3) é o
caminho para escala e está registrado como próxima etapa.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

from magnata_os.documental.importacao_lote.dominio import extrair_cpfs_distintos_de_texto
from magnata_os.documental.modulo01.dominio import Documento

from .ciclo_prestacao import NecessidadeDocumentoPrestacao
from .roteamento_documental import extrair_paginas_seguro
from .separacao_documental import indice_cpf_de_candidatos


class BuscaPorConteudoIncompleta(Exception):
    """Nenhum candidato encontrado e pelo menos um arquivo não pôde ser
    lido -- não é possível afirmar ausência."""


_ILEGIVEL = object()


class FonteCandidatosPorConteudo:
    def __init__(
        self,
        repositorio_documentos: object,
        armazenamento_arquivos: object,
        candidatos_colaborador: Sequence[object],
    ) -> None:
        self._repositorio = repositorio_documentos
        self._armazenamento = armazenamento_arquivos
        self._cpfs_por_colaborador: Dict[str, frozenset] = {}
        for cpf, (colaborador_id, _) in indice_cpf_de_candidatos(candidatos_colaborador).items():
            self._cpfs_por_colaborador[colaborador_id] = (
                self._cpfs_por_colaborador.get(colaborador_id, frozenset()) | {cpf}
            )
        self._paginas_por_hash: Dict[str, object] = {}
        self._resumo: Mapping[str, int] = {}

    def candidatos_para(self, necessidade: NecessidadeDocumentoPrestacao) -> Tuple[Documento, ...]:
        self._resumo = {}
        if necessidade.colaborador is None:
            return ()
        cpfs_alvo = self._cpfs_por_colaborador.get(necessidade.colaborador.entidade_id)
        if not cpfs_alvo:
            return ()

        encontrados = []
        analisados = sem_texto = ilegiveis = 0
        for documento in self._repositorio.listar_todos():
            if documento.mime_type != 'application/pdf':
                continue
            analisados += 1
            paginas = self._paginas(documento)
            if paginas is _ILEGIVEL:
                ilegiveis += 1
                continue
            if paginas is None:
                sem_texto += 1
                continue
            if any(cpfs_alvo.intersection(extrair_cpfs_distintos_de_texto(p)) for p in paginas):
                encontrados.append(documento)

        self._resumo = {
            'documentos_analisados': analisados,
            'documentos_sem_texto': sem_texto,
            'documentos_ilegiveis': ilegiveis,
            'documentos_encontrados': len(encontrados),
        }
        if not encontrados and ilegiveis:
            raise BuscaPorConteudoIncompleta(f'{ilegiveis} arquivo(s) não puderam ser lidos')
        return tuple(sorted(encontrados, key=lambda d: d.documento_id))

    def resumo_ultima_consulta(self) -> Mapping[str, int]:
        """Contagens da última consulta, para o rastro da localização."""
        return dict(self._resumo)

    def _paginas(self, documento: Documento) -> object:
        if documento.hash_sha256 not in self._paginas_por_hash:
            self._paginas_por_hash[documento.hash_sha256] = self._ler(documento)
        return self._paginas_por_hash[documento.hash_sha256]

    def _ler(self, documento: Documento) -> object:
        try:
            with self._armazenamento.abrir_leitura(documento.hash_sha256) as arquivo:
                conteudo = arquivo.read()
        except Exception:
            return _ILEGIVEL
        paginas: Optional[Tuple[str, ...]] = extrair_paginas_seguro(conteudo)
        return paginas
