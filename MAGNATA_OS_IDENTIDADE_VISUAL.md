# Magnata OS — Identidade Visual

**Status:** preparação da identidade visual, anterior à implementação do
painel da Fase 5. Nenhuma tela foi construída aqui — apenas os assets de
marca e as regras de uso que a Fase 5 vai consumir.

## Arquivo-mestre

`LOGO MAGNATA PDF .pdf` (fornecido pelo usuário) — **logomarca oficial
do Grupo Magnata**: um emblema circular (anel dourado, disco marinho,
estrela de seis pontas entrelaçada dourada) com o lockup textual "GRUPO
MAGNATA" abaixo.

### O PDF original é vetorial

**Sim — confirmado, não é uma imagem rasterizada dentro do PDF.**
Verificação feita em duas camadas independentes:

1. **Estrutura do arquivo:** nenhum `/Image` XObject, nenhum
   `DCTDecode` (JPEG) nem `CCITTFaxDecode` em todo o PDF. O conteúdo da
   página é um único content stream comprimido (`FlateDecode`) contendo
   operadores de desenho vetorial nativos do PDF (`m`/`l`/`c` — moveto/
   lineto/curveto bézier — e preenchimento `k`/`f`, nunca um `Do` de
   XObject de imagem).
2. **Confirmação via PyMuPDF:** `page.get_images()` retorna **0**
   imagens; `page.get_drawings()` retorna **24 objetos vetoriais**
   (paths reais, com curvas de bézier, cores de preenchimento e regras
   de preenchimento explícitas). O texto "GRUPO MAGNATA" já vem
   **convertido em contornos vetoriais** (outline), não como fonte
   embutida — `page.get_fonts()` retorna vazio.

Por ser 100% vetorial, a extração usada aqui (`page.get_svg_image()`,
PyMuPDF/MuPDF) reaproveita os **mesmos paths e curvas originais do PDF**
— nenhuma reconstrução aproximada, nenhuma vetorização automática de
uma imagem rasterizada. **Verificação de fidelidade:** o SVG extraído
foi renderizado de volta a 2160×2160px e comparado pixel a pixel contra
o PDF original renderizado na mesma resolução — diferença máxima de 2
em 255 por canal (ruído de anti-aliasing), **zero pixels com diferença
perceptível**.

## Versões da marca e onde usar cada uma

Todos os arquivos em `frontend/assets/brand/`:

| Arquivo | Conteúdo | Uso recomendado |
|---|---|---|
| `magnata-symbol.svg` | Só o emblema (anel + estrela), sem texto | Menu lateral (colapsado), favicon, avatar/ícone do sistema, telas pequenas, splash screen |
| `magnata-symbol.png` | Mesmo conteúdo, raster 3220×3220px, fundo transparente | Onde SVG não for aceito (ex.: metadados de app, preview de compartilhamento) |
| `magnata-logo.svg` | Lockup completo — emblema + "GRUPO MAGNATA" empilhados, exatamente como no arquivo-mestre | Tela de login, splash/loading, rodapé, materiais institucionais, qualquer espaço vertical generoso |
| `magnata-logo.png` | Mesmo conteúdo, raster 4320×4320px, fundo transparente | Onde SVG não for aceito |
| `magnata-logo-horizontal.svg` | Emblema à esquerda + "GRUPO MAGNATA" à direita, alinhados horizontalmente | **Cabeçalho do painel** (barra superior estreita e larga — o formato vertical não cabe bem nesse espaço) |

Não existe um `magnata-logo-horizontal.png` nesta entrega — se um
adapter/exportador precisar de raster horizontal, gerar a partir do SVG
horizontal (`frontend/assets/brand/magnata-logo-horizontal.svg`) segue
o mesmo processo usado para os outros dois PNGs (ver "Processo de
extração" abaixo), sem precisar reabrir o PDF.

### Composição do lockup horizontal (transparência sobre a decisão)

`magnata-logo-horizontal.svg` **não existe no arquivo-mestre** — foi
**composto** a partir dos dois elementos originais (emblema e
wordmark), cada um **com sua geometria interna 100% preservada**: nenhum
path foi editado, nenhuma letra redesenhada, nenhuma cor alterada. A
única operação aplicada foi **translação + escala uniforme de grupo**
(mover e redimensionar o bloco do wordmark como um todo rígido, mantendo
todas as proporções relativas entre "GRUPO" e "MAGNATA" exatamente como
desenhadas) para posicioná-lo ao lado do emblema. Parâmetros usados:
wordmark escalado para 62% da altura do emblema, com um espaçamento de
respiro entre os dois blocos — valores documentados aqui para que
possam ser ajustados no futuro sem precisar reabrir o PDF original.

## Preservação do desenho original

- **Proporções:** inalteradas — todo path usa as coordenadas exatas do
  PDF; nenhuma versão aplica stretch não-uniforme.
- **Cores:** inalteradas — os únicos dois preenchimentos do arquivo
  (dourado e marinho) foram extraídos diretamente dos operadores `k`
  (CMYK) do content stream, convertidos para sRGB pela própria engine
  PDF (MuPDF), não estimados visualmente.
- **Tipografia:** o texto já estava desenhado como contorno vetorial no
  arquivo-mestre (prática comum em arquivos de logo, para não depender
  de a fonte estar instalada) — reaproveitado tal como está, nenhuma
  letra foi re-desenhada ou substituída por uma fonte do sistema.
- **Margens de segurança:** o lockup completo (`magnata-logo.svg`)
  mantém a área de desenho 1080×1080 original, com as mesmas margens
  internas do arquivo-mestre. O símbolo isolado (`magnata-symbol.svg`)
  recebeu uma margem de recorte adicional (ver "Áreas de proteção"
  abaixo) — não faz parte do desenho, é só a "janela" (`viewBox`) de
  recorte ao redor dele.
- **Transparência de fundo:** todos os SVGs não têm nenhum retângulo de
  fundo — fundo transparente nativo. Os dois PNGs foram renderizados
  com canal alfa (`RGBA`), confirmado pixel a pixel (canto = alfa 0,
  centro = alfa 255).

Nenhuma marca foi redesenhada, estilizada ou re-vetorizada a partir de
um raster — ver seção "O PDF original é vetorial" acima.

## Tamanhos mínimos

| Versão | Tamanho mínimo recomendado | Observação |
|---|---|---|
| `magnata-symbol` | 24px (digital) | Abaixo de ~32px o entrelaçamento fino da estrela (os pequenos triângulos de sobreposição) começa a perder nitidez na tela; em favicon de 16px o símbolo ainda se reconhece como "emblema dourado/marinho", mas o detalhe do entrelaçamento se perde — aceitável só para favicon, não para uso de marca com destaque. |
| `magnata-logo` (vertical) | 140px de largura | Abaixo disso a linha "GRUPO" (proporcionalmente pequena mesmo no desenho original) perde legibilidade antes da palavra "MAGNATA". |
| `magnata-logo-horizontal` | 200px de largura | Formato mais largo que alto — precisa de mais espaço horizontal disponível que o vertical para manter a mesma legibilidade de texto. |

## Áreas de proteção (clear space)

Regra derivada do próprio desenho, não arbitrária: a **espessura do
anel dourado** (≈4,5% do diâmetro do símbolo — na arte mestre, ≈32
unidades num símbolo de ≈726 unidades de diâmetro) é a área de proteção
mínima ao redor de **qualquer** versão da marca — nenhum outro elemento
(texto, ícone, borda de card, outra imagem) deve invadir esse espaço.

- `magnata-symbol.svg` já foi exportado com essa margem embutida no
  `viewBox` (≈5,5% de respiro ao redor do emblema) — colável direto
  sem cálculo adicional.
- `magnata-logo.svg` e `magnata-logo-horizontal.svg`: aplicar a mesma
  regra proporcional (≈4,5% da maior dimensão do lockup) como respiro
  externo mínimo ao posicionar sobre qualquer fundo ou ao lado de outro
  elemento de UI.

## Cores extraídas

Únicas duas cores de toda a logomarca (nenhuma cor foi adicionada nem
estimada — ambas lidas diretamente dos operadores CMYK do PDF):

| | Hex (sRGB) | RGB | CMYK original (PDF) | Uso na marca |
|---|---|---|---|---|
| 🟡 Dourado | `#FDC82A` | `rgb(253, 200, 42)` | `C 0.4% M 21.7% Y 92.5% K 0.2%` | Anel externo, estrela de seis pontas |
| 🔵 Marinho | `#041B36` | `rgb(4, 27, 54)` | `C 98.5% M 84.1% Y 46.8% K 59.2%` | Disco de fundo do emblema, wordmark "GRUPO MAGNATA" |

### Uso institucional no painel (recomendação para a Fase 5)

Estas são as únicas cores COM origem na marca — qualquer outra cor
usada na interface (cinzas neutros, fundo, texto secundário) é uma
escolha de UI, não uma cor institucional, e deve ser tratada como
neutra/complementar, nunca confundida com identidade de marca:

- **Marinho (`#041B36`)** — texto de alta ênfase, cabeçalho, ícones
  ativos/selecionados, superfícies escuras pontuais. Nunca como cor de
  fundo de página inteira (perderia o contraste que dá ao dourado seu
  papel de destaque).
- **Dourado (`#FDC82A`)** — **com moderação**, só para o que precisa
  chamar atenção: botão primário, indicador de pendência/ação humana,
  badge de alerta, estado ativo de navegação. Nunca como cor de texto
  corrido (contraste insuficiente sobre branco) nem como fundo de
  áreas grandes.
- **Fundos neutros** (cinza muito claro / branco) — recomendados para
  a maior parte do painel, visual corporativo moderno, deixando as duas
  cores institucionais reservadas para os pontos que precisam de
  destaque (ver princípio da Fase 3/4: "o que está parado, por que
  parou, quem precisa agir" — o dourado é o candidato natural para
  sinalizar isso visualmente, com moderação).

## Usos proibidos

- Não recolorir o símbolo ou o wordmark para qualquer cor fora da
  tabela acima (incluindo variações de tom/saturação do mesmo dourado
  ou marinho).
- Não distorcer (esticar de forma não-uniforme, inclinar, espelhar).
- Não rotacionar o emblema ou o wordmark.
- Não adicionar sombra, contorno (stroke), brilho, gradiente ou
  qualquer efeito não presente no arquivo-mestre.
- Não separar o anel da estrela nem alterar o entrelaçamento
  (over/under) da estrela de seis pontas.
- Não recompor o wordmark "GRUPO MAGNATA" com uma fonte diferente da
  já desenhada nos contornos originais.
- Não usar uma versão rasterizada em baixa resolução quando a versão
  vetorial (SVG) estiver disponível — os SVGs desta entrega cobrem
  todos os casos de uso do painel.
- Não colocar a marca sobre fundos de baixo contraste (ex.: dourado
  sobre branco/amarelo claro, marinho sobre preto/azul muito escuro).
- Não invadir a área de proteção (ver seção acima) com texto, bordas ou
  outros elementos de UI.
- Não usar o símbolo isolado como substituto do lockup completo em
  contextos que exigem identificação formal da marca (ex.: rodapé de
  documento oficial) — nesses casos, `magnata-logo.svg` (ou a versão
  horizontal) é obrigatório.

## Processo de extração (reprodutibilidade)

1. `PyMuPDF` (`pip install pymupdf`) abre o PDF e confirma ausência de
   imagens raster (`page.get_images()`) e presença de paths vetoriais
   (`page.get_drawings()`, 24 objetos).
2. `page.get_svg_image()` exporta o SVG fiel ao content stream original
   (mesmos paths, mesmas curvas bézier, mesmas cores).
3. Os 24 `<path>` resultantes são particionados em dois grupos por
   índice (identificados por cor de preenchimento + posição/bounding
   box via `get_drawings()`): **símbolo** (anel + estrela, 10 paths) e
   **wordmark** (texto contornado, 14 paths).
4. `magnata-symbol.svg`: grupo símbolo, `viewBox` recortado ao bounding
   box do grupo + margem de proteção (ver seção própria) — nenhum path
   modificado.
5. `magnata-logo.svg`: os 24 paths na ordem de pintura original,
   `viewBox="0 0 1080 1080"` idêntico ao artboard do PDF.
6. `magnata-logo-horizontal.svg`: os dois grupos, cada um dentro de um
   `<g transform="...">` de translação (símbolo) ou translação+escala
   uniforme (wordmark) — nenhum path individual tocado, só reposicionado
   como bloco rígido (ver "Composição do lockup horizontal" acima).
7. PNGs renderizados via `page.get_pixmap(alpha=True)` a partir dos
   próprios SVGs, zoom 4x (`magnata-logo.png` 4320×4320px,
   `magnata-symbol.png` 3220×3220px) — fidelidade confirmada por
   comparação de pixel com o PDF original (ver seção "O PDF original é
   vetorial").

## O que esta preparação explicitamente NÃO faz

Não implementa nenhuma tela do painel da Fase 5 (CSS, componentes,
layout) — só prepara os assets e as regras de uso que a implementação
visual vai consumir. Não altera `app.py`. Não acessa nenhum serviço
real (Postgres/S3/Airtable). Não faz deploy.
