/**
 * Cabecalho (item 2 do pedido) -- identidade Magnata OS (versao
 * horizontal da marca em telas >= 640px, simbolo isolado abaixo disso),
 * texto "Magnata OS" + subtitulo "Central Documental", titulo da
 * pagina atual, atualizacao dos dados e identificacao do perfil atual
 * (mock visual -- sem autenticacao real, ver autorizacao.js Perfil).
 */
import { h } from '../utils/dom.js';
import { icon } from '../utils/icons.js';
import { Perfil } from '../api/autorizacao.js';
import { rotuloPerfil } from '../utils/format.js';

/**
 * @param {{tituloPagina:string, perfilAtual:string, atualizando:boolean,
 *   textoUltimaAtualizacao:string, onAtualizar:()=>void, onMudarPerfil:(perfil:string)=>void}} opcoes
 */
export function Header(opcoes) {
  const { tituloPagina, perfilAtual, atualizando, textoUltimaAtualizacao, onAtualizar, onMudarPerfil } = opcoes;

  return h('header', { className: 'app-header' }, [
    h('div', { className: 'header-esquerda' }, [
      h('img', { className: 'header-logo-horizontal', src: 'assets/brand/magnata-logo-horizontal.svg', alt: 'Grupo Magnata' }),
      h('img', { className: 'header-logo-simbolo', src: 'assets/brand/magnata-symbol.svg', alt: 'Grupo Magnata' }),
      h('div', { className: 'header-separador' }),
      h('div', { className: 'header-titulos' }, [
        h('span', { className: 'produto-nome' }, 'Magnata OS'),
        h('span', { className: 'produto-subtitulo' }, 'Central Documental'),
      ]),
      h('span', { className: 'somente-leitor-tela' }, tituloPagina ? `Página atual: ${tituloPagina}` : ''),
    ]),
    h('div', { className: 'header-direita' }, [
      textoUltimaAtualizacao ? h('span', { className: 'selo-atualizacao' }, textoUltimaAtualizacao) : null,
      h('button', {
        className: 'btn-atualizar', onClick: onAtualizar, disabled: atualizando,
        'aria-label': 'Atualizar dados',
      }, [
        icon('atualizar', { className: atualizando ? 'icone girando' : 'icone' }),
        h('span', {}, atualizando ? 'Atualizando…' : 'Atualizar'),
      ]),
      h('div', { className: 'selecao-perfil' }, [
        h('label', { htmlFor: 'seletor-perfil' }, 'Perfil'),
        h('select', {
          id: 'seletor-perfil',
          value: perfilAtual,
          onChange: (ev) => onMudarPerfil && onMudarPerfil(ev.target.value),
        }, Object.values(Perfil).map((p) => h('option', { value: p, selected: p === perfilAtual }, rotuloPerfil(p)))),
      ]),
    ]),
  ]);
}
