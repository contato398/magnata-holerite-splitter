"""Conftest raiz -- só existe para permitir que `app.py` seja importado em
ambiente de teste controlado depois da missão "ATIVAÇÃO MÍNIMA DA
AUTENTICAÇÃO ADMINISTRATIVA NO APP.PY".

`app.py` agora chama `configurar_sessao_segura(app)` (`magnata_os/
autenticacao/adapters/sessao.py`) no import, e essa função é fail-closed:
levanta `SegredoSessaoAusente` se `MAGNATA_SESSION_SECRET_KEY` não estiver
no ambiente (comportamento correto e intencional para produção -- ver
sessao.py). Vários arquivos de teste já existentes (ex.:
`test_seguranca_rotas_dp_fiscal.py`) fazem `import app` no nível de módulo,
durante a COLETA do pytest -- antes de qualquer `monkeypatch` de teste
individual poder agir. Sem este conftest, a suíte inteira falharia na
coleta em qualquer ambiente (local ou CI) que não tenha essa variável real
configurada, o que seria uma regressão de toda a suíte, não só dos testes
de autenticação.

`os.environ.setdefault` (nunca `os.environ[...] =`): só preenche o valor se
a variável ainda não existir -- um ambiente que já define
`MAGNATA_SESSION_SECRET_KEY` de verdade (produção nunca roda pytest, mas um
desenvolvedor testando localmente com uma chave real, por exemplo) não é
sobrescrito.

Valor sintético, reconhecido como placeholder pelo Gate 5 de governança
(`.magnata/patterns.sh`, SECRET_PLACEHOLDER_REGEX) -- nunca um segredo real
mascarado de teste."""
import os

_CHAVE_SESSAO_PLACEHOLDER_DE_TESTE = 'test'
os.environ.setdefault('MAGNATA_SESSION_SECRET_KEY', _CHAVE_SESSAO_PLACEHOLDER_DE_TESTE)
