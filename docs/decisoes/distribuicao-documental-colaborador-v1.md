# Distribuição Documental Genérica V1

## Objetivo

Fechar a capacidade genérica:

```
Documento(s) → Preview → Autorização → Obrigação (opcional) → PlanoDisparo → Envelope → AcaoEnvio PENDING
```

para **qualquer** `Documento` canônico do Módulo 01 (holerite, folha de
ponto, contrato, EPI, NR, rescisão, comprovante, etc.), sem transporte
real. Holerite + Folha de Ponto é apenas **um preset** desta capacidade
(`preset_id`/`politica_agrupamento`), nunca uma arquitetura própria — o
núcleo (`wiring_distribuicao_documental_shadow.py`) nunca testa
`tipo_documento` contra um valor específico.

## Decisão arquitetural

- `OrdemDistribuicaoDocumental` (imutável) é o contrato de entrada: 1..N
  documentos, `funcionario_id`, `destinatario`, `canal`, `preset_id`,
  `tipo_documento`, `exigir_assinatura`, `exigir_comprovante`,
  `politica_agrupamento`, `mensagem_texto`.
- `event_id` é derivado deterministicamente da serialização canônica
  completa da Ordem (nunca timestamp/UUID). `preview_id` é
  **exclusivamente** o produzido por `montar_preview_comunicacao` sobre
  o texto/composição exatos apresentados ao humano — nunca um segundo
  conceito de "preview_id da Ordem".
- `politica_agrupamento` tem efeito operacional real: é validada e
  mapeada para `PreferenciaComposicao` já existente
  (`_validar_e_mapear_politica_agrupamento`), fail-closed para qualquer
  combinação fora da tabela V1 (`(1, 'UNITARIO')`,
  `(2, 'AGRUPADO_1_LINK')` com `exigir_assinatura=True`).
- `PortaObrigacaoAssinatura.criar_ou_recuperar` foi pluralizada
  (`arquivo_record_id: str` → `arquivo_record_ids: Tuple[str, ...]`) —
  mudança de assinatura sem impacto em produção (nenhum caller real
  hoje; único consumidor real é `wiring_assinatura_comunicacao_shadow.py`,
  shadow, ajustado para passar `(id,)`).
- `HOLERITE_FOLHA_PONTO` só aparece em
  `adapters/obrigacao_assinatura_legado_http.py`
  (`TIPO_DOCUMENTO_PACOTE_LEGADO_2`) — é o único ponto que sabe que o
  motor legado agrupa exatamente 2 documentos sob 1 link para esse
  `tipo_documento`. Núcleo genérico nunca referencia esse valor.
- Ramo com assinatura: materializa cada documento via
  `MaterializadorArquivoLegado` (PR #172, inalterado) apenas quando
  `exigir_assinatura=True` — sem assinatura, nenhuma materialização em
  `TABLE_ARQUIVOS` é necessária (mesmo padrão das rotas legadas
  `whatsapp_enviar_documento`/`whatsapp_enviar_texto`, que já despacham
  mídia sem depender do motor de assinatura).
- Ordem dos efeitos do ramo com assinatura (obrigatória, fail-closed):
  resolver documentos → materializar → derivar `event_id` →
  `A = sha256(event_id|"assinatura_unica")` → consultar obrigação por
  `A` (somente leitura) → resolver link (recuperado ou token CSPRNG
  novo, só em memória) → montar preview exato → autorizar → **só
  então** criar/recuperar obrigação sob `A` → `PlanoDisparo` →
  `criar_registro_acao_plano` (com `acao_execucao_id` substituído por
  `A`) → envelope → ação PENDING. Nenhuma obrigação é criada antes da
  autorização do preview exato.
- Idempotência de replay: o link recuperado é sempre reconstruído no
  mesmo formato relativo (`/assinatura/{token}`) usado na criação —
  nunca a URL canônica devolvida por `ObrigacaoAssinatura.link`, que
  pode ter prefixo de domínio diferente e quebraria a estabilidade do
  texto entre replays.

## Correções da Ultrareview (ciclo único, antes do gate de publicação)

- **HIGH corrigido:** a extração do token a partir de `ObrigacaoAssinatura.link`
  (`obrigacao_existente.link.rsplit("/", 1)[-1]`) era fail-open — um link
  vazio, terminando em `/`, ou malformado nunca lançava exceção,
  produzindo silenciosamente um "token" inválido. Corrigido com
  `_extrair_token_do_link`/`_RE_TOKEN_RESERVADO`, reutilizando o mesmo
  formato de `_validar_reserva_assinatura` (app.py) — qualquer
  divergência de formato agora levanta `LinkObrigacaoAssinaturaMalformado`
  fail-closed, antes de qualquer autorização/obrigação.
- **MEDIUM corrigido:** corrida real entre 2 processos (TOCTOU entre
  `consultar_por_correlacao` e `criar_ou_recuperar` sob o mesmo `A`)
  causava exceção não tratada quando o vencedor já tinha criado a
  obrigação com um token diferente. Corrigido com retry de até 2
  tentativas em `_montar_ramo_com_assinatura`: a tentativa perdida nunca
  reaproveita seu próprio preview/token — refaz a consulta, que agora
  encontra o vencedor, e reconstrói preview/autorização com o link real.
- **MEDIUM corrigido (lacuna de teste):** `test_wiring_distribuicao_documental_shadow.py`
  ganhou casos para link malformado, corrida real com autocura, e ordem
  dos documentos alterando a identidade da Ordem.
- **Risco residual aceito, registrado, não corrigido nesta V1 (LOW):**
  `_extrair_token_do_link` valida só o FORMATO do último segmento de
  path, não a rota/domínio que o precede. Fechar isso por completo
  exigiria expor o token explicitamente em `ObrigacaoAssinatura`/
  `PortaObrigacaoAssinatura` (mudança de contrato maior, sugerida pela
  Ultrareview, fora de escopo desta correção pontual).
- **Risco residual aceito, registrado (LOW):** materialização parcial de
  N=2 (primeiro documento materializado, segundo falha) deixa um
  registro sem obrigação associada nesta tentativa — aceitável porque o
  materializador (PR #172) já é idempotente por `(hash_sha256,
  funcionario_id)`, reaproveitado no replay seguinte, nunca duplicado.

## O que NÃO foi feito nesta V1 (gate remanescente)

Agrupar 3+ documentos sob uma obrigação, ou 2 documentos com
`tipo_documento` diferente de `HOLERITE_FOLHA_PONTO`, exigiria
generalizar `_gerar_pacote_assinatura_holerite_ponto` dentro de
`app.py` (arquivo protegido, CLAUDE.md §7) — fora de escopo, registrado
como gate material, não implementado.

## Dívida técnica registrada, não corrigida nesta V1

`app.py` ainda contém 2 sites (fluxo de Kit de Admissão e de Folha de
Ponto) que reimplementam ad-hoc, via POST cru ao Airtable, o mesmo
padrão que `MaterializadorArquivoLegadoAirtable` já encapsula — nenhum
dos dois foi migrado para o materializador novo. Fora de escopo desta
V1 (exigiria tocar `app.py`).

## Arquivos

Criados: `magnata_os/orquestrador/wiring_distribuicao_documental_shadow.py`,
`magnata_os/orquestrador/distribuir_documento_v1.py`,
`test_wiring_distribuicao_documental_shadow.py`,
`test_distribuir_documento_v1.py`.

Editados: `magnata_os/orquestrador/obrigacao_assinatura.py`,
`magnata_os/orquestrador/adapters/obrigacao_assinatura_legado_http.py`,
`magnata_os/orquestrador/wiring_assinatura_comunicacao_shadow.py`,
`test_obrigacao_assinatura.py`, `test_adapter_obrigacao_assinatura_legado_http.py`,
`test_wiring_assinatura_comunicacao_shadow.py`, `.magnata/patterns.sh`,
`.githooks/pre-commit`.

Não tocados: `app.py`, migrations, transporte Evolution.
