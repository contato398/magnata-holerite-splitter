/**
 * Store reativo minimo (pub-sub) -- sem dependencia externa. Guarda o
 * estado global do painel (perfil mock atual, rota, filtros por tela,
 * cache da ultima resposta de cada consulta). Views se inscrevem e
 * re-renderizam quando o estado muda; nenhum componente muta o estado
 * diretamente, sempre via `store.setState(...)`.
 */

export function createStore(initialState = {}) {
  let state = { ...initialState };
  const listeners = new Set();

  function getState() {
    return state;
  }

  /** Aceita um objeto parcial ou uma funcao (state) => objeto parcial. */
  function setState(partial) {
    const delta = typeof partial === 'function' ? partial(state) : partial;
    state = { ...state, ...delta };
    for (const listener of listeners) listener(state);
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return { getState, setState, subscribe };
}
