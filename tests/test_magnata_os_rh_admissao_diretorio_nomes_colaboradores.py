"""`montar_diretorio_nomes` -- fonte real do `diretorio_nomes` que
`interpretar_ordem_operador_v1.py` já espera (Mapping[colaborador_id,
nome]). Dados 100% sintéticos."""
from typing import Dict, Optional, Tuple

from magnata_os.rh_admissao.dominio_cadastro_colaborador import Colaborador, SituacaoCadastroColaborador
from magnata_os.rh_admissao.diretorio_nomes_colaboradores import montar_diretorio_nomes


class _RepositorioColaboradoresEmMemoria:
    def __init__(self, colaboradores) -> None:
        self._por_id: Dict[str, Colaborador] = {c.colaborador_id: c for c in colaboradores}

    def salvar(self, colaborador: Colaborador) -> Colaborador:
        self._por_id[colaborador.colaborador_id] = colaborador
        return colaborador

    def buscar_por_id(self, colaborador_id: str) -> Optional[Colaborador]:
        return self._por_id.get(colaborador_id)

    def listar(self) -> Tuple[Colaborador, ...]:
        return tuple(self._por_id.values())


def test_monta_dict_colaborador_id_para_nome_independente_de_local_trabalho():
    repo = _RepositorioColaboradoresEmMemoria([
        Colaborador(
            colaborador_id='colab-1', cpf='900.000.000-01', nome='colaborador sintetico um',
            situacao_cadastro=SituacaoCadastroColaborador.CADASTRO_COMPLETO, local_trabalho='Escala A',
        ),
        Colaborador(
            colaborador_id='colab-2', cpf='900.000.000-02', nome='colaborador sintetico dois',
            situacao_cadastro=SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO,
        ),
    ])

    diretorio = montar_diretorio_nomes(repo)

    assert diretorio == {
        'colab-1': 'colaborador sintetico um',
        'colab-2': 'colaborador sintetico dois',
    }


def test_sem_colaboradores_devolve_dict_vazio():
    assert montar_diretorio_nomes(_RepositorioColaboradoresEmMemoria([])) == {}
