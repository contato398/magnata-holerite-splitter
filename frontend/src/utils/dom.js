/**
 * Helper minimo de criacao de DOM ("hyperscript-lite") -- sem
 * framework, sem virtual DOM, sem build step. Cada "componente" em
 * components/*.js e so uma funcao que recebe dados e devolve um Node
 * real via `h()`.
 *
 * Reescreve o container inteiro a cada render (nunca faz diffing) --
 * escolha deliberada de simplicidade para esta fase: o volume de dados
 * (dezenas de cartoes, nao milhares) nao justifica um virtual DOM.
 */

const EVENTO_PREFIXO = /^on([A-Z].*)$/;

function aplicarProps(el, props) {
  for (const [chave, valor] of Object.entries(props || {})) {
    if (valor == null || valor === false) continue;
    const matchEvento = chave.match(EVENTO_PREFIXO);
    if (matchEvento) {
      el.addEventListener(matchEvento[1].toLowerCase(), valor);
    } else if (chave === 'className') {
      el.setAttribute('class', valor);
    } else if (chave === 'style' && typeof valor === 'object') {
      Object.assign(el.style, valor);
    } else if (chave === 'dataset' && typeof valor === 'object') {
      for (const [dKey, dVal] of Object.entries(valor)) el.dataset[dKey] = dVal;
    } else if (chave in el && typeof el[chave] !== 'function' && chave !== 'list') {
      // propriedades DOM diretas (value, checked, disabled...) -- mais
      // confiavel que setAttribute para inputs/selects controlados.
      el[chave] = valor;
    } else {
      el.setAttribute(chave, valor);
    }
  }
}

function anexarFilhos(el, children) {
  const lista = Array.isArray(children) ? children : [children];
  for (const filho of lista.flat(Infinity)) {
    if (filho == null || filho === false) continue;
    el.appendChild(filho instanceof Node ? filho : document.createTextNode(String(filho)));
  }
}

/** @returns {HTMLElement} */
export function h(tag, props = {}, children = []) {
  const el = document.createElement(tag);
  aplicarProps(el, props);
  anexarFilhos(el, children);
  return el;
}

/** Marcado de proposito -- so para markup SVG estatico escrito por nos (icones), nunca para dados vindos da API/mock. */
export function svgIcon(svgMarkup, { className } = {}) {
  const template = document.createElement('template');
  template.innerHTML = svgMarkup.trim();
  const node = template.content.firstElementChild;
  if (className && node) node.setAttribute('class', className);
  return node;
}

export function mount(container, node) {
  clear(container);
  if (node != null) container.appendChild(node);
}

export function clear(container) {
  while (container.firstChild) container.removeChild(container.firstChild);
}

export function qs(selector, root = document) {
  return root.querySelector(selector);
}

export function qsa(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}
