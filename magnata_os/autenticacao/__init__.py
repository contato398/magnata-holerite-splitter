"""
Autenticação/autorização administrativa COMPARTILHADA do Magnata OS
(missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1").

**Autenticação é infraestrutura compartilhada, nunca domínio de um
módulo.** Antes desta missão, `Perfil`/`Sujeito`/`exigir_perfil`
existiam DUPLICADOS em `magnata_os/documental/modulo01/api/autorizacao.py`
e `magnata_os/documental/alocacao/autorizacao.py` — cada um "sem
autenticação real", cada um um gate aberto independente. Esta missão
consolida os dois na fonte única deste pacote (`identidade.py`) e
transforma os dois arquivos antigos em shims finos de compatibilidade
(mesmo import, mesmo comportamento, zero duplicação de lógica).

Nenhum módulo de domínio (`documental/*`) importa `flask`, driver de
sessão ou provedor de identidade concreto — só este pacote fala com
esse mundo externo, e só nos seus próprios adapters (`adapters/`).

Zero dependência nova instalada: o modelo escolhido (Google OIDC, ver
`provedor_google_oidc.py`) reaproveita `google-auth` (já instalado,
já usado por `documental/modulo01/adapters/email_gmail_readonly.py`
para um propósito totalmente diferente — aqui é `google.oauth2.
id_token`, nunca `Credentials.from_authorized_user_file`).

Airtable nunca é autoridade de identidade nem de autorização deste
pacote — ver `allowlist.py`.
"""
