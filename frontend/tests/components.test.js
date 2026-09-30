/**
 * Testes de renderizacao real de DOM (rodam no browser -- nao
 * precisam de jsdom) para: renderizacao do resumo, identidade visual,
 * colunas da esteira, cartoes, filtros, detalhe do documento, detalhe
 * do lote, carregando, vazio, erro, sem permissao (item 12).
 */
import { describe, it, assertEqual, assertTrue } from './test-harness.js';
import { ResumoCards } from '../src/components/ResumoCards.js';
import { DocumentoCard } from '../src/components/DocumentoCard.js';
import { EsteiraColuna } from '../src/components/EsteiraColuna.js';
import { EsteiraBoard } from '../src/components/EsteiraBoard.js';
import { Filtros } from '../src/components/Filtros.js';
import { Sidebar } from '../src/components/Sidebar.js';
import { Header } from '../src/components/Header.js';
import { PainelDetalheDocumento } from '../src/components/PainelDetalheDocumento.js';
import { PainelDetalheLote } from '../src/components/PainelDetalheLote.js';
import {
  estadoCarregando, estadoVazio, estadoNenhumaOcorrencia, estadoErro, estadoServicoIndisponivel, estadoSemPermissao,
} from '../src/components/EstadosUI.js';

const RESUMO_EXEMPLO = {
  total_documentos: 15, total_por_etapa: { REGISTRO: 3 }, total_por_situacao: { EM_PROCESSAMENTO: 2, EM_REVISAO: 1, ERRO: 1, PRONTO: 0, CONCLUIDO: 4 },
  total_bloqueados: 1, total_com_acao_humana: 10, total_em_erro: 1, total_parados_acima_do_limite: 2,
  limite_parado_segundos: 86400, lotes_recebidos_hoje: 1, tempo_medio_na_etapa_segundos: 5000, documento_mais_antigo_pendente: null,
};

const DOC_EXEMPLO = {
  documento_id: 'doc-teste-1', nome_original: 'Holerite Teste.pdf', lote_id: 'lote-xyz', origem: 'upload_manual',
  etapa_atual: 'CLASSIFICACAO', situacao: 'BLOQUEADO',
  motivo_bloqueio: { codigo: 'CPF_ILEGIVEL', descricao: 'CPF ilegível', detalhe_tecnico: null, resolvivel_automaticamente: false },
  proxima_acao: { acao: 'Resolver bloqueio', tipo: 'HUMANA', prazo: null, responsavel: null },
  tempo_na_etapa_segundos: 3600, ultimo_evento: { evento: 'ESTEIRA_BLOQUEIO_REGISTRADO', timestamp: '2026-01-01T10:00:00.000Z', correlation_id: 'c1' },
  recebido_em: '2026-01-01T08:00:00.000Z', atualizado_em: '2026-01-01T10:00:00.000Z', rastreado_pela_esteira: true,
};

describe('components/ResumoCards.js -- renderização do resumo', () => {
  it('renderiza os 9 cartões pedidos, com os valores certos', () => {
    const node = ResumoCards(RESUMO_EXEMPLO, { recebidosHoje: 7 });
    const cartoes = node.querySelectorAll('.cartao-resumo');
    assertEqual(cartoes.length, 9);
    const valores = [...cartoes].map((c) => c.querySelector('.valor').textContent);
    assertTrue(valores.includes('15')); // total
    assertTrue(valores.includes('7')); // recebidos hoje
    assertTrue(valores.includes('1')); // bloqueados
    assertTrue(valores.includes('10')); // acao humana
  });

  it('cartao clicavel dispara onSelecionar com a chave certa', () => {
    let chaveClicada = null;
    const node = ResumoCards(RESUMO_EXEMPLO, { onSelecionar: (chave) => { chaveClicada = chave; } });
    node.querySelector('.cartao-resumo.clicavel').click();
    assertTrue(chaveClicada != null);
  });
});

describe('components/DocumentoCard.js -- cartões', () => {
  it('mostra nome, origem, lote, situacao, tempo, motivo de bloqueio e proxima acao', () => {
    const node = DocumentoCard(DOC_EXEMPLO, { layout: 'linha' });
    const texto = node.textContent;
    assertTrue(texto.includes('Holerite Teste.pdf'));
    assertTrue(texto.includes('upload_manual'));
    assertTrue(texto.includes('lote-xyz'));
    assertTrue(texto.includes('Bloqueado'));
    assertTrue(texto.includes('CPF ilegível'));
    assertTrue(texto.includes('Precisa de você'));
  });

  it('documento bloqueado e marcado como prioritario', () => {
    const node = DocumentoCard(DOC_EXEMPLO, { layout: 'linha' });
    assertTrue(node.className.includes('prioritario'));
  });

  it('clicar no cartao chama onAbrir com o documento_id', () => {
    let idAberto = null;
    const node = DocumentoCard(DOC_EXEMPLO, { layout: 'linha', onAbrir: (id) => { idAberto = id; } });
    node.click();
    assertEqual(idAberto, 'doc-teste-1');
  });

  it('nunca renderiza a string "undefined" quando origem/lote estao ausentes', () => {
    const semOrigem = { ...DOC_EXEMPLO, origem: null, lote_id: null };
    const node = DocumentoCard(semOrigem, { layout: 'linha' });
    assertTrue(!node.textContent.includes('undefined'));
  });
});

describe('components/EsteiraColuna.js e EsteiraBoard.js -- colunas da esteira', () => {
  it('coluna mostra quantidade, bloqueados, acao humana e tempo medio', () => {
    const node = EsteiraColuna('CLASSIFICACAO', [DOC_EXEMPLO]);
    assertEqual(node.querySelector('.esteira-coluna-contagem').textContent, '1');
    assertTrue(node.textContent.includes('Classificação'));
  });

  it('coluna vazia mostra mensagem, nao quebra', () => {
    const node = EsteiraColuna('AUDITORIA', []);
    assertTrue(node.textContent.includes('Nenhum documento nesta etapa'));
  });

  it('documentos prioritarios aparecem primeiro na coluna', () => {
    const normal = { ...DOC_EXEMPLO, documento_id: 'normal', situacao: 'AGUARDANDO', motivo_bloqueio: null, tempo_na_etapa_segundos: 60 };
    const node = EsteiraColuna('CLASSIFICACAO', [normal, DOC_EXEMPLO]);
    const primeiro = node.querySelector('.cartao-documento');
    assertTrue(primeiro.dataset.documentoId === 'doc-teste-1');
  });

  it('EsteiraBoard em largura desktop usa kanban (10 colunas)', () => {
    const node = EsteiraBoard([DOC_EXEMPLO], { larguraViewport: 1280 });
    assertEqual(node.className, 'rolagem-horizontal');
    assertEqual(node.querySelectorAll('.esteira-coluna').length, 10);
  });

  it('EsteiraBoard em largura mobile usa lista + seletor de etapa (item 11)', () => {
    const node = EsteiraBoard([DOC_EXEMPLO], { larguraViewport: 375 });
    assertTrue(!!node.querySelector('.esteira-seletor-mobile'));
    assertTrue(!node.querySelector('.rolagem-horizontal'));
  });

  it('documentos nao rastreados pela esteira nunca aparecem no quadro', () => {
    const legado = { ...DOC_EXEMPLO, documento_id: 'legado', rastreado_pela_esteira: false, etapa_atual: null };
    const node = EsteiraBoard([DOC_EXEMPLO, legado], { larguraViewport: 1280 });
    assertTrue(!node.querySelector('[data-documento-id="legado"]'));
  });
});

describe('components/Filtros.js -- filtros', () => {
  it('renderiza todos os campos pedidos: etapa, situacao, origem, lote, bloqueado, acao humana, periodo, tempo minimo, busca', () => {
    const node = Filtros({}, { origens: ['upload_manual'], lotes: ['lote-1'], onMudar: () => {}, onLimpar: () => {} });
    assertTrue(!!node.querySelector('#filtro-busca'));
    assertTrue(!!node.querySelector('#filtro-etapa'));
    assertTrue(!!node.querySelector('#filtro-situacao'));
    assertTrue(!!node.querySelector('#filtro-origem'));
    assertTrue(!!node.querySelector('#filtro-lote_id'));
    assertTrue(!!node.querySelector('#filtro-bloqueado'));
    assertTrue(!!node.querySelector('#filtro-acao-humana'));
    assertTrue(!!node.querySelector('#filtro-recebido-de'));
    assertTrue(!!node.querySelector('#filtro-recebido-ate'));
    assertTrue(!!node.querySelector('#filtro-tempo-parado'));
  });

  it('mudar a busca chama onMudar com o valor certo, preservando os demais filtros', () => {
    let recebido = null;
    const node = Filtros({ etapa: 'REGISTRO' }, { onMudar: (v) => { recebido = v; }, onLimpar: () => {} });
    const input = node.querySelector('#filtro-busca');
    input.value = 'holerite';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    assertEqual(recebido.busca, 'holerite');
    assertEqual(recebido.etapa, 'REGISTRO');
  });

  it('botao limpar chama onLimpar', () => {
    let limpou = false;
    const node = Filtros({}, { onMudar: () => {}, onLimpar: () => { limpou = true; } });
    node.querySelector('.filtros-acao-limpar').click();
    assertTrue(limpou);
  });
});

describe('components/PainelDetalheDocumento.js e PainelDetalheLote.js', () => {
  it('painel de documento mostra todos os campos pedidos', () => {
    const node = PainelDetalheDocumento(DOC_EXEMPLO, { historico: { status: 'carregando' }, onFechar: () => {} });
    const texto = node.textContent;
    assertTrue(texto.includes('Holerite Teste.pdf'));
    assertTrue(texto.includes('upload_manual'));
    assertTrue(texto.includes('Classificação'));
    assertTrue(texto.includes('Bloqueado'));
    assertTrue(texto.includes('CPF ilegível'));
  });

  it('painel de documento com historico "sem-permissao" mostra o estado certo', () => {
    const node = PainelDetalheDocumento(DOC_EXEMPLO, { historico: { status: 'sem-permissao', perfilAtual: 'OPERACIONAL' }, onFechar: () => {} });
    assertTrue(!!node.querySelector('.estado-sem-permissao'));
  });

  it('painel de documento com historico carregado mostra a linha do tempo', () => {
    const historico = { status: 'ok', dados: { eventos: [{ evento: 'DOCUMENTO_RECEBIDO', timestamp: '2026-01-01T08:00:00.000Z', correlation_id: 'c1' }] } };
    const node = PainelDetalheDocumento(DOC_EXEMPLO, { historico, onFechar: () => {} });
    assertTrue(node.textContent.includes('DOCUMENTO_RECEBIDO'));
  });

  it('botao fechar do painel de documento chama onFechar', () => {
    let fechou = false;
    const node = PainelDetalheDocumento(DOC_EXEMPLO, { historico: { status: 'carregando' }, onFechar: () => { fechou = true; } });
    node.querySelector('.painel-fechar').click();
    assertTrue(fechou);
  });

  it('painel de lote mostra origem, quantidade e documentos do lote', () => {
    const lote = { lote_id: 'lote-xyz', origem: 'upload_manual', recebido_em: '2026-01-01T08:00:00.000Z', quantidade_arquivos: 3, situacao: 'CONCLUIDO', correlation_id: 'c1', criado_em: '2026-01-01T08:00:00.000Z', atualizado_em: '2026-01-01T09:00:00.000Z', metadados: {} };
    const node = PainelDetalheLote(lote, { documentos: { status: 'ok', dados: [DOC_EXEMPLO] }, onFechar: () => {}, onAbrirDocumento: () => {} });
    assertTrue(node.textContent.includes('lote-xyz'));
    assertTrue(node.textContent.includes('upload_manual'));
    assertTrue(node.textContent.includes('Holerite Teste.pdf'));
  });
});

describe('components/EstadosUI.js -- carregando, vazio, erro, sem permissão', () => {
  it('estadoCarregando marca aria-busy', () => {
    const node = estadoCarregando();
    assertEqual(node.getAttribute('aria-busy'), 'true');
  });

  it('estadoVazio mostra titulo e descricao', () => {
    const node = estadoVazio({ titulo: 'Nada aqui', descricao: 'explicação' });
    assertTrue(node.textContent.includes('Nada aqui'));
    assertTrue(node.textContent.includes('explicação'));
  });

  it('estadoNenhumaOcorrencia menciona os filtros', () => {
    const node = estadoNenhumaOcorrencia({ contexto: 'os filtros aplicados' });
    assertTrue(node.textContent.includes('Nenhuma ocorrência encontrada'));
  });

  it('estadoErro mostra botao de tentar novamente quando fornecido', () => {
    let tentou = false;
    const node = estadoErro({ aoTentarNovamente: () => { tentou = true; } });
    node.querySelector('button').click();
    assertTrue(tentou);
  });

  it('estadoServicoIndisponivel usa mensagem propria (nao generica de erro)', () => {
    const node = estadoServicoIndisponivel({});
    assertTrue(node.textContent.includes('Serviço indisponível'));
  });

  it('estadoSemPermissao lista os perfis permitidos', () => {
    const node = estadoSemPermissao({ perfilAtual: 'OPERACIONAL', perfisPermitidos: ['GESTOR', 'AUDITOR'] });
    assertTrue(node.textContent.includes('OPERACIONAL'));
    assertTrue(node.textContent.includes('GESTOR'));
    assertTrue(node.textContent.includes('AUDITOR'));
  });
});

describe('identidade visual -- símbolo, versão horizontal, nome e subtítulo do produto', () => {
  it('Sidebar usa o símbolo da marca (assets/brand/magnata-symbol.svg)', () => {
    const node = Sidebar({ rotaAtualId: 'resumo' });
    const img = node.querySelector('.marca-simbolo img');
    assertTrue(img.getAttribute('src').includes('assets/brand/magnata-symbol.svg'));
  });

  it('Header usa a versão horizontal da marca e mostra "Magnata OS" / "Central Documental"', () => {
    const node = Header({ tituloPagina: 'Resumo', perfilAtual: 'GESTOR', atualizando: false, textoUltimaAtualizacao: '', onAtualizar: () => {}, onMudarPerfil: () => {} });
    const logoHorizontal = node.querySelector('.header-logo-horizontal');
    assertTrue(logoHorizontal.getAttribute('src').includes('assets/brand/magnata-logo-horizontal.svg'));
    assertTrue(node.textContent.includes('Magnata OS'));
    assertTrue(node.textContent.includes('Central Documental'));
  });

  it('Header nunca referencia um arquivo de marca fora de assets/brand/ (nunca redesenha/duplica a logo)', () => {
    const node = Header({ tituloPagina: 'Resumo', perfilAtual: 'GESTOR', atualizando: false, textoUltimaAtualizacao: '', onAtualizar: () => {}, onMudarPerfil: () => {} });
    const imgs = [...node.querySelectorAll('img')];
    assertTrue(imgs.length > 0);
    assertTrue(imgs.every((img) => img.getAttribute('src').startsWith('assets/brand/')));
  });

  it('Sidebar mostra os 5 links de navegação com rota ativa marcada', () => {
    const node = Sidebar({ rotaAtualId: 'bloqueios' });
    const ativo = node.querySelector('[aria-current="page"]');
    assertTrue(ativo.getAttribute('href') === '#/bloqueios');
  });
});
