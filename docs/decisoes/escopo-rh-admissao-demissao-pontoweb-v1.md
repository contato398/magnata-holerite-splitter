# RH / Admissão-Demissão automática (PontoWeb Secullum) — escopo registrado

- **Data:** 2026-09-29
- **Natureza:** registro de escopo (auditoria + desenho). Nenhum código de integração real foi escrito. Nenhuma chamada à API do PontoWeb foi feita.
- **Pedido do operador:** quando chega o e-mail do DP com o kit de admissão de um colaborador novo, o Magnata OS deve cadastrar sozinho esse colaborador no PontoWeb, no local de trabalho definido, e o caminho contrário na demissão (baixa no PontoWeb e no sistema interno). O mesmo princípio vale para futuras integrações (outros sistemas de ponto, banco/extrato).

## 1. O que já existe (legado, produção) — reaproveitar, nunca reconstruir

| Peça | Onde | O que faz |
|---|---|---|
| Cliente da API do PontoWeb | `src/services/secullum_ponto.py` | login/senha → token Bearer com cache; cadastra funcionário (`sincronizar_funcionario`); marca demissão (`rota_excluir`, PUT com `Demissao=data`); lê cálculos de ponto; gera alertas |
| Extração de dados do holerite | `src/sync_new_employees.py` | nome, CPF, cargo, data de admissão, via regex no texto do PDF |
| Cadastro/atualização no Airtable | `src/sync_new_employees.py::criar_ou_completar_funcionario` | casa por CPF; nunca sobrescreve campo já preenchido |
| Registro HTTP ativo | `app.py:77-85` | os três blueprints (`secullum_bp`, `sync_bp`, `ingestao_bp`) já estão registrados e respondendo em produção |
| Classificação de "Kit de Admissão" | `app.py` (campos `F_FUNC_DOCS_ADMISSAO`, `F_FUNC_KIT_CONSOLIDADO`, tipo `KIT_ADMISSAO`) | o e-mail já é reconhecido e o documento já cai no lugar certo do Airtable |

**Diagnóstico do problema real:** as peças existem e funcionam isoladamente (comprovado: rotas HTTP registradas, `--dry-run` funcional), mas **nada as encadeia**. Hoje uma pessoa precisa rodar o script ou chamar a rota manualmente depois que o Kit de Admissão chega. Não é ausência de capacidade — é ausência de orquestração automática.

## 2. O que falta

1. **Gatilho automático:** ao classificar um documento como Kit de Admissão (isso já acontece), disparar a sincronização em vez de esperar alguém rodar o script.
2. **Decisão do local de trabalho:** hoje é lida do "Grupo de Escala" já preenchido manualmente na admissão. Falta decidir de onde vem essa informação automaticamente (o próprio e-mail do DP? um padrão por cliente/posto?). **Isso é decisão de negócio, não técnica** — registrado como pergunta aberta, não decidido aqui.
3. **Caminho de demissão simétrico:** hoje existe a rota que marca demissão no PontoWeb, mas não há gatilho automático a partir de um documento de rescisão chegando por e-mail, nem baixa espelhada no cadastro interno (Airtable/Postgres).
4. **Contrato genérico, não um script solto:** para seguir a arquitetura do Magnata OS (Orquestrador central, capacidades reutilizáveis), isso deveria virar uma capacidade — "admissão de colaborador" e "desligamento de colaborador" — com Preview, autorização e evidência, do mesmo jeito que a distribuição documental já funciona. Não um script Python chamado por fora do Orquestrador.

## 3. Desenho proposto (para quando for autorizado)

```
Kit de Admissão classificado (app.py, já existe)
        ↓
extrair dados (nome, CPF, cargo, admissão) — já existe, sync_new_employees.py
        ↓
resolver local de trabalho (REGRA DE NEGÓCIO — pendente de decisão do operador)
        ↓
Preview da ação "cadastrar no PontoWeb" (novo — segue o padrão do Orquestrador)
        ↓
autorização (fase, igual à distribuição documental)
        ↓
PortaSecullum.cadastrar_funcionario — ADAPTER sobre secullum_ponto.py existente,
nunca reimplementado
        ↓
evidência + auditoria (Secullum ID gravado, evento registrado)
```

Demissão é o espelho: documento de rescisão → Preview → autorização → `PortaSecullum.marcar_demitido` (já existe como função) → baixa espelhada no cadastro interno.

## 4. Gate humano (por que isto não foi implementado agora)

- O PontoWeb já tem credencial real configurada (`SECULLUM_USUARIO`/`SECULLUM_SENHA`, nomes de variável, nunca valor). Qualquer chamada de escrita é ação externa de produção — proibida por padrão (`CLAUDE.md` §6) até autorização de fase específica, que declare objetivo, sistema (PontoWeb), classe de escrita (cadastro/demissão), limites e critério de rollback.
- Um cadastro errado (local de trabalho errado, por exemplo) tem custo operacional real e não é uma reversão de um clique.
- A regra de "de onde vem o local de trabalho" é decisão de negócio, não dedutível com segurança do código existente.

## 5. Próximos passos autônomos (sem gate)

Posso, sem pedir autorização adicional:
- desenhar o contrato `PortaSecullum` (Protocol) e o adapter sobre `secullum_ponto.py`, em modo **dry-run/shadow**, do mesmo jeito que a distribuição documental tem `ExecutorAcaoDryRun`;
- ligar o gatilho automático até o ponto de Preview (nunca até a chamada real);
- deixar a pergunta de negócio (origem do local de trabalho) registrada e visível no relatório, para vocês decidirem quando quiserem.

## 6. Escopo maior (registrado para não perder)

O operador também sinalizou necessidade futura de integração com banco (extratos, movimentação financeira) e outros sistemas de ponto. Mesmo princípio se aplica a cada um: mapear o que já existe no legado antes de construir, nunca criar acesso de produção sem gate, e cada integração nova é uma capacidade do Orquestrador, nunca um sistema paralelo.
