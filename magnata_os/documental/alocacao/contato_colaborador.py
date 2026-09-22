"""Contato Canônico de Colaborador V1 -- domínio puro.

Fecha a lacuna comprovada por auditoria (ULTRAPLAN "RESOLUÇÃO CANÔNICA
DE DESTINATÁRIO PARA DISTRIBUIÇÃO DOCUMENTAL"): não existia nenhuma
capacidade persistente, não-Airtable, que resolvesse o telefone/
WhatsApp de um `colaborador_id` -- a única fonte real era um GET direto
ao Airtable em `app.py` (`_buscar_funcionario_nome_whatsapp`), a cada
disparo.

Mesmo padrão arquitetural já aprovado e em produção local por
`identidade_colaborador.py` (Identidade Canônica de Colaborador V1) --
`Protocol` + implementação em memória (testes) + implementação Postgres
(`adapters/postgres_contato_colaborador.py`) + bootstrap transitório a
partir do Airtable (`importacao_lote/adapters/
bootstrap_contato_colaborador_airtable.py`). **Airtable nunca é
consultado em runtime de resolução** -- mesma regra pétrea.

**Diferença deliberada em relação a `identidade_colaborador.py`**: CPF
só precisa de comparação de igualdade, por isso é armazenado como
HMAC-hash (nunca reversível). Telefone/WhatsApp, ao contrário, precisa
ser RECUPERÁVEL em forma usável para disparo real -- por isso este
módulo usa criptografia REVERSÍVEL (Fernet: AES-128-CBC + HMAC
autenticado, biblioteca `cryptography`, nunca uma implementação de
cifra própria) para o valor em si, e mantém um `hash_auxiliar`
(HMAC-SHA256, mesmo desenho de `identidade_colaborador.
calcular_identificador_hash`) só para comparação/deduplicação sem
precisar decifrar -- decisão de retenção aprovada explicitamente antes
desta implementação (nunca hash-only, nunca texto puro).

**Nenhuma dependência de Postgres/Airtable/Flask/`app.py` aqui** (mesma
disciplina de `magnata_os/CLAUDE.md` e do precedente já estabelecido
por `identidade_colaborador.py`) -- só `cryptography`/`hashlib`/`hmac`
da stdlib+lib de terceiros já declarada em `requirements.txt`. Chaves
(Fernet e HMAC) sempre já prontas (bytes), nunca lidas de variável de
ambiente por este módulo -- isso é `configuracao_contato_colaborador.py`.

**Normalização de número é reimplementação independente, não import de
`app.py`** (mesma disciplina já registrada em
`magnata_os/documental/importacao_lote/CLAUDE.md`: "IDs de tabela/campo
do Airtable duplicados aqui, não importados de `app.py`... custo
aceito... registrado, não escondido"). `app.py` é legado protegido
(`/CLAUDE.md` §7) -- nenhum módulo novo em `magnata_os/` cria
dependência de import contra ele. A lógica replicada aqui
(`normalizar_numero_whatsapp_v1`) é intencionalmente equivalente a
`app.py::_normalizar_numero_evolution` (DDI 55 + DDD + número, 12/13
dígitos finais) -- se o formato mudar num lugar, o outro precisa ser
atualizado separadamente; isso é aceito, não escondido.

`colaborador_id` é tratado como opaco em todo este módulo, mesmo
princípio de `identidade_colaborador.py` -- hoje, de fato, o Airtable
record id de Funcionários.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import re
import threading
from datetime import datetime
from typing import Dict, List, Optional, Protocol, Tuple

from cryptography.fernet import Fernet, InvalidToken

CANAL_WHATSAPP = 'whatsapp'
"""Único canal desta V1 -- texto livre (não Enum) para permitir canal
novo (ex.: 'email') sem migration de schema, mesmo espírito de
`origem` em `identidade_colaborador_observada`."""


def _exigir_texto(valor: str, nome_campo: str) -> None:
    if not (valor or '').strip():
        raise ValueError(f'{nome_campo} deve ser texto nao vazio')


def _exigir_bytes_nao_vazio(valor: bytes, nome_campo: str) -> None:
    if not isinstance(valor, (bytes, bytearray)) or len(valor) == 0:
        raise ValueError(f'{nome_campo} deve ser bytes nao vazio')


@dataclasses.dataclass(frozen=True)
class RegistroContatoColaborador:
    """Uma linha da tabela `contato_colaborador_observado` (migration
    0004) -- imutável, mesma disciplina de
    `IdentidadeColaboradorObservada`. `valor_cifrado` é sempre o
    resultado de `cifrar_valor_contato` (Fernet) -- nunca o valor em
    claro; `hash_auxiliar` é sempre `calcular_hash_auxiliar_contato`
    (HMAC-SHA256) -- serve só para detectar duplicidade/conflito sem
    decifrar, nunca para recuperar o valor."""

    colaborador_id: str
    canal: str
    valor_cifrado: bytes
    hash_auxiliar: str
    versao_chave: str
    origem: str
    criado_em: datetime
    atualizado_em: datetime

    def __post_init__(self) -> None:
        _exigir_texto(self.colaborador_id, 'colaborador_id')
        _exigir_texto(self.canal, 'canal')
        _exigir_bytes_nao_vazio(self.valor_cifrado, 'valor_cifrado')
        _exigir_texto(self.hash_auxiliar, 'hash_auxiliar')
        _exigir_texto(self.versao_chave, 'versao_chave')
        _exigir_texto(self.origem, 'origem')


class ConflitoContatoColaborador(Exception):
    """O MESMO (colaborador_id, canal) já está registrado com um
    `hash_auxiliar` DIFERENTE do que está sendo escrito -- nunca
    resolvido por sobrescrita silenciosa (mesmo princípio de
    `ConflitoIdentidadeColaborador`/"arquivo original é imutável",
    `/CLAUDE.md` raiz §4). Uma mudança legítima de telefone exige
    reconciliação explícita (fora do escopo desta V1 -- ver bootstrap),
    nunca uma escrita automática silenciosa.

    Nunca carrega valor em claro nem `valor_cifrado` -- só os 2
    `hash_auxiliar` em disputa, estruturados (nunca só no texto)."""

    def __init__(
        self, colaborador_id: str, canal: str,
        hash_auxiliar_existente: str, hash_auxiliar_tentativa: str,
    ) -> None:
        self.colaborador_id = colaborador_id
        self.canal = canal
        self.hash_auxiliar_existente = hash_auxiliar_existente
        self.hash_auxiliar_tentativa = hash_auxiliar_tentativa
        super().__init__(
            f'contato ja registrado para colaborador_id={colaborador_id!r} canal={canal!r} '
            f'(hash_auxiliar_existente={hash_auxiliar_existente!r}), tentativa com '
            f'hash_auxiliar_tentativa={hash_auxiliar_tentativa!r}'
        )


class ContatoColaboradorDescriptografiaFalhou(Exception):
    """`valor_cifrado` não pôde ser decifrado com a chave/versão
    informada -- chave errada, token corrompido, ou rotação sem a chave
    antiga disponível. Nunca propaga o erro original da biblioteca de
    criptografia (que pode incluir o token bruto) -- só este tipo,
    nunca com o `valor_cifrado` no texto da mensagem. Fail-closed: quem
    captura esta exceção nunca deve inferir o valor, só tratar como
    contato indisponível."""


_REGEX_SOMENTE_DIGITOS = re.compile(r'\D+')


def normalizar_numero_whatsapp_v1(bruto: Optional[str]) -> Optional[str]:
    """Normaliza um telefone bruto para o formato pronto para uso como
    destinatário de WhatsApp: DDI 55 + DDD + número, só dígitos.
    Reimplementação intencional e independente de
    `app.py::_normalizar_numero_evolution` (ver docstring do módulo) --
    mesmo comportamento observado: extrai dígitos; se já começa com
    '55' e tem 12/13 dígitos, usa como está; senão, se tem 10/11
    dígitos, prefixa '55'; qualquer outro caso -- vazio, tamanho
    inesperado -- é `None` (fail-closed, nunca uma adivinhação de
    formato)."""
    if not bruto or not str(bruto).strip():
        return None
    digitos = _REGEX_SOMENTE_DIGITOS.sub('', str(bruto))
    if not digitos:
        return None
    if digitos.startswith('55') and len(digitos) in (12, 13):
        candidato = digitos
    elif len(digitos) in (10, 11):
        candidato = f'55{digitos}'
    else:
        return None
    return candidato if len(candidato) in (12, 13) else None


def cifrar_valor_contato(chave_fernet: bytes, valor_normalizado: str) -> bytes:
    """Cifra (Fernet -- AES-128-CBC + HMAC autenticado) o valor JÁ
    NORMALIZADO (quem chama normaliza antes -- esta função nunca
    normaliza sozinha, para que o valor decifrado seja sempre
    exatamente o que foi persistido). Determinístico apenas quanto ao
    conteúdo decifrável -- Fernet inclui timestamp/nonce no token, então
    o MESMO valor cifrado duas vezes produz tokens BYTES diferentes;
    por isso a deduplicação nunca compara `valor_cifrado` diretamente,
    sempre `hash_auxiliar` (HMAC determinístico, ver
    `calcular_hash_auxiliar_contato`)."""
    if not chave_fernet:
        raise ValueError('chave_fernet nao pode ser vazia')
    if not (valor_normalizado or '').strip():
        raise ValueError('valor_normalizado nao pode ser vazio')
    return Fernet(chave_fernet).encrypt(valor_normalizado.encode('utf-8'))


def decifrar_valor_contato(chave_fernet: bytes, valor_cifrado: bytes) -> str:
    """Decifra `valor_cifrado` com a chave da versão correta (quem
    chama já resolveu qual chave usar, via `versao_chave` do registro).
    Este é o ÚNICO ponto autorizado a produzir o valor em claro --
    nunca chamado fora de `resolver_contato_colaborador_para_ordem`
    (ponto autorizado de resolução) nesta V1. Levanta
    `ContatoColaboradorDescriptografiaFalhou` (nunca a exceção crua da
    biblioteca) se o token for inválido/corrompido/chave errada."""
    if not chave_fernet:
        raise ValueError('chave_fernet nao pode ser vazia')
    _exigir_bytes_nao_vazio(valor_cifrado, 'valor_cifrado')
    try:
        return Fernet(chave_fernet).decrypt(valor_cifrado).decode('utf-8')
    except InvalidToken as exc:
        raise ContatoColaboradorDescriptografiaFalhou(
            'nao foi possivel decifrar o contato com a chave/versao informada'
        ) from exc


def calcular_hash_auxiliar_contato(chave_hmac: bytes, valor_normalizado: str) -> str:
    """HMAC-SHA256 (hex) do valor já normalizado, com uma chave SEPARADA
    da chave de cifragem Fernet (higiene criptográfica: nunca reusar a
    mesma chave para cifrar e para autenticar/comparar -- ver
    `configuracao_contato_colaborador.py`). Serve SÓ para detectar
    duplicidade/conflito (`RepositorioContatoColaborador.
    criar_ou_confirmar`) -- nunca para recuperar o valor (isso é
    `decifrar_valor_contato`, com a chave Fernet, não esta)."""
    if not chave_hmac:
        raise ValueError('chave_hmac nao pode ser vazia')
    if not valor_normalizado:
        raise ValueError('valor_normalizado nao pode ser vazio')
    return hmac.new(chave_hmac, valor_normalizado.encode('utf-8'), hashlib.sha256).hexdigest()


class RepositorioContatoColaborador(Protocol):
    """Contrato que qualquer adapter (memória, Postgres) precisa
    cumprir. `criar_ou_confirmar` é a ÚNICA forma de escrita -- garante
    que o mesmo (colaborador_id, canal) nunca é sobrescrito
    silenciosamente: mesmo `hash_auxiliar` é idempotente (reprocessamento
    do mesmo bootstrap); `hash_auxiliar` diferente é sempre
    `ConflitoContatoColaborador`, nunca um UPDATE automático."""

    def buscar_por_colaborador(
        self, colaborador_id: str, canal: str,
    ) -> Optional[RegistroContatoColaborador]: ...

    def criar_ou_confirmar(
        self, registro: RegistroContatoColaborador,
    ) -> Tuple[RegistroContatoColaborador, bool]: ...

    def listar_todos(self) -> List[RegistroContatoColaborador]: ...


class RepositorioContatoColaboradorEmMemoria:
    """Implementação em memória -- para testes e para qualquer fase sem
    Postgres real conectado. Protegida por `threading.Lock` único,
    mesma disciplina de `RepositorioIdentidadeColaboradorEmMemoria`:
    `criar_ou_confirmar` é atômica sob chamadas concorrentes."""

    def __init__(self) -> None:
        self._por_chave: Dict[Tuple[str, str], RegistroContatoColaborador] = {}
        self._lock = threading.Lock()

    def buscar_por_colaborador(
        self, colaborador_id: str, canal: str,
    ) -> Optional[RegistroContatoColaborador]:
        with self._lock:
            return self._por_chave.get((colaborador_id, canal))

    def criar_ou_confirmar(
        self, registro: RegistroContatoColaborador,
    ) -> Tuple[RegistroContatoColaborador, bool]:
        chave = (registro.colaborador_id, registro.canal)
        with self._lock:
            existente = self._por_chave.get(chave)
            if existente is not None:
                if existente.hash_auxiliar != registro.hash_auxiliar:
                    raise ConflitoContatoColaborador(
                        registro.colaborador_id, registro.canal,
                        existente.hash_auxiliar, registro.hash_auxiliar,
                    )
                return existente, False
            self._por_chave[chave] = registro
            return registro, True

    def listar_todos(self) -> List[RegistroContatoColaborador]:
        with self._lock:
            return list(self._por_chave.values())


def resolver_contato_colaborador_para_ordem(
    repositorio: RepositorioContatoColaborador,
    colaborador_id: str,
    canal: str,
    chave_fernet: bytes,
) -> Optional[str]:
    """Porta de runtime única desta missão -- o ÚNICO ponto autorizado
    a decifrar um contato para uso real (destinatário de uma Ordem).

    Fail-closed em toda borda, nunca uma exceção que propaga para quem
    chama (que é `ResolverParametrosOrdemPrestacao`, um `Callable` que
    já espera `Optional[...]`, nunca uma exceção de domínio de contato):
    - `colaborador_id`/`canal` vazios -> `None`;
    - nenhum registro encontrado (ausente) -> `None`;
    - descriptografia falha (chave errada/token corrompido) -> `None`;
    - valor decifrado não sobrevive à renormalização (defeito de dado
      histórico -- inválido) -> `None`.

    "Múltiplo" nunca acontece por construção (chave primária
    `(colaborador_id, canal)` no repositório garante no máximo 1
    registro) -- não há branch para isso porque o dado não permite.

    Nunca conhece Airtable, Evolution, WhatsApp real, Ordem ou
    Distribuição Documental -- só resolve o valor, puro (dado o
    repositório e a chave já prontos)."""
    if not (colaborador_id or '').strip() or not (canal or '').strip():
        return None

    registro = repositorio.buscar_por_colaborador(colaborador_id, canal)
    if registro is None:
        return None

    try:
        valor_decifrado = decifrar_valor_contato(chave_fernet, registro.valor_cifrado)
    except ContatoColaboradorDescriptografiaFalhou:
        return None

    return normalizar_numero_whatsapp_v1(valor_decifrado)
