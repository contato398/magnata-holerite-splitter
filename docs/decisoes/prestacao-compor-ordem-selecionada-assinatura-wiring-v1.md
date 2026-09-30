# Ligar `prestacao_compor_ordem_selecionada_cli.py` a presets COM assinatura -- wiring, não construção

## Necessidade de negócio (contexto maior, registrada por completo)

Pedido original do operador (já citado em
`docs/decisoes/selecao-envio-operador-v1.md`): "O que a gente quer é
ter total autonomia para escolher quais documentos enviar, para
quantos colaboradores enviar ... **se vai com assinatura digital e
comprovante da assinatura ou não**." A PR mesclada mais recente
(`feat/prestacao-compor-ordem-selecionada-shadow-v1`, PR #212) fechou
diagnóstico real -> seleção do operador -> Ordem real composta em
sombra, mas só para a metade "sem assinatura" dessa escolha -- exatamente
a mesma restrição que `prestacao_cliente_competencia_v1.py --ate-pending`
já tinha. Esta missão fecha a outra metade para
`scripts/prestacao_compor_ordem_selecionada_cli.py`.

## Investigação: wiring ou construção real? (evidência de código, não presunção)

Confirmado por leitura direta, ANTES de qualquer mudança, que os
componentes reais de assinatura **já existem** neste repositório e já
estão em uso em produção por outro caminho:

- `MaterializadorArquivoLegadoAirtable`
  (`magnata_os/documental/modulo01/adapters/materializador_arquivo_legado.py`)
  -- implementação real de `MaterializadorArquivoLegado`, escreve em
  `TABLE_ARQUIVOS` via HTTP contra o Airtable real.
- `AdapterObrigacaoAssinaturaLegadoHttp`
  (`magnata_os/orquestrador/adapters/obrigacao_assinatura_legado_http.py`)
  -- implementação real de `PortaObrigacaoAssinatura`, chama
  `POST /assinatura/gerar` (`disparar_whatsapp=false`) e
  `GET /assinatura/consulta` do motor legado (`app.py`, protegido, não
  tocado).
- `RepositorioConclusaoObrigacaoAssinaturaPostgres`
  (`magnata_os/orquestrador/adapters/postgres_conclusao_obrigacao_assinatura.py`)
  -- marcador canônico da obrigação (migration 0006).
- Os TRÊS já têm compositor real a partir do ambiente, fail-closed por
  credencial ausente, e já são chamados condicionalmente por
  `magnata_os/orquestrador/distribuir_documento_v1.py::main` (linhas
  113-153 e 192-196) quando `ordem.exigir_assinatura` é `True` -- a
  MESMA condição que faltava nesta CLI.
- O núcleo de composição (`wiring_distribuicao_documental_shadow.
  materializar_distribuicao_documental_shadow` / `_montar_ramo_com_
  assinatura`) e o elo de Prestação
  (`wiring_prestacao_distribuicao_documental_shadow.
  materializar_prestacao_distribuicao_documental_shadow`) **já aceitam**
  `materializador`/`porta_assinatura`/`repositorio_conclusao` como
  parâmetros opcionais e já sabem operar o ramo com assinatura -- nenhum
  dos dois precisou de qualquer mudança nesta missão.
- `resolver_parametros_ordem_prestacao_contato_v1.
  construir_resolvedor_parametros_ordem_prestacao_contato_v1` trata
  `preset_id` como dado opaco -- não impõe nenhuma restrição a presets
  com assinatura.
- `politica_preset_distribuicao_documental._PRESETS_V1` já define
  `DOCUMENTO_UNITARIO_COM_ASSINATURA` e
  `PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA`.

**Conclusão**: a única coisa que faltava era, dentro de
`scripts/prestacao_compor_ordem_selecionada_cli.py`, (a) `_parse_args`
rejeitar qualquer preset fora de `PRESETS_SEM_ASSINATURA`, e (b)
`executar()` sempre passar `materializador=None, porta_assinatura=None`
e nunca compor `repositorio_conclusao`, independentemente do preset
escolhido. **Isto é WIRING** -- religar peças reais já existentes e já
usadas em produção por outro caminho (`distribuir_documento_v1.py`) a
este caminho específico (Prestação selecionada pelo operador). Não é
construção de um provedor/mecanismo de assinatura novo, e não havia
necessidade de decisão de fornecedor para esta missão.

## O que foi feito

Em `scripts/prestacao_compor_ordem_selecionada_cli.py`:

1. `_parse_args` passou a validar `--preset` contra
   `politica_preset_distribuicao_documental.resolver_preset` (aceita
   qualquer `preset_id` conhecido, com ou sem assinatura) em vez de só
   `PRESETS_SEM_ASSINATURA`.
2. `executar()` passou a resolver `preset = resolver_preset(preset_id)`
   e a compor `materializador`/`porta_assinatura`/`repositorio_conclusao`
   a partir do ambiente **só quando `preset.exigir_assinatura` for
   `True`** -- reaproveitando, sem duplicar, os MESMOS três
   compositores já existentes em `distribuir_documento_v1.py`
   (`_compor_materializador_a_partir_do_ambiente`/`_compor_obrigacao_
   assinatura_a_partir_do_ambiente`/`_compor_repositorio_conclusao_a_
   partir_do_ambiente`). Sem assinatura, o comportamento é bit a bit o
   mesmo de antes (`None, None`, nenhuma credencial olhada).
3. `main()` ganhou um `except RuntimeError` para propagar, como
   `CONFIGURACAO_AUSENTE`, a falta de credencial que só pode ser
   descoberta dentro de `executar()` (depois que o preset é resolvido).

Nenhuma linha de `wiring_distribuicao_documental_shadow.py`,
`wiring_prestacao_distribuicao_documental_shadow.py`,
`executar_prestacao_selecionada_contato_ate_pending_shadow_v1.py`,
`distribuir_documento_v1.py`, `ciclo_producao_v1.py` ou qualquer
adapter foi tocada -- todos já estavam prontos para isto.

## Disciplina de sombra preservada -- e o que ela NÃO cobre

Continua verdade, sem alteração: nenhum import de `porta_execucao`,
`transporte_real_habilitado`, `ExecutorEvolutionLegado` ou
`ciclo_producao_v1` nesta CLI; a Ordem sempre termina em `PENDING`; as
3 barreiras de transporte real (`autorizar_transporte_real`,
`ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO`, `ORQUESTRADOR_DRY_RUN`)
continuam intactas e nunca tocadas por este caminho.

**Ponto explicitamente investigado e confirmado, não presumido**: NÃO
existe, nem antes nem depois desta mudança, uma barreira separada
específica para "disparo real de assinatura", distinta das barreiras
de transporte real. Rodar esta CLI com `--preset` com assinatura E com
`AIRTABLE_API_KEY`/`ORQUESTRADOR_ASSINATURA_BASE_URL`/
`ORQUESTRADOR_ASSINATURA_API_KEY` reais configuradas **chama de
verdade** `POST /assinatura/gerar` (`disparar_whatsapp=false`) contra o
motor de assinatura real e escreve de verdade em `TABLE_ARQUIVOS`
(Airtable) -- isto NÃO é WhatsApp real, mas É uma escrita externa real
(criação de obrigação de assinatura/link). Isto é exatamente o mesmo
comportamento que `distribuir_documento_v1.py` já tem em produção hoje
para Ordens com assinatura -- esta missão apenas religou o MESMO
comportamento a um segundo caminho de composição (o da seleção do
operador). A única barreira de fato é a credencial de ambiente: sem
ela, `RuntimeError` fail-closed antes de qualquer tentativa de rede
(comportamento herdado, não nesta migração). Autorizar essa credencial
em ambiente real continua sendo gate humano de produção (CLAUDE.md
§6/§12-I), nunca decidido por este módulo -- nenhuma chamada de rede
real foi feita durante esta missão (todos os testes usam fakes em
memória e há teste dedicado bloqueando `socket.connect`).

## Testes adicionados (`tests/test_scripts_prestacao_compor_ordem_selecionada_cli.py`)

- `test_preset_com_assinatura_e_aceito_e_compoe_materializador_e_porta_assinatura_reais`
  -- seleção com `exigir_assinatura_digital_e_comprovante=True` e preset
  com assinatura chega a `PENDING` com `assinatura_link` preenchido;
  materializador/porta_assinatura (fake em memória) são de fato
  chamados.
- `test_selecao_sem_assinatura_e_preset_com_assinatura_isola_so_esse_colaborador`
  -- isolamento de falha: 1 colaborador cujo item de seleção diverge do
  preset com assinatura desta execução é isolado
  (`PresetDaOrdemDivergeDaSelecaoOperador`, mecanismo já existente,
  reaproveitado); o outro colaborador, que bate com o preset, chega a
  `PENDING` normalmente.
- `test_preset_sem_assinatura_nunca_compoe_materializador_nem_porta_assinatura`
  -- garante que a mudança é estritamente aditiva: com preset sem
  assinatura, nenhum dos 3 compositores novos é sequer chamado.
- `test_preset_com_assinatura_sem_credencial_de_ambiente_falha_fail_closed_via_main`
  -- `RuntimeError` de credencial ausente vira `CONFIGURACAO_AUSENTE`
  via `main()`, sem chegar a tentar rede.
- `test_nenhuma_chamada_de_rede_real_e_feita_pelo_script_com_preset_de_assinatura`
  -- mesma garantia do teste já existente (bloqueia `socket.connect`),
  agora exercitando o ramo com assinatura, o mais arriscado de
  introduzir uma chamada de rede real por engano.
- Correção de teste pré-existente: `test_main_preset_invalido_falha_
  antes_de_compor_dependencias` usava `DOCUMENTO_UNITARIO_COM_ASSINATURA`
  como exemplo de preset inválido -- isso deixou de ser verdade (é
  justamente o preset que esta missão passou a aceitar). Corrigido para
  usar um `preset_id` que não existe em nenhum lugar
  (`PRESET_QUE_NAO_EXISTE`), preservando a garantia de fail-closed para
  preset genuinamente desconhecido.

Suíte completa: `3070 passed, 103 skipped` (0 regressão; os 103
skipped são pré-existentes, não relacionados a esta mudança). Gates de
governança local (`scripts/ci/validate_governance.sh`): 15/15
aprovados, incluindo a branch nova adicionada a
`.magnata/patterns.sh` (`AUTHORIZED_BRANCHES`).

## Riscos residuais declarados (não escondidos)

1. **Isolamento de falha SISTÊMICA (não de domínio) no ramo com
   assinatura ainda não é por colaborador.** `executar_prestacao_
   selecionada_ate_distribuicao_documental_shadow` (`wiring_prestacao_
   distribuicao_documental_shadow.py`, intocado nesta missão) só isola,
   por colaborador, exceções de DOMÍNIO
   (`PrestacaoDistribuicaoDocumentalError`/`DistribuicaoDocumentalError`
   e subclasses, ex.: `PresetDaOrdemDivergeDaSelecaoOperador`). Uma
   falha de REDE real do materializador (`ErroMaterializacaoAirtable`)
   ou do motor de assinatura (`ObrigacaoAssinaturaLegadoError`) --
   ambas `RuntimeError`, nunca `DistribuicaoDocumentalError` -- NÃO é
   capturada por esse isolamento e interrompe o processamento dos
   colaboradores restantes da mesma seleção. Isto é comportamento
   HERDADO e pré-existente (mesmo núcleo já usado por `distribuir_
   documento_v1.py` em produção); esta missão não o introduziu, só o
   tornou alcançável por um segundo caminho de composição (o da seleção
   do operador). Não foi corrigido aqui por ser uma mudança de
   comportamento do núcleo genérico compartilhado (fora do escopo
   estrito desta missão, que é ligar esta CLI aos compositores já
   existentes) -- registrado como candidato a uma fase futura separada
   (ex.: distinguir explicitamente falha de infraestrutura vs. falha de
   domínio no isolamento por colaborador), nunca decidido
   silenciosamente aqui.
2. **`prestacao_cliente_competencia_v1.py --ate-pending` continua com a
   MESMA restrição antiga** (só `PRESETS_SEM_ASSINATURA`) -- fora do
   escopo desta missão, que tratou especificamente do caminho da
   seleção do operador (`prestacao_compor_ordem_selecionada_cli.py`).
   Se o operador também precisar de assinatura pelo caminho "manda tudo
   que está pronto" (sem curadoria), o mesmo padrão de wiring aplicado
   aqui é diretamente reaproveitável lá -- registrado como sugestão
   separada, não incluída nesta entrega sem aviso.
3. **1 único `--preset` por execução continua valendo** -- misturar, na
   MESMA chamada da CLI, colaboradores que exigem assinatura com
   colaboradores que não exigem continua exigindo 2 chamadas (1 preset
   sem assinatura + 1 preset com assinatura), cada uma isolando quem
   não corresponde ao preset escolhido naquela chamada. Isto já era
   assim antes desta missão (design de `filtrar_trios_por_selecao_
   operador`/`PresetDaOrdemDivergeDaSelecaoOperador`) e não foi
   alterado.

## Próxima ação sugerida

Nenhuma ação imediata necessária -- a lacuna de negócio original
("com ou sem assinatura") está fechada para o caminho da seleção do
operador. Candidatos a fases futuras, se e quando priorizados: (a)
aplicar o mesmo wiring a `prestacao_cliente_competencia_v1.py
--ate-pending` (risco 2 acima); (b) endurecer o isolamento por
colaborador para também cobrir falha sistêmica de rede do
materializador/motor de assinatura (risco 1 acima).
