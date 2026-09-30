import { describe, it, assertEqual, assertTrue } from './test-harness.js';
import { createStore } from '../src/state/store.js';

describe('state/store.js', () => {
  it('getState devolve o estado inicial', () => {
    const store = createStore({ x: 1 });
    assertEqual(store.getState().x, 1);
  });

  it('setState com objeto faz merge raso', () => {
    const store = createStore({ x: 1, y: 2 });
    store.setState({ y: 20 });
    assertEqual(store.getState().x, 1);
    assertEqual(store.getState().y, 20);
  });

  it('setState aceita uma funcao (state) => delta', () => {
    const store = createStore({ contador: 0 });
    store.setState((s) => ({ contador: s.contador + 1 }));
    store.setState((s) => ({ contador: s.contador + 1 }));
    assertEqual(store.getState().contador, 2);
  });

  it('subscribe notifica listeners a cada setState', () => {
    const store = createStore({ x: 0 });
    let chamadas = 0;
    store.subscribe(() => { chamadas += 1; });
    store.setState({ x: 1 });
    store.setState({ x: 2 });
    assertEqual(chamadas, 2);
  });

  it('a funcao devolvida por subscribe cancela a inscricao', () => {
    const store = createStore({ x: 0 });
    let chamadas = 0;
    const cancelar = store.subscribe(() => { chamadas += 1; });
    store.setState({ x: 1 });
    cancelar();
    store.setState({ x: 2 });
    assertEqual(chamadas, 1);
  });

  it('dois stores independentes nao compartilham estado', () => {
    const s1 = createStore({ x: 1 });
    const s2 = createStore({ x: 1 });
    s1.setState({ x: 99 });
    assertEqual(s2.getState().x, 1);
    assertTrue(s1.getState().x !== s2.getState().x);
  });
});
