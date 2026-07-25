/** Debounce generico -- usado pela busca por nome (Filtros.js) para nao disparar uma consulta a cada tecla. */
export function debounce(fn, esperaMs = 250) {
  let timer = null;
  function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), esperaMs);
  }
  debounced.cancelar = () => clearTimeout(timer);
  return debounced;
}
