"""BRIDGE TRANSITÓRIO (read-only) -- destinatário organizacional do
cliente a partir da tabela Clientes do Airtable.

Decisão humana registrada (Prestação upstream real, J3): manter a fonte
real existente, read-only e atrás de Protocol
(`FonteDestinatarioOrganizacionalCliente`, `classificacao/pacote_
prestacao.py`), até existir cadastro interno equivalente -- então este
adapter é trocado pelo MESMO Protocol, sem tocar domínio.

Campos auditados no legado (`app.py`, `_gerar_fila_envios_email`):
`Email` (texto) e `Email Contador` (lookup, lista). Mapeamento 1 campo ->
1 papel, SEM regra de negócio:
  - `CLIENTE_INSTITUCIONAL` <- `Email`;
  - `CONTADOR_DO_CLIENTE`   <- `Email Contador`.
O fallback do legado ("sem Email, usar o 1º Email Contador") NÃO é
reproduzido aqui: é regra de entrega, e decidir adotá-la é da política de
canal. Endereço sem forma mínima de e-mail (exatamente 1 '@', partes não
vazias) é descartado -- nunca "consertado" nem inventado.

Nunca escreve no Airtable; nunca loga endereço.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import PapelDestinatarioOrganizacional

from .airtable_leitura import LeitorAirtableSomenteLeitura


def _forma_minima_de_email(valor) -> Optional[str]:
    if not isinstance(valor, str):
        return None
    limpo = valor.strip()
    local, arroba, dominio = limpo.partition('@')
    if not arroba or not local or not dominio or '@' in dominio or any(c.isspace() for c in limpo):
        return None
    return limpo


class FonteDestinatarioOrganizacionalClienteAirtableShadow:
    """Implementa `FonteDestinatarioOrganizacionalCliente`. Lê a tabela
    Clientes 1 vez por instância (1 execução), sob demanda."""

    def __init__(self, leitor: LeitorAirtableSomenteLeitura) -> None:
        self._leitor = leitor
        self._por_cliente: Optional[Dict[str, Dict[PapelDestinatarioOrganizacional, Tuple[str, ...]]]] = None

    def _carregar(self) -> Dict[str, Dict[PapelDestinatarioOrganizacional, Tuple[str, ...]]]:
        if self._por_cliente is None:
            por_cliente = {}
            for registro in self._leitor.listar_campos_destinatario_clientes():
                contador = registro.get('emails_contador') or ()
                if isinstance(contador, str):
                    contador = (contador,)
                por_cliente[registro['cliente_id']] = {
                    PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL: tuple(
                        e for e in (_forma_minima_de_email(registro.get('email')),) if e
                    ),
                    PapelDestinatarioOrganizacional.CONTADOR_DO_CLIENTE: tuple(dict.fromkeys(
                        e for e in (_forma_minima_de_email(v) for v in contador) if e
                    )),
                }
            self._por_cliente = por_cliente
        return self._por_cliente

    def enderecos_para(
        self, cliente: ReferenciaCanonica, papel: PapelDestinatarioOrganizacional,
    ) -> Tuple[str, ...]:
        if cliente.tipo_entidade != 'CLIENTE':
            return ()
        return self._carregar().get(cliente.entidade_id, {}).get(papel, ())
