/**
 * Menu lateral (item 2 do pedido) -- simbolo da marca no topo, links de
 * navegacao. So aparece em telas >= 768px (base.css); em telas menores
 * a navegacao mobile equivalente fica em Header.js/app.js
 * (.app-nav-mobile).
 */
import { h } from '../utils/dom.js';
import { ROTAS, iconeDaRota } from '../nav.js';

/**
 * @param {{rotaAtualId: string, contagens?: Object<string, number>}} opcoes
 */
export function Sidebar({ rotaAtualId, contagens = {} } = {}) {
  return h('nav', { className: 'app-sidebar', 'aria-label': 'Navegação principal' }, [
    h('div', { className: 'sidebar-topo' }, [
      h('div', { className: 'marca-simbolo' }, [h('img', { src: 'assets/brand/magnata-symbol.svg', alt: 'Símbolo Magnata' })]),
    ]),
    h('ul', { className: 'sidebar-nav' }, ROTAS.map((r) => h('li', {}, [
      h('a', {
        className: 'sidebar-link',
        href: r.rota,
        'aria-current': r.id === rotaAtualId ? 'page' : undefined,
      }, [
        iconeDaRota(r),
        h('span', {}, r.titulo),
        contagens[r.id] != null ? h('span', { className: 'contagem' }, String(contagens[r.id])) : null,
      ]),
    ]))),
    h('div', { className: 'sidebar-rodape' }, 'Magnata OS · Central Documental'),
  ]);
}

/** Navegacao horizontal para telas pequenas (item 11 -- nunca escondida, so reformatada). */
export function NavMobile({ rotaAtualId } = {}) {
  return h('nav', { className: 'app-nav-mobile', 'aria-label': 'Navegação principal (celular)' },
    ROTAS.map((r) => h('a', {
      className: 'nav-mobile-link',
      href: r.rota,
      'aria-current': r.id === rotaAtualId ? 'page' : undefined,
    }, r.titulo))
  );
}
