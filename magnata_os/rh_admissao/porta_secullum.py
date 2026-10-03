"""Contrato de acesso ao PontoWeb (Secullum) -- porta substituível.

O domínio (quem decide "este colaborador precisa ser cadastrado/desligado")
nunca fala com a API da Secullum diretamente. Ele fala com esta porta, que
tem duas implementações:

- `ExecutorSecullumSombra` (padrão, sempre segura): registra a intenção,
  nunca chama a rede. É o que roda enquanto não houver autorização de
  fase para escrita real (CLAUDE.md §6).
- `ExecutorSecullumReal`: adapter fino sobre `src/services/secullum_ponto.py`
  (nunca reimplementado -- só chamado). Só é composto quando
  `transporte_secullum_real_habilitado()` (mesmo padrão de três barreiras
  de `orquestrador/autorizacao_transporte_real.py`) devolve True.

CPF/nome do colaborador são estritamente necessários para a API real (ela
exige CPF), mas nunca aparecem em log nem em `ResultadoAcaoSecullum`: só
o `colaborador_id` interno e o `secullum_id` devolvido pela API.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol

from magnata_os.orquestrador.configuracao import deve_rodar_em_dry_run

_logger = logging.getLogger(__name__)

EVENTO_ACAO_SECULLUM_SOMBRA = 'acao_secullum_sombra'
EVENTO_ACAO_SECULLUM_REAL = 'acao_secullum_real'
EVENTO_ACAO_SECULLUM_FALHOU = 'acao_secullum_falhou'

NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL = 'MAGNATA_RH_SECULLUM_REAL_AUTORIZADO'
_VALOR_AUTORIZADO_EXATO = '1'


@dataclass(frozen=True)
class IntencaoCadastroSecullum:
    """Intenção idempotente: cadastrar `colaborador_id` no PontoWeb, no
    local de trabalho `grupo_escala_id`. `cpf` é estritamente transitório
    -- só existe para a chamada real, nunca fica no resultado."""

    colaborador_id: str
    cpf: str
    nome: str
    cargo: Optional[str] = None
    grupo_escala_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.colaborador_id.strip():
            raise ValueError('colaborador_id é obrigatório')
        if not self.cpf.strip():
            raise ValueError('cpf é obrigatório (exigido pela API Secullum)')


@dataclass(frozen=True)
class IntencaoDesligamentoSecullum:
    colaborador_id: str
    cpf: str
    data_demissao: date

    def __post_init__(self) -> None:
        if not self.colaborador_id.strip():
            raise ValueError('colaborador_id é obrigatório')
        if not self.cpf.strip():
            raise ValueError('cpf é obrigatório (exigido pela API Secullum)')


@dataclass(frozen=True)
class ResultadoAcaoSecullum:
    colaborador_id: str
    acao: str  # 'CADASTRO' | 'DESLIGAMENTO'
    executado: bool  # False em modo sombra
    secullum_id: Optional[str] = None
    erro_tipo: Optional[str] = None

    def como_evidencia(self) -> dict:
        """Só ids e o tipo do erro -- nunca CPF, nome ou mensagem crua."""
        return {
            'colaborador_id': self.colaborador_id, 'acao': self.acao,
            'executado': self.executado, 'secullum_id': self.secullum_id,
            'erro_tipo': self.erro_tipo,
        }


class PortaSecullum(Protocol):
    def cadastrar(self, intencao: IntencaoCadastroSecullum) -> ResultadoAcaoSecullum: ...

    def desligar(self, intencao: IntencaoDesligamentoSecullum) -> ResultadoAcaoSecullum: ...


class ExecutorSecullumSombra:
    """Padrão. Nunca chama rede -- só registra a intenção que TERIA sido
    executada. `executado=False` sempre."""

    def cadastrar(self, intencao: IntencaoCadastroSecullum) -> ResultadoAcaoSecullum:
        _logger.info(
            '%s colaborador_id=%s acao=CADASTRO', EVENTO_ACAO_SECULLUM_SOMBRA, intencao.colaborador_id,
            extra={'evento': EVENTO_ACAO_SECULLUM_SOMBRA, 'colaborador_id': intencao.colaborador_id, 'acao': 'CADASTRO'},
        )
        return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=False)

    def desligar(self, intencao: IntencaoDesligamentoSecullum) -> ResultadoAcaoSecullum:
        _logger.info(
            '%s colaborador_id=%s acao=DESLIGAMENTO', EVENTO_ACAO_SECULLUM_SOMBRA, intencao.colaborador_id,
            extra={'evento': EVENTO_ACAO_SECULLUM_SOMBRA, 'colaborador_id': intencao.colaborador_id, 'acao': 'DESLIGAMENTO'},
        )
        return ResultadoAcaoSecullum(intencao.colaborador_id, 'DESLIGAMENTO', executado=False)


class ExecutorSecullumReal:
    """Adapter fino sobre `src/services/secullum_ponto.py` -- nunca
    reimplementa autenticação, payload ou retry: só traduz a intenção
    para a chamada existente e o retorno dela para `ResultadoAcaoSecullum`,
    sem deixar CPF/nome vazarem para fora desta função."""

    def __init__(self, servico=None) -> None:
        if servico is None:
            from src.services import secullum_ponto as servico  # import tardio: só quando REAL é composto
        self._servico = servico

    def cadastrar(self, intencao: IntencaoCadastroSecullum) -> ResultadoAcaoSecullum:
        try:
            resultado = self._servico.sincronizar_funcionario(
                cpf=intencao.cpf, nome=intencao.nome, numero=intencao.grupo_escala_id,
            )
        except Exception as exc:
            _logger.error(
                '%s colaborador_id=%s acao=CADASTRO exception_type=%s',
                EVENTO_ACAO_SECULLUM_FALHOU, intencao.colaborador_id, type(exc).__name__,
                extra={'evento': EVENTO_ACAO_SECULLUM_FALHOU, 'colaborador_id': intencao.colaborador_id,
                       'acao': 'CADASTRO', 'exception_type': type(exc).__name__},
            )
            return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=False, erro_tipo=type(exc).__name__)
        secullum_id = str(resultado.get('id') or resultado.get('Id') or '') or None
        _logger.info(
            '%s colaborador_id=%s acao=CADASTRO', EVENTO_ACAO_SECULLUM_REAL, intencao.colaborador_id,
            extra={'evento': EVENTO_ACAO_SECULLUM_REAL, 'colaborador_id': intencao.colaborador_id, 'acao': 'CADASTRO'},
        )
        return ResultadoAcaoSecullum(intencao.colaborador_id, 'CADASTRO', executado=True, secullum_id=secullum_id)

    def desligar(self, intencao: IntencaoDesligamentoSecullum) -> ResultadoAcaoSecullum:
        try:
            func = self._servico.buscar_funcionario_secullum_por_cpf(intencao.cpf)
            if func is None:
                return ResultadoAcaoSecullum(
                    intencao.colaborador_id, 'DESLIGAMENTO', executado=False, erro_tipo='FuncionarioNaoEncontrado',
                )
            self._servico._secullum_request(  # mesma primitiva usada por rota_excluir; nunca duplicada aqui
                'PUT', f"Funcionarios/{func['Id']}",
                json={**{k: v for k, v in func.items() if k not in (
                    'Empresa', 'Departamento', 'Funcao', 'Horario', 'ListaCentroDeCustos',
                    'RespostasPerguntasAdicionais', 'CidadeId', 'Cidade',
                )}, 'Demissao': intencao.data_demissao.isoformat(), 'EmpresaId': func.get('EmpresaId') or 1},
            )
        except Exception as exc:
            _logger.error(
                '%s colaborador_id=%s acao=DESLIGAMENTO exception_type=%s',
                EVENTO_ACAO_SECULLUM_FALHOU, intencao.colaborador_id, type(exc).__name__,
                extra={'evento': EVENTO_ACAO_SECULLUM_FALHOU, 'colaborador_id': intencao.colaborador_id,
                       'acao': 'DESLIGAMENTO', 'exception_type': type(exc).__name__},
            )
            return ResultadoAcaoSecullum(intencao.colaborador_id, 'DESLIGAMENTO', executado=False, erro_tipo=type(exc).__name__)
        _logger.info(
            '%s colaborador_id=%s acao=DESLIGAMENTO', EVENTO_ACAO_SECULLUM_REAL, intencao.colaborador_id,
            extra={'evento': EVENTO_ACAO_SECULLUM_REAL, 'colaborador_id': intencao.colaborador_id, 'acao': 'DESLIGAMENTO'},
        )
        return ResultadoAcaoSecullum(intencao.colaborador_id, 'DESLIGAMENTO', executado=True, secullum_id=str(func['Id']))


def _autorizacao_operacional_explicita() -> bool:
    return os.environ.get(NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL) == _VALOR_AUTORIZADO_EXATO


def transporte_secullum_real_habilitado(*, autorizar_secullum_real: bool) -> bool:
    """Mesmo padrão de três barreiras de
    `orquestrador/autorizacao_transporte_real.py` (transporte WhatsApp),
    com variável própria -- autorizar um nunca autoriza o outro.

    REAL = autorizar_secullum_real is True
           AND MAGNATA_RH_SECULLUM_REAL_AUTORIZADO == "1" (exato)
           AND NOT deve_rodar_em_dry_run()
    """
    if autorizar_secullum_real is not True:
        return False
    if not _autorizacao_operacional_explicita():
        return False
    if deve_rodar_em_dry_run():
        return False
    return True


def compor_porta_secullum(*, autorizar_secullum_real: bool = False, servico=None) -> PortaSecullum:
    """Único ponto de decisão fake-vs-real. `autorizar_secullum_real` é
    `False` por padrão literal -- nunca lido de variável de ambiente aqui."""
    if transporte_secullum_real_habilitado(autorizar_secullum_real=autorizar_secullum_real):
        return ExecutorSecullumReal(servico)
    return ExecutorSecullumSombra()
