"""Ponte de leitura entre o Holerite avulso para colaborador (fluxo real
de produção, hoje inteiramente em `app.py::_buscar_funcionario_nome_
whatsapp`) e o Contato Canônico de Colaborador V1 (`contato_
colaborador.py`).

Fecha a lacuna registrada em `/mnt/project-files/magnata-os/origem-dados-
holerite.md` (Pergunta 2): a resolução sem Airtable já existe e está
testada (`resolver_contato_colaborador_para_ordem`), mas só tem um
composition root real ligado ao fluxo da Prestação de Contas
(`resolver_parametros_ordem_prestacao_contato_v1.py`) -- nunca ao fluxo
de Holerite avulso.

Responsabilidade ESTRITA deste módulo: decidir, dado o gate já aberto ou
fechado (`autorizacao_resolucao_contato_canonico_holerite_avulso_v1.py`,
decisão de outro módulo, nunca duplicada aqui), se e como chamar
`resolver_contato_colaborador_para_ordem` para um `funcionario_id` único.

Nunca:
    - decide o próprio gate -- `habilitado` é sempre argumento explícito
      do chamador, mesma disciplina de `autorizar_transporte_real` em
      `autorizacao_transporte_real.py`;
    - consulta Airtable (nenhum import de cliente Airtable aqui -- quem
      souber comparar/combinar com o valor do Airtable é `app.py`, via o
      diff proposto em `pacote-autorizacao-app-py.md`, item 5);
    - levanta exceção para fora deste módulo por falha de resolução
      (ausência de contato, descriptografia falha, `colaborador_id`
      vazio) -- todos esses casos já são `None` dentro de
      `resolver_contato_colaborador_para_ordem`, e este módulo preserva
      esse fail-closed sem adicionar nenhuma exceção nova;
    - abre conexão com Postgres -- `repositorio` é sempre injetado
      (`RepositorioContatoColaborador`, Protocol já existente), mesma
      disciplina de `construir_resolvedor_parametros_ordem_prestacao_
      contato_v1`.

**Reuso de conexão (resolve o risco registrado em
`pacote-autorizacao-app-py.md`, item 6):** `construir_resolvedor_
whatsapp_holerite_avulso_contato_canonico_v1`, abaixo, fecha sobre um
`repositorio`/`chave_fernet`/`habilitado` abertos UMA VEZ por quem
compõe e devolve uma função reutilizável para quantas chamadas forem
necessárias -- mesma disciplina de reuso já usada por
`ciclo_producao_v1.main` (uma conexão por ciclo, nunca uma por item
processado) e pelo CLI de bootstrap (`bootstrap_contato_colaborador_
whatsapp_cli.py`: uma conexão por execução, não por registro). Este
módulo nunca decide QUANDO abrir/fechar essa conexão (isso é de quem
compõe, por exemplo uma vez por requisição Flask via `flask.g`) -- só
garante que, uma vez aberta, a mesma conexão/repositório serve a
quantas resoluções forem precisas, sem reabrir."""
from __future__ import annotations

from typing import Callable, Optional

from .contato_colaborador import (
    CANAL_WHATSAPP,
    RepositorioContatoColaborador,
    resolver_contato_colaborador_para_ordem,
)

ResolvedorWhatsappHoleriteAvulso = Callable[[str], Optional[str]]
"""Assinatura do resolvedor já composto: `funcionario_id -> whatsapp ou
None`. Produzido por `construir_resolvedor_whatsapp_holerite_avulso_
contato_canonico_v1`, chamável múltiplas vezes sem reabrir nada."""


def resolver_whatsapp_holerite_avulso_via_contato_canonico(
    *,
    repositorio: RepositorioContatoColaborador,
    chave_fernet: bytes,
    funcionario_id: str,
    habilitado: bool,
    canal: str = CANAL_WHATSAPP,
) -> Optional[str]:
    """Devolve o WhatsApp resolvido via Contato Canônico, ou `None`
    quando: o gate está fechado (`habilitado=False`); `funcionario_id`
    é vazio; não há contato persistido para ele; ou a resolução falha
    por qualquer motivo já coberto por `resolver_contato_colaborador_
    para_ordem` (descriptografia, formato inválido).

    `None` aqui NUNCA significa "funcionário não tem WhatsApp" -- só
    significa "este módulo não pôde confirmar um valor pela via
    canônica". Quem chama (ver diff proposto) preserva o valor do
    Airtable como fallback nesse caso -- nunca trata `None` como
    `whatsapp_ausente` por conta própria."""
    if habilitado is not True:
        return None
    if not (funcionario_id or '').strip():
        return None
    return resolver_contato_colaborador_para_ordem(
        repositorio, funcionario_id, canal, chave_fernet,
    )


def construir_resolvedor_whatsapp_holerite_avulso_contato_canonico_v1(
    *,
    repositorio: RepositorioContatoColaborador,
    chave_fernet: bytes,
    habilitado: bool,
    canal: str = CANAL_WHATSAPP,
) -> ResolvedorWhatsappHoleriteAvulso:
    """Fábrica: fecha sobre `repositorio`/`chave_fernet`/`habilitado`
    (todos já prontos -- este módulo nunca os constrói) e devolve uma
    função `funcionario_id -> whatsapp ou None` chamável quantas vezes
    forem necessárias, sem reabrir nada a cada chamada.

    `habilitado` é capturado UMA VEZ na composição -- se o gate puder
    mudar durante a vida da conexão reutilizada (por exemplo, numa
    conexão de vida longa reusada entre requisições, o que esta V1 não
    pressupõe), quem compuser precisa reconstruir o resolvedor, não
    reutilizar um já composto com o valor antigo.

    Mesma disciplina de `ciclo_producao_v1.main` (conexão aberta uma
    vez, reutilizada por todas as ações do ciclo, fechada ao final) --
    este módulo não decide o ciclo de vida, só produz o resolvedor que
    não força reabertura."""
    def _resolvedor(funcionario_id: str) -> Optional[str]:
        return resolver_whatsapp_holerite_avulso_via_contato_canonico(
            repositorio=repositorio, chave_fernet=chave_fernet,
            funcionario_id=funcionario_id, habilitado=habilitado, canal=canal,
        )
    return _resolvedor
