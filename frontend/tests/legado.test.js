/**
 * "ausência de dependência do legado" (item 12 do pedido) -- verifica,
 * lendo o proprio codigo-fonte servido pelo navegador (mesma origem),
 * que nenhum arquivo do painel referencia o Flask/app.py legado, um
 * ID/campo do Airtable, nem chama `fetch()` contra um servico real --
 * este modulo so deve falar com data/mockData.js.
 */
import { describe, it, assertTrue } from './test-harness.js';

const ARQUIVOS_FONTE = [
  '../src/app.js', '../src/nav.js',
  '../src/api/contracts.js', '../src/api/autorizacao.js', '../src/api/errors.js', '../src/api/mockAdapter.js',
  '../src/state/store.js', '../src/state/filtros.js',
  '../src/data/mockData.js',
  '../src/utils/format.js', '../src/utils/dom.js', '../src/utils/icons.js', '../src/utils/prioridade.js',
  '../src/utils/responsive.js', '../src/utils/debounce.js',
  '../src/components/Sidebar.js', '../src/components/Header.js', '../src/components/ResumoCards.js',
  '../src/components/EsteiraColuna.js', '../src/components/EsteiraBoard.js', '../src/components/DocumentoCard.js',
  '../src/components/Filtros.js', '../src/components/Paginacao.js',
  '../src/components/PainelDetalheDocumento.js', '../src/components/PainelDetalheLote.js', '../src/components/EstadosUI.js',
  '../src/views/DashboardView.js', '../src/views/DocumentosView.js', '../src/views/BloqueiosView.js',
  '../src/views/AcoesHumanasView.js', '../src/views/ParadosView.js', '../src/views/viewHelpers.js',
];

// Termos cuja presenca indicaria acoplamento de CODIGO com o backend
// legado (Flask/app.py) -- nenhum arquivo desta fase deveria conter
// essas palavras em hipotese nenhuma, nem em comentario.
const TERMOS_PROIBIDOS_SEMPRE = ['flask', 'app.py', 'localhost:5000', 'localhost:10000'];

// Padroes de acoplamento REAL com o Airtable (URL da API, IDs de
// base/tabela/campo no formato do Airtable) -- mais precisos que a
// palavra solta "airtable", que pode aparecer legitimamente em
// comentario explicando que algo NAO usa Airtable (ver
// data/mockData.js: "nenhum campo ou identificador do Airtable e
// reaproveitado"). Os IDs so contam dentro de uma STRING LITERAL
// (entre aspas) -- um identificador de variavel/funcao em camelCase
// (ex.: "recebidosHojeResp") pode coincidir com o mesmo prefixo de 3
// letras + 14 caracteres por acaso; um literal de string com essa
// forma exata e um sinal real de acoplamento.
const PADROES_ACOPLAMENTO_AIRTABLE = [
  /airtable\.com/i,
  /['"](?:key|app|tbl|fld|rec)[a-zA-Z0-9]{14}['"]/, // API key / base / table / field / record id, como literal
];

describe('ausência de dependência do legado', () => {
  it('nenhum arquivo-fonte do painel menciona Flask ou app.py', async () => {
    for (const caminho of ARQUIVOS_FONTE) {
      const resposta = await fetch(new URL(caminho, import.meta.url));
      assertTrue(resposta.ok, `nao foi possivel ler ${caminho} (status ${resposta.status})`);
      const texto = (await resposta.text()).toLowerCase();
      for (const termo of TERMOS_PROIBIDOS_SEMPRE) {
        assertTrue(!texto.includes(termo), `${caminho} menciona um termo proibido: "${termo}"`);
      }
    }
  });

  it('nenhum arquivo-fonte tem acoplamento real com o Airtable (URL da API ou IDs de base/tabela/campo/registro)', async () => {
    for (const caminho of ARQUIVOS_FONTE) {
      const resposta = await fetch(new URL(caminho, import.meta.url));
      const texto = await resposta.text();
      for (const padrao of PADROES_ACOPLAMENTO_AIRTABLE) {
        assertTrue(!padrao.test(texto), `${caminho} parece acoplado ao Airtable (padrão: ${padrao})`);
      }
    }
  });

  it('nenhum arquivo-fonte chama fetch()/XMLHttpRequest contra um servico real (so o teste de legado acima usa fetch, para ler o proprio codigo)', async () => {
    for (const caminho of ARQUIVOS_FONTE) {
      const resposta = await fetch(new URL(caminho, import.meta.url));
      const texto = await resposta.text();
      assertTrue(!/\bfetch\s*\(/.test(texto), `${caminho} chama fetch() -- Fase 5 so deve usar dados mockados`);
      assertTrue(!/XMLHttpRequest/.test(texto), `${caminho} usa XMLHttpRequest -- Fase 5 so deve usar dados mockados`);
    }
  });

  it('mockData.js é a única fonte de dados do adapter -- nenhum outro arquivo importa dados brutos diretamente', async () => {
    const resposta = await fetch(new URL('../src/api/mockAdapter.js', import.meta.url));
    const texto = await resposta.text();
    assertTrue(texto.includes("from '../data/mockData.js'"));
  });
});
