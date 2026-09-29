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
  - necessidade sem colaborador (Extrato, FGTS, guias) é correlacionada
    pelo CNPJ do cliente (CNPJ exato via `fonte_cliente_direto`, a mesma
    porta do corredor); sem essa porta, não é atendida.
Registrado em `docs/magnata-os/MAGNATA_OS_CENTRAL_FUNDACAO.md`.

Falha de leitura de um arquivo não é silenciosa: se QUALQUER arquivo
não pôde ser lido, a fonte levanta `BuscaPorConteudoIncompleta` e a
localização registra INDETERMINADO ("não consegui olhar tudo") -- nem
"não existe", nem uma escolha feita por cima da lacuna (o arquivo
ilegível poderia ser uma versão corrigida). A falha de leitura não é
guardada em cache: a próxima necessidade tenta ler de novo. PDF sem texto
extraível (imagem sem OCR) não é falha de leitura: é contado em
`resumo_ultima_consulta()` como não pesquisável.

Documentos DERIVADOS (`origem == 'derivado_separacao'`) não são
devolvidos: a fonte devolve o PDF original, e a aquisição o troca pela
parte do colaborador. Assim um derivado antigo (de um agrupamento
anterior) nunca concorre com o atual.

Custo: varre `listar_todos()` a cada necessidade (texto cacheado por
hash). Aceitável para o volume atual; o índice persistente (J3) é o
caminho para escala e está registrado como próxima etapa.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

from magnata_os.documental.derivacao_documental import ORIGEM_DERIVADO_SEPARACAO
from magnata_os.documental.modulo01.dominio import Documento

from .ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.documental.ocr import extrair_paginas_com_ocr
from .separacao_documental import cpfs_da_pagina, indice_cpf_de_candidatos


class BuscaPorConteudoIncompleta(Exception):
    """Nenhum candidato encontrado e pelo menos um arquivo não pôde ser
    lido -- não é possível afirmar ausência."""


_ILEGIVEL = object()


class FonteCandidatosPorConteudo:
    """Colaborador: CPF do colaborador em alguma página. Cliente (necessidade
    sem colaborador -- Extrato, FGTS, guias): alguma página cujo CNPJ
    resolve EXATAMENTE para o cliente da necessidade via
    `fonte_cliente_direto` (mesma porta que o corredor usa para documentos
    de granularidade cliente). Sem `fonte_cliente_direto`, necessidades de
    cliente não são atendidas por esta fonte."""

    def __init__(
        self,
        repositorio_documentos: object,
        armazenamento_arquivos: object,
        candidatos_colaborador: Sequence[object],
        fonte_cliente_direto: Optional[object] = None,
        motor_ocr: Optional[object] = None,
    ) -> None:
        self._motor_ocr = motor_ocr
        self._repositorio = repositorio_documentos
        self._armazenamento = armazenamento_arquivos
        self._fonte_cliente_direto = fonte_cliente_direto
        self._cpfs_por_colaborador: Dict[str, frozenset] = {}
        self._indice = indice_cpf_de_candidatos(candidatos_colaborador)
        for cpf, (colaborador_id, _) in self._indice.items():
            self._cpfs_por_colaborador[colaborador_id] = (
                self._cpfs_por_colaborador.get(colaborador_id, frozenset()) | {cpf}
            )
        self._paginas_por_hash: Dict[str, object] = {}
        self._cpfs_por_hash: Dict[str, frozenset] = {}
        self._clientes_por_hash: Dict[str, frozenset] = {}
        self._resumo: Mapping[str, int] = {}

    def candidatos_para(
        self, necessidade: NecessidadeDocumentoPrestacao, criados_apos: Optional[object] = None,
    ) -> Tuple[Documento, ...]:
        """`criados_apos` (datetime): só examina documentos registrados
        depois desse instante -- usado pelo índice com frescor para olhar
        apenas o que chegou depois do que já está indexado."""
        self._resumo = {}
        if necessidade.colaborador is not None:
            cpfs_alvo = self._cpfs_por_colaborador.get(necessidade.colaborador.entidade_id)
            if not cpfs_alvo:
                return ()
            corresponde = lambda documento, paginas: bool(cpfs_alvo & self._cpfs(documento, paginas))  # noqa: E731
        elif self._fonte_cliente_direto is not None:
            corresponde = lambda documento, paginas: necessidade.cliente in self._clientes(documento, paginas)  # noqa: E731
        else:
            return ()

        encontrados = []
        analisados = sem_texto = ilegiveis = 0
        for documento in self._repositorio.listar_todos():
            if documento.mime_type != 'application/pdf' or documento.origem == ORIGEM_DERIVADO_SEPARACAO:
                continue
            if criados_apos is not None and documento.criado_em < criados_apos:
                continue
            analisados += 1
            paginas = self._paginas(documento)
            if paginas is _ILEGIVEL:
                ilegiveis += 1
                continue
            if paginas is None:
                sem_texto += 1
                continue
            if corresponde(documento, paginas):
                encontrados.append(documento)

        self._resumo = {
            'documentos_analisados': analisados,
            'documentos_sem_texto': sem_texto,
            'documentos_ilegiveis': ilegiveis,
            'documentos_encontrados': len(encontrados),
        }
        if ilegiveis:
            raise BuscaPorConteudoIncompleta(f'{ilegiveis} arquivo(s) não puderam ser lidos')
        return tuple(sorted(encontrados, key=lambda d: d.documento_id))

    def resumo_ultima_consulta(self) -> Mapping[str, int]:
        """Contagens da última consulta, para o rastro da localização."""
        return dict(self._resumo)

    def _cpfs(self, documento: Documento, paginas: Tuple[str, ...]) -> frozenset:
        if documento.hash_sha256 not in self._cpfs_por_hash:
            self._cpfs_por_hash[documento.hash_sha256] = frozenset(
                cpf for pagina in paginas for cpf in cpfs_da_pagina(pagina, self._indice)
            )
        return self._cpfs_por_hash[documento.hash_sha256]

    def _clientes(self, documento: Documento, paginas: Tuple[str, ...]) -> frozenset:
        """Clientes comprovados por CNPJ exato em alguma página. Falha da
        porta de cliente propaga (a localização registra a fonte como
        FALHOU -> INDETERMINADO), nunca vira "nenhum cliente"."""
        if documento.hash_sha256 not in self._clientes_por_hash:
            clientes = set()
            for pagina in paginas:
                cliente = self._fonte_cliente_direto.resolver_cliente_direto(pagina)
                if cliente is not None:
                    clientes.add(cliente)
            self._clientes_por_hash[documento.hash_sha256] = frozenset(clientes)
        return self._clientes_por_hash[documento.hash_sha256]

    def _paginas(self, documento: Documento) -> object:
        """Texto por página, None se sem texto, `_ILEGIVEL` se a leitura
        falhou (não cacheado: a próxima consulta tenta de novo)."""
        if documento.hash_sha256 in self._paginas_por_hash:
            return self._paginas_por_hash[documento.hash_sha256]
        try:
            with self._armazenamento.abrir_leitura(documento.hash_sha256) as arquivo:
                conteudo = arquivo.read()
        except Exception:
            return _ILEGIVEL
        extracao = extrair_paginas_com_ocr(conteudo, self._motor_ocr)
        if extracao is not None and extracao.ocr_falhou and extracao.paginas_sem_texto:
            # o motor de OCR falhou e sobrou página sem texto: o documento
            # NÃO foi examinado -- ilegível (busca incompleta), nunca "sem
            # texto", e não fica em cache (a próxima consulta tenta de novo)
            return _ILEGIVEL
        paginas: Optional[Tuple[str, ...]] = (
            extracao.paginas if extracao is not None and extracao.tem_texto else None
        )
        self._paginas_por_hash[documento.hash_sha256] = paginas
        return paginas
