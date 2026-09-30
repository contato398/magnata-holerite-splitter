/**
 * Autorizacao abstrata -- espelha autorizacao.py (Fase 4). Sem
 * autenticacao real nesta fase: o perfil atual e um mock visual (ver
 * components/Header.js), nunca o resultado de validar sessao/token.
 *
 * Separado de contracts.js de proposito para poder importar
 * PermissaoNegada de errors.js sem criar dependencia circular
 * (errors.js ja importa CodigoErro de contracts.js).
 */
import { PermissaoNegada } from './errors.js';

export const Perfil = Object.freeze({
  OPERACIONAL: 'OPERACIONAL',
  GESTOR: 'GESTOR',
  AUDITOR: 'AUDITOR',
});

export const PERMISSAO_LEITURA_GERAL = Object.freeze([Perfil.OPERACIONAL, Perfil.GESTOR, Perfil.AUDITOR]);
export const PERMISSAO_FILA_OPERACIONAL = Object.freeze([Perfil.OPERACIONAL, Perfil.GESTOR]);
export const PERMISSAO_AUDITORIA = Object.freeze([Perfil.GESTOR, Perfil.AUDITOR]);

/** Mesma regra de exigir_perfil() (autorizacao.py) -- nunca aplica em silencio. Levanta sempre um ApiError de verdade (PermissaoNegada), nunca um Error generico. */
export function exigirPerfil(perfilAtual, perfisPermitidos) {
  if (!perfisPermitidos.includes(perfilAtual)) {
    const permitidosStr = [...perfisPermitidos].sort().join(', ');
    throw new PermissaoNegada(
      `Perfil ${perfilAtual} nao tem permissao para esta consulta (permitido: ${permitidosStr}).`
    );
  }
}
