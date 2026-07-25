/**
 * Painel de detalhe do lote (item 7 do pedido).
 */
import { h } from '../utils/dom.js';
import { icon } from '../utils/icons.js';
import { rotuloSituacao, formatarDataHora } from '../utils/format.js';
import { DocumentoCard } from './DocumentoCard.js';
import { estadoCarregando, estadoVazio } from './EstadosUI.js';

function linha(rotulo, valor) {
  return h('div', { className: 'painel-linha' }, [h('span', { className: 'rotulo' }, rotulo), h('span', { className: 'valor' }, valor)]);
}

/**
 * @param {import('../api/contracts.js').LoteResponse} lote
 * @param {{documentos: {status:string, dados?:Array}, onFechar:()=>void, onAbrirDocumento:(id:string)=>void}} opcoes
 */
export function PainelDetalheLote(lote, opcoes) {
  const { documentos, onFechar, onAbrirDocumento } = opcoes;

  let blocoDocumentos;
  if (documentos.status === 'carregando') {
    blocoDocumentos = estadoCarregando({ linhas: 3 });
  } else if (!documentos.dados || !documentos.dados.length) {
    blocoDocumentos = estadoVazio({ titulo: 'Nenhum documento encontrado para este lote' });
  } else {
    blocoDocumentos = h('div', { className: 'lista-cartoes' },
      documentos.dados.map((doc) => DocumentoCard(doc, { layout: 'linha', onAbrir: onAbrirDocumento }))
    );
  }

  return h('div', { className: 'painel-sobreposto', onClick: (ev) => { if (ev.target === ev.currentTarget) onFechar(); } }, [
    h('div', { className: 'painel-conteudo', role: 'dialog', 'aria-label': `Detalhes do lote ${lote.lote_id}` }, [
      h('div', { className: 'painel-cabecalho' }, [
        h('div', {}, [
          h('h2', { style: { fontSize: 'var(--fonte-tamanho-lg)', color: 'var(--cor-marinho)' } }, `Lote ${lote.lote_id}`),
          h('span', { className: `badge badge-situacao-${lote.situacao.toLowerCase()} badge-ponto` }, rotuloSituacao(lote.situacao)),
        ]),
        h('button', { className: 'painel-fechar', onClick: onFechar, 'aria-label': 'Fechar painel' }, [icon('fechar', { style: { width: '16px', height: '16px' } })]),
      ]),

      h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Informações do lote'),
        linha('Origem', lote.origem),
        linha('Quantidade de arquivos', String(lote.quantidade_arquivos)),
        linha('Recebido em', formatarDataHora(lote.recebido_em)),
        linha('Criado em', formatarDataHora(lote.criado_em)),
        linha('Atualizado em', formatarDataHora(lote.atualizado_em)),
      ]),

      h('div', { className: 'painel-bloco' }, [
        h('span', { className: 'painel-bloco-titulo' }, 'Documentos deste lote'),
        blocoDocumentos,
      ]),
    ]),
  ]);
}
