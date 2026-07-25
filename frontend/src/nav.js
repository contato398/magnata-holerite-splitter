/**
 * Configuracao unica de navegacao -- usada por Sidebar.js, nav mobile
 * (base.css/.app-nav-mobile) e pelo roteador (app.js), para nunca haver
 * duas listas de telas que podem ficar dessincronizadas.
 */
import { icon } from './utils/icons.js';

export const ROTAS = Object.freeze([
  { id: 'resumo', rota: '#/resumo', titulo: 'Resumo', subtitulo: 'Visão geral da esteira', icone: 'engrenagem' },
  { id: 'documentos', rota: '#/documentos', titulo: 'Documentos', subtitulo: 'Buscar e filtrar documentos', icone: 'caixaVazia' },
  { id: 'bloqueios', rota: '#/bloqueios', titulo: 'Bloqueios', subtitulo: 'Documentos que precisam de desbloqueio', icone: 'cadeado' },
  { id: 'acoes-humanas', rota: '#/acoes-humanas', titulo: 'Ações humanas', subtitulo: 'Documentos que precisam de você', icone: 'pessoa' },
  { id: 'parados', rota: '#/parados', titulo: 'Parados', subtitulo: 'Documentos parados há mais tempo', icone: 'relogio' },
]);

export function rotaPorId(id) {
  return ROTAS.find((r) => r.id === id) || ROTAS[0];
}

export function iconeDaRota(rota) {
  return icon(rota.icone, { className: 'icone' });
}
