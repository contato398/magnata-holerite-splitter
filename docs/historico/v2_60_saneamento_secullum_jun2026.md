---
name: v2_60_saneamento_secullum_jun2026
description: "v2.58-2.60: saneamento de 20 'invisíveis' Secullum — schema real do POST (camelCase+descrição), limite de plano 85 ativos"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Saneamento em massa (27/06/2026, ordem da diretoria) dos 20 colaboradores
Ativos no Airtable sem nenhum registro na Secullum (achado da auditoria
v2.57, ver [[v2_55_gravacao_real_jun2026]]).

## Achado crítico: schema do POST é diferente do GET
`secullum_ponto.sincronizar_funcionario` SEMPRE esteve errado (nunca tinha
sido testado ponta a ponta com uma criação real — só dry_run ou casos já
existentes). Confirmado no Swagger oficial
(`pontowebintegracaoexterna.secullum.com.br/swagger/v1/swagger.json`):
POST `/IntegracaoExterna/Funcionarios` usa o schema
**`FuncionarioIntegracaoExternaPost`** — camelCase, bem diferente do shape
PascalCase devolvido pelo GET (que é só leitura):
- `nome`, `cpf`, `numeroFolha`, `numeroPis`, `admissao` (não Nome/Cpf/
  NumeroFolha/Pis/DataAdmissao).
- **Função e Departamento são por TEXTO da descrição**
  (`funcaoDescricao`/`departamentoDescricao`), não por Id.
- **Horário é por `horarioNumero`** (campo "Numero", não "Id" — embora
  sempre coincidam nos dados reais checados).
- `empresaId` (int) sozinho não bastou — precisou combinar com
  **`empresaCnpjCpf`** (string, CNPJ real "17987187000161") pro campo
  Empresa parar de dar 400 "obrigatório".
- POST de sucesso pode devolver **corpo vazio** (sem o Id) — buscar de
  novo por CPF (`buscar_funcionario_secullum_por_cpf`) pra confirmar/obter
  o Id real.

Mapa Cargo (Airtable) → (funcaoDescricao, departamentoDescricao) levantado
a partir dos 88 funcionários já cadastrados (`/secullum/debug?listar_referencias=1`).

## Achado crítico: limite de plano de 85 funcionários ATIVOS
Depois de 5 sucessos (1 já existente reconfirmado + 4 criações novas), a
Secullum passou a rejeitar com `quantidadePessoasAtivas: "O limite de 85
funcionários cadastrados foi atingido"`. **Não é bug — é limite
contratual/billing da conta Secullum.** Restam 13 dos 20 "invisíveis"
bloqueados até a diretoria fazer upgrade do plano ou desativar
funcionários inativos na própria Secullum pra liberar vaga.

## Resultado final (27/06/2026)
- 2 já existiam na Secullum (Antonio Marcelino Valerio Id=215, Lucas
  Rodrigues Machado Id=228) — não precisaram criação.
- 5 criados/confirmados com sucesso: Jose Jacson Biscaia Martins (259),
  Sidney Salvadori Junior (260), Guilherme Marques de Almeida (261),
  Cinthia Renata Bastida Flor de Souza (262), Wilza Aparecida de Souza (263).
  Airtable atualizado (Secullum ID + Status="Sincronizado") e confirmado.
- 13 bloqueados pelo limite de plano: Angela Aparecida de Lima, Lucas
  Eduardo Soares, Patrick Adriel Campina Correia, Leandro Faustino
  Silveira, Rafael Batista Elias, Inara Rafaaeli de Oliveira Muni, Adriano
  Francisco Pedroso de Oliveira, Joao Antonio Crepalde, Davi Leme dos
  Santos, Pedro Gabriel Kurnich, Luciano Nunes dos Santos, Leonardo
  Francisco Santos de Lima, Hebert Pereira de Carvalho.

## Pendência
Esses 13 ficam com "Status de Sincronização" ainda não preenchido (ou
"Pendente") até a diretoria resolver o limite de plano. Quando resolver,
rodar de novo `POST /sync-funcionarios/importar-cpfs` com os mesmos 13
CPFs (idempotente — `sincronizar_funcionario` já checa se existe antes de
criar). Horário usado pra todos foi o placeholder "comercial" (Numero=6,
"semanal 07h as 17h..."); ajuste fino de escala real é etapa separada,
ainda não feita.
