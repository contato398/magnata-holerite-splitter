# Autenticação Administrativa Compartilhada — V1

Documento de decisão da missão "AUTENTICAÇÃO ADMINISTRATIVA
COMPARTILHADA V1". Baseline: `main @ e7fc2ff1e0b83f66756b995b83f3e3109cdc608c`
(PR #117 mergeado). Branch: `fix/autenticacao-administrativa-compartilhada-v1`.

Regra arquitetural: autenticação é infraestrutura compartilhada do
Magnata OS, nunca domínio de um módulo — nada foi criado dentro de
`documental/alocacao/` nem `documental/modulo01/` nesta missão; tudo
vive em `magnata_os/autenticacao/` (novo pacote, top-level, ao lado de
`documental/`/`classificacao/`/`orquestrador/`).

## FASE 0 — Arqueologia

```text
AUTENTICACAO_EXISTENTE=Nenhuma real. app.py auditado por inteiro: sem login_required, sem SECRET_KEY, sem sessao Flask configurada, sem Basic Auth. Bearer tokens existentes sao todos de SAIDA (Airtable/Resend), nunca de entrada.
MODELOS_SUJEITO_EXISTENTES=2 copias identicas -- documental/modulo01/api/autorizacao.py (Sujeito(perfil), sem autenticacao real, gate ja documentado numa fase anterior) e documental/alocacao/autorizacao.py (mesma coisa, criada 2 missoes atras como duplicacao DELIBERADA para preservar desacoplamento entre modulos)
MODELOS_PERFIL_EXISTENTES=2 copias identicas -- Perfil(OPERACIONAL, GESTOR, AUDITOR), mesmos 3 valores nos 2 modulos
DUPLICACAO_AUTORIZACAO=Confirmada -- Perfil/Sujeito/exigir_perfil duplicados byte-a-byte entre os 2 modulos (~75 linhas cada); PermissaoNegada NAO era identica (modulo01 usa uma subclasse de ApiError com codigo/status_http, propria de sua camada de erros; alocacao usava uma Exception simples)
PROVEDOR_ID_EXISTENTE=google-auth==2.35.0 e google-api-python-client==2.149.0 ja instalados (requirements.txt), ja usados por documental/modulo01/adapters/email_gmail_readonly.py -- mas so para credencial de MAILBOX (Credentials.from_authorized_user_file, escopo gmail.readonly), nunca para login de usuario. google.oauth2.id_token (verificacao de ID token OIDC) faz parte do MESMO pacote ja instalado -- zero dependencia nova necessaria
SECRET_KEY_EXISTENTE=Nenhuma -- app.config nunca define secret_key; qualquer app.config['SECRET_KEY']/flask.session[...] hoje levantaria erro em runtime se chamado
SESSAO_FLASK_EXISTENTE=Nenhuma
```

Também auditado: `render.yaml`/`Procfile` (nenhuma menção a auth),
3 Blueprints já existentes fora de `app.py` (mesmo padrão de wiring de
2 linhas já usado 3x, reafirmado como o caminho correto quando o gate
de `app.py` for fechado), e `documental/modulo01/api/` inteiro
(`handlers.py`/`erros.py`/`contratos.py`/`serializacao.py`) — confirma
que aquele pacote já foi construído framework-agnóstico de propósito,
nunca wireado a uma rota HTTP real, precedente direto para o desenho
desta missão (`autenticacao/` também nunca importa Flask fora de
`adapters/`).

## FASE 1 — Escolha do modelo

**Escolhido: Google OIDC ("Sign in with Google"), delegado.**

| Critério | Local (senha) | Google OIDC | Outro nativo da infra |
|---|---|---|---|
| Segurança | Magnata OS armazenaria hash de senha — superfície de ataque nova | Google cuida de senha/MFA/recuperação — nunca armazenamos credencial | Render não oferece identity provider próprio |
| Simplicidade operacional | Exige fluxo de reset de senha, e-mail transacional, etc. | Só verificar 1 ID token — biblioteca já instalada | N/A |
| Revogação | Precisaria de tabela de sessões/tokens revogáveis | Revogar = remover da allowlist (Magnata OS) + o próprio usuário pode revogar acesso no Google | N/A |
| MFA | Teria que ser implementado do zero | Delegado à conta Google do operador (já presumivelmente com MFA da organização) | N/A |
| Identificação individual | Sim, mas exige cadastro próprio | Sim — e-mail verificado + `sub` estável | N/A |
| Custo | Zero, mas custo de manutenção de segurança | Zero — `google-auth` já é dependência instalada | N/A |
| Reuso entre módulos | Precisaria ser construído do zero mesmo assim | Mesmo modelo serve qualquer módulo futuro | N/A |
| Independência do Airtable | Sim (nenhuma opção usaria Airtable) | Sim | Sim |
| Zero dependência nova | Não (precisaria de hashing lib, etc.) | **Sim** — `google.oauth2.id_token` já instalado | N/A |

Nenhuma "solução nativa da infraestrutura" foi encontrada além do que
já é usado (Render não oferece IdP; Airtable está explicitamente
excluído por regra pétrea). Google OIDC vence em quase todos os
critérios e, decisivamente, tem custo de implementação zero em termos
de dependência nova — decisão não tomada por conveniência de
implementação isolada, mas porque a arqueologia (FASE 0) já mostrou a
biblioteca instalada e confiável no projeto.

## FASE 2 — Identidade canônica

`magnata_os/autenticacao/identidade.py` (novo, fonte única):
`Sujeito(perfil, sujeito_id=None, email=None, autenticado_por=None)` —
`perfil` continua campo 0 (compatibilidade retroativa: todo código
existente que fazia `Sujeito(Perfil.X)` posicionalmente continua
funcionando, confirmado por teste). `Perfil` idêntico ao que já existia
(nenhum perfil novo).

**Refatoração de compatibilidade** (FASE 2 autorizou explicitamente):
`documental/modulo01/api/autorizacao.py` e `documental/alocacao/
autorizacao.py` viraram shims finos — `Perfil`/`Sujeito` são os MESMOS
objetos (`is`, não só forma igual, confirmado por teste) importados
daqui; `exigir_perfil` de cada shim delega à checagem compartilhada,
injetando sua PRÓPRIA classe de erro (`classe_erro=...`) — modulo01
continua levantando `.erros.PermissaoNegada` (um `ApiError` real, com
`codigo`/`status_http`, consumido por `tratar_erro_para_resposta`);
alocação continua levantando a base genérica. Nenhum comportamento
observável mudou; toda a suíte de ambos os módulos roda sem alteração.

## FASE 3 — Autorização

Perfis auditados (FASE 0) e preservados sem alteração — nenhum perfil
novo criado. `documental/alocacao/api/handlers.py` não foi tocado
nesta missão: `confirmar_alocacao` continua exigindo só `GESTOR`;
`pre_visualizar_confirmacao` continua aceitando `GESTOR`/`OPERACIONAL`
— auditado e confirmado coerente, nenhuma mudança necessária.

## FASE 4 — Sessão segura

`magnata_os/autenticacao/adapters/sessao.py` (Flask nativo,
`itsdangerous` já dependência do próprio Flask — nenhuma lib nova):

- `HttpOnly`: sempre `True`.
- `Secure`: `True` por padrão; `secure=False` só aceito para o app de
  TESTE (nunca uma sessão real).
- `SameSite`: `Lax`.
- Expiração: `PERMANENT_SESSION_LIFETIME` (8h por padrão) +
  `session.permanent = True`.
- Logout: `session.clear()` — sessão inteira, nunca parcial.
- Segredo: `MAGNATA_SESSION_SECRET_KEY` (variável de ambiente nova),
  nunca hardcoded, nunca gerado on-the-fly (invalidaria sessões a cada
  restart e mascararia a variável ausente) — falha explícita
  (`SegredoSessaoAusente`) se não configurada.
- CSRF: synchronizer token pattern (`gerar_csrf_token`/
  `validar_csrf_token`, comparação em tempo constante via
  `hmac.compare_digest`), obrigatório em `/auth/logout` e no decorator
  `exigir_csrf` para rotas de domínio futuras.

**Nenhuma sessão real de produção é ativada por esta missão** —
`configurar_sessao_segura` só configura um `flask.Flask` já existente,
passado pelo chamador; nunca chamado contra o `app` real.

## FASE 5 — Allowlist administrativa

`magnata_os/autenticacao/allowlist.py` — **Airtable nunca é authority
de acesso** (confirmado estruturalmente por teste: nenhum módulo deste
pacote importa nada de Airtable). Menor mecanismo seguro para V1:
variável de ambiente `MAGNATA_ADMIN_ALLOWLIST` (formato
`email:PERFIL,email:PERFIL`) — zero schema novo, revogação/rotação é
só trocar a variável no Render e reiniciar (nenhum deploy de código).
`ResolvedorAllowlistAmbiente` é a única implementação V1; uma futura
`ResolvedorAllowlistPostgres` (tabela própria) implementaria a MESMA
interface (`perfil_para_email`) sem mudar nenhum chamador — evolução
natural, não construída agora (schema novo antes do gate, evitado de
propósito).

## FASE 6 — Auditoria "quem fez"

Fecha o 2º gate do PR #117. `eventos_documentais` (Módulo 01) avaliada
e rejeitada como reuso — FK obrigatória para `documentos`, não serve
para colaborador/posto (ou qualquer agregado futuro) sem migration
própria de qualquer forma. Desenhada uma trilha **genérica** (nunca
"auditoria de alocação"):

- `magnata_os/autenticacao/migrations/0001_criar_auditoria_operacoes.sql`
  (+ rollback) — `auditoria_operacoes(id, sujeito_id, email, perfil,
  operacao, referencia_agregado, resultado, erro_codigo, criado_em)`,
  append-only por trigger (mesmo padrão de
  `modulo01/migrations/0003_trigger_eventos_append_only.sql`).
  `operacao`/`referencia_agregado` são texto opaco, nunca FK para um
  módulo específico (mesma decisão já registrada para `alocacao.
  posto_id`) — schema compartilhado não pode acoplar a um módulo.
  `erro_codigo` é sempre nome de classe de exceção, nunca mensagem
  livre (nunca vaza detalhe técnico numa trilha legível por Auditor).
- `eventos.py`/`adapters/sqlite_auditoria.py`/`adapters/
  postgres_auditoria.py` — mesmo padrão de `documental/alocacao/`.
  **Nunca idempotente** de propósito: cada tentativa de operação é seu
  próprio fato auditável, mesmo quando o domínio subjacente é
  idempotente (reprocessar a mesma confirmação de alocação 3x gera 3
  linhas de auditoria).
- `auditoria_integracao.py` — composição genérica
  (`executar_com_auditoria`) + composição concreta
  (`confirmar_alocacao_com_auditoria`) que envolve `documental/
  alocacao/api/handlers.py::confirmar_alocacao` **sem modificá-lo**
  (mesma assinatura de sempre, zero parâmetro novo, zero teste
  existente quebrado) — prova ponta a ponta: identidade autenticada →
  operação de domínio real → trilha "quem fez" real.

**Nenhuma migration aplicada contra Postgres real/produção** — só
contra o Postgres efêmero de CI (FASE 9) e SQLite local.

## FASE 7 — Wiring

`magnata_os/autenticacao/adapters/blueprint_login.py` — Blueprint
completo (`/auth/login`, `/auth/logout`, `/auth/me`) + decorators
reutilizáveis para rotas de domínio futuras (`exigir_sessao_com_perfil`,
`exigir_csrf`). Fluxo exato pedido:
`request -> autenticar identidade (Google) -> construir Sujeito (via allowlist) -> handler de domínio`.

**Não registrado em `app.py`** — mesma decisão, pelo mesmo motivo, da
missão anterior: depende de `GOOGLE_OAUTH_CLIENT_ID`/
`MAGNATA_ADMIN_ALLOWLIST`/`MAGNATA_SESSION_SECRET_KEY` reais, nenhum
dos quais existe nesta sessão, e registrar uma rota real sem esses
segredos configurados seria pior do que não registrá-la. Diff mínimo
necessário quando o gate for fechado (idêntico ao padrão já usado 3x):

```python
from magnata_os.autenticacao.adapters.blueprint_login import auth_bp
app.register_blueprint(auth_bp)
```

`login`/`logout`/`me`/`exigir_sessao_com_perfil` NUNCA aceitam
`perfil` do corpo da requisição — confirmado por teste
(`test_login_ignora_perfil_autodeclarado_no_corpo`).

## FASE 8 — Testes adversariais

60 testes novos (`test_magnata_os_autenticacao_*.py`, 6 arquivos — 50
via SQLite/mocks, mais 10 no arquivo `_postgres_real.py`, que só roda
sob `MAGNATA_TEST_POSTGRES_REAL`) cobrem os 16 cenários pedidos: usuário não autenticado (401, nunca
allow-all); identidade inválida (401); usuário autenticado sem
permissão (403); gestor válido (200, identidade chega ao handler);
sessão expirada (config verificada — `PERMANENT_SESSION_LIFETIME`);
cookie adulterado (assinatura Flask/itsdangerous rejeita, testado via
logout com token forjado); CSRF ausente (403); logout (limpa sessão,
replay do cookie pós-logout confirmado `autenticado: False`); e-mail
não autorizado (403 `nao_autorizado`); mudança de perfil (perfil
sempre resolvido pela allowlist no momento do login, nunca em cache
indefinido); indisponibilidade do provedor Google (nunca aceito por
omissão — vira erro explícito); autenticação nunca degrada para
allow-all (rota protegida sem sessão sempre 401); Airtable indisponível
não afeta autenticação (estrutural — nenhum import); handlers nunca
aceitam perfil autodeclarado; identidade chega corretamente à trilha
de auditoria (prova ponta a ponta com `sub` do Google preservado até o
handler).

## FASE 9 — Não feito (registrado)

Nenhuma escrita Airtable, nenhum cadastro de usuário no Airtable,
nenhum Postgres real provisionado, nenhuma migration aplicada em
produção, nenhuma credencial real inserida, nenhum deploy, `app.py`
não tocado, nenhum login público ativado, nenhum dado pessoal real
usado em teste (e-mails 100% sintéticos, `@exemplo.com`).

**Gate externo real, fora da capacidade desta sessão:** registrar um
Client ID OAuth no Google Cloud Console é uma ação externa que esta
sessão não tem ferramenta para executar e que esta missão não deveria
executar mesmo se tivesse — decisão organizacional (qual conta Google
Workspace, qual projeto GCP) que precisa de um humano.

## FASE 10 — Duas revisões adversariais (autocorrigidas nesta rodada)

**Revisão 1 (autenticação/autorização/sessão/CSRF/privilege
escalation/spoofing de perfil/segredo/auditoria):** confirmado que
`exigir_perfil`/`exigir_sessao_com_perfil` sempre rodam antes de
qualquer I/O; CSRF comparado em tempo constante; segredo de sessão
nunca hardcoded/gerado on-the-fly. **Achado e corrigido:**
`verificar_id_token_google` descartava o claim `sub` (id estável do
Google) do token, então `Sujeito.sujeito_id` nunca seria populado pelo
fluxo real de login, apesar de a FASE 2 pedir explicitamente esse
campo na identidade canônica — corrigido para devolver
`IdentidadeGoogleVerificada(email, sub)`, threaded até
`iniciar_sessao(..., sujeito_id=identidade.sub)`, com teste de
regressão provando que o `sub` chega intacto ao handler protegido.

**Revisão 2 (compartilhamento entre módulos/eliminação de duplicação/
independência do Airtable/portabilidade/Render/regressões/futuro
Magnata OS):** ~150 linhas de `Perfil`/`Sujeito`/`exigir_perfil`
duplicadas eliminadas para 1 fonte única; nenhum import de Airtable em
nenhum módulo de `autenticacao/` (confirmado por teste estrutural via
AST, não só grep de texto); nenhuma especificidade de Render no código
(só `DATABASE_URL`-equivalente `MAGNATA_SESSION_SECRET_KEY`/
`GOOGLE_OAUTH_CLIENT_ID`/`MAGNATA_ADMIN_ALLOWLIST`, todas variáveis de
ambiente portáveis); suíte completa sem regressão.

## FASE 11 — Testes/Governança

Suíte completa local: 1886 passed, 5 failed, 34 errors (mesma baseline
pré-existente de sandbox Windows, sem regressão nova). Governança
local: 15/15 gates. `git diff --check` limpo. Job `postgres-real` de CI
estendido (1 linha de `run:`, nenhum job novo) para também validar
`magnata_os/autenticacao/migrations/` contra Postgres real efêmero.
