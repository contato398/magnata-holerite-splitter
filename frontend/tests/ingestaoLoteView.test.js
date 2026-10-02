/**
 * Testes da tela de Ingestão de Documentos em Lote
 * (views/IngestaoLoteView.js) -- formulário, clique, chamada à API
 * (sempre um duplo controlado aqui, nunca `apiClient` real) e exibição
 * do resumo. Ver docs/decisoes/painel-ingestao-documentos-lote-ui-v1.md.
 */
import { describe, it, assertEqual, assertTrue, assertFalse } from './test-harness.js';
import { IngestaoLoteView } from '../src/views/IngestaoLoteView.js';
import { createStore } from '../src/state/store.js';
import { PermissaoNegada } from '../src/api/errors.js';
import { FalhaSegurancaRequisicao } from '../src/api/apiAdapter.js';

function montarRaiz() {
  const raiz = document.createElement('div');
  document.body.appendChild(raiz);
  return raiz;
}

function montarView(apiClient) {
  const raiz = montarRaiz();
  const store = createStore({ perfil: 'GESTOR' });
  const destruir = IngestaoLoteView({ container: raiz, apiClient, store });
  return { raiz, store, destruir };
}

function preencherFormulario(raiz, { cliente, competencia }) {
  const campoCliente = raiz.querySelector('#ingestao-cliente');
  const campoCompetencia = raiz.querySelector('#ingestao-competencia');
  campoCliente.value = cliente;
  campoCliente.dispatchEvent(new Event('input', { bubbles: true }));
  campoCompetencia.value = competencia;
  campoCompetencia.dispatchEvent(new Event('input', { bubbles: true }));
}

function submeter(raiz) {
  const form = raiz.querySelector('form');
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

describe('views/IngestaoLoteView.js -- renderização inicial', () => {
  it('renderiza título, campos do formulário e botão desabilitado sem dados', () => {
    const { raiz, destruir } = montarView({ ingerirDocumentosLote: async () => ({}) });
    try {
      assertTrue(raiz.textContent.includes('Ingestão de documentos'));
      assertTrue(raiz.querySelector('#ingestao-cliente') !== null);
      assertTrue(raiz.querySelector('#ingestao-competencia') !== null);
      const botao = raiz.querySelector('button[type="submit"]');
      assertTrue(botao !== null);
      assertTrue(botao.disabled, 'botao deveria comecar desabilitado sem cliente/competencia preenchidos');
    } finally {
      destruir();
      raiz.remove();
    }
  });
});

describe('views/IngestaoLoteView.js -- submissão com sucesso', () => {
  it('chama apiClient.ingerirDocumentosLote com os valores do formulário e mostra o resumo formatado', async () => {
    let chamadaCom = null;
    const apiClient = {
      ingerirDocumentosLote: async (_sujeito, params) => {
        chamadaCom = params;
        return {
          cliente_id: params.clienteId,
          competencia_base: params.competenciaBase,
          anexos_encontrados: 5,
          documentos_ingeridos: 3,
          documentos_ja_existentes: 2,
          registros_sem_anexo: [],
          total_falhas: 0,
          falhas: [],
        };
      },
    };
    const { raiz, destruir } = montarView(apiClient);
    try {
      preencherFormulario(raiz, { cliente: 'recCLIENTE123', competencia: '2026-09' });
      await new Promise((resolve) => { submeter(raiz); setTimeout(resolve, 0); });

      assertEqual(chamadaCom.clienteId, 'recCLIENTE123');
      assertEqual(chamadaCom.competenciaBase, '2026-09');

      assertTrue(raiz.textContent.includes('3'), 'deveria mostrar 3 documentos ingeridos');
      assertTrue(raiz.textContent.includes('2'), 'deveria mostrar 2 ja existentes');
      assertFalse(raiz.textContent.includes('{'), 'nunca deveria mostrar JSON cru');
    } finally {
      destruir();
      raiz.remove();
    }
  });

  it('mostra indicador de carregamento enquanto a chamada esta pendente', async () => {
    let resolverChamada;
    const apiClient = {
      ingerirDocumentosLote: () => new Promise((resolve) => { resolverChamada = resolve; }),
    };
    const { raiz, destruir } = montarView(apiClient);
    try {
      preencherFormulario(raiz, { cliente: 'recX', competencia: '2026-09' });
      submeter(raiz);
      // o botao some com o formulario inteiro (render sincrono apos submit) e o esqueleto de carregamento aparece
      assertTrue(raiz.querySelector('[aria-busy="true"]') !== null, 'deveria mostrar algum estado aria-busy="true"');
      resolverChamada({
        cliente_id: 'recX', competencia_base: '2026-09', anexos_encontrados: 0,
        documentos_ingeridos: 0, documentos_ja_existentes: 0, registros_sem_anexo: [], total_falhas: 0, falhas: [],
      });
      await new Promise((resolve) => setTimeout(resolve, 0));
    } finally {
      destruir();
      raiz.remove();
    }
  });
});

describe('views/IngestaoLoteView.js -- tratamento de erro', () => {
  it('erro de permissão mostra o estado "sem permissão", nunca falha silenciosa', async () => {
    const apiClient = {
      ingerirDocumentosLote: async () => { throw new PermissaoNegada('Perfil AUDITOR nao tem permissao (permitido: GESTOR, OPERACIONAL).'); },
    };
    const { raiz, destruir } = montarView(apiClient);
    try {
      preencherFormulario(raiz, { cliente: 'recX', competencia: '2026-09' });
      await new Promise((resolve) => { submeter(raiz); setTimeout(resolve, 0); });
      assertTrue(raiz.textContent.includes('não tem acesso'), `mensagem inesperada: ${raiz.textContent}`);
    } finally {
      destruir();
      raiz.remove();
    }
  });

  it('falha de rede/CSRF mostra mensagem de erro legível, nunca quebra a tela', async () => {
    const apiClient = {
      ingerirDocumentosLote: async () => { throw new FalhaSegurancaRequisicao(); },
    };
    const { raiz, destruir } = montarView(apiClient);
    try {
      preencherFormulario(raiz, { cliente: 'recX', competencia: '2026-09' });
      await new Promise((resolve) => { submeter(raiz); setTimeout(resolve, 0); });
      assertTrue(raiz.textContent.includes('Recarregue a página'), `mensagem inesperada: ${raiz.textContent}`);
    } finally {
      destruir();
      raiz.remove();
    }
  });
});
