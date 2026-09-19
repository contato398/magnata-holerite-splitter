# Incremento Vertical: Prestação de Contas -> Distribuição Documental Genérica -> PENDING V1

## Objetivo

Fechar o elo que faltava entre a Prestação de Contas
(`magnata_os/classificacao/`) e o núcleo genérico de Distribuição
Documental (`magnata_os/orquestrador/wiring_distribuicao_documental_
shadow.py`, PR #173, já mergeado e intocado por esta correção):

```
NecessidadeDocumentoPrestacao -> ResultadoAquisicaoPorNecessidade
  -> Documento(s) + colaborador -> preset_id -> OrdemDistribuicaoDocumental
  -> materializar_distribuicao_documental_shadow -> Preview -> Autorização
  -> Obrigação opcional -> PlanoDisparo -> Envelope -> AcaoEnvio PENDING
```

Sempre sem transporte real.

## Decisão arquitetural

- **Direção de dependência**: `magnata_os/orquestrador/` importa de
  `magnata_os/classificacao/`, nunca o inverso -- mesmo padrão já usado
  por `wiring_prestacao_comunicacao_shadow.py`/`wiring_prestacao_
  orquestrador_postgres_shadow.py`. `wiring_distribuicao_documental_
  shadow.py` continua **zero alterado** e **zero acoplado** a
  Prestação, conforme seu próprio docstring e o ADR
  `distribuicao-documental-colaborador-v1.md`.
- **Presets `preset_id -> política`, nunca `tipo_documento ->
  política`** (`politica_preset_distribuicao_documental.py`): 3 presets
  V1 (`DOCUMENTO_UNITARIO_SEM_ASSINATURA`, `DOCUMENTO_UNITARIO_COM_
  ASSINATURA`, `PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA`), indexados
  só por `preset_id`. `tipo_documento` permanece dado opaco da Ordem,
  repassado só até o adapter legado
  (`TIPO_DOCUMENTO_PACOTE_LEGADO_2='HOLERITE_FOLHA_PONTO'`, inalterado).
  Um `tipo_documento` novo (EPI, NR01, CONTRATO, COMUNICADO, ...) usa
  qualquer preset compatível sem qualquer alteração de código --
  provado por `test_tipos_documentais_arbitrarios_usam_mesmo_preset_
  sem_alteracao_de_codigo` (parametrizado) e `test_mesmo_tipo_
  documento_usa_presets_diferentes`.
- **Correlação colaborador<->documento**: `ResultadoAquisicaoPorNecessidade`
  (promovido de privado `_ResultadoAquisicaoPorNecessidade` para
  público, mesma assinatura/shape/semântica -- única mudança
  contratual desta correção, declarada explicitamente aqui) já carrega
  `necessidade.colaborador`/`documento_id`/`hash_sha256` intactos,
  produzido por `adquirir_por_necessidades` (idem, promovida de
  `_adquirir_por_necessidades`). `executar_ciclo_prestacao_persistente`
  permanece **zero alterado** -- a correlação nunca precisou ser
  reconstruída nem enriquecida, só reexposta. Único caller de produção
  do símbolo promovido (`composicao_ciclo_persistente_prestacao.py`,
  mesmo módulo) e os 3 pontos de teste que já acessavam o símbolo
  privado foram atualizados para o novo nome público.
- **Wiring novo** (`wiring_prestacao_distribuicao_documental_shadow.py`):
  responsabilidade estrita de montar/repassar -- recebe
  `ResultadoAquisicaoPorNecessidade` (1 ou 2, já preservando
  colaborador), `destinatario` (dependência explícita do chamador),
  `preset_id`, `tipo_documento` (opaco, também explícito do chamador --
  nunca derivado por heurística de quantidade/tipo, o que
  reintroduziria conhecimento de tipo documental fora do adapter
  legado) e `mensagem_texto`; monta `ItemDocumentoOrdem`/
  `OrdemDistribuicaoDocumental` e chama `materializar_distribuicao_
  documental_shadow` (núcleo, sem duplicar nenhuma lógica de resolução/
  materialização/preview/autorização/persistência).
- **Fail-closed de colaborador**: `necessidade.colaborador is None` ->
  `ColaboradorAusenteNaNecessidade`; documentos de colaboradores
  diferentes na mesma Ordem -> `ColaboradorDivergenteEntreDocumentos`.
  Nenhum `funcionario_id` é inferido por heurística/nome.
- **Destinatário**: nesta V1, dependência explícita do chamador --
  este wiring **nunca** resolve telefone/WhatsApp, nunca conhece
  Evolution, não toca `app.py` (arquivo protegido) e não duplica
  `_buscar_funcionario_nome_whatsapp`/`_normalizar_numero_evolution`
  (únicas implementações reais hoje, cruas dentro de `app.py`).
  **A composição de uma fonte real de contato permanece requisito de
  uma etapa posterior, antes de qualquer canário operacional real** --
  este incremento fecha o caminho tecnicamente (Prestação -> Ordem ->
  PENDING), não a capacidade de enviar de fato para um número real.

## Teste Postgres real do núcleo genérico (gap fechado nesta correção)

`test_wiring_distribuicao_documental_shadow_real.py` -- primeiro teste
`_real` do núcleo `wiring_distribuicao_documental_shadow.py` (PR #173
só tinha cobertura por mocks/fakes até esta correção). Reutiliza
exatamente o padrão já estabelecido (`test_repositorio_acoes_execucao_
plano_postgres_real.py`/`test_wiring_prestacao_orquestrador_
persistente_shadow_real.py`): migrations 0001-0004, Postgres efêmero
via `MAGNATA_TEST_POSTGRES_REAL`, real só `RepositorioAutorizacoesGate
Postgres`+`RepositorioAcoesExecucaoPlanoPostgres`, fake/em memória o
resto (`RepositorioDocumentosEmMemoria`/`ArmazenamentoArquivosEmMemoria`),
`materializador=None`/`porta_assinatura=None` (ramo sem assinatura,
zero superfície Airtable adicional).

**Achado real deste teste** (não uma regressão -- uma lacuna de
validação até então nunca exercitada): `autorizacoes_gate.event_id` tem
FK para `execucoes(event_id)` (migration 0002), e o núcleo nunca cria
essa linha -- é responsabilidade de quem ingere o evento original
(fora do escopo deste wiring, que nunca importou `RepositorioExecucoes`).
O teste `_real` precisa semear essa linha antes de chamar o núcleo,
exatamente como `test_repositorio_acoes_execucao_plano_postgres_
real.py` já faz para seus próprios cenários sintéticos -- documentado
explicitamente no teste (`_semear_execucao_se_ausente`). Isso não é uma
correção de código de produção: é a integridade referencial funcionando
como desenhado, agora comprovada contra Postgres real pela primeira
vez.

Validado localmente contra Postgres 16 efêmero (não CI): 80/80 testes
`_real` do orquestrador passam juntos, na ordem exata do job
`postgres-real`, incluindo o novo teste.

## O que NÃO foi feito nesta correção (gate remanescente, fora de escopo)

- Resolução real de telefone/WhatsApp a partir de `colaborador_id` --
  não existe hoje fora de `app.py`/Airtable cru; extração para adapter
  vendor-free é decisão de produto + implementação futura, fora de
  escopo aqui.
- Qualquer alteração em `app.py`, migration, schema, Evolution,
  worker, Render, produção, env/secrets.
- Ativação real de transporte (barreiras já existentes, inalteradas).

## Arquivos

Criados: `magnata_os/orquestrador/politica_preset_distribuicao_
documental.py`, `magnata_os/orquestrador/wiring_prestacao_
distribuicao_documental_shadow.py`, `test_wiring_prestacao_
distribuicao_documental_shadow.py`, `test_wiring_distribuicao_
documental_shadow_real.py`.

Editados (rename de visibilidade, sem mudança de shape):
`magnata_os/classificacao/composicao_ciclo_persistente_prestacao.py`
(`_ResultadoAquisicaoPorNecessidade`->`ResultadoAquisicaoPorNecessidade`,
`_adquirir_por_necessidades`->`adquirir_por_necessidades`),
`test_composicao_ciclo_persistente_prestacao.py` (3 referências
atualizadas), `.github/workflows/magnata-testes.yml` (+1 arquivo no
job `postgres-real`), `.magnata/patterns.sh`, `.githooks/pre-commit`
(entradas nominais).

Não tocados: `app.py`, todas as migrations, `wiring_distribuicao_
documental_shadow.py`, `distribuir_documento_v1.py`,
`ciclo_producao_v1.py`, `adapters/obrigacao_assinatura_legado_http.py`,
`render.yaml`, Evolution, worker.

## Delta Final A-F -- Cliente+Competência -> PENDING (mesma branch)

Fecha o trecho upstream que faltava: `CLIENTE+COMPETÊNCIA` ->
requisitos -> necessidades -> aquisição -> readiness -> pacote -> elo
G-P acima -> PENDING.

- **Extração** (não mudança de contrato): `_descobrir_adquirir_e_
  recalcular_readiness` (privada) reúne os antigos passos 3-7 de
  `executar_ciclo_prestacao_persistente` -- refactor puro, comportamento
  idêntico, verificado pela suíte já existente (56/56 inalterados).
  `executar_ciclo_prestacao_persistente` passa a chamar essa função;
  seu retorno público (`ExecucaoPrestacao`) não muda.
- **Novo (Prestação)**: `resultados_aquisicao_prontos_por_cliente`
  reutiliza a mesma extração para devolver, por (cliente, competência)
  com `pacote.estado == PRONTO`, os `ResultadoAquisicaoPorNecessidade`
  correspondentes -- omite silenciosamente quem não está pronto
  (isolamento por cliente, sem contaminação, já garantido por
  `executar_ciclo_prestacao`/`avaliar_candidatos_ancora`). Não cria
  nem atualiza `ExecucaoPrestacao` -- é só leitura + gate; nunca cria
  um segundo `execucao_id` porque nunca cria nenhum.
- **Novo (Orquestrador)**: `executar_prestacao_ate_distribuicao_
  documental_shadow` + `ParametrosOrdemPrestacao` (dataclass fail-closed
  para campos vazios). Para cada (cliente, competência, resultados)
  pronto, chama `resolver_parametros_ordem` (callback do chamador --
  `destinatario`/`preset_id`/`tipo_documento`/`mensagem_texto` nunca
  inferidos aqui); `None` = fail-closed, zero Ordem para aquele
  cliente. Delega ao elo G-P já staged
  (`materializar_prestacao_distribuicao_documental_shadow`), sem
  duplicar nenhuma lógica de resolução/materialização/preview/
  autorização/persistência.
- **Testes**: `test_wiring_prestacao_ate_distribuicao_documental_
  shadow.py` -- readiness apto produz Ordem até PENDING; readiness
  insuficiente e destinatário ausente produzem zero Ordem (fail-closed);
  isolamento multi-cliente; replay sem duplicação; preset inválido
  propaga sem mascarar; zero transporte (AST); zero `ExecucaoPrestacao`
  criada por este composition root.
- **Não criado**: nenhum executor novo, fila, scheduler, segunda Ordem,
  segundo ciclo de Prestação. `wiring_distribuicao_documental_shadow.py`
  e `ciclo_producao_v1.py` continuam intocados.

### Correção da Ultrareview (ciclo único)

- **MEDIUM corrigido:** o loop de `executar_prestacao_ate_distribuicao_
  documental_shadow` não isolava exceções de DOMÍNIO de 1 cliente
  (`PrestacaoDistribuicaoDocumentalError`/subclasses --
  `ColaboradorAusenteNaNecessidade`, `ColaboradorDivergenteEntreDocumentos`
  -- e `DistribuicaoDocumentalError` do núcleo): um erro de dado de 1
  cliente propagava e impedia N-1 outros clientes prontos e íntegros
  de chegar a PENDING, violando a exigência de isolamento por cliente.
  Corrigido com `try/except` por cliente dentro do loop, registrando o
  evento (`EVENTO_CLIENTE_FALHOU_DISTRIBUICAO_DOCUMENTAL`, `_logger.error`,
  nunca silenciado) e prosseguindo para os demais clientes. Qualquer
  outra exceção (sistêmica -- falha de conexão, bug de programação)
  continua propagando e interrompendo, como antes. Testado por
  `test_erro_de_dominio_de_um_cliente_nao_impede_os_demais`.
- **LOW corrigido (reforço de teste):** `test_multi_cliente_
  isolamento_um_apto_outro_nao` provava menos do que o nome sugeria
  (cliente B nunca tinha candidato de aquisição, então nunca exercitava
  o executor real). Adicionado
  `test_multi_cliente_isolamento_ambos_com_candidatos_apenas_apto_
  recebe_ordem`, onde AMBOS os clientes têm candidato e só o cliente B
  diverge de âncora (resolve para cliente inesperado) -- prova real de
  isolamento, não apenas ausência de candidato.
