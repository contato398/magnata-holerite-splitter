/**
 * Harness de testes minimo, sem dependencia externa (nenhum Node.js
 * disponivel neste ambiente -- ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE5.md,
 * secao "Tecnologia escolhida"). `describe`/`it`/`assert*` bastam para
 * cobrir o item 12 do pedido sem precisar de Jest/Mocha/Vitest.
 *
 * Uso: tests/index.html carrega este arquivo + todos os *.test.js via
 * <script type="module">, chama rodarTestes() e renderiza o resultado
 * na propria pagina (visivel a olho e legivel por automacao de
 * navegador, sem precisar de terminal Node).
 */

const suites = [];
let suiteAtual = null;

export function describe(nome, fn) {
  const suite = { nome, testes: [] };
  suites.push(suite);
  const anterior = suiteAtual;
  suiteAtual = suite;
  fn();
  suiteAtual = anterior;
}

export function it(nome, fn) {
  if (!suiteAtual) throw new Error(`it("${nome}") chamado fora de um describe(...)`);
  suiteAtual.testes.push({ nome, fn });
}

export class AssercaoFalhou extends Error {}

export function assertTrue(valor, mensagem = 'esperado valor verdadeiro') {
  if (!valor) throw new AssercaoFalhou(mensagem);
}

export function assertFalse(valor, mensagem = 'esperado valor falso') {
  if (valor) throw new AssercaoFalhou(mensagem);
}

export function assertEqual(atual, esperado, mensagem) {
  if (atual !== esperado) {
    throw new AssercaoFalhou(mensagem || `esperado ${JSON.stringify(esperado)}, recebido ${JSON.stringify(atual)}`);
  }
}

export function assertDeepEqual(atual, esperado, mensagem) {
  const a = JSON.stringify(atual);
  const b = JSON.stringify(esperado);
  if (a !== b) throw new AssercaoFalhou(mensagem || `esperado ${b}, recebido ${a}`);
}

export function assertThrows(fn, validador, mensagem) {
  let lancou = false;
  let erroCapturado = null;
  try {
    fn();
  } catch (erro) {
    lancou = true;
    erroCapturado = erro;
  }
  if (!lancou) throw new AssercaoFalhou(mensagem || 'esperado que a funcao lancasse uma excecao');
  if (validador) {
    if (typeof validador === 'function' && validador.prototype instanceof Error) {
      assertTrue(erroCapturado instanceof validador, `esperado instancia de ${validador.name}, recebido ${erroCapturado.constructor.name}`);
    } else if (typeof validador === 'function') {
      assertTrue(validador(erroCapturado), mensagem || 'validador do erro retornou falso');
    }
  }
}

export async function assertRejects(promessaOuFn, validador, mensagem) {
  let lancou = false;
  let erroCapturado = null;
  try {
    await (typeof promessaOuFn === 'function' ? promessaOuFn() : promessaOuFn);
  } catch (erro) {
    lancou = true;
    erroCapturado = erro;
  }
  if (!lancou) throw new AssercaoFalhou(mensagem || 'esperado que a promise fosse rejeitada');
  if (validador) {
    if (typeof validador === 'function' && validador.prototype instanceof Error) {
      assertTrue(erroCapturado instanceof validador, `esperado instancia de ${validador.name}, recebido ${erroCapturado.constructor.name}`);
    } else if (typeof validador === 'function') {
      assertTrue(validador(erroCapturado), mensagem || 'validador do erro retornou falso');
    }
  }
}

/** @returns {Promise<{suites: number, testes: number, falhas: number, resultados: Array}>} */
export async function rodarTestes() {
  const resultados = [];
  let totalTestes = 0;
  let totalFalhas = 0;

  for (const suite of suites) {
    const resultadosSuite = [];
    for (const teste of suite.testes) {
      totalTestes += 1;
      try {
        await teste.fn();
        resultadosSuite.push({ nome: teste.nome, ok: true });
      } catch (erro) {
        totalFalhas += 1;
        resultadosSuite.push({ nome: teste.nome, ok: false, mensagem: erro.message, stack: erro.stack });
      }
    }
    resultados.push({ nome: suite.nome, testes: resultadosSuite });
  }

  return { suites: suites.length, testes: totalTestes, falhas: totalFalhas, resultados };
}

export function renderRelatorio(container, relatorio) {
  const doc = container.ownerDocument;
  container.innerHTML = '';

  const resumo = doc.createElement('h1');
  resumo.textContent = relatorio.falhas === 0
    ? `✅ ${relatorio.testes} testes, todos passaram (${relatorio.suites} suítes)`
    : `❌ ${relatorio.falhas} de ${relatorio.testes} testes falharam (${relatorio.suites} suítes)`;
  resumo.style.color = relatorio.falhas === 0 ? '#0e9f6e' : '#d64545';
  container.appendChild(resumo);
  container.dataset.status = relatorio.falhas === 0 ? 'ok' : 'falhou';
  container.dataset.totalTestes = String(relatorio.testes);
  container.dataset.totalFalhas = String(relatorio.falhas);

  for (const suite of relatorio.resultados) {
    const bloco = doc.createElement('section');
    const titulo = doc.createElement('h2');
    titulo.textContent = suite.nome;
    bloco.appendChild(titulo);

    const lista = doc.createElement('ul');
    for (const teste of suite.testes) {
      const item = doc.createElement('li');
      item.textContent = teste.ok ? `✅ ${teste.nome}` : `❌ ${teste.nome} — ${teste.mensagem}`;
      item.style.color = teste.ok ? '#0e9f6e' : '#d64545';
      item.dataset.ok = String(teste.ok);
      lista.appendChild(item);
    }
    bloco.appendChild(lista);
    container.appendChild(bloco);
  }
}
