"""Gatilho: Kit de Admissão classificado -> intenção de cadastro no
PontoWeb até o ponto de Preview/pendência.

Contexto (ver `docs/decisoes/escopo-rh-admissao-demissao-pontoweb-v1.md`
e `docs/decisoes/local-trabalho-determinacao-humana-admissao-v1.md`):
hoje a classificação de "Kit de Admissão" e a extração de dados
cadastrais já existem no legado (`app.py`, `src/sync_new_employees.py`),
mas nada encadeia o Kit classificado até uma intenção de cadastro na
Secullum. Este módulo fecha só esse elo -- nunca reimplementa
extração, nunca chama a API real (isso é papel de `porta_secullum.py`,
sempre em modo sombra aqui).

Regra de negócio (decisão do operador, registrada em
`docs/decisoes/local-trabalho-determinacao-humana-admissao-v1.md`):
o local de trabalho (`grupo_escala_id`) nunca é lido/inferido
automaticamente. Uma pessoa determina explicitamente o local de
trabalho a cada evento de admissão. Sem essa determinação, o gatilho
NUNCA adivinha -- produz uma pendência explícita e auditável.

Domínio puro: nenhum import de Flask, Airtable, driver de banco ou
biblioteca de rede. Quem chama este módulo é responsável por já ter
extraído `DadosColaboradorKitAdmissao` do Kit (reaproveitando o que já
existe no legado) e por fornecer (ou não) a `DeterminacaoLocalTrabalho`.
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from magnata_os.rh_admissao.porta_secullum import (
    IntencaoCadastroSecullum,
    PortaSecullum,
    ResultadoAcaoSecullum,
    compor_porta_secullum,
)

_logger = logging.getLogger(__name__)

EVENTO_GATILHO_ADMISSAO_PENDENTE = 'gatilho_admissao_pendente_local_trabalho'
EVENTO_GATILHO_ADMISSAO_COMPOSTO = 'gatilho_admissao_intencao_composta'
EVENTO_GATILHO_ADMISSAO_FALHOU = 'gatilho_admissao_falhou'
EVENTO_GATILHO_ADMISSAO_IDEMPOTENTE = 'gatilho_admissao_idempotente_reaproveitado'

MOTIVO_LOCAL_TRABALHO_NAO_DETERMINADO = 'local_trabalho_nao_determinado'


@dataclass(frozen=True)
class DadosColaboradorKitAdmissao:
    """O que já dá para extrair de um Kit de Admissão processado, hoje.

    `colaborador_id` é o identificador interno do Funcionário (ex.: o
    record id do Airtable já usado por `_vincular_documento_ao_funcionario`
    em `src/sync_new_employees.py`) -- o Kit de Admissão em produção já
    chega vinculado a um Funcionário existente, não a texto solto que
    precise de regex próprio (isso é o caso do holerite, não do Kit).
    """

    colaborador_id: str
    cpf: str
    nome: str
    cargo: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.colaborador_id.strip():
            raise ValueError('colaborador_id é obrigatório')
        if not self.cpf.strip():
            raise ValueError('cpf é obrigatório (exigido pela API Secullum)')
        if not self.nome.strip():
            raise ValueError('nome é obrigatório (exigido pela API Secullum)')


@dataclass(frozen=True)
class DeterminacaoLocalTrabalho:
    """A decisão humana pontual sobre onde o colaborador vai trabalhar.

    Nunca é lida de um campo já preenchido em outro sistema -- é
    fornecida explicitamente, por evento de admissão, por quem decidiu
    (ver decisão de negócio no cabeçalho deste módulo). `determinado_por`
    é um identificador de operador (usuário, e-mail interno, etc.),
    nunca dado do colaborador.
    """

    grupo_escala_id: str
    determinado_por: str
    determinado_em: datetime

    def __post_init__(self) -> None:
        if not self.grupo_escala_id.strip():
            raise ValueError('grupo_escala_id é obrigatório quando a determinação existe')
        if not self.determinado_por.strip():
            raise ValueError('determinado_por é obrigatório -- decisão humana precisa de autoria')


class SituacaoGatilhoAdmissao(str, enum.Enum):
    INTENCAO_COMPOSTA = 'INTENCAO_COMPOSTA'
    """Local de trabalho determinado; intenção de cadastro composta e
    enviada à porta Secullum (sempre em modo sombra nesta missão)."""
    AGUARDANDO_LOCAL_TRABALHO = 'AGUARDANDO_LOCAL_TRABALHO'
    """Sem determinação humana do local de trabalho -- pendência
    explícita. Nunca adivinha, nunca bloqueia os demais kits do lote."""
    FALHOU = 'FALHOU'
    """Falha isolada ao processar este kit (dado inválido, porta
    lançou). Nunca derruba o processamento de outros kits do lote."""


@dataclass(frozen=True)
class ResultadoGatilhoAdmissao:
    """Resultado de processar um Kit de Admissão pelo gatilho.

    `situacao`, `motivo_bloqueio` e `proxima_acao` ficam separados
    (nunca fundidos num campo só -- CLAUDE.md §4). `etapa_atual` não
    existe aqui porque este gatilho é um único ponto de decisão, não
    uma esteira multi-estágio."""

    colaborador_id: str
    situacao: SituacaoGatilhoAdmissao
    motivo_bloqueio: Optional[str] = None
    proxima_acao: Optional[str] = None
    resultado_secullum: Optional[ResultadoAcaoSecullum] = None
    erro_tipo: Optional[str] = None
    reaproveitado: bool = False
    """True quando este resultado veio do registro idempotente em vez
    de ser recomputado (mesmo kit reprocessado)."""

    def como_evidencia(self) -> Dict[str, object]:
        """Só ids, enums e o resultado Secullum (que já não vaza
        CPF/nome) -- nunca `nome`/`cpf` do colaborador."""
        return {
            'colaborador_id': self.colaborador_id,
            'situacao': self.situacao.value,
            'motivo_bloqueio': self.motivo_bloqueio,
            'proxima_acao': self.proxima_acao,
            'resultado_secullum': self.resultado_secullum.como_evidencia() if self.resultado_secullum else None,
            'erro_tipo': self.erro_tipo,
            'reaproveitado': self.reaproveitado,
        }


class RegistroGatilhoAdmissaoEmMemoria:
    """Guarda de idempotência mínima, em memória, injetável.

    Chave = `colaborador_id`: neste v1, um Kit de Admissão corresponde
    a um evento de admissão por colaborador (mesma suposição usada no
    legado, que vincula o Kit a um único Funcionário já existente).
    Reprocessar o mesmo `colaborador_id` devolve o resultado já
    registrado em vez de recompor a intenção ou chamar a porta de novo.

    Isto é auxiliar de processo (não é o "histórico append-only" oficial
    de um módulo com persistência real) -- um wiring com armazenamento
    durável trocaria esta classe por um adapter equivalente, sem mudar
    `processar_kit_admissao`.
    """

    def __init__(self) -> None:
        self._resultados: Dict[str, ResultadoGatilhoAdmissao] = {}

    def obter(self, colaborador_id: str) -> Optional[ResultadoGatilhoAdmissao]:
        return self._resultados.get(colaborador_id)

    def registrar(self, resultado: ResultadoGatilhoAdmissao) -> None:
        self._resultados[resultado.colaborador_id] = resultado


def processar_kit_admissao(
    dados: DadosColaboradorKitAdmissao,
    determinacao: Optional[DeterminacaoLocalTrabalho],
    *,
    porta: Optional[PortaSecullum] = None,
    registro: Optional[RegistroGatilhoAdmissaoEmMemoria] = None,
) -> ResultadoGatilhoAdmissao:
    """Processa um único Kit de Admissão já extraído.

    Sempre em modo sombra: `porta`, quando não injetada, vem de
    `compor_porta_secullum()` com o default literal
    (`autorizar_secullum_real=False`) -- este gatilho nunca passa
    `True` para isso. Nunca lança para o chamador: falha vira
    `SituacaoGatilhoAdmissao.FALHOU` no resultado.
    """
    if registro is not None:
        existente = registro.obter(dados.colaborador_id)
        if existente is not None:
            _logger.info(
                '%s colaborador_id=%s', EVENTO_GATILHO_ADMISSAO_IDEMPOTENTE, dados.colaborador_id,
                extra={'evento': EVENTO_GATILHO_ADMISSAO_IDEMPOTENTE, 'colaborador_id': dados.colaborador_id},
            )
            return dataclass_replace_reaproveitado(existente)

    try:
        if determinacao is None:
            resultado = ResultadoGatilhoAdmissao(
                colaborador_id=dados.colaborador_id,
                situacao=SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO,
                motivo_bloqueio=MOTIVO_LOCAL_TRABALHO_NAO_DETERMINADO,
                proxima_acao='aguardar determinação humana do local de trabalho para este evento de admissão',
            )
            _logger.info(
                '%s colaborador_id=%s', EVENTO_GATILHO_ADMISSAO_PENDENTE, dados.colaborador_id,
                extra={'evento': EVENTO_GATILHO_ADMISSAO_PENDENTE, 'colaborador_id': dados.colaborador_id},
            )
        else:
            intencao = IntencaoCadastroSecullum(
                colaborador_id=dados.colaborador_id,
                cpf=dados.cpf,
                nome=dados.nome,
                cargo=dados.cargo,
                grupo_escala_id=determinacao.grupo_escala_id,
            )
            porta_efetiva = porta if porta is not None else compor_porta_secullum(autorizar_secullum_real=False)
            resultado_secullum = porta_efetiva.cadastrar(intencao)
            resultado = ResultadoGatilhoAdmissao(
                colaborador_id=dados.colaborador_id,
                situacao=SituacaoGatilhoAdmissao.INTENCAO_COMPOSTA,
                proxima_acao='revisar Preview em modo sombra; nenhuma chamada real foi feita',
                resultado_secullum=resultado_secullum,
            )
            _logger.info(
                '%s colaborador_id=%s', EVENTO_GATILHO_ADMISSAO_COMPOSTO, dados.colaborador_id,
                extra={'evento': EVENTO_GATILHO_ADMISSAO_COMPOSTO, 'colaborador_id': dados.colaborador_id},
            )
    except Exception as exc:  # falha isolada -- nunca derruba o lote, nunca fica silenciosa
        resultado = ResultadoGatilhoAdmissao(
            colaborador_id=dados.colaborador_id,
            situacao=SituacaoGatilhoAdmissao.FALHOU,
            motivo_bloqueio='erro_ao_processar_kit',
            proxima_acao='revisar log (evento gatilho_admissao_falhou) e reprocessar manualmente',
            erro_tipo=type(exc).__name__,
        )
        _logger.error(
            '%s colaborador_id=%s exception_type=%s', EVENTO_GATILHO_ADMISSAO_FALHOU,
            dados.colaborador_id, type(exc).__name__,
            extra={'evento': EVENTO_GATILHO_ADMISSAO_FALHOU, 'colaborador_id': dados.colaborador_id,
                   'exception_type': type(exc).__name__},
        )

    if registro is not None:
        registro.registrar(resultado)
    return resultado


def dataclass_replace_reaproveitado(resultado: ResultadoGatilhoAdmissao) -> ResultadoGatilhoAdmissao:
    """Devolve uma cópia de `resultado` com `reaproveitado=True`, sem
    alterar o registro original (histórico do que foi de fato computado
    na primeira vez continua intacto)."""
    return ResultadoGatilhoAdmissao(
        colaborador_id=resultado.colaborador_id,
        situacao=resultado.situacao,
        motivo_bloqueio=resultado.motivo_bloqueio,
        proxima_acao=resultado.proxima_acao,
        resultado_secullum=resultado.resultado_secullum,
        erro_tipo=resultado.erro_tipo,
        reaproveitado=True,
    )


def processar_lote_kits_admissao(
    itens: List[Tuple[DadosColaboradorKitAdmissao, Optional[DeterminacaoLocalTrabalho]]],
    *,
    porta: Optional[PortaSecullum] = None,
    registro: Optional[RegistroGatilhoAdmissaoEmMemoria] = None,
) -> List[ResultadoGatilhoAdmissao]:
    """Processa vários kits isoladamente: a falha de um nunca impede o
    processamento dos demais (mesmo `registro`/`porta` compartilhados
    entre eles, mas cada item passa por sua própria captura de erro em
    `processar_kit_admissao`)."""
    resultados: List[ResultadoGatilhoAdmissao] = []
    for dados, determinacao in itens:
        resultados.append(
            processar_kit_admissao(dados, determinacao, porta=porta, registro=registro)
        )
    return resultados
