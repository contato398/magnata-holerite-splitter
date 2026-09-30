# Local de trabalho na admissão: determinação humana pontual, nunca leitura automática — V1

Documento de decisão da missão "GATILHO KIT DE ADMISSÃO → PREVIEW
SECULLUM V1". Branch: `fix/rh-admissao-gatilho-preview-secullum-v1`.
Complementa (não substitui) `escopo-rh-admissao-demissao-pontoweb-v1.md`,
que já registrava a pergunta em aberto "de onde vem o local de
trabalho" (§2, item 2) como decisão de negócio pendente. Este documento
registra a resposta que o operador deu.

## 1. Decisão de negócio (do operador, 2026-09-30)

- A Magnata quer **reduzir a dependência do Airtable** (não eliminar —
  reduzir ao mínimo). O local de trabalho (posto) de um colaborador
  hoje só existe gravado no Airtable (campo "Locais de trabalho",
  vínculo para a tabela Locais — ver `app.py:2535-2537` e
  `app.py:3608-3613`, que já documentam esse campo como *"vínculo para
  a tabela Locais e não é preenchido automaticamente; requer
  associação manual"*).
- **O gatilho automático nunca pode inferir/adivinhar o local de
  trabalho sozinho.** Quando um colaborador é admitido ou muda de
  local de trabalho, **uma pessoa determina explicitamente** o local
  de trabalho naquele momento — não é leitura de um campo já
  preenchido em algum sistema (Airtable ou outro). É decisão humana
  pontual, a cada evento.
- Consequência direta: quando um Kit de Admissão for processado e não
  houver uma determinação humana já registrada **para aquele evento**,
  a intenção de cadastro na Secullum **não é composta** — vira
  pendência explícita, aguardando a pessoa fornecer o local de
  trabalho. Nunca uma tentativa de adivinhação silenciosa (mesmo
  princípio de `/CLAUDE.md` §4, "Automação por confiança; ação humana
  para exceção").

## 2. O que já existia e foi confirmado, não reinventado

| Peça | Onde | Confirmação |
|---|---|---|
| Classificação de Kit de Admissão | `app.py` (`F_FUNC_DOCS_ADMISSAO`, `F_FUNC_KIT_CONSOLIDADO`, `TIPOS_KIT_ADMISSAO`, tipo `KIT_ADMISSAO`) | já existe; não alterado nesta missão (arquivo protegido, `/CLAUDE.md` §7) |
| "Locais de trabalho" nunca é automático | `app.py:2535-2537`, `app.py:3608-3613` | o próprio legado já documenta isso — a decisão do operador confirma e formaliza o que o código já fazia na prática |
| Contrato `PortaSecullum` / `IntencaoCadastroSecullum` / `compor_porta_secullum` | `magnata_os/rh_admissao/porta_secullum.py` | reaproveitado sem alteração; `grupo_escala_id` já era `Optional[str]` no dataclass — este gatilho é o primeiro chamador real que decide, no seu próprio nível, se esse campo pode ou não ser preenchido |
| "Grupo de Escala" é intenção definida na admissão, não leitura de dado já existente | `src/sync_new_employees.py` (docstring do módulo) | mesmo princípio já registrado ali para a Secullum; esta decisão estende o princípio para a origem do dado em si (Airtable) |

Nenhuma extração de dado pessoal do texto do Kit de Admissão em si
(nome/CPF de uma Ficha de Registro, por regex) existe hoje no legado —
só a extração de holerite (`src/sync_new_employees.py::extrair_dados_holerite`,
regex específico do layout do holerite, não do Kit). Por isso o gatilho
construído nesta missão recebe os dados do colaborador já extraídos/
resolvidos por quem o chama (ex.: o registro de Funcionário já
existente no Airtable, ao qual o Kit já chega vinculado — ver
`_vincular_documento_ao_funcionario` em `src/sync_new_employees.py`),
em vez de reimplementar uma extração que nunca existiu.

## 3. O que foi construído

`magnata_os/rh_admissao/gatilho_admissao.py` — módulo de domínio puro
(sem Flask/Airtable/driver de rede):

- `DadosColaboradorKitAdmissao` — o que já dá para ter de um Kit
  processado (`colaborador_id`, `cpf`, `nome`, `cargo` opcional).
- `DeterminacaoLocalTrabalho` — a decisão humana pontual
  (`grupo_escala_id`, `determinado_por`, `determinado_em`). É a
  interface pela qual uma pessoa fornece o local de trabalho —
  ver §4 sobre como isso chega até aqui na prática hoje.
- `processar_kit_admissao(dados, determinacao, *, porta=None, registro=None)`:
  - `determinacao is None` → `SituacaoGatilhoAdmissao.AGUARDANDO_LOCAL_TRABALHO`,
    `motivo_bloqueio='local_trabalho_nao_determinado'`, nunca chama a
    porta Secullum, nunca lança.
  - `determinacao` presente → monta `IntencaoCadastroSecullum` e chama
    `compor_porta_secullum(autorizar_secullum_real=False)` (hardcoded
    nesta missão — nunca `True`), sempre em modo sombra.
  - qualquer exceção inesperada vira `SituacaoGatilhoAdmissao.FALHOU`
    no resultado, nunca propaga — isola a falha de um kit sem travar
    os demais em `processar_lote_kits_admissao`.
- `RegistroGatilhoAdmissaoEmMemoria` — guarda de idempotência
  injetável (chave = `colaborador_id`): reprocessar o mesmo Kit
  devolve o resultado já computado (`reaproveitado=True`) em vez de
  recompor a intenção ou rechamar a porta. É auxiliar de processo, não
  o histórico append-only oficial de um módulo com persistência real —
  um wiring futuro com armazenamento durável troca esta classe por um
  adapter equivalente sem mudar `processar_kit_admissao`.
- `ResultadoGatilhoAdmissao.como_evidencia()` — nunca expõe CPF/nome
  (mesma disciplina de `ResultadoAcaoSecullum.como_evidencia()` em
  `porta_secullum.py`).

Campos de estado mantidos separados (`/CLAUDE.md` §4): `situacao`,
`motivo_bloqueio` e `proxima_acao` nunca fundidos num campo só.
`etapa_atual` foi deliberadamente omitido — este gatilho é um único
ponto de decisão, não uma esteira multi-estágio com transições.

## 4. Como uma pessoa fornece o local de trabalho, na prática, hoje

Esta missão entrega a **peça de domínio** (`DeterminacaoLocalTrabalho`
como parâmetro de entrada explícito), não uma interface de captura
(tela, comando de CLI, formulário). Isso é pendência separada — ver
§5. `DeterminacaoLocalTrabalho` foi desenhado para caber em qualquer
uma dessas superfícies sem mudar de forma:

- um comando/rota que uma pessoa aciona manualmente informando
  `grupo_escala_id` (ex.: `--grupo-escala "Escala A - Dias Pares"`);
- um campo estruturado num formulário interno (painel Fase 5, já
  existente para outras finalidades) que grava a decisão antes de
  disparar o gatilho;
- uma futura tela de aprovação de pendências, no mesmo padrão do que
  já existe para pré-cadastro (`app.py`, "Validação Pendente").

Nenhuma dessas superfícies foi construída nesta missão — só o contrato
que qualquer uma delas vai preencher.

## 5. O que continua pendência (declarado, não escondido)

- **Não há gatilho automático real rodando em produção.** Esta missão
  liga Kit de Admissão → Preview/pendência *como capacidade testável*,
  não como processo agendado. Falta decidir **como/quando** isso é
  disparado de fato a partir de um Kit de Admissão chegando em
  produção (cron? webhook do robô de e-mail existente? rota chamada
  pelo próprio fluxo de `app.py` que já classifica o Kit?) — decisão de
  arquitetura/operação separada, não tomada aqui.
- **Nenhuma interface de captura da determinação humana foi
  construída** (§4) — só o contrato de dados que ela vai preencher.
- **A extração de dados do colaborador a partir do próprio Kit
  continua não existindo** (só existe para holerite). O gatilho depende
  de quem o chama já ter `colaborador_id`/`cpf`/`nome` resolvidos (hoje,
  via o Funcionário ao qual o Kit já está vinculado no Airtable).
- **`autorizar_secullum_real` continua `False`, sempre, nesta missão.**
  Habilitar escrita real no PontoWeb continua exigindo autorização de
  fase específica (`/CLAUDE.md` §6) — gate humano, não decidido aqui.
- O caminho de demissão simétrico (documento de rescisão → Preview →
  `PortaSecullum.desligar`) continua fora de escopo desta missão —
  já registrado como próximo passo possível em
  `escopo-rh-admissao-demissao-pontoweb-v1.md` §5.

## 6. Gates que este documento não dispensa

Tudo que `/CLAUDE.md` §6 e §12-I já listam continua valendo: nenhuma
escrita real na Secullum, nenhum merge, nenhum push em `main`, nenhuma
autorização de fase concedida por este documento. Este documento só
registra a decisão de negócio sobre a origem do local de trabalho e o
que foi construído em modo sombra a partir dela.
